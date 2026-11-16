"""Entrada do robô da fila (GitHub Actions).

MODO (variável de ambiente ou 1º argumento):
  rodar       → a rodada normal (a cada ~5 min)
  simular     → igual, mas não escreve nada no Discord (só mostra o que faria)
  diagnostico → lista cargos e canais do servidor
  montar      → cria/ajusta categorias, fórum, etiquetas e textos fixos e imprime o config novo
"""
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fila  # noqa: E402
import setup  # noqa: E402
from discord_api import Discord  # noqa: E402


def main():
    modo = (os.environ.get("MODO") or (sys.argv[1] if len(sys.argv) > 1 else "rodar")).strip().lower()
    token = (os.environ.get("DISCORD_BOT_TOKEN") or "").strip()
    if not token:
        print("sem DISCORD_BOT_TOKEN: nada a fazer")
        return 0
    cfg = json.loads(Path(__file__).with_name("config.json").read_text(encoding="utf-8"))
    api = Discord(token, dry_run=(modo == "simular"))
    try:
        if modo == "diagnostico":
            setup.diagnostico(api, cfg)
            return 0
        if modo == "montar":
            novo = setup.montar(api, cfg)
            print("\nCONFIG NOVO (copiar para fila/config.json):")
            print(json.dumps(novo, ensure_ascii=False, indent=2))
            return 0
        if not cfg["canais"].get("forum"):
            print("ainda não montado: rode o modo 'montar' primeiro")
            return 0
        fila.Robo(api, cfg).rodar()
        return 0
    except Exception:
        traceback.print_exc()
        # na rodada automática não marca falha (evita um e-mail do GitHub a cada 5 min); nos manuais, marca
        return 0 if modo == "rodar" else 1


if __name__ == "__main__":
    sys.exit(main())
