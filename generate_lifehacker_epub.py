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
INPUT = Path("lifehacker/input.json")
OUT_DIR = Path(".")


def esc(s: str) -> str:
    return escape(str(s or ""), {'"': '&quot;', "'": '&apos;'})


def display_date(issue_date: str) -> str:
    try:
        return datetime.strptime(issue_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return issue_date


def load_input() -> dict:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    articles = data.get("articles")
    if not isinstance(articles, list) or not articles:
        raise ValueError("articles must be a non-empty list")
    if len(articles) > 20:
        raise ValueError("articles must contain at most 20 items")
    required = ("title", "url", "summary", "why", "critique", "takeaway")
    seen_urls = set()
    for i, article in enumerate(articles, 1):
        if not isinstance(article, dict):
            raise ValueError(f"article {i} must be an object")
        missing = [k for k in required if not str(article.get(k, "")).strip()]
        if missing:
            raise ValueError(f"article {i} missing fields: {', '.join(missing)}")
        url = str(article["url"]).split("?")[0].rstrip("/")
        if url in seen_urls:
            raise ValueError(f"duplicate article URL in issue: {url}")
        seen_urls.add(url)
    return data


def make_epub(data: dict, path: Path) -> None:
    articles = data["articles"]
    issue_date = str(data.get("date") or datetime.now(timezone(timedelta(hours=3))).date())
    date_label = display_date(issue_date)
    title = str(data.get("title") or f"Лайфхакер · {date_label}")
    book_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    body = [
        '<section id="cover">',
        '<h1>Лайфхакер</h1>',
        f'<p class="date">{esc(date_label)}</p>',
        f'<p class="meta">{len(articles)} материалов · пересказ и критические замечания ChatGPT</p>',
        '</section>',
        '<hr/>',
        '<h1 id="contents">Сегодня</h1>',
    ]
    nav_points = []
    for idx, a in enumerate(articles, 1):
        anchor = f"a{idx}"
        body.append(f'<article id="{anchor}">')
        body.append(f'<h2>{idx}. {esc(a["title"])}</h2>')
        if a.get("idea"):
            body.append('<p class="idea"><strong>ИДЕЯ ДЛЯ РАЗМЫШЛЕНИЯ</strong></p>')
        body.append(f'<p><strong>Суть.</strong> {esc(a["summary"])}</p>')
        body.append(f'<p><strong>Зачем читать.</strong> {esc(a["why"])}</p>')
        body.append(f'<p><strong>Критическое замечание.</strong> {esc(a["critique"])}</p>')
        body.append(f'<p class="takeaway"><strong>Унести с собой:</strong> {esc(a["takeaway"])}</p>')
        body.append(f'<p class="source"><a href="{esc(a["url"])}">Оригинал на Lifehacker.ru</a></p>')
        body.append('</article><hr/>')
        nav_points.append(
            f'''    <navPoint id="np{idx}" playOrder="{idx}">\n'''
            f'''      <navLabel><text>{esc(str(a["title"])[:80])}</text></navLabel>\n'''
            f'''      <content src="content.xhtml#{anchor}"/>\n'''
            f'''    </navPoint>'''
        )

    xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru">
<head>
<meta charset="utf-8"/>
<title>{esc(title)}</title>
<style>
body {{ font-family: serif; font-size: 1em; line-height: 1.42; margin: 0.75em; }}
h1 {{ font-size: 1.35em; page-break-before: always; margin: 1em 0 0.5em; }}
h1:first-of-type {{ page-break-before: avoid; }}
h2 {{ font-size: 1.12em; margin: 1em 0 0.45em; }}
p {{ margin: 0.5em 0; }}
#cover {{ text-align: center; margin-top: 2em; }}
.date {{ font-size: 1.15em; font-weight: bold; }}
.meta, .source {{ font-size: 0.84em; }}
.idea {{ font-size: 0.88em; margin: 0.25em 0 0.55em; }}
.takeaway {{ border-left: 2px solid #777; padding-left: 0.6em; }}
hr {{ border: none; border-top: 1px solid #bbb; margin: 1em 0; }}
a {{ text-decoration: underline; }}
</style>
</head>
<body>
{''.join(body)}
</body>
</html>
'''

    opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="BookId">urn:uuid:{book_id}</dc:identifier>
<dc:title>{esc(title)}</dc:title>
<dc:language>ru</dc:language>
<dc:creator>ChatGPT + Lifehacker</dc:creator>
<dc:date>{now}</dc:date>
</metadata>
<manifest>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
<item id="content" href="content.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine toc="ncx"><itemref idref="content"/></spine>
</package>
'''

    ncx = f'''<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head><meta name="dtb:uid" content="urn:uuid:{book_id}"/></head>
<docTitle><text>{esc(title)}</text></docTitle>
<navMap>
{chr(10).join(nav_points)}
</navMap>
</ncx>
'''

    container = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
'''

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.xhtml", xhtml, compress_type=zipfile.ZIP_DEFLATED)


def write_opds(data: dict, epub_name: str) -> None:
    issue_date = str(data.get("date") or datetime.now(timezone(timedelta(hours=3))).date())
    title = str(data.get("title") or f"Лайфхакер · {display_date(issue_date)}")
    count = len(data["articles"])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">
<id>urn:xteink:lifehacker</id>
<title>Лайфхакер</title>
<updated>{now}</updated>
<author><name>ChatGPT</name></author>
<link rel="self" href="{BASE_RAW}/opds-lifehacker.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
<link rel="start" href="{BASE_RAW}/opds-lifehacker.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
<entry>
<id>urn:xteink:lifehacker:latest</id>
<title>{esc(title)}</title>
<updated>{now}</updated>
<content type="text">{count} материалов: пересказ, польза, критика и мысль дня.</content>
<link rel="http://opds-spec.org/acquisition" href="{BASE_RAW}/{epub_name}" type="application/epub+zip"/>
</entry>
</feed>
'''
    (OUT_DIR / "opds-lifehacker.xml").write_text(xml, encoding="utf-8")


def main() -> None:
    data = load_input()
    issue_date = str(data.get("date") or datetime.now(timezone(timedelta(hours=3))).date())
    dated_name = f"lifehacker-{issue_date}.epub"
    out = OUT_DIR / dated_name
    make_epub(data, out)
    shutil.copyfile(out, OUT_DIR / "lifehacker-latest.epub")
    write_opds(data, dated_name)
    print(f"Built {dated_name}: {out.stat().st_size} bytes, {len(data['articles'])} articles")


if __name__ == "__main__":
    main()
