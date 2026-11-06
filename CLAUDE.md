# CLAUDE.md — Reponto

Contexto do projeto para sessões do Claude Code. Leia antes de mexer no código.
Idioma do produto, dos textos de UI, dos comentários de domínio e das mensagens de erro da API: **português do Brasil**. Responda ao usuário em português.

---

## 1. O que é o Reponto

**Reponto** ("Seu mercado, sempre no ponto") é um app web de **gestão de estoque com recomendação de compra por IA para mercados de bairro**.

O dono do mercado cadastra mercados e produtos, registra vendas, e o sistema diz **quanto comprar por ciclo de reposição** (diário, semanal, quinzenal, mensal). A recomendação mistura:

1. um **prior** (o que se espera vender): baseline da categoria × fator sazonal de um modelo LightGBM × clientes/dia;
2. a **taxa observada** nas vendas reais do próprio mercado (média com decaimento exponencial);
3. um peso `alpha` que cresce conforme entram vendas (o sistema "aprende").

Cada recálculo grava um log auditável, exibido ao usuário no painel "Como a IA calculou".

É um **PoC** (branch `feat/reponto-poc`): sem testes automatizados, sem migrations, sem CI. Priorize não quebrar o fluxo de ponta a ponta.

## 2. Stack e como roda

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12, FastAPI 0.115, SQLAlchemy 2 async + asyncpg, Pydantic 2, PyJWT, LightGBM, pandas, LangChain (`langchain-openai`) |
| Banco | PostgreSQL 16 (container) |
| Frontend | Next.js 14.2 (App Router, `output: "standalone"`), React 18, TypeScript, Tailwind 3, Radix UI (componentes estilo shadcn), Recharts, sonner, next-themes |
| LLM | OpenRouter (API compatível com OpenAI), opcional |
| Infra | `docker-compose.yml` com 3 serviços: `db`, `backend`, `frontend` |

### Subir tudo (forma suportada)

```bash
docker compose up -d --build          # sobe db + backend + frontend
docker compose ps                      # backend leva ~30-90s até ficar "healthy"
docker compose logs -f backend
docker compose down                    # para (volumes pgdata e ml_data persistem)
docker compose down -v                 # CUIDADO: apaga banco e modelo treinado
```

- Frontend: http://localhost:3000 — Backend: http://localhost:8000 (docs em `/docs`) — Health: `GET /health`.
- Não existe fluxo de dev local fora do Docker documentado. O backend assume `DATASET_DIR=/datasets` e `ML_MODEL_PATH=/app/ml_data/model.txt`; o frontend roda `next build` + `node server.js`.
- Reconstruir só um serviço: `docker compose up -d --build frontend` (ou `backend`).
- Windows: o Docker Desktop precisa estar aberto (`docker info` falha se o daemon estiver parado).

### Variáveis de ambiente (`.env` na raiz; modelo em `.env.example`)

O `.env` é lido **pelo Compose para interpolar `${VAR}`**, não é repassado inteiro ao container (não há `env_file`). Só as variáveis listadas em `environment:` do `docker-compose.yml` chegam ao backend. Para expor uma nova, adicione-a lá.

| Variável | Efeito | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | Habilita categorização por LLM e o "coach" do simulador. Vazia = tudo cai em fallback local | vazio |
| `OPENROUTER_MODEL` | Modelo no OpenRouter | `deepseek/deepseek-chat` |
| `SECRET_KEY` | Chave do JWT | `reponto-dev-secret` |
| `OBS_WINDOW_DAYS` | Janela máxima de observação (dias) | 90 |
| `EMA_HALF_LIFE_DAYS` | Meia-vida do decaimento das vendas (dias) | 30 |
| `BACKEND_PORT` / `FRONTEND_PORT` | Portas publicadas no host | 8000 / 3000 |
| `NEXT_PUBLIC_API_URL` | URL do backend **vista pelo navegador** | `http://localhost:8000` |

> **Armadilha nº 1:** `NEXT_PUBLIC_API_URL` é gravada no bundle do frontend **no build** (`ARG` no Dockerfile). Mudar o `.env` sem rebuild do frontend não surte efeito. Já aconteceu: o `.env` apontava para `:8001` e login/cadastro falhavam sem nenhuma requisição chegar ao backend. Deve bater com a porta publicada do backend (`BACKEND_PORT`).
>
> O `.env` contém uma chave real do OpenRouter e é ignorado pelo git. Nunca imprima, comite ou copie seu conteúdo.

