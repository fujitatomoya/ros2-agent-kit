---
name: ci-status
description: >
  Check and summarize the status of ci.ros2.org Jenkins jobs launched for one or more ROS 2
  pull requests: find the status badges posted by ros-ci-for-pr, query the Jenkins JSON API for
  each job's result, list failing tests, and say whether a re-run is warranted. Use whenever the
  user asks how CI is doing for a PR, whether the buildfarm jobs passed, what failed on
  ci.ros2.org, or to check the jobs they launched earlier.
---

# CI status

Read-only against GitHub and Jenkins.

## 1. Find the jobs

Jobs launched with `ros-ci-for-pr -c` leave a comment with badges on each PR; jobs launched without `-c` were reported in the terminal and may be in this conversation.

```bash
gh api repos/ros2/<repo>/issues/<n>/comments --paginate --jq '.[] | select(.body | test("ci.ros2.org")) | {user: .user.login, created: .created_at, body: .body}'
```

Extract the job URLs, of the form `https://ci.ros2.org/job/ci_<os>/<build>/`.

## 2. Query Jenkins

```bash
curl -fsS "https://ci.ros2.org/job/ci_linux/<build>/api/json?tree=result,building,timestamp,duration,description"
curl -fsS "https://ci.ros2.org/job/ci_linux/<build>/testReport/api/json?tree=failCount,skipCount,passCount,suites[cases[className,name,status,errorDetails]]"
```

`result` is `SUCCESS`, `UNSTABLE` (tests failed), `FAILURE` (build failed), `ABORTED`, or null while `building`.
For a `FAILURE`, the console tail usually holds the compiler error:

```bash
curl -fsS "https://ci.ros2.org/job/ci_linux/<build>/consoleText" | grep -n -B2 -A8 -m5 'error:'
```

## 3. Report

One line per job: OS, result, duration, and the number of failed tests.
Then the failing test names grouped by package, with the first error line each.
Say whether the failures look related to the PR (tests in the touched packages) or known flaky (also failing on the nightly, see `buildfarm-triage`).
Offer a re-run through `ci-trigger` only when the user asks or the failure is unrelated to the change, and let them confirm as always.
