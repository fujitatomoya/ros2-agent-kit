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

"""Result types shared by every check."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional

ERROR = 'error'
WARNING = 'warning'
INFO = 'info'


@dataclass
class Finding:
    """One check result. ``gate`` names the design gate, for example ``G1``."""

    level: str
    gate: str
    message: str
    fix: Optional[str] = None
    subject: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Report:
    """A list of findings plus the overall verdict."""

    findings: List[Finding] = field(default_factory=list)

    def add(self, level: str, gate: str, message: str, fix: Optional[str] = None,
            subject: Optional[str] = None) -> None:
        self.findings.append(Finding(level, gate, message, fix, subject))

    def error(self, gate: str, message: str, fix: Optional[str] = None,
              subject: Optional[str] = None) -> None:
        self.add(ERROR, gate, message, fix, subject)

    def warning(self, gate: str, message: str, fix: Optional[str] = None,
                subject: Optional[str] = None) -> None:
        self.add(WARNING, gate, message, fix, subject)

    def info(self, gate: str, message: str, fix: Optional[str] = None,
             subject: Optional[str] = None) -> None:
        self.add(INFO, gate, message, fix, subject)

    def extend(self, other: 'Report') -> None:
        self.findings.extend(other.findings)

    @property
    def ok(self) -> bool:
        return not any(f.level == ERROR for f in self.findings)

    def to_dict(self) -> dict:
        return {'ok': self.ok, 'findings': [f.to_dict() for f in self.findings]}

    def format_text(self) -> str:
        lines = []
        for f in self.findings:
            prefix = {ERROR: 'error', WARNING: 'warning', INFO: 'note'}[f.level]
            where = f' [{f.subject}]' if f.subject else ''
            lines.append(f'{prefix} ({f.gate}){where}: {f.message}')
            if f.fix:
                lines.append(f'    fix: {f.fix}')
        lines.append('ros2-gate: PASS' if self.ok else 'ros2-gate: FAIL')
        return '\n'.join(lines)
