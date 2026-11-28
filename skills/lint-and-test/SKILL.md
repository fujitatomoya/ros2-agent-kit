---
name: lint-and-test
description: >
  How to build, lint, and test ROS 2 packages the way the mainline expects, and how to record
  the result as evidence: colcon build and test with --packages-select, ament_lint_auto and
  ament_lint_common, running single linters, reading colcon test-result, coverage, and license
  headers. Use whenever the user asks to build, test, lint, or verify a ROS 2 package, before
  claiming that a build or test passed, or when a PR packet needs its verification block.
---

# Lint and test

A result may be reported only if it was run on the current tree.
Run through the evidence ledger so the PR packet and the G2 push gate can see it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.}/gate/ros2-gate" run -- colcon build --packages-select <pkg> --symlink-install
python3 "${CLAUDE_PLUGIN_ROOT:-.}/gate/ros2-gate" run -- colcon test --packages-select <pkg>
python3 "${CLAUDE_PLUGIN_ROOT:-.}/gate/ros2-gate" evidence
```

## Build

- Source the distribution first: `source /opt/ros/$ROS_DISTRO/setup.bash`; check `ros2 doctor` if anything looks off.
- Build only what changed plus dependents when needed: `--packages-select <pkg>` or `--packages-up-to <pkg>`, and `--packages-above <pkg>` for dependents.
- `--event-handlers console_direct+` shows compiler output live; `--cmake-args -DCMAKE_BUILD_TYPE=Debug` for debugging.
- Warnings are errors in review: fix `-Wall -Wextra -Wpedantic` output.
- Core repositories are built against `rolling` from source with `vcs import` of `ros2.repos`; a change in `rcl` means rebuilding `rclcpp` and above.

## Test

```bash
colcon test --packages-select <pkg> --event-handlers console_direct+
colcon test-result --verbose
```

- `colcon test` runs the linters too, through `ament_lint_auto`, so a clean `colcon test` is lint evidence as well.
- Run one test: `--ctest-args -R <name>` for gtest, `--pytest-args -k <name>` for pytest.
- `launch_testing` integration tests live under `test/` and are registered with `add_launch_test` or `pytest`.
- Flaky tests are a bug; do not loop until green.

## Lint

Every package lists `ament_lint_auto` and `ament_lint_common` as `<test_depend>` and has the `BUILD_TESTING` block in CMake, or `ament_flake8`, `ament_pep257`, and `ament_copyright` tests in an `ament_python` package.
To run one linter on changed files:

```bash
ament_uncrustify --reformat <files>
ament_cpplint <files>
ament_flake8 <files>
ament_pep257 <files>
ament_lint_cmake CMakeLists.txt
ament_xmllint package.xml
ament_copyright <paths>            # --add-missing "<holder>" apache2 adds the header
```

## Coverage

```bash
colcon build --packages-select <pkg> --cmake-args -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS="--coverage" -DCMAKE_C_FLAGS="--coverage"
colcon test --packages-select <pkg>
colcon lcov-result --packages-select <pkg>    # colcon-lcov-result
```

Core packages aim for high line coverage on new code; add tests with the change, not after review asks.

## Reporting

Quote the evidence entries in the PR packet's "Verification performed" block.
If something was not run, say "not run"; the G7 gate flags claims without evidence.
