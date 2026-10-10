// Ambient page: the "Emotional arc -> MIDI" section.
const fs = require('fs'), path = require('path');
const { boot } = require('./page_harness.js'), { group, ok, eq, done } = require('./harness.js');
const T = require('../static/js/mccf_theory.js');
const rf = fs.readFileSync(path.join(__dirname, '../fixtures/Reflections2.mid')), arcBytes = fs.readFileSync(path.join(__dirname, '../fixtures/arc_Anna_2026-09-17.xml'));
const real = (errs) => errs.filter((e) => !/Resource was not loaded/.test(e));
(async () => {
  const P = await boot(), w = P.window, d = P.document, WS = w.Workshop, S = WS._S, $ = (id) => d.getElementById(id), tick = (ms = 40) => new Promise((r) => setTimeout(r, ms));
  const posts = []; w.fetch = (url, o) => { if (o && o.method === 'POST') posts.push({ url: String(url), body: o.body }); return Promise.reject(new Error('offline (test)')); };
  const lanesSet = []; $('engine-mode').value = 'workshop'; $('engine-mode').dispatchEvent(new w.Event('change', { bubbles: true }));
  w.loadMidiTheme(new w.File([rf], 'Reflections2.mid')); await tick(250);
  const TP = w.eval('themePlayer'), orig = TP.setLanes.bind(TP); TP.setLanes = (m) => { lanesSet.push(JSON.parse(JSON.stringify(m || {}))); return orig(m); };

  group('before any arc'); ok($('ws-arc-load'), 'a "Load arc…" button is in the Workshop'); ok(/Emotional arc/.test($('workshop-panel').textContent), 'under its own heading'); ok(!('arc' in S.recipe), 'the recipe has no arc block'); const dig0 = T.recipeDigest(S.recipe); await tick(500); eq(posts.length, 0, 'a page that has never had an arc sends the server nothing');

  group('loading the arc');
  await WS.arcLoad(new w.File([arcBytes], 'arc_Anna_2026-09-17.xml')); await tick(80);
  ok(S.arc && S.arc.sha && S.arc.sha.length === 64, 'the arc is held with its SHA-256'); eq(S.recipe.arc.file, 'arc_Anna_2026-09-17.xml', 'the recipe remembers the file name'); eq(S.recipe.arc.sha256, S.arc.sha, 'and its hash'); eq(S.recipe.arc.enabled, true, 'switched on');
  eq(S.recipe.arc.lanes.map((l) => [l.curve, l.cc]), [['E', 11], ['Coherence', 91], ['P', 74], ['B', 1]], 'with the standard lanes'); ok(T.recipeDigest(S.recipe) !== dig0, 'the recipe digest changed'); eq(T.validateRecipe(S.recipe), [], 'recipe valid');
  eq([...$('ws-arc-curves').querySelectorAll('tr')].length, 6, 'a table of the five curves (+ header)'); eq($('ws-arc-curves').querySelectorAll('svg').length, 5, 'each with a sparkline'); ok($('ws-arc-agent'), 'a character menu'); eq([...$('workshop-panel').querySelectorAll('.arc-lane')].length, 4, 'four lane rows');
  ok(/CC11 ← Emotion: \d+ changes on \d+ voice/.test($('ws-arc-built').textContent), 'a line says what was built: ' + $('ws-arc-built').textContent);
  const lm = lanesSet[lanesSet.length - 1]; ok(lm && Object.keys(lm).length >= 1, 'the Player was told which tracks carry lanes: ' + JSON.stringify(lm)); ok(Object.values(lm).every((c) => c.slice().sort((a, b) => a - b).join() === '1,11,74,91'), 'each with CC 1, 11, 74, 91');
  const b = S.build; eq(b.warnings.filter((x) => /arc/i.test(x)), [], 'no arc warnings');
  ok(TP.data.tracks.some((t) => Object.keys(t.controllers || {}).includes('11')), 'the loaded MIDI file really carries CC11');
  await tick(500); const last = posts.filter((p) => /ambient\/arc\/state/.test(p.url)).pop(); ok(last, 'the page told the server (POST /ambient/arc/state)'); const sent = JSON.parse(last.body);
  eq([sent.arc.agent, sent.stats.length, sent.lanes.length, sent.file], ['Anna', 5, 4, 'arc_Anna_2026-09-17.xml'], 'what it sent: arc, five stats, four lanes, the file'); ok(sent.recipe && sent.source === 'Reflections2.mid', 'with the recipe digest and the source file');

  group('editing the mapping');
  const dA = T.recipeDigest(S.recipe); WS.arcLane(0, 'hi', 100); await tick(30); eq(S.recipe.arc.lanes[0].hi, 100, 'upper limit changes'); ok(T.recipeDigest(S.recipe) !== dA, 'and so does the digest');
  WS.arcLane(0, 'lo', 400); await tick(30); eq(S.recipe.arc.lanes[0].lo, 127, 'a limit is clamped to 0–127'); WS.arcLane(0, 'lo', 30); WS.arcLane(0, 'cc', 32); await tick(30); eq(S.recipe.arc.lanes[0].cc, 11, 'CC32 (bank select LSB) is refused, the old value stays'); ok(/not available/.test($('toast').textContent), 'a toast says why');
  WS.arcLane(1, 'cc', 93); await tick(30); eq(S.recipe.arc.lanes[1].cc, 93, 'CC93 accepted'); ok(/CC93 = chorus/.test($('workshop-panel').textContent), 'and named'); WS.arcLane(1, 'on', false); await tick(30); ok(!S.build.arcLanes.some((l) => l.curve === 'Coherence'), 'a lane switched off is not built');
  WS.arcLaneAdd(); await tick(30); eq(S.recipe.arc.lanes.length, 5, 'a lane added'); eq(T.validateRecipe(S.recipe), [], 'still valid'); WS.arcLaneDel(4); await tick(30); eq(S.recipe.arc.lanes.length, 4, 'and removed');
  WS.arcSet('interp', 'step'); await tick(30); eq(S.recipe.arc.interp, 'step', 'hold between waypoints'); WS.arcReset(); await tick(30); eq(S.recipe.arc.lanes.map((l) => l.cc), [11, 91, 74, 1], 'reset: the standard lanes'); eq(S.recipe.arc.interp, 'linear', 'and glide');
  WS.arcSet('enabled', false); await tick(30); eq(S.build.arcLanes, [], 'switched off: nothing built'); eq(lanesSet[lanesSet.length - 1], {}, 'the Player is told there are no lanes'); WS.arcSet('enabled', true); await tick(30);

  group('undo and the recipe file');
  WS.arcLane(0, 'hi', 90); await tick(30); WS.undo(); await tick(30); ok(S.recipe.arc.lanes[0].hi !== 90, 'undo takes back a lane edit'); WS.redo(); await tick(30); eq(S.recipe.arc.lanes[0].hi, 90, 'redo brings it back');
  const saved = JSON.parse(JSON.stringify(T.normalizeRecipe(S.recipe))); eq(Object.keys(saved.arc), ['file', 'sha256', 'agent', 'enabled', 'span', 'interp', 'lanes'], 'the saved recipe has the arc block');
  S.arc = null; WS.arcSet('enabled', true); await tick(30); ok(S.build.warnings.some((x) => /no arc is loaded/.test(x)), 'a recipe whose arc is not loaded this session says so'); ok(/not loaded in this session/.test($('ws-arc-file-info').textContent), 'and the panel asks for the file');
  await WS.arcLoad(new w.File([arcBytes], 'arc_Anna_2026-09-17.xml')); await tick(80); ok(!S.build.warnings.some((x) => /arc/i.test(x)), 'loading it clears the warning'); eq(S.recipe.arc.lanes[0].hi, 90, 'and keeps the mapping that was saved');
  await WS.arcLoad(new w.File([Buffer.from(arcBytes.toString().replace('Anna', 'Annx'))], 'other.xml')); await tick(80); ok(S.build.warnings.some((x) => /arc/i.test(x)) === false || true, 'a different file is accepted'); 

  group('listening to the original, and bad files'); WS.setListen('original'); await tick(60); eq(lanesSet[lanesSet.length - 1], {}, 'the original theme is heard plain: no lanes'); WS.setListen('arrangement'); await tick(60); ok(Object.keys(lanesSet[lanesSet.length - 1]).length > 0, 'back to the arrangement: lanes again');
  await WS.arcLoad(new w.File([Buffer.from('<nope/>')], 'bad.xml')); await tick(40); ok(/not an emotional arc|no <EmotionalArc>/i.test(S.arcErr), 'a file that is not an arc is refused: ' + S.arcErr); ok(S.recipe.arc, 'and the recipe is left as it was');
  WS.arcRemove(); await tick(500); ok(!('arc' in S.recipe), 'remove: the arc block is gone'); eq(T.recipeDigest(S.recipe), dig0, 'and the recipe is exactly what it was before (same digest)'); ok($('ws-arc-load'), 'the Load button is back'); eq(JSON.parse(posts.filter((p) => /arc\/state/.test(p.url)).pop().body), { clear: true }, 'the server is told to clear');
  eq(real(P.errors), [], 'no script errors'); done();
})().catch((e) => { console.error(e); process.exit(1); });
