#!/bin/sh
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
#
# Application skill check (design section 11.2, item 4). Runs inside a
# ros:<distro>-ros-base container: creates the packages exactly as the
# workspace-and-packages skill says, builds them, and runs colcon test, which
# includes the ament linters. A failure here means a skill instruction no
# longer holds on that distribution.
set -eu
: "${ROS_DISTRO:?set by the ros image}"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  ros-dev-tools \
  "ros-$ROS_DISTRO-ament-lint-auto" \
  "ros-$ROS_DISTRO-ament-lint-common" \
  "ros-$ROS_DISTRO-ament-cmake-gtest" \
  "ros-$ROS_DISTRO-ament-cmake-pytest" \
  "ros-$ROS_DISTRO-std-msgs" \
  python3-pytest >/dev/null
# The ROS setup scripts read variables that may be unset, so relax -u around them.
set +u
# shellcheck disable=SC1090
. "/opt/ros/$ROS_DISTRO/setup.sh"
set -u
ws="$(mktemp -d)"
mkdir -p "$ws/src"
cd "$ws/src"
ros2 pkg create --build-type ament_cmake --license Apache-2.0 \
  --dependencies rclcpp std_msgs --node-name talker kit_smoke_cpp
ros2 pkg create --build-type ament_python --license Apache-2.0 \
  --dependencies rclpy --node-name listener kit_smoke_py
cd "$ws"
colcon build --event-handlers console_cohesion+
colcon test --event-handlers console_cohesion+
colcon test-result --verbose
echo "app smoke passed on $ROS_DISTRO"
