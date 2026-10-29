const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const source = ts.transpileModule(fs.readFileSync(__dirname + '/../src/lib/market-sort.ts', 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020},
}).outputText;
const context = {exports: {}};
vm.runInNewContext(source, context);
const {nextProductSort, sortMarketProducts, productStockStatus} = context.exports;
const rows = [
  {id:'a', name:'Banana', category_name:'Frutas', price:'10.00', cost:'5.00', stock:'8', min_stock:'2', learned_rate:4, status:'ready'},
  {id:'b', name:'Arroz', category_name:'Mercearia', price:'2.00', cost:'1.00', stock:'1', min_stock:'2', learned_rate:1, status:'ready'},
  {id:'c', name:'Abacaxi', category_name:'Frutas', price:'20.00', cost:'7.00', stock:'0', min_stock:'2', learned_rate:2, status:'ready'},
  {id:'d', name:'Novo', category_name:null, price:'2.00', cost:'1.00', stock:'3', min_stock:'0', learned_rate:0, status:'processing'},
];
const ids = result => Array.from(result, p => p.id).join('');
assert.equal(ids(sortMarketProducts(rows, null)), 'abcd');
let state = nextProductSort(null, 'price');
assert.equal(state.direction, 'asc');
assert.equal(ids(sortMarketProducts(rows, state)), 'bdac', 'Ordenação numérica, com empates estáveis');
state = nextProductSort(state, 'price');
assert.equal(state.direction, 'desc');
assert.equal(ids(sortMarketProducts(rows, state)), 'cabd');
state = nextProductSort(state, 'price');
assert.equal(state, null);
assert.equal(ids(sortMarketProducts(rows, state)), 'abcd', 'Terceiro clique restaura o padrão');
assert.equal(ids(rows), 'abcd', 'Não altera o array recebido da API');
const sort = (key, direction='asc') => ids(sortMarketProducts(rows, {key, direction}));
assert.equal(sort('name'), 'cbad');
assert.equal(sort('category'), 'acbd');
assert.equal(sort('cost'), 'bdac');
assert.equal(sort('stock'), 'cbda');
assert.equal(sort('coverage'), 'cbad');
assert.equal(sort('coverage', 'desc'), 'abcd', 'Cobertura indisponível fica no fim');
assert.equal(sort('status'), 'bcda');
assert.equal(sort('learned_rate'), 'bcad');
assert.equal(productStockStatus(rows[1]), 'low');
assert.equal(nextProductSort({key:'price',direction:'desc'}, 'name').direction, 'asc');
const updated = rows.map(row => row.id === 'a' ? {...row, stock:'0'} : row);
assert.equal(ids(sortMarketProducts(updated, {key:'stock',direction:'asc'})), 'acbd', 'Reaplica ordenação após eventos de estoque');
console.log('OK: oito colunas, valores numéricos, empates, atualização por eventos e ciclo crescente/decrescente/padrão.');
