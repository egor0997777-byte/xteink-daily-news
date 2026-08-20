#!/usr/bin/env python3
"""Minimal RSS → EPUB + hierarchical OPDS for Xteink X3 / CrossPoint.
Only standard library. Text-only EPUBs, no images.
"""

from __future__ import annotations

import html
import re
import uuid
import zipfile
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

# --- Config ---
# (display name, slug for files, rss url)
RSS_FEEDS = [
    ("Хабр (новости)", "habr-news", "https://habr.com/ru/rss/news/"),
    ("Хабр (статьи)", "habr-articles", "https://habr.com/ru/rss/articles/"),
    ("Хабр (разработка)", "habr-dev", "https://habr.com/ru/rss/flows/develop/"),
    ("Лайфхакер", "lifehacker", "https://lifehacker.ru/feed/"),
    ("VC.ru", "vc", "https://vc.ru/rss"),
    ("iXBT", "ixbt", "https://www.ixbt.com/export/rss.xml"),
    ("3DNews", "3dnews", "https://3dnews.ru/news/rss/"),
    ("Tproger", "tproger", "https://tproger.ru/feed/"),
    ("DTF", "dtf", "https://dtf.ru/rss/all"),
]

MAX_ITEMS_TOTAL = 80
MAX_ITEMS_PER_SOURCE = 40
MAX_AGE_HOURS = 36
USER_AGENT = "XteinkNewsBot/1.0 (+https://github.com/egor0997777-byte/xteink-daily-news)"
REPO_OWNER = "egor0997777-byte"
REPO_NAME = "xteink-daily-news"
BRANCH = "main"
OUTPUT_DIR = Path(".")
BASE_RAW = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}"


def fetch_url(url: str, timeout: int = 25) -> bytes:
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
    t = re.sub(r"\s+", " ", t)
    return t


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
        print(f"[WARN] Failed {name}: {e}")
        return items

    channel = root.find("channel")
    if channel is not None:
        entries = channel.findall("item")
    else:
        entries = root.findall("{http://www.w3.org/2005/Atom}entry") or root.findall("entry")

    for entry in entries:
        title = get_text(entry, "title")
        link = get_link(entry)
        description = get_text(
            entry, "description", "summary", "{http://purl.org/rss/1.0/modules/content/}encoded"
        )
        pub = parse_pubdate(entry)
        if not title or not link:
            continue
        items.append(
            {
                "title": title,
                "link": link,
                "description": strip_html(description),
                "pub": pub,
                "source": name,
            }
        )
    print(f"[OK] {name}: {len(items)} items")
    return items


def dedup_and_filter(items: list[dict], limit: int) -> list[dict]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[dict] = []
    for it in items:
        url = it["link"].split("?")[0].rstrip("/")
        nt = normalize_title(it["title"])
        if url in seen_urls or nt in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(nt)
        unique.append(it)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    fresh = []
    for it in unique:
        if it["pub"] is None or it["pub"] >= cutoff:
            fresh.append(it)

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


