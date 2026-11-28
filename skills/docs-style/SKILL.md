---
name: docs-style
description: >
  ROS documentation conventions for Markdown and reStructuredText: one sentence per line, ATX
  headings in Markdown, the RST heading hierarchy used by ros2_documentation, a language on every
  code block, and README expectations for packages. Use whenever writing or editing README.md,
  design documents, docs.ros.org pages, package documentation, or any .md or .rst file in a ROS 2
  repository.
---

# ROS documentation style

- One sentence per line.
  Diffs then show exactly which sentence changed, and reviewers can comment on one sentence.
- Markdown headings are ATX (`#`, `##`), one `#` title per file, no skipped levels.
- Every fenced code block names a language: `bash`, `cpp`, `python`, `cmake`, `xml`, `yaml`, `text`.
- Prefer `ros2 run <package> <executable>` and full commands that a reader can paste.
- Use the distribution name the page is for, and `rolling` only for unreleased behavior.
- Link to docs.ros.org pages by their stable URL, and to GitHub issues and PRs by number with a link.

## reStructuredText on docs.ros.org

Heading hierarchy in `ros2_documentation`:

```rst
Page title
==========

Section
-------

Subsection
^^^^^^^^^^

Sub-subsection
~~~~~~~~~~~~~~
```

Underlines are at least as long as the text.
Code blocks are `.. code-block:: bash` with a blank line and a 3-space indent.
Tabs for distributions use the `.. tabs::` directive already present on neighboring pages; copy a sibling page's structure.
Build locally with `make html` in the documentation repository when changing more than a sentence.

## Package README

A package README states what the package does, how to build and run it, its parameters and interfaces (topics, services, actions with types and QoS), and a link to the design or API docs.
Keep examples runnable.

## Design documents

ROS 2 design documents live in `ros2/design` or the repository's `doc/` directory and follow the same one-sentence-per-line rule.
New features and infrastructure changes need one before the PR; see the `contribute-preflight` skill.
