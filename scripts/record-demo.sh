#!/usr/bin/env bash
# Record the red → green → archive loop with asciinema.
# GIF generation is optional and local (see README). This script never
# phones home and never touches a paid API.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGING="$(mktemp -d "${TMPDIR:-/tmp}/goal-run-demo.XXXXXX")"
CAST="${1:-$ROOT/demo.cast}"

cleanup() {
  rm -rf "$STAGING"
}
trap cleanup EXIT

python -m pip install -e "$ROOT" >/dev/null

cp "$ROOT/examples/red.md" "$STAGING/GOAL.md"
mkdir -p "$STAGING/goals/archive"

if ! command -v asciinema >/dev/null 2>&1; then
  cat <<EOF
asciinema is not installed.

Install it, then re-run this script:

  pip install asciinema
  # or: brew install asciinema

Without asciinema you can still walk the demo by hand:

  cd $STAGING
  goal-run check          # RED
  # then copy examples/green.md over GOAL.md, tick every box, check, done

EOF
  echo "staging dir (will be deleted on exit): $STAGING"
  exit 1
fi

# A tiny driver so the cast is deterministic.
cat > "$STAGING/drive.sh" <<'EOS'
set -euo pipefail
export PS1='$ '
set -x
goal-run status
goal-run check || true
# Flip RED → GREEN by replacing the failing verifier and ticking every box.
python - <<'PY'
from pathlib import Path
p = Path("GOAL.md")
text = p.read_text()
text = text.replace('python -c "raise SystemExit(1)"', 'python -c "print(\'GREEN\'); raise SystemExit(0)"')
text = text.replace("- [ ]", "- [x]")
p.write_text(text)
PY
goal-run check
goal-run done --date 2026-09-19
ls -la goals/archive
EOS

(
  cd "$STAGING"
  asciinema rec --overwrite --command "bash drive.sh" --title "goal-run red → green → archive" "$CAST"
)

echo "wrote $CAST"
echo "optional GIF: agg $CAST demo.gif   # https://github.com/asciinema/agg"
