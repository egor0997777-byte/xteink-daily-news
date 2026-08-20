#!/usr/bin/env python3
"""RSS to dated EPUB + OPDS for Xteink X3. Full text + nested TOC. Stdlib only."""
from __future__ import annotations
import html, re, shutil, time, uuid, zipfile
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
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
MAX_PER_SOURCE, MAX_AGE_HOURS, MAX_FULL_FETCH, SHORT_DESC = 15, 48, 80, 600
USER_AGENT = "Mozilla/5.0 (compatible; XteinkNewsBot/1.0)"
REPO, BRANCH = "egor0997777-byte/xteink-daily-news", "main"
BASE_RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
OUTPUT_DIR = Path(".")

def fetch_url(url, timeout=18):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()

def strip_html(text):
    if not text: return ""
    text = html.unescape(text)
    text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", text, flags=re.I|re.S)
    text = re.sub(r"</?(p|div|br|h[1-6]|li|tr|blockquote)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()

class ArticleExtractor(HTMLParser):
    SKIP = {"script","style","nav","footer","header","aside","form","iframe","noscript"}
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip_depth=0
    def handle_starttag(self, tag, attrs):
        t=tag.lower()
        if t in self.SKIP: self.skip_depth+=1; return
        if self.skip_depth: return
        if t in ("p","br","h1","h2","h3","h4","li","blockquote"): self.parts.append("\n")
    def handle_endtag(self, tag):
        t=tag.lower()
        if t in self.SKIP and self.skip_depth: self.skip_depth-=1; return
        if self.skip_depth: return
        if t in ("p","h1","h2","h3","h4","li","blockquote","div"): self.parts.append("\n")
    def handle_data(self, data):
        if self.skip_depth: return
        s=data.strip()
        if s: self.parts.append(s+" ")
    def text(self):
        t="".join(self.parts)
        t=re.sub(r"[ \t]+"," ",t)
        return re.sub(r"\n{3,}","\n\n",t).strip()

def extract_article_text(page_html):
    candidates=[]
    for pat in (r'<article[^>]*>(.*?)</article>',
                r'<div[^>]+class="[^"]*(?:article-body|post-content|entry-content|tm-article-body|content-body|article__text)[^"]*"[^>]*>(.*?)</div>',
                r'<div[^>]+itemprop="articleBody"[^>]*>(.*?)</div>'):
        m=re.search(pat, page_html, re.I|re.S)
        if m: candidates.append(m.group(1) if m.lastindex else m.group(0))
    chunk=max(candidates,key=len) if candidates else page_html
    chunk=re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>","",chunk,flags=re.I|re.S)
    p=ArticleExtractor()
    try:
        p.feed(chunk); text=p.text()
    except Exception:
        text=strip_html(chunk)
    return text[:25000] if len(text)>=200 else ""

def normalize_title(title):
    t=title.lower().strip()
    t=re.sub(r"[^\w\sа-яё]","",t,flags=re.I)
    return re.sub(r"\s+"," ",t)

def parse_pubdate(item):
    for tag in ("pubDate","{http://purl.org/dc/elements/1.1/}date","date"):
        el=item.find(tag)
        if el is not None and el.text:
            try:
                dt=parsedate_to_datetime(el.text.strip())
                if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception: pass
    return None

def get_text(item, *tags):
    for tag in tags:
        el=item.find(tag)
        if el is not None and el.text: return el.text.strip()
        for child in item:
            if child.tag.endswith("}"+tag) or child.tag==tag:
                if child.text: return child.text.strip()
    return ""

def get_link(item):
    link=get_text(item,"link")
    if link: return link
    for el in item.findall("link")+item.findall("{http://www.w3.org/2005/Atom}link"):
        href=el.get("href")
        if href: return href
        if el.text: return el.text.strip()
    return ""

def fetch_feed(name, url):
    items=[]
    try:
        data=fetch_url(url)
        if not data or len(data)<50:
            print(f"[WARN] {name}: empty response"); return items
        root=ET.fromstring(data)
    except Exception as e:
        print(f"[WARN] {name}: {e}"); return items
    channel=root.find("channel")
    entries=channel.findall("item") if channel is not None else (root.findall("{http://www.w3.org/2005/Atom}entry") or root.findall("entry"))
    for entry in entries:
        title=get_text(entry,"title"); link=get_link(entry)
        desc=get_text(entry,"description","summary","{http://purl.org/rss/1.0/modules/content/}encoded")
        pub=parse_pubdate(entry)
        if not title or not link: continue
        items.append({"title":title,"link":link,"description":strip_html(desc),"body":"","pub":pub,"source":name})
    print(f"[OK] {name}: {len(items)}"); return items

def dedup_filter(items, limit):
    seen_u,seen_t=set(),set(); unique=[]
    for it in items:
        u=it["link"].split("?")[0].rstrip("/"); nt=normalize_title(it["title"])
        if u in seen_u or nt in seen_t: continue
        seen_u.add(u); seen_t.add(nt); unique.append(it)
    cutoff=datetime.now(timezone.utc)-timedelta(hours=MAX_AGE_HOURS)
    fresh=[it for it in unique if it["pub"] is None or it["pub"]>=cutoff]
    fresh.sort(key=lambda x: x["pub"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return fresh[:limit]

def enrich_full_text(items):
    fetched=0
    for it in items:
        if fetched>=MAX_FULL_FETCH: break
        desc=it.get("description") or ""
        if len(desc)>=SHORT_DESC: it["body"]=desc; continue
        try:
            raw=fetch_url(it["link"], timeout=15)
            try: page=raw.decode("utf-8")
            except UnicodeDecodeError: page=raw.decode("cp1251", errors="ignore")
            text=extract_article_text(page)
            if len(text)>len(desc)+100:
                it["body"]=text; fetched+=1
                print(f"  [full] {it['title'][:50]} ({len(text)} c)")
            else: it["body"]=desc
            time.sleep(0.25)
        except Exception as e:
            it["body"]=desc; print(f"  [skip] {it['title'][:40]}: {e}")

def escape_xml(s):
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&apos;")

def build_epub(by_source, path, book_title):
    book_id=str(uuid.uuid4()); now=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body_parts=[f"<h1>{escape_xml(book_title)}</h1>"]
    total=sum(len(v) for v in by_source.values())
    body_parts.append(f'<p class="meta">Обновлено: {now} · {total} статей · {len(by_source)} источников</p><hr/>')
    ncx_nav=[]; play=1; art_id=0
    for src_name, items in by_source.items():
        if not items: continue
        chap_id=f"ch-{play}"
        body_parts.append(f'<h1 id="{chap_id}">{escape_xml(src_name)}</h1>')
        child_nav=[]
        for it in items:
            art_id+=1; aid=f"a{art_id}"; pub_str=""
            if it["pub"]:
                try: pub_str=it["pub"].astimezone(timezone(timedelta(hours=3))).strftime("%d.%m %H:%M")
                except Exception: pass
            t=escape_xml(it["title"]); body=escape_xml(it.get("body") or it.get("description") or ""); link=escape_xml(it["link"])
            body_parts.append(f'<article id="{aid}"><h2>{t}</h2><p class="meta">{pub_str}</p><p>{body}</p><p class="link"><a href="{link}">Источник</a></p></article><hr/>')
            child_nav.append(f'      <navPoint id="np{play}-{art_id}" playOrder="{play+art_id}">\n        <navLabel><text>{escape_xml(it["title"][:70])}</text></navLabel>\n        <content src="content.xhtml#{aid}"/>\n      </navPoint>')
        ncx_nav.append(f'    <navPoint id="np{play}" playOrder="{play}">\n      <navLabel><text>{escape_xml(src_name)} ({len(items)})</text></navLabel>\n      <content src="content.xhtml#{chap_id}"/>\n'+"\n".join(child_nav)+f'\n    </navPoint>')
        play+=1
    content_xhtml=f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru">
<head><meta charset="utf-8"/><title>{escape_xml(book_title)}</title>
<style>body{{font-family:serif;font-size:1em;line-height:1.4;margin:0.7em}}h1{{font-size:1.3em;margin:1em 0 0.4em;page-break-before:always}}h1:first-of-type{{page-break-before:avoid}}h2{{font-size:1.1em;margin:0.8em 0 0.25em}}.meta{{font-size:0.85em;color:#444}}.link{{font-size:0.8em}}hr{{border:none;border-top:1px solid #ccc;margin:0.9em 0}}p{{margin:0.4em 0}}</style>
</head><body>
{chr(10).join(body_parts)}
</body></html>'''
    opf=f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="BookId">urn:uuid:{book_id}</dc:identifier>
<dc:title>{escape_xml(book_title)}</dc:title><dc:language>ru</dc:language>
<dc:creator>Xteink Daily News</dc:creator><dc:date>{now}</dc:date>
</metadata>
<manifest>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
<item id="content" href="content.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine toc="ncx"><itemref idref="content"/></spine>
</package>'''
    ncx=f'''<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head><meta name="dtb:uid" content="urn:uuid:{book_id}"/><meta name="dtb:depth" content="2"/>
<meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/></head>
<docTitle><text>{escape_xml(book_title)}</text></docTitle>
<navMap>
{chr(10).join(ncx_nav)}
</navMap></ncx>'''
    container='''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>'''
    with zipfile.ZipFile(path,"w") as zf:
        zf.writestr("mimetype","application/epub+zip",compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml",container,compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf",opf,compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/toc.ncx",ncx,compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.xhtml",content_xhtml,compress_type=zipfile.ZIP_DEFLATED)

def write_opds(path, epub_name, title, count):
    now=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml=f'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">
<id>urn:xteink:daily-news</id><title>Xteink Tech News</title><updated>{now}</updated>
<author><name>Xteink Daily News</name></author>
<link rel="self" href="{BASE_RAW}/opds.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
<link rel="start" href="{BASE_RAW}/opds.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
<entry>
<id>urn:xteink:latest</id><title>{escape_xml(title)}</title><updated>{now}</updated>
<content type="text">{count} статей. Оглавление: источник → статья. Полный текст где возможно.</content>
<link rel="http://opds-spec.org/acquisition" href="{BASE_RAW}/{epub_name}" type="application/epub+zip"/>
</entry></feed>'''
    path.write_text(xml, encoding="utf-8")

def main():
    print("Collecting RSS..."); by_source={}
    for name,url in RSS_FEEDS:
        items=fetch_feed(name,url)
        filtered=dedup_filter(items, MAX_PER_SOURCE)
        if filtered: by_source[name]=filtered
    seen=set()
    for src in list(by_source.keys()):
        cleaned=[]
        for it in by_source[src]:
            key=it["link"].split("?")[0].rstrip("/")
            if key in seen: continue
            seen.add(key); cleaned.append(it)
        if cleaned: by_source[src]=cleaned
        else: del by_source[src]
    all_items=[it for items in by_source.values() for it in items]
    print(f"Sources: {len(by_source)}, items: {len(all_items)}")
    print("Fetching full text where needed..."); enrich_full_text(all_items)
    msk=datetime.now(timezone(timedelta(hours=3)))
    date_str=msk.strftime("%Y-%m-%d")
    book_title=f"Техновости · {msk.strftime('%d.%m.%Y')}"
    dated_name=f"{date_str}.epub"
    print(f"Building {dated_name}...")
    build_epub(by_source, OUTPUT_DIR/dated_name, book_title)
    shutil.copy(OUTPUT_DIR/dated_name, OUTPUT_DIR/"latest.epub")
    write_opds(OUTPUT_DIR/"opds.xml", dated_name, book_title, len(all_items))
    print(f"Done: {dated_name} ({(OUTPUT_DIR/dated_name).stat().st_size} bytes)")

if __name__ == "__main__":
    main()
