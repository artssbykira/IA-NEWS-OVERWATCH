"""Robô da fila de análise de replay do KIRA.

Roda no GitHub Actions a cada ~5 min e usa o próprio Discord como banco de dados:
as etiquetas dos posts do fórum dizem o estado de cada pedido e as mensagens do
robô terminam com uma marca "-# 🤖 fila:<tipo>".

O que ele faz em cada rodada:
  1. comandos da staff no 📥fila (!fila, !livepix, !ajuda)
  2. confere pedido novo no fórum (é membro? tem cota no mês? mandou código e "Autorizo"?)
  3. ✅ / 🔁 da staff (no 📥fila ou no próprio post) → marca analisado / pede código novo
  4. código novo mandado pela pessoa → anota; patch novo do jogo → avisa quem está na fila
  5. quinta às 17h → posta a fila do dia no 📥fila
  6. Duo Meteoro: dá boas-vindas e junta os BattleTags
  7. atualiza o 📊painel do mês
"""
import re
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import textos as T
from discord_api import DiscordError

EPOCH_DISCORD = 1420070400000
OK, VOLTA, ROBO = "✅", "🔁", "🤖"
RE_MARCA = re.compile(r"fila:([a-z\-]+)(?::(\S+))?")
RE_URL = re.compile(r"https?://\S+|<[^>]*>")
RE_COD_ROTULO = re.compile(
    r"c[oó]d(?:igo)?(?:\s+d[oe]\s+replay)?\s*[:=\-–]?\s*\**([A-Za-z0-9]{6})\**(?![A-Za-z0-9])", re.I)
RE_TOKEN6 = re.compile(r"(?<![A-Za-z0-9#@/])([A-Za-z0-9]{6})(?![A-Za-z0-9#])")
RE_BATTLETAG = re.compile(r"(?<![\w#])([^\W\d_][^\W_]{2,11}#\d{4,6})(?!\d)")
RE_MES_TITULO = re.compile(r"^\W*(" + "|".join(T.MES_CURTO) + r")\b", re.I)
RE_MENCAO = re.compile(r"<@!?(\d+)>")


# ------------------------------------------------------------------ utilidades
def hora_do_id(snowflake):
    return datetime.fromtimestamp(((int(snowflake) >> 22) + EPOCH_DISCORD) / 1000, tz=timezone.utc)


def quando(msg):
    if msg.get("timestamp"):
        return datetime.fromisoformat(msg["timestamp"])
    return hora_do_id(msg["id"])


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn").lower()


def achar_codigo(texto):
    if not texto:
        return None
    limpo = RE_URL.sub(" ", texto)
    m = RE_COD_ROTULO.search(limpo)
    if m:
        return m.group(1).upper()
    for tok in RE_TOKEN6.findall(limpo):
        if tok.upper() == tok and any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok):
            return tok
    return None


def tem_autorizo(texto):
    return "autorizo" in sem_acento(texto)


def achar_battletag(texto):
    m = RE_BATTLETAG.search(RE_URL.sub(" ", texto or ""))
    return m.group(1) if m else None


def marcas_de(msg):
    tipos = []
    textos_msg = [msg.get("content") or ""]
    for e in msg.get("embeds") or []:
        textos_msg.append((e.get("footer") or {}).get("text") or "")
    for t in textos_msg:
        for m in RE_MARCA.finditer(t):
            tipos.append((m.group(1), m.group(2)))
    return tipos


def escapar(texto):
    return (texto or "").replace("[", "(").replace("]", ")").replace("*", "").replace("_", " ")


