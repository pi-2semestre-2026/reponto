const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

const source = ts.transpileModule(fs.readFileSync(__dirname + '/../src/lib/events.ts', 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020},
}).outputText;
const settle = async () => {for (let i = 0; i < 4; i++) await new Promise(setImmediate);};

function setup(status = 200) {
  const events = new Map();
  const connections = [];
  const timers = new Map();
  let token = 'test-token';
  const context = {
    exports: {}, AbortController, TextDecoder, console,
    require: name => name === './api' ? {API_URL: 'http://api', setToken: value => {token = value;}} : {getToken: () => token},
    document: {
      hidden: false,
      addEventListener: (name, fn) => events.set(name, fn),
      removeEventListener: name => events.delete(name),
    },
    window: {
      location: {href: '/sales'},
      addEventListener: (name, fn) => events.set(name, fn),
      removeEventListener: name => events.delete(name),
    },
    setTimeout: (fn, ms) => {assert.equal(ms, 3000); const id = {}; timers.set(id, fn); return id;},
    clearTimeout: id => timers.delete(id),
    fetch: async (url, options) => {
      assert.equal(url, 'http://api/events');
      assert.equal(options.headers.Authorization, 'Bearer test-token');
      const connection = {signal: options.signal};
      const body = new ReadableStream({start(controller) {
        connection.push = value => controller.enqueue(new TextEncoder().encode(value));
        connection.close = () => controller.close();
        options.signal.addEventListener('abort', () => controller.error(new Error('Aborted')));
      }});
      connections.push(connection);
      return {status, ok: status === 200, body};
    },
  };
  vm.runInNewContext(source, context);
  return {context, connections, timers, events, subscribe: context.exports.subscribeEvents};
}

(async () => {
  const h = setup();
  let refreshes = 0;
  const stop = h.subscribe(async () => {refreshes++;});
  await settle();
  assert.equal(h.connections.length, 1);
  assert.equal(refreshes, 0, 'Não consulta vendas sem receber evento');
  assert.equal(h.timers.size, 0, 'Conexão ativa não agenda polling');
  h.connections[0].push('event: rea');
  h.connections[0].push('dy\ndata: {}\n\n');
  await settle();
  assert.equal(refreshes, 1, 'ready carrega dados após assinatura');
  h.connections[0].push(': keepalive\n\n');
  await settle();
  assert.equal(refreshes, 1, 'Heartbeat não recarrega vendas');
  h.connections[0].push('event: change\ndata: {}\n\n');
  await settle();
  assert.equal(refreshes, 2);
  h.context.document.hidden = true;
  h.connections[0].push('event: change\ndata: {}\n\n');
  await settle();
  assert.equal(refreshes, 2);
  h.context.document.hidden = false;
  h.events.get('visibilitychange')();
  await settle();
  assert.equal(refreshes, 3, 'Aplica mudança ao retornar à aba');
  h.connections[0].close();
  await settle();
  assert.equal(h.timers.size, 1, 'Reconecta somente após desconexão');
  const [id, retry] = [...h.timers][0]; h.timers.delete(id); retry();
  await settle();
  assert.equal(h.connections.length, 2);
  stop();
  await settle();
  assert.equal(h.connections[1].signal.aborted, true);
  assert.equal(h.events.size, 0, 'Remove listeners ao sair da página');
  assert.equal(h.timers.size, 0);

  const unauthorized = setup(401);
  const cleanup = unauthorized.subscribe(async () => {});
  await settle();
  assert.equal(unauthorized.context.window.location.href, '/login');
  assert.equal(unauthorized.timers.size, 0);
  cleanup();
  console.log('OK: SSE autenticado, eventos fragmentados, aba oculta, reconexão, cleanup e sessão expirada.');
})().catch(error => {console.error(error); process.exitCode = 1;});
