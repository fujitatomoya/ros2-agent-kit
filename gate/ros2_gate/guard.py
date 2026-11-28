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
from . import evidence, gitinfo
from .identities import AgentIdentities
from .profile import Profile

ALLOW = 'allow'
BLOCK = 'block'
ASK = 'ask'  # allowed only after the human confirms the exact command

_SEPARATORS = {'&&', '||', ';', '|', '(', ')', '&', ';;'}

# gh subcommands that create or change content on GitHub (G3), in two kinds.
# Submission creates or changes a pull request or an issue: the human wrote the text and
# stays responsible, so the agent may run the command once the human confirms it.
# Discussion posts a comment or a review, which the OSRF policy reserves for the human.
_GH_PR_SUBMISSION = {'create', 'edit', 'close', 'reopen', 'merge', 'ready', 'lock', 'unlock',
                     'update-branch'}
_GH_PR_DISCUSSION = {'comment', 'review'}
_GH_ISSUE_SUBMISSION = {'create', 'edit', 'close', 'reopen', 'delete', 'pin', 'unpin',
                        'transfer', 'lock', 'unlock', 'develop'}
_GH_ISSUE_DISCUSSION = {'comment'}
_GH_COMMENTING_VERBS = {'close', 'reopen'}  # these accept -c/--comment and then post a reply
_GH_API_BODY_FLAGS = {'-f', '--raw-field', '-F', '--field', '--input'}
_GH_API_DISCUSSION_WORDS = ('comment', 'review', 'replies', 'reaction')
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

    @property
    def needs_confirmation(self) -> bool:
        return self.decision == ASK

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
    if sub == 'push':
        return _guard_git_push(args, profile, identities, cwd)
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


def _guard_git_push(args: List[str], profile: Profile, identities: AgentIdentities,
                    cwd: Optional[str]) -> Decision:
    """G2: every commit since the merge base passes, and evidence exists for the current tree."""
    if any(a in ('--dry-run', '-n', '--delete', '-d', '--tags') for a in args):
        return Decision(ALLOW)
    if not gitinfo.is_repository(cwd):
        return Decision(ALLOW)
    base = commit_checks.default_base(profile, cwd)
    if base is not None:
        report = commit_checks.check_range(profile, identities, base=base, cwd=cwd)
        if not report.ok:
            first = next(f for f in report.findings if f.level == 'error')
            return Decision(BLOCK, 'G2', f'a commit on this branch fails G1: {first.message}'
                                         + (f' (fix: {first.fix})' if first.fix else ''))
    required = [k for k in ('build', 'test')
                if profile.rule(f'verification.{"tests" if k == "test" else k}') == 'required']
    if not required:
        return Decision(ALLOW)
    have = evidence.successful_kinds(cwd)
    missing = [k for k in required if k not in have]
    if missing:
        hint = {'build': 'ros2-gate run -- colcon build --packages-select <pkg>',
                'test': 'ros2-gate run -- colcon test --packages-select <pkg>'}
        return Decision(BLOCK, 'G2', 'no successful ' + ' and '.join(missing) + ' evidence for the '
                                     'current tree; run ' + '; '.join(hint[k] for k in missing)
                                     + ' and then push')
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


def _gh_api_is_discussion(args: List[str]) -> bool:
    """A mutating gh api call that touches comments or reviews, judged by its visible text."""
    joined = ' '.join(args).lower()
    return any(word in joined for word in _GH_API_DISCUSSION_WORDS)


def _has_comment_flag(tokens: List[str]) -> bool:
    return any(t in ('-c', '--comment') or t.startswith('--comment=') for t in tokens)


def _classify_gh(tokens: List[str]) -> Tuple[Optional[str], str]:
    """Return ``(kind, description)``; kind is ``submission``, ``discussion``, or None."""
    positional = [t for t in tokens[1:] if not t.startswith('-')]
    if not positional:
        return None, ''
    group = positional[0]
    verb = positional[1] if len(positional) > 1 else ''
    for name, submission, discussion in (('pr', _GH_PR_SUBMISSION, _GH_PR_DISCUSSION),
                                         ('issue', _GH_ISSUE_SUBMISSION, _GH_ISSUE_DISCUSSION)):
        if group != name:
            continue
        if verb in discussion:
            return 'discussion', f'gh {name} {verb}'
        if verb in submission:
            if verb in _GH_COMMENTING_VERBS and _has_comment_flag(tokens):
                return 'discussion', f'gh {name} {verb} with a comment'
            return 'submission', f'gh {name} {verb}'
    if group == 'api' and _gh_api_is_mutation(tokens[2:]):
        if _gh_api_is_discussion(tokens[2:]):
            return 'discussion', 'a gh api call that writes a comment or a review'
        return 'submission', 'a mutating gh api call'
    return None, ''


def _guard_gh(tokens: List[str], profile: Profile) -> Decision:
    """G3: what the agent may send to GitHub, and whether the human confirms it first."""
    kind, what = _classify_gh(tokens)
    if kind is None:
        return Decision(ALLOW)
    mode = profile.posting(kind)
    if mode == 'allow':
        return Decision(ALLOW)
    if mode == 'confirm':
        if kind == 'submission':
            duty = ('by confirming, the human states that they wrote the description, understand '
                    'every change, and verified it')
        else:
            duty = 'by confirming, the human states that they wrote this text by hand'
        return Decision(ASK, 'G3', f"{what} goes out under the human's name, so profile "
                                   f'{profile.id} requires the human to confirm the exact '
                                   f'command first; {duty}')
    if kind == 'discussion':
        return Decision(BLOCK, 'G3', f'{what} is not allowed for an agent under profile '
                                     f'{profile.id}: replies in a review or an issue thread are '
                                     "the human's to write by hand and to post; tell the human "
                                     'what was done and let them reply')
    return Decision(BLOCK, 'G3', f'{what} is not allowed for an agent under profile '
                                 f'{profile.id}: the profile requires the human to write and '
                                 'submit this; prepare the text in a local file, show the exact '
                                 'command, and let the human run it')


def guard(command: str, profile: Profile, identities: AgentIdentities,
          cwd: Optional[str] = None) -> Decision:
    """Decide on a command line: the first block wins, then the first ask, else allow."""
    pending: Optional[Decision] = None
    for seg in segments(command):
        seg = _strip_prefixes(seg)
        if not seg:
            continue
        prog = seg[0].rsplit('/', 1)[-1]
        if prog in ('bash', 'sh', 'zsh') and '-c' in seg:
            inner = seg[seg.index('-c') + 1] if seg.index('-c') + 1 < len(seg) else ''
            d = guard(inner, profile, identities, cwd)
        elif prog == 'git':
            d = _guard_git(seg, profile, identities, cwd)
        elif prog == 'gh':
            d = _guard_gh(seg, profile)
        else:
            continue
        if d.allowed:
            continue
        if d.command is None:
            d.command = ' '.join(seg)
        if not d.needs_confirmation:
            return d
        if pending is None:
            pending = d
    return pending or Decision(ALLOW)
