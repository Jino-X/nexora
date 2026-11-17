#!/usr/bin/env python3
"""Create local .env files from the .env.example templates, filling development secrets with fresh
random values. Existing files are never overwritten unless --force is given.

    python3 infrastructure/scripts/bootstrap-env.py [--force]
"""

from __future__ import annotations

import argparse
import base64
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def fill(template: str, values: dict[str, str]) -> str:
    out = []
    for line in template.splitlines():
        key = line.split("=", 1)[0].strip()
        if not line.startswith("#") and "=" in line and key in values:
            line = f"{key}={values[key]}"
        out.append(line)
    return "\n".join(out) + "\n"


def write(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        print(f"skip  {path.relative_to(ROOT)} (exists; use --force to overwrite)")
        return
    path.write_text(content)
    path.chmod(0o600)
    print(f"wrote {path.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    internal_key = secrets.token_urlsafe(32)
    api_values = {
        "DEV_JWT_SECRET": secrets.token_urlsafe(48),
        "INTERNAL_SERVICE_KEY": internal_key,
        "VAULT_MASTER_KEYS": f"dev1:{base64.b64encode(secrets.token_bytes(32)).decode()}",
        "VAULT_ACTIVE_KEY_ID": "dev1",
    }
    api_dir = ROOT / "services" / "api"
    write(api_dir / ".env", fill((api_dir / ".env.example").read_text(), api_values), args.force)

    agent_dir = ROOT / "services" / "voice-agent"
    if (agent_dir / ".env.example").exists():
        write(agent_dir / ".env", fill((agent_dir / ".env.example").read_text(),
                                       {"NEXORA_INTERNAL_SERVICE_KEY": internal_key}), args.force)

    web_dir = ROOT / "apps" / "web"
    if (web_dir / ".env.example").exists():
        write(web_dir / ".env.local", (web_dir / ".env.example").read_text(), args.force)

    speech_dir = ROOT / "services" / "speech"
    if (speech_dir / ".env.example").exists():
        write(speech_dir / ".env", (speech_dir / ".env.example").read_text(), args.force)


if __name__ == "__main__":
    main()
