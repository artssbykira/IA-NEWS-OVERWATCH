#!/usr/bin/env python3
"""
Robo de noticias de Overwatch para o Discord do KIRA.

A cada execucao:
  1. le as fontes (forum oficial da Blizzard, YouTube do Overwatch, Reddit)
  2. separa o que ainda nao foi postado (vistos.json)
  3. a IA (Gemini, camada gratis) resume em portugues e diz se afeta o Doomfist
  4. posta no #overwatch-news e, quando for o caso, no #doomfist

So usa a biblioteca padrao do Python: nada para instalar.

Uso:
  python noticias.py                    execucao normal
  python noticias.py --seco             mostra o que postaria, sem postar nem salvar
  python noticias.py --postar-ultimo 1  posta a ultima nota de patch agora (teste)
  python noticias.py --sem-ia           nao chama a IA (filtro por palavra-chave)
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
ESTADO = os.path.join(AQUI, 'vistos.json')
UA = 'Mozilla/5.0 (compatible; KiraNewsBot/1.0; +https://linktr.ee/kira_owbr)'

# Nao posta nada mais antigo que isso, mesmo que nunca tenha sido visto.
IDADE_MAXIMA = timedelta(days=3)

FONTES = [
    {'id': 'forum', 'nome': 'Blizzard - Anuncios oficiais', 'cor': 0xF99E1A,
     'url': 'https://us.forums.blizzard.com/en/overwatch/c/announcements/5.rss'},
    {'id': 'youtube', 'nome': 'YouTube - Overwatch', 'cor': 0xFF0000,
     'url': 'https://www.youtube.com/feeds/videos.xml?channel_id=UClOf1XXinvZsy4wKPAkro2A'},
    # O Reddit as vezes recusa (429/403). Quando falha, o robo so pula a fonte.
    {'id': 'reddit-ow', 'nome': 'Reddit - r/Overwatch', 'cor': 0xFF4500,
     'url': 'https://www.reddit.com/r/Overwatch/top/.rss?t=day&limit=10'},
    {'id': 'reddit-doom', 'nome': 'Reddit - r/DoomfistMains', 'cor': 0xFF4500,
     'url': 'https://www.reddit.com/r/DoomfistMains/top/.rss?t=day&limit=10'},
]

COR_DOOMFIST = 0x8E44AD
MODELOS = [m.strip() for m in os.environ.get('GEMINI_MODELO', '').split(',') if m.strip()] or \
          ['gemini-flash-latest', 'gemini-2.5-flash', 'gemini-2.0-flash']


try:  # o console do Windows nao imprime emoji sem isso
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass


def log(msg):
    print(time.strftime('%H:%M:%S'), msg, flush=True)


# ---------------------------------------------------------------- leitura das fontes

def baixar(url, dados=None, cabecalhos=None, timeout=40):
    req = urllib.request.Request(url, data=dados, headers={'User-Agent': UA, **(cabecalhos or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def limpar_html(texto):
    texto = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', texto or '', flags=re.S | re.I)
    texto = re.sub(r'<br\s*/?>|</p>|</li>|</h\d>', '\n', texto, flags=re.I)
    texto = re.sub(r'<[^>]+>', ' ', texto)
    texto = html.unescape(texto)
    texto = re.sub(r'[ \t\r\f\v]+', ' ', texto)
    return re.sub(r'\n\s*\n+', '\n', texto).strip()


def data_iso(texto):
    if not texto:
        return datetime.now(timezone.utc)
    try:
        return parsedate_to_datetime(texto).astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(texto.replace('Z', '+00:00')).astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def ler_fonte(fonte):
    raiz = ET.fromstring(baixar(fonte['url']))
    itens = []
    if raiz.tag == 'rss':
        for it in raiz.iter('item'):
            link = (it.findtext('link') or '').strip()
            itens.append({
                'id': (it.findtext('guid') or link).strip(),
                'titulo': (it.findtext('title') or '').strip(),
                'link': link,
                'data': data_iso(it.findtext('pubDate')),
                'texto': limpar_html(it.findtext('description')),
            })
    else:  # Atom (YouTube e Reddit)
        ns = {'a': 'http://www.w3.org/2005/Atom', 'm': 'http://search.yahoo.com/mrss/'}
        for en in raiz.findall('a:entry', ns):
            link = ''
            for l in en.findall('a:link', ns):
                if l.get('rel', 'alternate') == 'alternate':
                    link = l.get('href', '')
            corpo = en.findtext('a:content', '', ns) or en.findtext('m:group/m:description', '', ns)
            itens.append({
                'id': (en.findtext('a:id', '', ns) or link).strip(),
                'titulo': (en.findtext('a:title', '', ns) or '').strip(),
                'link': link,
                'data': data_iso(en.findtext('a:published', '', ns) or en.findtext('a:updated', '', ns)),
                'texto': limpar_html(corpo),
            })
    for it in itens:
        it['fonte'] = fonte
    return itens


# ---------------------------------------------------------------- IA (Gemini gratis)

PROMPT = """Voce e o editor do Discord do KIRA, streamer brasileiro de Overwatch que joga de Doomfist
(Top 500 no 5v5 e um dos melhores Doomfist do modo Stadium).

