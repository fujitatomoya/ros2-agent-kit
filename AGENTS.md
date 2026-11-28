# Agent instructions for ros2-agent-kit

This repository builds `ros2-agent-kit`, a set of agent skills, hooks, and checks for ROS 2 development and mainline contribution.
The design lives in `design/ros2-agent-kit-design.md` and is the source of truth for scope and rules.

## Rules for working in this repository

- Commits are authored and signed off by the human contributor (`git commit -s`).
  Never commit under an agent identity, and never add a `Signed-off-by` line for an agent.
- Add `Assisted-by: {agent}:{model}` as a commit trailer when you helped with a commit.
- Open or change a pull request or an issue on GitHub only after the human confirms the exact command.
  The human writes the description, so prepare the text in a local file for them first.
- Never post comments or reviews on GitHub; replies are the human's to write and post.
- Only report a test result that you actually ran on the current tree.
- The gate engine in `gate/` is standard-library Python only, supports Python 3.10 and newer, and makes no network calls.
  Network helpers belong in `tools/`.
- Every new source file carries the Apache-2.0 header.
- Documentation style: one sentence per line, ATX headings, a language on every code block.

## Layout

- `policy/` profiles and sources, JSON, rules as data.
- `gate/` the `ros2-gate` engine and its tests (`cd gate && python3 -m unittest discover -s tests -t .`).
- `adapters/` hook adapters per harness.
- `hooks/hooks.json` hook registration for Claude Code and Codex.
- `tools/` helpers that may use the network.
- `templates/` the draft organization `AGENTS.md`.
