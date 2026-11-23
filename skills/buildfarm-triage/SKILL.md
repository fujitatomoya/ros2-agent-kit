---
name: buildfarm-triage
description: >
  Fetch and summarize failure logs from build.ros2.org binary and devel jobs and from
  ci.ros2.org nightly jobs for a ROS 2 package: identify the failing stage, extract the first
  real error with context, say which package and distribution are affected, and check whether
  the same failure is already reported. Use whenever a maintainer asks why a buildfarm job is
  red, what broke the nightly, to look at a build.ros2.org failure email, or to triage a
  packaging failure.
---

# Buildfarm triage

Read-only.
The result is a summary the maintainer uses to decide what to fix or whom to notify.

## Where the jobs are

| Job | URL pattern |
| --- | --- |
| Binary package, Ubuntu | `https://build.ros2.org/job/<D>bin_uN64__<pkg>__ubuntu_<codename>_amd64__binary/` |
| Devel (source build and test) | `https://build.ros2.org/job/<D>dev__<pkg>__ubuntu_<codename>_amd64/` |
| Nightly, ci.ros2.org | `https://ci.ros2.org/job/nightly_linux_debug/`, `nightly_linux_release`, `nightly_linux-aarch64_release`, `nightly_win_rel`, `nightly_osx_release` |

`<D>` is the distribution letter in upper case (`H` for humble, `J` for jazzy, `R` for rolling); `<codename>` is the Ubuntu release.
The `lastFailedBuild` and `lastBuild` aliases avoid guessing numbers.

## Fetch

```bash
curl -fsS "<job>/lastBuild/api/json?tree=result,timestamp,number,changeSet[items[msg,author[fullName]]]"
curl -fsS "<job>/lastBuild/consoleText" > console.txt
grep -n -m1 -E 'error:|Error [0-9]|FAILED|CMake Error|ERROR: the following rosdeps|No such file' console.txt
curl -fsS "<job>/lastBuild/testReport/api/json?tree=failCount,suites[cases[className,name,status,errorDetails]]"
```

Read the console around the first hit with `sed -n '<start>,<end>p' console.txt`; the last lines of a Jenkins log are usually cleanup, not the cause.

## Classify

1. Dependency: `rosdep` resolution or apt failure; usually infrastructure or a missing key.
2. Configure: CMake error; often a dependency's exported targets changed.
3. Compile: compiler error; find the first `error:` and the file.
4. Test: `UNSTABLE` result; list the failing tests and their first assertion message.
5. Infrastructure: timeouts, agent offline, network; look at `https://status.openrobotics.org/`.

Check whether the nightly on ci.ros2.org fails the same way, and search for an existing report:

```bash
gh search issues --owner ros2 "<first error line, shortened>" --state open --limit 5
```

## Report

Package, distribution, job, first failing stage, the error with five lines of context, the changeset since the last success, whether it is already reported, and what to do next phrased as options.
Opening the issue or commenting is the maintainer's action; `issue-report` prepares the body if they want one.
