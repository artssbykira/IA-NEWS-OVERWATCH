"""Todos os textos que o robô da fila escreve no Discord.

Para mudar uma frase, mude aqui. Não apague as marcas "-# 🤖 fila:..." do fim
das mensagens: é por elas que o robô reconhece o que ele mesmo já fez.
"""

ALUNO = "Aluno Foguete"
DUO = "Duo Meteoro"
LIVEPIX_URL = "https://livepix.gg/kiraow"
JOIN_URL = "https://www.youtube.com/@kira_owbr/join"
VODS_URL = "https://www.youtube.com/@kira_owbr/streams"
CONVITE = "discord.gg/dxh3ZzDr9y"

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
MES_CURTO = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

COR_PUBLICO = 0xFF6A18
COR_STAFF = 0x5B1F7A


def marca(tipo):
    return f"\n-# 🤖 fila:{tipo}"


# ------------------------------------------------------------ respostas no post
def aceito(dono, posicao, nivel, codigo):
    extra = " Como você é Duo Meteoro, o seu passa na frente." if nivel == "duo" else ""
    return (f"✅ <@{dono}>, seu pedido entrou na fila! Hoje você é o **{posicao}º**.{extra}\n"
            f"Código anotado: **{codigo}**.\n"
            "As análises são **toda quinta, ao vivo**. Quando eu analisar o seu, te aviso aqui e no privado.\n"
            "Saiu patch antes da sua vez? Manda um código novo aqui mesmo: não gasta outro pedido."
            + marca("ok"))


def faltou(dono, faltam):
    itens = "\n".join(f"• {f}" for f in faltam)
    return (f"⚠️ <@{dono}>, quase lá! Faltou:\n{itens}\n"
            "Manda aqui embaixo (ou edita o post) que eu confiro de novo em alguns minutos."
            + marca("faltou"))


FALTA_CODIGO = "o código do replay (escreve assim: `Código: ABC123`)"
FALTA_AUTORIZO = "escrever **Autorizo** (deixa eu mostrar seu replay e seu nick na live e em vídeo)"


def cota(dono, nivel, mes, quantas):
    nome = DUO if nivel == "duo" else ALUNO
    usadas = f"a sua análise de {mes}" if quantas == 1 else f"as suas {quantas} análises de {mes}"
    return (f"🚫 <@{dono}>, você já usou {usadas} "
            f"({nome}: {quantas} por mês, não acumula). Esse pedido não entra na fila.\n"
            "No mês que vem libera de novo. Quer uma agora? Na live, manda R$ 10 no LivePix "
            f"com ANÁLISE + o código: {LIVEPIX_URL}"
            + marca("cota"))


def sem_assinatura(dono):
    return (f"🚫 <@{dono}>, não achei sua assinatura de membro do canal, então esse pedido não entra na fila.\n"
            f"Se você é membro, conecta o YouTube aqui no Discord (Configurações de usuário → Conexões → YouTube). "
            f"Seja membro: {JOIN_URL}"
            + marca("sem-assinatura"))


def saiu(dono):
    return (f"🚫 <@{dono}>, sua assinatura de membro acabou, então esse pedido saiu da fila. "
            f"Voltou a ser membro? É só postar de novo: {JOIN_URL}"
            + marca("saiu"))


def feito(dono, dia, data):
    quem = f"<@{dono}>, " if dono else ""
    return (f"🎥 {quem}análise feita na live de {dia}, {data}! Valeu por mandar.\n"
            f"Perdeu? O VOD fica no canal: {VODS_URL}"
            + marca("feito"))


def feito_dm(dia, data):
    return (f"🎥 Sua análise de replay saiu na live de {dia} ({data}) no canal do KIRA! "
            f"Se perdeu, o VOD fica aqui: {VODS_URL}")


def codigo_venceu(dono):
    quem = f"<@{dono}>, " if dono else ""
    return (f"🔁 {quem}esse código de replay não abriu: saiu atualização do jogo e ele morreu. "
            "Abre o replay de novo no jogo e manda o **código novo** aqui. Não gasta outro pedido: "
            "você continua no mesmo lugar da fila."
            + marca("codigo"))


