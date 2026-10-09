# Núcleo de ML do Reponto — roteiro em fases e Fase 1 detalhada

## Contexto

Hoje o app recomenda estoque a partir de constantes calibradas à mão:

- `baseline_rate` por categoria em `backend/app/services/seed_data.py`;
- um fator sazonal de um LightGBM treinado em 336 linhas agregadas (`backend/app/services/ml.py`);
- multiplicadores fixos do ciclo (0,3 / 0,4 / 1,2 / 2,0) em `backend/app/services/recommender.py`.

O núcleo acadêmico substitui isso por previsão e regra de reposição medidas em dados reais (Favorita). Ele nasce separado em `notebooks/` e `src/pipeline/`. Nas fases 1 a 5 nada muda em `backend/` nem em `frontend/`; o app só é tocado nas fases 6 e 7.

A Fase 1 entrega o chão do projeto: séries semanais confiáveis, um baseline simples e um protocolo de avaliação que a Fase 2 reutiliza sem alterar. Se esse protocolo sair errado (vazamento, semana mal definida, métrica mal calculada), toda comparação posterior fica inválida.

### O que já foi medido em `data/raw/favorita/train.csv` (somente leitura)

| Fato | Valor |
|---|---|
| Linhas e colunas | 3.000.888 linhas; `id, date, store_nbr, family, sales, onpromotion` |
| Período | 2013-01-01 (terça) a 2017-08-15 (terça) |
| Painel | 54 lojas × 33 famílias = 1.782 séries, 1.684 linhas cada |
| Datas ausentes | só 25/12 de 2013 a 2016 |
| Vendas zeradas | 31,3% das linhas diárias; nenhuma negativa; 15,4% fracionárias |
| Semanas completas (segunda a domingo) | 240, de 2013-01-07 a 2017-08-13 |
| Séries sem nenhuma semana zerada | 711 de 1.782 |
| Lojas que abrem depois de jan/2013 | 20, 21, 22, 29, 36, 42, 52, 53 |

Na mesma pasta estão `stores.csv` (cidade, estado, tipo, cluster) e `holidays_events.csv`. O ambiente local tem Python 3.13.7, sem pandas, Jupyter ou pytest, e sem venv.

## Roteiro

| Fase | Entrega | O que ela exige da Fase 1 |
|---|---|---|
| 1 | Séries semanais de 5 a 10 pares loja × família, baseline de média móvel, MAE e MAPE | — |
| 2 | LightGBM com validação walk-forward, comparado ao baseline | As mesmas 52 semanas de teste, o mesmo horizonte e as mesmas funções de métrica |
| 3 | Perfil semanal por loja (proporção das vendas por dia da semana) | O carregador diário de `data.py`; previsão semanal × proporção do dia = previsão diária |
| 4 | Ponto de pedido em dias de cobertura (venda diária prevista × lead time + estoque de segurança) | Os resíduos por série do backtest, porque o estoque de segurança sai do desvio do erro de previsão |
| 5 | Avaliação da recomendação e explicação via LLM | Métricas com a mesma definição do simulador do app |
| 6 | Importação de vendas por CSV no app (primeira fase que toca o app) | — |
| 7 | Modelo treinado substitui as constantes de `seed_data.py` | pandas e numpy nas versões do `backend/requirements.txt` |

Pontos de atenção das fases seguintes, para não virarem surpresa:

- **Fase 4:** o mercado no app tem `replenishment_cycle_days`, mas não tem lead time. No pipeline o lead time é parâmetro; na integração vira campo novo.
- **Fase 5:** o app já chama LLM via OpenRouter com `ChatOpenAI` (`backend/app/services/categorizer.py`). A explicação pode seguir o mesmo padrão.
- **Fase 6:** a API já aceita venda retroativa com `sold_at` (é o que `scripts/simular_vendas.py` usa). A importação reaproveita esse caminho.
- **Fase 7:** há um descasamento de unidade. O Favorita mede unidades da família inteira por loja; `baseline_rate` é unidades por cliente por dia de um SKU típico. A conversão precisa do `transactions.csv` da mesma competição, que ainda não está em `data/raw/favorita/`.

