---
name: nodes-and-components
description: >
  Write ROS 2 nodes the conventional way in rclcpp and rclpy: node classes with NodeOptions,
  declared parameters with callbacks, publishers and subscriptions, timers, composable nodes
  registered as components, lifecycle nodes with managed transitions, logging, and the pitfalls
  (shared_from_this in constructors, spinning inside callbacks, blocking calls). Use whenever the
  user writes or edits a node, asks about parameters, composition, components, lifecycle, or
  why a node does not behave as expected.
---

# Nodes and components

Check what is installed first: `ros2 pkg prefix rclcpp`, and `ros2 doctor --report` for the RMW in use.
APIs below exist on every active distribution unless marked.

## A node in rclcpp

```cpp
class Talker : public rclcpp::Node
{
public:
  explicit Talker(const rclcpp::NodeOptions & options)
  : Node("talker", options)
  {
    count_ = declare_parameter<int>("start_count", 0);
    pub_ = create_publisher<std_msgs::msg::String>("chatter", rclcpp::QoS(10));
    timer_ = create_wall_timer(std::chrono::seconds(1), [this]() {on_timer();});
  }

private:
  void on_timer()
  {
    std_msgs::msg::String msg;
    msg.data = "hello " + std::to_string(count_++);
    RCLCPP_INFO(get_logger(), "publishing '%s'", msg.data.c_str());
    pub_->publish(msg);
  }

  int count_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr pub_;
  rclcpp::TimerBase::SharedPtr timer_;
};
```

Rules the compiler does not enforce:

- Take `const rclcpp::NodeOptions &` in the constructor so the node can be composed and remapped.
- Declare every parameter before use, with a type and a default, and read it with `get_parameter` when it may change; validate changes with `add_on_set_parameters_callback`.
- Do not call `shared_from_this()` in the constructor; it throws.
  Finish setup in a one-shot timer or an `init()` called after construction.
- Do not call `rclcpp::spin` or `spin_until_future_complete` inside a callback; see `executors-and-qos`.
- Do not block in callbacks; long work goes to its own thread or a reentrant callback group.
- Keep `rclcpp::init` and `rclcpp::shutdown` in `main`, never in library code.
- Topic names are relative unless they start with `/`; let users remap with `--ros-args -r chatter:=other`.
- Logging through `RCLCPP_INFO` and friends, with `RCLCPP_INFO_THROTTLE` for periodic messages; no `printf` or `std::cout` in nodes.

## Composition

Build the node as a shared library and register it:

```cpp
#include "rclcpp_components/register_node_macro.hpp"
RCLCPP_COMPONENTS_REGISTER_NODE(my_package::Talker)
```

```cmake
find_package(rclcpp_components REQUIRED)
add_library(talker_component SHARED src/talker.cpp)
target_link_libraries(talker_component PUBLIC rclcpp::rclcpp rclcpp_components::component ${std_msgs_TARGETS})
rclcpp_components_register_node(talker_component PLUGIN "my_package::Talker" EXECUTABLE talker)
```

Run it standalone with `ros2 run my_package talker`, or in a container: `ros2 run rclcpp_components component_container`, then `ros2 component load /ComponentManager my_package my_package::Talker`.
Composition is the default for anything that will run alongside other nodes; a plain `main` is for tools.

## Lifecycle nodes

Derive from `rclcpp_lifecycle::LifecycleNode`, implement `on_configure`, `on_activate`, `on_deactivate`, `on_cleanup`, `on_shutdown`, and `on_error`, each returning `CallbackReturn::SUCCESS`, `FAILURE`, or `ERROR`.
Create publishers in `on_configure` and activate them in `on_activate`; a lifecycle publisher drops messages while inactive.
Drive transitions with `ros2 lifecycle set /node configure` and `activate`, and from launch with `LifecycleNode` plus event handlers.

## rclpy

```python
class Listener(Node):

    def __init__(self):
        super().__init__('listener')
        self.declare_parameter('threshold', 0.5)
        self.sub = self.create_subscription(String, 'chatter', self.on_msg, 10)

    def on_msg(self, msg):
        self.get_logger().info(f'heard: {msg.data}')


def main(args=None):
    rclpy.init(args=args)
    node = Listener()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
```

Keep the handle to a subscription or timer, or it is garbage collected and stops working.
Register the entry point in `setup.py` under `console_scripts`.
