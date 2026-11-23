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

import unittest

from tests import helpers
from ros2_gate import commit
from ros2_gate.findings import ERROR, INFO

OSRA = helpers.load_profile('osra-ros2')
APP = helpers.load_profile('app')
IDS = helpers.identities()
NAME, EMAIL = helpers.HUMAN


def errors(report):
    return [f.message for f in report.findings if f.level == ERROR]


class TrailerParsing(unittest.TestCase):

    def test_parses_known_trailers(self):
        msg = ('Fix thing\n\nBody text\n\nSigned-off-by: A <a@x>\n'
               'Assisted-by: Claude:claude-fable-5-1 [Claude Code]\nCo-authored-by: B <b@x>\n')
        keys = [k for k, _ in commit.parse_trailers(msg)]
        self.assertEqual(keys, ['signed-off-by', 'assisted-by', 'co-authored-by'])

    def test_subject_is_not_a_trailer(self):
        self.assertEqual(commit.parse_trailers('rclcpp: fix executor\n'), [])


class CheckMessage(unittest.TestCase):

    def test_clean_commit_passes(self):
        msg = f'Fix executor lifetime\n\nSigned-off-by: {NAME} <{EMAIL}>\n'
        report = commit.check_message(msg, NAME, EMAIL, OSRA, IDS)
        self.assertTrue(report.ok, report.format_text())
        self.assertTrue(any(f.level == INFO and 'disclosure' in f.message for f in report.findings))

    def test_missing_signoff_fails(self):
        report = commit.check_message('Fix thing\n', NAME, EMAIL, OSRA, IDS)
        self.assertFalse(report.ok)
        self.assertIn('missing Signed-off-by', errors(report)[0])

    def test_signoff_must_match_author(self):
        msg = 'Fix\n\nSigned-off-by: Someone Else <else@example.com>\n'
        report = commit.check_message(msg, NAME, EMAIL, OSRA, IDS)
        self.assertTrue(any('does not match' in e or 'no sign-off matches' in e for e in errors(report)))

    def test_agent_author_rejected(self):
        msg = 'Fix\n\nSigned-off-by: Claude <noreply@anthropic.com>\n'
        report = commit.check_message(msg, 'Claude', 'noreply@anthropic.com', OSRA, IDS)
        self.assertTrue(any('agent identity' in e for e in errors(report)))

    def test_agent_signoff_rejected_even_with_human_author(self):
        msg = (f'Fix\n\nSigned-off-by: {NAME} <{EMAIL}>\n'
               'Signed-off-by: Claude <noreply@anthropic.com>\n')
        report = commit.check_message(msg, NAME, EMAIL, OSRA, IDS)
        self.assertTrue(any('agent identity' in e for e in errors(report)))

    def test_human_named_claude_is_not_an_agent(self):
        msg = 'Fix\n\nSigned-off-by: Claude Dupont <claude.dupont@example.org>\n'
        report = commit.check_message(msg, 'Claude Dupont', 'claude.dupont@example.org', OSRA, IDS)
        self.assertTrue(report.ok, report.format_text())

    def test_assisted_by_format(self):
        good = f'Fix\n\nSigned-off-by: {NAME} <{EMAIL}>\nAssisted-by: Claude:claude-fable-5-1 [Claude Code]\n'
        self.assertTrue(commit.check_message(good, NAME, EMAIL, OSRA, IDS).ok)
        bad = f'Fix\n\nSigned-off-by: {NAME} <{EMAIL}>\nAssisted-by: Claude\n'
        report = commit.check_message(bad, NAME, EMAIL, OSRA, IDS)
        self.assertTrue(any('malformed Assisted-by' in e for e in errors(report)))

    def test_coauthored_by_model_is_accepted(self):
        msg = (f'Fix\n\nSigned-off-by: {NAME} <{EMAIL}>\n'
               'Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n')
        report = commit.check_message(msg, NAME, EMAIL, OSRA, IDS)
        self.assertTrue(report.ok, report.format_text())
        self.assertTrue(any('Assisted-by is preferred' in f.message for f in report.findings))

    def test_app_profile_does_not_require_signoff(self):
        report = commit.check_message('Fix\n', NAME, EMAIL, APP, IDS)
        self.assertTrue(report.ok)

    def test_app_profile_allows_agent_identity(self):
        report = commit.check_message('Fix\n', 'Claude', 'noreply@anthropic.com', APP, IDS)
        self.assertTrue(report.ok)

    def test_empty_message(self):
        self.assertFalse(commit.check_message('  \n', NAME, EMAIL, OSRA, IDS).ok)


class CheckRepository(unittest.TestCase):

    def test_check_commit_and_range(self):
        repo = helpers.new_repo()
        base = helpers.commit(repo, 'base', signoff=True)
        helpers.commit(repo, 'good one', signoff=True)
        helpers.commit(repo, 'bad one, no signoff')
        self.assertTrue(commit.check_commit('HEAD~1', OSRA, IDS, repo).ok)
        self.assertFalse(commit.check_commit('HEAD', OSRA, IDS, repo).ok)
        report = commit.check_range(OSRA, IDS, base=base, cwd=repo)
        self.assertFalse(report.ok)
        self.assertEqual(len(errors(report)), 1)
        self.assertTrue(any('checked 2 commit' in f.message for f in report.findings))

    def test_range_default_base_uses_target_branch(self):
        repo = helpers.new_repo()
        helpers.commit(repo, 'base', signoff=True)
        helpers.git(repo, 'branch', 'origin/rolling')  # a local branch named like the remote ref
        helpers.git(repo, 'checkout', '-q', '-b', 'feature')
        helpers.commit(repo, 'feature work', signoff=True)
        report = commit.check_range(OSRA, IDS, cwd=repo)
        self.assertTrue(report.ok, report.format_text())
        self.assertTrue(any('checked 1 commit' in f.message for f in report.findings))

    def test_message_file_uses_git_identity(self):
        repo = helpers.new_repo()
        path = f'{repo}/COMMIT_EDITMSG'
        with open(path, 'w') as fh:
            fh.write(f'Fix\n\n# comment line\nSigned-off-by: {NAME} <{EMAIL}>\n')
        self.assertTrue(commit.check_message_file(path, OSRA, IDS, repo).ok)
        with open(path, 'w') as fh:
            fh.write('Fix without signoff\n')
        self.assertFalse(commit.check_message_file(path, OSRA, IDS, repo).ok)


if __name__ == '__main__':
    unittest.main()