## 3. Estrutura do repositório

```
reponto/
├── docker-compose.yml
├── .env / .env.example
├── .gitattributes              # força LF em *.sh (CRLF quebra o entrypoint no container)
├── datasets/
│   └── Store Item Demand Forecasting Challenge/   # CSVs do Kaggle (train.csv ~18 MB), montados em /datasets (ro)
├── scripts/simular_vendas.py   # gerador de vendas via API (stdlib only)
├── backend/
│   ├── Dockerfile, requirements.txt, bootstrap_entrypoint.sh
│   ├── app/                    # API + domínio (núcleo)
│   │   ├── main.py             # FastAPI, CORS, lifespan, monta routers e simulador
│   │   ├── config.py           # Settings (pydantic-settings)
│   │   ├── database.py         # engine async, SessionLocal, Base, get_db
│   │   ├── models.py           # todos os modelos SQLAlchemy
│   │   ├── schemas.py          # todos os schemas Pydantic
│   │   ├── security.py         # PBKDF2 + JWT HS256
│   │   ├── bootstrap.py        # criação de tabelas, seed, ingestão, treino
│   │   ├── routers/            # auth, markets, products, sales, categories, analytics, dep
│   │   └── services/
│   │       ├── recommender.py  # CORAÇÃO: fórmula prior/observado/alpha, logs
│   │       ├── ml.py           # LightGBM sazonal (RateModel / singleton rate_model)
│   │       ├── datasets.py     # ÚNICO ponto de entrada de dataset externo
│   │       ├── categorizer.py  # categorização keywords → LLM → default
│   │       ├── importer.py     # importação CSV do PDV/ERP (vendas e cadastro)
│   │       ├── explainer.py    # explicação em linguagem natural + verificação dos números
│   │       ├── evaluation.py   # backtest walk-forward LightGBM vs. média móvel
│   │       ├── seed_data.py    # categorias PT-BR, keywords, baselines, buckets de porte
│   │       └── clock.py        # tempo local (America/Sao_Paulo)
│   └── simulator/              # jogo/stress-test do recomendador (isolado, ver §7)
└── frontend/
    ├── Dockerfile, next.config.mjs, tailwind.config.ts, tsconfig.json (alias @/* → src/*)
    └── src/
        ├── app/                # rotas (App Router)
        ├── components/         # header, learning-panel, sale-cart, ui/*, simulator/*
        └── lib/                # api.ts, i18n.tsx, types.ts, token.ts, simulator-api.ts, format.ts
```

## 4. Backend — arquitetura

### 4.1 Ciclo de vida / boot

`bootstrap_entrypoint.sh`: espera o Postgres → roda `python -m app.bootstrap` (tolera falha) → `exec uvicorn app.main:app`. O `lifespan` do FastAPI roda `prepare_data()` **de novo** (por isso tudo é idempotente).

`prepare_data()` (`app/bootstrap.py`), em ordem:
1. `Base.metadata.create_all` — **não há Alembic**. Colunas novas em tabelas existentes vão em `COLUMN_PATCHES` (`bootstrap.py`, `ADD COLUMN IF NOT EXISTS`). Tabelas novas são criadas pelo `create_all`.
2. `seed_categories` — upsert das categorias de `SEED_CATEGORIES` (atualiza descrição/keywords a cada boot).
3. `run_ingestion` — agrega `train.csv` em 336 linhas (`DatasetAggregate`: mês × dia da semana × porte) **uma única vez**; depois o CSV nunca mais é lido.
4. `sync_category_priors` — a cada boot, alinha `CategoryPrior` aos baselines do código.
5. `rate_model.ensure` — carrega o modelo LightGBM do volume `ml_data` ou treina e salva (`model.txt` + `model.txt.meta.json`; retreina se `MODEL_VERSION` em `ml.py` mudar).
6. `recover_stale_products` — reprocessa produtos presos em `processing` (> 180 s) ou `ready` sem nenhum log.

### 4.2 Modelo de dados (`app/models.py`)

