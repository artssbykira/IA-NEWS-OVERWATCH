"""Monta (ou ajusta) a estrutura da fila no servidor e mostra um diagnóstico.

  diagnostico → só lê: cargos (incluindo os da integração do YouTube), categorias e canais
  montar      → cria o que faltar e ajusta o que existe; pode rodar de novo sem duplicar nada
"""
import textos as T
from discord_api import DiscordError

VIEW, SEND, ADD_REACTIONS = 1 << 10, 1 << 11, 1 << 6
MANAGE_MESSAGES, EMBED, ATTACH, HISTORY = 1 << 13, 1 << 14, 1 << 15, 1 << 16
MENTION_EVERYONE, EXTERNAL_EMOJIS = 1 << 17, 1 << 18
MANAGE_THREADS, SEND_IN_THREADS, PIN = 1 << 34, 1 << 38, 1 << 51

MEMBRO = VIEW | HISTORY | SEND | SEND_IN_THREADS | ADD_REACTIONS | ATTACH | EMBED | EXTERNAL_EMOJIS
STAFF = MEMBRO | MANAGE_MESSAGES | MANAGE_THREADS
ROBO = STAFF | MENTION_EVERYONE | PIN

NOMES = {
    "cat_membros": "💎 MEMBROS",
    "membros": "💬membros",
    "forum": "📼análise-de-replay",
    "duo": "☄️duo-meteoro",
    "cat_staff": "🛠️ STAFF",
    "manual": "📋manual",
    "fila": "📥fila",
    "painel": "📊painel",
    "publico": "📼como-pedir-análise",
}

ETIQUETAS = [  # chave, nome, emoji, só moderador aplica?
    ("fila", "Na fila", "⏳", False),
    ("duo", "Duo Meteoro", "☄️", True),
    ("feito", "Analisado", "🎥", True),
    ("codigo", "Código venceu", "🔁", True),
    ("livepix", "LivePix", "💸", True),
    ("fora", "Fora da fila", "🚫", True),
]


ADMIN = 1 << 3

# permissões que o convite do robô pede (o Discord só deixa o robô dar num canal o que ele mesmo tem)
CONVITE = ROBO | (1 << 4) | (1 << 28)  # + gerenciar canais + gerenciar cargos


def _ow(alvo, tipo, allow=0, deny=0):
    return {"id": alvo, "type": tipo, "allow": str(allow), "deny": str(deny)}


def permissoes_do_robo(api, g, robo, roles):
    m = api.member(g, robo) or {}
    meus = set(m.get("roles") or []) | {g}
    total = 0
    for r in roles:
        if r["id"] in meus:
            total |= int(r.get("permissions") or 0)
    return total


def diagnostico(api, cfg, log=print):
    g = cfg["guild_id"]
    me = api.me()
    guild = api.guild(g)
    log(f"servidor: {guild['name']} · dono {guild['owner_id']} · robô {me['username']} ({me['id']})")
    log("\nCARGOS (do mais alto pro mais baixo):")
    for r in sorted(api.roles(g), key=lambda r: -r["position"]):
        tags = r.get("tags") or {}
        nota = ""
        if "integration_id" in tags:
            nota = f"  ← integração {tags['integration_id']}"
        elif "bot_id" in tags:
            nota = f"  ← cargo do robô {tags['bot_id']}"
        log(f"  {r['id']}  {r['name']!r}  gerenciado={r.get('managed')}{nota}")
    canais = api.channels(g)
    log("\nCANAIS:")
    cats = {c["id"]: c for c in canais if c["type"] == 4}
    for cat in sorted(cats.values(), key=lambda c: c["position"]):
        log(f"  [{cat['id']}] {cat['name']}")
        for c in sorted((c for c in canais if c.get("parent_id") == cat["id"]), key=lambda c: c["position"]):
            log(f"      {c['id']}  tipo={c['type']}  {c['name']}")
    soltos = [c for c in canais if c["type"] != 4 and not c.get("parent_id")]
    for c in soltos:
        log(f"  (sem categoria) {c['id']}  tipo={c['type']}  {c['name']}")


