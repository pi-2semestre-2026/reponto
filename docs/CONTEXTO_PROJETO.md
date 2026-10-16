# Reponto — documento de contexto do projeto

> Documento de consulta para novas sessões. Descreve **o que o projeto é, como está construído, como rodar,
> como o motor de recomendação calcula, o que já existe, o que está planejado e onde estão as armadilhas**.
>
> - Estado descrito: branch `pipeline-ml`, commit `bd7661c`, levantado em 2026-10-15.
> - Tudo aqui foi extraído do código e do histórico git. Onde há incerteza ou inferência, está marcado como **(inferido)** ou **(a confirmar)**.
> - Se o código divergir deste documento, o código vence — e este documento deve ser atualizado.
> - O único outro documento do repositório é `docs/PLANO_ML.md` (roteiro do núcleo de ML, em fases). Não há `README.md` nem `CLAUDE.md` na árvore atual.

---

## 1. TL;DR

**Reponto** ("Seu mercado, sempre no ponto") é um app web de **gestão de estoque com recomendação de reposição por IA para mercados de bairro**.
O lojista cadastra um mercado (clientes/dia e ciclo de reposição), cadastra produtos, registra vendas, e o sistema aprende a
**taxa diária de venda** de cada produto e recomenda **estoque mínimo, máximo e quantidade a comprar por ciclo**.

Três camadas convivem no repositório:

| Camada | Onde | Estado |
|---|---|---|
| **App** (FastAPI + Next.js + Postgres, em Docker) | `backend/`, `frontend/`, `docker-compose.yml` | Funcional (PoC). É o que está em `feat/reponto-poc` e herdado por `pipeline-ml`. |
| **Simulador de estoque** (jogo que testa o recomendador contra uma "realidade" estocástica) | `backend/simulator/`, `frontend/src/components/simulator/` | Funcional, isolado do núcleo. |
| **Núcleo acadêmico de ML** (pipeline em notebooks, dataset Favorita, baseline → LightGBM → ponto de pedido) | `docs/PLANO_ML.md` (só o plano) | **Planejado; nenhuma linha escrita.** Não existem `src/`, `notebooks/`, `tests/`, `pyproject.toml`. |

O recomendador **em produção hoje** é uma mistura de: constantes calibradas à mão por categoria (`baseline_rate`) × um fator sazonal
de um LightGBM minúsculo (336 linhas) × clientes/dia, combinada por EMA com o que as vendas reais do lojista mostram.
O objetivo do trabalho em andamento (`pipeline-ml`) é **substituir essas constantes por previsão e regra de reposição medidas em dados reais**.

---

## 2. Contexto e propósito

- **Natureza:** projeto acadêmico em grupo (PII — Projeto Integrador/Interdisciplinar **(inferido)** do histórico), prazo previsto de 3–4 meses.
  Tema: previsão de demanda e recomendação de reposição de estoque em pequeno varejo.
- **Idioma do produto:** PT-BR (UI padrão `pt`, com alternativa `en`). Código e identificadores em inglês; textos de notebooks planejados em português.
- **Dataset acadêmico alvo:** *Store Sales – Time Series Forecasting* (Favorita, Kaggle). Granularidade: família × loja; previsão semanal.
- **Dataset usado hoje pelo app:** *Store Item Demand Forecasting Challenge* (Kaggle), só para moldar sazonalidade.
- **Histórico de regras do dono (recuperável com `git show bd949c3:docs/BRIEFING.md`):** o arquivo, removido no commit `772ed1c`, dizia que
  este é "um projeto de aprendizado": antes de escrever código que implemente um conceito de dados/ML (limpeza, agregação, features, modelo,
  validação, métricas, simulação de estoque, avaliação), **explicar o conceito e perguntar se o dono quer escrever**; ao revisar código dele,
  **apontar o erro e explicar o porquê, sem reescrever**; infraestrutura (pastas, config, ambiente, dependências, scripts de dado falso) pode ser feita direto.
  O `docs/PLANO_ML.md` mantém o espírito (cada etapa tem "Conceitos antes de implementar").
  **(a confirmar com o dono se essa regra continua valendo para o trabalho em `pipeline-ml`.)**
  Ressalva: outras "decisões fechadas" daquele arquivo (sem Docker, sem login, sem banco, sem LangChain) **foram superadas** pelo app que existe hoje.

---

## 3. Estado do repositório

### 3.1 Branches e histórico

```
main              bd949c3  feat: project initial structure           (esqueleto vazio: data/, notebooks/, src/, docs/, README, requirements.txt)
feat/reponto-poc  4dc7396  fix: backend container not starting due to CRLF entrypoint   (app completo — PoC)
pipeline-ml  *    bd7661c  docs: add ML core roadmap with detailed Phase 1 plan          (= feat/reponto-poc + .gitignore + docs/PLANO_ML.md)
```

Commits relevantes em ordem: `9ee4834` Initial commit → `942fa2f` Update README → `75d83a2` estrutura inicial → `bd949c3` estrutura (main) →
`772ed1c` initial commit (traz o app inteiro, remove README/BRIEFING/requirements) → `4dc7396` fix CRLF do entrypoint → `b1b97ff` ignora `data/raw/` → `bd7661c` PLANO_ML.

Remotos: `origin/main`, `origin/feat/reponto-poc`. A branch `pipeline-ml` ainda não tem upstream listado.
Autoria git: Pedro Cavalheiro. Commits do assistente usam trailer `Co-Authored-By: Claude …`.

### 3.2 O que existe vs. o que não existe

