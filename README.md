# ros2-agent-kit

`ros2-agent-kit` is a set of agent skills, hooks, and checks dedicated to ROS 2 development.
It targets Claude Code, Codex, and Gemini CLI from one source tree.
It covers three jobs: building ROS 2 applications, contributing issues and pull requests to the ROS 2 mainline, and recurring maintainer work such as launching CI on ci.ros2.org.

Its distinguishing feature is contribution compliance.
It encodes the DCO sign-off, the OSRF generative-tools policy, and the upstream PR and issue templates as machine-checkable rules, and enforces them before anything reaches a maintainer.

This is a personal project of a ROS 2 maintainer.
It is not an official ROS project.
The full design, including the roadmap, is in [design/ros2-agent-kit-design.md](design/ros2-agent-kit-design.md).

## Status

Milestone M0 is implemented: the policy profiles, the `ros2-gate` check engine with gates G1, G3, G4, and G5, and Claude Code packaging.
Skills, Codex and Gemini packaging, and the git-hook and CI integration for other tools follow in M1.

## What the gates do

| Gate | When | Check | Result |
| --- | --- | --- | --- |
| G1 | The agent runs `git commit` | The author is the human contributor, not an agent identity; the DCO sign-off is present; hooks are not bypassed | Block |
| G3 | The agent runs `gh pr create`, `gh issue create`, any `gh` comment, review, edit, or merge command, or a mutating `gh api` call | Not allowed under a profile where the human submits | Block, with instructions for the human |
| G4 | The agent writes `PR_BODY.md` or `ISSUE_BODY.md` | Every template section is present, the description and the generative-AI disclosure are filled in, and no placeholder is left | Block |
| G5 | Session start | The active profile and ROS distribution are printed | Inform |

Rules come from a profile selected by the git remote.
Repositories under `github.com/ros2/*` get the `osra-ros2` profile with full enforcement.
Other repositories get `generic-dco` when they mention the DCO, and `app` otherwise.
`ROS2_GATE_PROFILE=osra-ros2` forces a profile.

## Install

Claude Code:

```text
/plugin marketplace add fujitatomoya/ros2-agent-kit
/plugin install ros2@ros2-agent-kit
```

Or in one step on Claude Code 2.1.275 or later:

```text
/plugin install ros2 --marketplace fujitatomoya/ros2-agent-kit
```

Requirements: `git`, and `python3` 3.10 or newer, which every supported ROS 2 distribution provides.
The gate engine has no third-party dependencies and makes no network calls.

## Running the gate by hand

The same engine runs from the command line, from git hooks, and from CI.

```bash
python3 gate/ros2-gate profile                      # which rules apply here, and why
python3 gate/ros2-gate check-commit HEAD            # sign-off, identity, Assisted-by format
python3 gate/ros2-gate check-range                  # every commit since the merge base with rolling
python3 gate/ros2-gate check-pr-body PR_BODY.md --issue 1234
python3 gate/ros2-gate check-issue-body ISSUE_BODY.md --template bug_report
python3 gate/ros2-gate guard -- gh pr create        # allow or block, with the reason
```

Exit codes: 0 pass, 1 fail, 2 usage or runtime error.

Templates are read from the target repository, never vendored.
When a repository relies on its organization's default templates, cache them once:

```bash
python3 tools/fetch_templates.py ros2
```

## Development

```bash
cd gate && python3 -m unittest discover -s tests -t . -v
```

The repository applies its own rules: DCO sign-off on every commit, the ROS PR template with the generative-AI field, Apache-2.0 headers, and `ros2-gate check-range` in CI.
See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0, see [LICENSE](LICENSE).
