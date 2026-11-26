#!/bin/sh
set -eu
if command -v uv >/dev/null; then
  [ -x .venv/bin/python ] || uv venv --python 3.12 .venv
  uv pip install --python .venv/bin/python -r requirements.txt
else
  [ -x .venv/bin/python ] || python3.12 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
