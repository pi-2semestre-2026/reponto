# Roteiro da banca — Reponto

Apresentação de 15 a 20 minutos. Cada bloco diz **o que mostrar**, **o que falar** (em linguagem
simples) e **o que aquilo prova**. Os números são do ambiente atual e podem ser regenerados
pelos comandos do fim.

## 0. Preparação (antes da banca)

```bash
docker compose up -d --build                     # app (3000), API (8000), caixa (3301)
# esperar o backend treinar o modelo (~3 min): http://localhost:3000/modelo deixa de mostrar "Treinando"
python scripts/popular_demo.py --email banca@reponto.com.br --days 91   # mercados com 3 meses de vendas
```

- Login: `banca@reponto.com.br` / `reponto123`.
- Deixe abertas quatro abas:
  1. `/modelo`
  2. `/laboratorio`
  3. o mercado "Mercadinho Dona Maria"
  4. o caixa (`localhost:3301`)
- Plano B sem internet: a IA de texto cai sozinha para o texto padrão verificado, e tudo o mais funciona offline.

## 1. O problema (1 min)

> "O dono de um mercadinho decide quanto comprar no olho. Se compra pouco, falta produto e o cliente
> vai embora. Se compra demais, o dinheiro fica parado ou o produto estraga. E as vendas mudam com o dia
> da semana: cerveja quase não sai na terça, mas no sábado vende o dobro."

## 2. O app no dia a dia (3 min): mostra que o lojista consegue usar

1. **Caixa (3301):** fazer uma venda de cerveja. Ela aparece na hora no Reponto, por eventos do banco.
   - *Prova:* integração com o sistema de vendas (requisito do professor). Também existe a importação de CSV do ERP, em Mercados → Importar.
2. **Mercado → Cerveja → "Como a IA calculou":**
   - **Ritmo da semana:** o gráfico "Aprendido nesta loja × Ponto de partida (categoria)" mostra sexta a domingo bem acima da média e a terça abaixo.
     > "Ninguém digitou isso. A IA tirou das vendas desta loja."
   - **Previsão do modelo treinado:** a previsão da semana e o "limite 95%".
     > "Em 95 de cada 100 semanas a venda fica abaixo desse limite: a margem de segurança cobre até ele."
   - **Explicação em português:** é verificada número a número contra o cálculo, então a IA de texto não pode inventar números.
3. **Lista de compras:** o quanto comprar de cada produto e por quê.

## 3. O modelo funciona? (4 min): `/modelo`, prova com dados reais

> "Não testamos com dados inventados. Usamos 4,5 anos de vendas reais de 54 supermercados (dataset
> Favorita): 1.729 séries de produto × loja."

| O que mostrar | Número | O que significa |
|---|---|---|
| Erro do modelo × regra anterior do app | **8,06% × 10,24% (−21%)** | Erra 1/5 a menos que a regra antiga |
| Erro × média móvel (o que faria uma planilha) | 8,06% × 10,20% | Ganha da planilha |
| Margem de 95% acerta | **95,1%** das semanas | A margem de segurança é honesta, nem exagerada nem curta |
| Por volume (tabela) | vence em todas as faixas; empata abaixo de 5/semana | Honestidade: produto que vende 2 por semana é quase sorte |
| Validação × teste | escolhido no ano de validação, confirmado no ano de teste | O número não é otimista: o teste ficou guardado |

**Prova extra do "ritmo da semana"** (Fase 3, `scripts/experimentos/perfil_dia_semana.py`): distribuir a
venda da semana pelos dias com o padrão de cada produto e loja erra **12,2%**. "Igual todo dia" erra
**22,3%**, e um padrão único para todas as lojas, **16,6%**. Ou seja: aprender o ritmo de cada loja
**corta o erro diário pela metade**.

## 4. A IA aprendendo ao vivo (5 min): `/laboratorio`, o momento principal

1. Clique em **Começar a demonstração**. Explique as três realidades (cartões) e as duas lojas gêmeas: mesmos clientes, uma com o Reponto e outra "no olho".
2. Rode em **1 dia**. Aponte:
   - **Cerveja, ritmo da semana:** as barras laranja (IA) se aproximam das cinzas (realidade). Até a semana 3 a IA já vê o pico de sábado e a terça fraca.
   - **Previsão do dia:** a linha da IA sobe no fim de semana e desce na terça; a da loja "sem IA" é reta.
   - **Pão:** começa errado (o padrão da categoria subestima esta padaria) e corrige em cerca de 3 semanas. Quando esgota, o sistema entende que a procura era maior do que a venda registrada.
3. Por volta do **dia 49**, clique em **"Jogo toda quarta"**:
   > "Começou o campeonato. A quarta-feira passa a vender 2,6 vezes mais. Ninguém avisa o sistema."

   A curva de aprendizado sobe e volta a cair. A quarta da IA vai subindo semana a semana.
   > "Ela não muda no primeiro dia de propósito: precisa de algumas semanas para ter certeza de que não foi um acaso."
4. Por volta do **dia 63**, o selo muda para **"modelo treinado"**: com 8 semanas de histórico, o modelo validado assume.
5. **Placar final** (três execuções de 91 dias, média):

| | Com Reponto | Sem IA |
|---|---|---|
| Procura atendida | ~93% | ~89% |
| Dias com falta de produto | ~45 | ~90 |
| Vendas perdidas | ~R$ 2,1 mil | ~R$ 8,3 mil |
| Lucro | **+7%** | — |

## 5. Decisões de engenharia que valem perguntas (2 min)

- **Validação sem vazamento:** cada previsão só usa semanas anteriores, e o modelo foi escolhido na validação e reportado no teste.
- **Qualidade dos dados:** encontramos semanas de "apagão de registro" no Favorita (a série zera por semanas e volta). Elas ensinavam ao modelo saltos de 50× e foram tratadas como falha, não como demanda zero.
- **Perecíveis:** o pão não mira 95% de atendimento. A regra do jornaleiro equilibra o custo de jogar fora com o de perder o cliente.
- **Demanda censurada:** quando esgota, a venda registrada é só um piso da procura. Sem corrigir isso, o sistema entra numa espiral de comprar cada vez menos.
- **Trava de sanidade:** a previsão nunca passa de 4× (nem fica abaixo de ¼) do ritmo recente do produto.

## 6. Limitações (dizer antes que perguntem)

- Os dados de treino são do Equador. Natal e fim de semana se transferem bem, mas Carnaval, Dia das Mães e Black Friday não estão nos dados. Em produção, o feriado usa o calendário do Brasil e o ritmo da semana vem da própria loja.
- O Favorita mede famílias de produto por loja, não itens. Por isso o modelo usa atributos sem escala e foi avaliado por faixa de volume.
- O nível inicial de um produto novo ainda vem de referências por categoria; ele se ajusta com as vendas.
- O laboratório usa um mercado simulado. O ganho real precisa ser confirmado num piloto com uma loja de verdade.

## Comandos para regenerar os números

```bash
python -m pipeline.phase1                                  # Fase 1 (baseline)
python -m pipeline.app_export                              # recorte do Favorita para o app
python scripts/experimentos/perfil_dia_semana.py           # prova do ritmo da semana
PYTHONPATH=backend DATASET_DIR=$PWD/datasets ML_MODEL_PATH=$PWD/backend/ml_data/model.txt \
  python scripts/experimentos/rodar_laboratorio.py 7 49    # laboratório no terminal
# backtest completo: POST /ml/evaluation/run (ou a página /modelo)
```