## Fase 1

A ordem abaixo é a de implementação. Cada etapa só começa quando a anterior passou no seu "Pronto quando".

### Decisões fixadas (valem também para a Fase 2)

- **Semana:** segunda a domingo, soma das vendas, rotulada pela segunda-feira. Só as 240 semanas completas.
- **Teste:** as últimas 52 semanas, da semana de 2016-08-15 à de 2017-08-07. É um ano inteiro, para cada sazonalidade aparecer uma vez. Sobram 188 semanas de histórico.
- **Horizonte:** 1 semana à frente, com origem móvel. `horizon` é parâmetro das funções, caso a Fase 4 precise de 2.
- **Baseline oficial:** média das 4 semanas anteriores. k = 1, 8 e 13 entram só como análise de sensibilidade.
- **MAPE:** ignora semanas com venda real zero e informa quantas ignorou.
- **Idioma:** código em inglês, como no resto do repositório; texto dos notebooks em português.

### Arquivos a criar, na ordem

```
pyproject.toml                           etapa 0
.gitignore                               etapa 0 (editar)
src/pipeline/__init__.py                 etapa 0
src/pipeline/config.py                   etapa 0, completado na etapa 3
src/pipeline/data.py                     etapa 1
notebooks/01_exploracao.ipynb            etapa 1
src/pipeline/weekly.py                   etapa 2
tests/pipeline/test_weekly.py            etapa 2
notebooks/02_agregacao_e_selecao.ipynb   etapas 2 e 3
src/pipeline/metrics.py                  etapa 4
tests/pipeline/test_metrics.py           etapa 4
src/pipeline/baseline.py                 etapa 5
src/pipeline/evaluation.py               etapa 5
tests/pipeline/test_baseline.py          etapa 5
notebooks/03_baseline_media_movel.ipynb  etapa 5
src/pipeline/phase1.py                   etapa 6
```

Gerados pelo código, não escritos à mão: `data/processed/favorita_weekly.parquet` e `reports/fase1_baseline.csv`.

A agregação semanal vem antes do recorte das séries porque os critérios do recorte (semanas zeradas, variabilidade semanal) são semanais.

### Etapa 0 — Ambiente e esqueleto

**Arquivos:** `pyproject.toml`, `.gitignore`, `src/pipeline/__init__.py`, `src/pipeline/config.py`.

**O que fazer:**

- Criar o venv com `python -m venv .venv` (a pasta já está no `.gitignore`) e instalar com `pip install -e ".[dev]"`.
- `pyproject.toml` declara o pacote `pipeline` em `src/` e as dependências:

  ```toml
  [project]
  name = "reponto-pipeline"
  version = "0.1.0"
  requires-python = ">=3.12"
  dependencies = ["pandas==2.2.3", "numpy==2.1.3", "pyarrow>=18"]

  [project.optional-dependencies]
  dev = ["jupyterlab", "matplotlib", "pytest"]

  [build-system]
  requires = ["setuptools>=68"]
  build-backend = "setuptools.build_meta"

  [tool.setuptools.packages.find]
  where = ["src"]
  ```

  pandas e numpy ficam nas versões do `backend/requirements.txt`. `lightgbm==4.5.0` entra na Fase 2.
- `.gitignore`: acrescentar `data/processed/` e `.ipynb_checkpoints/`.
- `config.py`: caminhos (`RAW_DIR`, `PROCESSED_DIR`, `REPORTS_DIR`) e as constantes das decisões acima (`TEST_WEEKS = 52`, `HORIZON = 1`, `MA_WINDOW = 4`). `SELECTED_SERIES` fica vazio até a etapa 3.

**Conceitos antes de implementar:**

