---
name: backport
description: >
  Backport a change that is merged on rolling to released ROS 2 distributions (humble, jazzy,
  kilted, lyrical): choose the target distributions, cherry-pick with -x onto the distro branch,
  check API and ABI compatibility, title the PR "[Distro] <original title>", and hand the PR to
  the human. Use whenever the user asks to backport, cherry-pick a merged PR to a distro branch,
  land a fix on humble or jazzy, or asks which distributions a fix should go to.
---

# Backport

Rolling first, always.
A backport starts only after the change is merged on `rolling`.

## 1. Targets

Read `policy/distributions.json` in the kit for the active distributions and their end of life.
A fix goes to every active distribution it applies to; a feature usually goes to none.
Rules that limit a backport:

- No API or ABI break on a released distribution; see the `api-abi-stability` skill.
- No new deprecations on a released distribution.
- No new dependencies that are not released for that distribution.
- The distro branch may lack code the fix relies on; then the backport is a separate change, not a cherry-pick.

Confirm the target list with the human before branching.

## 2. Branch and cherry-pick

```bash
git fetch upstream
git switch -c backport/<distro>/<topic> upstream/<distro>
git cherry-pick -x <merge-or-squash-commit-sha>
```

- `-x` records the source commit in the message; keep it.
- Resolve conflicts minimally and say in the summary what differed from `rolling`.
- Keep the original author and sign-off, and add the human's own sign-off to the cherry-picked commit before anyone has seen it.
- Build and test on that distribution's branch, through `ros2-gate run --`.

## 3. PR

Title: `[Humble] <original PR title>` with the distribution capitalized.
Body: use the `pr-prepare` skill, and add "Backport of #<n>" as the first line of the description so the human only has to confirm it.
Base branch is the distro branch, not `rolling`.

Some `ros2` repositories accept the Mergify command `@Mergifyio backport <distro>` as a PR comment by a maintainer, which opens the backport automatically.
Mention it to the human; posting it is their call and their action.

## 4. CI

A backport is tested on that distribution.
Offer the `ci-trigger` skill with `--target <distro>` for the new PR.
