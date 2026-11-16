# Robô da fila de análise de replay (Discord do KIRA)

Ele cuida sozinho da fila de análise dos membros do canal (Aluno Foguete e Duo Meteoro).
Roda no GitHub Actions a cada ~5 minutos. **Não precisa deixar o PC ligado.**

## O que ele faz

- **Confere cada pedido novo** no fórum `📼análise-de-replay`:
  - é membro?
  - ainda tem análise no mês? (Aluno 1, Duo 2)
  - mandou o código e escreveu "Autorizo"?
  - Ele responde no post: entrou na fila, faltou alguma coisa ou passou da cota.
- **Toda quinta às 17h** posta a fila do dia no `📥fila`, na ordem LivePix → Duo → chegada.
- **Você não escreve nada.** Terminou a análise? Clica ✅ na mensagem dela. O robô então:
  - troca a etiqueta para 🎥 Analisado;
  - responde no post;
  - avisa a pessoa no privado;
  - atualiza o painel.
- **Código não abriu?** Clica 🔁. O robô pede um código novo. Quando a pessoa manda, ele anota e a pessoa volta para a fila.
- **Saiu patch do jogo:** avisa quem está na fila para mandar código novo. Ele lê as notas de patch no fórum da Blizzard.
- **`📊painel`:** uma mensagem só, que o robô atualiza sozinho. Mostra:
  - quem está na fila;
  - quem já foi analisado no mês;
  - quem ainda não pediu;
  - o BattleTag de cada Duo Meteoro.
- **Duo novo:** o robô dá boas-vindas no `☄️duo-meteoro` e pede o BattleTag.

## Comandos (no `📥fila`, só staff)

- **`!fila`:** posta a fila agora.
- **`!livepix CÓDIGO nick herói rank`:** registra um LivePix que ficou para depois. Ele vai primeiro na quinta.
- **`!ajuda`:** mostra os comandos.

## Arquivos

- **`textos.py`:** tudo o que o robô escreve. Para mudar uma frase, é aqui.
- **`config.json`:** IDs do servidor, dos canais, das etiquetas e dos cargos. Também guarda:
  - a hora da lista de quinta;
  - a cota de cada nível.
- **`fila.py`:** a rodada.
- **`setup.py`:** monta os canais e os textos fixos. Pode rodar de novo sem duplicar nada.
- **`test_fila.py`:** testes com um Discord de mentira.
  - Rodar: `python -m unittest test_fila`, de dentro desta pasta.

## Rodar na mão

GitHub → **Actions** → **Fila de analise (Discord)** → **Run workflow**, e escolher o modo:

- **`simular`:** mostra o que faria, sem escrever nada.
- **`diagnostico`:** lista os cargos (inclusive os da integração do YouTube) e os canais.
- **`montar`:** cria e ajusta a estrutura. Copie o config que ele imprime para o `config.json`.

O token do robô fica só no segredo `DISCORD_BOT_TOKEN` do repositório. Ele nunca vai para o código.
