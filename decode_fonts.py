#!/usr/bin/env python3
"""Decode base64 font sidecars into .ttf files at build time (GitHub text push cannot carry binary fonts)."""
from pathlib import Path
import base64
static = Path(__file__).resolve().parent / "static"
for name in ("inter", "pf", "pfi"):
    src = static / f"{name}.ttf.b64"
    dst = static / f"{name}.ttf"
    if not src.exists():
        raise SystemExit(f"missing {src}")
    dst.write_bytes(base64.b64decode(src.read_text().encode("ascii")))
    print(f"wrote {dst} ({dst.stat().st_size} bytes)")
