#!/usr/bin/env python3
import json
from pathlib import Path

MANIFEST = Path("chatgpt/issue.json")
OUTPUT = Path("chatgpt/input.json")
PARTS_ROOT = Path("chatgpt/parts")

data = json.loads(MANIFEST.read_text(encoding="utf-8"))
date = str(data["date"]).strip()
title = str(data["title"]).strip()
parts = data.get("parts", [])
if not title.startswith("МУЖСКОЙ · "):
    raise ValueError("issue title must start with МУЖСКОЙ · ")
if not parts:
    raise ValueError("manifest has no parts")

articles = []
for raw in parts:
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts or not str(path).startswith(str(PARTS_ROOT) + "/"):
        raise ValueError(f"invalid part path: {raw}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["articles"] if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError(f"part must contain a list: {raw}")
    articles.extend(rows)

if not 10 <= len(articles) <= 35:
    raise ValueError(f"merged issue has {len(articles)} articles; expected 10..35")

out = {"date": date, "title": title, "articles": articles}
OUTPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Prepared {OUTPUT}: {len(articles)} articles")
