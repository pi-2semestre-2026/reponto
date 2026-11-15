# Ponto de retomada — atualizado em 2026-11-05

Branch `pipeline-ml`, **não enviada (push)**: o usuário confirma antes de cada push. O roteiro de
apresentação está em `docs/BANCA.md`, e a arquitetura atual em `CLAUDE.md` (§4.4, §4.10, §6, §7).

## Pedido em andamento

> "Deixar o app completamente pronto e de alta qualidade em IA [...] cerveja vende pouco na terça mas
> sexta, sábado e domingo vende muito mais, tem que saber lidar com isso e ser demonstrável na banca [...]
> demonstrar que o treinamento realmente funciona, simulando rapidamente ~3 meses, de forma dinâmica."
> (+ incluir o pão no laboratório)

Requisitos do professor, todos atendidos:
- **Integração com o ERP:** caixa do colega (porta 3301) e importação de CSV.
- **Adaptação por loja:** perfil por dia da semana aprendido das vendas da própria loja.

## Plano em 5 etapas (estado)

1. **Base:** merge do colega, A/B, explicação, painel, `/modelo`, Docker. ✅
2. **Ritmo da semana visível e medido:** perfil com semanas recentes pesando mais, partindo de categoria × loja; prova com números no Favorita (erro diário −45% contra "igual todo dia"). ✅
3. **Laboratório `/laboratorio`:** cerveja, pão e leite; lojas gêmeas com e sem IA; botão "jogo toda quarta". ✅
4. **Mercado de demonstração:** `scripts/popular_demo.py --email banca@reponto.com.br --days 91`. ✅ Popular de novo leva cerca de 1 h (cada venda recalcula os produtos).
5. **Material da banca:** `docs/BANCA.md`. ✅

## Correções de IA feitas nesta etapa (todas com número)

- **Qualidade dos dados de treino:** apagões de registro do Favorita (PRODUCE) faziam a previsão da banana saltar para 1.003/dia no simulador. As séries agora são cortadas nesses apagões, picos acima de 20× ficam fora do treino e há uma trava de [¼, 4×] em produção. Teste: WAPE 8,06% (antes 8,50%), −21% contra a regra anterior, cobertura de 95,1%.
- **Demanda censurada:** com o estoque zerado, a procura do dia é estimada em +25%. Sem isso o pão entrava numa espiral de falta.
- **Perecíveis:** regra do jornaleiro com custo de "cliente perdido" (50% do preço).
- **Margem por ciclo:** separa o erro de nível do ruído diário.
- **A/B do jogo** (36 partidas de 1 ano): atendimento 91,8% contra 90,1%; erro do ritmo 16,1% contra 17,4%; lucro empatado. Com reposição a cada 3 dias no cenário grande, fica levemente pior.
- **Laboratório** (3 sementes de 91 dias): atendimento ~93% contra ~89%; metade dos dias com falta; vendas perdidas ~R$ 2,1 mil contra ~R$ 8,3 mil; lucro +7%.

## Ideias que ficaram de fora (se houver tempo)

- Calendário de datas brasileiras (Dia das Mães, Black Friday) como atributo do modelo.
- Campo "perecível / validade" no cadastro do produto, em vez de inferir pela categoria.
- Testes unitários do recomendador (`forecast_math`) com pytest.
- No jogo `/admin/simulador`, descartar a sobra de pão no fim do dia, como o laboratório faz.
- `caixa/test_sync.cjs` falha (`empty-markets` indefinido) desde os commits de interface do colega no `main` (pasta `caixa/` idêntica ao main): avisar o colega.

## Frente A (dados de treino) — 2026-11-10

Pergunta do usuário: como resolver o problema dos dados de treino que prejudicam a previsão?
Plano: **A** (terminar a limpeza) → **C** (recalibrar a margem com o erro da própria loja) → **B** (dados por item).

Frente A concluída, com cada mudança testada na validação (`scripts/experimentos/frente_a.py`):

| Validação | WAPE | séries < 200/sem | semanas sem promoção | viés |
|---|---|---|---|---|
| atual | 8,89 | 23,77 | 16,37 | +0,89 |
| sem terremoto no treino | 8,91 | 23,75 | 16,34 | +0,90 |
| + promoção bruta | 9,33 | 23,62 | 16,23 | +0,08 |
| + promoção sem escala | 9,04 | 23,57 | 16,73 | +0,56 |