`User` 1—N `Market` 1—N `Product`; `Sale` 1—N `SaleItem`; `Product` 1—N `RecommendationLog`, `StockAdjustment`; `Category` global; `DatasetAggregate`; `CategoryPrior`.

- Todos os IDs de entidades de negócio são UUID; `SaleItem`, `StockAdjustment`, `RecommendationLog`, `DatasetAggregate` usam `BigInteger` autoincrement.
- `Product.status`: `processing` → `ready` (ou `error`, definido mas não usado). `confidence`: `baixa|media|alta`. `Sale.status`: `completed|cancelled`.
- `SaleItem` guarda **snapshot** (`product_name`, `unit_price`, `category_id`) e `product_id` vira `NULL` se o produto for excluído — histórico de vendas e analytics sobrevivem à exclusão.
- `Product` guarda o último estado calculado (`learned_rate`, `prior_rate`, `observed_rate`, `alpha`, `min/max/recommended`), e `RecommendationLog` guarda o histórico (com `details` em JSON serializado como `Text`).
- **Categorias são globais** (não por usuário): qualquer usuário autenticado pode criar/editar/excluir categorias não-seed. Categorias seed (`is_seed=True`) não podem ser excluídas; categoria em uso (409) também não.

### 4.3 API (todas exigem `Authorization: Bearer <jwt>` exceto `/auth/register`, `/auth/login`, `/health`)

