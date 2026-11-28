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
from ros2_gate import guard, profile as profile_mod

OSRA = helpers.load_profile('osra-ros2')
APP = helpers.load_profile('app')
DCO = helpers.load_profile('generic-dco')
IDS = helpers.identities()


class Segments(unittest.TestCase):

    def test_splits_compound_commands(self):
        segs = guard.segments('colcon build && git commit -s -m "a b" ; gh pr view 1 | cat')
        self.assertEqual(segs, [['colcon', 'build'], ['git', 'commit', '-s', '-m', 'a b'],
                                ['gh', 'pr', 'view', '1'], ['cat']])

    def test_unbalanced_quotes_do_not_crash(self):
        self.assertEqual(guard.segments('git commit -m "oops'), [['git', 'commit', '-m', '"oops']])


class GhPosting(unittest.TestCase):

    def check(self, cmd, prof=OSRA):
        return guard.guard(cmd, prof, IDS)

    def test_read_only_gh_allowed(self):
        for cmd in ('gh pr view 123', 'gh pr list', 'gh pr diff 1', 'gh issue view 5',
                    'gh pr checkout 7', 'gh api repos/ros2/rclcpp/pulls/1', 'gh auth status'):
            self.assertTrue(self.check(cmd).allowed, cmd)

    def test_submission_needs_confirmation(self):
        for cmd in ('gh pr create --title x', 'gh issue create', 'gh pr edit 1 --body y',
                    'gh pr merge 1', 'gh pr close 1', 'gh issue close 3',
                    'gh api repos/o/r/issues -f title=x',
                    'gh api graphql -f query="mutation { x }"'):
            d = self.check(cmd)
            self.assertEqual(d.decision, guard.ASK, cmd)
            self.assertTrue(d.needs_confirmation, cmd)
            self.assertFalse(d.allowed, cmd)
            self.assertEqual(d.gate, 'G3', cmd)
            self.assertIn('confirm', d.reason, cmd)

    def test_discussion_blocked(self):
        for cmd in ('gh pr comment 1 -b hi', 'gh pr review 1 --approve',
                    'gh issue comment 2 -b x', 'gh pr close 1 --comment done',
                    'gh issue close 2 -c bye', 'gh issue reopen 2 --comment=again',
                    'gh api -X POST repos/o/r/issues/1/comments -f body=hi',
                    'gh api -X POST repos/o/r/pulls/1/reviews -f event=APPROVE',
                    'gh api graphql -f query="mutation { addComment(input: {}) { id } }"'):
            d = self.check(cmd)
            self.assertEqual(d.decision, guard.BLOCK, cmd)
            self.assertFalse(d.needs_confirmation, cmd)
            self.assertEqual(d.gate, 'G3', cmd)

    def test_nested_shell_is_inspected(self):
        d = self.check('bash -c "gh issue create -t x"')
        self.assertTrue(d.needs_confirmation)
        self.assertEqual(d.command, 'gh issue create -t x')
        self.assertEqual(self.check('sh -c "gh pr comment 1 -b x"').decision, guard.BLOCK)

    def test_compound_command_blocked_on_any_segment(self):
        d = self.check('colcon build && gh pr comment 1 -b done')
        self.assertFalse(d.allowed)
        self.assertEqual(d.command, 'gh pr comment 1 -b done')

    def test_block_wins_over_confirmation(self):
        d = self.check('gh pr create --fill && gh pr comment 1 -b done')
        self.assertEqual(d.decision, guard.BLOCK)
        self.assertEqual(d.command, 'gh pr comment 1 -b done')
        d = self.check('gh pr create --fill && git status')
        self.assertTrue(d.needs_confirmation)
        self.assertEqual(d.command, 'gh pr create --fill')

    def test_app_profile_allows_posting(self):
        for cmd in ('gh pr create', 'gh pr comment 1 -b hi'):
            self.assertTrue(self.check(cmd, APP).allowed, cmd)
            self.assertTrue(self.check(cmd, DCO).allowed, cmd)

    def test_profile_modes(self):
        def prof(**authorship):
            return profile_mod.Profile('custom', {'rules': {'authorship': authorship}})
        deny = prof(agent_submission='deny', agent_discussion='deny')
        self.assertEqual(self.check('gh pr create', deny).decision, guard.BLOCK)
        both = prof(agent_submission='confirm', agent_discussion='confirm')
        self.assertTrue(self.check('gh pr comment 1 -b hi', both).needs_confirmation)
        # A profile from before the split, and a misspelled value, both fail closed.
        legacy = prof(agent_may_post=False)
        self.assertEqual(self.check('gh pr create', legacy).decision, guard.BLOCK)
        self.assertEqual(self.check('gh pr comment 1 -b hi', legacy).decision, guard.BLOCK)
        self.assertTrue(self.check('gh pr create', prof(agent_may_post=True)).allowed)
        typo = prof(agent_submission='confrim')
        self.assertEqual(self.check('gh pr create', typo).decision, guard.BLOCK)