- **Ambiente virtual e versões fixadas:** o resultado de hoje precisa ser reproduzível daqui a seis meses, e usar as versões do backend evita divergência na Fase 7.
- **Pacote instalado em modo editável:** é o que permite `from pipeline import ...` no notebook, no teste e no script, sem mexer em `sys.path`.
- **Notebook explora, módulo implementa:** todo número que vai para o trabalho sai de uma função em `src/pipeline/`, testável e reutilizável. O notebook chama e interpreta.
- **Dado bruto imutável, dado processado regenerável:** `data/raw/` nunca é editado; `data/processed/` é sempre produto de código.

**Pronto quando:** dentro do venv, `python -c "import pipeline, pandas; print(pandas.__version__)"` imprime `2.2.3`.

### Etapa 1 — Carga e exploração

**Arquivos:** `src/pipeline/data.py`, `notebooks/01_exploracao.ipynb`.

**O que fazer:**

- `data.py`: `load_train()` (datas convertidas, `family` como categoria) e `load_stores()`.
- Notebook:
  - conferir a tabela de fatos do Contexto;
  - venda total por dia e por semana ao longo do tempo;
  - padrão por dia da semana;
  - ranking de famílias e de lojas, com tipo e cluster do `stores.csv`;
  - data da primeira venda por loja × família;
  - zoom em abril e maio de 2016 e nas viradas de ano.

**Conceitos antes de implementar:**

- **Painel em formato longo e granularidade:** uma linha por data × loja × família. "Série" é um par (loja, família).
- **Significado das variáveis:** `sales` é o total de unidades da família naquele dia, fracionário porque há itens vendidos por peso. `onpromotion` é a quantidade de itens da família em promoção.
- **Componentes de uma série temporal:** nível, tendência, sazonalidade (semanal e anual) e ruído.
- **Efeitos de calendário e quebras:** lojas fechadas em 25/12 e 1º/01, pagamento do setor público nos dias 15 e último do mês, terremoto de 16/04/2016 (no `holidays_events.csv` como "Terremoto Manabi").
- **Ausente não é zero:** 25/12 não tem linha. Os zeros têm linha e podem significar "não vendeu", "loja ainda não existia" ou "família não registrada".
- **Demanda intermitente:** 31% das linhas diárias são zero, e isso decide quais séries e quais métricas fazem sentido.

**Pronto quando:** o notebook reproduz todos os valores da tabela de fatos, e você consegue apontar num gráfico a tendência, a sazonalidade anual e pelo menos um evento anômalo.

### Etapa 2 — Agregação semanal

**Arquivos:** `src/pipeline/weekly.py`, `tests/pipeline/test_weekly.py`, primeira parte de `notebooks/02_agregacao_e_selecao.ipynb`.

**O que fazer:** `to_weekly(daily)` devolve uma linha por semana × loja × família, com `week_start`, `sales` (soma), `onpromotion` (soma) e `n_days` (dias com registro). O caminho mais fácil de conferir é calcular `week_start = date − weekday dias`, agrupar por série e descartar o que estiver fora de 2013-01-07 a 2017-08-13.

**Conceitos antes de implementar:**

- **Reamostragem temporal:** variável de fluxo (vendas) se soma; variável de nível (preço, estoque) se tira média.
- **Convenção de semana e rótulo:** o `resample("W")` do pandas fecha no domingo e rotula pelo fim. Escolha uma convenção (aqui, a segunda-feira de início) e mantenha em tudo, senão features e feriados da Fase 2 ficam deslocados em uma semana.
- **Semanas incompletas nas bordas:** os dados começam e terminam numa terça. A primeira e a última semana são parciais e, se ficarem, parecem queda brusca de demanda.
- **Agrupar por série antes de agregar no tempo:** nunca misturar lojas ou famílias na mesma janela.
- **O que a agregação compra e o que custa:** ela tira o padrão de dia da semana e boa parte dos zeros, mas apaga o perfil dentro da semana, que a Fase 3 recupera.

**Pronto quando (testes):**

- cada série tem 240 linhas, sem NaN;
- a soma semanal é igual à soma diária no mesmo intervalo;
- `n_days` é 7 em todas as semanas, exceto 6 nas quatro semanas de Natal.

### Etapa 3 — Recorte das séries

