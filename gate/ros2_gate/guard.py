# Copyright 2026 Tomoya Fujita
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Decide whether a shell command is allowed under the active profile.

Only ``git`` and ``gh`` invocations are inspected. Everything else is allowed
so the gate stays narrow and fast next to other plugins' hooks.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import List, Optional, Tuple

from . import commit as commit_checks
from . import gitinfo
from .identities import AgentIdentities
from .profile import Profile

ALLOW = 'allow'
BLOCK = 'block'

_SEPARATORS = {'&&', '||', ';', '|', '(', ')', '&', ';;'}

# gh subcommands that create or change content on GitHub (G3).
_GH_PR_MUTATIONS = {'create', 'comment', 'review', 'edit', 'close', 'reopen', 'merge', 'ready',
                    'lock', 'unlock', 'update-branch'}
_GH_ISSUE_MUTATIONS = {'create', 'comment', 'edit', 'close', 'reopen', 'delete', 'pin', 'unpin',
                       'transfer', 'lock', 'unlock', 'develop'}
_GH_API_BODY_FLAGS = {'-f', '--raw-field', '-F', '--field', '--input'}
_GIT_COMMIT_VALUE_FLAGS = {'-m', '--message', '-F', '--file', '-C', '--reuse-message',
                           '-c', '--reedit-message', '--author', '--date', '-t', '--template',
                           '--fixup', '--squash', '--trailer', '--cleanup', '--pathspec-from-file'}


@dataclass
class Decision:
    decision: str
    gate: Optional[str] = None
    reason: Optional[str] = None
    command: Optional[str] = None

    @property
    def allowed(self) -> bool:
        return self.decision == ALLOW

    def to_dict(self) -> dict:
        d = {'decision': self.decision}
        if self.gate:
            d['gate'] = self.gate
        if self.reason:
            d['reason'] = self.reason
        if self.command:
            d['command'] = self.command
        return d