| Existe | Não existe |
|---|---|
| App FastAPI + Next.js + Postgres via `docker-compose` | Testes automatizados (nenhum `pytest`/`jest` no repo) |
| Recomendador EMA + prior (LightGBM) | Migrações de banco (usa `create_all`) |
| Categorização por palavras-chave → LLM (OpenRouter) | `README.md`, `CLAUDE.md`, CI |
| Simulador de estoque (jogo) + coach LLM | Pipeline Favorita (`src/pipeline/`, `notebooks/`, `pyproject.toml`) |
| Script `scripts/simular_vendas.py` | Importação de vendas por CSV no app |
| Datasets: `datasets/Store Item Demand…/` (versionado), `data/raw/favorita/` (local, ignorado) | Lead time por mercado no modelo de dados |
| `docs/PLANO_ML.md` | `transactions.csv` do Favorita (necessário para a Fase 7) |

### 3.3 Ambiente local do dono (observado)

- Windows 11, Git Bash/PowerShell. Python local 3.13.7 **sem** pandas/Jupyter/pytest e **sem venv** (segundo o PLANO_ML). Docker Desktop instalado; no momento do levantamento o daemon **não estava rodando**.
- `.env` na raiz (ignorado pelo git) existe e **contém uma `OPENROUTER_API_KEY` real preenchida**. Nunca imprimir/commitar. Chaves presentes: `OPENROUTER_API_KEY, OPENROUTER_MODEL, DATABASE_URL, SECRET_KEY, OBS_WINDOW_DAYS, EMA_HALF_LIFE_DAYS, BACKEND_PORT, NEXT_PUBLIC_API_URL, FRONTEND_PORT`.
- `data/raw/favorita/` contém `train.csv` (~121 MB, 3.000.888 linhas), `stores.csv` (54 lojas), `holidays_events.csv` (350 linhas). **Faltam** `transactions.csv`, `oil.csv`, `test.csv`.
- `.gitattributes` força LF em `*.sh` (CRLF no shebang quebrava o container). `core.autocrlf` do Windows continua sendo fonte de problemas se novos `.sh` forem criados.

---

## 4. Arquitetura e stack

```
 Navegador ── Next.js 14 (App Router, standalone, :3000)
                 │  fetch + Bearer JWT (localStorage "reponto_token")
                 ▼
            FastAPI (uvicorn, :8000)  ── LangChain/ChatOpenAI ──► OpenRouter (opcional)
                 │            └─ LightGBM em memória (rate_model)
                 ▼
            Postgres 16 (asyncpg, SQLAlchemy 2 async)

 /datasets (ro)  ──► agregado 1x no boot ──► tabela dataset_aggregates ──► treina/carrega model.txt (volume ml_data)
```

| Parte | Tecnologias (versões fixadas) |
|---|---|
| Backend | Python 3.12 (imagem `python:3.12-slim` + `libgomp1`, `curl`), FastAPI 0.115.6, uvicorn 0.34, SQLAlchemy 2.0.36 async, asyncpg 0.30, Pydantic 2.10.4 + pydantic-settings 2.7.1, PyJWT 2.10.1, langchain-core ≥0.3.29 <0.4, langchain-openai 0.3.0, **lightgbm 4.5.0, pandas 2.2.3, numpy 2.1.3**, email-validator, tzdata |
| Frontend | Next.js 14.2.25, React 18.3, TypeScript 5.7, Tailwind 3.4 (+ tailwindcss-animate), Radix UI (dialog, dropdown, label, popover, progress, select, separator, slot, switch, tooltip), class-variance-authority, recharts 2.15, sonner, next-themes, canvas-confetti, lucide-react. Node 20 alpine, `output: "standalone"` |
| Banco | `postgres:16-alpine`, usuário/senha/db `mercado`, volume `pgdata` |
| Infra | `docker-compose.yml` (projeto `reponto`), volume `ml_data` para o modelo treinado |

Decisões estruturais a lembrar:
- **Assíncrono de ponta a ponta** (AsyncSession). Tarefas pesadas usam `BackgroundTasks`/`asyncio.create_task`.
- **Tempo:** o banco guarda UTC; "dia do mercado" é sempre calculado em `APP_TZ` (padrão `America/Sao_Paulo`) via `app/services/clock.py`.
- **Isolamento por dono:** todo recurso (mercado → produto → venda) é filtrado por `owner_id` do usuário autenticado. **Exceção: categorias são globais** (ver §14).
- **Simulador é plugável:** `main.py` importa `simulator.register` dentro de `try/except ImportError`; `SIMULATOR_ENABLED` liga/desliga.

---

## 5. Estrutura de pastas

```
reponto/
├── .env / .env.example          # variáveis do compose (o .env real é ignorado pelo git)
├── .gitattributes               # *.sh eol=lf
├── .gitignore                   # node_modules, .next, .venv, __pycache__, .env, backend/ml_data, data/raw/, ...
├── docker-compose.yml           # db + backend + frontend
├── backend/
│   ├── Dockerfile               # python:3.12-slim; copia app/, simulator/, entrypoint; ENV ML_MODEL_PATH, DATASET_DIR
│   ├── bootstrap_entrypoint.sh  # espera DB → `python -m app.bootstrap` (tolera falha) → uvicorn
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py              # FastAPI, CORS, routers, lifespan (prepare_data), /health, monta o simulador
│   │   ├── bootstrap.py         # create_all → seed categorias → ingestão → sync priors → treina/carrega modelo → recupera produtos travados
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── database.py          # engine async, SessionLocal, Base, get_db
│   │   ├── models.py            # tabelas (ver §7.2)
│   │   ├── schemas.py           # modelos Pydantic de entrada/saída
│   │   ├── security.py          # PBKDF2 + JWT
│   │   ├── routers/             # auth, markets, products, sales, categories, analytics, dep (dependências)
│   │   └── services/
│   │       ├── recommender.py   # ★ coração: prior × observado, estoque mín/rec/máx, logs auditáveis
│   │       ├── ml.py            # RateModel (LightGBM) — treino/carga/predição
│   │       ├── datasets.py      # ingestão única do CSV do Kaggle → agregado (336 linhas)
│   │       ├── seed_data.py     # 14 categorias PT-BR com baseline_rate e keywords; buckets de porte
│   │       ├── categorizer.py   # palavras-chave → LLM → padrão; processamento em background
│   │       └── clock.py         # fuso/dia local
│   └── simulator/               # jogo de estoque (isolado) — ver §10
├── frontend/
│   ├── Dockerfile               # multi-stage; NEXT_PUBLIC_API_URL é build-arg
│   └── src/
│       ├── app/                 # rotas (ver §11)
│       ├── components/          # header, learning-panel, sale-cart, auth-form, logo, ui/* (shadcn-like), simulator/*
│       └── lib/                 # api.ts, simulator-api.ts, types.ts, i18n.tsx, token.ts, format.ts, utils.ts, confetti.ts
├── datasets/Store Item Demand Forecasting Challenge/   # train/test/sample_submission (versionado; só train.csv é lido)
├── data/raw/favorita/           # Favorita (local, ignorado pelo git) — insumo do núcleo de ML
├── docs/PLANO_ML.md             # roteiro do núcleo de ML + Fase 1 detalhada
└── scripts/simular_vendas.py    # gera vendas via API (stdlib only)
```