**Arquivos:** segunda parte de `notebooks/02_agregacao_e_selecao.ipynb`, `src/pipeline/config.py` (`SELECTED_SERIES`).

**O que fazer:** aplicar critérios declarados antes de olhar qualquer erro de previsão, e salvar o recorte em `data/processed/favorita_weekly.parquet` (Parquet preserva datas e tipos; CSV devolveria datas como texto).

1. Histórico completo: vende desde jan/2013 e não tem semana zerada.
2. Diversidade de loja (volume e tipo) e de família (perecível × não perecível, estável × volátil).
3. Famílias com equivalente direto nas categorias do app, pensando na Fase 7.

Ponto de partida sugerido pela leitura do CSV, a confirmar no notebook: 4 famílias × 2 lojas = 8 séries. Os valores são média semanal e coeficiente de variação nas 240 semanas.

| Família (categoria do app) | Loja 44 — Quito, tipo A, maior volume | Loja 54 — El Carmen (Manabí), tipo C, pequena |
|---|---|---|
| GROCERY I (Mercearia) | 68.005 / CV 0,18 | 18.467 / CV 0,20 |
| BEVERAGES (Bebidas) | 55.731 / CV 0,36 | 8.971 / CV 0,61 |
| DAIRY (Laticínios e Ovos) | 17.767 / CV 0,19 | 1.261 / CV 0,44 |
| BREAD/BAKERY (Padaria) | 9.682 / CV 0,21 | 1.527 / CV 0,14 |

- **Reservas para chegar a 10:** CLEANING e MEATS, sem semanas zeradas e com CV entre 0,08 e 0,21 nas cinco lojas amostradas.
- **Evitar PRODUCE,** apesar de ser a terceira família em volume: tem de 9 a 91 semanas zeradas e CV perto de 0,8, sinal de falha de registro nos primeiros anos.
- **Evitar HOME CARE** (nenhuma loja com histórico completo) e as 8 lojas que abrem depois de jan/2013.

**Conceitos antes de implementar:**

- **Critério de inclusão definido antes do resultado, e viés de seleção:** escolher séries limpas e volumosas deixa o erro melhor do que seria no catálogo inteiro. Isso entra como limitação declarada no texto.
- **Coeficiente de variação (desvio ÷ média):** medida simples de quão difícil é uma série.
- **Estratificação:** cobrir regimes diferentes vale mais do que oito séries parecidas.

**Pronto quando:** há uma tabela com volume médio, CV, semanas zeradas e tipo de loja de cada série escolhida, a lista está em `config.SELECTED_SERIES` e o Parquet tem (nº de séries × 240) linhas.

### Etapa 4 — Métricas

**Arquivos:** `src/pipeline/metrics.py`, `tests/pipeline/test_metrics.py`.

**O que fazer:** `mae(y, yhat)` e `mape(y, yhat)`. Recomendo incluir também `wape` e `bias` com a mesma definição que o simulador do app já usa em `backend/simulator/metrics.py` (`_aggregate`), para os números das fases 5 e 7 serem comparáveis com os do app.

**Conceitos antes de implementar:**

- **Erro de previsão `e = y − ŷ`:** e por que se usa o valor absoluto (erros para cima e para baixo não podem se cancelar).
- **MAE:** fica na unidade da série, então não se compara entre séries de volume diferente (68 mil unidades por semana contra 1,3 mil).
- **MAPE:** é percentual e comparável entre séries, mas não existe quando o real é zero, explode quando o real é pequeno e é assimétrico. Errar para menos custa no máximo 100%; errar para mais não tem teto, o que favorece modelos que subestimam.
- **Como resumir várias séries:** primeiro a tabela por série. Média de MAPE faz sentido; média de MAE é dominada pelas séries grandes.
- **WAPE (Σ|e| ÷ Σy) e viés (Σ(ŷ − y) ÷ Σy):** complementos que não sofrem com zeros e mostram se o modelo erra sempre para o mesmo lado.

**Pronto quando (testes):**

