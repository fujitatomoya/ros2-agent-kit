---
name: triggers-ci-trigger
description: must trigger the ci-trigger skill
max_turns: 6
allowed_tools: [Read, Glob, Grep, Skill]
---

Run lyrical CI for ros2/demos#806 and ros2/rclcpp#3235 on the buildfarm, but only test rclcpp.
