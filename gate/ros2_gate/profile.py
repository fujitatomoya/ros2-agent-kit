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

"""Policy profiles: rules as data, selected by the git remote.

Precedence: ``ROS2_GATE_PROFILE`` environment variable, then the first profile
whose remote pattern matches any remote of the working repository (``upstream``
is checked before ``origin``), then the ``dco`` fallback when the repository
looks like a DCO project, then the ``default`` fallback.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import gitinfo
from .identities import AgentIdentities

KIT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_POLICY_DIR = KIT_ROOT / 'policy'


def policy_dir() -> Path:
    env = os.environ.get('ROS2_GATE_POLICY_DIR')
    return Path(env).expanduser() if env else DEFAULT_POLICY_DIR


@dataclass
class Profile:
    id: str
    data: Dict[str, Any]
    matched_remote: Optional[str] = None
    reason: str = ''

    def rule(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data.get('rules', {})
        for key in dotted.split('.'):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    @property
    def description(self) -> str:
        return self.data.get('description', '')

    @property
    def sources(self) -> List[str]:
        return list(self.data.get('sources', []))

    def summary(self) -> str:
        """One line for session-start context."""
        parts = [f'profile {self.id}']
        if self.matched_remote:
            parts.append(f'remote {self.matched_remote}')
        parts.append('DCO required' if self.rule('dco.required') else 'DCO optional')
        parts.append('agent may not post' if not self.rule('authorship.agent_may_post')
                     else 'agent may post')
        target = self.rule('branching.target')
        if target:
            parts.append(f'target branch {target}')
        return '; '.join(parts)


def load_profiles(directory: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    directory = (directory or policy_dir()) / 'profiles'
    profiles: Dict[str, Dict[str, Any]] = {}
    for path in sorted(directory.glob('*.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        profiles[data['id']] = data
    if not profiles:
        raise FileNotFoundError(f'no profiles found in {directory}')
    return profiles


def load_identities(directory: Optional[Path] = None) -> AgentIdentities:
    return AgentIdentities.load((directory or policy_dir()) / 'agent-identities.json')


def load_sources(directory: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    path = (directory or policy_dir()) / 'sources.json'
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8')).get('sources', {})


_DCO_HINT = re.compile(r'Developer Certificate of Origin|Signed-off-by|\bDCO\b', re.I)


def looks_like_dco_repo(top: Path) -> bool:
    candidates = [top / 'DCO', top / 'DCO.md', top / 'DCO.txt']
    if any(c.exists() for c in candidates):
        return True
    for name in ('CONTRIBUTING.md', 'CONTRIBUTING.rst', 'CONTRIBUTING', 'CONTRIBUTING.txt'):
        path = top / name
        if path.exists():
            try:
                if _DCO_HINT.search(path.read_text(encoding='utf-8', errors='replace')):
                    return True
            except OSError:
                pass
    workflows = top / '.github' / 'workflows'
    if workflows.is_dir():
        for wf in workflows.glob('*.y*ml'):
            try:
                if re.search(r'dco', wf.read_text(encoding='utf-8', errors='replace'), re.I):
                    return True
            except OSError:
                pass
    return False


def detect(cwd: Optional[str] = None, override: Optional[str] = None,
           directory: Optional[Path] = None) -> Profile:
    profiles = load_profiles(directory)
    wanted = override or os.environ.get('ROS2_GATE_PROFILE')
    if wanted:
        if wanted not in profiles:
            raise KeyError(f'unknown profile {wanted!r}; known: {", ".join(profiles)}')
        return Profile(wanted, profiles[wanted], reason='explicitly selected')

    remote_urls: List[str] = []
    top: Optional[Path] = None
    if gitinfo.is_repository(cwd):
        top = Path(gitinfo.toplevel(cwd))
        remote_urls = [gitinfo.normalize_remote(url) for _, url in gitinfo.remotes(cwd)]

    for url in remote_urls:
        for pid, data in profiles.items():
            for pattern in data.get('applies_to', {}).get('remotes', []):
                if fnmatch.fnmatchcase(url.lower(), pattern.lower()):
                    return Profile(pid, data, matched_remote=url,
                                   reason=f'remote {url} matches {pattern}')

    by_detect = {d.get('applies_to', {}).get('detect'): pid for pid, d in profiles.items()}
    if top is not None and 'dco' in by_detect and looks_like_dco_repo(top):
        pid = by_detect['dco']
        return Profile(pid, profiles[pid], reason='repository mentions the DCO')
    pid = by_detect.get('default')
    if pid is None:
        raise KeyError('no profile has applies_to.detect == "default"')
    reason = 'no remote matched' if remote_urls else 'not a git repository or no remotes'
    return Profile(pid, profiles[pid], reason=reason)
