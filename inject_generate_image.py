#!/usr/bin/env python3
"""
inject_generate_image.py - injects POST /api/generate-image into main.py on the server.

On the droplet (after push to main), path must be api/ on GitHub:
  curl -s https://raw.githubusercontent.com/CEMTrading888/cem-bot-builder/main/api/inject_generate_image.py | python3
"""
import ast
import os
import sys
import textwrap

LOG = "/var/www/cemtrading888/inject_generate_image_log.txt"
TARGET = "/var/www/cemtrading888/main.py"
START_MARKER = "# === CEM_GENERATE_IMAGE_INJECT_START ==="
END_MARKER = "# === CEM_GENERATE_IMAGE_INJECT_END ==="


def log(message: str) -> None:
    print(message)
    try:
        with open(LOG, "a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except Exception:
        pass


try:
    open(LOG, "w", encoding="utf-8").close()
except Exception:
    pass

log("=== inject_generate_image.py START ===")

if not os.path.exists(TARGET):
    log(f"ERROR: {TARGET} not found - skip generate-image inject")
    sys.exit(0)

try:
    source = open(TARGET, encoding="utf-8").read()
except Exception as exc:
    log(f"READ FAILED: {exc}")
    sys.exit(1)

if START_MARKER in source and END_MARKER in source:
    before = source[: source.index(START_MARKER)]
    after = source[source.index(END_MARKER) + len(END_MARKER) :]
    source = before + after
    log("Stripped previous generate-image injection block")

route_block = textwrap.dedent(
    """

    # === CEM_GENERATE_IMAGE_INJECT_START ===
    import asyncio as _cem_img_asyncio
    import base64 as _cem_img_base64
    import json as _cem_img_json
    import os as _cem_img_os
    import time as _cem_img_time
    import urllib.error as _cem_img_error
    import urllib.parse as _cem_img_parse
    import urllib.request as _cem_img_request
    from fastapi import HTTPException as _cem_img_HTTPException
    from fastapi import Request as _cem_img_Request
    from fastapi.responses import JSONResponse as _cem_img_JSONResponse


    def _cem_img_placeholder(env_key: str, label: str):
        return {"placeholder": True, "message": f"{label}: add {env_key} to .env to activate"}


    def _cem_img_http_error(label: str, exc: Exception):
        detail = str(exc)
        if isinstance(exc, _cem_img_error.HTTPError):
            try:
                raw = exc.read().decode("utf-8", errors="ignore").strip()
                if raw:
                    detail = raw
            except Exception:
                pass
        raise _cem_img_HTTPException(status_code=502, detail=f"{label} request failed: {detail[:600]}")


    def _cem_img_request_json(label: str, url: str, headers: dict, payload=None, method: str = "GET"):
        data = None if payload is None else _cem_img_json.dumps(payload).encode("utf-8")
        request = _cem_img_request.Request(url, data=data, headers=headers, method=method)
        try:
            with _cem_img_request.urlopen(request, timeout=90) as response:
                raw = response.read().decode("utf-8")
        except Exception as exc:
            _cem_img_http_error(label, exc)
        try:
            return _cem_img_json.loads(raw)
        except Exception as exc:
            raise _cem_img_HTTPException(status_code=502, detail=f"{label} returned invalid JSON: {exc}")


    def _cem_img_guess_mime_from_b64(value: str):
        if not value:
            return "image/png"
        if value.startswith("/9j/"):
            return "image/jpeg"
        if value.startswith("iVBOR"):
            return "image/png"
        if value.startswith("R0lGOD"):
            return "image/gif"
        if value.startswith("UklGR"):
            return "image/webp"
        return "image/png"


    def _cem_img_data_url_from_b64(value: str, mime_type: str = ""):
        safe_mime = mime_type or _cem_img_guess_mime_from_b64(value)
        return f"data:{safe_mime};base64,{value}"


    def _cem_img_download_data_url(url: str, headers=None):
        request = _cem_img_request.Request(url, headers=headers or {}, method="GET")
        try:
            with _cem_img_request.urlopen(request, timeout=90) as response:
                data = response.read()
                mime_type = response.headers.get_content_type() or "image/png"
        except Exception as exc:
            _cem_img_http_error("image download", exc)
        encoded = _cem_img_base64.b64encode(data).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"


    def _cem_img_build_pollinations_payload(prompt: str, style: str = "", model_hint: str = ""):
        model_lookup = {
            "grok": "flux",
            "flux": "flux",
            "dalle": "gptimage",
            "cembot": "flux",
        }
        chosen_model = model_lookup.get(str(model_hint or "").strip().lower(), "flux")
        prompt_parts = [
            str(prompt or "").strip(),
            str(style or "").strip(),
            "professional",
            "high quality",
            "digital art",
        ]
        full_prompt = ", ".join(part for part in prompt_parts if part)
        encoded = _cem_img_parse.quote(full_prompt[:3000])
        image_url = (
            "https://image.pollinations.ai/prompt/"
            f"{encoded}?width=512&height=512&model={chosen_model}&nologo=true&enhance=true"
        )
        return {
            "url": image_url,
            "image_url": image_url,
            "prompt": full_prompt,
            "status": "ok",
            "provider": "pollinations",
            "model": chosen_model,
        }


    def _cem_img_with_query(url: str, **params):
        parsed = _cem_img_parse.urlsplit(url)
        query = dict(_cem_img_parse.parse_qsl(parsed.query, keep_blank_values=True))
        query.update({key: value for key, value in params.items() if value not in (None, "")})
        return _cem_img_parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, _cem_img_parse.urlencode(query), parsed.fragment)
        )


    def _cem_img_generate_grok(prompt: str):
        api_key = (_cem_img_os.getenv("XAI_API_KEY") or "").strip()
        if not api_key:
            return _cem_img_placeholder("XAI_API_KEY", "Grok Image")
        payload = {
            "model": "grok-imagine-image",
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
        }
        data = _cem_img_request_json(
            "xAI image generation",
            "https://api.x.ai/v1/images/generations",
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            payload,
            method="POST",
        )
        items = data.get("data") if isinstance(data, dict) else None
        first = items[0] if isinstance(items, list) and items else (data if isinstance(data, dict) else {})
        if isinstance(first, dict) and first.get("b64_json"):
            return {"image_url": _cem_img_data_url_from_b64(first["b64_json"]), "provider": "grok"}
        if isinstance(first, dict) and first.get("url"):
            return {"image_url": _cem_img_download_data_url(first["url"]), "provider": "grok"}
        if isinstance(data, dict) and data.get("url"):
            return {"image_url": _cem_img_download_data_url(data["url"]), "provider": "grok"}
        raise _cem_img_HTTPException(status_code=502, detail="xAI image response missing image data")


    def _cem_img_generate_flux(prompt: str):
        api_key = (_cem_img_os.getenv("BFL_API_KEY") or "").strip()
        if not api_key:
            return _cem_img_placeholder("BFL_API_KEY", "Flux Pro")
        request_data = _cem_img_request_json(
            "Flux generation request",
            "https://api.bfl.ai/v1/flux-pro-1.1",
            {
                "accept": "application/json",
                "x-key": api_key,
                "Content-Type": "application/json",
            },
            {
                "prompt": prompt,
                "width": 1024,
                "height": 1024,
            },
            method="POST",
        )
        request_id = request_data.get("id") if isinstance(request_data, dict) else None
        polling_url = request_data.get("polling_url") if isinstance(request_data, dict) else None
        if not request_id or not polling_url:
            raise _cem_img_HTTPException(status_code=502, detail="Flux generation did not return a polling URL")
        final_url = _cem_img_with_query(str(polling_url), id=request_id)
        for _ in range(60):
            result = _cem_img_request_json(
                "Flux polling",
                final_url,
                {
                    "accept": "application/json",
                    "x-key": api_key,
                },
                method="GET",
            )
            status = str((result or {}).get("status") or "").strip().lower()
            if status == "ready":
                sample_url = (((result or {}).get("result") or {}).get("sample") or result.get("sample") or "").strip()
                if not sample_url:
                    raise _cem_img_HTTPException(status_code=502, detail="Flux result was ready but missing sample URL")
                return {"image_url": _cem_img_download_data_url(sample_url), "provider": "flux"}
            if status in {"error", "failed"}:
                raise _cem_img_HTTPException(status_code=502, detail=f"Flux generation failed: {result}")
            _cem_img_time.sleep(0.5)
        raise _cem_img_HTTPException(status_code=504, detail="Flux generation timed out")


    def _cem_img_generate_dalle(prompt: str):
        api_key = (_cem_img_os.getenv("OPENAI_API_KEY") or "").strip()
        if not api_key:
            return _cem_img_placeholder("OPENAI_API_KEY", "DALL-E 3")
        data = _cem_img_request_json(
            "OpenAI image generation",
            "https://api.openai.com/v1/images/generations",
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            {
                "model": "dall-e-3",
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",
                "quality": "standard",
                "style": "vivid",
                "response_format": "b64_json",
            },
            method="POST",
        )
        items = data.get("data") if isinstance(data, dict) else None
        first = items[0] if isinstance(items, list) and items else {}
        if isinstance(first, dict) and first.get("b64_json"):
            return {
                "image_url": _cem_img_data_url_from_b64(first["b64_json"]),
                "provider": "dalle",
                "revised_prompt": data.get("revised_prompt"),
            }
        if isinstance(first, dict) and first.get("url"):
            return {
                "image_url": _cem_img_download_data_url(first["url"]),
                "provider": "dalle",
                "revised_prompt": data.get("revised_prompt"),
            }
        result_value = data.get("result") if isinstance(data, dict) else None
        if isinstance(result_value, str) and result_value.startswith("http"):
            return {"image_url": _cem_img_download_data_url(result_value), "provider": "dalle"}
        if isinstance(result_value, str) and result_value:
            return {"image_url": _cem_img_data_url_from_b64(result_value), "provider": "dalle"}
        raise _cem_img_HTTPException(status_code=502, detail="OpenAI image response missing image data")


    @app.post("/api/generate")
    async def generate_pollinations_image(request: _cem_img_Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        prompt = str((body or {}).get("prompt", "") or "").strip()
        style = str((body or {}).get("style", "trading dashboard") or "trading dashboard").strip()
        model_hint = str((body or {}).get("model", "") or "").strip()
        if not prompt:
            return _cem_img_JSONResponse({"error": "No prompt provided"}, status_code=400)
        return _cem_img_JSONResponse(_cem_img_build_pollinations_payload(prompt, style, model_hint))


    @app.post("/api/generate-image")
    async def generate_image(request: _cem_img_Request):
        body = await request.json()
        prompt = str(body.get("prompt", "") or "").strip()
        model = str(body.get("model", "grok") or "grok").strip().lower()

        if not prompt:
            return {"placeholder": True, "message": "Prompt required for image generation"}

        safe_prompt = prompt[:4000]

        if model == "grok":
            return await _cem_img_asyncio.to_thread(_cem_img_generate_grok, safe_prompt)

        if model == "flux":
            return await _cem_img_asyncio.to_thread(_cem_img_generate_flux, safe_prompt)

        if model == "dalle":
            return await _cem_img_asyncio.to_thread(_cem_img_generate_dalle, safe_prompt)

        if model == "cembot":
            return {"placeholder": True, "message": "CEMbot Custom: endpoint ready - model training in progress"}

        return {"placeholder": True, "message": f"Model not configured yet: {model}"}


    # === CEM_GENERATE_IMAGE_INJECT_END ===
    """
).strip("\n")

insert_pos = source.rfind("\nif __name__")
if insert_pos == -1:
    insert_pos = len(source)
    log("No 'if __name__' found - appending at end")
else:
    log(f"Inserting before 'if __name__' at pos {insert_pos}")

patched = source[:insert_pos] + "\n\n" + route_block + source[insert_pos:]

try:
    ast.parse(patched)
    log("SYNTAX OK")
except SyntaxError as exc:
    log(f"SYNTAX ERROR: {exc}")
    lines = patched.split("\n")
    start = max(0, (exc.lineno or 1) - 3)
    end = min(len(lines), (exc.lineno or 1) + 3)
    for index, line in enumerate(lines[start:end], start=start + 1):
        log(f"  {index}: {line}")
    sys.exit(1)

try:
    with open(TARGET, "w", encoding="utf-8") as handle:
        handle.write(patched)
except Exception as exc:
    log(f"WRITE FAILED: {exc}")
    sys.exit(1)

log("generate-image injection written successfully")
