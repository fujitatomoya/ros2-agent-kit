---
name: introspection
description: >
  Inspect a running ROS 2 system before changing code: ros2 doctor, node, topic, service,
  action, param, interface, bag, lifecycle, and component commands, QoS and discovery checks,
  domain and RMW environment variables, logging levels, and the daemon. Use whenever the user
  reports that something does not talk to something else, asks what is running, wants to record
  or replay data, or before debugging a node whose inputs are unknown.
---

# Introspection

Look before touching code.
These commands are read-only unless noted.

## Health and environment

```bash
ros2 doctor --report          # distribution, RMW, network, versions
echo "$ROS_DISTRO $ROS_DOMAIN_ID $RMW_IMPLEMENTATION"
ros2 daemon stop && ros2 daemon start   # when the graph looks stale (modifies the daemon only)
```

Discovery scope: `ROS_LOCALHOST_ONLY=1` on older distributions, `ROS_AUTOMATIC_DISCOVERY_RANGE` and `ROS_STATIC_PEERS` on recent ones; `ros2 doctor --report` prints which applies.
Two machines must share `ROS_DOMAIN_ID` and a compatible `RMW_IMPLEMENTATION`.

## Graph

```bash
ros2 node list
ros2 node info /talker                 # publishers, subscriptions, services, actions
ros2 topic list -t                     # with types
ros2 topic info -v /chatter            # endpoints and their QoS
ros2 topic echo --once /chatter
ros2 topic hz /chatter; ros2 topic bw /chatter
ros2 service list -t; ros2 service type /set_mode
ros2 action list -t; ros2 action info /dock
ros2 interface show std_msgs/msg/String
ros2 run rqt_graph rqt_graph           # when a display is available
```

`ros2 topic pub` and `ros2 service call` inject data and change the system; say so when you use them.

## Parameters

```bash
ros2 param list /talker
ros2 param get /talker start_count
ros2 param dump /talker                # YAML, reusable in a launch file
ros2 param set /talker start_count 5   # changes the running node
```

## Lifecycle and components

```bash
ros2 lifecycle nodes; ros2 lifecycle get /lc_node; ros2 lifecycle list /lc_node
ros2 component list                    # containers and loaded components
```

## Data

```bash
ros2 bag record -o run1 /chatter /tf   # or -a for everything, with care for bandwidth
ros2 bag info run1
ros2 bag play run1 --rate 0.5
```

## Logging

```bash
ros2 run my_package talker --ros-args --log-level talker:=debug
export RCUTILS_CONSOLE_OUTPUT_FORMAT="[{severity} {time}] [{name}]: {message}"
export RCUTILS_COLORIZED_OUTPUT=1
```

Logs also land under `~/.ros/log/`.

## What to report

State the distribution, RMW, domain, the nodes involved, the QoS of the endpoints in question, and the exact command outputs, verbatim.
That is the environment block of a bug report; see `issue-report`.
