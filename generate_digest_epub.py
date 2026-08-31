#!/usr/bin/env python3
import json, html, shutil, uuid, zipfile, re
from pathlib import Path
from datetime import datetime, timezone

REPO='egor0997777-byte/xteink-daily-news'
BASE=f'https://raw.githubusercontent.com/{REPO}/main'

def x(s): return html.escape(str(s), quote=True)

def compact_text(text, max_words=92):
    """Keep an article compact enough for roughly one X3 screen, ending on a sentence."""
    text=' '.join(str(text).split())
    words=text.split()
    if len(words) <= max_words:
        return text
    cut=' '.join(words[:max_words])
    # Prefer a complete sentence near the end of the target window.
    m=list(re.finditer(r'[.!?](?:[»”\"])?(?=\s|$)', cut))
    if m:
        end=m[-1].end()
        candidate=cut[:end].strip()
        if len(candidate.split()) >= 68:
            return candidate
    return cut.rstrip(' ,;:-') + '…'

def make_epub(data, out):
    uid=str(uuid.uuid4()); title=data['title']; articles=data['articles']
    tmp=Path('.digest_build'); shutil.rmtree(tmp, ignore_errors=True)
    (tmp/'META-INF').mkdir(parents=True); (tmp/'OEBPS').mkdir()
    (tmp/'mimetype').write_text('application/epub+zip',encoding='utf-8')
    (tmp/'META-INF/container.xml').write_text('<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',encoding='utf-8')
    css='body{font-family:serif;line-height:1.34;margin:4%;}h2{font-size:1.14em;line-height:1.18;margin:.15em 0 .65em 0;}p{font-size:1em;margin:0;text-align:left;} .article{page-break-after:always;break-after:page;}'
    (tmp/'OEBPS/style.css').write_text(css,encoding='utf-8')

    # No visible cover or table of contents: the first page is the first story.
    for i,a in enumerate(articles,1):
        body=compact_text(a.get('text',''))
        (tmp/f'OEBPS/a{i}.xhtml').write_text(
            f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>{x(a["title"])}</title><link rel="stylesheet" href="style.css" type="text/css"/></head><body><div class="article"><h2>{x(a["title"])}</h2><p>{x(body)}</p></div></body></html>',
            encoding='utf-8')

    manifest='<item id="css" href="style.css" media-type="text/css"/>' + ''.join(f'<item id="a{i}" href="a{i}.xhtml" media-type="application/xhtml+xml"/>' for i in range(1,len(articles)+1))
    spine=''.join(f'<itemref idref="a{i}"/>' for i in range(1,len(articles)+1))
    opf=f'''<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="uid">urn:uuid:{uid}</dc:identifier><dc:title>{x(title)}</dc:title><dc:language>ru</dc:language><dc:creator>Технодайджест Xteink X3</dc:creator><meta property="dcterms:modified">{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}</meta></metadata><manifest>{manifest}</manifest><spine>{spine}</spine></package>'''
    (tmp/'OEBPS/content.opf').write_text(opf,encoding='utf-8')
    with zipfile.ZipFile(out,'w') as z:
        z.write(tmp/'mimetype','mimetype',compress_type=zipfile.ZIP_STORED)
        for p in sorted(tmp.rglob('*')):
            if p.is_file() and p.name!='mimetype': z.write(p,p.relative_to(tmp),compress_type=zipfile.ZIP_DEFLATED)
    shutil.rmtree(tmp,ignore_errors=True)

def opds(data, epub):
    updated=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return f'''<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog"><id>urn:xteink:tech-digest</id><title>Техноновости для Xteink X3</title><updated>{updated}</updated><author><name>Технодайджест X3</name></author><entry><title>{x(data['title'])}</title><id>urn:xteink:tech:{x(data['date'])}</id><updated>{updated}</updated><content type="text">{len(data['articles'])} новостей — по одной законченной новости на экран, без оглавления и служебных строк.</content><link rel="http://opds-spec.org/acquisition" type="application/epub+zip" href="{BASE}/{epub}"/><link rel="http://opds-spec.org/acquisition" type="application/epub+zip" href="{BASE}/latest.epub"/></entry></feed>'''

def load_digest():
    parts=sorted(Path('tech_digest_parts').glob('part*.json'))
    if parts:
        merged=None; articles=[]
        for p in parts:
            chunk=json.loads(p.read_text(encoding='utf-8'))
            if merged is None:
                merged={'date':chunk['date'],'title':chunk['title'],'articles':[]}
            if chunk['date'] != merged['date']:
                raise ValueError(f'Date mismatch in {p}')
            articles.extend(chunk['articles'])
        merged['articles']=articles
        return merged
    return json.loads(Path('tech_digest.json').read_text(encoding='utf-8'))

data=load_digest()
epub=f"{data['date']}.epub"
make_epub(data,epub)
shutil.copyfile(epub,'latest.epub')
Path('opds.xml').write_text(opds(data,epub),encoding='utf-8')
print(f'Built {epub}: {len(data["articles"])} one-screen stories')
