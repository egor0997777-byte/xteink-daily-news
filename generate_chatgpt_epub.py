#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

REPO = "egor0997777-byte/xteink-daily-news"
BRANCH = "main"
BASE_RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
INPUT = Path("chatgpt/input.json")


def esc(value: object) -> str:
    return escape(str(value or ""), {'"': '&quot;', "'": '&apos;'})


def display_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return value


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in str(text).replace("\r\n", "\n").split("\n\n") if p.strip()]


def load_input() -> dict:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    articles = data.get("articles")
    if not isinstance(articles, list) or not articles:
        raise ValueError("articles must be a non-empty list")
    if len(articles) > 15:
        raise ValueError("articles must contain at most 15 items")
    required = ("source", "title", "url", "summary")
    seen = set()
    for i, article in enumerate(articles, 1):
        missing = [k for k in required if not str(article.get(k, "")).strip()]
        if missing:
            raise ValueError(f"article {i} missing fields: {', '.join(missing)}")
        clean_url = str(article["url"]).split("?")[0].split("#")[0].rstrip("/")
        if clean_url in seen:
            raise ValueError(f"duplicate URL: {clean_url}")
        seen.add(clean_url)
    return data


def make_epub(data: dict, path: Path) -> None:
    issue_date = str(data.get("date") or datetime.now(timezone(timedelta(hours=3))).date())
    date_label = display_date(issue_date)
    title = str(data.get("title") or f"ChatGPT на практике · {date_label}")
    articles = data["articles"]
    book_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    body = [
        '<section id="cover">',
        '<h1>ChatGPT на практике</h1>',
        f'<p class="date">{esc(date_label)}</p>',
        f'<p class="meta">{len(articles)} материалов · практическое обучение работе с ChatGPT</p>',
        '<p class="meta">Не новости об ИИ, а рабочие приёмы, туториалы и разборы реальных сценариев.</p>',
        '</section><hr/>',
    ]
    nav = []
    for idx, article in enumerate(articles, 1):
        anchor = f"a{idx}"
        body.append(f'<article id="{anchor}"><h2>{idx}. {esc(article["title"])}</h2>')
        body.append(f'<p class="source"><strong>{esc(article["source"])}</strong></p>')
        for p in paragraphs(article["summary"]):
            body.append(f'<p>{esc(p)}</p>')
        body.append(f'<p class="source"><a href="{esc(article["url"])}">Источник</a></p></article><hr/>')
        nav.append(
            f'<navPoint id="np{idx}" playOrder="{idx}"><navLabel><text>{esc(article["title"][:90])}</text></navLabel><content src="content.xhtml#{anchor}"/></navPoint>'
        )

    xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru">
<head><meta charset="utf-8"/><title>{esc(title)}</title>
<style>
body {{ font-family: serif; font-size: 1em; line-height: 1.5; margin: .75em; }}
h1 {{ font-size: 1.35em; margin: 1em 0 .5em; }}
h2 {{ font-size: 1.14em; margin: 1.15em 0 .45em; }}
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
    title = str(data.get("title") or f"ChatGPT на практике · {display_date(issue_date)}")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">
<id>urn:xteink:chatgpt-practice</id><title>ChatGPT на практике</title><updated>{now}</updated><author><name>ChatGPT</name></author>
<link rel="self" href="{BASE_RAW}/opds-chatgpt.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
<link rel="start" href="{BASE_RAW}/opds-chatgpt.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
<entry><id>urn:xteink:chatgpt-practice:latest</id><title>{esc(title)}</title><updated>{now}</updated><content type="text">{len(data['articles'])} практических материалов о работе с ChatGPT.</content><link rel="http://opds-spec.org/acquisition" href="{BASE_RAW}/{epub_name}" type="application/epub+zip"/></entry>
</feed>'''
    Path("opds-chatgpt.xml").write_text(xml, encoding="utf-8")


def main() -> None:
    data = load_input()
    issue_date = str(data.get("date") or datetime.now(timezone(timedelta(hours=3))).date())
    dated = f"chatgpt-{issue_date}.epub"
    make_epub(data, Path(dated))
    shutil.copyfile(dated, "chatgpt-latest.epub")
    write_opds(data, dated)
    print(f"Built {dated}: {len(data['articles'])} articles")


if __name__ == "__main__":
    main()