# --------------------------------------------------------------------- pedido
class Pedido:
    def __init__(self, fio, robo, msgs=None):
        self.robo = robo
        self.id = fio["id"]
        self.nome = fio.get("name") or ""
        self.dono = fio.get("owner_id")
        self.criado = hora_do_id(self.id)
        self.tags = set(fio.get("applied_tags") or [])
        md = fio.get("thread_metadata") or {}
        self.arquivado = bool(md.get("archived"))
        self.trancado = bool(md.get("locked"))
        self.arquivado_em = datetime.fromisoformat(md["archive_timestamp"]) if md.get("archive_timestamp") else None
        self._msgs = msgs

    def tem(self, chave):
        return self.robo.TG.get(chave) in self.tags

    def msgs(self):
        if self._msgs is None:
            self._msgs = sorted(self.robo.api.messages(self.id, limit=100), key=lambda m: int(m["id"]))
        return self._msgs

    def do_robo(self, m):
        return m["author"]["id"] == self.robo.bot_id

    def marcas(self):
        return [(m, tipo) for m in self.msgs() if self.do_robo(m) for tipo, _ in marcas_de(m)]

    def estado(self):
        if self.tem("feito"):
            return "feito"
        if self.tem("fora"):
            return "fora"
        tipos = {t for _, t in self.marcas()}
        if tipos & {"ok", "livepix"}:
            return "codigo" if self.tem("codigo") else "fila"
        if "faltou" in tipos:
            return "faltou"
        return "novo"

    def livepix(self):
        # a etiqueta basta; só olha as mensagens se elas já foram baixadas (evita uma chamada por post antigo)
        return self.tem("livepix") or (self._msgs is not None and any(t == "livepix" for _, t in self.marcas()))

    def pessoa(self):
        """Quem recebe o aviso: o dono do post ou, no LivePix, quem foi marcado."""
        if self.dono and self.dono != self.robo.bot_id:
            return self.dono
        for m in self.msgs():
            if self.do_robo(m) and any(t == "livepix" for t, _ in marcas_de(m)):
                achado = RE_MENCAO.search(m.get("content") or "")
                return achado.group(1) if achado else None
        return None

    def codigo_atual(self):
        """Último código mandado (pelo dono, pela staff ou no post do LivePix). -> (código, mensagem)"""
        for m in reversed(self.msgs()):
            autor = m["author"]["id"]
            if self.do_robo(m):
                if not any(t == "livepix" for t, _ in marcas_de(m)):
                    continue
            elif autor != self.dono and not self.robo.eh_staff(autor):
                continue
            cod = achar_codigo(m.get("content") or "")
            if cod:
                return cod, m
        return None, None

    def chave_ordem(self):
        grupo = 0 if self.livepix() else 1 if self.tem("duo") else 2
        return (grupo, int(self.id))

    def link(self):
        return f"https://discord.com/channels/{self.robo.g}/{self.id}"


