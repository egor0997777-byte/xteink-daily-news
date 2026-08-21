#!/usr/bin/env python3
"""RSS → dated EPUB + OPDS for Xteink X3.
Topic-based TOC, lead + full text, site cleanup. Stdlib only.
"""
from __future__ import annotations

import html
import re
import shutil
import time
import uuid
import zipfile
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

RSS_FEEDS = [
    ("Хабр", "https://habr.com/ru/rss/news/", "other", 5),
    ("Хабр", "https://habr.com/ru/rss/articles/", "other", 4),
    ("Хабр", "https://habr.com/ru/rss/flows/develop/", "dev", 6),
    ("Хабр", "https://habr.com/ru/rss/flows/admin/", "admin", 4),
    ("Хабр", "https://habr.com/ru/rss/flows/design/", "other", 2),
    ("Хабр", "https://habr.com/ru/rss/hubs/artificial_intelligence/all/", "ai", 5),
    ("Хабр", "https://habr.com/ru/rss/hubs/gadgets/all/", "gadgets", 3),
    ("Лайфхакер", "https://lifehacker.ru/feed/", "other", 5),
    ("VC.ru", "https://vc.ru/rss", "other", 4),
    ("iXBT", "https://www.ixbt.com/export/rss.xml", "gadgets", 6),
    ("iXBT", "https://www.ixbt.com/export/news.rss", "gadgets", 4),
    ("3DNews", "https://3dnews.ru/news/rss/", "gadgets", 6),
    ("Tproger", "https://tproger.ru/feed/", "dev", 4),
    ("DTF", "https://dtf.ru/rss/all", "other", 3),
    ("Computerra", "https://www.computerra.ru/feed/", "other", 4),
    ("N+1", "https://nplus1.ru/rss", "science", 6),
    ("HighTech", "https://hightech.fm/feed", "science", 4),
    ("Xakep", "https://xakep.ru/feed/", "admin", 4),
    ("CNews", "https://www.cnews.ru/inc/rss/news.xml", "other", 4),
    ("Mobile-Review", "https://www.mobile-review.com/rss.xml", "gadgets", 3),
]

TOPIC_ORDER = [
    ("main", "Главное"),
    ("ai", "ИИ"),
    ("gadgets", "Гаджеты и устройства"),
    ("admin", "ИТ / администрирование"),
    ("dev", "Разработка"),
    ("science", "Наука"),
    ("other", "Остальное"),
]
TOPIC_CAPS = {"main": 8, "ai": 12, "gadgets": 14, "admin": 10, "dev": 10, "science": 8, "other": 14}
MAX_TOTAL = 70
MAX_AGE_HOURS = 36
MAX_FULL_FETCH = 70
SHORT_DESC = 500
USER_AGENT = "Mozilla/5.0 (compatible; XteinkNewsBot/1.1)"
REPO, BRANCH = "egor0997777-byte/xteink-daily-news", "main"
BASE_RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
OUTPUT_DIR = Path(".")

TOPIC_KEYWORDS = {
    "ai": ["ии", "нейросет", "chatgpt", "gpt", "llm", "machine learning", "машинн", "искусственн", "openai", "claude", "gemini", "deepseek", "генератив", "diffusion", "transformer", "rag "],
    "gadgets": ["смартфон", "телефон", "ноутбук", "планшет", "наушник", "гаджет", "iphone", "android", "pixel", "xiaomi", "samsung", "macbook", "процессор", "видеокарт", "монитор", "роутер", "ssd", "hdd", "камера", "часы", "watch", "drone", "робот-пылесос"],
    "admin": ["linux", "kubernetes", "docker", "сервер", "devops", "сеть", "безопасност", "уязвим", "CVE", "firewall", "nginx", "systemd", "админ", "облак", "cloud", "vpn", "dns", "backup", "мониторинг"],
    "dev": ["python", "javascript", "typescript", "golang", "rust", "java", "программ", "разработ", "api", "framework", "git ", "код ", "frontend", "backend", "react", "vue", "kotlin", "swift", "компилятор", "алгоритм", "open source", "opensource", "github"],
    "science": ["наук", "физик", "хими", "биолог", "космос", "астроном", "исследован", "учёные", "ученые", "эксперимент", "ген ", "квант", "марс", "телескоп", "климат"],
}

def fetch_url(url, timeout=18):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()

def strip_html(text):
    if not text: return ""
    text = html.unescape(text)
    text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", text, flags=re.I|re.S)
    text = re.sub(r"</?(p|div|br|h[1-6]|li|tr|blockquote)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+", "", text) if False else re.sub(r"<[^>]+", "", text)
    text = re.sub(r"<[^>]+", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()

# NOTE: full script continues - this push may be incomplete if truncated
print("placeholder_should_not_happen")