def codigo_novo(dono, codigo):
    quem = f"<@{dono}>, " if dono else ""
    return f"✅ {quem}código novo anotado: **{codigo}**. Continua na fila." + marca("codigo-novo")


def patch(dono, data):
    quem = f"<@{dono}>, " if dono else ""
    return (f"⚠️ {quem}saiu atualização do Overwatch em {data}. Código de replay de antes do patch costuma "
            "não abrir mais. Se você ainda consegue, manda um **código novo** aqui (de uma partida depois "
            "do patch): não gasta outro pedido."
            + marca("patch"))


# ------------------------------------------------------- canal da staff (📥fila)
def lista_topo(dia, data, n, esperando, chave):
    if n == 0:
        corpo = "Ninguém na fila hoje."
    else:
        corpo = (f"**{n}** na fila. Ordem: 💸 LivePix → ☄️ Duo → chegada.\n"
                 "Terminou uma análise? **Clica ✅ na mensagem dela.** O robô marca, responde no post e avisa a pessoa.\n"
                 "Código não abriu? Clica 🔁 que o robô pede um novo.")
    if esperando:
        corpo += f"\n🔁 {esperando} esperando código novo (aparecem quando a pessoa mandar)."
    return f"📋 **FILA DE {dia.upper()}, {data}**\n{corpo}" + marca(f"lista:{chave}")


def lista_item(i, rotulo, nome, codigo, pedido_em, link, fio):
    return (f"**{i}.** {rotulo}{nome}\n"
            f"Código: **{codigo or '???'}** · pediu em {pedido_em} · {link}"
            + marca(f"item:{fio}"))


def item_feito(conteudo, quando):
    return f"✅ **FEITO** {quando} · " + conteudo


def item_codigo(conteudo):
    return "🔁 **CÓDIGO VENCEU** (esperando código novo) · " + conteudo


def aviso_membros(n, forum, ultima_quinta, mes):
    txt = f"🎥 Hoje é **quinta de análise**! {n} replay{'s' if n != 1 else ''} na fila pra live de hoje."
    if ultima_quinta:
        txt += (f"\nÉ a última quinta de {mes}: quem ainda não pediu a análise do mês, posta no <#{forum}> "
                "(não acumula pro mês que vem).")
    else:
        txt += f"\nAinda não pediu a sua de {mes}? É no <#{forum}>."
    return txt + marca("aviso-quinta")


def livepix_post(codigo, nick, pessoa, data):
    quem = f"<@{pessoa}>" if pessoa else nick
    return (f"💸 Pedido do LivePix (R$ 10) de {quem}, feito na live de {data}.\n"
            f"Código: {codigo}\n"
            "Vai primeiro na próxima quinta."
            + marca("livepix"))


LIVEPIX_SEM_CODIGO = ("Faltou o código. Exemplo: `!livepix ABC123 Fulano Doomfist Ouro 2` "
                      "(dá pra marcar a pessoa: `!livepix ABC123 @Fulano Doomfist Ouro 2`)" + marca("resposta"))

AJUDA = ("**Comandos (escreve aqui no 📥fila; o robô lê a cada ~5 min):**\n"
         "• `!fila` → posta a fila agora (ex.: chegou pedido depois das 17h de quinta)\n"
         "• `!livepix CÓDIGO nick herói rank` → registra um LivePix que não deu tempo de fazer na live\n"
         "• `!ajuda` → mostra isto\n"
         "Na fila: ✅ = analisado · 🔁 = código venceu."
         + marca("resposta"))


def boas_vindas_duo(usuario):
    return (f"☄️ <@{usuario}> chegou no **Duo Meteoro**! Manda aqui embaixo o seu **BattleTag** "
            "(ex.: `Kira#11234`) e a sua função (tank, dano ou suporte), pra entrar nas noites de partida comigo."
            + marca("boas-vindas"))


