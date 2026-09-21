// Drives the REAL mccf_character_creator.html in jsdom. Usage: node client_test.js <html>
const fs = require('fs'); const { JSDOM } = require('jsdom');
const file = process.argv[2]; const html = fs.readFileSync(file, 'utf8');
let pass = 0, fail = 0;
const check = (label, ok, detail) => { ok ? pass++ : fail++; console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}` + (!ok && detail !== undefined ? `   <- ${JSON.stringify(detail)}` : '')); };

// Anna's cultivar (reconstructed, see harness.py) as the server returns it
const ANNA = [['Bow','BowTimer'],['Fold Arms','Timer2'],['Idle','Timer3'],['Look Around','Timer4'],['Sit','Timer5'],['Wait','Timer6'],['Walk','Timer7'],
  ['Fold Arms 2','Fold Arms 2Timer'],['Idle 2','Idle 2Timer'],['Look Around 2','Look Around 2Timer'],['Sit 2','Sit 2Timer'],['Walk 2','Walk 2Timer']];
const cultivar = { agentname: 'Anna', hanim_src: 'Anna.x3d', hanim_loa: 4, weights: {E:.3,B:.2,P:.2,S:.2}, phrases: [], receptivity: {E:1,B:1,P:1,S:1},
  behavior_clips: ANNA.map(([n,t],i)=>({name:n,timerDEF:t,loop:false,priority:i,cycleInterval:6,E_min:0,E_max:1,B_min:0,B_max:1,P_min:0,P_max:1,S_min:0,S_max:1})) };
// discovery response as the PATCHED server returns it (14 real + some hollow)
const joints = { joints: [{name:'Root',def:'Root',center:[0,0,0],parent:null,region:'spine'}], joint_map: {},
  clips: [ {name:'Bow',timerDEF:'Timer8',cycleInterval:6.04,loop:false,routes:51,hollow:false,exported_as:['BowTimer']},
           {name:'clip 6',timerDEF:'Timer6',cycleInterval:6,loop:false,routes:51,hollow:false,exported_as:['Timer6']},
           {name:'Bow',timerDEF:'Timer1_1',cycleInterval:6.04,loop:false,routes:0,hollow:true,exported_as:['Timer1_1']},
           {name:'clip 1',timerDEF:'Timer1_2',cycleInterval:6,loop:true,routes:0,hollow:true,exported_as:[]} ] };

const sent = []; let manifestMode = 'network-error';
const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:5000/',
  beforeParse(w) {
    w.speechSynthesis = { getVoices: () => [], onvoiceschanged: null };
    w.SpeechSynthesisUtterance = function(){};
    w.alert = () => {}; w.confirm = () => true; w.scrollTo = () => {};
    w.fetch = async (url, opts) => {
      const u = String(url); const body = opts && opts.body ? JSON.parse(opts.body) : null;
      sent.push({ url: u, body });
      const ok = (o, status=200) => ({ ok: status < 400, status, json: async () => o, text: async () => JSON.stringify(o) });
      if (u.includes('/hanim/joints')) return ok(joints);
      if (u.includes('/hanim/export')) return ok({ status: 'ok', clips_written: 12, hanim_path: '/static/avatars/Anna.x3d', warnings: [], loop_updated: ['Timer8 loop=true'] });
      if (u.includes('.manifest.xml')) { if (manifestMode === 'network-error') throw new Error('offline'); return ok('', 404); }
      if (u.includes('/cultivars/xml')) return ok({ cultivars: [] });
      return ok({});
    };
  } });
const w = dom.window;
w.console.log = () => {}; w.console.warn = () => {}; w.console.info = () => {};
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  await sleep(300);
  console.log('\n== client: cultivar load -> clip dropdown (C2)');
  w.loadForm(cultivar);
  const sel = w.document.getElementById('he-clip-select');
  check('dropdown shows all 12 cultivar clips right after load (no control touched)', sel.options.length === 12, sel.options.length);
  check('dropdown starts on Bow', w._heClips[0].name === 'Bow' && sel.selectedIndex === 0);

  console.log('\n== client: open Pose tab (heLoadJoints) — hollow stubs hidden, cultivar clips kept');
  w.heLoadJoints('/static/avatars/Anna.x3d'); await sleep(50);
  check('still 12 clips (cultivar list not replaced by discovery)', w._heClips.length === 12, w._heClips.length);
  check('playback panel shows only the 2 real timers, not the hollow ones', w.document.querySelectorAll('#he-playback-btns .he-pb-btn').length === 2, w.document.querySelectorAll('#he-playback-btns .he-pb-btn').length);

  console.log('\n== client: tick Loop on Bow (C1)');
  const before = w._heClips.map(c => c.timerDEF);
  const loop = w.document.getElementById('he-clip-loop'); loop.checked = true; w.hePoseClipPropChanged();
  check("Bow's timerDEF unchanged after ticking Loop", w._heClips[0].timerDEF === 'BowTimer', w._heClips[0].timerDEF);
  check('no clip timerDEF changed anywhere', JSON.stringify(before) === JSON.stringify(w._heClips.map(c => c.timerDEF)));
  check('loop recorded and flagged as author-edited', w._heClips[0].loop === true && w._heClips[0]._loopEdited === true);
  // rename a whitespace clip: identity must not be re-derived
  w.hePoseSelectClip(7); w.document.getElementById('he-clip-name').value = 'Fold Arms Two'; w.hePoseClipPropChanged();
  check("renaming a clip does not re-derive its timerDEF", w._heClips[7].timerDEF === 'Fold Arms 2Timer', w._heClips[7].timerDEF);
  // bound of 0 survives
  w.hePoseSelectClip(1); w.document.getElementById('he-clip-E_max').value = '0'; w.hePoseClipPropChanged();
  check('E_max = 0 is kept (was coerced to 1)', w._heClips[1].E_max === 0, w._heClips[1].E_max);
  w.document.getElementById('he-clip-E_max').value = '1'; w.hePoseClipPropChanged();

  console.log('\n== client: Export payload (C3 + rig guard)');
  sent.length = 0;
  w.document.body.insertAdjacentHTML('beforeend', '<button id="he-export-btn"></button>');
  await w.heExport();
  const exp = sent.find(x => x.url.includes('/hanim/export'));
  check('export request was sent', !!exp);
  if (exp) {
    if (process.env.PAYLOAD_OUT) fs.writeFileSync(process.env.PAYLOAD_OUT, JSON.stringify(exp.body));
    const clips = exp.body.clips;
    check('12 clips sent', clips.length === 12, clips.length);
    check('every unedited clip sends keyframes: [] (no empty default keyframes)', clips.every(c => Array.isArray(c.keyframes) && c.keyframes.length === 0), clips.map(c => c.keyframes.length));
    check("timerDEFs sent are the cultivar's own", clips.map(c => c.timerDEF).join() === ANNA.map(a => a[1]).join(), clips.map(c => c.timerDEF));
    check('loop_edited only on Bow', clips.filter(c => c.loop_edited).map(c => c.name).join() === 'Bow', clips.filter(c => c.loop_edited).map(c => c.name));
    check('cameraRig is null when the manifest fetch FAILED (server leaves rig alone)', exp.body.cameraRig === null, exp.body.cameraRig);
  }
  check('loop_edited flags cleared after a successful export', w._heClips.every(c => !c._loopEdited));

  console.log('\n== client: authored clip still sends its keyframes');
  const wave = w._heNewClipObj('Wave', 6, false, 0); wave.keyframes[1].joints = { Root: [0,1,0,0.5] }; w._heClips.push(wave);
  const out = w._heClipForExport(wave);
  check("authored clip keeps its keyframes", out.keyframes.length === 2 && Object.keys(out.keyframes[1].joints).length === 1);
  check("new clip's timerDEF is sanitised", w._heNewClipObj('Fold Arms', 6, true, 0).timerDEF === 'Fold_ArmsTimer');

  console.log('\n== client: manifest 404 = settled (no rig authored yet) -> rig object is sent');
  manifestMode = '404'; w.loadForm(cultivar); await sleep(60); sent.length = 0; await w.heExport();
  const expN = sent.find(x => x.url.includes('/hanim/export'));
  check('404 manifest -> cameraRig object sent (author may be creating the first rig)', expN && expN.body.cameraRig && typeof expN.body.cameraRig === 'object');
  manifestMode = 'network-error'; w.loadForm(cultivar); await sleep(60);
  console.log('\n== client: rig sent once author edits it');
  sent.length = 0; w.heCameraRigFieldChanged(); await w.heExport();
  const exp2 = sent.find(x => x.url.includes('/hanim/export'));
  check('cameraRig is an object after the author edits the rig form', exp2 && exp2.body.cameraRig && typeof exp2.body.cameraRig === 'object');

  console.log(`\n${'-'.repeat(60)}\n${pass}/${pass + fail} checks passed`); process.exit(fail);
})().catch(e => { console.error('HARNESS ERROR', e); process.exit(99); });
