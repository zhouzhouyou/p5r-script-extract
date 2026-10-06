// Verify the sidebar expand/collapse + chapter-memory logic from reader/index.html
// against a minimal DOM stub. Run: node _tools/test_nav_toggle.js
'use strict';

const fs = require('fs');
const path = require('path');

const HTML = fs.readFileSync(
  path.join(__dirname, '..', 'reader', 'index.html'), 'utf8');

// ---- pull the functions under test out of the page script -------------------
function grab(name){
  const re = new RegExp('^function ' + name + '\\([\\s\\S]*?^}', 'm');
  const m = HTML.match(re);
  if (!m) throw new Error('could not find function ' + name);
  return m[0];
}

const SRC = ['selectCategory', 'setCatExpanded', 'isCatOpen', 'setCatButtons',
             'selectChapter'].map(grab).join('\n\n');

// ---- minimal DOM ------------------------------------------------------------
function mkEl(cls, dataset){
  return {
    className: cls || '',
    dataset: dataset || {},
    style: { display: 'none' },
    children: [],
    classList: {
      _el: null,
      add(c){ this._el.className += ' ' + c; },
      toggle(c, on){
        const parts = this._el.className.split(/\s+/).filter(Boolean);
        const has = parts.includes(c);
        if (on && !has) parts.push(c);
        if (!on && has) parts.splice(parts.indexOf(c), 1);
        this._el.className = parts.join(' ');
      },
    },
  };
}

const catBtns = [];
const wraps = {};

function setup(){
  catBtns.length = 0;
  for (const k of Object.keys(wraps)) delete wraps[k];

  for (const cid of ['main', 'daily', 'battle']){
    const b = mkEl('catbtn', { cat: cid });
    b.classList._el = b;
    catBtns.push(b);

    const w = mkEl('chapters', { chapters: cid });
    const all = mkEl('chbtn on', { ch: '' });
    all.classList._el = all;
    w.children.push(all);
    for (const ch of ['E1', 'E2']){
      const x = mkEl('chbtn', { ch });
      x.classList._el = x;
      w.children.push(x);
    }
    wraps[cid] = w;
  }
}

global.document = {
  querySelectorAll(sel){
    if (sel === '.catbtn') return catBtns;
    if (sel === '.chapters') return Object.values(wraps);
    throw new Error('unexpected selectorAll ' + sel);
  },
  querySelector(sel){
    const m = sel.match(/^\.chapters\[data-chapters="(.+)"\]$/);
    if (m) return wraps[m[1]] || null;
    throw new Error('unexpected selector ' + sel);
  },
};

global.applyFilters = () => { filtersCalled++; };
let filtersCalled = 0;

const S = { cat: null, ch: null, lastCh: {} };
global.S = S;
global.COLLAPSED = Symbol('collapsed');

// indirect eval -> declarations land on globalThis, like they do in the page
(0, eval)(SRC);

// ---- assertions -------------------------------------------------------------
let pass = 0, fail = 0;
function check(label, actual, expected){
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (ok) { pass++; console.log('  ok   ' + label); }
  else { fail++; console.log('  FAIL ' + label + '  got=' + JSON.stringify(actual) + ' want=' + JSON.stringify(expected)); }
}
const state = () => ({ cat: S.cat, ch: S.ch, open: isCatOpen(S.cat), lastCh: S.lastCh });

setup();

console.log('1) open 主线剧情');
selectCategory('main');
check('category selected', S.cat, 'main');
check('chapters visible', isCatOpen('main'), true);
check('no chapter chosen yet', S.ch, null);

console.log('2) pick chapter E2');
selectChapter('main', 'E2');
check('chapter applied', S.ch, 'E2');
check('remembered', S.lastCh.main, 'E2');

console.log('3) click 主线剧情 again -> collapse');
selectCategory('main');
check('collapsed', isCatOpen('main'), false);
check('list falls back to whole category', S.ch, null);
check('chapter still remembered', S.lastCh.main, 'E2');
check('category stays highlighted', catBtns[0].className.includes('on'), true);
check('no chapter row highlighted while collapsed',
      wraps.main.children.some(b => b.className.includes('on')), false);

console.log('4) click 主线剧情 again -> reopen restores E2');
selectCategory('main');
check('expanded', isCatOpen('main'), true);
check('chapter restored', S.ch, 'E2');
check('E2 row highlighted',
      wraps.main.children.find(b => b.dataset.ch === 'E2').className.includes('on'), true);
check('other rows not highlighted',
      wraps.main.children.filter(b => b.className.includes('on')).length, 1);

console.log('5) switching to another category');
selectCategory('daily');
check('daily open', isCatOpen('daily'), true);
check('main closed', isCatOpen('main'), false);
check('daily has no memory yet', S.ch, null);

console.log('6) back to main -> still E2');
selectCategory('main');
check('E2 restored after switching away', S.ch, 'E2');

console.log('7) collapse via re-click, then pick a different chapter');
selectCategory('main');                 // collapse (memory E2)
check('collapsed again', isCatOpen('main'), false);
selectChapter('main', 'E1');            // expands + selects E1
check('expanded by chapter click', isCatOpen('main'), true);
check('E1 selected', S.ch, 'E1');
check('memory updated', S.lastCh.main, 'E1');

console.log('8) "全部章节" is also remembered');
selectChapter('main', null);
check('all-chapters selected', S.ch, null);
check('memory cleared to null', 'main' in S.lastCh && S.lastCh.main, null);
selectCategory('main');                 // collapse
selectCategory('main');                 // reopen
check('reopened with 全部章节', S.ch, null);
check('全部章节 row highlighted',
      wraps.main.children.find(b => b.dataset.ch === '').className.includes('on'), true);

console.log('\nfilters() calls:', filtersCalled);
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