def tokenize(command: str) -> List[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        # Unbalanced quotes: fall back to a plain split so we still see the verbs.
        return command.split()


def segments(command: str) -> List[List[str]]:
    """Split a compound command line into simple commands."""
    result: List[List[str]] = []
    current: List[str] = []
    for tok in tokenize(command):
        if tok in _SEPARATORS:
            if current:
                result.append(current)
            current = []
        else:
            current.append(tok)
    if current:
        result.append(current)
    return result


def _strip_prefixes(tokens: List[str]) -> List[str]:
    """Drop ``sudo``, ``env VAR=x``, ``time``, ``nice`` and leading assignments."""
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ('sudo', 'env', 'time', 'nice', 'command', 'exec', 'nohup'):
            i += 1
            continue
        if '=' in tok and not tok.startswith('-') and tok.split('=', 1)[0].isidentifier():
            i += 1
            continue
        break
    return tokens[i:]


def _git_subcommand(tokens: List[str]) -> Tuple[Optional[str], List[str], dict]:
    """Return ``(subcommand, args_after_it, global_config_overrides)`` for a git command."""
    overrides = {}
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok == '-c' and i + 1 < len(tokens):
            key, _, value = tokens[i + 1].partition('=')
            overrides[key.lower()] = value
            i += 2
            continue
        if tok.startswith('-c') and len(tok) > 2 and '=' in tok:
            key, _, value = tok[2:].partition('=')
            overrides[key.lower()] = value
            i += 1
            continue
        if tok in ('-C', '--git-dir', '--work-tree', '--namespace', '--exec-path') and i + 1 < len(tokens):
            i += 2
            continue
        if tok.startswith('-'):
            i += 1
            continue
        return tok, tokens[i + 1:], overrides
    return None, [], overrides


def _parse_git_commit_args(args: List[str]) -> dict:
    """Extract what G1 needs from ``git commit`` arguments."""
    info = {'signoff': False, 'no_signoff': False, 'amend': False, 'no_edit': False,
            'no_verify': False, 'author': None, 'messages': [], 'message_file': None,
            'reuse': None}
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == '--':
            break
        if tok.startswith('--'):
            name, has_eq, value = tok.partition('=')
            if name in ('--signoff',):
                info['signoff'] = True
            elif name == '--no-signoff':
                info['no_signoff'] = True
            elif name == '--amend':
                info['amend'] = True
            elif name == '--no-edit':
                info['no_edit'] = True
            elif name in ('--no-verify',):
                info['no_verify'] = True
            elif name in _GIT_COMMIT_VALUE_FLAGS:
                if not has_eq:
                    value = args[i + 1] if i + 1 < len(args) else ''
                    i += 1
                if name == '--author':
                    info['author'] = value
                elif name == '--message':
                    info['messages'].append(value)
                elif name == '--file':
                    info['message_file'] = value
                elif name in ('--reuse-message', '--reedit-message'):
                    info['reuse'] = value
            i += 1
            continue
        if tok.startswith('-') and len(tok) > 1:
            # Short flag cluster such as -sam "msg" or -sm"msg".
            j = 1
            while j < len(tok):
                ch = tok[j]
                if ch == 's':
                    info['signoff'] = True
                elif ch == 'n':
                    info['no_verify'] = True
                elif ch in 'mFCc':
                    rest = tok[j + 1:]
                    if not rest:
                        rest = args[i + 1] if i + 1 < len(args) else ''
                        i += 1
                    if ch == 'm':
                        info['messages'].append(rest)
                    elif ch == 'F':
                        info['message_file'] = rest
                    else:
                        info['reuse'] = rest
                    break
                j += 1
            i += 1
            continue
        i += 1
    return info


def _message_has_signoff(info: dict, cwd: Optional[str]) -> Optional[bool]:
    """True/False when the message content is knowable, None when it is not."""
    if info['messages']:
        return commit_checks.has_signoff('\n'.join(info['messages']))
    if info['message_file']:
        try:
            with open(info['message_file'], encoding='utf-8', errors='replace') as fh:
                return commit_checks.has_signoff(fh.read())
        except OSError:
            return None
    ref = info['reuse'] or ('HEAD' if info['amend'] and info['no_edit'] else None)
    if ref:
        try:
            return commit_checks.has_signoff(gitinfo.commit_info(ref, cwd).message)
        except gitinfo.GitError:
            return None
    return None


def _guard_git(tokens: List[str], profile: Profile, identities: AgentIdentities,
               cwd: Optional[str]) -> Decision:
    sub, args, overrides = _git_subcommand(tokens)
    if sub != 'commit':
        return Decision(ALLOW)
    info = _parse_git_commit_args(args)

    if info['no_verify'] and not profile.rule('hooks.allow_bypass', False):
        return Decision(BLOCK, 'G1', 'git commit --no-verify bypasses the repository hooks; '
                                     'run the commit without --no-verify and fix what the hooks report')

    # Identity: --author, then -c user.*, then what git would use in cwd.
    name = email = None
    if info['author']:
        try:
            name, email = gitinfo.parse_ident(info['author'])
        except gitinfo.GitError:
            name, email = info['author'], ''
    else:
        try:
            name, email = gitinfo.author_ident(cwd)
        except gitinfo.GitError:
            name, email = None, None
        if 'user.name' in overrides:
            name = overrides['user.name']
        if 'user.email' in overrides:
            email = overrides['user.email']

    if profile.rule('dco.forbid_agent_identity', False):
        if name is None:
            return Decision(BLOCK, 'G1', 'git has no author identity configured; the human '
                                         'contributor must set user.name and user.email first')
        if identities.matches(name, email or ''):
            return Decision(BLOCK, 'G1', f'commit author "{name} <{email}>" is an agent identity; '
                                         'commits must be authored and signed off by the human '
                                         'contributor (set git user.name and user.email)')

    if profile.rule('dco.required', False):
        if info['no_signoff']:
            return Decision(BLOCK, 'G1', 'DCO sign-off is required; remove --no-signoff')
        known = _message_has_signoff(info, cwd)
        if not info['signoff'] and known is not True:
            return Decision(BLOCK, 'G1', 'DCO sign-off is required; add -s (--signoff) to '
                                         'git commit so the Signed-off-by trailer matches the author')
    return Decision(ALLOW)


def _gh_api_is_mutation(args: List[str]) -> bool:
    method = None
    i = 0
    while i < len(args):
        tok = args[i]
        if tok in ('-X', '--method'):
            method = args[i + 1].upper() if i + 1 < len(args) else None
            i += 2
            continue
        if tok.startswith('--method='):
            method = tok.split('=', 1)[1].upper()
        elif tok in _GH_API_BODY_FLAGS or any(tok.startswith(f + '=') for f in _GH_API_BODY_FLAGS):
            if method is None:
                method = 'POST'
        elif tok == 'graphql':
            pass
        i += 1
    if method is None:
        joined = ' '.join(args).lower()
        if 'graphql' in joined and 'mutation' in joined:
            return True
        return False
    return method != 'GET'


def _guard_gh(tokens: List[str], profile: Profile) -> Decision:
    if profile.rule('authorship.agent_may_post', True):
        return Decision(ALLOW)
    positional = [t for t in tokens[1:] if not t.startswith('-')]
    if len(positional) < 1:
        return Decision(ALLOW)
    group = positional[0]
    verb = positional[1] if len(positional) > 1 else ''
    human = ('the profile requires the human to write and submit this; prepare the text in a '
             'local file, show the exact command, and let the human run it')
    if group == 'pr' and verb in _GH_PR_MUTATIONS:
        return Decision(BLOCK, 'G3', f'gh pr {verb} is not allowed for an agent under profile '
                                     f'{profile.id}: {human}')
    if group == 'issue' and verb in _GH_ISSUE_MUTATIONS:
        return Decision(BLOCK, 'G3', f'gh issue {verb} is not allowed for an agent under profile '
                                     f'{profile.id}: {human}')
    if group == 'api' and _gh_api_is_mutation(tokens[2:]):
        return Decision(BLOCK, 'G3', f'mutating gh api calls are not allowed for an agent under '
                                     f'profile {profile.id}: {human}')
    return Decision(ALLOW)


def guard(command: str, profile: Profile, identities: AgentIdentities,
          cwd: Optional[str] = None) -> Decision:
    """Return the first blocking decision for any simple command in ``command``."""
    for seg in segments(command):
        seg = _strip_prefixes(seg)
        if not seg:
            continue
        prog = seg[0].rsplit('/', 1)[-1]
        if prog in ('bash', 'sh', 'zsh') and '-c' in seg:
            inner = seg[seg.index('-c') + 1] if seg.index('-c') + 1 < len(seg) else ''
            d = guard(inner, profile, identities, cwd)
            if not d.allowed:
                return d
            continue
        if prog == 'git':
            d = _guard_git(seg, profile, identities, cwd)
        elif prog == 'gh':
            d = _guard_gh(seg, profile)
        else:
            continue
        if not d.allowed:
            d.command = ' '.join(seg)
            return d
    return Decision(ALLOW)
