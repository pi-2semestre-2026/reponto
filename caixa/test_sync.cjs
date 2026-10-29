// Testa a sincronização sem navegador, dependências ou alterações no banco.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() {this.children = []; this.value = ''; this.hidden = false; this.textContent = ''; this.dataset = {};}
  get options() {return this.children;}
  replaceChildren(...children) {this.children = children;}
  append(...children) {this.children.push(...children);}
  closest() {return false;}
  setAttribute(name, value) {this[name] = value;}
  toggleAttribute(name, enabled) {this[name] = enabled;}
  contains(node) {return node === this || this.children.some(child => child.contains(node));}
}
const elements = new Map();
const events = {};
const saved = new Map();
const sessionSaved = new Map();
const staticTitle = new Element(); staticTitle.dataset.i18n = 'Últimas vendas do mercado';
const languageButtons = ['pt', 'en'].map(locale => {const node = new Element(); node.dataset.locale = locale; return node;});
const context = vm.createContext({
  console, crypto: require("node:crypto").webcrypto,
  AbortController, TextDecoder, TextEncoder, URLSearchParams, Event,
  localStorage: {getItem: key => saved.get(key), setItem: (key, value) => saved.set(key, value)},
  sessionStorage: {getItem: key => sessionSaved.get(key) || '', setItem: (key, value) => sessionSaved.set(key, value), removeItem: key => sessionSaved.delete(key)},
  document: {
    hidden: false, activeElement: null, documentElement: new Element(),
    querySelectorAll(selector) {return selector === '[data-i18n]' ? [staticTitle] : selector === '[data-locale]' ? languageButtons : [];},
    getElementById(id) {if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id);},
    createElement: () => new Element(),
    addEventListener(name, fn) {events[name] = fn;},
  },
  window: {addEventListener(name, fn) {events[name] = fn;}, dispatchEvent(event) {events[event.type]?.(event);}},
  setTimeout() {}, clearTimeout() {},
});
const run = code => vm.runInContext(code, context);
run(fs.readFileSync(__dirname + '/public/preferences.js', 'utf8'));
run(fs.readFileSync(__dirname + '/public/app.js', 'utf8'));
run(`
  const originalRender = render;
  let renders = 0;
  render = () => {renders++;};
  token = 'test-session';
  let marketsData = [];
  let productsData = [];
  let calls = 0;
  api = async path => {
    calls++;
    if (path === '/markets') return marketsData;
    if (path.includes('/products')) return productsData;
    if (path.startsWith('/sales/history?')) return {items: [], total: 0, page: 1};
    return [];
  };
`);

