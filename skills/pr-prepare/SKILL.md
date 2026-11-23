---
name: pr-prepare
description: >
  Build the pull request packet for a ROS 2 mainline contribution: the target repository's
  PR template filled with the facts (Fixes #, the generative-AI disclosure, the verification
  actually performed) and the sections the human must write left for them, plus the exact
  gh command for the human to submit. Use when the user asks to open, create, prepare, or
  draft a PR for a ros2/* or ament/* repository, or when a branch is ready for review. Never
  run gh pr create yourself under the osra-ros2 profile.
---

# PR packet

You produce a local file, not a pull request.
The human writes the description and submits.

## 1. Gather the facts

- `.ros2-agent-kit/context.json` from `contribute-preflight`: repository, issue number, base branch.
  If it is missing, ask for the issue number and confirm the base is `rolling`.
- The commits on the branch: `git log --oneline upstream/rolling..HEAD`.
- The verification that was actually run on the current tree:

  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT:-.}/gate/ros2-gate" evidence
  ```

  Only entries printed here may be listed.
  If nothing is listed, run the build and tests through `ros2-gate run -- ...` first, or write "none" and tell the user.
- Which packages the branch touches: `python3 tools/detect_packages.py --local`.

## 2. Get the template

Use the repository's `.github/PULL_REQUEST_TEMPLATE.md` when it exists.
Most `ros2` repositories use the organization default; cache it once:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.}/tools/fetch_templates.py" ros2
```

Keep every heading of the template, in order.

## 3. Write `.ros2-agent-kit/PR_BODY.md`

Fill in only the factual parts:

- `Fixes #<issue>` replacing the `Fixes # (issue)` placeholder.
- The "Did you use Generative AI?" section: the tool, the model, and which parts you generated (for example "unit tests in `test_foo.cpp`; the fix itself is hand-written").
  Never leave it empty and never write "No" when you helped.
- An "Additional Information" block titled "Verification performed" listing the evidence entries verbatim (command, exit code, commit).
- The description and the user-facing-change sections stay empty.
  Put an HTML comment in each with questions that help the human write it, for example `<!-- ros2-agent-kit: human writes this. What was wrong, why this fix, what did you consider and reject? -->`.
  The G4 gate reports those empty sections as warnings while the file is a draft; that is expected, and it is not a request for you to write them.

Start the file with a checklist in an HTML comment so GitHub hides it:

```markdown
<!-- ros2-agent-kit checklist (delete when done)
- [ ] target branch is rolling
- [ ] one feature per PR, no incidental changes
- [ ] documentation updated if behavior changed
- [ ] "Allow edits by maintainers" is selected
- [ ] every commit is signed off; run: python3 gate/ros2-gate check-range
-->
```

## 4. Hand over

Run the final check once the human has filled the description:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.}/gate/ros2-gate" check-pr-body .ros2-agent-kit/PR_BODY.md --issue <n>
```

Then give the human the exact command, and do not run it:

```bash
gh pr create --repo ros2/<repo> --base rolling --title "<title>" --body-file .ros2-agent-kit/PR_BODY.md
```

Mention that the branch must be pushed to their fork first (`git push -u origin <topic>`), that G2 will require evidence for the current tree before the push, and that review replies are theirs to write too; see `review-respond`.
