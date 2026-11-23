# Where ROS 2 issues go

| Symptom area | Repository |
| --- | --- |
| `rclcpp`, executors, callback groups, components, lifecycle (C++) | `ros2/rclcpp` |
| `rclpy` | `ros2/rclpy` |
| `rcl`, `rcl_action`, `rcl_lifecycle` | `ros2/rcl` |
| `rcutils`, logging primitives | `ros2/rcutils` |
| `rmw` API | `ros2/rmw` |
| Fast DDS middleware | `ros2/rmw_fastrtps` |
| Cyclone DDS middleware | `ros2/rmw_cyclonedds` |
| Connext middleware | `ros2/rmw_connextdds` |
| Zenoh middleware | `ros2/rmw_zenoh` |
| `ros2 <verb>` command line | `ros2/ros2cli` |
| `ros2 launch`, launch files | `ros2/launch`, `ros2/launch_ros` |
| Message generation, `rosidl` | `ros2/rosidl` and the `rosidl_*` repositories |
| Common interfaces (`std_msgs`, `geometry_msgs`, ...) | `ros2/common_interfaces` |
| `rcl_interfaces`, parameters messages | `ros2/rcl_interfaces` |
| Demos and examples | `ros2/demos`, `ros2/examples` |
| `ament_cmake`, `ament_lint`, `ament_index` | `ament/ament_cmake`, `ament/ament_lint`, `ament/ament_index` |
| `colcon` | `colcon/*` |
| Documentation at docs.ros.org | `ros2/ros2_documentation` |
| Cross-cutting, "I do not know where" | `ros2/ros2` |
| Build farm, ci.ros2.org, build.ros2.org | `ros2/ci`, `ros-infrastructure/*` |

When in doubt, `ros2 pkg xml <package>` and the `<url type="repository">` tag settle it.