# ----------------------------------------------------------------------- robô
class Robo:
    def __init__(self, api, cfg, agora=None, rss=None, log=print):
        self.api = api
        self.cfg = cfg
        self.log = log
        self.agora = agora or datetime.now(timezone.utc)
        self.tz = timezone(timedelta(hours=cfg.get("fuso_horas", -3)))
        self.local = self.agora.astimezone(self.tz)
        self.rss = rss
        self.g = cfg["guild_id"]
        self.C = cfg["canais"]
        self.TG = cfg["tags"]
        self.R = cfg["roles"]
        self.forcar_lista = False
        self.acoes = []

    # ------------------------------------------------------------ carregar
    def carregar(self):
        self.bot_id = self.api.me()["id"]
        self.dono_servidor = self.api.guild(self.g)["owner_id"]
        self.cache_membro = {}
        try:
            for m in self.api.members(self.g):
                self.cache_membro[m["user"]["id"]] = m
            self.lista_membros_ok = True
        except DiscordError as e:
            self.log(f"aviso: não deu pra listar os membros ({e.status}); ligar 'Server Members Intent' no portal")
            self.lista_membros_ok = False
        self.threads = self.carregar_threads()
        self.msgs_fila = sorted(self.api.messages(self.C["fila"], limit=100), key=lambda m: int(m["id"]))
        self.patch_data = self.ultimo_patch()

    def carregar_threads(self):
        forum = self.C["forum"]
        fios = [t for t in self.api.active_threads(self.g) if t.get("parent_id") == forum]
        vistos = {t["id"] for t in fios}
        limite = self.agora - timedelta(days=75)
        antes = None
        for _ in range(30):
            r = self.api.archived_threads(forum, before=antes)
            lote = r.get("threads") or []
            for t in lote:
                if t["id"] not in vistos:
                    fios.append(t)
                    vistos.add(t["id"])
            if not r.get("has_more") or not lote:
                break
            antes = lote[-1]["thread_metadata"]["archive_timestamp"]
            if datetime.fromisoformat(antes) < limite:
                break
        return [Pedido(t, self) for t in fios]

    def ultimo_patch(self):
        url = self.cfg.get("rss_patch")
        texto = self.rss
        if texto is None and url:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (fila-kira)"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    texto = r.read().decode("utf-8", "replace")
            except Exception as e:
                self.log(f"aviso: RSS de patch indisponível ({e})")
                return None
        if not texto:
            return None
        datas = []
        try:
            for item in ElementTree.fromstring(texto).iter("item"):
                titulo = (item.findtext("title") or "").lower()
                if "patch notes" not in titulo:
                    continue
                d = parsedate_to_datetime(item.findtext("pubDate") or "")
                if self.agora - timedelta(days=30) <= d <= self.agora:
                    datas.append(d)
        except Exception as e:
            self.log(f"aviso: RSS de patch ilegível ({e})")
            return None
        return max(datas) if datas else None

    # ------------------------------------------------------------- pessoas
    def membro(self, uid):
        if uid not in self.cache_membro:
            self.cache_membro[uid] = self.api.member(self.g, uid)
        return self.cache_membro[uid]

    def eh_staff(self, uid):
        if uid == self.dono_servidor:
            return True
        mod = self.R.get("moderador")
        m = self.membro(uid) if mod else None
        return bool(m and mod in (m.get("roles") or []))

    def nivel(self, uid, tags=()):
        m = self.membro(uid)
        if not m:
            return None
        cargos = set(m.get("roles") or [])
        if cargos & set(self.R.get("duo") or []):
            return "duo"
        if cargos & set(self.R.get("aluno") or []):
            if self.cfg.get("duo_por_etiqueta") and self.TG.get("duo") in tags:
                return "duo"
            return "aluno"
        return None

    def nome_de(self, uid):
        m = self.membro(uid) or {}
        u = m.get("user") or {}
        return m.get("nick") or u.get("global_name") or u.get("username") or "?"

    def cota(self, nivel):
        return (self.cfg.get("cota") or {}).get(nivel, 1)

    def mes(self, dt):
        loc = dt.astimezone(self.tz)
        return loc.year, loc.month

    def data(self, dt=None):
        return (dt or self.agora).astimezone(self.tz).strftime("%d/%m")

    # ------------------------------------------------------------- escrita
    def registrar(self, texto):
        self.acoes.append(texto)
        self.log("• " + texto)

    def _msg_local(self, retorno, canal, content, embeds=None):
        msg = dict(retorno or {})
        msg.setdefault("id", str(((int(self.agora.timestamp() * 1000) - EPOCH_DISCORD) << 22) + len(self.acoes)))
        msg.setdefault("channel_id", canal)
        msg["author"] = {"id": self.bot_id, "bot": True}
        msg["content"] = content
        msg["embeds"] = embeds or []
        msg["timestamp"] = self.agora.isoformat()
        msg.setdefault("reactions", [])
        return msg

    def responder(self, p, texto, pingar=None):
        if p.arquivado and p.trancado:
            self.editar_fio(p, archived=False)
        mencionar = {"parse": [], "users": [pingar]} if pingar and pingar != self.bot_id else None
        r = self.api.send(p.id, texto, mencionar=mencionar)
        p.msgs().append(self._msg_local(r, p.id, texto))
        p.arquivado = False

    def editar_fio(self, p, **campos):
        if p.arquivado and "archived" not in campos:
            campos["archived"] = False
        self.api.edit_channel(p.id, **campos)
        if "applied_tags" in campos:
            p.tags = set(campos["applied_tags"])
        if "name" in campos:
            p.nome = campos["name"]
        if "archived" in campos:
            p.arquivado = campos["archived"]
            if campos["archived"]:
                p.arquivado_em = self.agora
        if "locked" in campos:
            p.trancado = campos["locked"]

    def reacao_da_staff(self, canal, msg, emoji):
        for r in msg.get("reactions") or []:
            if (r.get("emoji") or {}).get("name") != emoji:
                continue
            if r.get("count", 0) <= (1 if r.get("me") else 0):
                return None
            for u in self.api.reaction_users(canal, msg["id"], emoji):
                if u["id"] != self.bot_id and self.eh_staff(u["id"]):
                    return u["id"]
        return None

    def consumir(self, canal, msg, emoji, usuario):
        try:
            self.api.unreact(canal, msg["id"], emoji, usuario)
        except DiscordError as e:
            self.log(f"aviso: não tirei a reação {emoji} ({e.status})")
        for r in msg.get("reactions") or []:
            if (r.get("emoji") or {}).get("name") == emoji:
                r["count"] = max(0, r.get("count", 1) - 1)

    # ------------------------------------------------------------- rodada
    def rodar(self):
        self.carregar()
        self.comandos()
        for p in list(self.threads):
            try:
                self.processar(p)
            except DiscordError as e:
                self.log(f"ERRO no post {p.id} ({p.nome}): {e}")
        self.reacoes_fila()
        self.lista_de_quinta()
        duo = self.duo()
        self.painel(duo)
        self.log(f"rodada ok: {len(self.threads)} posts, {len(self.acoes)} ações")

    def processar(self, p):
        if p.tem("feito") or p.tem("fora"):
            return
        e = p.estado()
        if e in ("novo", "faltou"):
            self.validar(p)
            return
        if not p.livepix() and not self.eh_staff(p.dono) and self.nivel(p.dono, p.tags) is None:
            self.recusar(p, T.saiu(p.dono), "assinatura acabou")
            return
        self.reacoes_no_post(p)
        if p.estado() in ("fila", "codigo"):
            self.codigo_novo(p)
        if p.estado() == "fila":
            self.aviso_patch(p)

    # ------------------------------------------------------------- pedidos
    def validar(self, p):
        dono = p.dono
        if dono == self.bot_id:
            return
        staff = self.eh_staff(dono)
        nivel = "staff" if staff else self.nivel(dono, p.tags)
        if nivel is None:
            self.recusar(p, T.sem_assinatura(dono), "sem assinatura")
            return
        if p.estado() == "novo" and not staff:
            usados = [q for q in self.threads
                      if q.dono == dono and q.id != p.id and int(q.id) < int(p.id)
                      and self.mes(q.criado) == self.mes(p.criado) and not q.tem("fora")]
            limite = self.cota(nivel)
            if len(usados) >= limite:
                mes = T.MESES[self.mes(p.criado)[1] - 1]
                self.recusar(p, T.cota(dono, nivel, mes, limite), f"cota de {mes}")
                return
        do_dono = [m for m in p.msgs() if m["author"]["id"] == dono]
        codigo, _ = p.codigo_atual()
        autorizo = staff or any(tem_autorizo(m.get("content")) for m in do_dono)
        faltam = []
        if not codigo:
            faltam.append(T.FALTA_CODIGO)
        if not autorizo:
            faltam.append(T.FALTA_AUTORIZO)
        if faltam:
            ultimo_dono = max((int(m["id"]) for m in do_dono), default=0)
            ultimo_aviso = max((int(m["id"]) for m, t in p.marcas() if t == "faltou"), default=0)
            if ultimo_aviso > ultimo_dono:
                return
            self.responder(p, T.faltou(dono, faltam), pingar=dono)
            self.registrar(f"pedido incompleto: {p.nome}")
            return
        tags = (p.tags - {self.TG["fila"], self.TG["codigo"], self.TG["fora"], self.TG["feito"]}) | {self.TG["fila"]}
        if nivel == "duo":
            tags.add(self.TG["duo"])
        nome = p.nome
        if not RE_MES_TITULO.match(nome):
            nome = f"{T.MES_CURTO[self.mes(p.criado)[1] - 1]} · {nome}"
        self.editar_fio(p, applied_tags=sorted(tags), name=nome[:100])
        posicao = 1 + sum(1 for q in self.threads
                          if q.id != p.id and q.estado() == "fila" and q.chave_ordem() < p.chave_ordem())
        self.responder(p, T.aceito(dono, posicao, nivel, codigo), pingar=dono)
        self.registrar(f"pedido aceito ({posicao}º): {p.nome}")

    def recusar(self, p, texto, motivo):
        self.editar_fio(p, applied_tags=[self.TG["fora"]])
        self.responder(p, texto, pingar=p.dono)
        self.editar_fio(p, archived=True, locked=True)
        self.registrar(f"pedido recusado ({motivo}): {p.nome}")

    def reacoes_no_post(self, p):
        msgs = p.msgs()
        if not msgs or msgs[0]["id"] != p.id:
            return
        inicio = msgs[0]
        quem = self.reacao_da_staff(p.id, inicio, OK)
        if quem:
            self.marcar_feito(p)
            self.consumir(p.id, inicio, OK, quem)
            return
        quem = self.reacao_da_staff(p.id, inicio, VOLTA)
        if quem and p.estado() == "fila":
            self.marcar_codigo(p)
            self.consumir(p.id, inicio, VOLTA, quem)

    def itens_da_fila(self, fio_id):
        return [m for m in self.msgs_fila
                if m["author"]["id"] == self.bot_id and ("item", fio_id) in marcas_de(m)]

    def marcar_feito(self, p):
        if p.tem("feito"):
            return
        self.editar_fio(p, applied_tags=sorted((p.tags - {self.TG["fila"], self.TG["codigo"]}) | {self.TG["feito"]}))
        pessoa = p.pessoa()
        dia, data = T.DIAS[self.local.weekday()], self.data()
        self.responder(p, T.feito(pessoa, dia, data), pingar=pessoa)
        if pessoa:
            try:
                self.api.dm(pessoa, T.feito_dm(dia, data))
            except DiscordError as e:
                self.log(f"aviso: DM não foi ({e.status})")
        self.editar_fio(p, archived=True)
        hora = self.local.strftime("%d/%m %H:%M")
        for item in self.itens_da_fila(p.id):
            if not (item.get("content") or "").startswith("✅ **FEITO**"):
                novo = T.item_feito(item["content"], hora)
                self.api.edit_message(self.C["fila"], item["id"], content=novo)
                item["content"] = novo
        self.registrar(f"analisado: {p.nome}")

    def marcar_codigo(self, p):
        if p.tem("codigo"):
            return
        self.editar_fio(p, applied_tags=sorted(p.tags | {self.TG["codigo"]}))
        pessoa = p.pessoa()
        self.responder(p, T.codigo_venceu(pessoa), pingar=pessoa)
        for item in self.itens_da_fila(p.id):
            if not (item.get("content") or "").startswith(("✅ **FEITO**", "🔁 **CÓDIGO")):
                novo = T.item_codigo(item["content"])
                self.api.edit_message(self.C["fila"], item["id"], content=novo)
                item["content"] = novo
        self.registrar(f"código venceu: {p.nome}")

    def codigo_novo(self, p):
        codigo, msg = p.codigo_atual()
        if not msg or p.do_robo(msg):
            return
        ultimo_robo = max((int(m["id"]) for m in p.msgs() if p.do_robo(m)), default=0)
        if int(msg["id"]) <= ultimo_robo:
            return
        if p.tem("codigo"):
            self.editar_fio(p, applied_tags=sorted(p.tags - {self.TG["codigo"]}))
        pessoa = p.pessoa()
        self.responder(p, T.codigo_novo(pessoa, codigo), pingar=pessoa)
        self.registrar(f"código novo ({codigo}): {p.nome}")

    def aviso_patch(self, p):
        if not self.patch_data:
            return
        _, msg = p.codigo_atual()
        hora_codigo = quando(msg) if msg else p.criado
        if self.patch_data <= hora_codigo:
            return
        if any(t == "patch" and quando(m) > self.patch_data for m, t in p.marcas()):
            return
        pessoa = p.pessoa()
        self.responder(p, T.patch(pessoa, self.data(self.patch_data)), pingar=pessoa)
        self.registrar(f"aviso de patch: {p.nome}")

    def ordem_fila(self):
        return sorted((p for p in self.threads if p.estado() == "fila"), key=Pedido.chave_ordem)

    # ------------------------------------------------------- canal 📥fila
    def comandos(self):
        for m in self.msgs_fila:
            if m["author"]["id"] == self.bot_id or m["author"].get("bot"):
                continue
            texto = (m.get("content") or "").strip()
            if not texto.startswith("!"):
                continue
            if any((r.get("emoji") or {}).get("name") == ROBO and r.get("me") for r in m.get("reactions") or []):
                continue
            if not self.eh_staff(m["author"]["id"]):
                continue
            cmd = texto.split()[0].lower()
            if cmd == "!fila":
                self.forcar_lista = True
            elif cmd == "!livepix":
                self.cmd_livepix(texto)
            elif cmd in ("!ajuda", "!help"):
                self.api.send(self.C["fila"], T.AJUDA)
            else:
                continue
            self.api.react(self.C["fila"], m["id"], ROBO)
            m.setdefault("reactions", []).append({"emoji": {"name": ROBO}, "count": 1, "me": True})
            self.registrar(f"comando {cmd}")

    def cmd_livepix(self, texto):
        partes = texto.split()[1:]
        codigo = None
        if partes and re.fullmatch(r"[A-Za-z0-9]{6}", partes[0]):
            codigo = partes.pop(0).upper()
        else:
            for i, t in enumerate(partes):
                if re.fullmatch(r"[A-Za-z0-9]{6}", t) and any(c.isdigit() for c in t):
                    codigo = partes.pop(i).upper()
                    break
        if not codigo:
            self.api.send(self.C["fila"], T.LIVEPIX_SEM_CODIGO)
            return
        pessoa, nick = None, None
        if partes and RE_MENCAO.fullmatch(partes[0]):
            pessoa = RE_MENCAO.fullmatch(partes.pop(0)).group(1)
            nick = self.nome_de(pessoa)
        elif partes:
            nick = partes.pop(0)
        heroi = partes.pop(0) if partes else ""
        rank = " ".join(partes)
        nick = nick or "LivePix"
        titulo = " · ".join(x for x in ["💸 " + T.MES_CURTO[self.local.month - 1], nick, heroi, rank] if x)
        conteudo = T.livepix_post(codigo, nick, pessoa, self.data())
        fio = self.api.create_forum_post(self.C["forum"], titulo, conteudo, [self.TG["livepix"], self.TG["fila"]])
        fio = dict(fio or {})
        fio.setdefault("name", titulo)
        fio["owner_id"] = self.bot_id
        fio["applied_tags"] = [self.TG["livepix"], self.TG["fila"]]
        inicio = self._msg_local({"id": fio["id"]}, fio["id"], conteudo)
        self.threads.append(Pedido(fio, self, msgs=[inicio]))

    def reacoes_fila(self):
        por_id = {p.id: p for p in self.threads}
        for item in self.msgs_fila:
            if item["author"]["id"] != self.bot_id:
                continue
            fios = [v for t, v in marcas_de(item) if t == "item"]
            if not fios or fios[0] not in por_id:
                continue
            p = por_id[fios[0]]
            try:
                quem = self.reacao_da_staff(self.C["fila"], item, OK)
                if quem:
                    if not p.tem("feito"):
                        self.marcar_feito(p)
                    self.consumir(self.C["fila"], item, OK, quem)
                    continue
                quem = self.reacao_da_staff(self.C["fila"], item, VOLTA)
                if quem:
                    if p.estado() == "fila":
                        self.marcar_codigo(p)
                    self.consumir(self.C["fila"], item, VOLTA, quem)
            except DiscordError as e:
                self.log(f"ERRO na reação do item {item['id']}: {e}")

    def lista_de_quinta(self):
        hoje = self.local.date()
        chave = hoje.isoformat()
        automatico = not self.forcar_lista
        if automatico:
            if self.local.weekday() != 3 or self.local.hour < self.cfg.get("lista_quinta_hora", 17):
                return
            if any(("lista", chave) in marcas_de(m) for m in self.msgs_fila if m["author"]["id"] == self.bot_id):
                return
        ordem = self.ordem_fila()
        esperando = sum(1 for p in self.threads if p.estado() == "codigo")
        dia = T.DIAS[self.local.weekday()]
        topo = T.lista_topo(dia, self.data(), len(ordem), esperando, chave)
        self.msgs_fila.append(self._msg_local(self.api.send(self.C["fila"], topo), self.C["fila"], topo))
        for i, p in enumerate(ordem, 1):
            rotulo = "💸 LivePix · " if p.livepix() else "☄️ Duo · " if p.tem("duo") else ""
            codigo, _ = p.codigo_atual()
            texto = T.lista_item(i, rotulo, p.nome, codigo, self.data(p.criado), p.link(), p.id)
            r = self.api.send(self.C["fila"], texto)
            self.msgs_fila.append(self._msg_local(r, self.C["fila"], texto))
            self.api.react(self.C["fila"], r["id"], OK)
            self.api.react(self.C["fila"], r["id"], VOLTA)
        if automatico and ordem:
            ultima = (hoje + timedelta(days=7)).month != hoje.month
            self.api.send(self.C["membros"], T.aviso_membros(len(ordem), self.C["forum"], ultima, T.MESES[hoje.month - 1]))
        self.registrar(f"fila de {dia} postada ({len(ordem)} pedidos)")

    # ------------------------------------------------------------ duo + painel
    def mensagem_do_painel(self):
        for m in self.api.messages(self.C["painel"], limit=30):
            if m["author"]["id"] == self.bot_id and ("painel", None) in marcas_de(m):
                return m
        return None

    def duo(self):
        if not self.R.get("duo") or not self.lista_membros_ok:
            return None
        duos = [m for m in self.cache_membro.values()
                if m and set(m.get("roles") or []) & set(self.R["duo"]) and not (m.get("user") or {}).get("bot")]
        battletags = {}
        for m in sorted(self.api.messages(self.C["duo"], limit=100), key=lambda x: int(x["id"])):
            if (m.get("author") or {}).get("bot"):
                continue
            bt = achar_battletag(m.get("content"))
            if bt:
                battletags[m["author"]["id"]] = bt
        self.painel_antigo = self.mensagem_do_painel()
        conhecidos = set()
        if self.painel_antigo:
            rodape = ((self.painel_antigo.get("embeds") or [{}])[0].get("footer") or {}).get("text") or ""
            achado = re.search(r"duo:([\d,]*)", rodape)
            conhecidos = set(filter(None, achado.group(1).split(","))) if achado else set()
        for d in duos:
            uid = d["user"]["id"]
            if uid not in conhecidos:
                self.api.send(self.C["duo"], T.boas_vindas_duo(uid), mencionar={"parse": [], "users": [uid]})
                self.registrar(f"boas-vindas Duo: {self.nome_de(uid)}")
        return [(d["user"]["id"], battletags.get(d["user"]["id"])) for d in duos]

    def painel(self, duo):
        ano, mes = self.local.year, self.local.month
        nome_mes = T.MESES[mes - 1]

        def linha(p, sufixo=""):
            rotulo = "💸 " if p.livepix() else "☄️ " if p.tem("duo") else ""
            return f"• {rotulo}[{escapar(p.nome)}]({p.link()}){sufixo}"

        def secao(titulo, linhas, limite=12):
            if not linhas:
                return f"**{titulo} (0)**"
            extra = f"\n… e mais {len(linhas) - limite}" if len(linhas) > limite else ""
            return f"**{titulo} ({len(linhas)})**\n" + "\n".join(linhas[:limite]) + extra

        fila = [linha(p, f" · desde {self.data(p.criado)}") for p in self.ordem_fila()]
        esperando = [linha(p) for p in self.threads if p.estado() == "codigo"]
        incompletos = [linha(p) for p in self.threads if p.estado() == "faltou"]
        feitos = sorted((p for p in self.threads if p.tem("feito") and p.arquivado_em
                         and self.mes(p.arquivado_em) == (ano, mes)), key=lambda p: p.arquivado_em)
        feitos = [linha(p, f" · {self.data(p.arquivado_em)}") for p in feitos]
        partes = [secao("⏳ Na fila", fila), secao("🔁 Esperando código novo", esperando),
                  secao("⚠️ Pedido incompleto", incompletos), secao(f"🎥 Analisados em {nome_mes}", feitos)]

        if self.lista_membros_ok:
            faltam = []
            for uid, m in self.cache_membro.items():
                if not m or (m.get("user") or {}).get("bot") or uid == self.dono_servidor:
                    continue
                nivel = self.nivel(uid)
                if not nivel:
                    continue
                usados = sum(1 for q in self.threads
                             if q.dono == uid and self.mes(q.criado) == (ano, mes) and not q.tem("fora"))
                sobra = self.cota(nivel) - usados
                if sobra > 0:
                    faltam.append(f"<@{uid}>" + (f" (Duo, falta {sobra})" if nivel == "duo" else ""))
            titulo = f"**🙋 Membros que ainda não pediram em {nome_mes} ({len(faltam)})**"
            extra = f" … e mais {len(faltam) - 40}" if len(faltam) > 40 else ""
            partes.append(titulo + ("\n" + " · ".join(faltam[:40]) + extra if faltam else ""))
        else:
            partes.append("**🙋 Membros que ainda não pediram:** ligar o *Server Members Intent* do robô no portal do Discord.")

        ids_duo = []
        if duo is not None:
            linhas = []
            for uid, bt in duo:
                ids_duo.append(uid)
                linhas.append(f"<@{uid}> · {bt}" if bt else f"<@{uid}> · ❗ sem BattleTag")
            partes.append(secao("☄️ Duo Meteoro: BattleTags", linhas, limite=40))

        descricao = "\n\n".join(partes)
        if len(descricao) > 4000:
            descricao = descricao[:3990] + "\n…"
        rodape = "Atualiza sozinho a cada ~5 min · fila:painel · duo:" + ",".join(ids_duo)
        embed = T.painel(f"📊 ANÁLISES DE {nome_mes.upper()}/{ano}", descricao, rodape)
        embed["timestamp"] = self.agora.isoformat()

        antigo = getattr(self, "painel_antigo", None)
        if antigo is None and not hasattr(self, "painel_antigo"):
            antigo = self.mensagem_do_painel()
        if antigo:
            velho = (antigo.get("embeds") or [{}])[0]
            igual = (velho.get("description") == descricao and velho.get("title") == embed["title"]
                     and (velho.get("footer") or {}).get("text") == rodape)
            ultima = datetime.fromisoformat(velho["timestamp"]) if velho.get("timestamp") else None
            if igual and ultima and self.agora - ultima < timedelta(minutes=60):
                return
            self.api.edit_message(self.C["painel"], antigo["id"], embeds=[embed])
        else:
            r = self.api.send(self.C["painel"], embeds=[embed])
            try:
                self.api.pin(self.C["painel"], r["id"])
            except DiscordError as e:
                self.log(f"aviso: não fixei o painel ({e.status})")
