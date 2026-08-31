#!/usr/bin/env python3
import json, html, shutil, uuid, zipfile
from pathlib import Path
from datetime import datetime, timezone

REPO='egor0997777-byte/xteink-daily-news'
BASE=f'https://raw.githubusercontent.com/{REPO}/main'

def x(s): return html.escape(str(s), quote=True)

def make_epub(data, out):
    uid=str(uuid.uuid4()); title=data['title']; articles=data['articles']
    tmp=Path('.digest_build'); shutil.rmtree(tmp, ignore_errors=True)
    (tmp/'META-INF').mkdir(parents=True); (tmp/'OEBPS').mkdir()
    (tmp/'mimetype').write_text('application/epub+zip',encoding='utf-8')
    (tmp/'META-INF/container.xml').write_text('<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',encoding='utf-8')
    css='body{font-family:serif;line-height:1.5;margin:5%;}h1{font-size:1.5em;}h2{font-size:1.2em;margin-top:1.5em;}p{margin:.65em 0;text-align:left}.source{font-size:.85em;color:#555}.toc li{margin:.55em 0}'
    (tmp/'OEBPS/style.css').write_text(css,encoding='utf-8')
    toc=''.join(f'<li><a href="a{i}.xhtml">{x(a["title"])}</a></li>' for i,a in enumerate(articles,1))
    (tmp/'OEBPS/index.xhtml').write_text(f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>{x(title)}</title><link rel="stylesheet" href="style.css" type="text/css"/></head><body><h1>{x(title)}</h1><p>Свежие технологические новости в нормальном связном пересказе — гаджеты, железо, игры, наука, космос, безопасность, транспорт, интернет и ИИ без перекоса в одну тему.</p><ol class="toc">{toc}</ol></body></html>',encoding='utf-8')
    for i,a in enumerate(articles,1):
        paras=''.join(f'<p>{x(p.strip())}</p>' for p in a['text'].split('\n\n') if p.strip())
        src=f'<p class="source">Источник: {x(a.get("source",""))}</p>' if a.get('source') else ''
        (tmp/f'OEBPS/a{i}.xhtml').write_text(f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>{x(a["title"])}</title><link rel="stylesheet" href="style.css" type="text/css"/></head><body><h2>{x(a["title"])}</h2>{paras}{src}</body></html>',encoding='utf-8')
    manifest='<item id="idx" href="index.xhtml" media-type="application/xhtml+xml"/><item id="css" href="style.css" media-type="text/css"/>' + ''.join(f'<item id="a{i}" href="a{i}.xhtml" media-type="application/xhtml+xml"/>' for i in range(1,len(articles)+1))
    spine='<itemref idref="idx"/>'+''.join(f'<itemref idref="a{i}"/>' for i in range(1,len(articles)+1))
    opf=f'''<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="uid">urn:uuid:{uid}</dc:identifier><dc:title>{x(title)}</dc:title><dc:language>ru</dc:language><dc:creator>Технодайджест Xteink X3</dc:creator><meta property="dcterms:modified">{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}</meta></metadata><manifest>{manifest}</manifest><spine>{spine}</spine></package>'''
    (tmp/'OEBPS/content.opf').write_text(opf,encoding='utf-8')
    with zipfile.ZipFile(out,'w') as z:
        z.write(tmp/'mimetype','mimetype',compress_type=zipfile.ZIP_STORED)
        for p in sorted(tmp.rglob('*')):
            if p.is_file() and p.name!='mimetype': z.write(p,p.relative_to(tmp),compress_type=zipfile.ZIP_DEFLATED)
    shutil.rmtree(tmp,ignore_errors=True)

def opds(data, epub):
    updated=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return f'''<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog"><id>urn:xteink:tech-digest</id><title>Техноновости для Xteink X3</title><updated>{updated}</updated><author><name>Технодайджест X3</name></author><entry><title>{x(data['title'])}</title><id>urn:xteink:tech:{x(data['date'])}</id><updated>{updated}</updated><content type="text">{len(data['articles'])} новостей — связный перевод-пересказ из разных зарубежных источников.</content><link rel="http://opds-spec.org/acquisition" type="application/epub+zip" href="{BASE}/{epub}"/><link rel="http://opds-spec.org/acquisition" type="application/epub+zip" href="{BASE}/latest.epub"/></entry></feed>'''

def load_digest():
    parts=sorted(Path('tech_digest_parts').glob('part*.json'))
    if parts:
        merged=None
        articles=[]
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
print(f'Built {epub}: {len(data["articles"])} narrated stories')
