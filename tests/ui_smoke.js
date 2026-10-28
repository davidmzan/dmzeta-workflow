// Carga todos los scripts de la interfaz (en el orden de index.html) en un DOM falso y ejecuta el arranque en modo demo.
// Detecta ReferenceError / errores de arranque sin necesidad de un navegador. Uso: node tests/ui_smoke.js <carpeta ui>
const vm = require('vm'), fs = require('fs'), path = require('path');
const ui = process.argv[2];
const html = fs.readFileSync(path.join(ui, 'index.html'), 'utf8');
const files = [...html.matchAll(/<script src="\/ui\/(js\/[^"]+)"/g)].map(m => m[1]);
if (!files.length) { console.error('sin scripts en index.html'); process.exit(2); }

const timers = [];
function stub(label) {
  const f = function () {};
  return new Proxy(f, {
    get(t, p) {
      if (p === Symbol.toPrimitive) return () => 0;
      if (p === Symbol.iterator) return function* () {};
      if (p === 'then') return undefined;
      if (p === 'length') return 0;
      if (p === 'style' || p === 'classList' || p === 'dataset') return stub(p);
      return stub(String(p));
    },
    set() { return true; }, apply() { return stub('ret'); }, construct() { return stub('new'); }, has() { return true; },
  });
}
const doc = new Proxy({}, { get(t, p) {
  if (p === 'querySelector' || p === 'getElementById' || p === 'createElement') return () => stub('el');
  if (p === 'querySelectorAll') return () => [];
  if (p === 'addEventListener') return () => {};
  if (p === 'body' || p === 'documentElement') return stub('body');
  return stub(String(p));
}, set() { return true; } });
const win = {};
const ctx = vm.createContext({
  document: doc, window: win, location: { search: '?demo=1', href: 'http://127.0.0.1/' }, navigator: { userAgent: 'node' }, console,
  setTimeout: (fn, ms) => { timers.push(fn); return timers.length; }, setInterval: () => 0, clearTimeout() {}, clearInterval() {}, requestAnimationFrame: () => 0, cancelAnimationFrame() {},
  fetch: () => Promise.reject(new Error('sin red en la prueba')), localStorage: { getItem: () => null, setItem() {} }, AudioContext: function () { return stub('audio'); },
  URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} }, Blob: function () {}, Float32Array, Uint8Array, Math, JSON, Promise, Date, Array, Object, String, Number, RegExp, Set, Map, parseInt, parseFloat, isNaN, encodeURIComponent, decodeURIComponent,
  CSS: { supports: () => true }, devicePixelRatio: 1, innerWidth: 1500, innerHeight: 900, getComputedStyle: () => stub('cs'),
});
win.addEventListener = () => {}; win.requestAnimationFrame = () => 0; win.AudioContext = ctx.AudioContext; win.devicePixelRatio = 1; ctx.window = win;
let loaded = 0;
for (const f of files) {
  try { vm.runInContext(fs.readFileSync(path.join(ui, f), 'utf8'), ctx, { filename: f }); loaded++; }
  catch (e) { console.error('ERROR al cargar ' + f + ': ' + e.message); process.exit(1); }
}
async function settle(p) {                                // avanza temporizadores y promesas hasta que p termina
  let done = false, err = null; p.then(() => { done = true; }, e => { done = true; err = e; });
  for (let i = 0; i < 400 && !done; i++) { await new Promise(r => setImmediate(r)); while (timers.length) timers.shift()(); }
  if (err) throw err; if (!done) throw new Error('no terminó (¿bucle?)');
}
(async () => {
  vm.runInContext("showErr=function(m){throw new Error('showErr: '+m)}", ctx);        // los errores que la app mostraría en pantalla aquí fallan la prueba
  await settle(vm.runInContext('init()', ctx));                                        // arranque en modo demo: estado, reglas, lista de pistas de ejemplo
  const rows = vm.runInContext('S.rows.length', ctx); if (!(rows > 3)) throw new Error('el modo demo no cargó pistas: ' + rows);
  await settle(vm.runInContext('(async()=>{ selectRow(1,false); renderInsp(); renderList(); renderFilters(); renderPads(); drawDeck(); renderDrawer(); await loadQuality(); })()', ctx));
  console.log('OK ' + loaded + ' scripts cargados, ' + rows + ' pistas de demo, vistas principales dibujadas');
})().catch(e => { console.error('ERROR: ' + (e && e.message)); process.exit(1); });
process.on('unhandledRejection', e => { console.error('ERROR (promesa): ' + (e && e.message)); process.exit(1); });