- `y = [100, 200]` e `ŷ = [110, 180]` dão MAE 15 e MAPE 10%;
- previsão perfeita dá 0;
- um `y` com zero é ignorado no MAPE e contado.

### Etapa 5 — Baseline de média móvel e avaliação

**Arquivos:** `src/pipeline/baseline.py`, `src/pipeline/evaluation.py`, `tests/pipeline/test_baseline.py`, `notebooks/03_baseline_media_movel.ipynb`.

**O que fazer:**

- `moving_average_forecast(weekly, window=4, horizon=1)`: por série, a previsão da semana t é a média das `window` semanas que terminam em t − `horizon`.
- `evaluate(weekly_with_forecast, test_weeks=52)`: devolve a tabela por série (MAE, MAPE, pontos usados) e os resíduos semana a semana do período de teste. Os resíduos são o insumo da Fase 4.
- Notebook: tabela por série, sensibilidade a k, gráfico real × previsto por série e erro ao longo do tempo.

**Conceitos antes de implementar:**

- **Para que serve um baseline:** é a referência que qualquer modelo precisa bater. Sem ele, "MAPE de 12%" não quer dizer nada.
- **Média móvel simples:** supõe nível localmente constante. k pequeno reage rápido e oscila; k grande suaviza e atrasa; k = 1 é a previsão ingênua. Ela fica para trás em tendência e ignora sazonalidade e feriado, que é onde a Fase 2 deve ganhar.
- **Vazamento de dados (look-ahead):** `rolling(k).mean()` na linha t inclui a própria semana t. A previsão de t só pode usar até t − h, então o `shift(h)` vem antes da média. É o erro mais comum e faz o baseline parecer melhor do que é.
- **Divisão temporal:** série temporal não se embaralha. Treino é passado, teste é futuro.
- **Origem e horizonte de previsão, e avaliação com origem móvel:** cada semana de teste é prevista só com o que existia até a semana anterior. A média móvel não tem parâmetro para treinar; na Fase 2 o walk-forward faz o mesmo percurso com re-treino, nas mesmas 52 semanas.
- **Não ajustar no teste:** escolher o k de menor erro nas semanas de teste é usar o teste para calibrar. Por isso k = 4 é fixado antes, e os outros k aparecem como sensibilidade.

**Pronto quando (testes):**

- na série `[10, 20, 30, 40, 50]`, com k = 2 e h = 1, a previsão é `[NaN, NaN, 15, 25, 35]`;
- alterar o valor da semana t não muda a previsão da semana t;
- com k = 1, a previsão é o valor da semana anterior.

No notebook, o esperado é que os maiores erros apareçam perto do Natal e do Ano-Novo. Se não aparecerem, vale investigar antes de seguir.

### Etapa 6 — Execução reproduzível e fechamento

**Arquivos:** `src/pipeline/phase1.py`.

**O que fazer:** `python -m pipeline.phase1` lê o bruto, agrega, filtra `SELECTED_SERIES`, grava `data/processed/favorita_weekly.parquet`, roda o baseline e grava `reports/fase1_baseline.csv` (série, k, MAE, MAPE, pontos).

**Conceitos antes de implementar:**

- **Reprodutibilidade:** um comando regenera tudo a partir do bruto. O notebook deixa de ser a fonte da verdade.
- **Contrato com a Fase 2:** mesmo arquivo de entrada, mesmas semanas de teste, mesmas funções de métrica. A tabela gerada aqui é a linha "baseline" da comparação.

**Pronto quando:** duas execuções seguidas dão números idênticos, e os valores do notebook 03 batem com o CSV.

### Verificação da fase

```
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
python -m pipeline.phase1
```

- `pytest` passa nos três arquivos de teste.
- Os três notebooks rodam do início ao fim com "Restart & Run All".
- `data/processed/favorita_weekly.parquet` tem (nº de séries × 240) linhas.
- `git status` não mostra nada alterado em `backend/` nem em `frontend/`.

### Fora da Fase 1

Features de defasagem, feriado e promoção; LightGBM e walk-forward com re-treino; perfil diário; qualquer alteração no app.