| Rota | Observação |
|---|---|
| `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | name 2–120, senha 6–128; email único (409); login inválido → 401 |
| `GET/POST /markets`, `GET/PATCH/DELETE /markets/{id}` | `cycle_unit` ∈ `diario|semanal|quinzenal|mensal` → 1/7/15/30 dias. PATCH que muda clientes/dia ou ciclo dispara `recalc_market_products` em background |
| `GET/POST /markets/{id}/products` | POST responde **202** com `status=processing`; categorização + 1º cálculo rodam em `BackgroundTasks` |
| `PATCH/DELETE /products/{id}`, `POST /products/{id}/stock`, `GET /products/{id}/learning` | stock não pode ficar negativo; `learning` devolve fórmula, evolução e últimos 50 logs |
| `POST /sales`, `GET /sales`, `GET /sales/{id}`, `POST /sales/{id}/cancel`, `GET /sales/stats/count` | ver §4.5 |
| `GET/POST/PATCH/DELETE /categories` | ver acima |
| `GET /analytics?date_from&date_to&market_id` | KPIs do período vs. período anterior, top produtos, receita/estoque por categoria, série diária, alertas de estoque baixo, visão por mercado. Default: últimos 30 dias |
| `POST /markets/{id}/import/preview`, `POST /markets/{id}/import`, `GET /markets/{id}/imports` | upload multipart (`file`). Ver §4.8 |
| `GET /markets/{id}/purchase-list`, `POST /markets/{id}/purchases` | lista de compras (ponto de pedido + reposição até o recomendado) e registro de recebimento (sobe estoque, recalcula com trigger `purchase`) |
| `GET /products/{id}/explanation?refresh=` | explicação em PT-BR verificada. Ver §4.9 |
| `GET /ml/evaluation`, `POST /ml/evaluation/run` | backtest do modelo. Ver §4.10 |
| `/admin/simulator/*` | ver §7 |

Autorização: `get_current_user` (`routers/dep.py`) e `get_owned_market`. **Todo recurso é checado por dono** (mercado → produto/venda via join); recurso de outro usuário responde **404**, não 403. Mantenha esse padrão em rotas novas.

### 4.4 Motor de recomendação (`app/services/recommender.py` + `forecast_math.py`)

Dois caminhos de previsão, escolhidos por produto:

1. **Modelo semanal** (`weekly_model.py`): produto com **≥ 8 semanas completas** de vendas e modelo carregado. LightGBM Tweedie com offset log(nível), treinado e validado no Favorita (§4.10, §6). `final_rate = previsão_semanal / 7`. A trava de sanidade mantém a previsão em [0,25; 4] × o nível recente.
2. **Regra** (produtos novos, ou antes de o modelo estar treinado):
```
prior_rate    = baseline(categoria) × fator_do_mês(categoria) × clientes_por_dia
observed_rate = Σ qty·2^(−idade/meia_vida) / Σ pesos_dos_dias   (janela da 1ª venda, máx. OBS_WINDOW_DAYS)
alpha         = max(0.3, n_vendas / (n_vendas + 10))
final_rate    = alpha·observed + (1−alpha)·prior
```

Comum aos dois caminhos:
- **Perfil por dia da semana**: o perfil do próprio produto, com as semanas recentes pesando mais (meia-vida de 42 dias), é encolhido (k=2) para o padrão da **categoria ajustado ao ritmo da loja** (`category_store_prior`). Foi escolhido no Favorita (`scripts/experimentos/perfil_dia_semana.py`): erro diário 12,2% contra 22,3% com "igual todo dia" e 16,6% com um padrão único. A projeção dia a dia = taxa × índice do dia.
- **Nível de atendimento** (`service_target`): produto que estraga antes da próxima entrega (`SHELF_LIFE_DAYS`: Padaria 1 dia, Peixes 2, Carnes 3, Hortifrúti 5 ≤ ciclo) segue a regra do jornaleiro, `Cu/(Cu+Co)` com Cu = margem + 50% do preço (cliente perdido) e Co = custo. O resultado fica limitado a [50%, 95%]. Os demais produtos miram 95%.
- **Margem de segurança**: no caminho regra, `z(nível)·σ_diário·√ciclo` (sem histórico: 30% da demanda do ciclo). No caminho modelo, o quantil calibrado `q(nível)` é dividido em erro de nível (cresce com ciclo/7) e ruído diário (cresce com √ciclo); para ciclo = 7 ele é exatamente o limite calibrado.
- **Demanda censurada**: dia em que a venda zerou o estoque (detectado pelo campo `estoque` do `RecommendationLog.details` com trigger `sale`) tem a procura estimada em +25% (`STOCKOUT_UPLIFT`). Sem isso, produto que esgota entra numa espiral de subestimar.
- **Níveis**: no caminho modelo, `recomendado = demanda do ciclo + margem`; no caminho regra, `1,2 × demanda + margem` (com 95%). `mínimo = demanda dos próximos 0,4×ciclo dias + margem`; `máximo = 2 × demanda + margem`.
- `refresh_stale_products` recalcula na listagem de produtos e na lista de compras quem foi calculado em outro dia ou antes do modelo atual (trigger `daily`).
- **Fontes** (`RecommendationLog.source`): `modelo_semanal` | `model` (prior sazonal) | `static` | `default`. O log grava o caminho, a previsão semanal, o limite de 95% e o estoque após o cálculo.
- `size_bucket_from_customers`: <150 → 0, <400 → 1, <1200 → 2, ≥1200 → 3.
- **Sincronia obrigatória**: `simulator/brain.py` replica tudo isso usando as mesmas funções de `forecast_math`/`weekly_model`. Isso vale também para o laboratório (§7).

### 4.5 Vendas

`POST /sales` (carrinho): uma transação; trava os produtos com `SELECT … FOR UPDATE`, valida estoque (400 com mensagem `Estoque insuficiente para X: N disponível`), baixa estoque, grava itens com snapshot; depois do commit recalcula os produtos em **sessão separada**. Cancelar devolve estoque e recalcula. `GET /sales` limita a 500 linhas.

### 4.6 Categorização (`app/services/categorizer.py`)

`resolve_category`: 1) keywords locais (normaliza acentos/caixa; vence o match mais longo; palavras-chave de até 4 letras só valem como palavra inteira, para "maca" não casar com "macarrão"; "Mercearia" concorre normalmente e só perde empates) → 2) LLM via OpenRouter (escolhe categoria existente **ou cria uma nova** em PT-BR) → 3) categoria default `Mercearia`. Sem `OPENROUTER_API_KEY`, o passo 2 é pulado. `process_product_background` nunca propaga exceção: em falha o produto fica `ready` na categoria default.

### 4.8 Importação do PDV/ERP (`app/services/importer.py`)

A "integração" pedida pelo professor: o lojista já tem os dados no sistema de caixa/gestão e não pode ter que digitar de novo. Aceita CSV/TXT como sai do ERP (`;`/`,`/tab/`|`, UTF-8 ou Windows-1252, vírgula decimal, `dd/mm/aaaa`, data+hora). Colunas são mapeadas por nome (`SYNONYMS`); o tipo é detectado: **vendas** (data + produto + quantidade) ou **cadastro** (produto + preço/custo/estoque). Regras: vendas importadas são histórico (`Sale.source="import"`) e **não mexem no estoque**; o cadastro define preço, custo e saldo (gera `StockAdjustment`); produtos casam por `sku` e depois por nome normalizado; o mesmo arquivo (hash) não entra duas vezes no mesmo mercado (409, tabela `import_batches`). Produtos novos ficam `processing` e vão para `process_product_background`; existentes são recalculados com trigger `import`. Arquivos de exemplo: `frontend/public/exemplos/*.csv` (gerados para a demo).

### 4.9 Explicação verificada (`app/services/explainer.py`)

Os números vêm de `compute_blend`; o LLM só redige. `verify()` extrai todo número do texto e casa com o fato calculado mais próximo (tolerância 4%); número sem correspondência, ausência da quantidade a comprar ou do ritmo de venda, ou jargão (alpha/prior/blend) → texto do LLM descartado e entra `template_text()` (determinístico). Números do nome do produto ("500ml") são ignorados. Cache em memória por (produto, último log, estoque). Latência típica do LLM: 4–11 s.

### 4.10 Backtest e treino do modelo semanal (`app/services/evaluation.py`)

Usa os dados reais do Favorita (`datasets/favorita/semanal.csv.gz`, 3.214 trechos limpos de 1.729 séries loja × família). Protocolo: **ano de validação** (escolha do modelo) e **ano de teste** (as últimas 52 semanas, resultado final), ambos em walk-forward com re-treino a cada 13 semanas e horizonte de 1 semana. Os baselines entram nas mesmas linhas: média móvel de 4 semanas, a regra anterior do app (EMA com meia-vida de 30 dias), semana passada e mesma semana do ano anterior. O intervalo é **conformal**, calibrado na validação e com a cobertura medida no teste, em vários níveis (50–95%) por faixa de volume. Ao final, treina o modelo de produção com todos os dados e grava `ml_data/weekly_model.txt` + `.meta.json` e `ml_data/evaluation.json`.

Roda em thread na inicialização (~3 min) se `EVAL_VERSION`/`weekly_model.MODEL_VERSION` mudarem, ou via `POST /ml/evaluation/run`.

Resultado no teste: **WAPE 8,06%** contra 10,24% da regra anterior (−21%) e 10,2% da média móvel; viés ≈ 0; cobertura do limite de 95% de 95,1% (de 94,6% a 96,5% por faixa). Abaixo de 5 un/semana o modelo empata com a média móvel (ruído de contagem).

### 4.7 Tempo

O banco guarda UTC; o produto fala em "dia do mercado" (`America/Sao_Paulo`, `APP_TZ`). Use `app/services/clock.py` (`today_local`, `local_date`, `day_bounds`) para janelas e buckets diários. Agrupamentos SQL por dia usam `func.timezone(<tz>, Sale.sold_at)`. Não use `date.today()`/`datetime.now()` crus em lógica de negócio.

## 5. Frontend — arquitetura

- **Rotas** (`src/app`): `/` (landing), `/login`, `/register`, `/dashboard`, `/markets`, `/markets/new`, `/markets/[id]` (produtos, cobertura em dias, venda, importação, painel de aprendizado com explicação), `/markets/[id]/compras` (lista de compras), `/modelo` (validação do modelo), `/laboratorio` (demonstração da banca), `/sales`, `/categories`, `/admin/simulador`.
- **Dev com hot reload**: rode só `db` e `backend` no Docker e o frontend no host: `cd frontend && npm ci && npm run dev` (com `NEXT_PUBLIC_API_URL=http://localhost:8000`). Pare o container `frontend` antes (`docker compose stop frontend`) porque ambos usam a porta 3000.
- Todas as páginas são `"use client"`. Não há middleware; a proteção é feita no cliente (`getToken()` + redirect para `/login`).
- **Auth**: JWT em `sessionStorage` na chave `reponto_token` (vale enquanto a aba estiver aberta, igual ao caixa). `lib/api.ts` (`api`, `setToken`, `ApiError`) injeta o Bearer; **qualquer 401 limpa o token e redireciona para `/login`**. `lib/token.ts` duplica a leitura do token (usada por páginas e pelo `simulator-api.ts`).
- **API client**: `lib/api.ts` centraliza as chamadas e tipos (`lib/types.ts`). `lib/simulator-api.ts` tem seu próprio `fetch` para `/admin/simulator`.
- **i18n**: `lib/i18n.tsx` com dicionários `pt` e `en` e `useI18n().t(key)`. Ao adicionar texto, crie a chave **nos dois idiomas**.
- **UI**: componentes em `components/ui/*` (padrão shadcn sobre Radix + `class-variance-authority`), utilitário `cn` em `lib/utils.ts`. Tema via CSS variables (`globals.css`) com tokens próprios `ponto`, `sun`, `chart-1..5`; fontes Bricolage Grotesque (display), Figtree (sans), IBM Plex Mono (mono); next-themes (claro/escuro). Identidade visual: o "ponto" (`PontoDot`) é o motivo da marca.
- **Polling de `processing`**: ao criar produto a UI recebe `status=processing` e refaz a listagem a cada 2 s enquanto houver produto processando (15 s caso contrário) — ver `markets/[id]/page.tsx`.
- `markets/[id]/page.tsx` (~690 linhas) e `components/simulator/game.tsx` (~600) são os maiores arquivos.
- Não há ESLint configurado nem testes de frontend. `npm run build` roda o type-check do Next.

## 6. Dataset

- **Favorita** (dados reais de uma rede de supermercados do Equador; ativo): o bruto fica em `data/raw/favorita/` (fora do git). `python -m pipeline.app_export` gera `datasets/favorita/` com `semanal.csv.gz` (treino do modelo semanal) e `perfil_diario.csv` (perfil sazonal por categoria, que o `ml.py` usa para produtos sem histórico). Tratamentos: zeros iniciais removidos, séries cortadas em apagões de registro (3+ semanas zeradas numa série de 20+/semana), perfil sem tendência. Ficha e limitações em `datasets/favorita/README.md`.
- **Store Item Demand** (Kaggle, sintético): reserva do `datasets.py`, usado só se o Favorita não estiver presente.
- Trocar de dataset = adapter em `app/services/datasets.py`. O `ml.py` retreina sozinho quando o conjunto de famílias muda (`MODEL_VERSION` = 3).

## 7. Simulador (`backend/simulator/`, rota `/admin/simulador`)

Jogo que **estressa o recomendador real** contra uma "realidade" estocástica independente.

- **Isolado**: nada em `app/` depende dele; é montado por `simulator.register(app)` em `main.py` dentro de `try/except ImportError`, e controlado por `SIMULATOR_ENABLED` (default `True`). Pode ser apagado sem afetar o resto.
- **Sem escrita no banco**: sessões vivem em memória (`store.py`: TTL 6 h, máx. 64), morrem com o processo.
- `engine.py`: loop diário. Dono "obediente" compra o que o `brain` recomenda; demanda real vem do `DemandOracle`; o que excede o estoque vira venda perdida (o sistema só aprende com o que vendeu).
- `ground_truth.py`: demanda = baseline × força do SKU × fator dia-da-semana × fator mês × eventos (onda de calor, feriado, promoção de rival, feira, semana de pagamento) com ruído lognormal + Poisson. Forma funcional **propositalmente diferente** do LightGBM para a nota não ser autorreferente.
- `metrics.py`: MAE, WAPE (diário e semanal "rate WAPE"), viés, nível de serviço, veredito `acertivo|parcial|fora`.
- `llm.py`: coach via OpenRouter com `fallback_coach` local.
- `scenarios.py`: `bairro` (45 clientes/dia), `medio` (180), `grande` (520) e catálogo de 27 SKUs.
- Endpoints: `GET /scenarios`, `POST /sessions`, `POST /sessions/{sid}/step`, `GET /sessions/{sid}`, `GET /sessions/{sid}/report`, `DELETE /sessions/{sid}`. Exigem usuário autenticado (qualquer um, não há papel admin).
- **Laboratório da banca** (`lab.py`, rota `/laboratorio`, endpoints `POST /admin/simulator/lab`, `/lab/{sid}/step`, `/lab/{sid}/shift`, `DELETE /lab/{sid}`): 91 dias em cerca de 1 minuto, com duas lojas gêmeas e a mesma demanda. Uma usa o cérebro real; a outra repõe a média da última semana + 10%. Produtos: cerveja (pico de sexta a domingo, reposição a cada 2 dias), pão (perecível, diário) e leite (controle). O botão "Jogo toda quarta" muda a realidade ao vivo. `scripts/experimentos/rodar_laboratorio.py` roda no terminal. Roteiro de apresentação em `docs/BANCA.md`.

## 8. Convenções para contribuir

- **Backend**: tudo async; sessões via `Depends(get_db)` nas rotas e `SessionLocal()` em tarefas de background. Tipos com `Mapped[...]`/`mapped_column`. Schemas em `schemas.py`, `response_model` em toda rota. Mensagens de erro (`HTTPException.detail`) em PT-BR. Lógica de domínio em `services/`, não nos routers.
- **Recálculo**: ao mudar qualquer coisa que afete estoque, preço de produto, categoria ou configuração do mercado, chame `recalc_product`/`recalc_market_products` com um `trigger` conhecido (e adicione o rótulo em `TRIGGER_LABELS`).
- **Frontend**: componentes client, alias `@/`, textos via `t()`, valores monetários/numéricos via `lib/format.ts` (`fmtMoney`, `fmtNum`).
- **Shell scripts** (`*.sh`) devem ficar com **LF**. Já houve falha de container por CRLF; `.gitattributes` e um `sed` no Dockerfile cobrem isso.
- **Commits**: mensagens em inglês no padrão Conventional Commits (`feat:`, `fix:`, `chore:`), como no histórico.
- Branch atual de trabalho: `pipeline-ml` (inclui `main` com o caixa); principal: `main`.

## 9. Pontos de atenção e dívidas conhecidas

- **Poucos testes**: há `tests/pipeline` (pytest, Fase 1), os testes de integração do caixa (`caixa/README.md`) e os `.cjs` do frontend; não há testes unitários do recomendador. **Sem migrations.** O laboratório, o A/B (`scripts/experimentos/ab_simulador.py`) e `scripts/simular_vendas.py` servem como teste funcional.
- `scripts/simular_vendas.py` tem `--api` com default `http://localhost:8001` (porta antiga); passe `--api http://localhost:8000`.
- O `.env` por padrão traz `OPENROUTER_MODEL=deepseek/deepseek-v4-flash` e uma chave real; o default em código é `deepseek/deepseek-chat`.
- Limitações declaradas do modelo: os padrões são do Equador (o feriado usa o calendário brasileiro em produção); cada série do Favorita é família × loja, não SKU; abaixo de 5 un/semana nenhum método supera a média; o +25% de demanda censurada e o custo de "cliente perdido" (50% do preço) são parâmetros de negócio, não estimados. No jogo (`/admin/simulador`) o pão não é descartado no fim do dia, ao contrário do laboratório.
- `Product.status = "error"` existe nas constantes mas nenhum fluxo o atribui.
- `RecommendationLog.window_start/window_end` são declarados como `Mapped[dt.date]` mas armazenados em coluna `DateTime`.
- `SECRET_KEY` tem default fraco e CORS libera apenas `FRONTEND_ORIGINS` (`localhost`/`127.0.0.1` na porta do frontend). Acessar o app por outro host/IP exige ajustar `FRONTEND_ORIGINS` **e** `NEXT_PUBLIC_API_URL` (+ rebuild).
- Categorias globais e simulador aberto a qualquer usuário: aceitável para PoC, não para multi-tenant real.
- `frontend/tsconfig.tsbuildinfo` está versionado (artefato de build).
- O `README.md` original foi removido no commit inicial; este arquivo é a documentação principal.

## 10. Receitas rápidas

```bash
# Ver se a API responde
curl http://localhost:8000/health

# Criar usuário de teste via API
curl -X POST http://localhost:8000/auth/register -H "Content-Type: application/json" \
  -d '{"name":"Teste","email":"teste@exemplo.com","password":"senha12345"}'

# Popular vendas de demonstração (stdlib only)
python scripts/simular_vendas.py --api http://localhost:8000 --days-back 21 --max-sales 50

# Psql no banco
docker compose exec db psql -U mercado -d mercado

# Forçar retreino do modelo: apagar o volume do modelo e reiniciar o backend
docker compose down && docker volume rm reponto_ml_data && docker compose up -d

# Reiniciar do zero (apaga usuários, vendas e modelo)
docker compose down -v && docker compose up -d --build
```
