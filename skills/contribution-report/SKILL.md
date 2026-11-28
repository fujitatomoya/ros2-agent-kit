---
name: contribution-report
description: >
  Produce a report of GitHub contributions to ROS 2 organizations over a period with the
  ros-github-contribution-report tool from ros-tooling/ros-github-scripts, for a person,
  a team, or a company, as a Markdown table with links. Use whenever the user asks for a
  contribution report, a summary of PRs or reviews over a quarter, who contributed to ros2
  repositories, or what they merged this month.
---

# Contribution report

Wrap the official tool as installed; see P8 in the design.

```bash
which ros-github-contribution-report || pip3 install git+https://github.com/ros-tooling/ros-github-scripts
ros-github-contribution-report --help
```

Read the help before composing the command; the flags for organizations, authors, dates, and output format are the tool's and may change.
The tool needs `GITHUB_ACCESS_TOKEN` or the token from `gh auth token`; never print it.

Typical request: "what did I contribute to ros2 and ament since October".
Compose the command with the organizations (`ros2`, `ament`, often `ros-tooling`, `ros-infrastructure`), the author or team, and the date range, show it, run it, and present the Markdown output as is.
Add nothing the tool did not report; if the user wants review counts or issue triage that the tool does not cover, say so and offer `gh search prs --reviewed-by <user> --owner ros2 --merged --updated >=<date>` as a read-only complement, clearly labeled as a separate source.
