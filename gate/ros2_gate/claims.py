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

"""G7: verification claims in an agent message that have no matching evidence."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from . import evidence, gitinfo
from .findings import Report

GATE = 'G7'

_CLAIMS = {
    'test': [
        re.compile(r'\b(?:all\s+|the\s+)?(?:unit\s+|integration\s+)?tests?\s+(?:are\s+|is\s+|now\s+)?'
                   r'(?:pass(?:es|ed|ing)?|succeed(?:ed|s)?|green|ok)\b', re.I),
        re.compile(r'\b(?:colcon\s+test|pytest|ctest)\s+(?:pass(?:es|ed)|succeed(?:ed|s)|is\s+green)\b',
                   re.I),
    ],
    'build': [
        re.compile(r'\b(?:the\s+)?build\s+(?:now\s+)?(?:pass(?:es|ed)|succeed(?:ed|s)|is\s+green|works|'
                   r'completes?\s+(?:successfully|cleanly))\b', re.I),
        re.compile(r'\bcompiles?\s+(?:fine|cleanly|successfully|without\s+(?:errors|warnings))\b', re.I),
        re.compile(r'\b(?:colcon\s+build|cmake)\s+(?:pass(?:es|ed)|succeed(?:ed|s))\b', re.I),
        re.compile(r'\bbuilt\s+successfully\b', re.I),
    ],
    'lint': [
        re.compile(r'\b(?:lint(?:ers?|ing)?|ament_lint|flake8|uncrustify|cpplint)\s+'
                   r'(?:pass(?:es|ed)|is\s+clean|clean|succeed(?:ed|s))\b', re.I),
    ],
}
_MODAL = re.compile(r'\b(?:should|will|would|if|once|after|when|until|make\s+sure|ensure|expect)\b[^.]{0,30}$',
                    re.I)


def find_claims(text: str) -> List[Tuple[str, str]]:
    """``(kind, snippet)`` for every assertion that something passed."""
    found = []
    for kind, patterns in _CLAIMS.items():
        for pat in patterns:
            for m in pat.finditer(text):
                before = text[max(0, m.start() - 40):m.start()]
                if _MODAL.search(before):
                    continue
                found.append((kind, m.group(0)))
    return found


def check_claims(text: str, cwd: Optional[str] = None) -> Report:
    report = Report()
    claims = find_claims(text)
    if not claims:
        return report
    if not gitinfo.is_repository(cwd):
        report.info(GATE, 'verification claims found but no repository to check evidence in')
        return report
    have = evidence.successful_kinds(cwd)
    seen = set()
    for kind, snippet in claims:
        if kind in seen:
            continue
        seen.add(kind)
        if kind in have:
            continue
        if kind == 'lint' and 'test' in have:
            continue
        report.warning(
            GATE,
            f'the message says "{snippet}" but the evidence ledger has no successful {kind} '
            f'command for the current tree',
            fix=f'run it through `ros2-gate run -- <{kind} command>` or correct the statement')
    return report
