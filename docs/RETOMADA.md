# Ponto de retomada — 2026-10-29

Sessão interrompida a pedido do usuário. **Leia isto antes de continuar.** Branch `pipeline-ml`,
nada foi enviado (push) nesta sessão. O último commit é um **WIP**: o código novo do backend
**ainda não foi reconstruído nem testado no Docker**, e o frontend ainda não foi adaptado.

## 1. Pedido do usuário (em andamento)

> "Vamos continuar, deixar o app pronto. Lembre de todos os requisitos que mencionei. [...] uma melhora
> dos dados de treinamento e do treinamento em si, para deixar a confiabilidade do app a mais alta
> possível e torná-lo um sistema preditivo assertivo e profissional de verdade."

Requisitos de negócio do professor (ainda valem):
1. **Integração com o sistema de vendas/ERP**: importação CSV (`importer.py`) e o **caixa do colega** (`caixa/`, porta 3301), já no app.
2. **Adaptação por loja** (ex.: "às segundas vende mais"): perfil semanal por loja (`forecast_math.py`) já no app; agora o modelo semanal também usa o histórico do próprio produto.

Preferência do usuário: explicar cada fase em linguagem simples (o que muda de verdade) antes ou junto de aplicar.

## 2. O que foi feito nesta sessão

| Commit | O quê |
|---|---|
| `2d9ad23` | Merge de `origin/main` (caixa do colega, PR #2) em `pipeline-ml`, sem conflitos |
| `3b3ffdd` | O caixa sobe com `docker compose up` comum (antes estava atrás de `profiles: ["caixa"]`) e o `.env.example` foi restaurado |
| `99a628f` | Fase 1 do pipeline completa (Etapas 2–6): `weekly.py`, `metrics.py`, `baseline.py`, `evaluation.py`, `phase1.py`, 21 testes, `reports/fase1_baseline.csv` |
| WIP (último) | Modelo semanal de produção treinado no Favorita (detalhes abaixo) |

**Por que o caixa "não aparecia":** (1) ele só existia em `origin/feat/reponto-caixa`/`origin/main`, não na `pipeline-ml`; (2) o serviço estava atrás de um *profile* do Compose. Ambos resolvidos e verificados: as 4 URLs respondem (8000, 3000, 3301 e 3301/api) e os 5 testes de integração do colega passam.

## 3. Descoberta central (dados reais × sintéticos)

O backtest antigo do app (Store Item, sintético) dizia "LightGBM −45% vs. média móvel". **No Favorita (real) o modelo antigo é PIOR que a média móvel nas séries pequenas**, que são o regime de um SKU de mercadinho: a perda L2 ponderada por volume ignorava as séries pequenas.

A correção é a **perda Tweedie com offset log(nível)**, mais os atributos categoria, feriados, `zero8` e `log_level`. A escolha foi feita no **período de validação** (52 semanas antes do teste) e confirmada no teste:

| | WAPE teste | WAPE validação | Viés |
|---|---|---|---|
| **LightGBM novo (produção)** | **8,50%** | **10,05%** | +0,08% |
| Regra anterior do app (EMA) | 10,70% | 10,84% | −0,93% |
| Média móvel 4 sem. | 10,57% | 10,95% | −0,44% |

Por faixa de volume (teste), LightGBM × média móvel:

| Faixa | LightGBM | Média móvel |
|---|---|---|
| <5 un/sem | 73,0 | 73,0 (empate: ruído irredutível) |
| 5–20 | 43,5 | 45,1 |
| 20–200 | 23,0 | 25,2 |
| 200–2k | 12,3 | 15,9 |
| >2k | 8,1 | 10,0 |

O **intervalo superior de 95%** foi calibrado por conformal na validação e medido no teste: a cobertura foi de **95,3%**, entre 95,2% e 95,6% em todas as faixas. A taxa de vitória sobre a média móvel é de 69,8% das séries.

## 4. Código do commit WIP (o que cada arquivo faz agora)

- `src/pipeline/app_export.py`: `python -m pipeline.app_export` gera `datasets/favorita/semanal.csv.gz` (2,1 MB, 349 mil semanas, 1.729 séries) e `perfil_diario.csv` (índice sazonal sem tendência por categoria do app). Saída determinística. A ficha dos dados está em `datasets/favorita/README.md`.
- `backend/app/services/weekly_model.py` (**novo**): atributos, treino Tweedie, previsão, quantis conformais, feriados do Brasil (`br_national_holidays`), `weekly_history()` e o singleton `weekly_model` (artefato `ml_data/weekly_model.txt` + `.meta.json`).
- `evaluation.py` (reescrito, `EVAL_VERSION=2`): backtest no Favorita (validação + teste, re-treino a cada 13 semanas), baselines inclusive EMA, `by_tier`, `by_category`, `calibration`. **Ao final treina e salva o modelo de produção.** Leva ~141 s localmente.
- `ml.py` (`MODEL_VERSION=3`): modelo sazonal com a categoria como atributo; retreina se o conjunto de famílias muda. `reference_mean()` substitui `overall_mean` no fator do mês.
- `datasets.py`: `FavoritaAdapter`, preferido quando `datasets/favorita/perfil_diario.csv` existe; o Store Item fica como reserva. A ingestão detecta a troca de dataset.
- `forecast_math.py`: `month_factor`/`dataset_weekday_prior` aceitam `category`; nova `model_stock_levels()` (recomendado = demanda do ciclo + margem calibrada; margem = semanal × (q95−1) × √(ciclo/7)).
- `recommender.py`: produto com ≥ 8 semanas completas e modelo carregado segue o caminho **"modelo"** (`final_rate = previsão semanal/7`); senão segue a regra antiga. Novos campos no blend: `forecast_source`, `weekly_forecast`, `weekly_upper`, `model_weeks`, `model_tier`, `model_q95`, …; o log grava `source="modelo_semanal"`.
- `bootstrap.py`: passa `family` ao modelo sazonal e carrega `weekly_model` no boot.
- `simulator/brain.py`: espelha o caminho "modelo"; `use_weekly_model=False` reproduz a regra antiga (A/B).
- `scripts/experimentos/`: `comparar_modelos_validacao_teste.py` (escolha do modelo) e `ab_simulador.py` (A/B no simulador).
- `scripts/popular_demo.py`: gerador de dados de demonstração de uma sessão anterior, até então não versionado.

## 5. O que falta (em ordem)

1. **A/B no simulador** (estava rodando quando a sessão parou). Com o venv do pipeline e as dependências instaladas (`fastapi`, `sqlalchemy`, `pydantic-settings` já instalados no `.venv`):
   ```bash
   export PYTHONPATH=backend DATASET_DIR=$PWD/datasets ML_MODEL_PATH=<pasta temporária>/model.txt
   python -c "from app.services import evaluation as e; e._run_and_save()"   # treina o modelo semanal (~2,5 min)
   python scripts/experimentos/ab_simulador.py 364
   ```
   Critério: com o modelo novo, o nível de serviço/fill rate deve ser ≥ ao anterior com estoque menor ou igual. **Se o serviço cair** (risco: a regra antiga tinha o multiplicador 1,2× extra), reavaliar `model_stock_levels` antes de seguir.
2. **`explainer.py`**: tratar `forecast_source == "modelo"`, sem as frases de peso/alpha nesse caminho. Incluir fatos verificáveis (`semanas_historico`, previsão semanal, `nivel_servico_pct = 95` para o método "modelo") em `NUMERIC_FACTS`, `template_text` e `facts_for_prompt`.
3. **Frontend**:
   - `components/learning-panel.tsx`: mostrar o caminho "modelo" (previsão semanal, limite 95%, semanas de histórico) em vez do blend.
   - `app/modelo/page.tsx` e `lib/types.ts`: exibir `validation_models`, `by_tier`, `calibration`, `improvement_vs_ema_pct`, `by_category`, `samples[].upper`. O dataset agora é o Favorita, e `model.m.items` hoje mostra "itens", que deveria ser "famílias".
   - `lib/i18n.tsx`: chaves novas nos dois idiomas. `ModelScore.key` passa a incluir `"ema"`.
4. **Docker**: `docker compose up -d --build` → o backtest roda em background na 1ª subida (`/ml/evaluation`). Conferir os logs, os testes do caixa (`caixa/README.md`, modo sem IA) e um produto com 8+ semanas, por exemplo via `scripts/popular_demo.py --days 90`.
5. **Docs**: atualizar `CLAUDE.md` (§4.4, §4.10 e §6: dataset Favorita, modelo semanal em produção, novos números) e `docs/CONTEXTO_PROJETO.md`. Marcar no `docs/PLANO_ML.md` as fases cobertas (2: modelo e walk-forward; 4: margem calibrada; 7: parcial, o modelo substitui a regra para produtos com histórico).
6. **Notebooks** `02_agregacao_e_selecao.ipynb` e `03_baseline_media_movel.ipynb` (Fase 1, acadêmicos). O código já existe; falta o notebook explicativo.
7. Perguntar ao usuário sobre o **push** e sobre manter o recorte do Favorita (dados do Kaggle) no repositório.

## 6. Limitações a declarar no trabalho

- Os padrões sazonais vêm do Equador. Em produção o feriado usa o calendário do Brasil, e o perfil por dia da semana vem da própria loja.
- O Favorita é família × loja, não SKU. Isso foi mitigado com atributos sem escala e avaliação por faixa de volume.
- Abaixo de 5 un/semana nenhum método supera a média móvel (ruído de contagem).
- Rupturas escondem demanda (vendas perdidas não são vistas).
- O nível inicial de um produto novo ainda vem dos `baseline_rate` manuais. Falta `transactions.csv` para converter unidades.
- O modelo prevê 1 semana à frente. Em ciclos de 15 a 30 dias a mesma previsão é estendida.