Arquivo-lixo versionado: `frontend/tsconfig.tsbuildinfo` (deveria estar no `.gitignore`).

---

## 6. Como rodar

### 6.1 Docker (caminho oficial)

```bash
cp .env.example .env        # preencher o que quiser; todos os valores têm default no compose
docker compose up --build   # sobe db, backend, frontend
```

| Item | Valor |
|---|---|
| Frontend | http://localhost:3000 (`FRONTEND_PORT`) |
| API | http://localhost:8000 (`BACKEND_PORT` — **atenção:** o compose publica `${BACKEND_PORT:-8000}:8000`) |
| Docs OpenAPI | http://localhost:8000/docs |
| Health | `GET /health` → `{"status":"ok"}` |

Sequência de boot do backend: espera Postgres → `python -m app.bootstrap` (**falha tolerada**: a API sobe mesmo assim com priors estáticos) → `uvicorn app.main:app`.
O `lifespan` do FastAPI roda `prepare_data()` de novo (idempotente), então o bootstrap efetivamente roda duas vezes por start.
Healthcheck do backend tem `start_period: 90s` (a 1ª subida lê 913 mil linhas do CSV e treina o LightGBM).

### 6.2 Variáveis de ambiente

| Variável | Default | Papel |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://mercado:mercado@localhost:5432/mercado` (compose aponta para `db`) | Conexão |
| `SECRET_KEY` | `dev-secret-change-me` (compose: `reponto-dev-secret`) | Assinatura do JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` (7 dias) | Validade do token (não exposto no compose) |
| `OPENROUTER_API_KEY` | vazio | Habilita categorização por LLM e coach do simulador. Vazio ⇒ fallbacks locais |
| `OPENROUTER_MODEL` | `deepseek/deepseek-chat` | Modelo no OpenRouter |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | |
| `OBS_WINDOW_DAYS` | `90` | Janela máxima de observação |
| `EMA_HALF_LIFE_DAYS` | `30` | Meia-vida do decaimento exponencial |
| `APP_TZ` / `TZ` | `America/Sao_Paulo` | Fuso do "dia do mercado" |
| `DATASET_DIR` | `/datasets` | Onde procurar o CSV (monta `./datasets` ro) |
| `ML_MODEL_PATH` | `/app/ml_data/model.txt` | Artefato LightGBM (volume `ml_data`) |
| `DEFAULT_MARKET_CUSTOMERS` | `100` | (definido, **não usado** no código visto) |
| `FRONTEND_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | CORS |
| `SIMULATOR_ENABLED` | `true` | Monta `/admin/simulator` (não exposto no compose) |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | **Embutida no build** do frontend — mudar exige rebuild |

`.env.example` está incompleto (faltam `ACCESS_TOKEN_EXPIRE_MINUTES`, `APP_TZ`, `SIMULATOR_ENABLED`, etc.) e tem todos os valores vazios.

### 6.3 Resetar estado

- Não há migrações: **mudou `models.py` ⇒ `docker compose down -v`** (apaga `pgdata` e `ml_data`) ou alterar o schema à mão. `create_all` não altera tabelas existentes.
- Para retreinar o LightGBM: apagar `ml_data` (ou incrementar `MODEL_VERSION` em `ml.py`).
- Para reingerir o dataset: esvaziar `dataset_aggregates`.

### 6.4 Script de vendas simuladas

`python scripts/simular_vendas.py [--api URL] [--days-back 14] [--qty 2] [--interval 20] [--max-sales N] …`
Autentica/registra `simulador@demo.com.br`, garante mercado "Mercado do Simulador" (150 clientes/dia, ciclo semanal) e produto "Água Mineral 500ml",
faz backfill retroativo via `sold_at`, e entra em loop vendendo/repondo imprimindo o painel de aprendizado.
**Atenção:** o default de `--api` é `http://localhost:8001`, mas o compose publica **8000** — passar `--api http://localhost:8000`.

---

## 7. Backend

### 7.1 Configuração e boot (`app/bootstrap.py`)

`prepare_data()`, nesta ordem:
1. `create_tables()` — `Base.metadata.create_all`.
2. `seed_categories()` — upsert das 14 categorias de `SEED_CATEGORIES` (descrição/keywords sobrescritas a cada boot; `is_seed=True`).
3. `run_ingestion()` — se `dataset_aggregates` já tem linhas `family="geral"`, pula; senão lê `train.csv`, agrega e persiste (apaga linhas de dataset anterior).
4. `sync_category_priors()` — **a cada boot** regrava `CategoryPrior` a partir de `baseline_by_name` (as baselines vivem no código).
5. Carrega linhas agregadas e chama `rate_model.ensure(path, rows)` — carrega `model.txt` se `.meta.json` tem `version == MODEL_VERSION (2)`, senão treina.
6. `recover_stale_products()` — reprocessa produtos `processing` há >180 s ou `ready` sem nenhum `RecommendationLog`.

