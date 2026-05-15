#!/usr/bin/env python3
"""
Insert POST /mcp/exec and POST /mcp/write into /var/www/cemtrading888/main.py (FastAPI).

Requires in .env on the server:
  CEM_EXEC_TOKEN=<your-secret>

Then restart: pkill -f uvicorn && systemctl restart cemtrading888

  curl -s https://raw.githubusercontent.com/CEMTrading888/cem-bot-builder/main/api/inject_mcp_exec_write.py | python3
"""
import ast
import os
import sys

MAIN = "/var/www/cemtrading888/main.py"
MARKER_START = "# === CEM_MCP_EXEC_WRITE_START ==="
MARKER_END = "# === CEM_MCP_EXEC_WRITE_END ==="

BLOCK = r'''

# === CEM_MCP_EXEC_WRITE_START ===
import subprocess as _cem_subprocess
import os as _cem_os
from typing import Optional as _Optional
from fastapi import Header as _Header, HTTPException as _HTTPException, Request

_CEM_EXEC_WHITELIST = {
    "systemctl restart cemtrading888": ["/usr/bin/systemctl", "restart", "cemtrading888"],
    "pkill -f uvicorn": ["/usr/bin/pkill", "-f", "uvicorn"],
    "journalctl -u cemtrading888 -n 50 --no-pager": [
        "/usr/bin/journalctl", "-u", "cemtrading888", "-n", "50", "--no-pager",
    ],
    "df -h": ["/bin/df", "-h"],
    "free -m": ["/usr/bin/free", "-m"],
    "systemctl status cemtrading888": ["/usr/bin/systemctl", "status", "cemtrading888"],
}
_CEM_WEB_ROOT = "/var/www/cemtrading888"
_CEM_ALLOWED_EXT = (".html", ".py", ".txt")


def _cem_require_token(x_cem_token: _Optional[str]) -> None:
    exp = (_cem_os.getenv("CEM_EXEC_TOKEN") or "").strip()
    if not exp or (x_cem_token or "").strip() != exp:
        raise _HTTPException(status_code=403, detail="Forbidden")


@app.post("/mcp/exec")
async def mcp_exec(request: Request, x_cem_token: _Optional[str] = _Header(default=None, alias="X-CEM-Token")):
    _cem_require_token(x_cem_token)
    body = await request.json()
    cmd = (body.get("command") or "").strip()
    if cmd not in _CEM_EXEC_WHITELIST:
        raise _HTTPException(status_code=400, detail="command not in whitelist")
    argv = _CEM_EXEC_WHITELIST[cmd]
    try:
        p = _cem_subprocess.run(
            argv,
            capture_output=True,
            timeout=120,
            text=True,
        )
        out = (p.stdout or "") + ((p.stderr or "") if p.stderr else "")
        return {"ok": p.returncode == 0, "code": p.returncode, "output": out}
    except _cem_subprocess.TimeoutExpired:
        raise _HTTPException(status_code=504, detail="command timed out")
    except Exception as e:
        raise _HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/write")
async def mcp_write(request: Request, x_cem_token: _Optional[str] = _Header(default=None, alias="X-CEM-Token")):
    _cem_require_token(x_cem_token)
    body = await request.json()
    filename = body.get("filename")
    content = body.get("content")
    if not isinstance(filename, str) or not isinstance(content, str):
        raise _HTTPException(status_code=400, detail="invalid body")
    base = _cem_os.path.basename(filename.strip())
    if not base or ".." in filename or base != filename.strip():
        raise _HTTPException(status_code=400, detail="invalid filename")
    if not any(base.endswith(ext) for ext in _CEM_ALLOWED_EXT):
        raise _HTTPException(status_code=400, detail="allowed extensions: .html, .py, .txt")
    dest = _cem_os.path.normpath(_cem_os.path.join(_CEM_WEB_ROOT, base))
    if not dest.startswith(_CEM_WEB_ROOT + _cem_os.sep):
        raise _HTTPException(status_code=400, detail="path not allowed")
    try:
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        raise _HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "path": dest}
# === CEM_MCP_EXEC_WRITE_END ===
'''


def main() -> None:
    if not os.path.isfile(MAIN):
        print(f"ERROR: {MAIN} not found", file=sys.stderr)
        sys.exit(1)
    with open(MAIN, "r", encoding="utf-8") as f:
        src = f.read()
    if MARKER_START in src and MARKER_END in src:
        before = src[: src.index(MARKER_START)]
        after = src[src.index(MARKER_END) + len(MARKER_END) :]
        src = before + after
        print("Removed previous injection block.")
    insert_at = src.rfind("\nif __name__")
    if insert_at == -1:
        insert_at = len(src)
    patched = src[:insert_at] + BLOCK + src[insert_at:]
    try:
        ast.parse(patched)
    except SyntaxError as e:
        print(f"SYNTAX ERROR after patch: {e}", file=sys.stderr)
        sys.exit(1)
    with open(MAIN, "w", encoding="utf-8") as f:
        f.write(patched)
    print(f"Injected {MARKER_START} into {MAIN}")
    print("Append to .env if missing:")
    print('  grep -q "^CEM_EXEC_TOKEN=" /var/www/cemtrading888/.env || echo "CEM_EXEC_TOKEN=cemtrading888secrettoken2026" >> /var/www/cemtrading888/.env')


if __name__ == "__main__":
    main()