(async () => {
  assert.equal(run("quantityWithUnit(3, 'unidade')"), '3 unidades');
  assert.equal(run("quantityWithUnit(1, 'unidade')"), '1 unidade');
  assert.equal(run("quantityWithUnit(4.3, 'g')"), '4,3 gramas');
  assert.equal(run("quantityWithUnit(5.6, 'kg')"), '5,6 quilogramas');
  assert.equal(run("quantityWithUnit(1, 'L')"), '1 litro');
  assert.equal(run("quantityWithUnit(2, 'ml')"), '2 mililitros');
  assert.equal(typeof events.focus, 'function');
  assert.equal(typeof events.focusout, 'function');
  assert.equal(/setInterval\(/.test(fs.readFileSync(__dirname + '/public/app.js', 'utf8')), false, 'Sem polling periódico');
  assert.equal(typeof events.online, 'function');
  assert.equal(typeof events.visibilitychange, 'function');
  await run('syncData()');
  assert.equal(elements.get('empty-markets').hidden, false);

  run(`marketsData = [{id: 'a', name: 'Mercado A'}]; productsData = [{id: 'p', name: 'Arroz', stock: '5'}];`);
  await run('syncData()');
  assert.equal(run(`$('market').value`), 'a');
  assert.equal(run('products.length'), 1);
  assert.equal(elements.get('empty-markets').hidden, true);

  run(`cart.set('p', 2); marketsData = [{id: 'b', name: 'Novo mercado'}, ...marketsData];`);
  await run('syncData()');
  assert.equal(run(`$('market').value`), 'a', 'Preserva a seleção quando outro mercado é criado');
  assert.equal(run(`cart.get('p')`), 2, 'Preserva o carrinho');
  const rendersBefore = run('renders');
  await run('syncData()');
  assert.equal(run('renders'), rendersBefore, 'Dados iguais não recriam os controles');

  run(`productsData = [{id: 'p', name: 'Arroz', stock: '1'}];`);
  await run('syncData()');
  assert.equal(run('cart.size'), 0);
  assert.match(elements.get('message').textContent, /estoque/);

  const callsBefore = run('calls');
  run('busy = true'); await run('syncData()'); run('busy = false');
  run('document.hidden = true'); await run('syncData()'); run('document.hidden = false');
  run('document.activeElement = {closest: () => true}'); await run('syncData()');
  run('document.activeElement = null');
  assert.equal(run('calls'), callsBefore, 'Aguarda venda, aba oculta e edição');

  run(`const originalApi = api; api = async () => {throw new Error('Offline');};`);
  await run('syncData()');
  assert.equal(run('syncing'), false, 'Libera sincronização após falha');
  run('api = originalApi');
  await run('syncData()');

  run(`marketsData = [{id: 'b', name: 'Novo mercado'}]; cart.set('p', 1);`);
  await run('syncData()');
  assert.equal(run(`$('market').value`), 'b');
  assert.equal(run('cart.size'), 0, 'Não transporta carrinho para outro mercado');

  run(`api = async path => {if (path === '/markets') {$('market').value = 'outro'; return marketsData;} return [];};`);
  await run('syncData()');
  assert.equal(run(`$('market').value`), 'outro', 'Descarta resposta se seleção mudou durante a consulta');
  run('busy = true; requestSync()');
  assert.equal(run('syncPending'), true, 'Evento durante venda fica pendente');
  run('busy = false; api = originalApi');
  await run('syncData()');
  assert.equal(run('syncPending'), false, 'Sincroniza evento pendente ao liberar edição');
  run(`
    let streamReads = 0;
    let cancelled = false;
    fetch = async (url, options) => {
      if (url !== '/api/events' || options.headers.Authorization !== 'Bearer test-session') throw new Error('Autenticação SSE inválida');
      const chunks = ['event: ready\\ndata: {}\\n\\nevent: cha', 'nge\\ndata: {}\\n\\n: keepalive\\n\\n'];
      return {ok: true, status: 200, body: {getReader: () => ({
        read: async () => streamReads < chunks.length ? {value: new TextEncoder().encode(chunks[streamReads++]), done: false} : {done: true},
        cancel: async () => {cancelled = true;}, releaseLock() {},
      })}};
    };
  `);
  await run('startEvents()');
  await run('syncData()');
  assert.equal(run('streamReads'), 2, 'Lê eventos mesmo fragmentados em blocos');
  assert.equal(run('cancelled'), true, 'Libera o leitor ao encerrar a conexão');
  assert.equal(run('eventController'), undefined);
  run(`
    let historyParams;
    api = async path => {
      historyParams = new URLSearchParams(path.split('?')[1]);
      return {items: Array.from({length: historyParams.get('page') === '3' ? 1 : 7}, (_, i) => ({
        id: String(i), total: '10', sold_at: '2026-10-26T12:00:00Z', status: 'completed',
        items: [{product_name: 'Arroz', quantity: '1.25', unit: 'kg'}],
      })), total: 15, page: Number(historyParams.get('page'))};
    };
    $('market').value = 'a'; historyMarket = 'a'; historyPage = 1;
    $('history-product').value = 'Arroz'; $('history-quantity').value = '2'; $('history-order').value = 'value_desc';
  `);
  await run('loadHistory()');
  assert.equal(elements.get('history').children.length, 7);
  assert.equal(elements.get('history').children[0].children[0].children[1].textContent, 'Arroz · Quantidade: 1,25 quilogramas');
  run(`caixaUI.setLocale('en'); caixaUI.setTheme('dark');`);
  assert.equal(staticTitle.textContent, 'Latest store sales');
  assert.equal(elements.get('history').children[0].children[0].children[1].textContent, 'Arroz · Quantity: 1.25 kilograms');
  assert.equal(run(`$('history-product').value`), 'Arroz', 'Idioma não muda os filtros');
  assert.equal(saved.get('pm_locale'), 'en');
  assert.equal(saved.get('theme'), 'dark');
  assert.equal(run('document.documentElement.dataset.theme'), 'dark');
  assert.equal(elements.get('theme-sun').hidden, false);
  assert.equal(elements.get('theme-moon').hidden, true);
  const html = fs.readFileSync(__dirname + '/public/index.html', 'utf8');
  for (const [, key] of html.matchAll(/data-i18n(?:-placeholder|-aria|-title)?="([^"]+)"/g)) {
    assert.notEqual(run(`caixaUI.t(${JSON.stringify(key)})`), key, `Tradução estática ausente: ${key}`);
  }
  assert.equal(run("caixaUI.t('Estoque insuficiente para Banana: 2 disponível')"), 'Insufficient stock for Banana: 2 available');
  run(`caixaUI.setUser({name: 'Demo', email: 'demo@example.com'});`);
  assert.equal(elements.get('user-name').textContent, 'Demo');
  assert.equal(elements.get('user-initial').textContent, 'D');
  assert.equal(elements.get('user-email').textContent, 'demo@example.com');
  assert.equal(elements.get('account-menu').hidden, false);
  run(`caixaUI.setUser(null); caixaUI.setLocale('pt'); caixaUI.setTheme('light');`);
  assert.equal(elements.get('account-menu').hidden, true);
  assert.equal(staticTitle.textContent, 'Últimas vendas do mercado');
  console.log('OK: modos claro/escuro, idioma completo, preferências persistidas e identificação da conta.');
  run(`$('history-next').onclick()`);
  await new Promise(setImmediate);
  assert.equal(run('historyPage'), 2);
  assert.equal(run("historyParams.get('product')"), 'Arroz');
  assert.equal(run("historyParams.get('quantity')"), '2');
  assert.equal(run("historyParams.get('order')"), 'value_desc');
  await run('loadHistory()');
  assert.equal(run('historyPage'), 2, 'Atualização por evento preserva página e filtros');
  run(`$('history-next').onclick()`);
  await new Promise(setImmediate);
  assert.equal(elements.get('history').children.length, 1, 'Última página contém só o restante');
  assert.equal(elements.get('history-next').disabled, true);
  run(`$('history-clear').onclick()`);
  await new Promise(setImmediate);
  assert.equal(run('historyPage'), 1);
  assert.equal(run("historyParams.get('product')"), null);
  assert.equal(run("historyParams.get('quantity')"), null);
  assert.equal(run("historyParams.get('order')"), 'recent');
  run(`$('history-product').value = 'Banana'; $('history-product').oninput()`);
  assert.equal(run('historyPage'), 1, 'Nova busca volta à primeira página');
  run(`cart.set('p', 2); caixaUI.setLocale('en'); caixaUI.setTheme('dark');`);
  assert.equal(run("cart.get('p')"), 2, 'Mudar idioma e tema preserva carrinho');
  run(`
    products = [
      {id:'u',name:'Unit',unit:'unidade',stock:'10',price:'2'},
      {id:'k',name:'Kg',unit:'kg',stock:'10',price:'2'},
      {id:'g',name:'Gram',unit:'g',stock:'10',price:'2'}
    ];
    cart = new Map([['u',2],['k',1.25],['g',4.3]]);
    busy = false; loading = false; originalRender();
  `);
  const inputs = elements.get('cart').children.map(row => row.children[1].children[0]);
  assert.deepEqual(inputs.map(input => input.step), ['1','0.1','1']);
  inputs[0].value = '1.25'; inputs[0].onchange();
  assert.equal(run("cart.get('u')"), 2, 'Produtos contáveis rejeitam frações');
  inputs[1].value = '1.251'; inputs[1].onchange();
  assert.equal(run("cart.get('k')"), 1.251, 'Medidas preservam três casas decimais digitadas');
  run(`
    $('history-quantity').value = '1.250';
    $('history-quantity').validity = {valid: false, stepMismatch: true};
  `);
  assert.equal(run('validHistoryQuantity()'), true, 'Busca fracionada ignora apenas o stepMismatch das setas');
  run(`$('history-quantity').value = '0.0001'`);
  assert.equal(run('validHistoryQuantity()'), false);
  run(`$('history-quantity').value = ''; currentUserId = 'owner'; busy = false; loading = false;
    cart = new Map([['p', 1.25]]); $('market').value = 'a';
    let attempts = [];
    startEvents = async () => {};
    api = async (path, body, key) => {
      if (path === '/sales') {
        attempts.push({body: JSON.stringify(body), key});
        if (attempts.length === 1) throw new Error('Resposta perdida');
        return {id:'same-sale',total:10,items:[]};
      }
      if (path === '/auth/me') return {id:'owner',name:'Demo',email:'demo@example.com'};
      if (path === '/markets') return [{id:'a',name:'Test'}];
      if (path.includes('/products')) return [];
      return {items:[],total:0,page:1};
    };
    flushSync = () => {};
  `);
  await run(`$('checkout').onclick()`);
  assert.ok(sessionSaved.get('caixa-pending-sale'), 'Tentativa persistida após resposta perdida');
  assert.equal(run('pendingSale.body.items[0].quantity'), 1.25);
  run(`products = [{id:'p',stock:'0'}]; reconcileCart()`);
  assert.equal(run("cart.get('p')"), 1.25, 'Atualização do estoque não altera uma tentativa pendente');
  run(`pendingSale = null; cart.clear()`);
  await run('start()');
  assert.equal(run('pendingSale.key === attempts[0].key'), true, 'Recarregar recupera a tentativa da mesma conta');
  assert.equal(run("cart.get('p')"), 1.25);
  await run(`$('checkout').onclick()`);
  assert.equal(run('attempts.length'), 2);
  assert.equal(run('attempts[0].key === attempts[1].key'), true);
  assert.equal(run('attempts[0].body === attempts[1].body'), true);
  assert.equal(run('pendingSale'), null);
  assert.equal(sessionSaved.has('caixa-pending-sale'), false);
  console.log('OK: busca fracionada e reenvio persistido com a mesma chave e os mesmos itens.');
  run(`caixaUI.setUser({name: 'Demo', email: 'demo@example.com'}); $('logout').onclick()`);
  assert.equal(run('token'), '');
  assert.equal(elements.get('account-menu').hidden, true, 'Sair remove a identificação da conta');
  assert.equal(saved.get('theme'), 'dark', 'Preferência de tema permanece após sair');
  assert.equal(saved.get('pm_locale'), 'en', 'Preferência de idioma permanece após sair');
  console.log('OK: histórico com filtros persistentes, 7 vendas por página, navegação e limpeza.');
  console.log('OK: listeners, novos mercados, carrinho, estoque, edição, recuperação e respostas obsoletas.');
})().catch(error => {console.error(error); process.exitCode = 1;});
