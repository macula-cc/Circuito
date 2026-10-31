#!/usr/bin/env python3
"""Baixa as fotos dos artistas (links da planilha) para catalogo-fotos/, já redimensionadas.

Por que existe: o Google limita (erro 429) miniaturas do Drive pedidas direto
pelo navegador dos visitantes. Baixando uma vez por aqui, o catalogo.html serve
as fotos do próprio site.

Uso (na pasta do projeto):   python3 scripts/baixar-fotos-catalogo.py
Refazer tudo:                python3 scripts/baixar-fotos-catalogo.py --force
Saída: catalogo-fotos/<slug>.jpg (até 1600px), catalogo-fotos/t/<slug>.jpg (até 640px)
       e catalogo-fotos/manifest.json (slug -> 1 = tem foto local, 0 = link não funciona).
"""
import csv, io, json, os, re, sys, time, unicodedata, urllib.request
from PIL import Image, ImageOps

SHEET = 'https://docs.google.com/spreadsheets/d/1Zjux0r3uVJ8ua1ZXpWd68lOSP5Kj0XkU/gviz/tq?tqx=out:csv&sheet=Circuito'
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'catalogo-fotos')
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/130 Safari/537.36'}
FORCE = '--force' in sys.argv


def slugify(s):
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'^-|-$', '', re.sub(r'[^a-z0-9]+', '-', s))


def photo_url(raw):
    m = re.search(r'https?://\S+', raw or '')
    if not m:
        return None
    url = m.group(0)
    d = re.search(r'drive\.google\.com/file/d/([\w-]+)', url) or re.search(r'drive\.google\.com/(?:open|uc)\?[^#]*\bid=([\w-]+)', url)
    if d:
        return f'https://drive.google.com/thumbnail?id={d.group(1)}&sz=w1600'
    if re.search(r'\.(jpe?g|png|webp|gif|avif)(\?|$)', url, re.I) or re.search(r'freight\.cargo\.site|payload\.cargocollective\.com', url):
        return url
    return None


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        ctype = r.headers.get('Content-Type', '')
        data = r.read()
    if not ctype.startswith('image/'):
        raise ValueError(f'não é imagem ({ctype})')
    return data


def save(data, path, maxside, quality):
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA')
        bg = Image.new('RGB', im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert('RGB')
    im.thumbnail((maxside, maxside), Image.LANCZOS)
    im.save(path, 'JPEG', quality=quality, optimize=True, progressive=True)


def main():
    os.makedirs(os.path.join(ROOT, 't'), exist_ok=True)
    text = urllib.request.urlopen(urllib.request.Request(SHEET, headers=UA), timeout=40).read().decode('utf-8')
    rows = list(csv.reader(io.StringIO(text)))
    idx = {h.strip(): i for i, h in enumerate(rows[0])}
    get = lambda r, n: r[idx[n]].strip() if n in idx and idx[n] < len(r) else ''

    used, manifest, falhas, semfoto = set(), {}, [], []
    for r in rows[1:]:
        nome = get(r, 'Nome do Artista')
        if not nome:
            continue
        slug = slugify(nome) or 'artista'
        base, n = slug, 2
        while slug in used:
            slug = f'{base}-{n}'; n += 1
        used.add(slug)
        url = photo_url(get(r, 'Foto do trabalho (URL)'))
        if not url:
            semfoto.append(nome); continue
        big, small = os.path.join(ROOT, f'{slug}.jpg'), os.path.join(ROOT, 't', f'{slug}.jpg')
        if not FORCE and os.path.exists(big) and os.path.exists(small):
            manifest[slug] = 1; continue
        ok = False
        for tentativa in range(3):
            try:
                data = fetch(url)
                save(data, big, 1600, 82); save(data, small, 640, 80)
                manifest[slug] = 1; ok = True
                print('ok  ', nome); break
            except Exception as e:
                err = str(e)
                time.sleep(1.5 * (tentativa + 1))
        if not ok:
            falhas.append((nome, err)); manifest[slug] = 0; print('FALHA', nome, '-', err)
        time.sleep(.25)

    with open(os.path.join(ROOT, 'manifest.json'), 'w') as f:
        json.dump(dict(sorted(manifest.items())), f, ensure_ascii=False, separators=(',', ':'))
    print(f'\n{sum(manifest.values())} fotos locais | {len(falhas)} falhas | {len(semfoto)} sem link de foto utilizável')
    for nome, err in falhas:
        print('  falhou:', nome, '-', err)


main()