# ------------------------------------------------------------ textos fixos
def diretrizes():
    return (
        "📼 COMO PEDIR SUA ANÁLISE\n"
        f"1 post = 1 replay. {ALUNO}: 1 por mês. {DUO}: 2 por mês, com prioridade. Não acumula de um mês pro outro.\n\n"
        "Título: seu nick · herói · rank (ex.: RLS · Doomfist · Diamante 3)\n\n"
        "No post:\n"
        "• Código: ABC123 (de uma partida do patch atual)\n"
        "• Herói e mapa\n"
        "• Rank atual\n"
        "• 1 coisa que você quer que eu olhe (ex.: \"morro logo depois do soco\")\n"
        "• Autorizo (= posso mostrar seu replay e seu nick na live e em vídeo)\n\n"
        "Marca a etiqueta ⏳ Na fila. O robô confere e responde em alguns minutos.\n\n"
        "As análises são toda QUINTA, ao vivo. Ordem: LivePix, depois Duo, depois chegada. "
        "De 10 a 15 min no que mais pesa. Quando eu fizer a sua, o robô te avisa aqui e no privado.\n\n"
        "Saiu patch antes da sua vez? O código morre. Manda um novo aqui no mesmo post: não gasta outro pedido."
    )


def publico():
    return {
        "title": "📼 QUER QUE EU ANALISE O SEU REPLAY?",
        "color": COR_PUBLICO,
        "description": (
            f"💸 **Na live:** manda R$ 10 no LivePix ({LIVEPIX_URL}) escrevendo **ANÁLISE + o código do replay** "
            "+ herói + rank. Eu analiso na mesma live (se não der tempo, você vai pra frente da fila de quinta).\n\n"
            f"🎓 **{ALUNO}** (membro do canal no YouTube, R$ 7,99/mês): 1 análise garantida todo mês, "
            "selo, emojis e vídeos só pra membros.\n\n"
            f"☄️ **{DUO}** (R$ 15,99/mês): 2 análises por mês, com prioridade, + 1 quinta por mês jogando comigo.\n\n"
            "As análises de membro são **toda quinta, ao vivo**.\n\n"
            "**Virou membro?** Aqui no Discord: Configurações de usuário → Conexões → YouTube. "
            "Os canais dos membros aparecem sozinhos.\n"
            f"**Seja membro:** {JOIN_URL}"
        ),
        "footer": {"text": "fila:publico"},
    }


def membros_fixo(forum, duo):
    return {
        "title": "💎 BEM-VINDO, MEMBRO!",
        "color": COR_PUBLICO,
        "description": (
            "Aqui é o canto de quem apoia o canal. O que você tem:\n"
            f"🎓 **{ALUNO}:** 1 análise de replay por mês.\n"
            f"☄️ **{DUO}:** 2 por mês (com prioridade) + 1 quinta por mês jogando comigo. Canal próprio: <#{duo}>.\n\n"
            f"📼 **Pra pedir a análise:** posta no <#{forum}>. As regras aparecem quando você cria o post.\n"
            "📅 **Análises: toda quinta, ao vivo.** O robô avisa quando sair a sua.\n\n"
            "Regras: respeito, sem spam, sem divulgar outros canais ou lives. "
            "A análise não acumula de um mês pro outro."
        ),
        "footer": {"text": "fila:membros"},
    }


def duo_fixo(forum, cargo_duo):
    chamada = f"<@&{cargo_duo}>" if cargo_duo else f"@{DUO}"
    return {
        "title": "☄️ DUO METEORO",
        "color": COR_PUBLICO,
        "description": (
            f"1 quinta por mês eu jogo com vocês. Eu marco aqui, chamando {chamada}, alguns dias antes.\n\n"
            "**Pra entrar nas partidas:** manda aqui embaixo o seu **BattleTag** (ex.: `Kira#11234`) "
            "e a sua função (tank, dano ou suporte). Mudou de conta? Manda de novo: vale o último.\n\n"
            f"Suas 2 análises do mês são pedidas no <#{forum}>, como todo membro. O robô já te coloca na frente."
        ),
        "footer": {"text": "fila:duo"},
    }


