# Favorita — recorte para o app

Derivado do dataset **Store Sales – Time Series Forecasting** (Kaggle, Corporación Favorita,
Equador): 54 lojas × 33 famílias de produto, vendas diárias de 2013-01-01 a 2017-08-15.
O CSV bruto (121 MB) fica fora do git, em `data/raw/favorita/`. Estes arquivos são
**gerados por código** e não devem ser editados à mão:

```bash
python -m pipeline.app_export      # requer data/raw/favorita/{train,holidays_events}.csv
```

| Arquivo | Conteúdo | Uso no app |
|---|---|---|
| `semanal.csv.gz` | 349.246 semanas (seg–dom) de 1.729 séries loja × família, a partir da semana em que cada série começa a vender | Treina, valida e calibra o modelo semanal de produção (`backend/app/services/weekly_model.py`, `evaluation.py`) |
| `perfil_diario.csv` | Índice sazonal sem tendência por categoria do app × porte da loja × mês × dia da semana (5.040 linhas, inclui `__all__`) | Molda a sazonalidade da estimativa inicial de produtos sem histórico (`ml.py`) |

## Colunas

`semanal.csv.gz`: `store_nbr`, `family` (Favorita), `category` (categoria do app), `size_bucket`
(quartil de volume da loja, 0 = menor), `week_start` (segunda-feira), `sales` (unidades na semana),
`holiday_days` (feriados nacionais na semana).

`perfil_diario.csv`: `category`, `size_bucket`, `month`, `weekday` (0 = segunda), `index`
(venda do dia ÷ média móvel de um ano da própria série, média das séries), `n_obs`.

## Decisões de tratamento

- **Zeros iniciais removidos:** antes da primeira venda, a série "ainda não existia" (loja não aberta
  ou família não registrada), não é demanda zero. Zeros depois disso ficam: são demanda real.
- **Só semanas completas** (240, de 2013-01-07 a 2017-08-07), sem as bordas parciais.
- **Perfil sem tendência:** cada dia é dividido pela média móvel centrada de um ano da sua série,
  para o crescimento de 2013 a 2017 não aparecer como "efeito do mês". Ficam de fora o 1º de janeiro
  (lojas fechadas) e o mês do terremoto de 16/04/2016.
- **Família → categoria:** mapeamento em `src/pipeline/app_export.py` (`FAMILY_TO_CATEGORY`), cobrindo
  as 14 categorias padrão do app.

## Limitações declaradas

- **País diferente:** os padrões sazonais são do Equador (calendário escolar, feriados). Natal, fim de
  semana e semana de feriado se transferem bem; datas próprias do Brasil (Carnaval, Dia das Mães,
  Black Friday) não estão nos dados. Em produção, o atributo de feriado usa o calendário nacional
  brasileiro, e o perfil por dia da semana é substituído pelo da própria loja assim que há histórico.
- **Granularidade:** cada série é uma família inteira numa loja, não um SKU. O modelo usa atributos
  sem escala (vendas ÷ nível recente da série) e foi avaliado por faixa de volume, inclusive séries
  com menos de 20 unidades por semana, que é o regime de um produto de mercadinho.
- **Termos de uso:** dados da competição do Kaggle. Este recorte é agregado (semanal/índices), não o
  arquivo original. Confirme com o grupo se o repositório pode ficar público com ele.
