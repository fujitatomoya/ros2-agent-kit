---
name: commit
description: >
  Make commits in a ROS 2 repository that pass the mainline rules: the human contributor's
  identity, a DCO sign-off that matches it, an Assisted-by trailer for agent help, a meaningful
  message, file moves in their own commit, and no squashing during review. Use whenever you
  are about to run git commit in a ROS 2 or DCO repository, or the user asks you to commit,
  amend, or fix up commits for a ROS 2 pull request.
---

# Commit

The DCO sign-off is a personal attestation by the human.
That shapes everything below.

## Before committing

1. Confirm the identity git will use and that it is the human's, not an agent's:

   ```bash
   git var GIT_AUTHOR_IDENT
   ```

2. Show the user the diff that will be committed (`git diff --staged` after staging) and get their confirmation.
   This is the default `human-confirmed` mode: you may run the commit only after the human has seen the diff in this session.
   If the user prefers `human-only` mode, write the message to a file and let them run the commit themselves.
3. Stage deliberately with `git add <paths>`.
   No `git add -A` in a repository with untracked build artifacts.

## The commit

```bash
git commit -s -F - <<'MSG'
<imperative subject, what the change does, under about 72 characters>

<why, and anything a reviewer needs to know; wrap at 72 columns>

Assisted-by: <agent>:<model> [<tools>]
MSG
```

- `-s` adds the `Signed-off-by` line from the git identity; never type a sign-off by hand and never sign off as an agent.
- Add `Assisted-by: {agent}:{model} [{tools}]` on every commit you helped with, for example `Assisted-by: Claude:claude-fable-5-1 [Claude Code]`.
  A harness-generated `Co-Authored-By: <model>` trailer is accepted too, but `Assisted-by` is the preferred form.
- Never pass `--no-verify`; the hooks are the point.
- Put file moves and renames in their own commit so review diffs stay readable.
- Keep one logical change per commit; small commits are easier to review and to backport.

Then verify:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.}/gate/ros2-gate" check-commit HEAD
```

## During review

- Do not squash or rebase a branch that is under review; add new commits so reviewers can see what changed.
  Maintainers squash on merge.
- Do not force-push over a reviewed branch unless the maintainer asked for a rebase.
- To fix an unsigned commit: `git commit --amend -s --no-edit` (only for commits that are not yet under review).
