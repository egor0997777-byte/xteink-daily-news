#!/usr/bin/env python3
"""Safe runner for Xteink Daily News.

Adds robust full-text extraction without rewriting the large generator:
- parses nested article/content containers structurally (not regex closing tags);
- skips junk blocks with balanced nesting;
- attempts to fetch the article page for every item;
- uses RSS text only as a fallback when the source page cannot be extracted;
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


JUNK_CLASS_HINTS = (
    "tm-meta", "tm-article-meta", "tm-votes", "tm-user", "user-info",
    "tm-separated-list", "tm-tags", "tm-hubs", "tm-publication-stats",
    "tm-article-snippet", "tm-data-icons", "tm-icon", "tm-button",
    "share", "social", "comment", "breadcrumb", "sidebar", "related",
    "advert", "banner", "cookie", "meta-bar", "post-meta", "byline",
    "author-info", "reading-time", "views-count",
)
TARGET_CLASS_HINTS = (
    "article-formatted-body", "tm-article-body", "article-body", "post-content",
    "entry-content", "content-body", "article__text", "article-content",
    "post__text", "post-text", "news-detail", "news__text",
)
BLOCK_TAGS = {"p", "br", "h1", "h2", "h3", "h4", "li", "blockquote", "div", "section"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class MainContentExtractor(HTMLParser):
    """Capture a complete article/content container with balanced nesting."""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.stack: list[tuple[str, bool]] = []
        self.capture_depth = 0
        self.skip_count = 0
        self.found_target = False

    @staticmethod
    def _attrs(attrs):
        return {str(k).lower(): (v or "") for k, v in attrs}

    def _is_target(self, tag: str, attrs) -> bool:
        a = self._attrs(attrs)
        classes = a.get("class", "").lower()
        itemprop = a.get("itemprop", "").lower()
        role = a.get("role", "").lower()
        return (
            tag == "article"
            or itemprop == "articlebody"
            or role == "main"
            or any(x in classes for x in TARGET_CLASS_HINTS)
        )

    def _is_junk(self, tag: str, attrs) -> bool:
        if tag in g.ArticleExtractor.SKIP:
            return True
        classes = self._attrs(attrs).get("class", "").lower()
        return any(x in classes for x in JUNK_CLASS_HINTS)

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        starts_capture = False
        if not self.found_target and self.capture_depth == 0 and self._is_target(t, attrs):
            self.found_target = True
            self.capture_depth = 1
            starts_capture = True
        elif self.capture_depth:
            self.capture_depth += 1

        starts_skip = bool(self.capture_depth and self._is_junk(t, attrs))
        if starts_skip:
            self.skip_count += 1
        self.stack.append((t, starts_skip))

        if self.capture_depth and not self.skip_count and not starts_capture and t in BLOCK_TAGS:
            self.parts.append("\n")

        if t in VOID_TAGS:
            _, skipped = self.stack.pop()
            if skipped and self.skip_count:
                self.skip_count -= 1
            if self.capture_depth and not starts_capture:
                self.capture_depth -= 1

    def handle_startendtag(self, tag, attrs):
        t = tag.lower()
        if self.capture_depth and not self.skip_count and t == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        t = tag.lower()
        if not self.stack:
            return

        popped: list[tuple[str, bool]] = []
        while self.stack:
            item = self.stack.pop()
            popped.append(item)
            if item[0] == t:
                break

        for _, started_skip in popped:
            if started_skip and self.skip_count:
                self.skip_count -= 1
            if self.capture_depth:
                self.capture_depth -= 1

        if self.found_target and not self.skip_count and t in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.capture_depth or self.skip_count:
            return
        s = data.strip()
        if s:
            self.parts.append(s + " ")

    def text(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+", " ", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()


class WholePageExtractor(HTMLParser):
    """Fallback parser for pages without a recognizable article container."""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.stack: list[tuple[str, bool]] = []
        self.skip_count = 0

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        classes = " ".join(v or "" for k, v in attrs if k == "class").lower()
        starts_skip = t in g.ArticleExtractor.SKIP or any(x in classes for x in JUNK_CLASS_HINTS)
        if starts_skip:
            self.skip_count += 1
        self.stack.append((t, starts_skip))
        if not self.skip_count and t in BLOCK_TAGS:
            self.parts.append("\n")
        if t in VOID_TAGS:
            _, skipped = self.stack.pop()
            if skipped and self.skip_count:
                self.skip_count -= 1

    def handle_startendtag(self, tag, attrs):
        if not self.skip_count and tag.lower() == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        t = tag.lower()
        if not self.stack:
            return
        popped: list[tuple[str, bool]] = []
        while self.stack:
            item = self.stack.pop()
            popped.append(item)
            if item[0] == t:
                break
        for _, started_skip in popped:
            if started_skip and self.skip_count:
                self.skip_count -= 1
        if not self.skip_count and t in BLOCK_TAGS:
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


def extract_article_text_safe(page_html: str, url: str = "") -> str:
    parser = MainContentExtractor()
    try:
        parser.feed(page_html)
        text = g.clean_body_text(parser.text())
    except Exception:
        text = ""

    if len(text) < 300:
        fallback = WholePageExtractor()
        try:
            fallback.feed(page_html)
            candidate = g.clean_body_text(fallback.text())
            if len(candidate) > len(text):
                text = candidate
        except Exception:
            pass

    return text[:25000] if len(text) >= 200 else ""


def enrich_full_text_all(items: list[dict]) -> None:
    """Try to fetch full HTML for every article; RSS is fallback only."""
    page_full = 0
    rss_fallback = 0
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

            extracted = extract_article_text_safe(page, it["link"])
            if len(extracted) >= 300:
                body = extracted
                page_full += 1
            else:
                body = fallback_text
                rss_fallback += 1
                failed_urls.append(it["link"])
        except Exception as exc:
            body = fallback_text
            rss_fallback += 1
            failed_urls.append(it["link"])
            print(f"[WARN] full text {idx}/{len(items)}: {it['source']}: {exc}")

        it["body"] = body
        it["lead"] = g.make_lead(desc, body)
        time.sleep(0.15)

    print(f"Full-text result: page={page_full}, RSS fallback={rss_fallback}, total={len(items)}")
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
    g.extract_article_text = extract_article_text_safe
    g.enrich_full_text = enrich_full_text_all
    g.main()

    msk = datetime.now(timezone(timedelta(hours=3)))
    dated = Path(f"{msk.strftime('%Y-%m-%d')}.epub")
    validate_epub(dated)
    validate_epub(Path("latest.epub"))


if __name__ == "__main__":
    main()
