#!/usr/bin/env python3
"""
Robo de noticias de Overwatch para o Discord do KIRA.

A cada execucao:
  1. le as fontes (forum da Blizzard, OW Cavalry, Google Noticias, YouTube, Reddit)
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
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from imagens import achar_imagem

AQUI = os.path.dirname(os.path.abspath(__file__))
ESTADO = os.path.join(AQUI, 'vistos.json')
UA = 'Mozilla/5.0 (compatible; KiraNewsBot/1.0; +https://linktr.ee/kira_owbr)'

# Nao posta nada mais antigo que isso, mesmo que nunca tenha sido visto.
IDADE_MAXIMA = timedelta(days=3)

# 'max' = quantos itens novos no maximo por rodada (Google Noticias traz dezenas).
# 'oficial' = no plano B sem IA, posta mesmo sem saber se e relevante.
def gnews(busca, hl, gl, lang):
    # "Overwatch" sozinho tambem e palavra comum em ingles (vigilancia): traz drone, K-pop...
    # Por isso a busca amarra em termos do jogo.
    return (f'https://news.google.com/rss/search?q={urllib.parse.quote(busca)}'
            f'&hl={hl}&gl={gl}&ceid={gl}:{lang}')
FONTES = [
    {'id': 'forum', 'nome': 'Blizzard - Anuncios oficiais', 'cor': 0xF99E1A, 'oficial': True,
     'url': 'https://us.forums.blizzard.com/en/overwatch/c/announcements/5.rss'},
    {'id': 'blizzard-tracker', 'nome': 'Blizzard - Devs no forum', 'cor': 0xF99E1A,
     'url': 'https://us.forums.blizzard.com/en/overwatch/g/blizzard-tracker/posts.rss'},
    {'id': 'owcavalry', 'nome': 'OW Cavalry', 'cor': 0x1185FE, 'oficial': True,
     'url': 'https://bsky.app/profile/owcavalry.com/rss'},
    {'id': 'youtube', 'nome': 'YouTube - Overwatch', 'cor': 0xFF0000, 'oficial': True,
     'url': 'https://www.youtube.com/feeds/videos.xml?channel_id=UClOf1XXinvZsy4wKPAkro2A'},
    {'id': 'gnews-en', 'nome': 'Google Noticias', 'cor': 0x4285F4, 'max': 6,
     'url': gnews('"Overwatch" (Blizzard OR hero OR patch OR season OR Stadium OR esports OR "World Cup") when:2d',
                  'en-US', 'US', 'en')},
    {'id': 'gnews-pt', 'nome': 'Google Noticias (BR)', 'cor': 0x4285F4, 'max': 4,
     'url': gnews('Overwatch (Blizzard OR herói OR temporada OR patch) when:2d', 'pt-BR', 'BR', 'pt-419')},
    {'id': 'gnews-doom', 'nome': 'Google Noticias', 'cor': 0x4285F4, 'max': 4,
     'url': gnews('Doomfist Overwatch when:7d', 'en-US', 'US', 'en')},
    # O Reddit as vezes recusa (429/403). Quando falha, o robo so pula a fonte.
    {'id': 'reddit-ow', 'nome': 'Reddit - r/Overwatch', 'cor': 0xFF4500,
     'url': 'https://www.reddit.com/r/Overwatch/top/.rss?t=day&limit=10'},
    {'id': 'reddit-comp', 'nome': 'Reddit - r/Competitiveoverwatch', 'cor': 0xFF4500,
     'url': 'https://www.reddit.com/r/Competitiveoverwatch/top/.rss?t=day&limit=10'},
    {'id': 'reddit-doom', 'nome': 'Reddit - r/DoomfistMains', 'cor': 0xFF4500,
     'url': 'https://www.reddit.com/r/DoomfistMains/top/.rss?t=day&limit=10'},
]

COR_DOOMFIST = 0x8E44AD
MODELOS = [m.strip() for m in os.environ.get('GEMINI_MODELO', '').split(',') if m.strip()] or \
          ['gemini-flash-latest', 'gemini-flash-lite-latest']


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
            desc = it.findtext('description') or ''
            img = re.search(r'<img[^>]+src="([^"]+)"', desc)
            itens.append({
                'id': (it.findtext('guid') or link).strip(),
                'titulo': (it.findtext('title') or '').strip(),
                'link': link,
                'data': data_iso(it.findtext('pubDate')),
                'texto': limpar_html(desc),
                'imagem_feed': html.unescape(img.group(1)) if img else '',
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
                'imagem_feed': html.unescape((en.find('m:thumbnail', ns).get('url') if en.find('m:thumbnail', ns) is not None
                                              else en.find('m:group/m:thumbnail', ns).get('url') if en.find('m:group/m:thumbnail', ns) is not None
                                              else '')),
            })
    for it in itens:
        it['fonte'] = fonte
        if not it['titulo']:  # Bluesky nao tem titulo: usa o comeco do post
            it['titulo'] = it['texto'].split('\n')[0][:90]
    return itens


def palavras(titulo):
    t = re.sub(r'\s+-\s+[^-]+$', '', titulo.lower())  # tira " - Nome do Site" do Google Noticias
    return {w for w in re.findall(r'[a-z0-9À-ÿ]+', t) if len(w) > 2}


def parecido(titulo, recentes):
    """Mesma noticia vinda de outra fonte? Compara as palavras do titulo."""
    a = palavras(titulo)
    if len(a) < 3:
        return False
    for r in recentes:
        b = palavras(r['titulo_original'])
        if b and len(a & b) / len(a | b) >= 0.55:
            return True
    return False


# ---------------------------------------------------------------- IA (Gemini gratis)

PROMPT = """Voce e o editor do Discord do KIRA, streamer brasileiro de Overwatch que joga de Doomfist
(Top 500 no 5v5 e um dos melhores Doomfist do modo Stadium).

