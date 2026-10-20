#!/usr/bin/env python3
"""Сбор кандидатов для ночного выпуска «МУЖСКОЙ».

Читает RSS-ленты из FEEDS, отбрасывает уже использованные материалы (chatgpt/seen.json,
по URL и по заголовку), загружает полный текст, уважая robots.txt, и оставляет статьи
длиннее MIN_CHARS. Результат: editor/work/harvest.json (список кандидатов с полным
текстом) и editor/work/list.txt (краткий список для выбора).

Запуск:  python3 editor/harvest.py
Только стандартная библиотека. Платные стены и запреты robots.txt не обходятся.
"""
import concurrent.futures as cf
import html
import html.parser
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = Path(__file__).resolve().parent / "work"
UA = "xteink-daily-news/1.0 (personal reader, one fetch per article)"
MIN_CHARS = 3500
PER_FEED = 14

FEEDS = {
    "Men's Health": "https://www.menshealth.com/rss/all.xml/",
    "GQ": "https://www.gq.com/feed/rss",
    "Esquire": "https://www.esquire.com/rss/all.xml/",
    "Runner's World": "https://www.runnersworld.com/rss/all.xml/",
    "Bicycling": "https://www.bicycling.com/rss/all.xml/",
    "Outside": "https://www.outsideonline.com/feed/",
    "Road & Track": "https://www.roadandtrack.com/rss/all.xml/",
    "Car and Driver": "https://www.caranddriver.com/rss/all.xml/",
    "Popular Mechanics": "https://www.popularmechanics.com/rss/all.xml/",
    "Popular Science": "https://www.popsci.com/arcio/rss/",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "WIRED": "https://www.wired.com/feed/rss",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
    "Smithsonian": "https://www.smithsonianmag.com/rss/latest_articles/",
    "Atlas Obscura": "https://www.atlasobscura.com/feeds/latest",
    "Quanta": "https://www.quantamagazine.org/feed/",
    "Scientific American": "https://www.scientificamerican.com/platform/syndication/rss/",
    "Gear Patrol": "https://www.gearpatrol.com/feed/",
}

# покупки, скидки, политика и войны в журнал не берём
BAD = re.compile(
    r"\bbest\b|\bdeals?\b|\bgift|advent|\breview\b|\bsale\b|\bhow to watch\b|\bcoupon|\bdiscount|% off|"
    r"\bprime day|black friday|\bgallery|\btrump|\bbiden|\bgaza|\bukraine|\bkirk\b|election|\bhoroscope",
    re.I)

# с этих строк начинаются хвосты «читайте также», подписки и био автора
TAIL = re.compile(
    r"^(more great|more from|more of our|read more|readers also|related|you might also|you may also|"
    r"sign up|subscribe|newsletter|follow us|this story originally|this article originally|"
    r"to read more|more stories|recommended|trending|advertisement|get the .* newsletter)", re.I)


