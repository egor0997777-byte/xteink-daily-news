#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from xml.sax.saxutils import escape

REPO = "egor0997777-byte/xteink-daily-news"
BRANCH = "main"
BASE_RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
INPUT = Path("chatgpt/input.json")
SEEN = Path("chatgpt/seen.json")
MAGAZINE = "МУЖСКОЙ"


def esc(value: object) -> str:
    return escape(str(value or ""), {'"': '&quot;', "'": '&apos;'})


def display_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return value


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in str(text).replace("\r\n", "\n").split("\n\n") if p.strip()]


def normalize_url(value: str) -> str:
    parts = urlsplit(str(value).strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+$", "", parts.path) or "/"
    return urlunsplit(("https", host, path, "", ""))


def title_key(value: str) -> str:
    return re.sub(r"[^0-9a-zа-яё]+", " ", str(value).lower()).strip()


def load_seen() -> list[dict]:
    if not SEEN.exists():
        return []
    data = json.loads(SEEN.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("chatgpt/seen.json must contain a JSON list")
    return data


def load_input() -> dict:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    articles = data.get("articles")
    if not isinstance(articles, list) or not articles:
        raise ValueError("articles must be a non-empty list")
    if not 10 <= len(articles) <= 15:
        raise ValueError("articles must contain 10 to 15 items")

    required = ("category", "source", "title", "url", "summary")
    urls = set()
    titles = set()
    for i, article in enumerate(articles, 1):
        missing = [k for k in required if not str(article.get(k, "")).strip()]
        if missing:
            raise ValueError(f"article {i} missing fields: {', '.join(missing)}")
        ukey = normalize_url(article["url"])
        tkey = title_key(article["title"])
        if ukey in urls:
            raise ValueError(f"duplicate URL in current issue: {ukey}")
        if tkey in titles:
            raise ValueError(f"duplicate title in current issue: {article['title']}")
        urls.add(ukey)
        titles.add(tkey)

    issue_date = str(data.get("date") or "")
    for old in load_seen():
        old_date = str(old.get("date") or "")
        if old_date == issue_date:
            continue
        old_url = normalize_url(old.get("url", "")) if old.get("url") else ""
        old_title = title_key(old.get("title", ""))
        for article in articles:
            if old_url and old_url == normalize_url(article["url"]):
                raise ValueError(f"article already used on {old_date}: {article['url']}")
            if old_title and old_title == title_key(article["title"]):
                raise ValueError(f"title already used on {old_date}: {article['title']}")
    return data


def make_epub(data: dict, path: Path) -> None:
    issue_date = str(data.get("date") or datetime.now(timezone(timedelta(hours=3))).date())
    date_label = display_date(issue_date)
    title = str(data.get("title") or f"{MAGAZINE} · {date_label}")
    articles = data["articles"]
    book_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    body = [
        '<section id="cover">',
        f'<h1>{MAGAZINE}</h1>',
        f'<p class="date">{esc(date_label)}</p>',
        f'<p class="meta">{len(articles)} материалов · здоровье, форма, технологии, стиль и жизнь</p>',
        '<p class="meta">Ежедневный журнал: подробные русские пересказы лучших материалов из международных изданий.</p>',
        '</section><hr/>',
    ]
    nav = []
    previous_category = None
    for idx, article in enumerate(articles, 1):
        category = str(article["category"]).strip()
        if category != previous_category:
            body.append(f'<h2 class="section">{esc(category)}</h2>')
            previous_category = category
        anchor = f"a{idx}"
        body.append(f'<article id="{anchor}"><h3>{idx}. {esc(article["title"])}</h3>')
        published = str(article.get("published") or "").strip()
        source_line = esc(article["source"])
        if published:
            source_line += f' · {esc(display_date(published))}'
        body.append(f'<p class="source"><strong>{source_line}</strong></p>')
        for p in paragraphs(article["summary"]):
            body.append(f'<p>{esc(p)}</p>')
        body.append(f'<p class="source"><a href="{esc(article["url"])}">Оригинал статьи</a></p></article><hr/>')
        nav.append(
            f'<navPoint id="np{idx}" playOrder="{idx}"><navLabel><text>{esc(category)} · {esc(article["title"][:78])}</text></navLabel><content src="content.xhtml#{anchor}"/></navPoint>'
        )

    xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru">
<head><meta charset="utf-8"/><title>{esc(title)}</title>
<style>
body {{ font-family: serif; font-size: 1em; line-height: 1.5; margin: .75em; }}
h1 {{ font-size: 1.55em; margin: 1em 0 .5em; letter-spacing: .04em; }}
h2.section {{ font-size: 1.22em; margin: 1.35em 0 .55em; border-bottom: 1px solid #777; padding-bottom: .2em; }}
h3 {{ font-size: 1.12em; margin: 1.05em 0 .42em; }}
p {{ margin: .65em 0; }}
#cover {{ text-align: center; margin-top: 2em; }}
.date {{ font-size: 1.15em; font-weight: bold; }}
.meta,.source {{ font-size: .84em; }}
hr {{ border: none; border-top: 1px solid #bbb; margin: 1em 0; }}
</style></head><body>{''.join(body)}</body></html>'''

    opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="BookId">urn:uuid:{book_id}</dc:identifier><dc:title>{esc(title)}</dc:title><dc:language>ru</dc:language><dc:creator>ChatGPT</dc:creator><dc:date>{now}</dc:date></metadata>
<manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/><item id="content" href="content.xhtml" media-type="application/xhtml+xml"/></manifest>
<spine toc="ncx"><itemref idref="content"/></spine></package>'''

    ncx = f'''<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head><meta name="dtb:uid" content="urn:uuid:{book_id}"/></head><docTitle><text>{esc(title)}</text></docTitle><navMap>{''.join(nav)}</navMap></ncx>'''

    container = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'''

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.xhtml", xhtml, compress_type=zipfile.ZIP_DEFLATED)


def write_opds(data: dict, epub_name: str) -> None:
    issue_date = str(data.get("date") or datetime.now(timezone(timedelta(hours=3))).date())
    title = str(data.get("title") or f"{MAGAZINE} · {display_date(issue_date)}")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">
<id>urn:xteink:chatgpt-practice</id><title>{MAGAZINE}</title><updated>{now}</updated><author><name>ChatGPT</name></author>
<link rel="self" href="{BASE_RAW}/opds-chatgpt.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
<link rel="start" href="{BASE_RAW}/opds-chatgpt.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
<entry><id>urn:xteink:chatgpt-practice:latest</id><title>{esc(title)}</title><updated>{now}</updated><content type="text">{len(data['articles'])} материалов о здоровье, форме, технологиях, стиле и жизни.</content><link rel="http://opds-spec.org/acquisition" href="{BASE_RAW}/{epub_name}" type="application/epub+zip"/></entry>
</feed>'''
    Path("opds-chatgpt.xml").write_text(xml, encoding="utf-8")


def update_seen(data: dict) -> None:
    issue_date = str(data["date"])
    seen = load_seen()
    index = {(normalize_url(x.get("url", "")), str(x.get("date", ""))): i for i, x in enumerate(seen) if x.get("url")}
    for article in data["articles"]:
        row = {
            "date": issue_date,
            "category": article["category"],
            "source": article["source"],
            "title": article["title"],
            "url": article["url"],
        }
        key = (normalize_url(article["url"]), issue_date)
        if key in index:
            seen[index[key]] = row
        else:
            index[key] = len(seen)
            seen.append(row)
    SEEN.write_text(json.dumps(seen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    data = load_input()
    issue_date = str(data.get("date") or datetime.now(timezone(timedelta(hours=3))).date())
    dated = f"chatgpt-{issue_date}.epub"
    make_epub(data, Path(dated))
    shutil.copyfile(dated, "chatgpt-latest.epub")
    write_opds(data, dated)
    update_seen(data)
    print(f"Built {dated}: {len(data['articles'])} articles")


if __name__ == "__main__":
    main()
