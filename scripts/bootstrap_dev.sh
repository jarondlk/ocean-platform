#!/usr/bin/env sh
set -eu

project_venv_dir="${PROJECT_VENV_DIR:-.venv}"
project_python="${PROJECT_PYTHON:-python3.12}"

"$project_python" -m venv "$project_venv_dir"
"$project_venv_dir/bin/python" -m pip install --upgrade pip
"$project_venv_dir/bin/python" -m pip install \
  --require-hashes \
  -r requirements/dev.txt
"$project_venv_dir/bin/python" -m pip check

printf 'Development environment ready at %s\n' "$project_venv_dir"
