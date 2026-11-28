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

import os
import unittest
from pathlib import Path

from tests import helpers
from ros2_gate import gitinfo, profile as profile_mod


class RemoteNormalization(unittest.TestCase):

    def test_forms(self):
        for url in ('git@github.com:ros2/rclcpp.git', 'https://github.com/ros2/rclcpp.git',
                    'https://github.com/ros2/rclcpp', 'ssh://git@github.com/ros2/rclcpp.git',
                    'https://user@github.com/ros2/rclcpp/'):
            self.assertEqual(gitinfo.normalize_remote(url), 'github.com/ros2/rclcpp', url)


class Detection(unittest.TestCase):

    def setUp(self):
        os.environ.pop('ROS2_GATE_PROFILE', None)

    def test_ros2_remote_selects_osra(self):
        repo = helpers.new_repo(remote='git@github.com:ros2/rclcpp.git')
        prof = profile_mod.detect(repo)
        self.assertEqual(prof.id, 'osra-ros2')
        self.assertEqual(prof.matched_remote, 'github.com/ros2/rclcpp')

    def test_fork_with_upstream_remote_selects_osra(self):
        repo = helpers.new_repo(remote='git@github.com:jane/rclcpp.git')
        helpers.git(repo, 'remote', 'add', 'upstream', 'https://github.com/ros2/rclcpp.git')
        self.assertEqual(profile_mod.detect(repo).id, 'osra-ros2')

    def test_unknown_remote_without_dco_selects_app(self):
        repo = helpers.new_repo(remote='git@github.com:jane/my_robot.git')
        self.assertEqual(profile_mod.detect(repo).id, 'app')

    def test_dco_mention_selects_generic_dco(self):
        repo = helpers.new_repo(remote='git@github.com:acme/thing.git')
        Path(repo, 'CONTRIBUTING.md').write_text('Please add a Signed-off-by line (DCO).\n')
        self.assertEqual(profile_mod.detect(repo).id, 'generic-dco')

    def test_env_override(self):
        repo = helpers.new_repo()
        os.environ['ROS2_GATE_PROFILE'] = 'osra-ros2'
        try:
            self.assertEqual(profile_mod.detect(repo).id, 'osra-ros2')
        finally:
            del os.environ['ROS2_GATE_PROFILE']

    def test_unknown_override_raises(self):
        with self.assertRaises(KeyError):
            profile_mod.detect(helpers.new_repo(), override='nope')

    def test_rule_lookup_and_summary(self):
        prof = helpers.load_profile('osra-ros2')
        self.assertTrue(prof.rule('dco.required'))
        self.assertEqual(prof.rule('branching.target'), 'rolling')
        self.assertIsNone(prof.rule('does.not.exist'))
        self.assertIn('only after the human confirms', prof.summary())
        self.assertIn('agent may not post comments or reviews', prof.summary())
        self.assertEqual(prof.posting('submission'), 'confirm')
        self.assertEqual(prof.posting('discussion'), 'deny')
        self.assertIn('agent may post', helpers.load_profile('app').summary())


if __name__ == '__main__':
    unittest.main()
