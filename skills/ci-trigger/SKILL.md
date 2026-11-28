---
name: ci-trigger
description: >
  Trigger ROS 2 CI jobs on ci.ros2.org for one or more GitHub pull requests using
  ros-ci-for-pr (from ros-tooling/ros-github-scripts), with automatic detection of the
  affected ROS packages from the PR diffs. Use whenever the user wants to run, launch, or
  kick off ROS CI, ci.ros2.org, Jenkins, or buildfarm jobs for a ROS 2 PR, mentions
  ros-ci-for-pr, asks to test a ros2/* pull request on a distro (rolling, lyrical, kilted,
  jazzy, humble), asks which packages a PR touches, or wants to bundle several PRs into one
  CI run, even without saying "CI" (for example "build rclcpp#3235 on the buildfarm").
---

# ROS CI trigger

Compose and run `ros-ci-for-pr` so the user never lists package names by hand.
The tool is used as installed; this skill never replaces it.

## Prerequisites (check once per session, on first use)

1. `ros-ci-for-pr` is installed: `which ros-ci-for-pr`.
   If missing, offer: `pip3 install git+https://github.com/ros-tooling/ros-github-scripts`.
2. `GITHUB_ACCESS_TOKEN` is set.
   It must be a classic personal access token with the `public_repo`, `gist`, and `read:org` scopes; a fine-grained token fails at the Jenkins job-creation step.
   If unset but `gh` is logged in, package detection still works through `gh auth token`; job creation does not.
3. The user has build access to ci.ros2.org.
   Without it, stop after step 3 and hand the composed command to a maintainer.

Never print, echo, store, or write a token anywhere.
Run `python3 "${CLAUDE_PLUGIN_ROOT:-.}/gate/ros2-gate" doctor` when something looks off; it reports these prerequisites.

## 1. Parse the request

- **PRs**: one or more, as `org/repo#N`.
  Accept URLs and shorthand ("rclcpp 3235" is `ros2/rclcpp#3235`; confirm the repo when ambiguous).
- **Target distro**: `rolling` by default, or what the user names.
  If the PR's base branch is a distro branch, use that distro and say so.
- **Packages**: as given, otherwise auto-detect.
- **Build versus test split**: the user may want to build a broad set and test a subset.
- **Extra arguments**: `--colcon-build-args`, `--colcon-test-args`, `--build`, `-c`.

Ask one concise question only if something is genuinely ambiguous; otherwise state your assumptions.

## 2. Detect the packages

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.}/tools/detect_packages.py" ros2/demos#806 ros2/rclcpp#3235
```

It prints one package per line (the union) and, on stderr, the list per PR and the files that map to no package.
Show the list grouped by PR, in full, so the user can trim it ("drop the `*_py` demos", "only test rclcpp").
Heed any warning about a truncated tree listing or a deleted fork.

## 3. Compose and confirm

```bash
ros-ci-for-pr \
  --target lyrical \
  --pulls ros2/rclcpp#3235 ros2/rcl#1200 \
  --packages rclcpp rcl \
  --build \
  -c
```

- Verified flags: `--target`, `--pulls`, `--packages`, `--build`, `--comment`/`-c`, `--branch`, `--colcon-build-args`.
  For anything else, including a build/test split, run `ros-ci-for-pr --help` and read it; the tool's help is the source of truth.
- `-c` posts status badges as comments on the PRs.
  Include it only when the user asks for comments.
- An unknown `--target` means the installed tool predates the distro; show the upstream error and suggest updating the package.
  Do not install from forks.

**Always show the exact command and wait for an explicit go-ahead before running it.**
CI consumes a shared build farm and `-c` posts publicly.
A "just run it from now on" holds for this session only.

## 4. Run and report

Run the confirmed command in the foreground.
If it prompts for Jenkins credentials, let the user answer in the terminal; never capture or repeat what they type.
If the environment cannot show prompts, give the user the command to run themselves.

Report: the gist URL of the generated `ros2.repos`, the Jenkins job URLs or badges, and which PRs were commented on.
On failure show the real error; the usual causes are a fine-grained token, a missing `read:org` scope, no build access, or an outdated tool for a new distro.

## Re-runs

"Same but on rolling", "add rcl_action to the test set": take the previous command from the conversation, apply the delta, show it, confirm, run.
