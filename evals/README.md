# Skill trigger evaluations

These are `claude plugin eval` cases (Claude Code 2.1.269 or later).
Each `triggers-<skill>` case sends one prompt that should activate that skill and passes when the `Skill` tool was invoked with that skill's name.
`ignores-unrelated-request` sends an unrelated prompt and passes when none of the pushy skills fired.

Run them before a release, not on every PR; every run is a real model call:

```bash
claude plugin eval . --trust-plugin --ablation none --runs 3 --threshold 0.8 --no-publish --max-cost-usd 10 --json results.json
```

`--ablation none` keeps the `Skill` graders scored and halves the cost.
Results land in `evals/results/`, which is ignored by git.
When a case fails, the usual cause is the skill's `description` not matching the prompt's phrasing; adjust the description, not the prompt.
