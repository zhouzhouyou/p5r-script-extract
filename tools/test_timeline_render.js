// Verify the reader's timeline renderer against a minimal DOM stub.
// Run: node _tools/test_timeline_render.js
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const HTML = fs.readFileSync(
  path.join(__dirname, '..', 'reader', 'index.html'), 'utf8');

function grab(name){
  const re = new RegExp('^function ' + name + '\\([\\s\\S]*?^}', 'm');
  const m = HTML.match(re);
  if (!m) throw new Error('function not found: ' + name);
  return m[0];
}

const SRC = ['sameItem', 'commonSuffixLen', 'dlgNode', 'optionsOf', 'joinNote',
             'timelineNode', 'countRefs', 'mustShow', 'countItemRefs', 'timelineAligned', 'renderTimeline'].map(grab).join('\n\n');

// ---------------------------------------------------------------- DOM stub
function mkEl(tag, cls, text){
  const e = {
    tag, className: cls || '', textContent: text === undefined ? '' : text,
    children: [], dataset: {}, style: {},
    classList: {
      toggle(c, on){
        const parts = e.className.split(/\s+/).filter(Boolean);
        const has = parts.includes(c);
        if (on && !has) parts.push(c);
        if (!on && has) parts.splice(parts.indexOf(c), 1);
        e.className = parts.join(' ');
      },
      add(c){ e.className = (e.className ? e.className + ' ' : '') + c; },
      contains(c){ return e.className.split(/\s+/).includes(c); },
    },
    appendChild(c){ e.children.push(c); return c; },
    get innerHTML(){ return ''; },
    set innerHTML(v){ e._html = v; },
    addEventListener(){},
  };
  return e;
}

