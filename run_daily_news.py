#!/usr/bin/env python3
"""Safe runner for Xteink Daily News.

Patches full-text extraction without rewriting the large generator:
- fixes nested skipped HTML blocks with a tag stack;
- attempts to fetch the article page for every item;
- uses RSS text only as a fallback;
- validates generated EPUB before success.
"""
from __future__ import annotations

import re
import time
import zipfile
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

import generate_news_epub as g


class SafeArticleExtractor(HTMLParser):
    SKIP = g.ArticleExtractor.SKIP
    JUNK_CLASS_HINTS = (
        "tm-meta", "tm-article-meta", "tm-votes", "tm-user", "user-info",
        "tm-separated-list", "tm-tags", "tm-hubs", "tm-publication-stats",
        "tm-article-snippet", "tm-data-icons", "tm-icon", "tm-button",
        "share", "social", "comment", "breadcrumb", "sidebar", "related",
        "advert", "banner", "cookie", "meta-bar", "post-meta", "byline",
        "author-info", "reading-time", "views-count",
    )

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.stack: list[tuple[str, bool]] = []
        self.skip_count = 0

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        classes = " ".join(v or "" for k, v in attrs if k == "class").lower()
        should_skip = t in self.SKIP or any(x in classes for x in self.JUNK_CLASS_HINTS)
        inherited_skip = self.skip_count > 0
        active_skip = inherited_skip or should_skip
        self.stack.append((t, should_skip))
        if should_skip:
            self.skip_count += 1
        if active_skip:
            return
        if t in ("p", "br", "h1", "h2", "h3", "h4", "li", "blockquote"):
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        t = tag.lower()
        if self.skip_count:
            return
        if t == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        t = tag.lower()
        if not self.stack:
            return

        # Pop until the matching tag. This is resilient to imperfect HTML.
        popped: list[tuple[str, bool]] = []
        while self.stack:
            item = self.stack.pop()
            popped.append(item)
            if item[0] == t:
                break
        for _, started_skip in popped:
            if started_skip and self.skip_count:
                self.skip_count -= 1

        if self.skip_count:
            return
        if t in ("p", "h1", "h2", "h3", "h4", "li", "blockquote", "div"):
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_count:
            return
        s = data.strip()
        if s:
            self.parts.append(s + " ")

    def text(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+", " ", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()


def enrich_full_text_all(items: list[dict]) -> None:
    """Try to fetch full HTML for every article; RSS is fallback only."""
    full = 0
    fallback = 0
    failed_urls: list[str] = []

    for idx, it in enumerate(items, start=1):
        desc = it.get("description") or ""
        fallback_text = g.clean_body_text(desc)
        body = ""

        try:
            raw = g.fetch_url(it["link"], timeout=18)
            try:
                page = raw.decode("utf-8")
            except UnicodeDecodeError:
                page = raw.decode("cp1251", errors="ignore")

            extracted = g.extract_article_text(page, it["link"])
            # Prefer page text whenever it is substantial. Do not require it
            # to exceed the RSS description by a fixed margin.
            if len(extracted) >= 300:
                body = extracted
                full += 1
            else:
                body = fallback_text
                fallback += 1
                failed_urls.append(it["link"])
        except Exception as exc:
            body = fallback_text
            fallback += 1
            failed_urls.append(it["link"])
            print(f"[WARN] full text {idx}/{len(items)}: {it['source']}: {exc}")

        it["body"] = body
        it["lead"] = g.make_lead(desc, body)
        time.sleep(0.15)

    print(f"Full-text result: page={full}, RSS fallback={fallback}, total={len(items)}")
    if failed_urls:
        print("[WARN] RSS fallback URLs:")
        for url in failed_urls:
            print(f"  {url}")


def validate_epub(path: Path) -> None:
    if not path.exists() or path.stat().st_size < 5000:
        raise RuntimeError(f"EPUB missing or too small: {path}")

    required = {
        "mimetype",
        "META-INF/container.xml",
        "OEBPS/content.opf",
        "OEBPS/toc.ncx",
        "OEBPS/content.xhtml",
    }
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"Corrupt EPUB member: {bad}")
        names = set(zf.namelist())
        missing = required - names
        if missing:
            raise RuntimeError(f"EPUB missing files: {sorted(missing)}")

        ET.fromstring(zf.read("META-INF/container.xml"))
        ET.fromstring(zf.read("OEBPS/content.opf"))
        ET.fromstring(zf.read("OEBPS/toc.ncx"))
        content = zf.read("OEBPS/content.xhtml").decode("utf-8")

    article_count = content.count("<article")
    full_article_count = content.count('<article id="')
    if article_count < 10 or full_article_count < 5:
        raise RuntimeError(
            f"Suspicious EPUB: article_count={article_count}, full_articles={full_article_count}"
        )
    print(
        f"Validation OK: {path.name}, size={path.stat().st_size}, "
        f"articles={article_count}, full_articles={full_article_count}"
    )


def main() -> None:
    g.ArticleExtractor = SafeArticleExtractor
    g.enrich_full_text = enrich_full_text_all
    g.main()

    msk = datetime.now(timezone(timedelta(hours=3)))
    dated = Path(f"{msk.strftime('%Y-%m-%d')}.epub")
    validate_epub(dated)
    validate_epub(Path("latest.epub"))


if __name__ == "__main__":
    main()