Cada etapa é protegida por `try/except` com log: o app degrada para priors estáticos em vez de cair.

### 7.2 Modelo de dados (`app/models.py`)

| Tabela | Campos principais | Observações |
|---|---|---|
| `users` | id (UUID), name, email (único), hashed_password, created_at | Cascata para `markets` |
| `categories` | id, name (único), description, keywords (CSV), is_seed | **Globais**, compartilhadas entre usuários |
| `markets` | id, owner_id, name, location, **customers_per_day** (default 100), **replenishment_cycle_days** (default 7), cycle_unit (`diario/semanal/quinzenal/mensal`) | Cascata para `products` |
| `products` | id, market_id, category_id, name, unit, price, stock, min_stock, max_stock, recommended_quantity, learned_rate, prior_rate, observed_rate, alpha, confidence (`baixa/media/alta`), status (`processing/ready/error`) | Numeric(12,3) para quantidades |
| `sales` | id, market_id, user_id, total, status (`completed/cancelled`), **sold_at** (indexado), created_at, cancelled_at | `sold_at` pode ser retroativo |
| `sale_items` | id, sale_id, product_id (SET NULL ao excluir produto), product_name (snapshot), category_id, quantity, unit_price, subtotal | Snapshot preserva histórico |
| `stock_adjustments` | id, product_id, delta, reason, created_at | Trilha de ajustes manuais |
| `recommendation_logs` | id, product_id, trigger, prior_rate, observed_rate, alpha, final_rate, safety_stock, min/max/recommended, window_start/end, n_sales, source (`model/static/default`), details (JSON texto) | **Trilha de auditoria** de cada recálculo |
| `dataset_aggregates` | family, month, weekday, size_bucket, avg_sales_per_tx, n_days (único por family+month+weekday+size_bucket) | 336 linhas; CSV nunca mais é lido |
| `category_priors` | category_id (PK), prior_rate, n_days | Fallback estático por categoria |

`SALE_STATUS_ENUM` está definido e **não é usado**.

### 7.3 API

Todas as rotas (exceto `/auth/register`, `/auth/login`, `/health`) exigem `Authorization: Bearer <jwt>`. Erros usam `{"detail": "..."}` em PT-BR.

| Método e rota | Função | Notas |
|---|---|---|
| `POST /auth/register` | Cria usuário, retorna token | 409 se e-mail existe; senha 6–128 |
| `POST /auth/login` | Retorna token | 401 genérico |
| `GET /auth/me` | Usuário atual | |
| `GET/POST /markets` | Lista/cria mercados do usuário | `cycle_unit` conhecido ⇒ dias derivados (1/7/15/30); desconhecido ⇒ usa `replenishment_cycle_days` |
| `GET/PATCH/DELETE /markets/{id}` | Detalhe/edita/exclui | PATCH exige corpo completo; se mudar clientes ou ciclo ⇒ recálculo em background de todos os produtos (`market_updated`) |
| `POST /markets/{id}/products` | Cria produto — **202**, `status=processing` | Categoria provisória = "Mercearia"; categorização + 1ª recomendação em background |
| `GET /markets/{id}/products` | Lista produtos | Mais novos primeiro |
| `PATCH /products/{id}` | Edita nome/preço/unidade | Recalcula na hora (`product_updated`) |
| `DELETE /products/{id}` | Exclui | |
| `POST /products/{id}/stock` | Ajuste de estoque `{delta, reason}` | 400 se ficar negativo; grava `StockAdjustment`; recalcula (`stock_adjust`) |
| `GET /products/{id}/learning` | **Painel "Como a IA calculou"** | blend atual, fórmula textual, evolução e até 50 logs |
| `POST /sales` | Checkout `{market_id, items[], sold_at?}` | Transação única, `SELECT … FOR UPDATE`; 400 se estoque insuficiente; aceita `sold_at` retroativo; recalcula produtos (`sale`) |
| `GET /sales` | Lista (filtros `market_id`, `date_from`, `date_to`) | limite 500, mais recentes primeiro |
| `GET /sales/{id}`; `POST /sales/{id}/cancel` | Detalhe / cancela | Cancelar devolve estoque e a venda sai do aprendizado (`sale_cancelled`) |
| `GET /sales/stats/count` | Contagem de vendas do usuário | |
| `GET/POST/PATCH/DELETE /categories` | CRUD de categorias | Não exclui `is_seed`; 409 se há produtos; nome único (case-insensitive) |
| `GET /analytics` | Painel: período atual vs. anterior (mesma duração), top 8 produtos, receita por categoria, série diária, estoque por categoria, alertas (top 20 com `stock <= min_stock`), visão por mercado | `date_from/date_to` default = últimos 30 dias; só vendas `completed` |
| `GET /health` | Liveness | |
| `/admin/simulator/*` | Simulador (ver §10) | Autenticado, **sem papel de admin** |

### 7.4 Autenticação (`security.py`, `routers/dep.py`)

PBKDF2-HMAC-SHA256 com 120 000 iterações e sal de 16 bytes (formato `pbkdf2$salt$hash`); JWT HS256 com `sub`=user id, `exp` 7 dias.
`get_current_user` → 401 se ausente/inválido; `get_owned_market` → 404 (não 403) se o mercado não é do usuário.

### 7.5 Fluxo de criação de produto

1. `POST /markets/{id}/products` cria `Product(status="processing")` com categoria padrão e responde 202.
2. `process_product_background`: `resolve_category` (palavras-chave → LLM → padrão) → `status="ready"` → `recalc_product(..., "product_created")`.
3. Em qualquer exceção: cai para categoria padrão, `ready`, tenta recalcular; nunca propaga erro.
4. O frontend faz polling (2 s enquanto houver `processing`, senão 15 s) e dispara toast "IA terminou".
5. Se o processo morre no meio, `recover_stale_products()` no próximo boot reprocessa.