Leia a publicacao abaixo e responda APENAS com um JSON neste formato:
{{
  "relevante": true/false,
  "titulo": "titulo curto em portugues do Brasil, ate 90 caracteres",
  "resumo": "resumo em portugues do Brasil, 2 a 6 linhas comecando com '• ', ate 700 caracteres",
  "doomfist": true/false,
  "doomfist_resumo": "o que muda para o Doomfist, em portugues do Brasil"
}}

Regras:
- "relevante" = true so para noticia de verdade: nota de patch, balanceamento, heroi/mapa/modo novo,
  temporada, evento, atualizacao dos desenvolvedores, correcao de bug importante, mudanca no Stadium,
  campeonato grande, recompensas (drops). Memes, fan art, reclamacao, clipes e posts de humor = false.
  Video curto promocional do YouTube so e relevante se anunciar algo concreto.
- "doomfist" = true so se a publicacao falar CONCRETAMENTE do Doomfist: mudanca de habilidade ou
  numero, poderes/itens do Stadium do Doomfist, skin, bug, counter, meta ou dica de jogador pro.
  Uma simples citacao de passagem nao conta.
- "doomfist_resumo": liste cada mudanca com o numero antes -> depois (ex.: "Seismic Slam: dano 50 -> 60"),
  inclua comentarios dos desenvolvedores se houver e separe o que e do 5v5 e do Stadium.
  Ate 1200 caracteres. Deixe "" se "doomfist" for false.
- Nao invente nada que nao esteja no texto. Mantenha nomes de habilidades em ingles.

