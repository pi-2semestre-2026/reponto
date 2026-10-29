const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const source = ts.transpileModule(fs.readFileSync(__dirname + '/../src/lib/api.ts', 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020},
}).outputText;
let status = 409;
let result = {detail: {code: 'duplicate_product', message: 'Produto existente', existing_product: {id: 'existing', name: 'Arroz', price: '10.00', cost: '4.00', unit: 'kg'}}};
let posted;
const context = {
  exports: {}, URL,
  process: {env: {NEXT_PUBLIC_API_URL: 'http://api'}},
  window: {location: {}},
  localStorage: {getItem: () => 'token'},
  fetch: async (url, options) => {
    assert.equal(url, 'http://api/markets/market/products');
    assert.equal(options.headers.Authorization, 'Bearer token');
    posted = JSON.parse(options.body);
    return {status, ok: status === 200, json: async () => result};
  },
};
vm.runInNewContext(source, context);
(async () => {
  const {api, ApiError} = context.exports;
  const payload = {name: 'Arroz', price: 12, cost: 5, stock: 3, unit: 'kg'};
  await assert.rejects(api.createProduct('market', payload), error => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 409);
    assert.equal(error.message, 'Produto existente');
    assert.equal(error.detail.existing_product.price, '10.00');
    assert.equal(error.detail.existing_product.cost, '4.00');
    return true;
  });
  status = 200; result = {id: 'existing', stock_added: true};
  const merged = await api.createProduct('market', {...payload, duplicate_action: 'add_stock', existing_product_id: 'existing'});
  assert.equal(merged.stock_added, true);
  assert.equal(posted.duplicate_action, 'add_stock');
  assert.equal(posted.existing_product_id, 'existing');
  assert.equal(posted.stock, 3);
  await api.createProduct('market', {...payload, duplicate_action: 'create_new'});
  assert.equal(posted.duplicate_action, 'create_new');
  console.log('OK: conflito mantém valores do produto existente e envia decisões explícitas de adicionar ou criar.');
})().catch(error => {console.error(error); process.exitCode = 1;});
