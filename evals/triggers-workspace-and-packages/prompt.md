---
name: triggers-workspace-and-packages
description: must trigger the workspace-and-packages skill
max_turns: 6
allowed_tools: [Read, Glob, Grep, Skill]
---

Create a new ROS 2 package called lidar_filter with a C++ node that depends on sensor_msgs, and set up the workspace for it.
