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

# (display_source, rss_url, default_topic, max_items)
# Topics: ai, gadgets, admin, dev, science, other
RSS_FEEDS = [
    ("Хабр", "https://habr.com/ru/rss/news/", "other", 5),
    ("Хабр", "https://habr.com/ru/rss/articles/", "other", 4),
    ("Хабр", "https://habr.com/ru/rss/flows/develop/", "dev", 5),
    ("Хабр", "https://habr.com/ru/rss/flows/admin/", "admin", 4),
    ("Хабр", "https://habr.com/ru/rss/flows/design/", "other", 2),
    ("Хабр", "https://habr.com/ru/rss/hubs/artificial_intelligence/all/", "ai", 5),
    ("Хабр", "https://habr.com/ru/rss/hubs/gadgets/all/", "gadgets", 3),
    ("Лайфхакер", "https://lifehacker.ru/feed/", "other", 5),
    ("VC.ru", "https://vc.ru/rss", "other", 5),
    ("iXBT", "https://www.ixbt.com/export/rss.xml", "gadgets", 5),
    ("iXBT", "https://www.ixbt.com/export/news.rss", "gadgets", 4),
    ("3DNews", "https://3dnews.ru/news/rss/", "gadgets", 6),
    ("Tproger", "https://tproger.ru/feed/", "dev", 4),
    ("DTF", "https://dtf.ru/rss/all", "other", 3),
    ("Computerra", "https://www.computerra.ru/feed/", "other", 4),
    ("N+1", "https://nplus1.ru/rss", "science", 6),
    ("HighTech", "https://hightech.fm/feed", "science", 5),
    ("Xakep", "https://xakep.ru/feed/", "admin", 5),
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
TOPIC_CAPS = {
    "main": 8,
    "ai": 11,
    "gadgets": 12,
    "admin": 9,
    "dev": 10,
    "science": 8,
    "other": 12,
}
MAX_TOTAL = 68
MAX_AGE_HOURS = 40
MAX_FULL_FETCH = 68
SHORT_DESC = 450
# Hard cap per display source after dedup (Habr has many feeds)
SOURCE_CAPS = {
    "Хабр": 20,
    "iXBT": 8,
    "3DNews": 7,
    "Лайфхакер": 5,
    "VC.ru": 5,
    "N+1": 6,
    "HighTech": 5,
    "Xakep": 5,
    "CNews": 4,
    "Tproger": 4,
    "DTF": 3,
    "Computerra": 4,
    "Mobile-Review": 3,
}
USER_AGENT = "Mozilla/5.0 (compatible; XteinkNewsBot/1.2)"
REPO, BRANCH = "egor0997777-byte/xteink-daily-news", "main"
BASE_RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
OUTPUT_DIR = Path(".")

# Keyword hints to reclassify topic from title/desc
TOPIC_KEYWORDS = {
    "ai": [
        "ии", "нейросет", "chatgpt", "gpt", "llm", "machine learning",
        "машинн", "искусственн", "openai", "claude", "gemini", "deepseek",
        "генератив", "diffusion", "transformer", "rag ",
    ],
    "gadgets": [
        "смартфон", "телефон", "ноутбук", "планшет", "наушник", "гаджет",
        "iphone", "android", "pixel", "xiaomi", "samsung", "macbook",
        "процессор", "видеокарт", "монитор", "роутер", "ssd", "hdd",
        "камера", "часы", "watch", "drone", "робот-пылесос",
    ],
    "admin": [
        "linux", "kubernetes", "docker", "сервер", "devops", "сеть",
        "безопасност", "уязвим", "CVE", "firewall", "nginx", "systemd",
        "админ", "облак", "cloud", "vpn", "dns", "backup", "мониторинг",
    ],
    "dev": [
        "python", "javascript", "typescript", "golang", "rust", "java",
        "программ", "разработ", "api", "framework", "git ", "код ",
        "frontend", "backend", "react", "vue", "kotlin", "swift",
        "компилятор", "алгоритм", "open source", "opensource", "github",
    ],
    "science": [
        "наук", "физик", "хими", "биолог", "космос", "астроном",
        "исследован", "учёные", "ученые", "эксперимент", "ген ",
        "квант", "марс", "телескоп", "климат",
    ],
}


def fetch_url(url: str, timeout: int = 18) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", text, flags=re.I | re.S)
    text = re.sub(r"</?(p|div|br|h[1-6]|li|tr|blockquote)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --- Cleanup of full page text ---
JUNK_LINE_PATTERNS = [
    re.compile(r"^время на прочтение", re.I),
    re.compile(r"^\d+\s*мин\.?$", re.I),
    re.compile(r"^\d+\s*минут", re.I),
    re.compile(r"простой\s*$", re.I),
    re.compile(r"^сложность", re.I),
    re.compile(r"^рейтинг", re.I),
    re.compile(r"^охват", re.I),
    re.compile(r"^просмотров?", re.I),
    re.compile(r"^читател", re.I),
    re.compile(r"^\d[\d\s.,]*[kкmм]?$", re.I),  # bare numbers / 1.4K
    re.compile(r"^теги?\s*:", re.I),
    re.compile(r"^хабы?\s*:", re.I),
    re.compile(r"^комментари", re.I),
    re.compile(r"^подписаться", re.I),
    re.compile(r"^поделиться", re.I),
    re.compile(r"^источник\s*$", re.I),
    re.compile(r"^читать далее", re.I),
    re.compile(r"^все публикации", re.I),
    re.compile(r"^лучшие за", re.I),
    re.compile(r"^главная$", re.I),
    re.compile(r"^навигация", re.I),
    re.compile(r"^меню$", re.I),
    re.compile(r"^реклама$", re.I),
    re.compile(r"^cookie", re.I),
    re.compile(r"^принять$", re.I),
    re.compile(r"^войти$", re.I),
    re.compile(r"^регистрац", re.I),
    re.compile(r"^автор\s*:", re.I),
    re.compile(r"^опубликован", re.I),
    re.compile(r"^\d{1,2}\s+(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)", re.I),
    # "username 2 часа назад" / "denis-19 1 час назад"
    re.compile(r"^[\w.\-@]+\s+\d+\s+(час|мин|дн|день|недел)", re.I),
    re.compile(r"^\d+\s+(час|мин|дн|день|недел).*(назад)?$", re.I),
    re.compile(r"^open source\s*\*", re.I),
    re.compile(r"^[\w\s]+\s*\*\s*(windows|linux|ios|android|python|javascript)", re.I),
]


def clean_body_text(text: str) -> str:
    if not text:
        return ""
    lines = []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if len(s) < 3:
            continue
        skip = False
        for pat in JUNK_LINE_PATTERNS:
            if pat.search(s):
                skip = True
                break
        if skip:
            continue
        # drop short tag/hub-like tokens and lone asterisks
        if len(s) < 45 and re.fullmatch(r"[\w\s\-/+#.*=*]+", s) and s.count(" ") <= 3:
            low = s.lower().strip("* ").strip()
            if low in {
                "python", "javascript", "linux", "devops", "безопасность",
                "гаджеты", "научпоп", "космос", "новости", "статьи",
                "open source", "windows", "ios", "android", "софт", "звук",
                "системное администрирование", "разработка", "дизайн",
                "искусственный интеллект", "машинное обучение",
            } or s.strip() in ("*", "·", "•"):
                continue
        lines.append(s)
    # collapse
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


class ArticleExtractor(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "header", "aside", "form", "iframe", "noscript", "svg", "button"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in self.SKIP:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        # skip known junk classes
        classes = " ".join(v for k, v in attrs if k == "class").lower()
        if any(
            x in classes
            for x in (
                "tm-meta", "tm-article-meta", "tm-votes", "tm-user", "user-info",
                "tm-separated-list", "tm-tags", "tm-hubs", "tm-publication-stats",
                "tm-article-snippet", "tm-data-icons", "tm-icon", "tm-button",
                "share", "social", "comment", "breadcrumb", "sidebar", "related",
                "advert", "banner", "cookie", "meta-bar", "post-meta", "byline",
                "author-info", "reading-time", "views-count",
            )
        ):
            self.skip_depth += 1
            return
        if t in ("p", "br", "h1", "h2", "h3", "h4", "li", "blockquote"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            # class-based skip also uses skip_depth
            if t in ("div", "section", "span", "ul", "ol", "a"):
                # imperfect but reduces stuck skip
                pass
            return
        if t in ("p", "h1", "h2", "h3", "h4", "li", "blockquote", "div"):
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth:
            return
        s = data.strip()
        if s:
            self.parts.append(s + " ")

    def text(self) -> str:
        t = "".join(self.parts)
        t = re.sub(r"[ \t]+", " ", t)
        return re.sub(r"\n{3,}", "\n\n", t).strip()


def extract_habr(page_html: str) -> str:
    m = re.search(
        r'<div[^>]+class="[^"]*article-formatted-body[^"]*"[^>]*>(.*?)</div>\s*</div>',
        page_html,
        re.I | re.S,
    )
    if not m:
        m = re.search(
            r'<div[^>]+class="[^"]*tm-article-body[^"]*"[^>]*>(.*?)</div>',
            page_html,
            re.I | re.S,
        )
    if m:
        chunk = m.group(1)
        chunk = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", chunk, flags=re.I | re.S)
        p = ArticleExtractor()
        try:
            p.feed(chunk)
            return clean_body_text(p.text())
        except Exception:
            return clean_body_text(strip_html(chunk))
    return ""


def extract_article_text(page_html: str, url: str = "") -> str:
    if "habr.com" in url:
        t = extract_habr(page_html)
        if len(t) >= 200:
            return t[:25000]

    candidates = []
    for pat in (
        r'<article[^>]*>(.*?)</article>',
        r'<div[^>]+class="[^"]*(?:article-body|post-content|entry-content|tm-article-body|content-body|article__text|article-formatted-body)[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]+itemprop="articleBody"[^>]*>(.*?)</div>',
    ):
        m = re.search(pat, page_html, re.I | re.S)
        if m:
            candidates.append(m.group(1) if m.lastindex else m.group(0))
    chunk = max(candidates, key=len) if candidates else page_html
    chunk = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", chunk, flags=re.I | re.S)
    p = ArticleExtractor()
    try:
        p.feed(chunk)
        text = p.text()
    except Exception:
        text = strip_html(chunk)
    text = clean_body_text(text)
    return text[:25000] if len(text) >= 200 else ""


def make_lead(desc: str, body: str) -> str:
    """1–3 sentence lead from RSS desc or body start."""
    src = (desc or "").strip()
    if len(src) < 40:
        src = (body or "").strip()
    src = clean_body_text(src)
    # take first 1-3 sentences
    parts = re.split(r"(?<=[.!?…])\s+", src)
    lead_parts = []
    total = 0
    for p in parts:
        p = p.strip()
        if len(p) < 20:
            continue
        lead_parts.append(p)
        total += len(p)
        if len(lead_parts) >= 3 or total >= 280:
            break
    lead = " ".join(lead_parts).strip()
    if len(lead) > 400:
        lead = lead[:397] + "…"
    return lead


def normalize_title(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r"[^\w\sа-яё]", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t)


def parse_pubdate(item: ET.Element) -> Optional[datetime]:
    for tag in ("pubDate", "{http://purl.org/dc/elements/1.1/}date", "date"):
        el = item.find(tag)
        if el is not None and el.text:
            try:
                dt = parsedate_to_datetime(el.text.strip())
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                pass
    return None


def get_text(item: ET.Element, *tags: str) -> str:
    for tag in tags:
        el = item.find(tag)
        if el is not None and el.text:
            return el.text.strip()
        for child in item:
            if child.tag.endswith("}" + tag) or child.tag == tag:
                if child.text:
                    return child.text.strip()
    return ""


def get_link(item: ET.Element) -> str:
    link = get_text(item, "link")
    if link:
        return link
    for el in item.findall("link") + item.findall("{http://www.w3.org/2005/Atom}link"):
        href = el.get("href")
        if href:
            return href
        if el.text:
            return el.text.strip()
    return ""


def detect_topic(title: str, desc: str, default: str) -> str:
    blob = f"{title} {desc}".lower()
    scores = {k: 0 for k in TOPIC_KEYWORDS}
    for topic, kws in TOPIC_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in blob:
                scores[topic] += 1
    best = max(scores, key=scores.get)
    if scores[best] >= 1:
        return best
    return default


def score_main(it: dict) -> float:
    """Simple transparent ranking for «Главное»."""
    score = 0.0
    # prefer full body
    body_len = len(it.get("body") or "")
    if body_len > 1500:
        score += 3
    elif body_len > 600:
        score += 1.5
    # topic weight
    topic_w = {"ai": 2.5, "science": 2.0, "gadgets": 1.5, "admin": 1.5, "dev": 1.5, "other": 1.0}
    score += topic_w.get(it.get("topic", "other"), 1.0)
    # freshness (hours ago)
    if it.get("pub"):
        age_h = (datetime.now(timezone.utc) - it["pub"]).total_seconds() / 3600
        if age_h < 12:
            score += 2
        elif age_h < 24:
            score += 1
    # title length heuristic (not too short)
    tl = len(it.get("title") or "")
    if 30 <= tl <= 120:
        score += 0.5
    return score


def fetch_feed(name: str, url: str, default_topic: str, limit: int) -> list[dict]:
    items = []
    try:
        data = fetch_url(url)
        if not data or len(data) < 50:
            print(f"[WARN] {name}: empty")
            return items
        root = ET.fromstring(data)
    except Exception as e:
        print(f"[WARN] {name}: {e}")
        return items

    channel = root.find("channel")
    entries = (
        channel.findall("item")
        if channel is not None
        else (root.findall("{http://www.w3.org/2005/Atom}entry") or root.findall("entry"))
    )
    for entry in entries:
        title = get_text(entry, "title")
        link = get_link(entry)
        desc = get_text(
            entry, "description", "summary", "{http://purl.org/rss/1.0/modules/content/}encoded"
        )
        pub = parse_pubdate(entry)
        if not title or not link:
            continue
        clean_desc = strip_html(desc)
        topic = detect_topic(title, clean_desc, default_topic)
        items.append(
            {
                "title": title,
                "link": link,
                "description": clean_desc,
                "body": "",
                "lead": "",
                "pub": pub,
                "source": name,
                "topic": topic,
            }
        )
    # keep newest
    items.sort(
        key=lambda x: x["pub"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True
    )
    print(f"[OK] {name} ({default_topic}): {len(items)} → take {min(limit, len(items))}")
    return items[:limit]


def dedup(items: list[dict]) -> list[dict]:
    """Dedup by URL and title; keep the longer body/desc."""
    by_url: dict[str, dict] = {}
    by_title: dict[str, str] = {}  # title -> url key

    def quality(it: dict) -> int:
        return len(it.get("body") or "") + len(it.get("description") or "")

    for it in items:
        url = it["link"].split("?")[0].rstrip("/")
        nt = normalize_title(it["title"])
        if url in by_url:
            if quality(it) > quality(by_url[url]):
                by_url[url] = it
            continue
        if nt in by_title:
            old_url = by_title[nt]
            if quality(it) > quality(by_url[old_url]):
                del by_url[old_url]
                by_url[url] = it
                by_title[nt] = url
            continue
        by_url[url] = it
        by_title[nt] = url
    return list(by_url.values())


def enrich_full_text(items: list[dict]) -> None:
    fetched = 0
    for it in items:
        desc = it.get("description") or ""
        if len(desc) >= SHORT_DESC:
            it["body"] = clean_body_text(desc)
            it["lead"] = make_lead(desc, it["body"])
            continue
        if fetched >= MAX_FULL_FETCH:
            it["body"] = clean_body_text(desc)
            it["lead"] = make_lead(desc, it["body"])
            continue
        try:
            raw = fetch_url(it["link"], timeout=15)
            try:
                page = raw.decode("utf-8")
            except UnicodeDecodeError:
                page = raw.decode("cp1251", errors="ignore")
            text = extract_article_text(page, it["link"])
            if len(text) > len(desc) + 80:
                it["body"] = text
                fetched += 1
            else:
                it["body"] = clean_body_text(desc)
            it["lead"] = make_lead(desc, it["body"])
            time.sleep(0.2)
        except Exception:
            it["body"] = clean_body_text(desc)
            it["lead"] = make_lead(desc, it["body"])


def escape_xml(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def body_to_html(text: str) -> str:
    """Split cleaned text into <p> paragraphs for readability on e-ink."""
    if not text:
        return ""
    paras = re.split(r"\n\s*\n", text.strip())
    out = []
    for p in paras:
        p = p.strip()
        if not p:
            continue
        # single newlines inside para → space
        p = re.sub(r"\s*\n\s*", " ", p)
        out.append(f"<p>{escape_xml(p)}</p>")
    return "\n".join(out) if out else f"<p>{escape_xml(text)}</p>"


def format_ru_date(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    months = [
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    local = dt.astimezone(timezone(timedelta(hours=3)))
    return f"{local.day} {months[local.month]} · {local.strftime('%H:%M')}"


def format_cover_date(dt: datetime) -> str:
    weekdays = [
        "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье",
    ]
    months = [
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    local = dt.astimezone(timezone(timedelta(hours=3)))
    return f"{weekdays[local.weekday()]}, {local.day} {months[local.month]} {local.year}"


def build_epub(
    by_topic: dict[str, list[dict]],
    main_ids: set[str],
    path: Path,
    book_title: str,
    cover_stats: dict,
) -> None:
    book_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    now_s = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    msk = now.astimezone(timezone(timedelta(hours=3)))

    # Assign stable anchors
    article_anchor: dict[str, str] = {}
    aid = 0
    for tid, items in by_topic.items():
        if tid == "main":
            continue
        for it in items:
            key = it["link"].split("?")[0].rstrip("/")
            if key not in article_anchor:
                aid += 1
                article_anchor[key] = f"a{aid}"

    body_parts: list[str] = []
    # --- Cover ---
    body_parts.append('<div id="cover">')
    body_parts.append("<h1>Утренний выпуск</h1>")
    body_parts.append(f'<p class="cover-date">{escape_xml(format_cover_date(msk))}</p>')
    total = cover_stats.get("total", 0)
    body_parts.append(f'<p class="cover-meta">Сегодня: {total} материалов</p>')
    body_parts.append('<p class="cover-stats">')
    for tid, label in TOPIC_ORDER:
        n = cover_stats.get(tid, 0)
        if n:
            body_parts.append(f"{escape_xml(label)} — {n}<br/>")
    body_parts.append("</p>")
    body_parts.append(
        f'<p class="cover-meta">Выпуск собран в {msk.strftime("%H:%M")}</p>'
    )
    body_parts.append("</div><hr/>")

    ncx_nav: list[str] = []
    play = 1

    # Cover nav
    ncx_nav.append(
        f'    <navPoint id="np0" playOrder="0">\n'
        f'      <navLabel><text>Утренний выпуск</text></navLabel>\n'
        f'      <content src="content.xhtml#cover"/>\n'
        f"    </navPoint>"
    )

    for tid, label in TOPIC_ORDER:
        items = by_topic.get(tid) or []
        if not items:
            continue
        chap_id = f"ch-{tid}"
        body_parts.append(f'<h1 id="{chap_id}">{escape_xml(label)}</h1>')

        child_nav = []
        for it in items:
            key = it["link"].split("?")[0].rstrip("/")
            # Main section: link to real article, no full duplicate
            if tid == "main":
                anchor = article_anchor.get(key, "cover")
                t = escape_xml(it["title"])
                src = escape_xml(it["source"])
                ds = format_ru_date(it.get("pub"))
                lead = escape_xml(it.get("lead") or "")
                body_parts.append(
                    f'<article class="main-item">'
                    f"<h2>{t}</h2>"
                    f'<p class="meta">{src} · {ds}</p>'
                    f'<p class="lead">{lead}</p>'
                    f'<p class="link"><a href="content.xhtml#{anchor}">Читать полностью →</a></p>'
                    f"</article><hr/>"
                )
                child_nav.append(
                    f'      <navPoint id="np{play}-m{len(child_nav)}" playOrder="{play}">\n'
                    f'        <navLabel><text>{escape_xml(it["title"][:70])}</text></navLabel>\n'
                    f'        <content src="content.xhtml#{anchor}"/>\n'
                    f"      </navPoint>"
                )
                continue

            anchor = article_anchor[key]
            t = escape_xml(it["title"])
            src = escape_xml(it["source"])
            ds = format_ru_date(it.get("pub"))
            lead_raw = it.get("lead") or ""
            body_raw = it.get("body") or it.get("description") or ""
            # avoid lead repeating at start of body
            if lead_raw and body_raw.startswith(lead_raw[:80]):
                body_raw = body_raw[len(lead_raw):].lstrip(" .")
            lead = escape_xml(lead_raw)
            body_html = body_to_html(body_raw)
            link = escape_xml(it["link"])
            body_parts.append(
                f'<article id="{anchor}">'
                f"<h2>{t}</h2>"
                f'<p class="meta">{src} · {ds}</p>'
                f'<p class="lead">{lead}</p>'
                f"{body_html}"
                f'<p class="link"><a href="{link}">Источник</a></p>'
                f"</article><hr/>"
            )
            child_nav.append(
                f'      <navPoint id="np{play}-{anchor}" playOrder="{play}">\n'
                f'        <navLabel><text>{escape_xml(it["title"][:70])}</text></navLabel>\n'
                f'        <content src="content.xhtml#{anchor}"/>\n'
                f"      </navPoint>"
            )

        ncx_nav.append(
            f'    <navPoint id="np{play}" playOrder="{play}">\n'
            f'      <navLabel><text>{escape_xml(label)} ({len(items)})</text></navLabel>\n'
            f'      <content src="content.xhtml#{chap_id}"/>\n'
            + "\n".join(child_nav)
            + f"\n    </navPoint>"
        )
        play += 1

    content_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru">
<head>
  <meta charset="utf-8"/>
  <title>{escape_xml(book_title)}</title>
  <style>
    body {{ font-family: serif; font-size: 1em; line-height: 1.4; margin: 0.7em; }}
    h1 {{ font-size: 1.3em; margin: 1em 0 0.4em; page-break-before: always; }}
    h1:first-of-type {{ page-break-before: avoid; }}
    #cover h1 {{ page-break-before: avoid; text-align: center; margin-top: 1.5em; }}
    .cover-date {{ text-align: center; font-size: 1.05em; margin: 0.4em 0; }}
    .cover-meta {{ text-align: center; font-size: 0.9em; color: #333; }}
    .cover-stats {{ text-align: center; font-size: 0.95em; margin: 1em 0; line-height: 1.6; }}
    h2 {{ font-size: 1.1em; margin: 0.8em 0 0.2em; }}
    .meta {{ font-size: 0.85em; color: #444; margin: 0.1em 0 0.4em; }}
    .lead {{ font-style: italic; margin: 0.3em 0 0.6em; }}
    .link {{ font-size: 0.8em; margin-top: 0.5em; }}
    hr {{ border: none; border-top: 1px solid #ccc; margin: 0.9em 0; }}
    p {{ margin: 0.4em 0; }}
  </style>
</head>
<body>
{chr(10).join(body_parts)}
</body>
</html>
"""

    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="BookId">urn:uuid:{book_id}</dc:identifier>
    <dc:title>{escape_xml(book_title)}</dc:title>
    <dc:language>ru</dc:language>
    <dc:creator>Xteink Daily News</dc:creator>
    <dc:date>{now_s}</dc:date>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="content" href="content.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="content"/>
  </spine>
</package>
"""

    ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:{book_id}"/>
    <meta name="dtb:depth" content="2"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{escape_xml(book_title)}</text></docTitle>
  <navMap>
{chr(10).join(ncx_nav)}
  </navMap>
</ncx>
"""

    container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.xhtml", content_xhtml, compress_type=zipfile.ZIP_DEFLATED)


def write_opds(path: Path, epub_name: str, title: str, count: int) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opds="http://opds-spec.org/2010/catalog">
  <id>urn:xteink:daily-news</id>
  <title>Xteink Tech News</title>
  <updated>{now}</updated>
  <author><name>Xteink Daily News</name></author>
  <link rel="self" href="{BASE_RAW}/opds.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
  <link rel="start" href="{BASE_RAW}/opds.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
  <entry>
    <id>urn:xteink:latest</id>
    <title>{escape_xml(title)}</title>
    <updated>{now}</updated>
    <content type="text">{count} материалов. Разделы: Главное, ИИ, Гаджеты, ИТ, Разработка, Наука.</content>
    <link rel="http://opds-spec.org/acquisition"
          href="{BASE_RAW}/{epub_name}"
          type="application/epub+zip"/>
  </entry>
</feed>
"""
    path.write_text(xml, encoding="utf-8")


def main() -> None:
    print("Collecting RSS...")
    raw: list[dict] = []
    for name, url, topic, limit in RSS_FEEDS:
        raw.extend(fetch_feed(name, url, topic, limit))

    # age filter
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    raw = [it for it in raw if it["pub"] is None or it["pub"] >= cutoff]

    items = dedup(raw)
    print(f"After dedup: {len(items)}")

    # Per-source hard caps (Habr must not dominate)
    by_src: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_src[it["source"]].append(it)
    capped: list[dict] = []
    for src, lst in by_src.items():
        lst.sort(
            key=lambda x: x["pub"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True
        )
        limit = SOURCE_CAPS.get(src, 5)
        capped.extend(lst[:limit])
    items = capped
    print(f"After source caps: {len(items)}")

    print("Fetching full text...")
    enrich_full_text(items)

    # group by topic
    by_topic: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_topic[it.get("topic", "other")].append(it)

    # sort each topic by time
    for tid in by_topic:
        by_topic[tid].sort(
            key=lambda x: x["pub"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True
        )
        cap = TOPIC_CAPS.get(tid, 10)
        by_topic[tid] = by_topic[tid][:cap]

    # select main
    pool = [it for tid, lst in by_topic.items() if tid != "main" for it in lst]
    pool.sort(key=score_main, reverse=True)
    main_items = pool[: TOPIC_CAPS["main"]]
    main_ids = {it["link"].split("?")[0].rstrip("/") for it in main_items}
    by_topic["main"] = main_items

    # enforce total
    total = sum(len(v) for k, v in by_topic.items() if k != "main")
    if total > MAX_TOTAL:
        # trim other first
        overflow = total - MAX_TOTAL
        for tid in ("other", "gadgets", "dev", "admin", "ai", "science"):
            if overflow <= 0:
                break
            lst = by_topic.get(tid) or []
            cut = min(overflow, max(0, len(lst) - 3))
            if cut:
                by_topic[tid] = lst[:-cut]
                overflow -= cut

    cover_stats = {tid: len(by_topic.get(tid) or []) for tid, _ in TOPIC_ORDER}
    real_total = sum(cover_stats[t] for t, _ in TOPIC_ORDER if t != "main")
    cover_stats["total"] = real_total
    print("Topics:", {k: cover_stats[k] for k, _ in TOPIC_ORDER})

    msk = datetime.now(timezone(timedelta(hours=3)))
    date_str = msk.strftime("%Y-%m-%d")
    book_title = f"Техновости · {msk.strftime('%d.%m.%Y')}"
    dated_name = f"{date_str}.epub"

    print(f"Building {dated_name}...")
    build_epub(by_topic, main_ids, OUTPUT_DIR / dated_name, book_title, cover_stats)
    shutil.copy(OUTPUT_DIR / dated_name, OUTPUT_DIR / "latest.epub")
    write_opds(OUTPUT_DIR / "opds.xml", dated_name, book_title, real_total)
    size = (OUTPUT_DIR / dated_name).stat().st_size
    print(f"Done: {dated_name} ({size} bytes), articles={real_total}")


if __name__ == "__main__":
    main()