class Http:
    def get(self, url, timeout=30, max_bytes=3_000_000):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(max_bytes + 1)
                cs = r.headers.get_content_charset() or "utf-8"
                return r.status, raw[:max_bytes].decode(cs, errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, ""
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return 0, str(e)[:80]


class Extract(html.parser.HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "aside", "form", "noscript", "svg", "template"}
    BLOCK = {"p", "h1", "h2", "h3", "li", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.art = 0
        self.cur = None
        self.blocks = []
        self.title = ""
        self.og = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("property") == "og:title":
            self.og = a.get("content") or ""
        if tag == "title":
            self.in_title = True
        if tag in self.SKIP:
            self.skip += 1
        elif tag in ("article", "main"):
            self.art += 1
        elif tag in self.BLOCK and self.skip == 0:
            self.cur = (tag, [])

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in ("article", "main"):
            self.art = max(0, self.art - 1)
        elif self.cur and tag == self.cur[0]:
            t = re.sub(r"\s+", " ", "".join(self.cur[1])).strip()
            if t:
                self.blocks.append((self.art > 0, tag, t))
            self.cur = None

    def handle_data(self, d):
        if self.in_title:
            self.title += d
        if self.cur is not None and self.skip == 0:
            self.cur[1].append(d)


def article_text(page):
    p = Extract()
    p.feed(page)
    keep = lambda bl: [t for _, tag, t in bl if tag.startswith("h") or len(t) >= 25]
    inside = keep([b for b in p.blocks if b[0]])
    chosen = inside if sum(map(len, inside)) >= 1500 else keep(p.blocks)
    paras = []
    for t in chosen:
        if TAIL.match(t):
            break  # всё после «читайте также» — мусор
        paras.append(t)
    return (p.og or p.title).strip(), "\n\n".join(paras)


def norm_title(s):
    return re.sub(r"[^a-zа-я0-9]+", " ", s.lower()).strip()


def load_seen():
    urls, titles = set(), set()
    p = ROOT / "chatgpt" / "seen.json"
    if p.exists():
        for a in json.load(open(p, encoding="utf-8")):
            urls.add(a.get("url", ""))
            titles.add(norm_title(a.get("title", "")))
    return urls, titles


def main():
    http = Http()
    seen_urls, seen_titles = load_seen()

    def feed(item):
        name, url = item
        st, xml = http.get(url, max_bytes=4_000_000)
        if st != 200:
            return name, [], f"HTTP {st} {xml if st == 0 else ''}".strip()
        try:
            root = ET.fromstring(xml.encode("utf-8"))
        except ET.ParseError as e:
            return name, [], f"XML: {e}"
        out = []
        for it in list(root.iter("item")) + list(root.iter("{http://www.w3.org/2005/Atom}entry")):
            g = lambda tag: next((e for e in it if e.tag.split('}')[-1] == tag), None)
            l = g("link")
            link = ((l.text or l.get("href") or "") if l is not None else "").strip()
            ti = g("title")
            title = html.unescape((ti.text or "").strip()) if ti is not None else ""
            if link.startswith("http") and title and link not in seen_urls \
                    and norm_title(title) not in seen_titles and not BAD.search(title):
                out.append({"source": name, "title": title, "url": link})
        return name, out[:PER_FEED], ""

    pool = []
    with cf.ThreadPoolExecutor(6) as ex:
        for name, items, err in ex.map(feed, FEEDS.items()):
            print(f"лента {name}: {len(items)} {err}")
            pool += items

    robots = {}

    def allowed(url):
        parts = urllib.parse.urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in robots:
            rp = urllib.robotparser.RobotFileParser()
            st, txt = http.get(host + "/robots.txt", timeout=15)
            if st == 200:
                rp.parse(txt.splitlines())
                robots[host] = rp
            else:
                robots[host] = None
        rp = robots[host]
        return rp is None or rp.can_fetch(UA, url)

    def art(c):
        try:
            if not allowed(c["url"]):
                return dict(c, chars=0, err="robots.txt")
            st, page = http.get(c["url"], max_bytes=2_000_000)
            if st != 200:
                return dict(c, chars=0, err=f"HTTP {st}")
            _, text = article_text(page)
            m = re.search(r'(?:article:published_time|datePublished)["\']?[^0-9]{0,12}(\d{4}-\d{2}-\d{2})', page)
            return dict(c, published=m.group(1) if m else "", chars=len(text), text=text)
        except Exception as e:  # одна плохая статья не должна валить сбор
            return dict(c, chars=0, err=str(e)[:80])

    with cf.ThreadPoolExecutor(6) as ex:
        res = list(ex.map(art, pool))
    good = [r for r in res if r["chars"] >= MIN_CHARS]
    WORK.mkdir(exist_ok=True)
    json.dump(good, open(WORK / "harvest.json", "w", encoding="utf-8"), ensure_ascii=False)
    with open(WORK / "list.txt", "w", encoding="utf-8") as f:
        for i, r in enumerate(good):
            f.write(f"{i}\t{r['source']}\t{r['chars']}\t{r.get('published','')}\t{r['title'][:100]}\n")
    print(f"полных текстов >= {MIN_CHARS}: {len(good)} из {len(res)}; список: {WORK/'list.txt'}")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
