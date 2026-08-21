#!/usr/bin/env python3
"""Loader: assemble generator from parts then run."""
from pathlib import Path
p1 = Path(__file__).with_name("_p1.txt").read_text()
p2 = Path(__file__).with_name("_p2.txt").read_text()
code = p1 + p2
ns = {"__name__": "__main__", "__file__": str(Path(__file__).resolve())}
exec(compile(code, "generate_news_epub.py", "exec"), ns)
