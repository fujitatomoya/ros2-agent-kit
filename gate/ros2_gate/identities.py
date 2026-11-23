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

"""Known agent identities that must never author or sign off a commit."""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Dict, List


class AgentIdentities:

    def __init__(self, emails: List[str], names: List[str]):
        self.emails = [e.lower() for e in emails]
        self.names = [n.lower() for n in names]

    @classmethod
    def load(cls, path: Path) -> 'AgentIdentities':
        data: Dict = json.loads(path.read_text(encoding='utf-8'))
        return cls(data.get('emails', []), data.get('names', []))

    def matches(self, name: str, email: str) -> bool:
        name_l = name.strip().lower()
        email_l = email.strip().lower()
        if any(fnmatch.fnmatchcase(email_l, pat) for pat in self.emails):
            return True
        return any(fnmatch.fnmatchcase(name_l, pat) for pat in self.names)