---

## 8. Motor de recomendação (`app/services/recommender.py`)

> Replicado **fielmente** em `backend/simulator/brain.py`. **Qualquer mudança de fórmula precisa ser feita nos dois lugares.**

### 8.1 Fórmulas

```
size_bucket   = 0 se clientes/dia <150; 1 se <400; 2 se <1200; 3 caso contrário

prior_rate    = baseline_rate(categoria) × fator_sazonal × clientes_por_dia          [unid/dia]
  fator_sazonal = clamp( LightGBM(mês, dia_da_semana, size_bucket) / média_geral , 0.5 , 2.0 )   # usa a data de HOJE
  sem modelo    → CategoryPrior.prior_rate × clientes  (source="static")
  sem nada      → baseline × clientes                    (source="default")

observed_rate = Σ qtd × 2^(−idade_dias / meia_vida)  /  Σ pesos_dos_dias_da_janela
  janela      = [primeira venda do produto, hoje], limitada a OBS_WINDOW_DAYS (90)
  denominador = (1 − r^(janela_dias+1)) / (1 − r),  r = 2^(−1/meia_vida)           # série geométrica fechada
  n_sales     = nº de VENDAS distintas (cupons) com o produto na janela, status=completed

alpha         = max(0.3, n_sales / (n_sales + 10))
  n_sales == 0 → alpha = 0.3 e observed = estoque/ciclo (se estoque>0) ou 0 (se não)

final_rate    = alpha × observed + (1 − alpha) × prior

safety_stock  = final_rate × ciclo × 0.3
min_stock     = final_rate × ciclo × 0.4 + safety
recommended   = final_rate × ciclo × 1.2 + safety     (recommended_quantity)
max_stock     = final_rate × ciclo × 2.0 + safety

confidence    = "baixa" se n_sales < 3 · "media" se < 10 · "alta" caso contrário
```

Constantes: `DEFAULT_PRIOR = 0.08` (também `DEFAULT_BASELINE_RATE`), `SEASONAL_FACTOR_BOUNDS = (0.5, 2.0)`, multiplicadores 0,3 / 0,4 / 1,2 / 2,0.
Meia-vida e janela vêm de `EMA_HALF_LIFE_DAYS` e `OBS_WINDOW_DAYS`.

### 8.2 Exemplo numérico

Mercado com 100 clientes/dia, ciclo semanal (7 d), produto de "Bebidas" (baseline 0,25), fator sazonal 1,0, sem vendas, estoque 0:
- prior = 0,25 × 1,0 × 100 = **25 un/dia**; observed = 0; alpha = 0,3 ⇒ final = 0,7 × 25 = **17,5 un/dia**.
- safety = 17,5 × 7 × 0,3 = 36,75; **min = 85,75**; **recomendado = 183,75**; **max = 281,75**.

### 8.3 Gatilhos de recálculo (`TRIGGER_LABELS`)

`product_created`, `sale`, `sale_cancelled`, `stock_adjust`, `product_updated`, `market_updated`, `recalc`. Cada um grava um `RecommendationLog` com `details` JSON (motivo, fórmula, janela, numerador/denominador, composição do prior, contexto do modelo, notas, segurança).

### 8.4 Semântica e limitações (importante para o roadmap)

- `recommended_quantity` é um **nível-alvo de estoque** para o ciclo (1,2 × demanda do ciclo + segurança), **não** "quanto comprar líquido do estoque atual". O simulador compra `max(0, round(recomendado − estoque))`; o app só exibe o valor. A landing page chama de "Comprar".
- O **nível absoluto** vem das baselines manuais; o dataset só molda sazonalidade. O painel, porém, rotula a fatia `(1−alpha)` como "dataset" (`dataset_share_pct`) — termo enganoso.
- O fator sazonal usa **só a data de hoje**, não a média sobre o ciclo inteiro.
- Não há **lead time** nem desvio do erro de previsão: o estoque de segurança é uma fração fixa (30%) da demanda do ciclo.
- **Vendas perdidas por ruptura** não aparecem nos dados (o sistema só vê o que vendeu) — viés conhecido, medido pelo simulador.
- Venda retroativa **respeita `sold_at` no aprendizado**, mas o **estoque é decrementado no momento do cadastro** (sem viagem no tempo).

---

## 9. Camada de ML atual e categorização

### 9.1 LightGBM sazonal (`app/services/ml.py`, `app/services/datasets.py`)

- **Dado:** Kaggle *Store Item Demand Forecasting Challenge* — `date,store,item,sales`; 10 lojas × 50 itens × 5 anos ≈ 913 mil linhas. Sem categorias.
- **Agregação (1x no boot):** média de unidades por item-dia por **mês (12) × dia da semana (7) × porte da loja (4 quartis de volume)** = **336 linhas** → tabela `dataset_aggregates`.
- **Modelo:** `lgb.train` regressão L2, `learning_rate 0.06`, `num_leaves 31`, `min_data_in_leaf 10`, bagging/feature fraction 0,9, `seed 42`, 250 rodadas. Features: `[month, weekday, size_bucket]`.
- **Persistência:** `model.txt` + `model.txt.meta.json` (`{"version": 2, "overall_mean": …}`) no volume `ml_data`. Predição cacheada por `(mês, dia, porte)`.
- **Uso:** só produz o **fator sazonal** (`pred / overall_mean`, clamp 0,5–2,0). É deliberadamente "dataset-wide".

### 9.2 Baselines por categoria (`seed_data.py`)

`baseline_rate` = ritmo esperado de um SKU típico, em **unidades por cliente por dia**:

