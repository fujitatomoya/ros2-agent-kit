---
name: launch-and-interfaces
description: >
  ROS 2 launch files and interface definitions: Python launch files with Node, arguments,
  parameters from YAML, remappings, includes, and composable node containers, where launch and
  config files are installed, and msg, srv, and action definitions with their naming rules,
  CMake generation, and generated header and module names. Use whenever the user writes or edits
  a launch file, a parameters YAML, or a .msg, .srv, or .action file, or asks how to start several
  nodes together or define a custom message.
---

# Launch and interfaces

Verify against the installed distribution: `ros2 interface list | head` and `ros2 launch --help`.

## Launch files

`launch/<name>.launch.py`:

```python
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params = PathJoinSubstitution([FindPackageShare('my_package'), 'config', 'params.yaml'])
    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        Node(
            package='my_package',
            executable='talker',
            name='talker',
            namespace='demo',
            parameters=[params, {'use_sim_time': LaunchConfiguration('use_sim_time')}],
            remappings=[('chatter', 'conversation')],
            output='screen',
        ),
    ])
```

- Install with `install(DIRECTORY launch config DESTINATION share/${PROJECT_NAME})` in CMake, or `data_files` in `setup.py` for `ament_python`.
- Include another launch file with `IncludeLaunchDescription(PythonLaunchDescriptionSource(...))` and pass `launch_arguments`.
- Composable nodes: `ComposableNodeContainer` with `ComposableNode(package=..., plugin='ns::Class', name=...)` runs several nodes in one process.
- XML and YAML launch files are supported and often shorter; pick what the package already uses.
- `ros2 launch my_package name.launch.py use_sim_time:=true` passes arguments; `--show-args` lists them.

Parameters YAML:

```yaml
/demo/talker:
  ros__parameters:
    start_count: 10
    rate_hz: 2.0
```

The node name key must match the launched name and namespace; `/**` applies to every node.
Types are inferred from the YAML value, so `2` and `2.0` are different parameter types.

## Interfaces

Live in a dedicated `<name>_interfaces` package built with `ament_cmake`:

```text
my_interfaces/
├── msg/Status.msg
├── srv/SetMode.srv
└── action/Dock.action
```

```text
# msg/Status.msg
std_msgs/Header header
uint8 MODE_IDLE=0
uint8 MODE_ACTIVE=1
uint8 mode
float64[] values
string name
```

```text
# srv/SetMode.srv
uint8 mode
---
bool success
string message
```

```text
# action/Dock.action
geometry_msgs/PoseStamped target
---
bool docked
---
float32 distance_remaining
```

Rules:

- File names in CamelCase, fields in snake_case, constants in UPPER_CASE, no field named like a type.
- A `header` field of type `std_msgs/Header` comes first when the message is stamped.
- Prefer existing semantic types from `common_interfaces` (`geometry_msgs`, `sensor_msgs`) over `std_msgs` wrappers.
- Changing a released message is an API break for every user; add a new message or field only on `rolling`.

```cmake
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Status.msg"
  "srv/SetMode.srv"
  "action/Dock.action"
  DEPENDENCIES std_msgs geometry_msgs)
```

```xml
<buildtool_depend>rosidl_default_generators</buildtool_depend>
<depend>std_msgs</depend>
<exec_depend>rosidl_default_runtime</exec_depend>
<member_of_group>rosidl_interface_packages</member_of_group>
```

Generated names: `my_interfaces/msg/status.hpp` and `my_interfaces::msg::Status` in C++, `from my_interfaces.msg import Status` in Python.
`ros2 interface show my_interfaces/msg/Status` confirms the build.
