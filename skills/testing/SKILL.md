---
name: testing
description: >
  Test ROS 2 code at the right level: gtest and gmock unit tests with ament_cmake_gtest, pytest
  for Python packages, launch_testing for integration tests that start nodes, when a test needs a
  running context, timeouts, and how to run a single test. Use whenever the user adds or fixes a
  test in a ROS 2 package, asks how to test a node, publisher, service, or launch file, or asks
  the difference between unit, integration, and system tests in ROS 2.
---

# Testing

Levels, and where they live:

| Level | Scope | Tool | Location |
| --- | --- | --- | --- |
| Unit | One class or function, no middleware | gtest, gmock, pytest | `test/test_<thing>.cpp`, `test/test_<thing>.py` |
| Integration | Nodes talking over topics or services | gtest with `rclcpp::init`, `launch_testing` | `test/` |
| System | A launch file and the real stack | `launch_testing`, bag playback | `test/`, often a separate package |

Keep units free of `rclcpp::init`; a class that takes its dependencies as arguments can be tested without a node.

## gtest

```cmake
if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_counter test/test_counter.cpp TIMEOUT 60)
  target_link_libraries(test_counter ${PROJECT_NAME})
endif()
```

For tests that need a node:

```cpp
class NodeTest : public ::testing::Test
{
protected:
  static void SetUpTestSuite() {rclcpp::init(0, nullptr);}
  static void TearDownTestSuite() {rclcpp::shutdown();}
};

TEST_F(NodeTest, publishes_once)
{
  auto node = std::make_shared<rclcpp::Node>("test_node");
  // publish, then spin until the subscription saw it, with a bound:
  rclcpp::executors::SingleThreadedExecutor exec;
  exec.add_node(node);
  auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
  while (!received && std::chrono::steady_clock::now() < deadline) {
    exec.spin_some(std::chrono::milliseconds(50));
  }
  EXPECT_TRUE(received);
}
```

- Bound every wait; never `sleep` for a fixed time and hope.
- `ament_add_gmock` for mocks; `ament_cmake_gtest` also provides `ament_add_gtest_executable` plus `ament_add_gtest_test` when the binary needs arguments.
- Each test gets its own node name or a unique domain to avoid cross-talk when tests run in parallel; `ros2 run domain_coordinator` is used by core packages for that.

## pytest

`ament_python` packages run every `test/test_*.py` through pytest automatically, including the `ament_flake8`, `ament_pep257`, and `ament_copyright` tests the template adds.
In `ament_cmake` packages: `find_package(ament_cmake_pytest REQUIRED)` and `ament_add_pytest_test(test_name test/)`.
Use `rclpy.init()` and `rclpy.shutdown()` in a fixture; spin with `rclpy.spin_once(node, timeout_sec=0.1)` in a bounded loop.

## launch_testing

```python
import unittest

import launch_testing
import pytest
from launch import LaunchDescription
from launch_ros.actions import Node


@pytest.mark.launch_test
def generate_test_description():
    talker = Node(package='my_package', executable='talker')
    return LaunchDescription([talker, launch_testing.actions.ReadyToTest()]), {'talker': talker}


class TestTalker(unittest.TestCase):

    def test_output(self, proc_output, talker):
        proc_output.assertWaitFor('publishing', process=talker, timeout=10)
```

Register with `add_launch_test(test/test_talker.launch_test.py)` after `find_package(launch_testing_ament_cmake REQUIRED)`.
Post-shutdown checks use `@launch_testing.post_shutdown_test()` and `launch_testing.asserts.assertExitCodes`.

## Running

```bash
colcon test --packages-select my_package --event-handlers console_direct+
colcon test --packages-select my_package --ctest-args -R test_counter
colcon test --packages-select my_package --pytest-args -k test_output
colcon test-result --verbose
```

Record runs through `ros2-gate run --` so the result can be reported; `--retest-until-pass` hides flaky tests and is not acceptable in a PR.
