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

"""G4: pull request and issue bodies checked against the target repository's templates.

Templates are read, not vendored. Lookup order: an explicit ``--template``,
the repository's own ``.github/`` files, then the organization default that
``tools/fetch_templates.py`` cached under ``$XDG_CACHE_HOME/ros2-agent-kit``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .findings import Report
from .profile import Profile

GATE = 'G4'

_HEADING_RE = re.compile(r'^(?P<hashes>#{1,6})\s+(?P<text>.*?)\s*#*\s*$')
_COMMENT_RE = re.compile(r'<!--.*?-->', re.S)
_FIXES_RE = re.compile(r'\b(?:fixes|closes|resolves)\s*:?\s*(?:#(?P<num>\d+)|'
                       r'(?P<url>https?://github\.com/[\w.-]+/[\w.-]+/issues/(?P<num2>\d+)))',
                       re.I)
_FIXES_PLACEHOLDER_RE = re.compile(r'fixes\s*#\s*\(issue\)', re.I)
_PLACEHOLDER_TOKEN_RE = re.compile(r'<[A-Z][A-Z0-9 _-]{2,}>')
_GENAI_RE = re.compile(r'generative\s*ai', re.I)
_NO_RESPONSE = '_no response_'


def cache_dir() -> Path:
    base = os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache')
    return Path(base) / 'ros2-agent-kit' / 'templates'


def strip_comments(text: str) -> str:
    return _COMMENT_RE.sub('', text)


def normalize_heading(text: str) -> str:
    return re.sub(r'\s+', ' ', text.strip().rstrip(':').strip()).lower()


@dataclass
class Section:
    heading: Optional[str]
    level: int
    body: str

    @property
    def content(self) -> str:
        return strip_comments(self.body).strip()

    @property
    def is_empty(self) -> bool:
        return self.content == '' or self.content.lower() == _NO_RESPONSE


def split_sections(text: str) -> List[Section]:
    sections: List[Section] = [Section(None, 0, '')]
    in_fence = False
    for line in text.split('\n'):
        if line.strip().startswith('```'):
            in_fence = not in_fence
        m = None if in_fence else _HEADING_RE.match(line)
        if m:
            sections.append(Section(m.group('text'), len(m.group('hashes')), ''))
        else:
            sections[-1].body += line + '\n'
    return sections


def section_map(text: str) -> Dict[str, Section]:
    return {normalize_heading(s.heading): s for s in split_sections(text) if s.heading}


# --- pull request template -------------------------------------------------

_PR_TEMPLATE_NAMES = [
    '.github/PULL_REQUEST_TEMPLATE.md', '.github/pull_request_template.md',
    'PULL_REQUEST_TEMPLATE.md', 'pull_request_template.md',
    'docs/PULL_REQUEST_TEMPLATE.md', 'docs/pull_request_template.md',
]


def find_pr_template(repo_root: Optional[Path], org: Optional[str] = None) -> Optional[Path]:
    if repo_root is not None:
        for name in _PR_TEMPLATE_NAMES:
            path = repo_root / name
            if path.is_file():
                return path
    if org:
        for name in ('PULL_REQUEST_TEMPLATE.md', 'pull_request_template.md'):
            path = cache_dir() / org / '.github' / name
            if path.is_file():
                return path
    return None


def check_pr_body(body: str, template: Optional[str], profile: Profile,
                  issue: Optional[int] = None) -> Report:
    report = Report()
    disclosure = profile.rule('ai_disclosure.pull_request', 'optional')
    if not body.strip():
        report.error(GATE, 'PR body is empty')
        return report

    body_sections = section_map(body)
    if template:
        template_sections = [s for s in split_sections(template) if s.heading]
        for idx, ts in enumerate(template_sections):
            key = normalize_heading(ts.heading)
            bs = body_sections.get(key)
            if bs is None:
                report.error(GATE, f'template section "{ts.heading}" is missing from the PR body',
                             fix='keep every heading of the PR template, even when a section is empty')
                continue
            required = idx == 0 or (disclosure == 'required' and _GENAI_RE.search(ts.heading))
            content = _FIXES_PLACEHOLDER_RE.sub('', bs.content).strip()
            if required and (bs.is_empty or not content):
                what = 'the AI disclosure' if _GENAI_RE.search(ts.heading) else 'the description'
                who = ('state the tool and model, or "No"' if _GENAI_RE.search(ts.heading)
                       else 'the human contributor writes it')
                report.error(GATE, f'section "{ts.heading}" is empty; {what} is required ({who})')
            if bs.content and _PLACEHOLDER_TOKEN_RE.search(bs.content):
                report.error(GATE, f'section "{ts.heading}" still contains a template placeholder')
    else:
        report.warning(GATE, 'no PR template found; checked generic rules only',
                       fix='pass --template <file> or run tools/fetch_templates.py to cache '
                           'the organization default')
        if disclosure == 'required' and not _GENAI_RE.search(body):
            report.error(GATE, 'no "Generative AI" disclosure section in the PR body')

    plain = strip_comments(body)
    if _FIXES_PLACEHOLDER_RE.search(plain):
        report.error(GATE, 'the "Fixes # (issue)" placeholder was left as is',
                     fix='replace it with "Fixes #<number>" or remove the line')
    fixes = [m.group('num') or m.group('num2') for m in _FIXES_RE.finditer(plain)]
    if issue is not None:
        if str(issue) not in fixes:
            report.error(GATE, f'PR body does not reference the issue with "Fixes #{issue}"')
    elif not fixes:
        report.info(GATE, 'no "Fixes #" reference; fine only if this PR has no issue')
    return report


# --- issue forms -----------------------------------------------------------

@dataclass
class FormField:
    type: str
    id: str = ''
    label: str = ''
    required: bool = False
    value: str = ''
    placeholders: List[str] = field(default_factory=list)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
        return value[1:-1]
    return value


def parse_issue_form(text: str) -> List[FormField]:
    """Parse the subset of a GitHub issue form that the body check needs.

    This is a line scanner for the fixed shape GitHub accepts, not a YAML parser.
    """
    fields: List[FormField] = []
    current: Optional[FormField] = None
    block_key: Optional[str] = None
    block_indent = 0
    block_lines: List[str] = []

    def flush_block() -> None:
        nonlocal block_key, block_lines
        if current is not None and block_key:
            content = '\n'.join(block_lines)
            if block_key == 'value':
                current.value = content
            current.placeholders += _PLACEHOLDER_TOKEN_RE.findall(content)
        block_key, block_lines = None, []

    for raw in text.split('\n'):
        if block_key is not None:
            indent = len(raw) - len(raw.lstrip(' '))
            if raw.strip() == '' or indent > block_indent:
                block_lines.append(raw.strip())
                continue
            flush_block()
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip(' '))
        if stripped.startswith('- type:'):
            current = FormField(type=_unquote(stripped.split(':', 1)[1]))
            fields.append(current)
            continue
        if current is None or ':' not in stripped:
            continue
        key, _, value = stripped.partition(':')
        key, value = key.strip(), value.strip()
        if key == 'id':
            current.id = _unquote(value)
        elif key == 'label':
            current.label = _unquote(value)
        elif key == 'required':
            current.required = value.lower() == 'true'
        elif key in ('value', 'placeholder'):
            if value in ('|', '|-', '>', '>-', '|+'):
                block_key, block_indent, block_lines = key, indent, []
            else:
                content = _unquote(value)
                if key == 'value':
                    current.value = content
                current.placeholders += _PLACEHOLDER_TOKEN_RE.findall(content)
    flush_block()
    return [f for f in fields if f.type != 'markdown']


def find_issue_template(repo_root: Optional[Path], name: str,
                        org: Optional[str] = None) -> Optional[Path]:
    """Locate ``.github/ISSUE_TEMPLATE/<name>.yml`` (or ``.md``) locally, then in the cache."""
    stems = [name]
    if '.' not in name:
        stems = [f'{name}.yml', f'{name}.yaml', f'{name}.md']
    roots: List[Path] = []
    if repo_root is not None:
        roots.append(repo_root)
    if org:
        roots.append(cache_dir() / org)
    for root in roots:
        for stem in stems:
            path = root / '.github' / 'ISSUE_TEMPLATE' / stem
            if path.is_file():
                return path
    return None


def check_issue_body(body: str, form: List[FormField], profile: Profile) -> Report:
    report = Report()
    disclosure = profile.rule('ai_disclosure.issue', 'optional')
    if not body.strip():
        report.error(GATE, 'issue body is empty')
        return report
    sections = section_map(body)
    for f in form:
        if not f.label:
            continue
        key = normalize_heading(f.label)
        sec = sections.get(key)
        genai = bool(_GENAI_RE.search(f.label))
        required = f.required or (genai and disclosure == 'required')
        if sec is None:
            if required:
                why = 'required by the template' if f.required else 'required by the profile'
                report.error(GATE, f'field "{f.label}" is missing ({why})',
                             fix=f'add a "### {f.label}" heading with the content')
            continue
        if required and sec.is_empty:
            report.error(GATE, f'field "{f.label}" is empty')
            continue
        for token in f.placeholders:
            if token in sec.content:
                report.error(GATE, f'field "{f.label}" still contains the placeholder {token}')
    return report


def check_issue_body_markdown(body: str, template: str, profile: Profile) -> Report:
    """Legacy Markdown issue templates: every template heading must exist and be non-empty."""
    report = Report()
    sections = section_map(body)
    for ts in split_sections(template):
        if not ts.heading:
            continue
        bs = sections.get(normalize_heading(ts.heading))
        if bs is None:
            report.error(GATE, f'template section "{ts.heading}" is missing from the issue body')
        elif bs.is_empty:
            report.error(GATE, f'section "{ts.heading}" is empty')
    return report
