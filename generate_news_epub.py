#!/usr/bin/env python3
"""Decompress embedded generator and run."""
import base64, gzip
from pathlib import Path
b64 = Path(__file__).with_name("_gen.b64").read_text().strip()
code = gzip.decompress(base64.b64decode(b64)).decode("utf-8")
ns = {"__name__": "__main__", "__file__": str(Path(__file__).resolve())}
exec(compile(code, "generate_news_epub.py", "exec"), ns)
