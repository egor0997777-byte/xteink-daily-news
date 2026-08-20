#!/usr/bin/env python3
"""RSS → one dated EPUB + simple OPDS for Xteink X3 / CrossPoint.
Chapters inside EPUB = sources. Text only, no images. Stdlib only.
"""

from __future__ import annotations

import html
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

RSS_FEEDS = [
    ("Хабр — новости", "https://habr.com/ru/rss/news/"),
    ("Хабр — статьи", "https://habr.com/ru/rss/articles/"),
    ("Хабр — разработка", "https://habr.com/ru/rss/flows/develop/"),
    ("Хабр — администрирование", "https://habr.com/ru/rss/flows/admin/"),
    ("Хабр — дизайн", "https://habr.com/ru/rss/flows/design/"),
    ("Хабр — ИИ", "https://habr.com/ru/rss/hubs/artificial_intelligence/all/"),
    ("Хабр — гаджеты", "https://habr.com/ru/rss/hubs/gadgets/all/"),
    ("Лайфхакер", "https://lifehacker.ru/feed/"),
    ("VC.ru", "https://vc.ru/rss"),
    ("iXBT", "https://www.ixbt.com/export/rss.xml"),
    ("iXBT — новости", "https://www.ixbt.com/export/news.rss"),
    ("3DNews", "https://3dnews.ru/news/rss/"),
    ("Tproger", "https://tproger.ru/feed/"),
    ("DTF", "https://dtf.ru/rss/all"),
    ("Computerra", "https://www.computerra.ru/feed/"),
    ("N+1", "https://nplus1.ru/rss"),
    ("HighTech", "https://hightech.fm/feed"),
    ("Xakep", "https://xakep.ru/feed/"),
    ("CNews", "https://www.cnews.ru/inc/rss/news.xml"),
    ("Mobile-Review", "https://www.mobile-review.com/rss.xml"),
]

MAX_PER_SOURCE = 25
MAX_AGE_HOURS = 48
USER_AGENT = "XteinkNewsBot/1.0 (+https://github.com/egor0997777-byte/xteink-daily-news)"
REPO = "egor0997777-byte/xteink-daily-news"
BRANCH = "main"
BASE_RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
OUTPUT_DIR = Path(".")


def fetch_url(url: str, timeout: int = 20) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.I | re.S)
    text = re.sub(r"</?(p|div|br|h[1-6]|li|tr)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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


def fetch_feed(name: str, url: str) -> list[dict]:
    items = []
    try:
        data = fetch_url(url)
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
        items.append(
            {
                "title": title,
                "link": link,
                "description": strip_html(desc),
                "pub": pub,
                "source": name,
            }
        )
    print(f"[OK] {name}: {len(items)}")
    return items


def dedup_filter(items: list[dict], limit: int) -> list[dict]:
    seen_u, seen_t = set(), set()
    unique = []
    for it in items:
        u = it["link"].split("?")[0].rstrip("/")
        nt = normalize_title(it["title"])
        if u in seen_u or nt in seen_t:
            continue
        seen_u.add(u)
        seen_t.add(nt)
        unique.append(it)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    fresh = [it for it in unique if it["pub"] is None or it["pub"] >= cutoff]
    fresh.sort(
        key=lambda x: x["pub"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True
    )
    return fresh[:limit]


def escape_xml(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build_epub(by_source: dict[str, list[dict]], path: Path, book_title: str) -> None:
    book_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    body_parts = [f"<h1>{escape_xml(book_title)}</h1>"]
    total = sum(len(v) for v in by_source.values())
    body_parts.append(
        f'<p class="meta">Обновлено: {now} · {total} материалов · {len(by_source)} источников</p><hr/>'
    )

    ncx_nav = []
    play = 1
    art_id = 0

    for src_name, items in by_source.items():
        if not items:
            continue
        chap_id = f"ch-{play}"
        body_parts.append(f'<h1 id="{chap_id}">{escape_xml(src_name)}</h1>')
        ncx_nav.append(
            f'    <navPoint id="np{play}" playOrder="{play}">\n'
            f'      <navLabel><text>{escape_xml(src_name)} ({len(items)})</text></navLabel>\n'
            f'      <content src="content.xhtml#{chap_id}"/>\n'
            f"    </navPoint>"
        )
        play += 1

        for it in items:
            art_id += 1
            pub_str = ""
            if it["pub"]:
                try:
                    pub_str = it["pub"].astimezone(timezone(timedelta(hours=3))).strftime(
                        "%d.%m %H:%M"
                    )
                except Exception:
                    pub_str = str(it["pub"])[:16]
            t = escape_xml(it["title"])
            desc = escape_xml(it["description"][:1500]) if it["description"] else ""
            link = escape_xml(it["link"])
            body_parts.append(
                f'<article id="a{art_id}">'
                f"<h2>{t}</h2>"
                f'<p class="meta">{pub_str}</p>'
                f"<p>{desc}</p>"
                f'<p class="link"><a href="{link}">Источник</a></p>'
                f"</article><hr/>"
            )

    content_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru">
<head>
  <meta charset="utf-8"/>
  <title>{escape_xml(book_title)}</title>
  <style>
    body {{ font-family: serif; font-size: 1em; line-height: 1.35; margin: 0.8em; }}
    h1 {{ font-size: 1.35em; margin: 1em 0 0.4em; page-break-before: always; }}
    h1:first-of-type {{ page-break-before: avoid; }}
    h2 {{ font-size: 1.1em; margin: 0.7em 0 0.2em; }}
    .meta {{ font-size: 0.85em; color: #444; margin: 0.15em 0; }}
    .link {{ font-size: 0.8em; }}
    hr {{ border: none; border-top: 1px solid #ccc; margin: 0.8em 0; }}
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
    <dc:date>{now}</dc:date>
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
    <meta name="dtb:depth" content="1"/>
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
    epub_url = f"{BASE_RAW}/{epub_name}"
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
    <content type="text">{count} материалов. Главы = источники. Только текст.</content>
    <link rel="http://opds-spec.org/acquisition"
          href="{epub_url}"
          type="application/epub+zip"/>
  </entry>
</feed>
"""
    path.write_text(xml, encoding="utf-8")


def main() -> None:
    print("Collecting...")
    by_source: dict[str, list[dict]] = {}

    for name, url in RSS_FEEDS:
        items = fetch_feed(name, url)
        filtered = dedup_filter(items, MAX_PER_SOURCE)
        if filtered:
            by_source[name] = filtered
            print(f"  → keep {len(filtered)}")

    seen = set()
    for src in list(by_source.keys()):
        cleaned = []
        for it in by_source[src]:
            key = it["link"].split("?")[0].rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(it)
        if cleaned:
            by_source[src] = cleaned
        else:
            del by_source[src]

    total = sum(len(v) for v in by_source.values())
    print(f"Sources: {len(by_source)}, items: {total}")

    msk = datetime.now(timezone(timedelta(hours=3)))
    date_str = msk.strftime("%Y-%m-%d")
    book_title = f"Техновости · {msk.strftime('%d.%m.%Y')}"
    dated_name = f"{date_str}.epub"

    print(f"Building {dated_name}...")
    build_epub(by_source, OUTPUT_DIR / dated_name, book_title)
    shutil.copy(OUTPUT_DIR / dated_name, OUTPUT_DIR / "latest.epub")
    write_opds(OUTPUT_DIR / "opds.xml", dated_name, book_title, total)
    print(f"Done: {dated_name} + latest.epub + opds.xml")
    print(f"  size: {(OUTPUT_DIR / dated_name).stat().st_size} bytes")


if __name__ == "__main__":
    main()
