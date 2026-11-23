---
name: executors-and-qos
description: >
  ROS 2 executors, callback groups, and quality of service: which executor to use, mutually
  exclusive versus reentrant callback groups, the deadlock from waiting on a service inside a
  callback, QoS profiles and the reliability and durability compatibility rules, and how to
  diagnose "no messages received". Use whenever the user asks why callbacks do not run, why a
  subscription receives nothing, how to use MultiThreadedExecutor or callback groups, or which
  QoS to pick for sensors, services, or latched topics.
---

# Executors and QoS

Check the installed rclcpp before using a newer executor:

```bash
ls /opt/ros/$ROS_DISTRO/include/rclcpp/rclcpp/executors/
```

## Executors

| Executor | Use |
| --- | --- |
| `SingleThreadedExecutor` | Default; one callback at a time; `rclcpp::spin(node)` uses it |
| `MultiThreadedExecutor` | Callbacks in parallel, governed by callback groups |
| `EventsExecutor` | Lower overhead, event driven; present on recent distributions, check the include directory |
| `StaticSingleThreadedExecutor` | Deprecated on recent distributions; do not use in new code |

```cpp
rclcpp::executors::MultiThreadedExecutor exec;
exec.add_node(node);
exec.spin();
```

One executor spins a node; adding a node to two executors throws.
`spin_some` and `spin_once` are for integrating with another loop, not for polling in a callback.

## Callback groups

- Default: every callback of a node is in one `MutuallyExclusive` group, so nothing runs in parallel even with `MultiThreadedExecutor`.
- `Reentrant` group: callbacks in it may run concurrently, including the same callback twice; protect shared state.
- Put a service client and the callback that waits on it in different groups, or the wait deadlocks: the executor cannot deliver the response while the mutually exclusive group is busy waiting.

```cpp
cb_group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
rclcpp::SubscriptionOptions opts;
opts.callback_group = cb_group_;
sub_ = create_subscription<Msg>("topic", 10, callback, opts);
client_ = create_client<Srv>("service", rclcpp::ServicesQoS(), other_group_);
```

Prefer the asynchronous pattern: `client_->async_send_request(req, [this](Future f) {...})` and return from the callback.
`spin_until_future_complete` belongs in `main` or in tests, never inside a callback.

## QoS

`rclcpp::QoS(10)` means keep last 10, reliable, volatile.
Profiles: `SensorDataQoS()` (best effort, small history) for sensors, `ServicesQoS()` for services, `SystemDefaultsQoS()` to defer to the middleware, `QoS(1).transient_local()` for latched state such as a map or a static transform.

Compatibility, publisher versus subscription:

| Publisher | Subscription | Result |
| --- | --- | --- |
| reliable | reliable | ok |
| reliable | best effort | ok |
| best effort | reliable | incompatible, no data |
| volatile | transient local | incompatible, no data |
| transient local | volatile | ok, late joiners get nothing |

Other policies: `deadline`, `lifespan`, `liveliness`, and the `history` depth.
A mismatch is reported once by rclcpp as a QoS incompatibility warning; `ros2 topic info -v /topic` shows both sides.

Diagnosing "no messages":

1. `ros2 topic info -v /topic` for the QoS of each endpoint and the node names.
2. `ros2 topic hz /topic` and `ros2 topic echo --qos-reliability best_effort /topic` to match the publisher.
3. Same `ROS_DOMAIN_ID` and `RMW_IMPLEMENTATION` on both sides; `ros2 doctor --report`.
4. The subscription handle is kept alive and the node is being spun.
