// Runtime smoke test: execute the REAL boot() + openScene() from reader/index.html
// against a mock DOM and a fetch() that reads from disk.
//
// This catches the class of bug that a syntax check cannot: undefined helpers,
// declaration-order problems, wrong fetch paths, exceptions during render.
//
// Usage: node tools/test_scene_load.js <reader dir>
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const DIR = path.resolve(process.argv[2] || path.join(__dirname, '..', 'reader'));
const INDEX = JSON.parse(fs.readFileSync(path.join(DIR, 'data', 'index.json'), 'utf8'));

// ------------------------------------------------------------------ mock DOM
function mkEl(tag, cls, text){
  const e = {
    tagName: String(tag).toUpperCase(),
    textContent: text === undefined ? '' : text,
    children: [], dataset: {}, style: {},
    _html: '',
    scrollTop: 0,
    _cls: '',
    appendChild(c){ e.children.push(c); return c; },
    removeChild(c){ const i = e.children.indexOf(c); if (i >= 0) e.children.splice(i, 1); return c; },
    addEventListener(){},
    scrollIntoView(){},
    get innerHTML(){ return e._html; },
    set innerHTML(v){ e._html = v; if (v === '') e.children.length = 0; },
    querySelector(sel){ return querySel(e, sel); },
    querySelectorAll(sel){ return queryAll(e, sel); },
  };
  // keep className and classList in sync, like the real DOM
  e.classList = {
    _s: new Set(),
    add(c){ this._s.add(c); e._cls = [...this._s].join(' '); },
    remove(c){ this._s.delete(c); e._cls = [...this._s].join(' '); },
    contains(c){ return this._s.has(c); },
    toggle(c, on){
      const want = on === undefined ? !this._s.has(c) : !!on;
      if (want) this._s.add(c); else this._s.delete(c);
      e._cls = [...this._s].join(' ');
      return want;
    },
  };
  Object.defineProperty(e, 'className', {
    get(){ return e._cls; },
    set(v){
      e._cls = v == null ? '' : String(v);
      e.classList._s = new Set(e._cls.split(/\s+/).filter(Boolean));
    },
  });
  e.className = cls || '';
  return e;
}
function matches(n, sel){
  if (!n || !n.className) return false;
  const cls = String(n.className).split(/\s+/);
  if (sel.startsWith('.')) return cls.includes(sel.slice(1));
  // strip attribute predicates like .chapters[data-chapters="x"]
  const m = sel.match(/^\.([\w-]+)\[([\w-]+)="([^"]*)"\]$/);
  if (m) return cls.includes(m[1]) && n.dataset && String(n.dataset[m[2]]) === m[3];
  return n.tagName === sel.toUpperCase();
}
function walk(root, fn){ fn(root); (root.children || []).forEach(c => walk(c, fn)); }
function queryAll(root, sel){
  const out = [];
  walk(root, n => { if (n !== root && matches(n, sel)) out.push(n); });
  return out;
}
function querySel(root, sel){ const r = queryAll(root, sel); return r.length ? r[0] : null; }

const body = mkEl('body');
const nodes = {
  '#brandSub': mkEl('div'), '#inner': mkEl('div'), '#toast': mkEl('div'),
  '#navBody': mkEl('div'), '#list': mkEl('div'), '#listTitle': mkEl('div'),
  '#listCount': mkEl('div'), '#rsub': mkEl('div'), '#rtitle': mkEl('h2'),
  '#rpos': mkEl('span'), '#prevBtn': mkEl('button'), '#nextBtn': mkEl('button'),
  '#modeChip': mkEl('button'), '#varToggle': mkEl('button'), '#autoChip': mkEl('button'),
  '#readBody': mkEl('div'), '#q': mkEl('input'), '#clearBtn': mkEl('button'),
};
// the known nodes live in the document tree so querySelectorAll can find them
for (const k of Object.keys(nodes)) body.appendChild(nodes[k]);
const document = {
  body,
  createElement: t => mkEl(t),
  createDocumentFragment: () => mkEl('#fragment'),
  createTextNode: t => mkEl('#text', '', String(t)),
  addEventListener(){},
  querySelector(sel){
    if (nodes[sel]) return nodes[sel];
    return querySel(body, sel);
  },
  querySelectorAll(sel){
    if (sel === '.sc') return [];
    return queryAll(body, sel);
  },
};

// -------------------------------------------------------------------- fetch
const fetched = [];
function fetchMock(url){
  fetched.push(url);
  const p = path.join(DIR, url);
  return new Promise((resolve, reject) => {
    fs.readFile(p, (err, buf) => {
      if (err) return reject(new Error('mock 404: ' + url));
      resolve({
        ok: true, status: 200,
        headers: { get: () => String(buf.length) },
        text: async () => buf.toString('utf8'),
        body: null,                       // force the text() fallback path
      });
    });
  });
}

