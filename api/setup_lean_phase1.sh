#!/usr/bin/env bash
set -euo pipefail

PY311_BIN="${1:-python3.11}"
LEAN_ROOT="/home/lean-workspace"
LEAN_VENV="$LEAN_ROOT/.venv"
DATA_ROOT="/home/lean-data"
CONFIG_FILE="$LEAN_ROOT/config/databento_config.py"

apt_updated=0

apt_install() {
  if [ "$apt_updated" -eq 0 ]; then
    apt-get update
    apt_updated=1
  fi
  DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
}

if [ ! -x "$PY311_BIN" ] && ! command -v "$PY311_BIN" >/dev/null 2>&1; then
  echo "Python 3.11 binary not found: $PY311_BIN" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  apt_install docker.io
fi

if ! command -v docker-compose >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
  if ! apt_install docker-compose; then
    apt_install docker-compose-plugin
  fi
fi

systemctl start docker
systemctl enable docker

mkdir -p "$LEAN_ROOT/config" "$LEAN_ROOT/strategies" "$DATA_ROOT/futures"

create_lean_venv() {
  rm -rf "$LEAN_VENV"
  if ! "$PY311_BIN" -m venv "$LEAN_VENV"; then
    apt_install python3.11-venv
    rm -rf "$LEAN_VENV"
    "$PY311_BIN" -m venv "$LEAN_VENV"
  fi
}

if [ ! -x "$LEAN_VENV/bin/pip" ]; then
  create_lean_venv
fi

"$LEAN_VENV/bin/pip" install --upgrade pip
"$LEAN_VENV/bin/pip" install --upgrade lean databento pandas numpy

ln -sf "$LEAN_VENV/bin/lean" /usr/local/bin/lean

if ! docker image inspect quantconnect/lean:latest >/dev/null 2>&1; then
  docker pull quantconnect/lean:latest
fi

if [ ! -f "$CONFIG_FILE" ]; then
  cat > "$CONFIG_FILE" <<'PYEOF'
DATABENTO_API_KEY = "YOUR_KEY_HERE"  # Sign up at databento.com -- $125 free credits
PYEOF
fi

lean --version
"$LEAN_VENV/bin/python" -c "import databento as db; print(db.__version__)"
