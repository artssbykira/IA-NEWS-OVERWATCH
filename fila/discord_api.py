"""Cliente mínimo da API REST do Discord (só biblioteca padrão do Python).

Usado pelo robô da fila de análise. Com dry_run=True nada é escrito no Discord:
as chamadas de escrita só aparecem no log (modo "simular").
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://discord.com/api/v10"
UA = "DiscordBot (https://github.com/artssbykira/IA-NEWS-OVERWATCH, 1.0)"


class DiscordError(Exception):
    def __init__(self, status, corpo, metodo, caminho):
        super().__init__(f"{metodo} {caminho} -> {status}: {corpo}")
        self.status = status
        self.corpo = corpo
        try:
            self.codigo = json.loads(corpo).get("code")
        except Exception:
            self.codigo = None


def _emoji(e):
    return urllib.parse.quote(e)


class Discord:
    def __init__(self, token, dry_run=False, log=print):
        self.token = token
        self.dry = dry_run
        self.log = log
        self._falso = 0

    # ------------------------------------------------------------------ base
    def req(self, metodo, caminho, corpo=None, params=None):
        if self.dry and metodo != "GET":
            self.log(f"[simular] {metodo} {caminho} {json.dumps(corpo, ensure_ascii=False)[:300] if corpo else ''}")
            self._falso += 1
            return {"id": str(9_000_000_000_000_000_000 + self._falso), "_simulado": True}
        url = API + caminho
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        for tentativa in range(6):
            r = urllib.request.Request(url, data=dados, method=metodo)
            r.add_header("Authorization", "Bot " + self.token)
            r.add_header("User-Agent", UA)
            if dados is not None:
                r.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(r, timeout=30) as resp:
                    bruto = resp.read()
                    return json.loads(bruto) if bruto else {}
            except urllib.error.HTTPError as e:
                bruto = e.read() or b""
                if e.code == 429:
                    try:
                        espera = float(json.loads(bruto).get("retry_after", 1))
                    except Exception:
                        espera = 2.0
                    time.sleep(min(espera, 30) + 0.25)
                    continue
                if e.code >= 500 and tentativa < 5:
                    time.sleep(1 + tentativa)
                    continue
                raise DiscordError(e.code, bruto.decode("utf-8", "replace")[:600], metodo, caminho)
            except urllib.error.URLError:
                if tentativa < 5:
                    time.sleep(1 + tentativa)
                    continue
                raise
        raise DiscordError(429, "limite de requisições persistente", metodo, caminho)

    # ---------------------------------------------------------------- leitura
    def me(self):
        return self.req("GET", "/users/@me")

    def guild(self, g):
        return self.req("GET", f"/guilds/{g}")

    def roles(self, g):
        return self.req("GET", f"/guilds/{g}/roles")

    def channels(self, g):
        return self.req("GET", f"/guilds/{g}/channels")

    def channel(self, c):
        return self.req("GET", f"/channels/{c}")

    def member(self, g, u):
        """Membro do servidor, ou None se a pessoa não está mais no servidor."""
        try:
            return self.req("GET", f"/guilds/{g}/members/{u}")
        except DiscordError as e:
            if e.status == 404:
                return None
            raise

    def members(self, g):
        """Todos os membros (precisa do 'Server Members Intent' ligado no portal)."""
        todos, depois = [], "0"
        while True:
            lote = self.req("GET", f"/guilds/{g}/members", params={"limit": 1000, "after": depois})
            todos.extend(lote)
            if len(lote) < 1000:
                return todos
            depois = lote[-1]["user"]["id"]

    def active_threads(self, g):
        return self.req("GET", f"/guilds/{g}/threads/active").get("threads", [])

    def archived_threads(self, c, before=None):
        return self.req("GET", f"/channels/{c}/threads/archived/public", params={"limit": 100, "before": before})

    def messages(self, c, limit=100, before=None):
        return self.req("GET", f"/channels/{c}/messages", params={"limit": limit, "before": before})

    def reaction_users(self, c, m, emoji):
        return self.req("GET", f"/channels/{c}/messages/{m}/reactions/{_emoji(emoji)}", params={"limit": 100})

    # ---------------------------------------------------------------- escrita
    def send(self, c, content=None, embeds=None, mencionar=None):
        corpo = {"allowed_mentions": mencionar or {"parse": []}}
        if content is not None:
            corpo["content"] = content
        if embeds is not None:
            corpo["embeds"] = embeds
        return self.req("POST", f"/channels/{c}/messages", corpo)

    def edit_message(self, c, m, content=None, embeds=None):
        corpo = {"allowed_mentions": {"parse": []}}
        if content is not None:
            corpo["content"] = content
        if embeds is not None:
            corpo["embeds"] = embeds
        return self.req("PATCH", f"/channels/{c}/messages/{m}", corpo)

    def react(self, c, m, emoji):
        return self.req("PUT", f"/channels/{c}/messages/{m}/reactions/{_emoji(emoji)}/@me")

    def unreact(self, c, m, emoji, usuario):
        return self.req("DELETE", f"/channels/{c}/messages/{m}/reactions/{_emoji(emoji)}/{usuario}")

    def pin(self, c, m):
        try:
            return self.req("PUT", f"/channels/{c}/messages/pins/{m}")
        except DiscordError as e:
            if e.status in (404, 405):
                return self.req("PUT", f"/channels/{c}/pins/{m}")
            raise

    def edit_channel(self, c, **campos):
        return self.req("PATCH", f"/channels/{c}", campos)

    def create_channel(self, g, **campos):
        return self.req("POST", f"/guilds/{g}/channels", campos)

    def create_role(self, g, **campos):
        return self.req("POST", f"/guilds/{g}/roles", campos)

    def create_forum_post(self, forum, nome, content, tags):
        corpo = {"name": nome[:100], "applied_tags": tags,
                 "message": {"content": content, "allowed_mentions": {"parse": []}}}
        return self.req("POST", f"/channels/{forum}/threads", corpo)

    def dm(self, usuario, content):
        canal = self.req("POST", "/users/@me/channels", {"recipient_id": usuario})
        return self.send(canal["id"], content)
