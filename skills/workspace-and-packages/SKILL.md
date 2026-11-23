---
name: workspace-and-packages
description: >
  Create and lay out ROS 2 workspaces and packages the conventional way: colcon workspace
  structure, ros2 pkg create for ament_cmake and ament_python, package.xml format 3 with the
  right dependency tags, naming rules, interface packages, rosdep, and overlay sourcing. Use
  whenever the user wants to create a package, set up a workspace, fix package.xml or
  dependencies, or asks how a ROS 2 project should be structured.
---

# Workspaces and packages

Check the installed distribution before relying on memory:

```bash
echo "$ROS_DISTRO"; ros2 pkg prefix rclcpp; ros2 pkg list | grep -c .
```

If `ROS_DISTRO` is empty, source `/opt/ros/<distro>/setup.bash` first and ask which distribution the user targets.

## Workspace

```text
ws/
├── src/            # packages, one directory each, or vcs-imported repositories
├── build/          # colcon output, never committed
├── install/
└── log/
```

```bash
mkdir -p ws/src && cd ws
rosdep install --from-paths src --ignore-src -y     # system dependencies from package.xml
colcon build --symlink-install
source install/setup.bash                            # overlay on top of /opt/ros
```

Source the overlay in a new shell, not the one that ran the build, and never commit `build/`, `install/`, or `log/`.

## Creating a package

```bash
ros2 pkg create --build-type ament_cmake --license Apache-2.0 \
  --dependencies rclcpp std_msgs --node-name talker my_package
ros2 pkg create --build-type ament_python --license Apache-2.0 \
  --dependencies rclpy --node-name listener my_py_package
```

Naming (REP-144): lowercase letters, digits, and underscores, starting with a letter, no hyphens, and the package name equals the CMake project name and the directory name.
One build type per package; C++ and Python in one package needs `ament_cmake_python`, which is rarely worth it.
Interfaces (`msg`, `srv`, `action`) live in their own `<name>_interfaces` package so that users can depend on messages without the nodes.

## package.xml (format 3)

```xml
<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>my_package</name>
  <version>0.1.0</version>
  <description>One sentence that says what the package does.</description>
  <maintainer email="maintainer@example.com">Maintainer Name</maintainer>
  <license>Apache-2.0</license>

  <buildtool_depend>ament_cmake</buildtool_depend>
  <depend>rclcpp</depend>
  <depend>std_msgs</depend>

  <test_depend>ament_lint_auto</test_depend>
  <test_depend>ament_lint_common</test_depend>
  <test_depend>ament_cmake_gtest</test_depend>

  <export>
    <build_type>ament_cmake</build_type>
  </export>
</package>
```

- `<depend>` covers build, export, and exec; use `<build_depend>`, `<exec_depend>`, `<build_export_depend>` only when they differ.
- Every `find_package` in CMake and every `import` of a ROS package in Python has a matching tag; `rosdep` and the build farm read this file, not CMake.
- `<version>` is bumped by the release tooling, not by hand in a feature PR.
- Keys must exist in rosdep (`rosdep resolve <key>`); a missing key blocks release.

## Build types

- `ament_cmake` with `CMakeLists.txt`; see the `cmake-style` skill.
- `ament_python` with `setup.py`, `setup.cfg`, `resource/<package>`, and `<package>/__init__.py`; executables come from `entry_points.console_scripts`; launch and config files are installed through `data_files`.
- `ament_cmake` packages that only hold interfaces use `rosidl_generate_interfaces`; see `launch-and-interfaces`.

## Multiple repositories

`vcs import src < repos.yaml` pulls a set of repositories; `vcs export` records them.
`colcon list`, `colcon graph`, and `colcon info` describe what is in the workspace.