Fonte: {fonte}
Titulo: {titulo}
Texto:
{texto}
"""


def gemini(prompt):
    chave = os.environ.get('GEMINI_API_KEY', '').strip()
    if not chave:
        return None
    corpo = json.dumps({
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.2},
    }).encode()
    for modelo in list(MODELOS):
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent'
        for tentativa in range(3):
            try:
                resp = json.loads(baixar(url, corpo, {'Content-Type': 'application/json',
                                                      'x-goog-api-key': chave}, timeout=120))
                texto = resp['candidates'][0]['content']['parts'][0]['text']
                return json.loads(texto)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    log(f'  Gemini: limite gratis por minuto, esperando 65 s (tentativa {tentativa + 1})')
                    time.sleep(65)
                    continue
                if e.code in (400, 404):
                    log(f'  Gemini: modelo {modelo} indisponivel ({e.code}), tentando o proximo')
                    MODELOS.remove(modelo)
                    break
                log(f'  Gemini: erro HTTP {e.code}: {e.read()[:200]!r}')
                break
            except (KeyError, IndexError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as e:
                log(f'  Gemini: resposta inesperada ({e.__class__.__name__}), tentando de novo')
                time.sleep(5)
    return None


def sem_ia(item):
    """Plano B quando nao ha chave ou a IA falha: palavra-chave e trecho do texto."""
    texto = item['texto']
    oficial = item['fonte']['id'] in ('forum', 'youtube')
    m = re.search(r'doom ?fist', texto, re.I) or re.search(r'doom ?fist', item['titulo'], re.I)
    trecho = ''
    if m and m.string is texto:
        ini = max(0, m.start() - 80)
        trecho = '…' + texto[ini:ini + 1100].strip() + '…'
    elif m:
        trecho = texto[:1100]
    return {
        'relevante': oficial,
        'titulo': item['titulo'],
        'resumo': (texto[:500] + '…') if len(texto) > 500 else texto,
        'doomfist': bool(m),
        'doomfist_resumo': trecho,
    }


def analisar(item, usar_ia=True):
    if usar_ia and os.environ.get('GEMINI_API_KEY'):
        r = gemini(PROMPT.format(fonte=item['fonte']['nome'], titulo=item['titulo'],
                                 texto=item['texto'][:120000]))
        time.sleep(7)  # camada gratis: ~10 pedidos por minuto
        if isinstance(r, dict) and 'relevante' in r:
            return r
        log('  IA indisponivel para este item, usando o filtro por palavra-chave')
    return sem_ia(item)


# ---------------------------------------------------------------- Discord

def postar(webhook, titulo, link, texto, rodape, cor, data, seco):
    embed = {
        'title': titulo[:256], 'url': link, 'description': texto[:4000], 'color': cor,
        'footer': {'text': rodape}, 'timestamp': data.isoformat(),
    }
    if seco or not webhook:
        log(f'  [seco] {rodape} | {titulo}\n{texto[:600]}\n')
        return True
    corpo = json.dumps({'username': 'KIRA • Notícias OW', 'embeds': [embed],
                        'allowed_mentions': {'parse': []}}).encode()
    for _ in range(4):
        try:
            baixar(webhook + ('&' if '?' in webhook else '?') + 'wait=true', corpo,
                   {'Content-Type': 'application/json'})
            return True
        except urllib.error.HTTPError as e:
            if e.code == 429:
                espera = float(json.loads(e.read() or b'{}').get('retry_after', 2))
                time.sleep(espera + 0.5)
                continue
            log(f'  Discord recusou ({e.code}): {e.read()[:200]!r}')
            return False
    return False


# ---------------------------------------------------------------- estado

def carregar_estado():
    try:
        with open(ESTADO, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {'semeado': False, 'vistos': {}}


def salvar_estado(est):
    # guarda so os 3000 mais recentes para o arquivo nao crescer para sempre
    est['vistos'] = dict(sorted(est['vistos'].items(), key=lambda kv: kv[1])[-3000:])
    with open(ESTADO, 'w', encoding='utf-8') as f:
        json.dump(est, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- principal

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seco', action='store_true')
    ap.add_argument('--sem-ia', action='store_true')
    ap.add_argument('--postar-ultimo', type=int, default=0)
    a = ap.parse_args()

    wh_ow = os.environ.get('WEBHOOK_OVERWATCH', '').strip()
    wh_doom = os.environ.get('WEBHOOK_DOOMFIST', '').strip()
    usar_ia = not a.sem_ia
    if usar_ia and not os.environ.get('GEMINI_API_KEY'):
        log('Sem GEMINI_API_KEY: rodando com o filtro por palavra-chave')
    if not a.seco and not (wh_ow and wh_doom):
        log('Faltam WEBHOOK_OVERWATCH e/ou WEBHOOK_DOOMFIST: rodando em modo seco')
        a.seco = True

    est = carregar_estado()
    todos = []
    for fonte in FONTES:
        try:
            itens = ler_fonte(fonte)
            log(f'{fonte["nome"]}: {len(itens)} itens')
            todos += itens
        except Exception as e:  # uma fonte fora do ar nao pode derrubar as outras
            log(f'{fonte["nome"]}: pulada ({e.__class__.__name__}: {e})')

    agora = datetime.now(timezone.utc)
    if a.postar_ultimo:
        patches = sorted([i for i in todos if i['fonte']['id'] == 'forum' and 'patch' in i['titulo'].lower()],
                         key=lambda i: i['data'])
        novos = patches[-a.postar_ultimo:]
        log(f'Modo teste: postando {len(novos)} nota(s) de patch mesmo que ja vista(s)')
    else:
        novos = [i for i in todos if i['id'] not in est['vistos']]
        if not est.get('semeado'):
            # primeira execucao: marca tudo como visto para nao despejar o historico no canal
            for i in novos:
                est['vistos'][i['id']] = i['data'].isoformat()
            est['semeado'] = True
            if not a.seco:
                salvar_estado(est)
            log(f'Primeira execucao: {len(novos)} itens marcados como ja vistos. Nada postado.')
            return 0
        recentes = [i for i in novos if agora - i['data'] <= IDADE_MAXIMA]
        for i in novos:
            if i not in recentes:
                est['vistos'][i['id']] = i['data'].isoformat()
        novos = recentes

    novos.sort(key=lambda i: i['data'])
    log(f'{len(novos)} item(ns) novo(s) para analisar')
    postados = doom = 0
    for item in novos:
        log(f'- {item["fonte"]["nome"]}: {item["titulo"][:90]}')
        r = analisar(item, usar_ia)
        ok = True
        if r.get('relevante'):
            ok = postar(wh_ow, r.get('titulo') or item['titulo'], item['link'], r.get('resumo', ''),
                        item['fonte']['nome'], item['fonte']['cor'], item['data'], a.seco)
            postados += ok
        else:
            log('  nao e noticia, fica fora do #overwatch-news')
        if r.get('doomfist') and (r.get('doomfist_resumo') or '').strip():
            ok = postar(wh_doom, '👊 Doomfist: ' + (r.get('titulo') or item['titulo']), item['link'],
                        r['doomfist_resumo'], item['fonte']['nome'], COR_DOOMFIST, item['data'], a.seco) and ok
            doom += 1
        if ok and not a.postar_ultimo:
            est['vistos'][item['id']] = item['data'].isoformat()
            if not a.seco:
                salvar_estado(est)  # salva a cada item: se cair no meio, nao repete
    if not a.seco:
        salvar_estado(est)
    log(f'Fim: {postados} no #overwatch-news, {doom} no #doomfist')
    return 0


if __name__ == '__main__':
    sys.exit(main())
