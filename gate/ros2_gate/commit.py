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

"""G1: commit identity, sign-off, and disclosure trailer checks."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from . import gitinfo
from .findings import Report
from .identities import AgentIdentities
from .profile import Profile

GATE = 'G1'

_TRAILER_RE = re.compile(r'^(?P<key>[A-Za-z][A-Za-z0-9-]*):\s*(?P<value>.*?)\s*$')
_SIGNOFF_RE = re.compile(r'^(?P<name>.*?)\s*<(?P<email>[^<>]+)>\s*$')
# Assisted-by: {agent}:{model} [{tools}]
_ASSISTED_RE = re.compile(r'^(?P<agent>[^:\[\]]+?):(?P<model>[^\s\[\]]+)(?:\s+\[(?P<tools>[^\]]*)\])?$')

SIGNOFF_KEY = 'signed-off-by'
ASSISTED_KEY = 'assisted-by'
COAUTHOR_KEY = 'co-authored-by'


def parse_trailers(message: str) -> List[Tuple[str, str]]:
    """Return ``(key, value)`` for every trailer-shaped line in the message.

    Keys are lower-cased. Lines inside the subject are ignored.
    """
    lines = message.strip().split('\n')
    result: List[Tuple[str, str]] = []
    for line in lines[1:]:
        m = _TRAILER_RE.match(line)
        if m:
            result.append((m.group('key').lower(), m.group('value')))
    return result


def signoffs(message: str) -> List[str]:
    return [v for k, v in parse_trailers(message) if k == SIGNOFF_KEY]


def has_signoff(message: str) -> bool:
    return bool(signoffs(message))


def check_message(message: str, author_name: str, author_email: str,
                  profile: Profile, identities: AgentIdentities,
                  subject: Optional[str] = None) -> Report:
    """Check one commit message against the profile. ``subject`` labels findings."""
    report = Report()
    trailers = parse_trailers(message)
    offs = [v for k, v in trailers if k == SIGNOFF_KEY]
    assisted = [v for k, v in trailers if k == ASSISTED_KEY]
    coauthors = [v for k, v in trailers if k == COAUTHOR_KEY]

    dco_required = bool(profile.rule('dco.required', False))
    must_match = bool(profile.rule('dco.signoff_must_match_author', True))
    forbid_agent = bool(profile.rule('dco.forbid_agent_identity', False))
    trailer_rule = profile.rule('ai_disclosure.commit_trailer', 'optional')
    trailer_format = profile.rule('ai_disclosure.trailer_format',
                                  'Assisted-by: {agent}:{model} [{tools}]')

    if not message.strip():
        report.error(GATE, 'empty commit message', subject=subject)
        return report

    if forbid_agent and identities.matches(author_name, author_email):
        report.error(
            GATE,
            f'commit author "{author_name} <{author_email}>" is an agent identity',
            fix='set git user.name and user.email to the human contributor and re-commit '
                '(git commit --amend --reset-author -s --no-edit)',
            subject=subject)

    if dco_required and not offs:
        report.error(
            GATE, 'missing Signed-off-by trailer (DCO sign-off is required)',
            fix='git commit --amend -s --no-edit', subject=subject)

    matched_author = False
    for value in offs:
        m = _SIGNOFF_RE.match(value)
        if not m:
            report.error(GATE, f'malformed sign-off "{value}", expected "Name <email>"',
                         subject=subject)
            continue
        name, email = m.group('name'), m.group('email')
        if forbid_agent and identities.matches(name, email):
            report.error(
                GATE, f'sign-off "{value}" is an agent identity; the DCO is a personal attestation',
                fix='remove the agent sign-off and sign off as the human contributor '
                    '(git commit --amend -s --no-edit)',
                subject=subject)
            continue
        if email.lower() == author_email.lower():
            matched_author = True
            if name.strip() != author_name.strip():
                report.warning(
                    GATE,
                    f'sign-off name "{name}" differs from author name "{author_name}"',
                    subject=subject)
    if offs and must_match and not matched_author:
        report.error(
            GATE,
            f'no sign-off matches the commit author <{author_email}> '
            f'(found: {", ".join(offs)})',
            fix='sign off with the same identity as the author '
                '(git commit --amend --reset-author -s --no-edit)',
            subject=subject)

    for value in assisted:
        if not _ASSISTED_RE.match(value):
            report.error(
                GATE, f'malformed Assisted-by trailer "{value}"',
                fix=f'use the format "{trailer_format}", for example '
                    '"Assisted-by: Claude:claude-fable-5-1"',
                subject=subject)

    agent_coauthors = []
    for value in coauthors:
        m = _SIGNOFF_RE.match(value)
        if m and identities.matches(m.group('name'), m.group('email')):
            agent_coauthors.append(value)
    if agent_coauthors and not assisted:
        report.info(
            GATE,
            'agent named in Co-authored-by is accepted as disclosure; Assisted-by is preferred',
            subject=subject)

    disclosed = bool(assisted or agent_coauthors)
    if trailer_rule == 'required' and not disclosed:
        report.error(
            GATE, 'missing AI disclosure trailer',
            fix=f'add "{trailer_format}" to the commit message', subject=subject)
    elif trailer_rule == 'recommended' and not disclosed:
        report.info(
            GATE,
            'no AI disclosure trailer; add one if an agent assisted with this commit',
            subject=subject)
    return report


def check_commit(ref: str, profile: Profile, identities: AgentIdentities,
                 cwd: Optional[str] = None) -> Report:
    commit = gitinfo.commit_info(ref, cwd)
    label = f'{commit.sha[:10]} {commit.subject}'
    return check_message(commit.message, commit.author_name, commit.author_email,
                         profile, identities, subject=label)


def check_message_file(path: str, profile: Profile, identities: AgentIdentities,
                       cwd: Optional[str] = None) -> Report:
    """For the ``commit-msg`` git hook: the message file plus the identity git will use."""
    with open(path, encoding='utf-8', errors='replace') as fh:
        raw = fh.read()
    message = '\n'.join(line for line in raw.split('\n') if not line.startswith('#'))
    name, email = gitinfo.author_ident(cwd)
    return check_message(message, name, email, profile, identities, subject=path)


def default_base(profile: Profile, cwd: Optional[str] = None) -> Optional[str]:
    """Pick the base ref for ``check-range``: the profile target branch, then common defaults."""
    candidates: List[str] = []
    target = profile.rule('branching.target')
    if target:
        candidates += [f'upstream/{target}', f'origin/{target}', target]
    candidates += ['upstream/HEAD', 'origin/HEAD', 'origin/main', 'origin/master', 'main', 'master']
    for ref in candidates:
        if gitinfo.ref_exists(ref, cwd):
            base = gitinfo.merge_base(ref, 'HEAD', cwd)
            if base:
                return base
    return None


def check_range(profile: Profile, identities: AgentIdentities, base: Optional[str] = None,
                head: str = 'HEAD', cwd: Optional[str] = None) -> Report:
    report = Report()
    if base is None:
        base = default_base(profile, cwd)
        if base is None:
            report.error(GATE, 'cannot determine a base ref; pass --base <ref>')
            return report
    shas = gitinfo.rev_list(base, head, cwd)
    if not shas:
        report.info(GATE, f'no commits between {base[:10]} and {head}')
        return report
    for sha in shas:
        report.extend(check_commit(sha, profile, identities, cwd))
    report.info(GATE, f'checked {len(shas)} commit(s) since {base[:10]}')
    return report
