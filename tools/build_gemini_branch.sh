#!/bin/sh
# Copyright 2026 Tomoya Fujita
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Assemble the Gemini CLI extension tree from the canonical sources.
# Usage: tools/build_gemini_branch.sh <output-dir>
# CI pushes the result to the `gemini` branch; users install with
#   gemini extensions install https://github.com/fujitatomoya/ros2-agent-kit --ref gemini
set -eu
out="${1:?output directory}"
root="$(cd "$(dirname "$0")/.." && pwd)"
case "$out" in
  /*) ;;
  *) out="$(pwd)/$out" ;;
esac
if [ -e "$out" ] && [ ! -f "$out/GENERATED.md" ]; then
  echo "refusing to replace $out: it is not a previously generated tree" >&2
  exit 1
fi
rm -rf "$out"
mkdir -p "$out/hooks"
for d in skills gate adapters policy tools templates agents assets; do
  [ -d "$root/$d" ] && cp -R "$root/$d" "$out/$d"
done
rm -rf "$out/gate/tests" "$out/tools/tests"
find "$out" -name __pycache__ -type d -prune -exec rm -rf {} +
cp "$root/LICENSE" "$out/LICENSE"
cp "$root/README.md" "$out/README.md"
cp "$root/gemini/gemini-extension.json" "$out/gemini-extension.json"
cp "$root/gemini/GEMINI.md" "$out/GEMINI.md"
cp "$root/gemini/hooks.json" "$out/hooks/hooks.json"
cp -R "$root/gemini/commands" "$out/commands"
printf 'Generated from %s by tools/build_gemini_branch.sh. Do not edit; edit main.\n' \
  "$(git -C "$root" rev-parse --short HEAD 2>/dev/null || echo unknown)" > "$out/GENERATED.md"
echo "gemini extension assembled in $out"
