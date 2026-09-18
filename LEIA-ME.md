# Robô de notícias de Overwatch — Discord do KIRA

A cada 3 horas ele:

1. lê o **fórum oficial da Blizzard** (anúncios e notas de patch completas), o **YouTube do Overwatch** e o **Reddit** (r/Overwatch e r/DoomfistMains)
2. pega só o que é novo
3. a **IA Gemini (grátis)** resume em português e decide se aquilo afeta o Doomfist
4. posta:
   - no **#overwatch-news** → toda notícia de verdade (memes e clipes ficam de fora)
   - no **#doomfist** → só o que muda para o Doom, com os números antes → depois (5v5 e Stadium)

Custo: **zero**. Roda no GitHub Actions (grátis) e usa a camada gratuita do Gemini.
Não precisa deixar o PC ligado.

---

## Configuração (uma vez só, uns 15 minutos)

### 1. Criar os dois webhooks no Discord

Para **cada** canal (`#overwatch-news` e `#doomfist`):

1. Clique na engrenagem do canal → **Integrações** → **Webhooks** → **Novo webhook**
2. Dê um nome (ex.: `KIRA Notícias`) e, se quiser, uma foto
3. **Copiar URL do webhook** e guarde num bloco de notas

> ⚠️ Quem tiver essa URL consegue postar no canal. Não mostre em live e não mande em chat.

### 2. Pegar a chave grátis do Gemini

1. Entre em **https://aistudio.google.com** com sua conta Google
2. **Get API key** → **Create API key**
3. Copie a chave (começa com `AIza...`)

Não precisa de cartão. Não ative faturamento — é isso que mantém de graça.

### 3. Criar o repositório no GitHub

1. Crie uma conta em **https://github.com** (se não tiver)
2. **New repository** → nome `kira-noticias-ow` → marque **Private** → **Create repository**
3. Clique em **uploading an existing file** e arraste **tudo desta pasta**, incluindo a pasta
   `.github` (no Explorer, ative *Exibir → Itens ocultos* se ela não aparecer)
4. **Commit changes**

> Se o upload pela web ignorar a pasta `.github`: no repositório, **Add file → Create new file**,
> digite o nome `.github/workflows/noticias.yml` e cole o conteúdo do arquivo.

### 4. Guardar as três senhas no GitHub

No repositório: **Settings → Secrets and variables → Actions → New repository secret**.
Crie estes três (o nome tem que ser exatamente assim):

| Name | Secret |
|---|---|
| `GEMINI_API_KEY` | a chave do passo 2 |
| `WEBHOOK_OVERWATCH` | URL do webhook do `#overwatch-news` |
| `WEBHOOK_DOOMFIST` | URL do webhook do `#doomfist` |

### 5. Ligar e testar

1. Aba **Actions** → se pedir, clique em **I understand my workflows, go ahead and enable them**
2. À esquerda, **Noticias Overwatch** → **Run workflow** → marque **Postar a ultima nota de patch agora** → **Run workflow**
3. Em ~1 minuto deve aparecer a última nota de patch no `#overwatch-news` e o trecho do Doomfist no `#doomfist`

Depois disso ele roda sozinho a cada 3 horas. A **primeira** execução automática só marca o
histórico como lido (para não despejar notícias antigas no canal); a partir da segunda ele posta
o que sair de novo.

---

## Dúvidas comuns

**Parou de postar?** Aba **Actions** → abra a última execução e leia o log. As mensagens estão
em português.

**Postou algo que não devia / deixou passar algo?** O critério da IA está no texto `PROMPT`
dentro de `noticias.py`. Dá para ajustar ali.

**O Reddit aparece como "pulada"?** Normal. O Reddit às vezes bloqueia robôs; o resto continua
funcionando e ele tenta de novo na próxima rodada.

**A IA ficou fora do ar?** O robô não para: ele cai para um filtro por palavra-chave
(procura "Doomfist" no texto) e posta o trecho original em inglês.

**O GitHub desativou o robô?** Em repositórios sem atividade por 60 dias o GitHub pausa os
agendamentos. Como o robô grava o `vistos.json` sempre que sai notícia nova, isso não deve
acontecer; se acontecer, é só entrar em **Actions** e reativar.

**Quero mudar a frequência:** em `.github/workflows/noticias.yml`, a linha
`cron: '17 */3 * * *'` significa "a cada 3 horas". `'17 */1 * * *'` seria a cada hora.
