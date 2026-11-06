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