| Categoria | baseline | Categoria | baseline |
|---|---|---|---|
| Padaria | 0,6 | Limpeza | 0,05 |
| Hortifrúti | 0,3 | Higiene e Beleza | 0,06 |
| Bebidas | 0,25 | Peixes e Frutos do Mar | 0,04 |
| Laticínios e Ovos | 0,2 | Pet e Bebê | 0,03 |
| Carnes e Aves | 0,15 | Lar e Cozinha | 0,02 |
| Mercearia (padrão) | 0,15 | Festa e Papelaria | 0,02 |
| Congelados e Frios | 0,08 | Diversos | 0,015 |

Cada categoria tem `description` (usada no prompt do LLM) e `keywords` (CSV, usado no match local). Categoria padrão: **Mercearia**.

### 9.3 Categorização (`categorizer.py`)

1. **Palavras-chave:** normaliza (minúsculas, sem acento), procura cada keyword como substring; vence a de maior keyword casada (desempate por nº de matches); "Mercearia" só ganha se nada mais casou.
2. **LLM** (se `OPENROUTER_API_KEY`): `ChatOpenAI` via OpenRouter, `temperature=0`, `max_tokens=900`, `timeout=30`, `reasoning excluded`. Recebe as categorias com descrições; responde JSON `{"categoria": …}` ou `{"nova_categoria": {nome, descricao}}`. **Pode criar categoria nova** (`is_seed=False`).
3. **Padrão:** Mercearia.

Usa `SystemMessage/HumanMessage` direto (sem templates) para que chaves `{}` do JSON de exemplo não virem variáveis do LangChain.

---

## 10. Simulador de estoque (`backend/simulator/`)

Jogo "Simulador de Estoque" que testa o recomendador real contra uma realidade estocástica independente. **Totalmente em memória, zero escrita no banco**, nada em `app/` depende dele.

| Módulo | Papel |
|---|---|
| `mount.py` / `__init__.py` | `register(app)` — monta o router se `SIMULATOR_ENABLED` |
| `api.py` | Router `/admin/simulator`: `GET /scenarios`, `POST /sessions` (`scenario, days 7–1095, cycle_days 1–30, seed`), `POST /sessions/{sid}/step` (`days 1–90`), `GET /sessions/{sid}`, `GET /sessions/{sid}/report`, `DELETE /sessions/{sid}` |
| `store.py` | Sessões em dict; TTL 6 h; máx. 64 (descarta a mais antiga). Morrem com o processo |
| `scenarios.py` | 3 cenários: **bairro** (45 clientes/dia, 14 produtos), **medio** (180, 20), **grande** (520, 27); catálogo de 27 SKUs com `strength` aleatória por partida, preço por categoria e custo = 68% do preço |
| `engine.py` | Laço diário (ver abaixo) |
| `brain.py` | `SimRecommender`: réplica em memória de `compute_prior_rate` + `compute_blend` |
| `ground_truth.py` | `DemandOracle`: a "verdade" |
| `metrics.py` | MAE, WAPE, viés, nível de serviço, métricas "clean", veredito |
| `llm.py` | Coach via OpenRouter; sem chave ou em falha ⇒ `fallback_coach` local |

**Dia do jogo:** (1) o mundo cria/expira eventos; (2) em dia de reposição (`day_index % cycle == 0`) o "dono obediente" compra até o nível recomendado, a custo; (3) a demanda real é sorteada e o estoque vende até zerar — o excedente é **venda perdida** que o sistema nunca vê; (4) as vendas entram no histórico do `brain`.
Prateleira inicial = 2 × ciclo × prior. Data inicial = 1º de jan. de `max(2020, ano_atual − 1)`.

**Oráculo (propositalmente de forma funcional diferente do LightGBM):** `base = baseline(categoria) × strength × clientes`, × fator de dia da semana (seg 0,90 … sáb 1,38) × fator de mês (dez 1,30) × eventos; ruído lognormal σ=0,24 e amostragem Poisson. Eventos (prob. 3,5%/dia): `heatwave`, `holiday`, `rival_promo`, `street_fair`, `payday_week`.
*Nota:* o oráculo usa as **mesmas baselines** do recomendador — o nível é compartilhado; só a sazonalidade e o ruído diferem.

**Métricas** (`metrics.py`): `wape_pct`, `bias_pct`, `service_pct` (dias-produto sem ruptura), variantes `*_clean` (excluem rupturas e o dia 0) e `rate_wape_pct` (WAPE semanal por produto — a medida "honesta" do ritmo).
**Veredito:** +2 se WAPE ≤15 (+1 se ≤30); +1 se |viés| ≤10; +1 se serviço ≥97. ≥4 `acertivo`, ≥2 `parcial`, senão `fora`; direção `superestima/subestima` se |viés| >10.

> O `PLANO_ML.md` (Fase 5) exige que as métricas do núcleo de ML tenham **a mesma definição** de `_aggregate` em `simulator/metrics.py` (WAPE = Σ|e|/Σy; viés = Σ(ŷ−y)/Σy).

---

## 11. Frontend (`frontend/src`)

### 11.1 Rotas (App Router, todas `"use client"`)

| Rota | Conteúdo |
|---|---|
| `/` | Landing (redireciona para `/dashboard` se há token) |
| `/login`, `/register` | `AuthForm` |
| `/dashboard` | KPIs com comparação ao período anterior, gráficos (recharts), top produtos, alertas de estoque; presets hoje/7d/30d/mês/personalizado |
| `/markets` | Lista de mercados |
| `/markets/new` | Wizard em 5 passos (nome → clientes/dia → local → ciclo → revisão) com barra de progresso e confete |
| `/markets/[id]` | Tabela de produtos (status, estoque, taxa aprendida), diálogos: novo/editar produto, ajuste de estoque, excluir, configurações do mercado, **carrinho de venda**, **painel de aprendizado** |
| `/sales` | Histórico de vendas, filtros, cancelamento |
| `/categories` | CRUD de categorias (seed não excluíveis) |
| `/admin/simulador` | Jogo (setup → partida com velocidades 1/7/30 dias → relatório + coach) |

