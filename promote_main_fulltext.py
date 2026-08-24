#!/usr/bin/env python3
"""Post-process the generated tech-news EPUB for Xteink X3.

The base generator keeps «Главное» as short teasers linking to the same full
articles later in topic chapters. On the X3 that adds an unnecessary click and
uses a glyph that may not render. This script promotes those full article
blocks into «Главное», removes their later duplicates, and fixes NCX duplicate
navigation entries.
"""
from __future__ import annotations

import copy
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

XHTML_NS = "http://www.w3.org/1999/xhtml"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
ATOM_NS = "http://www.w3.org/2005/Atom"

ET.register_namespace("", XHTML_NS)


def q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def current_epub_from_opds() -> Path:
    root = ET.parse("opds.xml").getroot()
    for link in root.findall(f".//{q(ATOM_NS, 'link')}"):
        if link.get("type") == "application/epub+zip":
            href = link.get("href", "")
            name = href.rsplit("/", 1)[-1]
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.epub", name):
                path = Path(name)
                if path.exists():
                    return path
    raise RuntimeError("Could not locate current dated EPUB from opds.xml")


def article_anchor(main_article: ET.Element) -> str:
    for p in main_article.findall(q(XHTML_NS, "p")):
        if p.get("class") != "link":
            continue
        a = p.find(q(XHTML_NS, "a"))
        if a is None:
            continue
        href = a.get("href", "")
        m = re.fullmatch(r"content\.xhtml#(a\d+)", href)
        if m:
            return m.group(1)
    raise RuntimeError("Main teaser has no internal full-article link")


def patch_content(content_bytes: bytes) -> tuple[bytes, list[str]]:
    root = ET.fromstring(content_bytes)
    body = root.find(q(XHTML_NS, "body"))
    if body is None:
        raise RuntimeError("EPUB XHTML has no body")

    main_articles = [
        el for el in list(body)
        if el.tag == q(XHTML_NS, "article") and el.get("class") == "main-item"
    ]
    if not main_articles:
        raise RuntimeError("No main teaser articles found")

    anchors: list[str] = []
    for main in main_articles:
        anchor = article_anchor(main)
        targets = [
            el for el in list(body)
            if el.tag == q(XHTML_NS, "article") and el.get("id") == anchor
        ]
        if len(targets) != 1:
            raise RuntimeError(f"Expected one full article for {anchor}, found {len(targets)}")
        target = targets[0]
        full = copy.deepcopy(target)
        full.set("class", "main-item")

        children = list(body)
        main_index = children.index(main)
        body.remove(main)
        body.insert(main_index, full)

        children = list(body)
        target_index = children.index(target)
        body.remove(target)
        # The generator writes <hr/> immediately after every article.
        children = list(body)
        if target_index < len(children) and children[target_index].tag == q(XHTML_NS, "hr"):
            body.remove(children[target_index])

        anchors.append(anchor)

    # Validation: no generated «read fully» links remain and every promoted
    # article anchor occurs exactly once in the XHTML.
    for a in root.findall(f".//{q(XHTML_NS, 'a')}"):
        label = "".join(a.itertext()).strip().lower()
        if label.startswith("читать полностью"):
            raise RuntimeError("A «Читать полностью» link remained after patching")
    for anchor in anchors:
        count = len(root.findall(f".//{q(XHTML_NS, 'article')}[@id='{anchor}']"))
        if count != 1:
            raise RuntimeError(f"Promoted anchor {anchor} occurs {count} times")

    return ET.tostring(root, encoding="utf-8", xml_declaration=True), anchors


def patch_ncx(ncx_bytes: bytes, anchors: list[str]) -> bytes:
    ET.register_namespace("", NCX_NS)
    root = ET.fromstring(ncx_bytes)
    nav_map = root.find(q(NCX_NS, "navMap"))
    if nav_map is None:
        raise RuntimeError("NCX has no navMap")

    anchor_set = set(anchors)

    def content_anchor(nav: ET.Element) -> str | None:
        content = nav.find(q(NCX_NS, "content"))
        if content is None:
            return None
        src = content.get("src", "")
        m = re.fullmatch(r"content\.xhtml#(a\d+)", src)
        return m.group(1) if m else None

    # Remove topic-level duplicate entries. Main child navPoints have IDs such
    # as np1-m0; topic child entries have IDs such as np2-a7.
    for parent in root.findall(f".//{q(NCX_NS, 'navPoint')}"):
        for child in list(parent.findall(q(NCX_NS, "navPoint"))):
            anchor = content_anchor(child)
            nav_id = child.get("id", "")
            if anchor in anchor_set and "-m" not in nav_id:
                parent.remove(child)

    # Keep displayed chapter counts consistent with the remaining child navs.
    for top in nav_map.findall(q(NCX_NS, "navPoint")):
        children = top.findall(q(NCX_NS, "navPoint"))
        if not children:
            continue
        text_el = top.find(f"{q(NCX_NS, 'navLabel')}/{q(NCX_NS, 'text')}")
        if text_el is not None and text_el.text:
            text_el.text = re.sub(r"\s*\(\d+\)$", f" ({len(children)})", text_el.text)

    for anchor in anchors:
        refs = 0
        for nav in root.findall(f".//{q(NCX_NS, 'navPoint')}"):
            if content_anchor(nav) == anchor:
                refs += 1
        if refs != 1:
            raise RuntimeError(f"NCX anchor {anchor} has {refs} navigation entries")

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def patch_epub(path: Path) -> list[str]:
    with zipfile.ZipFile(path, "r") as src:
        infos = src.infolist()
        if not infos or infos[0].filename != "mimetype":
            raise RuntimeError("EPUB mimetype is not the first ZIP entry")
        if infos[0].compress_type != zipfile.ZIP_STORED:
            raise RuntimeError("EPUB mimetype is compressed")
        content = src.read("OEBPS/content.xhtml")
        ncx = src.read("OEBPS/toc.ncx")
        patched_content, anchors = patch_content(content)
        patched_ncx = patch_ncx(ncx, anchors)

        with tempfile.NamedTemporaryFile(prefix="x3-main-", suffix=".epub", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with zipfile.ZipFile(tmp_path, "w") as dst:
                for info in infos:
                    if info.filename == "OEBPS/content.xhtml":
                        data = patched_content
                    elif info.filename == "OEBPS/toc.ncx":
                        data = patched_ncx
                    else:
                        data = src.read(info.filename)
                    dst.writestr(info, data)
            shutil.move(tmp_path, path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    # Re-open and validate the repacked file itself.
    with zipfile.ZipFile(path, "r") as check:
        infos = check.infolist()
        if infos[0].filename != "mimetype" or infos[0].compress_type != zipfile.ZIP_STORED:
            raise RuntimeError("Repacked EPUB broke mimetype placement/compression")
        patched_root = ET.fromstring(check.read("OEBPS/content.xhtml"))
        for a in patched_root.findall(f".//{q(XHTML_NS, 'a')}"):
            if "".join(a.itertext()).strip().lower().startswith("читать полностью"):
                raise RuntimeError("Validation found a «Читать полностью» link")
    return anchors


def main() -> None:
    dated = current_epub_from_opds()
    anchors = patch_epub(dated)
    shutil.copyfile(dated, "latest.epub")
    if Path("latest.epub").read_bytes() != dated.read_bytes():
        raise RuntimeError("latest.epub does not match the patched dated EPUB")
    print(f"Promoted {len(anchors)} full articles into Главое: {', '.join(anchors)}")


if __name__ == "__main__":
    main()
