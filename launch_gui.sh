#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v conda >/dev/null 2>&1; then
  echo "Conda is required by this launcher. Alternatively activate your environment and run python tiltseries_protocol_gui.py." >&2
  exit 1
fi
exec conda run --no-capture-output -n warp-tilt-prep-new python "$SCRIPT_DIR/tiltseries_protocol_gui.py"
