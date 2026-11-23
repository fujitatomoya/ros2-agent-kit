# Contributing

This is a personal project of a ROS 2 maintainer, and in the current phase nobody else is invited to own or contribute content.
See [section 11.1 of the design](design/ros2-agent-kit-design.md) for the reasoning.
Bug reports and questions are welcome as issues.

The repository applies the same rules it enforces:

- Every commit carries a Developer Certificate of Origin sign-off (`git commit -s`) that matches the commit author.
- Every pull request fills in the "Did you use Generative AI?" field of the PR template.
- Commits assisted by an agent carry an `Assisted-by: {agent}:{model}` trailer.
- Source files carry the Apache-2.0 license header.
- Documentation uses one sentence per line and ATX headings.

CI runs `ros2-gate check-range` on every pull request, so an unsigned commit fails the build.