def make_xhtml(items: list[dict], title: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body_parts = [
        f"<h1>{escape_xml(title)}</h1>",
        f'<p class="meta">Обновлено: {now} · {len(items)} материалов</p>',
        "<hr/>",
    ]
    for i, it in enumerate(items, 1):
        pub_str = ""
        if it["pub"]:
            try:
                pub_str = it["pub"].astimezone(timezone(timedelta(hours=3))).strftime(
                    "%d.%m %H:%M"
                )
            except Exception:
                pub_str = str(it["pub"])[:16]
        src = escape_xml(it["source"])
        t = escape_xml(it["title"])
        desc = escape_xml(it["description"][:1200]) if it["description"] else ""
        link = escape_xml(it["link"])
        body_parts.append(
            f'<article id="n{i}">'
            f"<h2>{t}</h2>"
            f'<p class="meta">{src} · {pub_str}</p>'
            f"<p>{desc}</p>"
            f'<p class="link"><a href="{link}">Источник</a></p>'
            f"</article><hr/>"
        )
    body = "\n".join(body_parts)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru">
<head>
  <meta charset="utf-8"/>
  <title>{escape_xml(title)}</title>
  <style>
    body {{ font-family: serif; font-size: 1em; line-height: 1.35; margin: 0.8em; }}
    h1 {{ font-size: 1.4em; margin-bottom: 0.3em; }}
    h2 {{ font-size: 1.15em; margin: 0.8em 0 0.2em; }}
    .meta {{ font-size: 0.85em; color: #444; margin: 0.2em 0; }}
    .link {{ font-size: 0.8em; }}
    hr {{ border: none; border-top: 1px solid #ccc; margin: 1em 0; }}
    article {{ margin-bottom: 0.5em; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def build_epub(items: list[dict], path: Path, book_title: str) -> None:
    book_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    content_xhtml = make_xhtml(items, book_title)

    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
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

    ncx_nav = []
    for i, it in enumerate(items, 1):
        ncx_nav.append(
            f'    <navPoint id="np{i}" playOrder="{i}">\n'
            f'      <navLabel><text>{escape_xml(it["title"][:80])}</text></navLabel>\n'
            f'      <content src="content.xhtml#n{i}"/>\n'
            f"    </navPoint>"
        )
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


def write_opds_catalog(
    path: Path,
    feed_id: str,
    feed_title: str,
    entries_xml: str,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    self_url = f"{BASE_RAW}/{path.name}"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opds="http://opds-spec.org/2010/catalog">
  <id>{feed_id}</id>
  <title>{escape_xml(feed_title)}</title>
  <updated>{now}</updated>
  <author><name>Xteink Daily News</name></author>
  <link rel="self" href="{self_url}" type="application/atom+xml;profile=opds-catalog;kind=navigation"/>
  <link rel="start" href="{BASE_RAW}/opds.xml" type="application/atom+xml;profile=opds-catalog;kind=navigation"/>
{entries_xml}
</feed>
"""
    path.write_text(xml, encoding="utf-8")


def main() -> None:
    print("Collecting news...")
    by_source: dict[str, list[dict]] = {}
    slug_of: dict[str, str] = {}
    all_raw: list[dict] = []

    for name, slug, url in RSS_FEEDS:
        items = fetch_feed(name, url)
        filtered = dedup_and_filter(items, MAX_ITEMS_PER_SOURCE)
        if filtered:
            by_source[name] = filtered
            slug_of[name] = slug
            all_raw.extend(filtered)

    all_items = dedup_and_filter(all_raw, MAX_ITEMS_TOTAL)
    print(f"Total after dedup/filter: {len(all_items)}")

    date_str = datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y")
    print("Building latest.epub...")
    build_epub(all_items, OUTPUT_DIR / "latest.epub", f"Техновости · {date_str}")

    source_files: list[tuple[str, str, int]] = []
    for name, items in by_source.items():
        slug = slug_of[name]
        epub_name = f"{slug}.epub"
        print(f"Building {epub_name}...")
        build_epub(items, OUTPUT_DIR / epub_name, f"{name} · {date_str}")
        source_files.append((name, slug, len(items)))

    root_entries = []
    root_entries.append(
        f"""  <entry>
    <id>urn:xteink:all</id>
    <title>Все новости</title>
    <updated>{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}</updated>
    <content type="text">{len(all_items)} материалов из всех источников</content>
    <link rel="http://opds-spec.org/acquisition"
          href="{BASE_RAW}/latest.epub"
          type="application/epub+zip"/>
  </entry>"""
    )
    for name, slug, count in source_files:
        root_entries.append(
            f"""  <entry>
    <id>urn:xteink:cat:{slug}</id>
    <title>{escape_xml(name)}</title>
    <updated>{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}</updated>
    <content type="text">{count} материалов</content>
    <link rel="subsection"
          href="{BASE_RAW}/opds-{slug}.xml"
          type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
  </entry>"""
        )
    write_opds_catalog(
        OUTPUT_DIR / "opds.xml",
        "urn:xteink:daily-news",
        "Xteink Tech News",
        "\n".join(root_entries),
    )

    for name, slug, count in source_files:
        entries = f"""  <entry>
    <id>urn:xteink:book:{slug}</id>
    <title>{escape_xml(name)} · {date_str}</title>
    <updated>{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}</updated>
    <content type="text">{count} материалов. Только текст.</content>
    <link rel="http://opds-spec.org/acquisition"
          href="{BASE_RAW}/{slug}.epub"
          type="application/epub+zip"/>
  </entry>"""
        write_opds_catalog(
            OUTPUT_DIR / f"opds-{slug}.xml",
            f"urn:xteink:cat:{slug}",
            name,
            entries,
        )

    print("Done.")
    print(f"  latest.epub + {len(source_files)} source EPUBs")
    print(f"  opds.xml + {len(source_files)} subcatalogs")


if __name__ == "__main__":
    main()