### 11.2 Convenções

- **Auth:** token em `localStorage["reponto_token"]`; `api.ts` injeta `Authorization`; **401 ⇒ limpa token e `window.location = "/login"`**. Não há middleware Next nem proteção server-side: cada página checa `getToken()`.
- **API:** `lib/api.ts` (`api.get/post/patch/delete` + métodos nomeados), `lib/simulator-api.ts` (cliente próprio), tipos em `lib/types.ts` (decimais vêm como **string**).
- **i18n:** `lib/i18n.tsx`, dicionários `pt`/`en` em um único arquivo (274 chaves cada), `useI18n().t(key)`, escolha em `localStorage["pm_locale"]`, fallback para `pt` e depois para a própria chave. Chaves do simulador: `sim.*`; do painel de IA: `aiPanel.*`.
- **Tema:** next-themes, padrão `light`, alternância manual; tokens HSL em `globals.css`; marca com verde profundo (`--primary`) e o **"ponto" laranja** (`--ponto`) — `PontoDot`, `Wordmark`/`LogoMark`. Fontes: Bricolage Grotesque (display), Figtree (sans), IBM Plex Mono (mono).
- **UI:** componentes estilo shadcn em `components/ui/*`; variantes de botão incluem `press` (3D) e `ponto`.
- **Formatação:** `fmtMoney` (BRL), `fmtNum`, `fmtDate*` em `pt-BR`.
- **Header:** navegação (Painel, Mercados, Vendas, Categorias), idioma, tema, menu do usuário com link para o simulador e "Sair". O toast de logout decide o idioma comparando `t("common.loading") === "Loading..."` (gambiarra).
- **Painel "Como a IA calculou"** (`learning-panel.tsx`): mostra prior × observado × alpha, % "seus dados" vs "dataset", janela, fórmula, evolução (gráfico) e logs.

---

## 12. Datasets

| Dataset | Local | Versionado? | Uso |
|---|---|---|---|
| Store Item Demand Forecasting Challenge | `datasets/Store Item Demand Forecasting Challenge/` (`train.csv` 18 MB, `test.csv`, `sample_submission.csv`) | **Sim** | App: agregado 336 linhas → LightGBM sazonal. O adaptador busca `train.csv` em `DATASET_DIR` ou subpastas |
| Favorita (Store Sales – Time Series Forecasting) | `data/raw/favorita/` | **Não** (`data/raw/` no `.gitignore`) | Núcleo de ML (Fases 1+). Imutável |

**Favorita — fatos medidos (PLANO_ML):** 3.000.888 linhas (`id,date,store_nbr,family,sales,onpromotion`); 2013-01-01 a 2017-08-15; 54 lojas × 33 famílias = 1.782 séries de 1.684 linhas; só falta 25/12; 31,3% de linhas zeradas; 240 semanas completas (seg–dom) de 2013-01-07 a 2017-08-13; 711 séries sem semana zerada; lojas que abrem depois de jan/2013: 20, 21, 22, 29, 36, 42, 52, 53. `stores.csv`: `store_nbr,city,state,type,cluster`. `holidays_events.csv`: `date,type,locale,locale_name,description,transferred`.

---

## 13. Roadmap do núcleo de ML (`docs/PLANO_ML.md`)

Nasce **separado do app**, em `notebooks/` e `src/pipeline/`. Fases 1–5 **não tocam** `backend/` nem `frontend/`; o app só é alterado nas Fases 6–7.

| Fase | Entrega | Dependência que a Fase 1 precisa deixar pronta |
|---|---|---|
| 1 | Séries semanais de 5–10 pares loja×família, baseline média móvel (k=4), MAE e MAPE | — |
| 2 | LightGBM com validação walk-forward vs. baseline | Mesmas 52 semanas de teste, mesmo horizonte, mesmas métricas |
| 3 | Perfil semanal por loja (proporção por dia da semana) | Carregador diário de `data.py` |
| 4 | Ponto de pedido em dias de cobertura (previsão × lead time + estoque de segurança) | Resíduos por série do backtest |
| 5 | Avaliação da recomendação + explicação via LLM | Métricas com a mesma definição do simulador |
| 6 | Importação de vendas por CSV no app (1ª fase que toca o app) | Reaproveita `sold_at` retroativo |
| 7 | Modelo treinado substitui as constantes de `seed_data.py` | pandas/numpy nas versões do backend |

**Fase 1 — decisões fixadas (valem para a Fase 2):**
- Semana = segunda a domingo, soma das vendas, rótulo = segunda; só as 240 semanas completas.
- Teste = últimas 52 semanas (semana de 2016-08-15 a 2017-08-07); 188 semanas de histórico.
- Horizonte = 1 semana, origem móvel (`horizon` parametrizável).
- Baseline oficial = média das 4 semanas anteriores (k = 1, 8, 13 só como sensibilidade; **nunca escolher k no teste**).
- MAPE ignora semanas com venda real 0 e informa quantas ignorou.
- Recorte sugerido: 4 famílias × 2 lojas (GROCERY I, BEVERAGES, DAIRY, BREAD/BAKERY × lojas 44 e 54); reservas CLEANING e MEATS; **evitar** PRODUCE (muitas semanas zeradas), HOME CARE e lojas que abriram depois de jan/2013.
- Etapas (cada uma só começa quando a anterior passou no "Pronto quando"): 0 ambiente (`pyproject.toml`, venv, pandas 2.2.3, numpy 2.1.3, pyarrow) → 1 carga/exploração → 2 agregação semanal (`weekly.py`) → 3 recorte → 4 métricas → 5 baseline + avaliação → 6 `python -m pipeline.phase1`.
- Saídas geradas por código: `data/processed/favorita_weekly.parquet`, `reports/fase1_baseline.csv`.
- **Contratos:** dado bruto imutável; processado regenerável; notebook explora, módulo (`src/pipeline/`) implementa e é testado.

