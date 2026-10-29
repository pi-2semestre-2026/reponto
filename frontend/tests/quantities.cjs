const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
function read(name) {
  const ctx = {exports: {}};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(`${__dirname}/../src/lib/${name}.ts`, 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText, ctx);
  return ctx.exports;
}
const f = read('format');
assert.equal(f.fmtNum('0.001'), '0,001');
assert.equal(f.fmtNum('1.250'), '1,25');
assert.equal(f.fmtMoney('1.25'), 'R$\u00a01,25');
assert.equal(f.fmtQuantity('1.001', 'kg'), '1,001 quilogramas');
assert.equal(f.fmtQuantity('1', 'unidade'), '1 unidade');
assert.equal(f.fmtQuantity('3', 'g', 'en'), '3 grams');
assert.equal(f.saleQuantities([{quantity:'0.001',unit:'kg'},{quantity:'0.002',unit:'kg'},{quantity:'2',unit:'unidade'}]), '0,003 quilogramas · 2 unidades');
assert.equal(f.fmtQuantity('2', 'L'), '2 litros');
assert.equal(f.fmtQuantity('1', 'dz'), '1 dúzia');
assert.equal(f.fmtQuantity('2', 'fardo'), '2 fardo');
const {openDatePicker} = read('date-picker');
let opened = 0, focused = 0;
openDatePicker({showPicker(){opened++;}});
openDatePicker({showPicker(){throw new Error('unsupported');},focus(){focused++;}});
openDatePicker({focus(){focused++;}});
assert.equal(opened, 1); assert.equal(focused, 1);
console.log('OK: precisão de três casas, unidades separadas, moeda e abertura do calendário.');
