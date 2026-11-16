"""Guarda o token do robô da fila no GitHub (segredo DISCORD_BOT_TOKEN).

Uso, num terminal:
    python definir_token.py
Cole o token (ele não aparece na tela) e aperte Enter.

O token vai direto do terminal para o GitHub, cifrado com a chave pública do
repositório. Ninguém mais vê: nem o Claude, nem o código. O login do GitHub
usado é o que o Windows já guarda para o usuário artssbykira.
"""
import base64
import getpass
import json
import subprocess
import sys
import urllib.error
import urllib.request

from nacl import encoding, public

REPO = "artssbykira/IA-NEWS-OVERWATCH"
NOME = "DISCORD_BOT_TOKEN"


def login_github():
    saida = subprocess.run(["git", "credential", "fill"],
                           input="protocol=https\nhost=github.com\nusername=artssbykira\n\n",
                           capture_output=True, text=True).stdout
    return dict(l.split("=", 1) for l in saida.splitlines() if "=" in l).get("password")


def api(metodo, caminho, gh, corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    r = urllib.request.Request("https://api.github.com" + caminho, data=dados, method=metodo, headers={
        "Authorization": "Bearer " + gh, "Accept": "application/vnd.github+json", "User-Agent": "fila-kira"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        bruto = resp.read()
        return json.loads(bruto) if bruto else {}


def cifrar(chave_publica_b64, texto):
    caixa = public.SealedBox(public.PublicKey(chave_publica_b64.encode(), encoding.Base64Encoder()))
    return base64.b64encode(caixa.encrypt(texto.encode())).decode()


def main(testar=False):
    gh = login_github()
    if not gh:
        print("Não achei o login do GitHub (artssbykira) guardado no Windows. Nada foi salvo.")
        return 1
    chave = api("GET", f"/repos/{REPO}/actions/secrets/public-key", gh)
    if testar:
        cifrar(chave["key"], "teste")
        print("Teste ok: login do GitHub e chave do repositório funcionando (nada foi salvo).")
        return 0
    token = getpass.getpass("Cole o token do robô (não aparece na tela) e aperte Enter: ").strip()
    if len(token) < 50 or token.count(".") != 2:
        print("Isso não parece um token de robô do Discord (são 3 partes separadas por ponto). Nada foi salvo.")
        return 1
    try:
        api("PUT", f"/repos/{REPO}/actions/secrets/{NOME}", gh,
            {"encrypted_value": cifrar(chave["key"], token), "key_id": chave["key_id"]})
    except urllib.error.HTTPError as e:
        print(f"O GitHub recusou ({e.code}). Nada foi salvo.")
        return 1
    print(f"Pronto: o segredo {NOME} está salvo no GitHub. Pode fechar esta janela.")
    return 0


if __name__ == "__main__":
    sys.exit(main(testar="--testar" in sys.argv))