def manual(forum, fila, painel, duo):
    return {
        "title": "📋 MANUAL DA FILA DE ANÁLISE (pra mim e pros mods)",
        "color": COR_STAFF,
        "description": (
            "**COMO FUNCIONA**\n"
            f"1. O membro posta no <#{forum}>. Em ~5 min o robô confere se é membro, se ainda tem análise no mês, "
            "se mandou o código e o \"Autorizo\". Responde no post e põe na fila.\n"
            f"2. **Toda quinta às 17h** o robô posta a fila do dia no <#{fila}>, na ordem: 💸 LivePix → ☄️ Duo → chegada.\n"
            f"3. Na live: abre o <#{fila}>, pega o código da 1ª mensagem e analisa (10 a 15 min).\n"
            "4. **Terminou → clica ✅ na mensagem dela.** Ninguém escreve nada: o robô troca a etiqueta pra "
            f"🎥 Analisado, responde no post, avisa a pessoa no privado e atualiza o <#{painel}>.\n"
            "5. **Código não abriu → clica 🔁.** O robô pede um código novo; quando a pessoa mandar, volta pra fila.\n"
            "O robô lê a cada ~5 min, então a marcação aparece uns minutos depois do clique.\n\n"
            "**LIVEPIX** (R$ 10 com \"ANÁLISE + código\")\n"
            "• Deu tempo: analisa na mesma live. Nada a registrar.\n"
            f"• Não deu: escreve no <#{fila}>: `!livepix CÓDIGO nick herói rank` "
            "(ex.: `!livepix ABC123 Fulano Doomfist Ouro 2`). Vira um post 💸 e vai primeiro na quinta.\n\n"
            "**COMANDOS** (no 📥fila)\n"
            "• `!fila` → posta a fila agora (ex.: pedido novo depois das 17h de quinta)\n"
            "• `!livepix CÓDIGO nick herói rank` → registra um LivePix pra depois\n"
            "• `!ajuda` → lista os comandos\n\n"
            "**REGRAS**\n"
            f"• {ALUNO}: 1 por mês. {DUO}: 2 por mês, com prioridade. Não acumula.\n"
            "• Pedido além da cota: o robô recusa sozinho e explica.\n"
            "• Análise de membro tem o mesmo tamanho da do LivePix: 10 a 15 min. Nunca maior.\n"
            "• Sem \"Autorizo\" não entra: é o que deixa mostrar o replay na live e no vídeo.\n"
            "• Assinatura acabou: o Discord tira o cargo e o robô tira a pessoa da fila.\n"
            "• Saiu patch: o robô avisa quem está na fila pra mandar código novo.\n\n"
            "**CARGOS**\n"
            "• Os cargos \"YouTube Member: Aluno Foguete\" e \"YouTube Member: Duo Meteoro\" vêm sozinhos quando "
            "a pessoa conecta o YouTube no Discord, e saem 1 dia depois que a assinatura acaba. Ninguém dá cargo na mão.\n"
            "• Mod = cargo MOD: vê a STAFF e o ✅ dele vale.\n\n"
            "**NOITE DO DUO** (1 quinta por mês)\n"
            f"• Quem é Duo e o BattleTag de cada um ficam no <#{painel}>. ❗ = ainda não mandou BattleTag.\n"
            f"• Pra chamar: escreve no <#{duo}> marcando o cargo Duo Meteoro, com dia e hora.\n\n"
            "**ERROU O CLIQUE?** No post, troca a etiqueta de volta pra ⏳ Na fila e apaga a resposta do robô.\n\n"
            "**QUANDO CRESCER** (mais de ~3 h de análise por semana): análise de até 10 min, "
            "ou a garantia fica só no Duo. Avisar os membros com 30 dias."
        ),
        "footer": {"text": "fila:manual"},
    }


def painel(titulo, secoes, rodape):
    return {"title": titulo, "color": COR_STAFF, "description": secoes, "footer": {"text": rodape}}