class GitCommit(unittest.TestCase):

    def setUp(self):
        self.repo = helpers.new_repo()

    def check(self, cmd, prof=OSRA):
        return guard.guard(cmd, prof, IDS, cwd=self.repo)

    def test_signoff_required(self):
        self.assertFalse(self.check('git commit -m "x"').allowed)
        self.assertEqual(self.check('git commit -m "x"').gate, 'G1')
        for cmd in ('git commit -s -m x', 'git commit -sm x', 'git commit -asm "x y"',
                    'git commit --signoff', 'git commit -a --signoff -m x',
                    'git commit -m "x" -s'):
            self.assertTrue(self.check(cmd).allowed, cmd)

    def test_message_with_signoff_text_is_enough(self):
        msg = 'git commit -m "Fix\n\nSigned-off-by: Jane Developer <jane@example.com>"'
        self.assertTrue(self.check(msg).allowed)

    def test_no_signoff_flag_blocked(self):
        self.assertFalse(self.check('git commit -s --no-signoff -m x').allowed)

    def test_no_verify_blocked(self):
        d = self.check('git commit -s -m x --no-verify')
        self.assertFalse(d.allowed)
        self.assertIn('bypass', d.reason)
        self.assertFalse(self.check('git commit -sn -m x').allowed)

    def test_amend_no_edit_checks_head(self):
        helpers.commit(self.repo, 'signed', signoff=True)
        self.assertTrue(self.check('git commit --amend --no-edit').allowed)
        helpers.commit(self.repo, 'unsigned')
        self.assertFalse(self.check('git commit --amend --no-edit').allowed)
        self.assertTrue(self.check('git commit --amend --no-edit -s').allowed)

    def test_agent_identity_blocked(self):
        d = self.check('git -c user.name=Claude -c user.email=noreply@anthropic.com commit -s -m x')
        self.assertFalse(d.allowed)
        self.assertIn('agent identity', d.reason)
        d = self.check('git commit -s -m x --author="Claude <noreply@anthropic.com>"')
        self.assertFalse(d.allowed)
        agent_repo = helpers.new_repo(name='Claude', email='noreply@anthropic.com')
        self.assertFalse(guard.guard('git commit -s -m x', OSRA, IDS, cwd=agent_repo).allowed)

    def test_other_git_commands_allowed(self):
        for cmd in ('git status', 'git push --dry-run', 'git log --oneline', 'git add -A',
                    'git -C /tmp status', 'git rebase -i HEAD~2'):
            self.assertTrue(self.check(cmd).allowed, cmd)

    def test_app_profile_commit_without_signoff(self):
        self.assertTrue(self.check('git commit -m x', APP).allowed)

    def test_generic_dco_requires_signoff(self):
        self.assertFalse(self.check('git commit -m x', DCO).allowed)

    def test_non_git_commands_untouched(self):
        for cmd in ('colcon build --symlink-install', 'rm -rf build', 'ls', ''):
            self.assertTrue(self.check(cmd).allowed, cmd)


if __name__ == '__main__':
    unittest.main()