const sandbox = {
  document, fetch: fetchMock, console, setTimeout, clearTimeout, TextDecoder,
  AbortController,
  navigator: { clipboard: null },
  localStorage: {
    _m: {},
    getItem(k){ return this._m[k] === undefined ? null : this._m[k]; },
    setItem(k, v){ this._m[k] = String(v); },
  },
  location: { pathname: '/reader/', replace(){} },
  requestAnimationFrame: fn => setTimeout(fn, 0),
  IntersectionObserver: function(){ this.observe = () => {}; this.disconnect = () => {}; },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.window.addEventListener = () => {};

const html = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (!scripts.length) { console.error('no script found'); process.exit(2); }

let pass = 0, fail = 0;
const check = (label, actual, expected) => {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (ok) { pass++; console.log('  ok   ' + label); }
  else { fail++; console.log('  FAIL ' + label + '\n        got  ' + JSON.stringify(actual)
                             + '\n        want ' + JSON.stringify(expected)); }
};

(async () => {
  vm.createContext(sandbox);

  // 1) the whole page script must evaluate without throwing
  try {
    vm.runInContext(scripts.join('\n'), sandbox, { filename: 'reader.js' });
    check('page script evaluates', true, true);
  } catch (e) {
    check('page script evaluates: ' + e.message, false, true);
    process.exit(1);
  }

  // boot() is called at the end of the script; wait for it to settle
  await new Promise(r => setTimeout(r, 300));

  check('index.json was fetched', fetched.includes('data/index.json'), true);
  const navBox = nodes['#navBody'];
  if (process.env.DBG) {
    console.log('   [dbg] navBody children:', navBox.children.length,
                navBox.children.map(c => c.className));
    console.log('   [dbg] #inner children:', nodes['#inner'].children.length,
                nodes['#inner'].children.map(c => c.className));
  }
  check('nav built (categories)', sandbox.document.querySelectorAll('.catbtn').length > 0, true);
  check('nav category count matches index',
        sandbox.document.querySelectorAll('.catbtn').length, INDEX.categories.length);

  // 2) open a scene from every category and require real dialogue to render
  const inner = nodes['#inner'];
  let rendered = 0, withText = 0;
  for (const cat of INDEX.categories.map(c => c.id)) {
    const scene = INDEX.scenes.find(s => s.c === cat);
    if (!scene) continue;
    inner.children.length = 0;
    try {
      await sandbox.openScene(scene.id, false);
    } catch (e) {
      check('openScene(' + scene.id + ') threw: ' + e.message, false, true);
      continue;
    }
    rendered++;
    // Collect the visible dialogue text. renderText() appends text nodes and
    // `mark`/`span` element children, so walk the whole subtree and only count
    // the ones inside a `.say` block.
    let txt = '';
    (function collect(n, inSay){
      if (!n) return;
      const nowInSay = inSay || String(n.className).split(/\s+/).includes('say');
      if (nowInSay && n.tagName === '#TEXT' && n.textContent) txt += n.textContent;
      if (nowInSay && n.tagName === 'MARK' && n.textContent) txt += n.textContent;
      (n.children || []).forEach(c => collect(c, nowInSay));
    })(inner, false);
    if (txt.trim().length > 0) withText++;
    else {
      console.log('     (no dialogue text for ' + scene.id + ')');
      if (process.env.DBG) {
        console.log('       inner.children:', inner.children.map(c => c.className));
        console.log('       html head:', String(inner.innerHTML).slice(0, 200));
      }
    }
  }
  check('every category opened a scene', rendered, INDEX.categories.length);
  check('every scene rendered dialogue text', withText, rendered);

  // 3) the loading path must have issued the right URLs
  const sceneUrls = fetched.filter(u => u.startsWith('data/scenes/'));
  check('scene files fetched for each category',
        [...new Set(sceneUrls)].length >= INDEX.categories.length, true);

  // 4) the loading UI must actually report progress
  vm.runInContext('S.cache.clear(); S.tlCache.clear();', sandbox);
  inner.children.length = 0;
  await sandbox.openScene(INDEX.scenes[0].id, false);
  const leftoverSpinner = [];
  walk(inner, n => { if (String(n.className).split(/\s+/).includes('loading')) leftoverSpinner.push(n); });
  check('spinner is removed once content is ready', leftoverSpinner.length, 0);

  // fetchJSON must report byte progress (drives the percentage + bar)
  const prog = [];
  sandbox.__prog = prog;
  await vm.runInContext(
    'fetchJSON("data/index.json", (g,t)=>__prog.push([g,t]))', sandbox);
  check('progress callback fired', prog.length > 0, true);
  check('progress reported a positive total',
        prog.length > 0 && prog[prog.length - 1][1] > 0, true);
  check('progress reached 100%',
        prog.length > 0 && prog[prog.length - 1][0] === prog[prog.length - 1][1], true);

  // 5) a failing fetch must be reported, not swallowed
  // `S` is a `const` in the page script's lexical scope, so it is not reachable
  // as a sandbox property -- clear the caches from inside the same context.
  vm.runInContext('S.cache.clear(); S.tlCache.clear();', sandbox);
  sandbox.fetch = () => Promise.reject(new Error('boom'));
  inner.children.length = 0;
  let threw = false;
  try { await sandbox.openScene(INDEX.scenes[0].id, false); }
  catch (e) { threw = true; }
  check('fetch failure does not throw out of openScene', threw, false);
  const errHtml = String(inner.innerHTML || '') +
                  inner.children.map(c => String(c.innerHTML || '') + c.textContent).join('');
  if (process.env.DBG) console.log('   [dbg] errHtml:', JSON.stringify(errHtml.slice(0, 300)),
                                   'children:', inner.children.map(c => c.className));
  check('fetch failure renders an error message', /无法载入/.test(errHtml), true);

  console.log('\n' + pass + ' passed, ' + fail + ' failed');
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('UNEXPECTED', e); process.exit(2); });
