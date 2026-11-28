---
name: rosdistro-release
description: >
  Walk a maintainer through releasing a ROS 2 package: changelog and version bump with
  catkin_generate_changelog and catkin_prepare_release, the bloom-release run that opens the
  ros/rosdistro pull request, first-time versus subsequent releases, the rosdistro checklist,
  and how to verify the release landed. Use whenever the user asks to release, bloom, bump the
  version, update the changelog, add a package to rosdistro, or index a repository for a
  distribution.
---

# Release to rosdistro

A release is a sequence of tool runs that the human confirms one by one.
Bloom opens the `ros/rosdistro` pull request itself; that PR body is tool-generated and is not agent authorship, but the human runs bloom and answers its prompts.

## 0. Preconditions

- The change is merged on the branch being released (`rolling` for the rolling release, the distro branch for a distro release).
- CI is green on that branch (`ci-status`).
- The package is released in the target distribution, or this is a first release and the maintainer has the rights.
- Tools: `python3-bloom`, `python3-catkin-pkg`, `ros-dev-tools`; a GitHub token for bloom's PR step, kept in the user's environment.

Read `bloom-release --help` and the [release page](https://docs.ros.org/en/rolling/How-To-Guides/Releasing/Releasing-a-Package.html) rather than relying on memory; the flags change.

## 1. Changelog and version

```bash
catkin_generate_changelog                     # updates CHANGELOG.rst per package from git log
# the human edits the entries: one line per change, no "update", no agent-speak
catkin_prepare_release --no-push -y           # bumps package.xml versions, commits, tags locally
```

Show the diff before anything is pushed.
The human pushes the commit and the tag: `git push && git push --tags`.
Rules: semantic version, one version across all packages of the repository, changelog entries reference PR numbers.

## 2. Bloom

First release of a repository into a distribution:

```bash
bloom-release --new-track --rosdistro <distro> --track <distro> <repo_name>
```

Subsequent releases:

```bash
bloom-release --rosdistro <distro> --track <distro> <repo_name>
```

Bloom asks for the release repository (`ros2-gbp/<repo_name>-release`), the upstream URL and branch, and the version tag; it then pushes the release branches and offers to open the rosdistro PR.
The human answers every prompt; do not script answers into it.

## 3. The rosdistro PR

Bloom's PR edits `<distro>/distribution.yaml`.
A first release also needs the `source` and `doc` entries and the maintainer listed in `package.xml`.
Checklist the rosdistro reviewers apply:

1. The release repository exists under `ros2-gbp` and the version matches the tag.
2. Every package name is unique across the distribution and follows REP-144.
3. Dependencies are released in the same distribution or are rosdep keys.
4. The license is OSI approved and matches the files.
5. Status `developed` or `maintained` in the `source` entry.

The human submits and watches the review; replies are theirs.

## 4. Verify

The build farm builds the package within a day and `https://build.ros2.org/` shows the jobs; `buildfarm-triage` helps when one fails.
After the next sync, `apt update && apt policy ros-<distro>-<package>` shows the version, and `rosdep update` knows the key.
Report only what you observed.
