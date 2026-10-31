"""
Acha uma imagem REAL para cada notícia (nunca gerada): a da própria matéria.

Ordem de tentativa:
  1. imagem que já vem no feed (<img> do fórum da Blizzard, media:thumbnail do Reddit/YouTube)
  2. Bluesky: imagem/cartão anexado ao post (API pública, sem login)
  3. Google Notícias: descobre o link real da matéria
  4. página da matéria: og:image / twitter:image
Se nada der certo, devolve None e a notícia sai sem imagem (como antes).
"""
import html
import json
import re
import urllib.parse
import urllib.request

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
RUINS = ('google.com/images', 'gstatic.com', 'lh3.googleusercontent.com/-', 'redditstatic.com', 'default', 'placeholder',
         'logo', 'favicon', 'sprite', 'emoji', 'avatar')


def _get(url, dados=None, cab=None, timeout=15, limite=600_000):
    req = urllib.request.Request(url, data=dados, headers={'User-Agent': UA, 'Accept-Language': 'pt-BR,en;q=0.8', **(cab or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read(limite).decode('utf-8', 'replace')


def _boa(url):
    if not url or not url.startswith('http'):
        return None
    u = html.unescape(url).strip()
    return None if any(r in u.lower() for r in RUINS) else u


def _meta(pagina):
    for prop in ('og:image:secure_url', 'og:image', 'twitter:image', 'twitter:image:src'):
        m = re.search(r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']+)' % re.escape(prop), pagina, re.I) \
            or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']%s["\']' % re.escape(prop), pagina, re.I)
        if m and _boa(m.group(1)):
            return _boa(m.group(1))
    return None


def _bluesky(link):
    m = re.search(r'bsky\.app/profile/([^/]+)/post/([^/?#]+)', link)
    if not m:
        return None
    ator, post = m.groups()
    api = 'https://public.api.bsky.app/xrpc/'
    if not ator.startswith('did:'):
        ator = json.loads(_get(api + 'com.atproto.identity.resolveHandle?handle=' + ator)[1])['did']
    uri = f'at://{ator}/app.bsky.feed.post/{post}'
    d = json.loads(_get(api + 'app.bsky.feed.getPosts?uris=' + urllib.parse.quote(uri))[1])
    emb = (d.get('posts') or [{}])[0].get('embed') or {}
    emb = emb.get('media') or emb  # post com mídia + citação
    if emb.get('images'):
        return emb['images'][0].get('fullsize') or emb['images'][0].get('thumb')
    if emb.get('thumbnail'):  # vídeo
        return emb['thumbnail']
    if (emb.get('external') or {}).get('thumb'):
        return emb['external']['thumb']
    return None


def link_real_google(link):
    """news.google.com/rss/articles/... -> URL da matéria (Google mudou o formato em 2024; precisa do batchexecute)."""
    m = re.search(r'news\.google\.com/(?:rss/)?articles/([^?/#]+)', link)
    if not m:
        return link
    gid = m.group(1)
    _, pag = _get(f'https://news.google.com/rss/articles/{gid}', limite=2_000_000)
    sg = re.search(r'data-n-a-sg="([^"]+)"', pag)
    ts = re.search(r'data-n-a-ts="([^"]+)"', pag)
    if not (sg and ts):
        return link
    req = ['Fbv4je', json.dumps(['garturlreq', [['X', 'X', ['X', 'X'], None, None, 1, 1, 'US:en', None, 1, None, None, None, None, None, 0, 1],
                                                'X', 'X', 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0], gid, int(ts.group(1)), sg.group(1)])]
    corpo = 'f.req=' + urllib.parse.quote(json.dumps([[req]]))
    _, resp = _get('https://news.google.com/_/DotsSplashUi/data/batchexecute', corpo.encode(),
                   {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'})
    m = re.search(r'\[\\"garturlres\\",\\"(.*?)\\"', resp)
    if not m:
        return link
    url = json.loads('"' + m.group(1) + '"').replace('\\/', '/')
    return re.sub(r'\\u([0-9a-fA-F]{4})', lambda x: chr(int(x.group(1), 16)), url)  # vem escapado duas vezes


def achar_imagem(item):
    """Devolve (url_da_imagem ou None, link_final_da_matéria)."""
    link = item.get('link') or ''
    try:
        if item.get('imagem_feed') and _boa(item['imagem_feed']):
            return _boa(item['imagem_feed']), link
        if 'bsky.app/' in link:
            return _bluesky(link), link
        if 'news.google.com/' in link:
            link = link_real_google(link)
            if 'news.google.com/' in link:
                return None, item.get('link')
        yt = re.search(r'(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})', link)
        if yt:  # vídeo e Short do YouTube: a capa oficial do vídeo
            return f'https://i.ytimg.com/vi/{yt.group(1)}/hqdefault.jpg', link
        final, pagina = _get(link)
        return _meta(pagina), link
    except Exception:
        return None, link