def montar(api, cfg, log=print):
    g = cfg["guild_id"]
    me = api.me()
    robo = me["id"]
    roles = api.roles(g)
    canais = api.channels(g)
    aluno = list(cfg["roles"].get("aluno") or [])
    duo = list(cfg["roles"].get("duo") or [])
    if not aluno and not duo:
        raise SystemExit("Preencha roles.aluno / roles.duo no config.json (veja o diagnóstico) antes de montar.")

    # cargo Moderador (sem nenhuma permissão no servidor; só enxerga a staff)
    mod = cfg["roles"].get("moderador")
    if not mod:
        achado = next((r for r in roles if r["name"].strip().lower() in ("moderador", "moderadores", "mod", "mods")), None)
        if achado:
            mod = achado["id"]
        else:
            mod = api.create_role(g, name="Moderador", permissions="0", mentionable=False, hoist=False)["id"]
            log("criado cargo Moderador")
    cfg["roles"]["moderador"] = mod

    def achar(nome, tipo, pai=None):
        for c in canais:
            if c["name"] == nome and c["type"] == tipo and (pai is None or c.get("parent_id") == pai):
                return c
        return None

    def garantir(chave, tipo, pai=None, **campos):
        nome = NOMES[chave]
        atual = achar(nome, tipo, pai)
        if pai:
            campos["parent_id"] = pai
        if atual:
            api.edit_channel(atual["id"], **campos)
            log(f"ajustado: {nome}")
            return atual
        novo = api.create_channel(g, name=nome, type=tipo, **campos)
        canais.append(novo)
        log(f"criado: {nome}")
        return novo

    tenho = permissoes_do_robo(api, g, robo, roles)
    mascara = -1 if tenho & ADMIN else tenho
    falta = CONVITE & ~tenho if mascara != -1 else 0
    if falta:
        log(f"aviso: o robô está sem algumas permissões do convite (bits {falta}); elas ficam de fora dos canais")

    def ow(alvo, tipo, allow=0, deny=0):
        return _ow(alvo, tipo, allow & mascara, deny & mascara)

    todos = g  # o cargo @everyone tem o mesmo id do servidor
    ow_membros = ([ow(todos, 0, deny=VIEW)] + [ow(r, 0, MEMBRO) for r in aluno + duo]
                  + [ow(mod, 0, STAFF), ow(robo, 1, ROBO)])
    ow_duo = [ow(todos, 0, deny=VIEW)] + [ow(r, 0, MEMBRO) for r in duo] + [ow(mod, 0, STAFF), ow(robo, 1, ROBO)]
    ow_staff = [ow(todos, 0, deny=VIEW), ow(mod, 0, STAFF), ow(robo, 1, ROBO)]

    cat_m = garantir("cat_membros", 4, permission_overwrites=ow_membros)
    membros = garantir("membros", 0, cat_m["id"], permission_overwrites=ow_membros,
                       topic="Canal dos membros do canal no YouTube. Pedido de análise: no fórum aqui embaixo.")

    forum = achar(NOMES["forum"], 15, cat_m["id"])
    existentes = {t["name"]: t for t in (forum or {}).get("available_tags") or []}
    etiquetas = []
    for chave, nome, emoji, moderada in ETIQUETAS:
        if chave == "duo" and cfg.get("duo_por_etiqueta"):
            moderada = False
        e = {"name": nome, "emoji_name": emoji, "moderated": moderada}
        if nome in existentes:
            e["id"] = existentes[nome]["id"]
        etiquetas.append(e)
    campos_forum = dict(permission_overwrites=ow_membros, topic=T.diretrizes(), available_tags=etiquetas,
                        default_sort_order=1, default_forum_layout=1, default_auto_archive_duration=10080)
    try:
        forum = garantir("forum", 15, cat_m["id"], **campos_forum)
    except DiscordError as e:
        if e.status != 400:
            raise
        for et in etiquetas:  # alguns emojis só passam sem o seletor de variação
            et["emoji_name"] = et["emoji_name"].replace("️", "")
        forum = garantir("forum", 15, cat_m["id"], **campos_forum)
    forum = api.edit_channel(forum["id"], flags=16)  # 16 = exigir etiqueta ao postar
    tags = {}
    for chave, nome, _, _ in ETIQUETAS:
        tag = next((t for t in forum.get("available_tags") or [] if t["name"] == nome), None)
        tags[chave] = tag["id"] if tag else ""

    canal_duo = garantir("duo", 0, cat_m["id"], permission_overwrites=ow_duo,
                         topic="Só Duo Meteoro: noites de partida com o KIRA. Manda seu BattleTag aqui.")
    cat_s = garantir("cat_staff", 4, permission_overwrites=ow_staff)
    manual = garantir("manual", 0, cat_s["id"], permission_overwrites=ow_staff, topic="Como operar a fila de análise.")
    fila = garantir("fila", 0, cat_s["id"], permission_overwrites=ow_staff,
                    topic="Fila de quinta. ✅ = analisado · 🔁 = código venceu · !ajuda = comandos")
    painel = garantir("painel", 0, cat_s["id"], permission_overwrites=ow_staff,
                      topic="Painel do mês: quem está na fila, quem já foi, quem não pediu, BattleTags do Duo.")

    alvo = (cfg.get("categoria_publica") or "INFORMA").lower()
    cat_info = next((c for c in canais if c["type"] == 4 and alvo in c["name"].lower()), None)
    if cat_info:
        # copia as regras da categoria (só leitura pra galera) e libera o robô pra postar
        ow_pub = [ow(o["id"], o["type"], int(o["allow"]), int(o["deny"]))
                  for o in cat_info.get("permission_overwrites") or [] if o["id"] != robo]
        ow_pub.append(ow(robo, 1, VIEW | SEND | EMBED | HISTORY | ADD_REACTIONS | PIN))
        publico = garantir("publico", 0, cat_info["id"], permission_overwrites=ow_pub,
                           topic="Como pedir análise do seu replay.")
    else:
        log("aviso: não achei a categoria pública; o post 'como pedir' ficou de fora")
        publico = None

    def fixar(canal, embed):
        marca = embed["footer"]["text"]
        for m in api.messages(canal, limit=50):
            if m["author"]["id"] == robo and any((e.get("footer") or {}).get("text") == marca for e in m.get("embeds") or []):
                api.edit_message(canal, m["id"], embeds=[embed])
                log(f"texto atualizado: {marca}")
                return
        r = api.send(canal, embeds=[embed])
        try:
            api.pin(canal, r["id"])
        except DiscordError as e:
            log(f"aviso: não fixei {marca} ({e.status})")
        log(f"texto postado: {marca}")

    if publico:
        fixar(publico["id"], T.publico())
    fixar(membros["id"], T.membros_fixo(forum["id"], canal_duo["id"]))
    fixar(canal_duo["id"], T.duo_fixo(forum["id"], duo[0] if duo else None))
    fixar(manual["id"], T.manual(forum["id"], fila["id"], painel["id"], canal_duo["id"]))

    cfg["canais"] = {"forum": forum["id"], "membros": membros["id"], "duo": canal_duo["id"], "manual": manual["id"],
                     "fila": fila["id"], "painel": painel["id"], "publico": publico["id"] if publico else ""}
    cfg["tags"] = tags
    return cfg
