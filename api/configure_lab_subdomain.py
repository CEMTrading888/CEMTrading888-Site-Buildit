#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path

WEBROOT = Path("/var/www/cemtrading888")
PRIMARY_SITE = Path("/etc/nginx/sites-enabled/cemtrading888")
LAB_SITE = Path("/etc/nginx/conf.d/lab-cemtrading888.conf")
LAB_HOST = "lab.cemtrading888.com"


def extract_ssl_directives(config_text: str) -> list[str]:
    directives: list[str] = []
    patterns = (
        r"^\s*ssl_certificate\s+[^;]+;$",
        r"^\s*ssl_certificate_key\s+[^;]+;$",
        r"^\s*include\s+/etc/letsencrypt/[^;]+;$",
        r"^\s*ssl_dhparam\s+[^;]+;$",
    )
    for pattern in patterns:
        match = re.search(pattern, config_text, flags=re.MULTILINE)
        if match:
            directives.append(match.group(0).strip())
    return directives


def build_lab_config(ssl_directives: list[str]) -> str:
    if ssl_directives:
        tls_block = "\n".join(f"    {directive}" for directive in ssl_directives)
        return (
            "server {\n"
            "    listen 80;\n"
            "    listen [::]:80;\n"
            f"    server_name {LAB_HOST};\n"
            "    return 301 https://$host$request_uri;\n"
            "}\n\n"
            "server {\n"
            "    listen 443 ssl http2;\n"
            "    listen [::]:443 ssl http2;\n"
            f"    server_name {LAB_HOST};\n"
            f"    root {WEBROOT};\n"
            "    index lab-dashboard.html;\n"
            f"{tls_block}\n"
            "    location = / {\n"
            "        try_files /lab-dashboard.html =404;\n"
            "    }\n"
            "    location / {\n"
            "        try_files $uri /lab-dashboard.html =404;\n"
            "    }\n"
            "}\n"
        )
    return (
        "server {\n"
        "    listen 80;\n"
        "    listen [::]:80;\n"
        f"    server_name {LAB_HOST};\n"
        f"    root {WEBROOT};\n"
        "    index lab-dashboard.html;\n"
        "    location = / {\n"
        "        try_files /lab-dashboard.html =404;\n"
        "    }\n"
        "    location / {\n"
        "        try_files $uri /lab-dashboard.html =404;\n"
        "    }\n"
        "}\n"
    )


def main() -> None:
    lab_dashboard = WEBROOT / "lab-dashboard.html"
    if not lab_dashboard.exists():
        raise SystemExit(f"Missing expected dashboard file: {lab_dashboard}")

    primary_text = PRIMARY_SITE.read_text(encoding="utf-8") if PRIMARY_SITE.exists() else ""
    if LAB_HOST in primary_text:
        print(f"{LAB_HOST} already appears in {PRIMARY_SITE}; skipping separate lab config write.")
        return

    ssl_directives = extract_ssl_directives(primary_text)
    target_text = build_lab_config(ssl_directives)
    LAB_SITE.parent.mkdir(parents=True, exist_ok=True)
    if LAB_SITE.exists() and LAB_SITE.read_text(encoding="utf-8") == target_text:
        print(f"{LAB_SITE} already up to date.")
    else:
        LAB_SITE.write_text(target_text, encoding="utf-8")
        print(f"Wrote lab subdomain config to {LAB_SITE}.")

    subprocess.run(["nginx", "-t"], check=True)
    subprocess.run(["systemctl", "reload", "nginx"], check=True)
    print("nginx reloaded successfully.")


if __name__ == "__main__":
    main()
