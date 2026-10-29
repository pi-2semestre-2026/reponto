const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const source = ts.transpileModule(fs.readFileSync(__dirname + '/../src/lib/date-range.ts', 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020},
}).outputText;
const context = {exports: {}};
vm.runInNewContext(source, context);
const range = (preset, date, from = '', to = '') => JSON.parse(JSON.stringify(context.exports.dashboardRange(preset, from, to, new Date(date))));
const late = '2026-10-27T01:38:00Z'; // 26/10 22:38 em São Paulo.
assert.deepEqual(range('today', late), {from: '2026-10-26', to: '2026-10-26'});
assert.deepEqual(range('7d', late), {from: '2026-10-20', to: '2026-10-26'});
assert.deepEqual(range('30d', late), {from: '2026-09-27', to: '2026-10-26'});
assert.deepEqual(range('month', late), {from: '2026-10-01', to: '2026-10-26'});
assert.deepEqual(range('today', '2026-10-27T02:59:59Z'), {from: '2026-10-26', to: '2026-10-26'});
assert.deepEqual(range('today', '2026-10-27T03:00:00Z'), {from: '2026-10-27', to: '2026-10-27'});
assert.deepEqual(range('month', '2026-11-01T01:00:00Z'), {from: '2026-10-01', to: '2026-10-31'});
assert.deepEqual(range('7d', '2027-01-01T12:00:00Z'), {from: '2026-12-26', to: '2027-01-01'});
assert.deepEqual(range('7d', '2024-03-01T12:00:00Z'), {from: '2024-02-24', to: '2024-03-01'});
assert.deepEqual(range('custom', late, '2026-01-01', '2026-01-31'), {from: '2026-01-01', to: '2026-01-31'});
assert.equal(range('custom', late), null);
console.log('OK: presets usam o calendário de São Paulo, incluindo viradas de dia, mês e ano.');