- **Ficou:** semanas do terremoto fora do treino, mas **dentro da calibração**. Na primeira tentativa elas saíram também da calibração e a cobertura caiu para 94,0%. Também ficou o perfil diário sem os apagões, com reingestão por conteúdo.
- **Não ficou:** promoção como atributo. Não ganha de forma clara, e o app não registra promoções; a coluna fica no export.
- **Teste final:** WAPE 8,02% (antes 8,06%), −22% contra a regra anterior, cobertura de 94,9%, viés −0,2%.
- **Conclusão:** a limpeza barata se esgotou. O que falta é dado mais parecido com um SKU de mercadinho (frente B) ou dado da própria loja (frente C).

**Frente B:** o usuário precisa baixar o *Favorita Grocery Sales Forecasting* (Kaggle, por item, ~5 GB) para `data/raw/`. Ele entra como fonte principal do modelo semanal, e o recorte atual continua alimentando o perfil por categoria.

**Frente C:** recalibrar os quantis da margem com os resíduos (previsto × vendido) de cada loja, semana a semana, e mostrar a cobertura da loja no painel e no laboratório.

## Frente B (dados por item) — 2026-11-12 ✅

- **Dados:** `scripts/baixar_favorita_itens.py` (kagglehub; token em `~/.kaggle/access_token.txt`, regras aceitas na conta *pcavalheiroo*) → `pipeline.itens` (125 mi de linhas → 23,4 mi de semanas, 174.595 séries loja × item) → `pipeline.app_export_itens` (4.000 séries estratificadas, 3 MB, `datasets/favorita_itens/`).
- **Decisão na validação** (`scripts/experimentos/frente_b.py`, mesmas séries por item):

| Treino | WAPE validação | WAPE teste |
|---|---|---|
| família (anterior) | 21,78 | 23,49 |
| item | 19,54 | 21,77 |
| família + item | 20,73 | 22,32 |
| EMA (regra anterior) | 21,02 | 24,53 |

  O modelo treinado por família **não se transferia** para produto individual: perdia para a média móvel.
- **Produção** (`TRAINING_DATASETS`): teste por item com WAPE 20,3% contra 23,1% da regra anterior (−12%), vence a média móvel em 76% das séries, cobertura de 94,1%.
- **Bug corrigido na calibração:** uma faixa com poucas linhas usava o resíduo geral, e a regra monotônica inflava as faixas maiores (cobertura de 97–99%). Agora ela empresta da faixa vizinha.
- **A/B do jogo:** atendimento 92,6% contra 90,1%; vendas perdidas −26%; lucro +1%; vence em todos os cenários, inclusive o "grande, a cada 3 dias", que antes perdia.
- **Laboratório:** atendimento ~93% contra ~89%; lucro +5%.
- O mercado da demonstração precisa ser populado **na véspera**: semanas sem venda depois da população derrubam a previsão, e isso é comportamento correto.

**Próximo: frente C** — recalibrar a margem com o erro (previsto × vendido) de cada loja.

## Frente C (margem por loja) — 2026-11-15: testada e NÃO adotada

Ideia: recalibrar o multiplicador da margem de 95% com o erro de cada loja, refazendo as previsões das semanas passadas e encolhendo para o fator geral com k semanas a priori.

- **No Favorita** (`scripts/experimentos/frente_c.py`, 53 lojas): a margem geral já fica, em média, a 1,0–1,1 p.p. da meta em cada loja. O ajuste não melhora (1,1–1,25 p.p.), porque as lojas são da mesma rede.
- **Em lojas diferentes das do treino** (`scripts/experimentos/frente_c_simulador.py`, 9 lojas simuladas): a margem geral cobre **93,6%** da procura real (a 1,7 p.p. da meta). Ajustada com as semanas 9–30, ela cobre só 89,1% (5,9 p.p.). O ajuste aprendeu com meses calmos e encolheu a margem antes de dezembro.
- **Conclusão:** o erro muda ao longo do ano, e calibrar com poucos meses de uma loja é arriscado. A calibração geral (um ano inteiro de 4.000 séries) se transfere bem e fica.
- **Possível evolução:** acompanhar a cobertura medida em cada loja e só *aumentar* a margem com evidência longa (≥ 1 ano), sem nunca reduzi-la.
