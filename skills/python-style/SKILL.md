---
name: python-style
description: >
  The ROS 2 Python style rules that differ from plain PEP 8 and that agents get wrong: 100
  columns, single quotes, one import per line in the order ament_flake8 enforces, pep257
  docstrings, and ament_flake8 as the oracle. Use whenever writing or editing Python in a ROS 2
  package (rclpy, ros2cli, launch, ament_python packages, tests), before running ament_flake8
  and ament_pep257, or when the user asks about ROS 2 Python conventions.
---

# ROS 2 Python style

`ament_flake8` and `ament_pep257` decide.
These are the rules a PEP 8 habit gets wrong in ROS 2.

- Python 3 only; the version is the distribution's system Python (`python3 --version`), so do not use features newer than that.
- 100 columns, 4-space indent.
- Single quotes for strings; double quotes only to avoid escaping a single quote inside.
  Docstrings use triple double quotes.
- One import per line, no `from x import a, b`.
  Order: standard library, third party, then local, each group alphabetized; `ament_flake8` runs `flake8-import-order` in the `google` style, which also sorts `import x` and `from x import y` together by module name.
- No wildcard imports, no unused imports, no mutable default arguments.
- Docstrings follow pep257: one-line summary ending with a period, blank line, then details.
  `ament_pep257` checks every public module, class, and function.
- Comparisons: `is None`, `isinstance`, never `== None` or `type(x) ==`.
- Line continuation inside parentheses, not with backslashes.
- Type hints are welcome and should match the actual runtime types; `ament_mypy` is opt-in per package.
- Tests use `pytest`; files are `test/test_<thing>.py` and are listed in `setup.py` or found by `ament_cmake_pytest`.

Package layout for `ament_python`: `setup.py`, `setup.cfg`, `package.xml`, `resource/<package>` marker file, `<package>/__init__.py`, entry points under `console_scripts`.

Check before committing:

```bash
ament_flake8 <paths>
ament_pep257 <paths>
ament_copyright <paths>
```

Record the run with `ros2-gate run --` when the result will be reported.
