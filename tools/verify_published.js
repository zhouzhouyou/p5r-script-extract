// Verify a reader deployment from files on disk (no network).
// Usage: node tools/verify_published.js <dir containing index.html + data/>
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const DIR = path.resolve(process.argv[2] || '.');
const CATS = ['battle','confidant','daily','facility','main','mypalace','script'];

function mkEl(t, c, x){
  const e = { tag:t, className:c||'', textContent:x===undefined?'':x, children:[],
    dataset:{}, style:{}, classList:{toggle(){},add(){},contains(){return false}},
    appendChild(k){ e.children.push(k); return k; },
    get innerHTML(){return '';}, set innerHTML(v){}, addEventListener(){} };
  return e;
}
function findAll(node, cls, out){
  out = out || [];
  if (!node) return out;
  if (node.className && String(node.className).split(/\s+/).includes(cls)) out.push(node);
  (node.children || []).forEach(c => findAll(c, cls, out));
  return out;
}

const html = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
const m = html.match(/<script>\s*([\s\S]*?)\s*<\/script>/);
if (!m) { console.error('no <script> found in index.html'); process.exit(2); }
const src = m[1];

function grab(name){
  const re = new RegExp('^function ' + name + '\\([\\s\\S]*?^}', 'm');
  const mm = src.match(re);
  if (!mm) throw new Error('missing function ' + name);
  return mm[0];
}

const sandbox = { el:mkEl, renderText(c,t){c.textContent=t;}, toast(){}, navigator:{}, console };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(['sameItem','commonSuffixLen','dlgNode','optionsOf','joinNote',
                 'timelineNode','countRefs','mustShow','countItemRefs',
                 'timelineAligned','renderTimeline'].map(grab).join('\n\n'), sandbox);

let scenes = 0, aligned = 0, sels = 0, hidden = 0, oneItem = 0, missing = 0, spoken = 0;

for (const cat of CATS){
  const scPath = path.join(DIR, 'data', 'scenes', cat + '.json');
  const tlPath = path.join(DIR, 'data', 'timeline', cat + '.json');
  if (!fs.existsSync(scPath) || !fs.existsSync(tlPath)) {
    console.log(`  ${cat.padEnd(10)} MISSING files`);
    missing++;
    continue;
  }
  const S = JSON.parse(fs.readFileSync(scPath, 'utf8'));
  const T = JSON.parse(fs.readFileSync(tlPath, 'utf8'));
  let n = 0;
  for (const sid of Object.keys(T)){
    scenes++;
    const scene = S[sid];
    if (!scene) { missing++; continue; }
    const t = T[sid];
    if (!sandbox.timelineAligned(t.seq || [], scene)) continue;
    aligned++;
    const host = mkEl('div');
    sandbox.renderTimeline(t.seq, host, scene, null, (scene.src||[''])[0]);
    n++;

    (function countSay(nd){
      if (!nd) return;
      if (nd.className && String(nd.className).split(/\s+/).includes('say')) spoken++;
      (nd.children||[]).forEach(countSay);
    })(host);

    const refSels = new Set();
    (function collect(x){
      if (Array.isArray(x)) return x.forEach(collect);
      if (!x || typeof x !== 'object') return;
      if (typeof x.sel === 'number') refSels.add(x.sel);
      (x.branches||[]).forEach(collect);
    })(t.seq);
    const visible = new Set();
    (function walk(nd, hid){
      if (!nd) return;
      const h = hid || (nd.style && nd.style.display === 'none');
      if (!h && nd.dataset && nd.dataset.idx !== undefined) visible.add(Number(nd.dataset.idx));
      (nd.children||[]).forEach(c => walk(c, h));
    })(host, false);
    refSels.forEach(i => {
      sels++;
      if (!visible.has(i)) { hidden++; console.log('  !! hidden choice in', sid); }
    });
    oneItem += findAll(host,'tlSelectHead').filter(x=>/选择 1 项/.test(x.textContent||'')).length;
  }
  console.log(`  ${cat.padEnd(10)} scenes=${String(n).padStart(5)}  ok`);
}

console.log();
console.log('dir                   :', DIR);
console.log('scenes with timeline  :', scenes);
console.log('  aligned (rendered)  :', aligned);
console.log('  spoken blocks        :', spoken);
console.log('flow-driven selections:', sels, '| hidden:', hidden, '(must be 0)');
console.log('1-item choices        :', oneItem, '(must be 0)');
console.log('missing scenes/files  :', missing, '(must be 0)');
const ok = hidden === 0 && oneItem === 0 && missing === 0 && spoken > 0;
console.log('\nRESULT:', ok ? 'PASS' : 'FAIL');
process.exit(ok ? 0 : 1);
