#!/usr/bin/env python3
"""
Replace all /mcp-proxy* FastAPI routes in /var/www/cemtrading888/main.py with the
Streamable HTTP transport block from the repo (GET + POST + OPTIONS per embedded spec).

Run on droplet:
  curl -s https://raw.githubusercontent.com/CEMTrading888/cem-bot-builder/main/api/inject_mcp_streamable_http.py | python3
"""
import ast
import os
import sys

MAIN = "/var/www/cemtrading888/main.py"
LEGACY_START = "# === CEM_STREAMABLE_MCP_START ==="
LEGACY_END = "# === CEM_STREAMABLE_MCP_END ==="
TRANSPORT_START = "# ── MCP Streamable HTTP Transport (2025-03-26 spec) ──────────────────────────"
TRANSPORT_END = "# ── End MCP Transport ─────────────────────────────────────────────────────────"


def strip_between(src: str, start: str, end: str) -> str:
    if start not in src or end not in src:
        return src
    a = src.index(start)
    b = src.index(end, a) + len(end)
    # drop following newline if present
    if b < len(src) and src[b] == "\n":
        b += 1
    return src[:a] + src[b:]


def strip_mcp_proxy_routes(src: str) -> str:
    """Remove top-level @app.* lines whose decorator path includes mcp-proxy, plus the following function."""
    lines = src.splitlines(keepends=True)
    out = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if line.startswith("@app.") and "mcp-proxy" in line:
            i += 1
            while i < n and not lines[i].startswith("@app."):
                i += 1
            continue
        out.append(line)
        i += 1
    return "".join(out)


def strip_all_injected_transport(src: str) -> str:
    src = strip_between(src, LEGACY_START, LEGACY_END)
    src = strip_between(src, TRANSPORT_START, TRANSPORT_END)
    return src


# Injected verbatim (expects main.py to define Request, _json_resp, _MCP_TOOLS, _tool_result, _do_*).
BLOCK = r'''

# ── MCP Streamable HTTP Transport (2025-03-26 spec) ──────────────────────────
from fastapi.responses import StreamingResponse as _StreamingResponse
import asyncio as _asyncio
import json as _json

@app.api_route('/mcp-proxy', methods=['GET', 'POST', 'OPTIONS'])
async def mcp_streamable(request: Request):
    if request.method == 'OPTIONS':
        from fastapi.responses import Response as _R
        return _R('', headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, Accept, mcp-session-id',
        })
    if request.method == 'GET':
        async def keep_alive():
            while True:
                yield ': ping\n\n'
                await _asyncio.sleep(20)
        return _StreamingResponse(keep_alive(), media_type='text/event-stream', headers={
            'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Access-Control-Allow-Origin': '*',
        })
    try:
        body = await request.json()
    except Exception:
        return _json_resp({'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Parse error'}})
    method = body.get('method','')
    id_ = body.get('id')
    params = body.get('params') or {}
    if method == 'initialize':
        result = {'protocolVersion':'2025-03-26','capabilities':{'tools':{}},'serverInfo':{'name':'CEMTrading888-Brain','version':'3.0.0'}}
    elif method in ('notifications/initialized','initialized'):
        result = {}
    elif method == 'tools/list':
        result = {'tools': _MCP_TOOLS}
    elif method == 'tools/call':
        name = params.get('name','')
        args = params.get('arguments') or {}
        if name == 'write_brain':
            out = _do_write_brain(args.get('key','UNNAMED'), args.get('text',''), args.get('category','context'))
        elif name == 'write_task':
            out = _do_write_task(args.get('title',''), args.get('description',''), args.get('status','pending'))
        elif name == 'read_brain':
            out = _do_read_brain(args.get('query',''))
        elif name == 'get_status':
            out = _do_get_status()
        else:
            return _json_resp({'jsonrpc':'2.0','id':id_,'error':{'code':-32601,'message':f'Tool not found: {name}'}})
        result = _tool_result(out)
    else:
        return _json_resp({'jsonrpc':'2.0','id':id_,'error':{'code':-32601,'message':f'Method not found: {method}'}})
    resp_data = _json.dumps({'jsonrpc':'2.0','id':id_,'result':result})
    async def sse_resp():
        yield f'data: {resp_data}\n\n'
    return _StreamingResponse(sse_resp(), media_type='text/event-stream', headers={
        'Cache-Control':'no-cache','X-Accel-Buffering':'no','Access-Control-Allow-Origin':'*',
    })
# ── End MCP Transport ─────────────────────────────────────────────────────────
'''


def main() -> None:
    if not os.path.isfile(MAIN):
        print(f"ERROR: {MAIN} not found", file=sys.stderr)
        sys.exit(1)
    with open(MAIN, "r", encoding="utf-8") as f:
        src = f.read()
    src = strip_all_injected_transport(src)
    src = strip_mcp_proxy_routes(src)
    insert_at = src.rfind("\nif __name__")
    if insert_at == -1:
        insert_at = len(src)
    patched = src[:insert_at] + BLOCK + src[insert_at:]
    try:
        ast.parse(patched)
    except SyntaxError as e:
        print(f"SYNTAX ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    with open(MAIN, "w", encoding="utf-8") as f:
        f.write(patched)
    print(f"OK: MCP Streamable HTTP block written to {MAIN}")


if __name__ == "__main__":
    main()