const sandbox = {
  el: mkEl,
  renderText(container, text){ container.textContent = text; },
  toast(){},
  navigator: {},
  console,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(SRC, sandbox);

// ------------------------------------------------------------------ helpers
let pass = 0, fail = 0;
function check(label, actual, expected){
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (ok){ pass++; console.log('  ok   ' + label); }
  else { fail++; console.log('  FAIL ' + label + '\n        got  ' + JSON.stringify(actual)
                                 + '\n        want ' + JSON.stringify(expected)); }
}
function walk(node, out){
  if (!node) return out;
  out.push(node.className || node.tag);
  (node.children || []).forEach(c => walk(c, out));
  return out;
}
// collect visible spoken text, in document order
function texts(node, out){
  if (!node) return out;
  if (node.className && node.className.includes('say')) out.push(node.textContent);
  (node.children || []).forEach(c => texts(c, out));
  return out;
}
function findAll(node, cls, out){
  out = out || [];
  if (!node) return out;
  if (node.className && node.className.split(/\s+/).includes(cls)) out.push(node);
  (node.children || []).forEach(c => findAll(c, cls, out));
  return out;
}

const { timelineNode, commonSuffixLen } = sandbox;

// a scene shaped like reader/data/scenes/*.json
const scene = {
  dlg: [
    { s:'系长机器人', t:'都是因为你们这帮偷懒的家伙。', k:'msg', i:'MSG_0' },   // 0
    { s:'佐仓　双叶', t:'要不要试着动摇对方看看？',       k:'msg', i:'MSG_1' },   // 1
    { s:'选项',       t:'你讨厌课长吗？\n课长是怎样的人？', k:'sel', i:'SEL_2' }, // 2
    { s:'系长机器人', t:'那种家伙有谁会喜欢啊！',         k:'msg', i:'MSG_3' },   // 3
    { s:'系长机器人', t:'他就是个讨人厌的家伙啦！',       k:'msg', i:'MSG_4' },   // 4
    { s:'选项',       t:'拿情报交换\n那样的话就帮你',     k:'sel', i:'SEL_5' },   // 5
    { s:'系长机器人', t:'什么！？',                       k:'msg', i:'MSG_6' },   // 6
  ],
};

console.log('1) commonSuffixLen');
check('identical tails', commonSuffixLen([[3,5],[4,5]]), 1);
check('no common tail', commonSuffixLen([[3],[4]]), 0);
check('fully identical', commonSuffixLen([[3,4],[3,4]]), 2);
check('empty', commonSuffixLen([]), 0);

console.log('2) optionsOf');
check('splits options', sandbox.optionsOf(scene.dlg[2]), ['你讨厌课长吗？','课长是怎样的人？']);

console.log('3) selection node');
const selNode = timelineNode({sel:2}, scene, null, 'X.msg');
check('is a selection box', findAll(selNode,'tlSelect').length, 1);
check('option rows', findAll(selNode,'tlOptText').map(n=>n.textContent),
      ['你讨厌课长吗？','课长是怎样的人？']);

console.log('4) branch node — labels come from the selection text');
const branch = {
  cond:'var3 == 0 / else', var:'var3', values:[0,null], varMsg:2,
  branches:[[3,{sel:5}],[4,{sel:5}]],
};
const bNode = timelineNode(branch, scene, null, 'X.msg');
check('one branch box', findAll(bNode,'tlBranch').length, 1);
check('branch labels', findAll(bNode,'tlBranchLabel').map(n=>n.textContent),
      ['选「你讨厌课长吗？」','其他选择']);
check('spine order: sel → branch',
      [findAll(bNode,'tlSelect').length, findAll(bNode,'tlBranch').length], [1,1]);
check('SEL_5 is lifted into the shared join (not repeated per branch)',
      findAll(bNode,'tlJoin').length, 1);
check('option text appears once, in the join',
      findAll(bNode,'tlOptText').map(n=>n.textContent), ['拿情报交换','那样的话就帮你']);
check('branch bodies hold only the branch-specific dialog',
      findAll(bNode,'tlBranchBody').map(n=>texts(n,[])),
      [['那种家伙有谁会喜欢啊！'],['他就是个讨人厌的家伙啦！']]);
check('spoken text in order', texts(bNode, []),
      ['那种家伙有谁会喜欢啊！','他就是个讨人厌的家伙啦！']);

console.log('5) shared continuation is lifted once');
const branch2 = {
  cond:'var3 == 0 / else', var:'var3', values:[0,null], varMsg:2,
  branches:[[3,6],[4,6]],
};
const b2 = timelineNode(branch2, scene, null, 'X.msg');
check('join box present', findAll(b2,'tlJoin').length, 1);
check('tail appears once', texts(b2, []).filter(t=>t==='什么！？').length, 1);
check('branch bodies do not repeat it',
      findAll(b2,'tlBranchBody').map(n=>texts(n,[])),
      [['那种家伙有谁会喜欢啊！'],['他就是个讨人厌的家伙啦！']]);

console.log('6) no shared tail -> no join box');
const b3 = timelineNode({cond:'c',var:'v',values:[0,1],varMsg:2,branches:[[3],[4]]}, scene, null,'X.msg');
check('no join box', findAll(b3,'tlJoin').length, 0);

console.log('7) empty branch shows a note');
const b4 = timelineNode({cond:'c',var:'v',values:[0,1],varMsg:2,branches:[[3],[]]}, scene, null,'X.msg');
check('note in empty branch', findAll(b4,'tlNote').length, 1);
check('note text', findAll(b4,'tlNote')[0].textContent, '（此分支没有额外台词）');

console.log('8) dynamic (unresolved) chain still renders its branches');
const b5 = timelineNode({cond:'BIT_CHK(5) == 1',var:null,values:[1],varMsg:null,
                         branches:[[0]]}, scene, null, 'X.msg');
check('renders a node', !!(b5 && typeof b5 === 'object'), true);
check('label falls back to the condition',
      findAll(b5,'tlBranchLabel').map(n=>n.textContent), ['满足 BIT_CHK(5) == 1']);
check('text kept', texts(b5, []), ['都是因为你们这帮偷懒的家伙。']);

console.log('9) plain dialog index');
const d0 = timelineNode(0, scene, null, 'X.msg');
check('spoken', texts(d0, []), ['都是因为你们这帮偷懒的家伙。']);
check('missing index is skipped', timelineNode(99, scene, null, 'X.msg'), null);

console.log('10) countRefs — resolution guard used to fall back to file order');
const { countRefs } = sandbox;
check('all resolve', countRefs([0,1,2], 3), {ok:3, total:3});
check('some out of range', countRefs([0,99], 3), {ok:1, total:2});
check('inside branches', countRefs([{cond:'c',branches:[[0],[99]]}], 3), {ok:1, total:2});
check('selection counts too', countRefs([{sel:1}], 3), {ok:1, total:1});
check('empty timeline', countRefs([], 3), {ok:0, total:0});

console.log('11) empty game text renders a placeholder, not blank');
const dEmpty = timelineNode(0, {dlg:[{s:'旁白',t:'',k:'msg',i:'X'}]}, null, '');
check('placeholder shown', texts(dEmpty, []), ['（原文为空）']);

console.log('12) a [sel] with ONE option is not a choice');
// real shape: [sel SEL_007_0_0 top] followed by a single [s]... option line
const oneOptScene = {
  dlg: [
    { s:'品行不端的少年', t:'想怎样就怎样……他以为自己是城堡里的国王啊。', k:'msg', i:'MSG_6' },
    { s:'选项', t:'（咂嘴）', k:'sel', i:'SEL_7' },
    { s:'品行不端的少年', t:'不，我是说……', k:'msg', i:'MSG_8' },
  ],
};
const oneSel = timelineNode({sel:1}, oneOptScene, null, 'X.msg');
check('no 选择 N 项 header', findAll(oneSel,'tlSelectHead').length, 0);
check('no option rows', findAll(oneSel,'tlOpt').length, 0);
check('not styled as 选项', (oneSel.className||'').includes('sel'), false);
check('labelled 单项确认', findAll(oneSel,'who').map(n=>n.textContent), ['单项确认']);
check('text kept', texts(oneSel, []), ['（咂嘴）']);
check('single-option branch is inlined, no branch box',
      timelineNode({cond:'var0 == 0', var:'var0', values:[0], varMsg:1,
                    branches:[[2]]}, oneOptScene, null, 'X.msg').__inline,
      [2]);
const host = mkEl('div');
sandbox.renderTimeline([{sel:1}, {cond:'var0 == 0', var:null, values:[0], varMsg:1, branches:[[2]]}],
                       host, oneOptScene, null, 'X.msg');
check('inlined output has no branch UI',
      [findAll(host,'tlBranch').length, findAll(host,'tlSelect').length], [0,0]);
check('inlined output keeps both lines',
      texts(host, []), ['（咂嘴）', '不，我是说……']);

console.log('13) a real 2-option [sel] still renders as a choice');
const twoSel = timelineNode({sel:2}, scene, null, 'X.msg');
check('header shows the count', findAll(twoSel,'tlSelectHead').map(n=>n.textContent), ['选择 2 项']);
check('both options listed', findAll(twoSel,'tlOptText').map(n=>n.textContent),
      ['你讨厌课长吗？','课长是怎样的人？']);

console.log('14) the exact screenshot shape: 1-option confirm must not fork');
// MSG_006 (question) -> SEL_007 (1 option) -> {var0==0} -> MSG_008 -> SEL (2 options)
const shot = { dlg: [
  { s:'品行不端的少年', t:'啊？刚才那辆车啊。\n那是鸭志田吧。', k:'msg', i:'MSG_004_0_0' },  // 0
  { s:'选项', t:'（咂嘴）', k:'sel', i:'MSG_005_0_0' },                                        // 1
  { s:'品行不端的少年', t:'想怎样就怎样……他以为自己是城堡里的国王啊。\n你不觉得吗？', k:'msg', i:'MSG_006_0_0' }, // 2
  { s:'选项', t:'城堡里的国王？\n哪里的城堡？', k:'sel', i:'SEL_007_0_0' },                   // 3
  { s:'品行不端的少年', t:'不，我是说……', k:'msg', i:'MSG_008_0_0' },                        // 4
]};
// the flow: sel(1) then a chain whose var comes from sel(1), body = [2]
const seq = [
  { sel: 1 },
  { cond:'var0 == 0', var:'var0', values:[0], varMsg:1, branches:[[2]] },
  { sel: 3 },
  4,
];
const host2 = mkEl('div');
sandbox.renderTimeline(seq, host2, shot, null, 'X.msg');
check('no fake branch box', findAll(host2,'tlBranch').length, 0);
check('no fake branch header', findAll(host2,'tlBranchHead').length, 0);
check('speaker tags: confirm + the question, at top level',
      findAll(host2,'who').map(n=>n.textContent),
      ['单项确认','品行不端的少年','品行不端的少年']);
check('the question paragraph is top-level, not nested in a branch',
      findAll(host2,'say').map(n=>n.textContent)[1],
      '想怎样就怎样……他以为自己是城堡里的国王啊。\n你不觉得吗？');
check('the 2-option menu is top-level and shows both options',
      findAll(host2,'tlOptText').map(n=>n.textContent),
      ['城堡里的国王？','哪里的城堡？']);
check('reading order preserved (confirm, question, menu, reply)', [
      ...findAll(host2,'say').map(n=>n.textContent).slice(0,2),
      ...findAll(host2,'tlOptText').map(n=>n.textContent),
      ...findAll(host2,'say').map(n=>n.textContent).slice(2),
    ],
    ['（咂嘴）','想怎样就怎样……他以为自己是城堡里的国王啊。\n你不觉得吗？',
     '城堡里的国王？','哪里的城堡？','不，我是说……']);
check('no 选择 1 项 anywhere',
      findAll(host2,'tlSelectHead').filter(n=>/选择 1 项/.test(n.textContent)).length, 0);

console.log('15) game-state branch rows collapse in a scene with no choices');
// a scene that contains no [sel] at all: pure state-driven branch noise
const plainScene = { dlg: scene.dlg.map(d => ({...d, k:'msg'})) };
const stateChain = {cond:'BIT_CHK(5) == 1 / BIT_CHK(6) == 1', var:null, values:[1,1],
                    varMsg:null, branches:[[0,1],[2,3]]};
const sNode = timelineNode(stateChain, plainScene, null, 'X.msg');
const sBodies = findAll(sNode,'tlBranchBody');
check('both state bodies collapsed',
      sBodies.map(b=>b.style.display), ['none','none']);
check('each row offers an expand affordance',
      findAll(sNode,'tlRowMore').map(n=>n.textContent), ['  ▸ 2 条','  ▸ 2 条']);
check('no fold toggle for a 2-row chain (row-level folding is enough)',
      findAll(sNode,'tlFoldToggle').length, 0);

console.log('16) a state row that leads to a choice is never hidden');
const withChoice = {cond:'BIT_CHK(5) == 1 / BIT_CHK(6) == 1', var:null, values:[1,1],
                    varMsg:null, branches:[[0,1,{sel:2}],[2,3]]};
const wc = timelineNode(withChoice, scene, null, 'X.msg');
check('row with a nested selection stays open',
      findAll(wc,'tlBranchBody').map(b=>b.style.display||''), ['','']);
check('and its selection is rendered',
      findAll(wc,'tlSelect').length, 1);
check('row is tagged 含选项',
      findAll(wc,'tlRowHas').map(n=>n.textContent), ['  含选项']);
check('a choice-bearing chain is not chain-folded',
      findAll(wc,'tlFoldToggle').length, 0);

check('mustShow: plain dialogs -> false', sandbox.mustShow([0,1,[2]]), false);
check('mustShow: nested sel -> true', sandbox.mustShow([0,[1,{sel:2}]]), true);
check('mustShow: nested choice branch -> true',
      sandbox.mustShow([{cond:'c',var:'v',varMsg:1,values:[0],branches:[[0]]}]), true);
check('mustShow: state branch only -> false',
      sandbox.mustShow([{cond:'c',var:null,varMsg:null,values:[1],branches:[[0]]}]), false);

const bigChain = {cond:'c1 / c2 / c3 / c4', var:null, values:[1,2,3,4], varMsg:null,
                  branches:[[0],[1],[2],[3]]};
const bNode2 = timelineNode(bigChain, scene, null, 'X.msg');
check('a 4-row state chain gets a fold toggle',
      findAll(bNode2,'tlFoldToggle').map(n=>n.textContent),
      ['▸ 游戏状态分支 4 条（点此展开）']);

// choice-driven rows must stay expanded -- that is the content the user wants
const cNode = timelineNode({cond:'var3 == 0 / else', var:'var3', values:[0,null],
                            varMsg:2, branches:[[3],[4]]}, scene, null, 'X.msg');
check('choice rows are not collapsed',
      findAll(cNode,'tlBranchBody').map(b=>b.style.display||''), ['','']);
check('choice rows have no expand affordance',
      findAll(cNode,'tlRowMore').length, 0);
check('choice boxes never fold',
      findAll(cNode,'tlFoldToggle').length, 0);

console.log('17) timelineAligned — only trust a timeline that provably lines up');
// scene: idx0 msg, idx1 msg, idx2 sel, idx3 msg
const alScene = { dlg: [
  {s:'A',t:'a',k:'msg',i:'M0'},{s:'A',t:'b',k:'msg',i:'M1'},
  {s:'选项',t:'x\ny',k:'sel',i:'S2'},{s:'A',t:'c',k:'msg',i:'M3'},
]};
const { timelineAligned } = sandbox;
check('sel lands on a sel dialog -> aligned',
      timelineAligned([0, {sel:2}, 3], alScene), true);
check('no sel refs and refs in range -> aligned',
      timelineAligned([0, 1, 3], alScene), true);
check('sel lands on a plain msg -> MISALIGNED',
      timelineAligned([0, {sel:1}, 3], alScene), false);
check('sel out of range -> misaligned',
      timelineAligned([0, {sel:9}], alScene), false);
check('most refs out of range -> misaligned',
      timelineAligned([0, 11, 12, 13], alScene), false);
check('empty -> misaligned', timelineAligned([], alScene), false);
check('sel nested in branches is checked too',
      timelineAligned([0, {cond:'c',var:'v',varMsg:1,values:[0],
                           branches:[[{sel:1}]]}], alScene), false);
check('a correctly nested sel passes',
      timelineAligned([0, {cond:'c',var:'v',varMsg:2,values:[0],
                           branches:[[{sel:2}]]}], alScene), true);

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