Leia a publicacao abaixo e responda APENAS com um JSON neste formato:
{{
  "relevante": true/false,
  "titulo": "titulo curto em portugues do Brasil, ate 90 caracteres",
  "resumo": "resumo em portugues do Brasil, 2 a 6 linhas comecando com '• ', ate 700 caracteres",
  "doomfist": true/false,
  "doomfist_resumo": "o que muda para o Doomfist, em portugues do Brasil",
  "ja_postado": true/false
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
- "ja_postado" = true se o ASSUNTO desta publicacao ja estiver na lista "Ja postado recentemente"
  abaixo (a mesma noticia vinda de outro site ou rede). Nesse caso nada sera postado.
- Nao invente nada que nao esteja no texto. Se so houver a manchete (Google Noticias), resuma em
  1 ou 2 linhas apenas com o que a manchete diz. Mantenha nomes de habilidades em ingles.

Ja postado recentemente:
{recentes}

Fonte: {fonte}
Titulo: {titulo}
Texto:
{texto}
"""


def modelos_disponiveis(chave):
    """Pergunta ao Google quais modelos 'flash' existem hoje (os nomes mudam: 2.0/2.5 foram desligados em out/2026)."""
    try:
        d = json.loads(baixar('https://generativelanguage.googleapis.com/v1beta/models?pageSize=200', None,
                              {'x-goog-api-key': chave}, timeout=20))
    except Exception as e:
        log(f'  Gemini: nao consegui listar os modelos ({e.__class__.__name__}), usando a lista fixa')
        return list(MODELOS)
    nomes = [m['name'].split('/', 1)[1] for m in d.get('models', [])
             if 'generateContent' in m.get('supportedGenerationMethods', []) and 'flash' in m['name']
             and not re.search(r'image|tts|audio|live|exp|preview|thinking|8b', m['name'])]

    def ordem(n):
        num = re.search(r'(\d+(?:\.\d+)?)', n)
        return (0 if n.endswith('flash-latest') else 2 if 'lite' in n else 1, -float(num.group(1)) if num else 0)
    nomes.sort(key=ordem)
    log(f'  Gemini: modelos disponiveis {nomes[:5]}')
    return nomes or list(MODELOS)


PRAZO = {'fim': None}   # a rodada para de chamar a IA depois disso (sobra tempo para salvar o que foi postado)


def gemini(prompt):
    chave = os.environ.get('GEMINI_API_KEY', '').strip()
    if not chave or getattr(gemini, 'esgotado', False):
        return None
    if not getattr(gemini, 'modelos', None):
        gemini.modelos = modelos_disponiveis(chave)
    corpo = json.dumps({
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.2},
    }).encode()
    for modelo in list(gemini.modelos):
        if PRAZO['fim'] and time.time() > PRAZO['fim']:
            return None
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent'
        for tentativa in range(2):
            try:
                resp = json.loads(baixar(url, corpo, {'Content-Type': 'application/json',
                                                      'x-goog-api-key': chave}, timeout=45))
                texto = resp['candidates'][0]['content']['parts'][0]['text']
                gemini.limites = 0  # so conta 429 seguidos
                return json.loads(texto)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    gemini.limites = getattr(gemini, 'limites', 0) + 1
                    if gemini.limites >= 3:  # cota gratis do dia acabou: nao adianta esperar
                        log('  Gemini: cota gratis esgotada nesta rodada, seguindo com o filtro por palavra-chave')
                        gemini.esgotado = True
                        return None
                    if tentativa == 0:
                        log(f'  Gemini ({modelo}): limite gratis por minuto, esperando 30 s')
                        time.sleep(30)
                        continue
                if e.code in (400, 404):
                    log(f'  Gemini: modelo {modelo} nao existe mais ({e.code}), tirando da lista')
                    gemini.modelos.remove(modelo)
                else:
                    log(f'  Gemini ({modelo}): erro {e.code}, tentando o proximo modelo')
                break
            except (KeyError, IndexError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as e:
                log(f'  Gemini ({modelo}): {e.__class__.__name__}, tentando o proximo modelo')
                break
    return None


def sem_ia(item):
    """Plano B quando nao ha chave ou a IA falha: palavra-chave e trecho do texto."""
    texto = item['texto']
    oficial = bool(item['fonte'].get('oficial'))
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


def analisar(item, recentes, usar_ia=True):
    if usar_ia and os.environ.get('GEMINI_API_KEY'):
        lista = '\n'.join(f'- {r["titulo"]}' for r in recentes[-40:]) or '(nada)'
        r = gemini(PROMPT.format(fonte=item['fonte']['nome'], titulo=item['titulo'],
                                 texto=item['texto'][:120000], recentes=lista))
        time.sleep(7)  # camada gratis: ~10 pedidos por minuto
        if isinstance(r, dict) and 'relevante' in r:
            return r
        log('  IA indisponivel para este item, usando o filtro por palavra-chave')
    return sem_ia(item)


# ---------------------------------------------------------------- Discord

def postar(webhook, titulo, link, texto, rodape, cor, data, seco, imagem=None):
    embed = {
        'title': titulo[:256], 'url': link, 'description': texto[:4000], 'color': cor,
        'footer': {'text': rodape}, 'timestamp': data.isoformat(),
    }
    if imagem:
        embed['image'] = {'url': imagem}
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
    est.setdefault('fontes', [])
    est.setdefault('recentes', [])

    def visto(i):
        est['vistos'][i['id']] = i['data'].isoformat()

    if a.postar_ultimo:
        patches = sorted([i for i in todos if i['fonte']['id'] == 'forum' and 'patch' in i['titulo'].lower()],
                         key=lambda i: i['data'])
        novos = patches[-a.postar_ultimo:]
        log(f'Modo teste: postando {len(novos)} nota(s) de patch mesmo que ja vista(s)')
    else:
        # Fonte que aparece pela primeira vez: marca o que ela ja tem como visto, para nao
        # despejar o historico no canal. Vale para a primeira execucao e para fontes novas.
        for fid in sorted({i['fonte']['id'] for i in todos} - set(est['fontes'])):
            da_fonte = [i for i in todos if i['fonte']['id'] == fid]
            for i in da_fonte:
                visto(i)
            est['fontes'].append(fid)
            log(f'Fonte nova "{fid}": {len(da_fonte)} itens marcados como ja vistos (nada postado)')

        novos = [i for i in todos if i['id'] not in est['vistos']]
        for i in [i for i in novos if agora - i['data'] > IDADE_MAXIMA]:
            visto(i)  # velho demais para ser noticia
        novos = [i for i in novos if agora - i['data'] <= IDADE_MAXIMA]

        # Google Noticias traz dezenas por dia: fica so com os mais novos de cada fonte
        filtrados = []
        for fonte in FONTES:
            da_fonte = sorted([i for i in novos if i['fonte'] is fonte], key=lambda i: i['data'], reverse=True)
            limite = fonte.get('max', 99)
            filtrados += da_fonte[:limite]
            for i in da_fonte[limite:]:
                visto(i)
        novos = filtrados

    novos.sort(key=lambda i: i['data'])
    PRAZO['fim'] = time.time() + 8 * 60
    log(f'{len(novos)} item(ns) novo(s) para analisar')
    postados = doom = repetidos = 0
    for item in novos:
        if time.time() > PRAZO['fim'] + 60:
            log('Tempo da rodada acabou: o resto fica para a proxima (nada se perde)')
            break
        log(f'- {item["fonte"]["nome"]}: {item["titulo"][:90]}')
        if not a.postar_ultimo and parecido(item['titulo'], est['recentes']):
            log('  mesma noticia ja postada por outra fonte, pulando')
            repetidos += 1
            visto(item)
            continue
        r = analisar(item, est['recentes'], usar_ia)
        if r.get('ja_postado') and not a.postar_ultimo:
            log('  a IA reconheceu como assunto ja postado, pulando')
            repetidos += 1
            visto(item)
            continue
        ok = True
        postou = False
        imagem = None
        if r.get('relevante') or r.get('doomfist'):
            imagem, link_real = achar_imagem(item)
            item['link'] = link_real or item['link']
            log(f'  imagem: {imagem or "nenhuma"}')
        if r.get('relevante'):
            ok = postar(wh_ow, r.get('titulo') or item['titulo'], item['link'], r.get('resumo', ''),
                        item['fonte']['nome'], item['fonte']['cor'], item['data'], a.seco, imagem)
            postados += ok
            postou = ok
        else:
            log('  nao e noticia, fica fora do #overwatch-news')
        if r.get('doomfist') and (r.get('doomfist_resumo') or '').strip():
            ok_doom = postar(wh_doom, '👊 Doomfist: ' + (r.get('titulo') or item['titulo']), item['link'],
                             r['doomfist_resumo'], item['fonte']['nome'], COR_DOOMFIST, item['data'], a.seco, imagem)
            ok = ok and ok_doom
            doom += ok_doom
            postou = postou or ok_doom
        if postou:
            est['recentes'] = (est['recentes'] + [{
                'titulo': r.get('titulo') or item['titulo'], 'titulo_original': item['titulo'],
                'data': item['data'].isoformat()}])[-60:]
        if ok and not a.postar_ultimo:
            visto(item)
            if not a.seco:
                salvar_estado(est)  # salva a cada item: se cair no meio, nao repete
    if not a.seco:
        salvar_estado(est)
    log(f'Fim: {postados} no #overwatch-news, {doom} no #doomfist, {repetidos} repetido(s) evitado(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
