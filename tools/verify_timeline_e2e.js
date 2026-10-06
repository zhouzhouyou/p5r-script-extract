// End-to-end check: real reader data -> timeline renderer.
// Run: node _tools/verify_timeline_e2e.js
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..');
const HTML = fs.readFileSync(path.join(ROOT, 'reader', 'index.html'), 'utf8');

function grab(name){
  const re = new RegExp('^function ' + name + '\\([\\s\\S]*?^}', 'm');
  const m = HTML.match(re);
  if (!m) throw new Error('function not found: ' + name);
  return m[0];
}

function mkEl(tag, cls, text){
  const e = {
    tag, className: cls || '', textContent: text === undefined ? '' : text,
    children: [], dataset: {}, style: {},
    classList: { toggle(){}, add(){}, contains(){ return false; } },
    appendChild(c){ e.children.push(c); return c; },
    get innerHTML(){ return ''; },
    set innerHTML(v){ e._html = v; },
    addEventListener(){},
  };
  return e;
}

const sandbox = {
  el: mkEl,
  renderText(c, t){ c.textContent = t; },
  toast(){},
  navigator: {},
  console,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(['sameItem','commonSuffixLen','dlgNode','optionsOf','joinNote',
                 'timelineNode','countRefs','mustShow','countItemRefs','timelineAligned','renderTimeline'].map(grab).join('\n\n'), sandbox);

function texts(node, out){
  out = out || [];
  if (!node) return out;
  if (node.className && String(node.className).includes('say')) out.push(node.textContent);
  (node.children || []).forEach(c => texts(c, out));
  return out;
}
function labels(node, out){
  out = out || [];
  if (!node) return out;
  if (node.className && String(node.className).includes('tlBranchLabel'))
    out.push(node.textContent);
  (node.children || []).forEach(c => labels(c, out));
  return out;
}
function findAll(node, cls, out){
  out = out || [];
  if (!node) return out;
  if (node.className && String(node.className).split(/\s+/).includes(cls)) out.push(node);
  (node.children || []).forEach(c => findAll(c, cls, out));
  return out;
}

const index = JSON.parse(fs.readFileSync(path.join(ROOT,'reader','data','index.json'), 'utf8'));
console.log('index.timeline :', JSON.stringify(index.timeline));

let scenesWithTl = 0, withBranch = 0, rendered = 0, spoken = 0, problems = 0;
let tlUsed = 0, tlFallback = 0, refsOk = 0, refsTotal = 0;
let branchBoxes = 0, selBoxes = 0, oneOptConfirms = 0, joins = 0;
let choiceBranches = 0, stateBranches = 0;
let stateBranchRows = 0, choiceBranchRows = 0;
let foldedChains = 0, foldedRows = 0;
let hiddenSelections = 0, hiddenChoiceBranches = 0;
const samples = [];

for (const cat of index.categories.map(c => c.id)) {
  const scenes = JSON.parse(fs.readFileSync(
    path.join(ROOT,'reader','data','scenes',cat+'.json'), 'utf8'));
  const tl = JSON.parse(fs.readFileSync(
    path.join(ROOT,'reader','data','timeline',cat+'.json'), 'utf8'));

  for (const sid of Object.keys(tl)) {
    scenesWithTl++;
    const scene = scenes[sid];
    if (!scene) { problems++; console.log('  !! timeline for unknown scene', sid); continue; }
    const t = tl[sid];

    // same guard the UI uses
    const stat = sandbox.countRefs(t.seq || [], scene.dlg.length);
    refsOk += stat.ok; refsTotal += stat.total;
    const resolvable = sandbox.timelineAligned(t.seq || [], scene);
    if (!resolvable) { tlFallback++; continue; }
    tlUsed++;

    const host = mkEl('div');
    sandbox.renderTimeline(t.seq, host, scene, null, (scene.src||[''])[0]);
    branchBoxes += findAll(host, 'tlBranch').length;
    selBoxes    += findAll(host, 'tlSelect').length;
    joins       += findAll(host, 'tlJoin').length;
    oneOptConfirms += findAll(host, 'who')
      .filter(n => n.textContent === '单项确认').length;
    // a branch is "choice-driven" when its rows are labelled by option text
    findAll(host, 'tlBranch').forEach(b => {
      const rows = findAll(b, 'tlBranchRow');
      const choice = rows.some(r => {
        const l = findAll(r, 'tlBranchLabel')[0];
        return l && /^选/.test(l.textContent || '');
      });
      if (choice) { choiceBranches++; choiceBranchRows += rows.length; }
      else        { stateBranches++;  stateBranchRows  += rows.length; }
      if (findAll(b, 'tlFoldToggle').length) {
        foldedChains++;
        foldedRows += rows.length;
      }
    });

    // no selection may ever be rendered as a 1-item "choice"
    const oneItemChoices = findAll(host, 'tlSelectHead')
      .filter(n => /选择 1 项/.test(n.textContent||''));
    if (oneItemChoices.length) {
      problems++;
      console.log('  !! rendered a 1-item choice in', sid);
    }
    // branch boxes must never be empty (that would mean a dangling cond);
    // a folded box is fine -- its rows live in the fold container
    const emptyBranch = findAll(host, 'tlBranch').filter(
      b => !findAll(b, 'tlBranchRow').length && !findAll(b, 'tlJoin').length
           && !findAll(b, 'tlFoldToggle').length);
    if (emptyBranch.length) {
      problems++;
      console.log('  !! empty branch box in', sid);
    }

    // A player choice must NEVER be hidden behind a collapse. Only selections
    // the flow actually drives are checked -- a scene's dlg array often holds
    // menus that this flow never references. Visibility is read off the real
    // rendered DOM (elements are tagged with their dialog index).
    const refSels = new Set();
    (function collectSels(node){
      if (Array.isArray(node)) return node.forEach(collectSels);
      if (!node || typeof node !== 'object') return;
      if (typeof node.sel === 'number') refSels.add(node.sel);
      (node.branches || []).forEach(collectSels);
    })(t.seq);

    const visibleIdx = new Set();
    (function walkVisible(n, hidden){
      if (!n) return;
      const hiddenNow = hidden || (n.style && n.style.display === 'none');
      if (!hiddenNow) {
        const di = n.dataset ? n.dataset.idx : undefined;
        if (di !== undefined && di !== null && di !== '') visibleIdx.add(Number(di));
      }
      (n.children || []).forEach(c => walkVisible(c, hiddenNow));
    })(host, false);

    refSels.forEach(idx => {
      const d = scene.dlg[idx];
      if (!d) return;
      if (!visibleIdx.has(idx)) {
        hiddenSelections++;
        problems++;
        if (hiddenSelections <= 12) {
          console.log('  !! hidden choice', d.i, 'idx', idx, 'in', sid);
          if (process.env.DBG_SID && sid === process.env.DBG_SID) {
            console.log('     dlg:', scene.dlg.length,
                        'refSels:', JSON.stringify([...refSels]));
            console.log('     visible:', JSON.stringify([...visibleIdx].sort((a,b)=>a-b)));
          }
        }
      }
    });
    // choice-driven branch rows must not be collapsed either
    findAll(host, 'tlBranch').forEach(b => {
      const rows = findAll(b, 'tlBranchRow');
      const choiceBox = rows.some(r => {
        const l = findAll(r, 'tlBranchLabel')[0];
        return l && /^选/.test(l.textContent || '');
      });
      if (!choiceBox) return;
      rows.forEach(r => {
        const body = findAll(r, 'tlBranchBody')[0];
        if (body && body.style && body.style.display === 'none') {
          hiddenChoiceBranches++;
          problems++;
          console.log('  !! hidden choice branch row in', sid);
        }
      });
    });

    const hasBranch = t.seq.some(x => x && x.branches);
    if (hasBranch) withBranch++;
    if (host.children.length) rendered++;

    const sp = [];
    // count spoken lines actually emitted
    const collect = (n) => {
      if (!n) return;
      if (n.className && String(n.className).includes('say')) sp.push(n.textContent);
      (n.children||[]).forEach(collect);
    };
    collect(host);
    spoken += sp.length;
    if (hasBranch && samples.length < 3) {
      samples.push({sid, labels: findAll(host,'tlBranchLabel').map(n=>n.textContent), spoken: sp});
    }
  }
}

console.log('scenes with timeline   :', scenesWithTl);
console.log('  shown as timeline    :', tlUsed);
console.log('  fell back to raw     :', tlFallback, '(refs would not resolve)');
console.log('  of shown, with branch:', withBranch);
console.log('  rendered a node tree :', rendered);
console.log('  spoken blocks total  :', spoken);
console.log('rendered UI elements   :');
console.log('  branch boxes         :', branchBoxes);
console.log('    choice-driven      :', choiceBranches, '(rows', choiceBranchRows + ')');
console.log('    game-state only    :', stateBranches, '(rows', stateBranchRows + ')');
console.log('  selection boxes      :', selBoxes);
console.log('  join points          :', joins);
console.log('  folded state chains  :', foldedChains, '(rows hidden by default:', foldedRows + ')');
console.log('  hidden choices       :', hiddenSelections,
            '| hidden choice rows:', hiddenChoiceBranches, '(both must be 0)');
console.log('  单项确认 lines        :', oneOptConfirms);
console.log('dialog refs resolvable :', refsOk + '/' + refsTotal,
            '(' + (100*refsOk/refsTotal).toFixed(1) + '%)');
console.log('broken references      :', problems);
console.log();
for (const s of samples) {
  console.log('--- ' + s.sid);
  console.log('    labels :', JSON.stringify(s.labels.slice(0, 8)));
  console.log('    spoken :', JSON.stringify(s.spoken.slice(0,4)));
}

process.exit(problems ? 1 : 0);
