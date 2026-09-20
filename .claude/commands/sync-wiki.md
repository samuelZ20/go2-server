---
description: Regenera o GitHub Wiki a partir de docs/PROBLEMAS_E_SOLUCOES.md
---

Regenere o GitHub Wiki deste repositório a partir de `docs/PROBLEMAS_E_SOLUCOES.md`. Esse arquivo é a **fonte da verdade** — o wiki é sempre uma regeneração total (não incremental) derivada dele. Nunca edite o `.wiki.git` fora deste fluxo.

## Componentes válidos

- `client-tvbox`: PyAudio, ALSA, microfone Anker, `generate_env.sh`, detecção de IP no lado da TV box, path do `.env` no `client_armbian.py` (repo separado [go2-tvbox](https://github.com/carlosvts/go2-tvbox))
- `server-docker-network`: firewalld, Windows Firewall, `network_mode`, WSL2, docker-compose
- `dependencias-python`: pip, torch, transformers, openwakeword, conflitos de versão
- `performance-gpu`: latência do Whisper, CUDA, CPU vs GPU
- `go2`: controle do robô via WebRTC, comandos de movimento, conexão/autenticação com o Go2 — vive no repositório separado `go2-api`, não neste repo

Se um item tocar mais de uma categoria, classifique pela categoria onde a **causa raiz** mora, e adicione a outra como tag secundária.

## Passo 1 — Padronizar entradas novas

Para cada entrada em `docs/PROBLEMAS_E_SOLUCOES.md` que ainda não tenha o cabeçalho `[BUG-0XX]`, adicione (sem alterar Sintoma/Causa raiz/Solução):

```
### [BUG-0XX] <título curto do problema>
**Componente:** <client-tvbox | server-docker-network | dependencias-python | performance-gpu | go2>
**Tags:** <3-5 palavras-chave em minúsculo, separadas por vírgula>
```

IDs são sequenciais e **nunca renumerados**. Descubra o próximo ID livre com:
```bash
grep -oP '(?<=\[BUG-)\d+' docs/PROBLEMAS_E_SOLUCOES.md | sort -n | tail -1
```
Mostre o diff completo e pare para confirmação antes de continuar.

## Passo 2 — Confirmar wiki habilitado

```bash
gh api repos/{owner}/{repo} -q '.has_wiki'
```
Se `false`: `gh api -X PATCH repos/{owner}/{repo} -f has_wiki=true`. Se isso falhar por permissão, pare e diga ao usuário qual caixa marcar em Settings → Features → Wikis.

## Passo 3 — Clonar/atualizar o wiki

O clone vive em `../<repo>.wiki` (um nível acima do repo principal, nunca dentro dele). Se não existir:
```bash
git clone git@github.com:{owner}/{repo}.wiki.git ../<repo>.wiki
```
Se o clone falhar com "Repository not found" mesmo com `has_wiki: true`, o repositório git do wiki só é criado depois que alguém cria a primeira página pela interface web (`https://github.com/{owner}/{repo}/wiki` → "Create the first page"). Pare e peça para o usuário fazer isso uma vez.

Se o clone já existir, rode `git pull` para garantir que está atualizado antes de regenerar.

## Passo 4 — Gerar as páginas

A partir do `docs/PROBLEMAS_E_SOLUCOES.md` já padronizado, gere/sobrescreva dentro do clone do wiki:

- **`Home.md`** — aviso de que o wiki é gerado automaticamente, resumo curto do projeto, link para cada página de categoria (incluindo `Go2`), link para `Como-Reportar-Bugs`, e data do sync.
- **`Client-TVBox.md`**, **`Server-Docker-Network.md`**, **`Dependencias-Python.md`**, **`Performance-GPU.md`**, **`Go2.md`** — entradas da categoria em ordem crescente de ID. Cada entrada com âncora `<a id="bug-0XX"></a>` antes do `###`, para permitir link cruzado entre páginas (ex: `[BUG-002](Server-Docker-Network#bug-002)`). Se uma categoria não tiver itens ainda, deixe a página com uma nota "Nenhum item registrado ainda".
- **`_Sidebar.md`** — navegação lateral customizada, agrupada por categoria na ordem acima.
- **`Como-Reportar-Bugs.md`** — mantenha em sync com a seção equivalente do `README.md` do repo principal (não regenere do zero a cada vez; apenas confirme que bate).

Referências cruzadas dentro do texto original (ex: "ver item #8") devem virar links markdown para a âncora correta, considerando se o alvo está na mesma página ou em outra.

## Passo 5 — Commit e sync

1. `git add -A` dentro do clone do wiki.
2. Só commite se houver mudança: `git diff --cached --quiet || git commit -m "sync: regenerar wiki a partir do PROBLEMAS_E_SOLUCOES.md"`.
3. Mostre o diff (`git diff --cached` antes de commitar, ou o resumo do commit depois) e **pare para confirmação explícita antes de `git push`**.
4. Se não houver nenhuma mudança desde o último sync, avise e não faça push vazio.

## Regras de segurança

- Nunca dê `git push` sem mostrar o diff antes e esperar confirmação explícita.
- Nunca edite arquivos do `.wiki.git` fora deste fluxo de regeneração.
- Se algo der errado (has_wiki não habilita, clone falha, etc.), pare e explique — não tente workarounds não solicitados.

## Ao final

Resuma: quantas entradas por categoria, URL do wiki, e qualquer item com categorização ambígua para revisão manual.
