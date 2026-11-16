"""Testes do robô da fila com um Discord de mentira (não acessa a internet).

Rodar:  python -m unittest fila/test_fila.py -v
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fila  # noqa: E402
from discord_api import DiscordError  # noqa: E402

EPOCH = fila.EPOCH_DISCORD
G = "1365461838594314380"
BOT, DONO, ALUNO1, ALUNO2, DUO1, MOD = "900", "100", "201", "202", "301", "400"
R_ALUNO, R_DUO, R_MOD = "r-aluno", "r-duo", "r-mod"
TG = {"fila": "t-fila", "duo": "t-duo", "feito": "t-feito", "codigo": "t-codigo", "livepix": "t-livepix", "fora": "t-fora"}
CANAIS = {"forum": "c-forum", "membros": "c-membros", "duo": "c-duo", "manual": "c-manual",
          "fila": "c-fila", "painel": "c-painel", "publico": "c-publico"}
CFG = {"guild_id": G, "fuso_horas": -3, "lista_quinta_hora": 17, "cota": {"aluno": 1, "duo": 2, "staff": 99},
       "duo_por_etiqueta": False, "roles": {"aluno": [R_ALUNO], "duo": [R_DUO], "moderador": R_MOD},
       "canais": CANAIS, "tags": TG, "rss_patch": ""}


def sf(dt, n=0):
    return str(((int(dt.timestamp() * 1000) - EPOCH) << 22) + n)


class FakeDiscord:
    def __init__(self, agora):
        self.agora = agora
        self.seq = 0
        self.membros = {
            DONO: {"user": {"id": DONO, "username": "kira"}, "roles": []},
            ALUNO1: {"user": {"id": ALUNO1, "username": "rls"}, "roles": [R_ALUNO]},
            ALUNO2: {"user": {"id": ALUNO2, "username": "gui"}, "roles": [R_ALUNO]},
            DUO1: {"user": {"id": DUO1, "username": "doom"}, "roles": [R_DUO]},
            MOD: {"user": {"id": MOD, "username": "mod"}, "roles": [R_MOD]},
            BOT: {"user": {"id": BOT, "username": "fila", "bot": True}, "roles": []},
        }
        self.fios = {}
        self.msgs = {c: [] for c in CANAIS.values()}
        self.reacoes = {}  # (canal, msg, emoji) -> [user ids]
        self.dms = []
        self.pins = []

    def novo_id(self, dt=None):
        self.seq += 1
        return sf(dt or self.agora, self.seq)

    # helpers do cenário
    def postar_pedido(self, dono, nome, texto, quando, tags=("t-fila",)):
        fid = self.novo_id(quando)
        self.fios[fid] = {"id": fid, "name": nome, "owner_id": dono, "parent_id": "c-forum",
                          "applied_tags": list(tags), "thread_metadata": {"archived": False, "locked": False}}
        self.msgs[fid] = [{"id": fid, "author": {"id": dono}, "content": texto,
                           "timestamp": quando.isoformat(), "reactions": []}]
        return fid

    def escrever(self, canal, autor, texto, quando):
        m = {"id": self.novo_id(quando), "author": {"id": autor}, "content": texto,
             "timestamp": quando.isoformat(), "reactions": []}
        self.msgs.setdefault(canal, []).append(m)
        return m

    def reagir(self, canal, msg_id, emoji, usuario):
        self.reacoes.setdefault((canal, msg_id, emoji), []).append(usuario)

    def resumo_reacoes(self, canal, m):
        out = []
        for (c, mid, emoji), users in self.reacoes.items():
            if c == canal and mid == m["id"] and users:
                out.append({"emoji": {"name": emoji}, "count": len(users), "me": BOT in users})
        return out

    # API
    def me(self):
        return {"id": BOT, "username": "fila"}

    def guild(self, g):
        return {"id": G, "owner_id": DONO, "name": "KIRA"}

    def members(self, g):
        return list(self.membros.values())

    def member(self, g, u):
        return self.membros.get(u)

    def active_threads(self, g):
        return [dict(f) for f in self.fios.values() if not f["thread_metadata"]["archived"]]

    def archived_threads(self, c, before=None):
        return {"threads": [dict(f) for f in self.fios.values() if f["thread_metadata"]["archived"]], "has_more": False}

    def messages(self, c, limit=100, before=None):
        lst = []
        for m in self.msgs.get(c, []):
            m = dict(m)
            m["reactions"] = self.resumo_reacoes(c, m)
            lst.append(m)
        return list(reversed(lst))[:limit]

    def reaction_users(self, c, m, emoji):
        return [{"id": u} for u in self.reacoes.get((c, m, emoji), [])]

    def send(self, c, content=None, embeds=None, mencionar=None):
        m = {"id": self.novo_id(), "author": {"id": BOT, "bot": True}, "content": content or "",
             "embeds": embeds or [], "timestamp": self.agora.isoformat(), "reactions": []}
        if c in self.fios:
            if self.fios[c]["thread_metadata"]["locked"]:
                raise DiscordError(403, "locked", "POST", c)
            self.fios[c]["thread_metadata"]["archived"] = False
        self.msgs.setdefault(c, []).append(m)
        return dict(m)

    def edit_message(self, c, mid, content=None, embeds=None):
        for m in self.msgs[c]:
            if m["id"] == mid:
                if content is not None:
                    m["content"] = content
                if embeds is not None:
                    m["embeds"] = embeds
                return dict(m)
        raise DiscordError(404, "msg", "PATCH", mid)

    def react(self, c, m, emoji):
        self.reagir(c, m, emoji, BOT)

    def unreact(self, c, m, emoji, usuario):
        self.reacoes[(c, m, emoji)].remove(usuario)

    def pin(self, c, m):
        self.pins.append(m)

    def edit_channel(self, c, **campos):
        f = self.fios[c]
        if f["thread_metadata"]["archived"] and campos.get("archived") is not False and set(campos) - {"archived", "locked"}:
            raise DiscordError(400, "thread arquivada", "PATCH", c)
        for k, v in campos.items():
            if k in ("archived", "locked"):
                f["thread_metadata"][k] = v
            else:
                f[k] = v
        return dict(f)

    def create_forum_post(self, forum, nome, content, tags):
        fid = self.novo_id()
        self.fios[fid] = {"id": fid, "name": nome, "owner_id": BOT, "parent_id": forum, "applied_tags": list(tags),
                          "thread_metadata": {"archived": False, "locked": False}}
        self.msgs[fid] = [{"id": fid, "author": {"id": BOT, "bot": True}, "content": content,
                           "timestamp": self.agora.isoformat(), "reactions": []}]
        return dict(self.fios[fid])

    def dm(self, u, content):
        self.dms.append((u, content))


def rodar(api, agora, rss=None):
    api.agora = agora
    r = fila.Robo(api, CFG, agora=agora, rss=rss, log=lambda *_: None)
    r.rodar()
    return r


def ultima(api, canal):
    return api.msgs[canal][-1]["content"]


class TestUtilidades(unittest.TestCase):
    def test_codigo(self):
        self.assertEqual(fila.achar_codigo("Código: abc123 doom"), "ABC123")
        self.assertEqual(fila.achar_codigo("cod 8RSFXP"), "8RSFXP")
        self.assertEqual(fila.achar_codigo("ANÁLISE W6EWZ0 Doomfist Ouro 2"), "W6EWZ0")
        self.assertIsNone(fila.achar_codigo("cheguei no top500 ontem, MESTRE"))
        self.assertIsNone(fila.achar_codigo("https://youtu.be/AB12CD"))
        self.assertEqual(fila.achar_codigo("Código do replay: QWERTY"), "QWERTY")

    def test_battletag(self):
        self.assertEqual(fila.achar_battletag("meu btag é Kira#11234, tank"), "Kira#11234")
        self.assertEqual(fila.achar_battletag("JoãoZ#1234"), "JoãoZ#1234")
        self.assertIsNone(fila.achar_battletag("#1234"))

    def test_autorizo(self):
        self.assertTrue(fila.tem_autorizo("AUTORIZO sim"))
        self.assertFalse(fila.tem_autorizo("não autorizado"))


class TestFila(unittest.TestCase):
    def setUp(self):
        # segunda, 16/11/2026 15:00 BRT
        self.t0 = datetime(2026, 11, 16, 18, 0, tzinfo=timezone.utc)
        self.api = FakeDiscord(self.t0)

    def texto_ok(self, cod="AB12CD"):
        return f"Código: {cod}\nDoomfist, Junkertown\nDiamante 3\nmorro depois do soco\nAutorizo"

    def test_pedido_valido_entra_na_fila(self):
        fid = self.api.postar_pedido(ALUNO1, "RLS · Doomfist · Diamante 3", self.texto_ok(), self.t0)
        rodar(self.api, self.t0 + timedelta(minutes=5))
        f = self.api.fios[fid]
        self.assertEqual(f["applied_tags"], ["t-fila"])
        self.assertTrue(f["name"].startswith("NOV · "))
        self.assertIn("1º", ultima(self.api, fid))
        self.assertIn("fila:ok", ultima(self.api, fid))
        # segunda rodada não repete nada
        n = len(self.api.msgs[fid])
        rodar(self.api, self.t0 + timedelta(minutes=10))
        self.assertEqual(len(self.api.msgs[fid]), n)

    def test_segundo_pedido_do_mes_e_recusado(self):
        self.api.postar_pedido(ALUNO1, "a", self.texto_ok(), self.t0)
        f2 = self.api.postar_pedido(ALUNO1, "b", self.texto_ok("ZX98YU"), self.t0 + timedelta(minutes=1))
        rodar(self.api, self.t0 + timedelta(minutes=5))
        self.assertEqual(self.api.fios[f2]["applied_tags"], ["t-fora"])
        self.assertTrue(self.api.fios[f2]["thread_metadata"]["locked"])
        self.assertIn("fila:cota", ultima(self.api, f2))

    def test_duo_tem_duas_e_passa_na_frente(self):
        a = self.api.postar_pedido(ALUNO1, "a", self.texto_ok(), self.t0)
        d1 = self.api.postar_pedido(DUO1, "d1", self.texto_ok("DD11EE"), self.t0 + timedelta(minutes=1))
        d2 = self.api.postar_pedido(DUO1, "d2", self.texto_ok("DD22EE"), self.t0 + timedelta(minutes=2))
        d3 = self.api.postar_pedido(DUO1, "d3", self.texto_ok("DD33EE"), self.t0 + timedelta(minutes=3))
        r = rodar(self.api, self.t0 + timedelta(minutes=5))
        self.assertIn("t-duo", self.api.fios[d1]["applied_tags"])
        self.assertIn("t-duo", self.api.fios[d2]["applied_tags"])
        self.assertEqual(self.api.fios[d3]["applied_tags"], ["t-fora"])
        ordem = [p.id for p in r.ordem_fila()]
        self.assertEqual(ordem, [d1, d2, a])

    def test_sem_autorizo_pede_e_depois_aceita(self):
        fid = self.api.postar_pedido(ALUNO2, "gui", "Código: GG55HH Doomfist", self.t0)
        rodar(self.api, self.t0 + timedelta(minutes=5))
        self.assertIn("fila:faltou", ultima(self.api, fid))
        n = len(self.api.msgs[fid])
        rodar(self.api, self.t0 + timedelta(minutes=10))
        self.assertEqual(len(self.api.msgs[fid]), n, "não pode repetir o aviso sem a pessoa mandar nada")
        self.api.escrever(fid, ALUNO2, "Autorizo!", self.t0 + timedelta(minutes=11))
        rodar(self.api, self.t0 + timedelta(minutes=15))
        self.assertIn("fila:ok", ultima(self.api, fid))

    def test_nao_membro_e_recusado(self):
        self.api.membros["555"] = {"user": {"id": "555", "username": "x"}, "roles": []}
        fid = self.api.postar_pedido("555", "x", self.texto_ok(), self.t0)
        rodar(self.api, self.t0 + timedelta(minutes=5))
        self.assertIn("fila:sem-assinatura", ultima(self.api, fid))

    def test_quinta_lista_e_check_marca_analisado(self):
        a = self.api.postar_pedido(ALUNO1, "RLS · Doomfist", self.texto_ok(), self.t0)
        rodar(self.api, self.t0 + timedelta(minutes=5))
        # quinta 19/11, 16:55 BRT: ainda não posta
        quinta = datetime(2026, 11, 19, 19, 55, tzinfo=timezone.utc)
        rodar(self.api, quinta)
        self.assertFalse(any("fila:lista" in m["content"] for m in self.api.msgs["c-fila"]))
        # 17:05 BRT: posta topo + 1 item, com ✅ e 🔁 já reagidos pelo robô
        rodar(self.api, quinta + timedelta(minutes=10))
        conteudos = [m["content"] for m in self.api.msgs["c-fila"]]
        self.assertTrue(any("fila:lista:2026-11-19" in c for c in conteudos))
        item = next(m for m in self.api.msgs["c-fila"] if f"fila:item:{a}" in m["content"])
        self.assertIn("AB12CD", item["content"])
        self.assertIn(BOT, self.api.reacoes[("c-fila", item["id"], "✅")])
        self.assertIn("fila:aviso-quinta", ultima(self.api, "c-membros"))
        # não posta de novo na rodada seguinte
        n = len(self.api.msgs["c-fila"])
        rodar(self.api, quinta + timedelta(minutes=15))
        self.assertEqual(len(self.api.msgs["c-fila"]), n)
        # o KIRA clica ✅
        self.api.reagir("c-fila", item["id"], "✅", DONO)
        rodar(self.api, quinta + timedelta(hours=3))
        f = self.api.fios[a]
        self.assertEqual(f["applied_tags"], ["t-feito"])
        self.assertTrue(f["thread_metadata"]["archived"])
        self.assertIn("fila:feito", ultima(self.api, a))
        self.assertIn("quinta, 19/11", ultima(self.api, a))
        self.assertEqual(self.api.dms[0][0], ALUNO1)
        self.assertTrue(item["content"].startswith("✅ **FEITO**"))
        self.assertNotIn(DONO, self.api.reacoes[("c-fila", item["id"], "✅")])
        # painel conta o analisado
        painel = self.api.msgs["c-painel"][-1]["embeds"][0]
        self.assertIn("Analisados em novembro (1)", painel["description"])

    def test_check_de_quem_nao_e_staff_nao_vale(self):
        a = self.api.postar_pedido(ALUNO1, "x", self.texto_ok(), self.t0)
        rodar(self.api, self.t0 + timedelta(minutes=5))
        self.api.reagir(a, a, "✅", ALUNO1)
        rodar(self.api, self.t0 + timedelta(minutes=10))
        self.assertNotIn("t-feito", self.api.fios[a]["applied_tags"])

    def test_mod_marca_pelo_proprio_post(self):
        a = self.api.postar_pedido(ALUNO1, "x", self.texto_ok(), self.t0)
        rodar(self.api, self.t0 + timedelta(minutes=5))
        self.api.reagir(a, a, "✅", MOD)
        rodar(self.api, self.t0 + timedelta(minutes=10))
        self.assertEqual(self.api.fios[a]["applied_tags"], ["t-feito"])

    def test_codigo_venceu_e_codigo_novo(self):
        a = self.api.postar_pedido(ALUNO1, "x", self.texto_ok(), self.t0)
        rodar(self.api, self.t0 + timedelta(minutes=5))
        self.api.reagir(a, a, "🔁", DONO)
        rodar(self.api, self.t0 + timedelta(minutes=10))
        self.assertIn("t-codigo", self.api.fios[a]["applied_tags"])
        self.assertIn("fila:codigo", ultima(self.api, a))
        r = rodar(self.api, self.t0 + timedelta(minutes=12))
        self.assertEqual(r.ordem_fila(), [], "esperando código não entra na lista")
        self.api.escrever(a, ALUNO1, "novo: Código XY77ZZ", self.t0 + timedelta(minutes=13))
        r = rodar(self.api, self.t0 + timedelta(minutes=15))
        self.assertNotIn("t-codigo", self.api.fios[a]["applied_tags"])
        self.assertIn("XY77ZZ", ultima(self.api, a))
        self.assertEqual(r.ordem_fila()[0].codigo_atual()[0], "XY77ZZ")

    def test_aviso_de_patch(self):
        a = self.api.postar_pedido(ALUNO1, "x", self.texto_ok(), self.t0)
        rodar(self.api, self.t0 + timedelta(minutes=5))
        patch = self.t0 + timedelta(days=1)
        rss = ("<rss><channel><item><title>Overwatch Retail Patch Notes – November 17, 2026</title>"
               f"<pubDate>{patch.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate></item>"
               "<item><title>Evento novo</title><pubDate>Tue, 17 Nov 2026 20:00:00 +0000</pubDate></item>"
               "</channel></rss>")
        rodar(self.api, patch + timedelta(hours=1), rss=rss)
        self.assertIn("fila:patch", ultima(self.api, a))
        n = len(self.api.msgs[a])
        rodar(self.api, patch + timedelta(hours=2), rss=rss)
        self.assertEqual(len(self.api.msgs[a]), n, "um aviso por patch")

    def test_comando_livepix_vai_primeiro(self):
        a = self.api.postar_pedido(ALUNO1, "x", self.texto_ok(), self.t0)
        d = self.api.postar_pedido(DUO1, "d", self.texto_ok("DD11EE"), self.t0)
        rodar(self.api, self.t0 + timedelta(minutes=5))
        cmd = self.api.escrever("c-fila", DONO, "!livepix LP12AB Fulano Doomfist Ouro 2", self.t0 + timedelta(minutes=6))
        r = rodar(self.api, self.t0 + timedelta(minutes=10))
        lp = [f for f in self.api.fios.values() if f["owner_id"] == BOT]
        self.assertEqual(len(lp), 1)
        self.assertEqual(lp[0]["name"], "💸 NOV · Fulano · Doomfist · Ouro 2")
        self.assertEqual([p.id for p in r.ordem_fila()], [lp[0]["id"], d, a])
        self.assertIn(BOT, self.api.reacoes[("c-fila", cmd["id"], "🤖")])
        rodar(self.api, self.t0 + timedelta(minutes=15))
        self.assertEqual(len([f for f in self.api.fios.values() if f["owner_id"] == BOT]), 1, "comando só uma vez")

    def test_assinatura_acabou_sai_da_fila(self):
        a = self.api.postar_pedido(ALUNO1, "x", self.texto_ok(), self.t0)
        rodar(self.api, self.t0 + timedelta(minutes=5))
        self.api.membros[ALUNO1]["roles"] = []
        rodar(self.api, self.t0 + timedelta(minutes=10))
        self.assertEqual(self.api.fios[a]["applied_tags"], ["t-fora"])
        self.assertIn("fila:saiu", ultima(self.api, a))

    def test_duo_boas_vindas_battletag_e_painel(self):
        self.api.escrever("c-duo", DUO1, "Doom#11234 tank", self.t0)
        rodar(self.api, self.t0 + timedelta(minutes=5))
        self.assertTrue(any("fila:boas-vindas" in m["content"] for m in self.api.msgs["c-duo"]))
        painel = self.api.msgs["c-painel"][-1]["embeds"][0]
        self.assertIn("Doom#11234", painel["description"])
        self.assertIn(f"<@{ALUNO1}>", painel["description"])  # ainda não pediu
        self.assertIn("duo:" + DUO1, painel["footer"]["text"])
        rodar(self.api, self.t0 + timedelta(minutes=10))
        self.assertEqual(sum("fila:boas-vindas" in m["content"] for m in self.api.msgs["c-duo"]), 1)
        self.assertEqual(len(self.api.msgs["c-painel"]), 1, "painel é editado, não repostado")

    def test_staff_post_entra_sem_cota(self):
        a = self.api.postar_pedido(DONO, "teste", "Código: KK11LL", self.t0)
        b = self.api.postar_pedido(DONO, "teste2", "Código: KK22LL", self.t0 + timedelta(minutes=1))
        rodar(self.api, self.t0 + timedelta(minutes=5))
        self.assertIn("fila:ok", ultima(self.api, a))
        self.assertIn("fila:ok", ultima(self.api, b))


if __name__ == "__main__":
    unittest.main()


class FakeSetup:
    """Discord de mentira só para o modo montar."""
    def __init__(self, admin=False):
        self.n = 0
        self.canais = [{"id": "cat-info", "type": 4, "name": "📌 INFORMAÇÕES", "position": 0,
                        "permission_overwrites": [{"id": G, "type": 0, "allow": "0", "deny": str(1 << 11)}]}]
        perm = (1 << 3) if admin else __import__("setup").CONVITE
        self.lista_roles = [{"id": G, "name": "@everyone", "permissions": "0", "position": 0},
                      {"id": "r-bot", "name": "Fila", "permissions": str(perm), "position": 1, "managed": True},
                      {"id": R_ALUNO, "name": "Aluno Foguete", "permissions": "0", "position": 2, "managed": True}]
        self.msgs = {}
        self.chamadas = []

    def _id(self):
        self.n += 1
        return f"novo{self.n}"

    def me(self):
        return {"id": BOT, "username": "fila"}

    def member(self, g, u):
        return {"user": {"id": u}, "roles": ["r-bot"]} if u == BOT else None

    def roles(self, g):
        return [dict(r) for r in self.lista_roles]

    def channels(self, g):
        return [dict(c) for c in self.canais]

    def create_role(self, g, **k):
        r = {"id": self._id(), **k}
        self.lista_roles.append(r)
        return r

    def create_channel(self, g, **k):
        c = {"id": self._id(), **k}
        if c.get("type") == 15:
            c["available_tags"] = [dict(t, id=self._id()) for t in k.get("available_tags", [])]
        self.canais.append(c)
        self.chamadas.append(("create", k.get("name")))
        return dict(c)

    def edit_channel(self, cid, **k):
        c = next(c for c in self.canais if c["id"] == cid)
        for o in k.get("permission_overwrites", []):
            assert int(o["allow"]) >= 0 and int(o["deny"]) >= 0
        c.update(k)
        if "available_tags" in k:
            c["available_tags"] = [dict(t, id=t.get("id") or self._id()) for t in k["available_tags"]]
        self.chamadas.append(("edit", c["name"]))
        return dict(c)

    def messages(self, c, limit=50, before=None):
        return list(reversed(self.msgs.get(c, [])))

    def send(self, c, content=None, embeds=None, mencionar=None):
        m = {"id": self._id(), "author": {"id": BOT}, "content": content, "embeds": embeds or []}
        self.msgs.setdefault(c, []).append(m)
        return m

    def edit_message(self, c, mid, content=None, embeds=None):
        m = next(m for m in self.msgs[c] if m["id"] == mid)
        m["embeds"] = embeds
        return m

    def pin(self, c, m):
        pass


class TestMontar(unittest.TestCase):
    def cfg(self):
        import copy
        c = copy.deepcopy(CFG)
        c["roles"] = {"aluno": [R_ALUNO], "duo": [R_DUO], "moderador": ""}
        c["canais"] = {k: "" for k in CANAIS}
        c["tags"] = {k: "" for k in TG}
        return c

    def test_monta_e_roda_de_novo_sem_duplicar(self):
        import setup
        api = FakeSetup()
        novo = setup.montar(api, self.cfg(), log=lambda *_: None)
        self.assertTrue(all(novo["canais"].values()))
        self.assertTrue(all(novo["tags"].values()))
        self.assertTrue(novo["roles"]["moderador"])
        criados = [n for t, n in api.chamadas if t == "create"]
        self.assertEqual(len(criados), 9)  # 2 categorias + 7 canais
        n_msgs = sum(len(v) for v in api.msgs.values())
        self.assertEqual(n_msgs, 4)
        # 2ª vez: só ajusta
        api.chamadas.clear()
        novo2 = setup.montar(api, novo, log=lambda *_: None)
        self.assertFalse([n for t, n in api.chamadas if t == "create"])
        self.assertEqual(sum(len(v) for v in api.msgs.values()), 4)
        self.assertEqual(novo2["tags"], novo["tags"])
        # o canal público herda o "só leitura" da categoria
        pub = next(c for c in api.canais if c["id"] == novo["canais"]["publico"])
        todos = next(o for o in pub["permission_overwrites"] if o["id"] == G)
        self.assertTrue(int(todos["deny"]) & (1 << 11))

    def test_sem_cargos_nao_monta(self):
        import setup
        c = self.cfg()
        c["roles"] = {"aluno": [], "duo": [], "moderador": ""}
        with self.assertRaises(SystemExit):
            setup.montar(FakeSetup(), c, log=lambda *_: None)
