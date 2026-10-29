# Caixa de mercado

Aplicação independente em HTML, CSS e JavaScript, servida pelo Nginx na porta 3301.
Compartilha somente a API do Reponto: autenticação, mercados, produtos e vendas.
Não precisa de OpenRouter. As operações afetam o banco e o estoque reais conectados
ao backend; prefira um mercado de testes.

## Executar sem IA

Na raiz do repositório, com Docker Desktop em execução:

```sh
docker compose -f docker-compose.yml -f caixa/compose.sem-ia.yml --profile caixa up --build -d
```

Acesse http://localhost:3301. Entre com uma conta do Reponto, escolha o mercado,
busque produtos, adicione ao carrinho e conclua a venda. Aceita quantidades
fracionárias de até três casas decimais para produtos medidos. Produtos por unidade,
pacote, caixa ou dúzia usam quantidades inteiras. As setas avançam uma unidade
(0,1 para kg e litros). Mercados, produtos, estoque e histórico
são atualizados por eventos do PostgreSQL enviados pelo backend via SSE,
somente depois do commit, sem consultas periódicas. O caixa também atualiza ao
voltar à aba ou recuperar a conexão. A atualização preserva o mercado selecionado e o carrinho;
itens sem estoque suficiente são removidos com aviso. Durante a conclusão de
uma venda ou edição da quantidade, o evento fica pendente até a operação terminar ou o campo perder o foco.
Cadastre previamente a conta, o mercado,
os produtos e o estoque no Reponto (http://localhost:3300 na configuração atual).

A chave vazia é aplicada ao contêiner backend, sem editar o `.env`. Isso desativa
a IA também nas outras telas que usam esse backend. Para voltar à configuração
do `.env`, execute `docker compose --profile caixa up -d` sem o arquivo adicional.
Para mudar a porta do caixa, defina `CAIXA_PORT` no `.env` (padrão: 3301).

O Nginx encaminha `/api/` ao backend internamente. Não é necessário configurar
CORS, colocar chave no navegador ou fornecer acesso direto ao PostgreSQL.
A sessão fica em `sessionStorage`, separada do frontend principal, e é apagada
ao sair. Somente os mercados do usuário autenticado aparecem. Não é preciso
sair e entrar novamente para carregar novos mercados.

O cabeçalho oferece modo claro/escuro, idiomas português/inglês e a conta
autenticada (nome, inicial, e-mail e saída). A identidade vem de `/auth/me`.
Tema e idioma usam as mesmas chaves do Reponto, `theme` e `pm_locale`, e são
persistidos no armazenamento local do navegador. Como o caixa e o frontend
principal usam portas diferentes, cada origem guarda suas próprias preferências.
Mudar idioma ou tema preserva o carrinho e os filtros do histórico.

O histórico permite buscar pelo nome do produto (sem diferenciar maiúsculas de
minúsculas) e pela quantidade exata vendida de um item, inclusive fracionada (até três casas decimais). As setas do campo variam
de uma em uma unidade.
Quando combinados, os filtros precisam corresponder ao mesmo item da venda.
A ordenação usa o valor total ou a soma das quantidades da venda, em ordem
crescente/decrescente; o padrão é mais recentes. A consulta é paginada no
backend em grupos de sete vendas, sem o limite anterior de oito registros.
Filtros, ordenação e página são mantidos nas atualizações por eventos e ao
navegar. Uma nova busca ou a opção Limpar filtros volta à primeira página.

## Testar a persistência sem chave

Para validar os listeners e a sincronização sem dependências ou acesso ao banco:

```sh
node caixa/test_sync.cjs
```

Com os serviços acima ativos, execute na raiz:

```sh
docker compose exec -T backend python < caixa/test_integracao.py
docker compose exec -T backend python < caixa/test_events.py
docker compose exec -T backend python < caixa/test_history.py
docker compose exec -T backend python < caixa/test_product_registration.py
```

O teste exige a chave vazia, cria uma conta, mercado e produto exclusivos,
rejeita tentativas sem login e sem estoque, conclui uma venda de 1,250 kg a
R$ 10,00 e consulta o PostgreSQL via SQLAlchemy para conferir:

- `sales`: venda concluída, mercado correto e total R$ 12,50;
- `sale_items`: produto, quantidade, preço e subtotal;
- `products`: estoque reduzido de 5,000 para 3,750;
- API de histórico: a mesma venda está disponível para consulta.

Ao terminar, remove apenas a conta e os dados criados pelo próprio teste,
inclusive em caso de falha. Não testa a interação visual do navegador.
O teste de eventos valida a conexão pelo Nginx, a notificação após venda,
isolamento entre usuários, ausência de evento em rollback e reconexão.

O cadastro manual no Reponto soma estoque quando encontra no mesmo mercado um
produto com o mesmo nome, preço de venda, custo e unidade. Maiúsculas e espaços
duplicados no nome não criam outro produto. Se preço ou custo diferirem, a API
retorna um conflito sem gravar: o formulário permite cancelar, adicionar estoque
ao existente (mantendo seus valores) ou criar outro produto. Unidades diferentes
não são somadas. Os testes de cadastro usam dados exclusivos e também verificam
cadastros simultâneos. O teste do cliente da API pode ser executado em
`frontend/` com `node tests/product-conflict.cjs` após instalar as dependências.

Para conferir manualmente uma venda feita pela tela, copie o ID do comprovante:

```sh
docker compose exec db psql -U mercado -d mercado
```

No psql, substitua `ID_DA_VENDA` pelo UUID exibido:

```sql
SELECT id, market_id, total, status, sold_at
FROM sales WHERE id = 'ID_DA_VENDA';

SELECT si.product_name, si.quantity, si.unit_price, si.subtotal, p.stock
FROM sale_items si
LEFT JOIN products p ON p.id = si.product_id
WHERE si.sale_id = 'ID_DA_VENDA';
```

A tabela de últimas vendas do caixa permite conferir o histórico pela API.
Cada tentativa de venda envia uma chave `Idempotency-Key`. O backend reutiliza
a venda confirmada para essa conta e chave, sem nova baixa de estoque, inclusive
em reenvios simultâneos. A mesma chave com outros itens retorna conflito.
Em falhas de conexão, a tentativa e os itens ficam guardados na sessão da aba;
o botão “Confirmar venda pendente” repete a mesma tentativa. O carrinho fica
bloqueado até a confirmação ou rejeição definitiva. Recarregar a página e entrar
novamente na mesma conta recupera a tentativa. Uma nova venda confirmada usa outra chave.

A conexão SSE usa o token no cabeçalho Authorization e filtra eventos pelo
proprietário. Triggers de `markets`, `products` e `sales` cobrem mudanças feitas
pela API, importações e SQL direto. Transações desfeitas não geram atualização.
Comentários de manutenção da conexão são enviados a cada 15 segundos, sem
consultar as tabelas. Se a conexão cair, a reconexão tenta após três segundos e
recarrega os dados; os eventos não são um histórico persistente. Cada caixa
conectado utiliza uma conexão dedicada ao PostgreSQL.