**Pontos de atenção futuros:** (F4) mercado não tem lead time — no pipeline é parâmetro, na integração vira campo novo; (F5) LLM via OpenRouter com `ChatOpenAI` (padrão do `categorizer.py`); (F7) **descasamento de unidade**: Favorita mede unidades da *família inteira por loja*, `baseline_rate` é *unidades por cliente por dia de um SKU típico* — a conversão exige `transactions.csv`, que ainda não está em `data/raw/favorita/`.

**Estado atual:** nada da Fase 1 implementado. `.gitignore` ainda **não** tem `data/processed/` nem `.ipynb_checkpoints/` (o plano manda acrescentar na Etapa 0).

---

## 14. Armadilhas, inconsistências e dívidas conhecidas

1. **Sem migrações** — mudança de schema exige reset do volume (`docker compose down -v`) ou SQL manual.
2. **Categorias são globais**: qualquer usuário autenticado cria/edita/exclui categorias não-seed que afetam todos; o LLM também cria categorias globais.
3. **`/admin/simulator` sem autorização de admin** — qualquer usuário logado acessa; sessões são compartilháveis por `sid`.
4. **Rate limit/validação de LLM:** chave real no `.env` local; sem limites de uso; falha do LLM cai silenciosamente para "Mercearia".
5. **Porta do script:** `simular_vendas.py` assume `:8001`; o compose usa `:8000`.
6. **`.env.example` incompleto** e com valores vazios; `DEFAULT_MARKET_CUSTOMERS` não é usado; `SALE_STATUS_ENUM` morto; `markets/new` envia `replenishment_cycle_days: 7` fixo (o backend corrige via `cycle_unit`).
7. **Bootstrap duplicado** (entrypoint + lifespan) — idempotente, mas dobra o tempo de boot na 1ª subida.
8. **`dataset_share_pct` / "dataset"** no painel não é literal: o dataset só dá sazonalidade; o nível é manual.
9. **Dataset do app ≠ domínio:** o Store Item Demand é de marketplace/itens genéricos; por isso o modelo não tem categoria. Substituí-lo é o objetivo das Fases 6–7.
10. **Estoque retroativo:** vendas com `sold_at` no passado baixam o estoque *agora*; cancelar devolve *agora*.
11. **LightGBM com 3 features sobre 336 linhas** é essencialmente uma tabela de lookup suavizada; não há validação/medição desse modelo no repositório.
12. **Fator sazonal usa só "hoje"**; ciclos longos (quinzenal/mensal) não ponderam o período coberto.
13. **Sem testes automatizados** em nenhum lado; a verificação hoje é manual/pelo simulador/pelo script.
14. **`frontend/tsconfig.tsbuildinfo`** versionado; `NEXT_PUBLIC_API_URL` é fixada no build.
15. **Segurança de PoC:** `SECRET_KEY` com default fraco, CORS por lista, token em `localStorage`, PBKDF2 120k iterações, sem refresh/revogação, sem verificação de e-mail.
16. **Plano diz "pandas e numpy nas versões do backend"** — se o pipeline for instalado em Python 3.13 local, conferir wheels das versões fixadas (numpy 2.1.3/pandas 2.2.3).
17. **Finais de linha:** Windows com `core.autocrlf=true` + scripts `.sh` ⇒ usar sempre LF (já coberto por `.gitattributes`).

---

## 15. Glossário

| Termo | Significado |
|---|---|
| **Ciclo de reposição** | Intervalo entre compras (`diario`=1, `semanal`=7, `quinzenal`=15, `mensal`=30 dias) |
| **Taxa (rate)** | Unidades vendidas por dia de um produto |
| **Prior** | Estimativa a priori da taxa: baseline × sazonalidade × clientes |
| **Observado** | Taxa medida nas vendas reais do lojista, com decaimento exponencial |
| **Alpha** | Peso do observado no blend; sobe com o nº de vendas (piso 0,3) |
| **Taxa aprendida / final_rate** | `alpha × observado + (1−alpha) × prior` |
| **Estoque de segurança** | 30% da demanda do ciclo (constante hoje) |
| **Ponto (de reposição)** | Metáfora da marca: o "ponto" laranja; "no ponto" = estoque certo |
| **Baseline (ML)** | Previsor simples de referência (média móvel das 4 semanas anteriores) |
| **Walk-forward** | Validação temporal com origem móvel e re-treino |
| **WAPE / viés** | Σ\|e\|/Σy e Σ(ŷ−y)/Σy |
| **Venda perdida** | Demanda não atendida por ruptura — invisível ao sistema |
| **Favorita** | Dataset Kaggle de lojas equatorianas (Corporación Favorita) |

---

## 16. Mapa rápido "quero mexer em X → vá para Y"

| Quero… | Arquivo |
|---|---|
| Mudar a fórmula de recomendação | `backend/app/services/recommender.py` **e** `backend/simulator/brain.py` |
| Ajustar baselines/categorias/keywords | `backend/app/services/seed_data.py` (sincroniza a cada boot) |
| Trocar/retreinar o modelo sazonal | `backend/app/services/ml.py` (+ `MODEL_VERSION`), `datasets.py` |
| Mexer em preços/regras de venda e estoque | `backend/app/routers/sales.py`, `products.py` |
| Mudar o painel/analytics | `backend/app/routers/analytics.py`, `frontend/src/app/dashboard/page.tsx` |
| Mudar textos da UI | `frontend/src/lib/i18n.tsx` (pt e en) |
| Mudar o contrato da API | `backend/app/schemas.py` + `frontend/src/lib/types.ts` + `api.ts` |
| Mexer no jogo | `backend/simulator/*`, `frontend/src/components/simulator/*`, `lib/simulator-api.ts` |
| Começar o pipeline de ML | seguir `docs/PLANO_ML.md` (criar `pyproject.toml`, `src/pipeline/`, `notebooks/`, `tests/pipeline/`) |
