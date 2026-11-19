# Favorita por item — recorte para o app (treino do modelo semanal)

Derivado do dataset **Corporación Favorita Grocery Sales Forecasting** (Kaggle, 2017): vendas
diárias de cerca de 4.100 produtos em 54 lojas de uma rede do Equador, de 2013-01-01 a 2017-08-15
(125 milhões de linhas). O bruto fica fora do git, em `data/raw/favorita_itens/`. Estes arquivos
são **gerados por código**:

```bash
pip install -e ".[dados]"
python scripts/baixar_favorita_itens.py     # token do Kaggle em ~/.kaggle/access_token + regras aceitas
python -m pipeline.itens                    # 5 GB -> semanal por loja x item (data/processed/, ~10 min)
python -m pipeline.app_export_itens         # amostra -> datasets/favorita_itens/semanal.csv.gz
```

| Arquivo | Conteúdo | Uso no app |
|---|---|---|
| `semanal.csv.gz` | 602.146 semanas de **4.000 séries loja × item** (9.278 trechos), 14 categorias | Treina, valida e calibra o modelo semanal de produção (`evaluation.py` → `weekly_model.py`) |

O recorte por família (`datasets/favorita/`) continua sendo usado pelo perfil sazonal por categoria (`ml.py`).

## Por que trocar o treino para item

Na validação (`scripts/experimentos/frente_b.py`), avaliando sempre nas mesmas séries por item:

| Treino | WAPE validação | WAPE teste | Viés teste |
|---|---|---|---|
| Famílias (modelo anterior) | 21,78% | 23,49% | +1,3% |
| **Itens** | **19,54%** | **21,77%** | −1,7% |
| Famílias + itens | 20,73% | 22,32% | −0,3% |
| Regra anterior do app (EMA) | 21,02% | 24,53% | 0,0% |
| Média móvel 4 semanas | 21,33% | 24,83% | +0,2% |

O modelo treinado por família **não se transfere** para um produto individual: no nível de item ele
perde para a média móvel. Treinado por item, ele vence a média móvel e a regra anterior em todas as
faixas a partir de 5 un/semana.

## Colunas

`store_nbr`, `item_nbr`, `family`, `perishable` (0/1, do `items.csv`), `segment` (trecho entre períodos
fora da prateleira), `category` (categoria do app), `size_bucket` (quartil de volume da loja),
`week_start` (segunda-feira), `sales` (unidades na semana), `holiday_days`, `shock` (semanas do
terremoto de 2016: fora do treino, dentro da calibração).

## Regras de qualidade (decididas antes de olhar qualquer erro)

- **Dia sem linha = zero, só enquanto o item está ativo** na loja (da primeira à última semana com venda).
  O arquivo do Kaggle só tem linhas de dias com venda; antes e depois do período ativo, não há demanda a medir.
- **Devoluções** (venda negativa) viram zero antes de somar a semana.
- **Fora da prateleira:** 4+ semanas zeradas num item que vende 3+/semana (ou 12+ semanas num item mais
  lento) é item fora de linha ou em falta, não procura zero. A série é cortada ali.
- **Amostra estratificada** por venda semanal mediana, com semente fixa: 1.000 séries abaixo de 5/semana,
  1.400 de 5 a 20, 1.200 de 20 a 200 e 400 acima de 200, priorizando o regime de um mercadinho.
  Séries elegíveis: ativas por pelo menos 40 semanas (153.476 de 174.592).

## Limitações

- Mesma rede e país do recorte por família (Equador). O feriado usa o calendário brasileiro em produção.
- Lojas de rede maiores que um mercadinho: o modelo usa atributos sem escala, e o resultado é reportado por faixa de volume.
- Itens que esgotaram aparecem com venda baixa (o arquivo não informa estoque). A correção de demanda
  censurada do app não se aplica ao treino.
- **Termos de uso:** dados de competição do Kaggle. Este recorte é uma amostra agregada por semana, não o
  arquivo original. Confirme com o grupo antes de deixar o repositório público.
