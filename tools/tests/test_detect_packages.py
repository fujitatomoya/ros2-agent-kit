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

"""Unit tests with recorded GitHub API shapes; no network."""

import base64
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import detect_packages as dp  # noqa: E402


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def tree(paths, truncated=False):
    return {'truncated': truncated, 'tree': [{'path': p, 'type': 'blob'} for p in paths]}


def pkg_xml(name: str) -> str:
    return f'<?xml version="1.0"?>\n<package format="3">\n  <name>{name}</name>\n</package>\n'


class FakeApi:
    """Routes API paths to recorded responses and counts calls."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, path, token):
        self.calls.append(path)
        for prefix, value in self.routes.items():
            if path.startswith(prefix):
                return value
        raise AssertionError(f'unexpected API call {path}')


def pr_payload(owner='ros2', repo='demos', head_owner='jane', head_repo='demos',
               head_sha='headsha', base_sha='basesha', head_deleted=False):
    head = None if head_deleted else {'repo': {'owner': {'login': head_owner}, 'name': head_repo},
                                      'sha': head_sha}
    return {'head': head or {'repo': None, 'sha': head_sha},
            'base': {'repo': {'owner': {'login': owner}, 'name': repo}, 'sha': base_sha}}


class Mapping(unittest.TestCase):

    def test_nearest_package_dir_prefers_deepest(self):
        dirs = ['', 'a', 'a/nested']
        self.assertEqual(dp.nearest_package_dir('a/nested/src/x.cpp', dirs), 'a/nested')
        self.assertEqual(dp.nearest_package_dir('a/src/x.cpp', dirs), 'a')
        self.assertEqual(dp.nearest_package_dir('README.md', dirs), '')
        self.assertIsNone(dp.nearest_package_dir('b/x.cpp', ['a', 'a/nested']))
        self.assertIsNone(dp.nearest_package_dir('ab/x.cpp', ['a']))

    def test_parse_pr_spec(self):
        self.assertEqual(dp.parse_pr_spec('ros2/demos#806'), ('ros2', 'demos', 806))
        self.assertEqual(dp.parse_pr_spec('https://github.com/ros2/rclcpp/pull/3235'),
                         ('ros2', 'rclcpp', 3235))
        with self.assertRaises(ValueError):
            dp.parse_pr_spec('rclcpp 3235')

    def test_name_from_xml(self):
        self.assertEqual(dp.package_name_from_xml(pkg_xml('demo_nodes_cpp'), 'dir'), 'demo_nodes_cpp')
        self.assertEqual(dp.package_name_from_xml('<package/>', 'dir'), 'dir')


class Remote(unittest.TestCase):

    def test_two_prs_union_and_unmapped(self):
        api = FakeApi({
            '/repos/ros2/demos/pulls/806/files': [
                {'filename': 'demo_nodes_cpp/src/talker.cpp', 'status': 'modified'},
                {'filename': 'lifecycle/lifecycle_py/x.py', 'status': 'added'},
                {'filename': 'README.md', 'status': 'modified'},
            ],
            '/repos/ros2/demos/pulls/806': pr_payload(),
            '/repos/ros2/demos/git/trees/basesha': tree(['demo_nodes_cpp/package.xml']),
            '/repos/jane/demos/git/trees/headsha': tree([
                'demo_nodes_cpp/package.xml', 'lifecycle/package.xml',
                'lifecycle/lifecycle_py/package.xml']),
            '/repos/jane/demos/contents/demo_nodes_cpp/package.xml': {'content': b64(pkg_xml('demo_nodes_cpp'))},
            '/repos/jane/demos/contents/lifecycle/lifecycle_py/package.xml': {'content': b64(pkg_xml('lifecycle_py'))},
            '/repos/ros2/rclcpp/pulls/3235/files': [
                {'filename': 'rclcpp/include/rclcpp/node.hpp', 'status': 'modified'}],
            '/repos/ros2/rclcpp/pulls/3235': pr_payload(repo='rclcpp', head_repo='rclcpp', head_sha='h2'),
            '/repos/jane/rclcpp/git/trees/h2': tree(['rclcpp/package.xml', 'rclcpp_action/package.xml']),
            '/repos/jane/rclcpp/contents/rclcpp/package.xml': {'content': b64(pkg_xml('rclcpp'))},
        })
        result = dp.detect_remote(['ros2/demos#806', 'https://github.com/ros2/rclcpp/pull/3235'], api)
        self.assertEqual(result.per_pr['ros2/demos#806'], ['demo_nodes_cpp', 'lifecycle_py'])
        self.assertEqual(result.per_pr['ros2/rclcpp#3235'], ['rclcpp'])
        self.assertEqual(result.union, ['demo_nodes_cpp', 'lifecycle_py', 'rclcpp'])
        self.assertEqual(result.unmapped, ['ros2/demos#806:README.md'])
        self.assertEqual(result.warnings, [])
        # package.xml is read once per package, not once per file
        self.assertEqual(sum('contents/' in c for c in api.calls), 3)

    def test_directory_name_is_not_trusted(self):
        api = FakeApi({
            '/repos/ros2/x/pulls/1/files': [{'filename': 'dirname/src/a.cpp', 'status': 'modified'}],
            '/repos/ros2/x/pulls/1': pr_payload(repo='x', head_repo='x'),
            '/repos/jane/x/git/trees/headsha': tree(['dirname/package.xml']),
            '/repos/jane/x/contents/dirname/package.xml': {'content': b64(pkg_xml('real_name'))},
        })
        self.assertEqual(dp.detect_remote(['ros2/x#1'], api).union, ['real_name'])

    def test_removed_file_uses_base_tree(self):
        api = FakeApi({
            '/repos/ros2/x/pulls/2/files': [{'filename': 'old_pkg/src/a.cpp', 'status': 'removed'}],
            '/repos/ros2/x/pulls/2': pr_payload(repo='x', head_repo='x'),
            '/repos/jane/x/git/trees/headsha': tree([]),
            '/repos/ros2/x/git/trees/basesha': tree(['old_pkg/package.xml']),
            '/repos/ros2/x/contents/old_pkg/package.xml': {'content': b64(pkg_xml('old_pkg'))},
        })
        self.assertEqual(dp.detect_remote(['ros2/x#2'], api).union, ['old_pkg'])

    def test_deleted_fork_falls_back_to_base(self):
        api = FakeApi({
            '/repos/ros2/x/pulls/3/files': [{'filename': 'p/src/a.cpp', 'status': 'modified'}],
            '/repos/ros2/x/pulls/3': pr_payload(repo='x', head_deleted=True),
            '/repos/ros2/x/git/trees/basesha': tree(['p/package.xml']),
            '/repos/ros2/x/contents/p/package.xml': {'content': b64(pkg_xml('p'))},
        })
        result = dp.detect_remote(['ros2/x#3'], api)
        self.assertEqual(result.union, ['p'])
        self.assertTrue(any('deleted fork' in w for w in result.warnings))

    def test_truncated_tree_warns(self):
        api = FakeApi({
            '/repos/ros2/x/pulls/4/files': [{'filename': 'p/a.cpp', 'status': 'modified'}],
            '/repos/ros2/x/pulls/4': pr_payload(repo='x', head_repo='x'),
            '/repos/jane/x/git/trees/headsha': tree(['p/package.xml'], truncated=True),
            '/repos/jane/x/contents/p/package.xml': {'content': b64(pkg_xml('p'))},
        })
        result = dp.detect_remote(['ros2/x#4'], api)
        self.assertTrue(any('truncated' in w for w in result.warnings))

    def test_pagination(self):
        page1 = [{'filename': f'p/f{i}.cpp', 'status': 'modified'} for i in range(100)]
        page2 = [{'filename': 'q/g.cpp', 'status': 'modified'}]
        api = FakeApi({
            '/repos/ros2/x/pulls/5/files?per_page=100&page=1': page1,
            '/repos/ros2/x/pulls/5/files?per_page=100&page=2': page2,
            '/repos/ros2/x/pulls/5': pr_payload(repo='x', head_repo='x'),
            '/repos/jane/x/git/trees/headsha': tree(['p/package.xml', 'q/package.xml']),
            '/repos/jane/x/contents/p/package.xml': {'content': b64(pkg_xml('p'))},
            '/repos/jane/x/contents/q/package.xml': {'content': b64(pkg_xml('q'))},
        })
        self.assertEqual(dp.detect_remote(['ros2/x#5'], api).union, ['p', 'q'])


class Local(unittest.TestCase):

    def git(self, *args):
        subprocess.run(['git', '-C', self.repo] + list(args), check=True, capture_output=True)

    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix='detect-')
        self.git('init', '-q', '-b', 'rolling')
        self.git('config', 'user.email', 'jane@example.com')
        self.git('config', 'user.name', 'Jane')
        for d, name in (('pkg_a', 'real_a'), ('nested/pkg_b', 'pkg_b')):
            os.makedirs(os.path.join(self.repo, d, 'src'))
            Path(self.repo, d, 'package.xml').write_text(pkg_xml(name))
            Path(self.repo, d, 'src', 'main.cpp').write_text('int main(){}\n')
        Path(self.repo, 'README.md').write_text('readme\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'base')
        self.git('branch', 'origin/rolling')
        self.git('checkout', '-q', '-b', 'feature')

    def test_committed_and_uncommitted_changes(self):
        Path(self.repo, 'pkg_a', 'src', 'main.cpp').write_text('int main(){return 1;}\n')
        self.git('commit', '-qam', 'change a')
        Path(self.repo, 'nested', 'pkg_b', 'src', 'new.cpp').write_text('x')  # untracked
        Path(self.repo, 'README.md').write_text('changed\n')  # uncommitted, unmapped
        result = dp.detect_local(cwd=self.repo)
        self.assertEqual(result.union, ['pkg_b', 'real_a'])
        self.assertTrue(any(u.endswith(':README.md') for u in result.unmapped))

    def test_deleted_package_resolved_from_base(self):
        self.git('rm', '-rq', 'pkg_a')
        self.git('commit', '-qm', 'remove a')
        self.assertEqual(dp.detect_local(cwd=self.repo).union, ['real_a'])

    def test_explicit_base(self):
        self.assertEqual(dp.detect_local(base='rolling', cwd=self.repo).union, [])


if __name__ == '__main__':
    unittest.main()
