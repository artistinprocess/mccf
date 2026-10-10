const fs = require('fs'), path = require('path');
const { group, ok, eq, done } = require('./harness.js');
const A = require('../static/js/mccf_arc.js');
const xml = fs.readFileSync(path.join(__dirname, '../fixtures/arc_Anna_2026-09-17.xml'), 'utf8');
const near = (a, b, eps, msg) => ok(Math.abs(a - b) <= (eps || 1e-9), msg + ' (got ' + a + ', want ' + b + ')');

group('parseArc: the real Anna arc');
const arc = A.parseArc(xml), pts = arc.cultivars[0].points;
eq(arc.scene, 'GardenOfTheGoddess_Scene01', 'scene'); eq(arc.id, 'Anna_2026-09-17T000603.624Z', 'id'); eq(arc.title, 'MCCF Constitutional Arc Export', 'title'); eq(arc.cultivars.length, 1, 'one cultivar'); eq(arc.cultivars[0].agent, 'Anna', 'agent');
eq(pts.length, 46, '46 waypoints'); eq(pts.map((p) => p.step), Array.from({ length: 46 }, (_, i) => i + 1), 'steps 1..46 in order'); eq(pts[0].id, 'line_new_v5t92', 'first waypoint id'); eq(pts[45].id, 'line_new_vhltu', 'last waypoint id');
near(pts[0].E, 0.3143, 1e-9, 'E of step 1'); near(pts[12].E, 0.1458, 1e-9, 'E of step 13 (the low)'); near(pts[8].S, 0.2305, 1e-9, 'S of step 9 (the high)'); near(pts[45].Coherence, 0.0664, 1e-9, 'coherence of the last');
eq(pts[0].mode, 'repair', 'mode'); eq([pts[0].valence, pts[0].uncertainty, pts[0].reward], [null, null, null], 'empty Valence / Uncertainty / Reward are null, not 0');
ok(/^Art is all/.test(pts[0].text), 'statement text'); ok(/artist’s hand/.test(pts[1].text), 'unicode kept'); ok(pts[8].text.startsWith('[gentle, instructive]'), 'bracketed direction kept'); eq(pts.reduce((s, p) => s + p.text.split(/\s+/).filter(Boolean).length, 0), 940, '940 words in all');

group('parseArc: odd and bad input');
const ent = '<EmotionalArc id="x" scene="s"><Cultivar agentname="A &amp; B"><Waypoint id="w1" stepno="1" E="0.5" B="" P="x" S="0.1" Coherence="0.2"><Statement speaker="A">Tom &amp; Jerry &lt;3 &quot;hi&quot;</Statement></Waypoint><Waypoint id="w2" E="0.6"/></Cultivar></EmotionalArc>';
const e = A.parseArc(ent); eq(e.cultivars[0].agent, 'A & B', 'entities in attributes'); eq(e.cultivars[0].points[0].text, 'Tom & Jerry <3 "hi"', 'entities in text'); eq(e.cultivars[0].points[0].B, null, 'an empty number is null'); eq(e.cultivars[0].points[0].P, null, 'a non-number is null'); eq(e.cultivars[0].points[1].step, 2, 'a missing stepno takes its position'); eq(e.cultivars[0].points[1].text, '', 'a self-closing waypoint has no text');
const two = '<EmotionalArc id="x"><Cultivar agentname="A"><Waypoint id="a" E="0.1"/></Cultivar><Cultivar agentname="B"><Waypoint id="b" E="0.2"/><Waypoint id="c" E="0.3"/></Cultivar></EmotionalArc>'; eq(A.parseArc(two).cultivars.map((c) => [c.agent, c.points.length]), [['A', 1], ['B', 2]], 'several cultivars in one file');
const thr = (s, m) => { let msg = ''; try { A.parseArc(s); } catch (x) { msg = x.message; } ok(msg, 'throws for ' + m); return msg; };
ok(/not an emotional arc/.test(thr('<svg/>', 'an unrelated file')), 'says so'); ok(/not an emotional arc/.test(thr('', 'empty text')), 'empty'); thr('<EmotionalArc id="x"></EmotionalArc>', 'no cultivar'); thr('<EmotionalArc id="x"><Cultivar agentname="A"></Cultivar></EmotionalArc>', 'no waypoints'); thr('x'.repeat(9 * 1024 * 1024), 'a huge file'); thr(null, 'null');

group('curveStats agree with the planning spreadsheet');
const st = (k) => A.curveStats(pts, k);
near(st('E').min, 0.1458, 1e-9, 'E min'); near(st('E').max, 0.4103, 1e-9, 'E max'); near(st('E').mean, 0.2940, 5e-4, 'E mean'); near(st('E').sd, 0.0533, 5e-4, 'E sd'); eq(st('E').distinct, 43, 'E has 43 distinct values');
eq(st('B').distinct, 7, 'B 7'); eq(st('P').distinct, 6, 'P 6'); eq(st('S').distinct, 4, 'S 4'); eq(st('Coherence').distinct, 37, 'Coherence 37'); near(st('Coherence').range, 0.0096, 1e-9, 'Coherence range'); eq(st('E').n, 46, 'n');
eq(A.curveStats([], 'E').n, 0, 'no points: n 0'); eq(A.curveStats([{ E: null }], 'E').min, null, 'no numbers: null');

group('normalized');
const nE = A.normalized(pts, 'E'); eq(nE.length, 46, 'one per waypoint'); eq([Math.min(...nE), Math.max(...nE)], [0, 1], 'E spans 0..1 exactly'); near(nE[12], 0, 1e-12, 'step 13 is the low'); near(nE[8], 1, 1e-12, 'step 9 is the high');
const nC = A.normalized(pts, 'Coherence'); eq([Math.min(...nC), Math.max(...nC)], [0, 1], 'coherence is stretched to its own range too (that is the point of it)'); ok(nC[45] > nC[0], 'and still rises');
eq(A.normalized([{ E: 0.3 }, { E: 0.3 }], 'E'), [0, 0], 'a flat curve is all 0 (as in the spreadsheet)'); eq(A.normalized([{ E: 0.2 }, { E: null }, { E: 0.4 }], 'E'), [0, 0, 1], 'a gap holds the previous value'); eq(A.normalized([{ E: null }, { E: 0.2 }, { E: 0.4 }], 'E'), [0, 0, 1], 'a leading gap takes the first real value'); eq(A.normalized([], 'E'), [], 'empty');

group('the same numbers as the spreadsheet at the waypoints');
const lane = (c) => A.DEFAULT_LANES.find((l) => l.curve === c), at = (c, i) => Math.round(lane(c).lo + A.normalized(pts, c)[i] * (lane(c).hi - lane(c).lo));
eq([at('E', 0), at('Coherence', 0), at('P', 0), at('B', 0)], [81, 20, 50, 60], 'row 1: CC11 81, CC91 20, CC74 50, CC1 60'); eq([at('E', 1), at('Coherence', 1), at('P', 1), at('B', 1)], [80, 24, 56, 51], 'row 2'); eq([at('E', 45), at('Coherence', 45), at('P', 45), at('B', 45)], [72, 89, 56, 51], 'row 46');
const spec0 = A.defaultSpec(); eq(A.sample(A.normalized(pts, 'E'), 7 / 45, 'linear'), nE[7], 'the linear sample at a waypoint position is that waypoint');

group('spec');
eq(spec0.lanes.map((l) => [l.curve, l.cc, l.lo, l.hi]), [['E', 11, 30, 110], ['Coherence', 91, 20, 90], ['P', 74, 50, 90], ['B', 1, 0, 60]], 'the standard lanes (CC 11, 91, 74, 1)'); eq(A.validateSpec(spec0), [], 'valid'); eq(Object.keys(spec0), ['file', 'sha256', 'agent', 'enabled', 'span', 'interp', 'lanes'], 'fixed key order (digest stability)');
eq(A.normalizeSpec(A.normalizeSpec(spec0)), spec0, 'normalising twice changes nothing'); eq(A.normalizeSpec({}).lanes, [], 'empty spec has no lanes');
const bad = (mut, re, msg) => { const s = JSON.parse(JSON.stringify(spec0)); mut(s); const er = A.validateSpec(s); ok(er.some((x) => re.test(x)), msg + ': ' + er.join(' | ')); };
bad((s) => { s.lanes[0].cc = 0; }, /controller/, 'CC0 (bank select) refused'); bad((s) => { s.lanes[0].cc = 32; }, /controller/, 'CC32 refused'); bad((s) => { s.lanes[0].cc = 6; }, /controller/, 'CC6 (data entry) refused'); bad((s) => { s.lanes[0].cc = 99; }, /controller/, 'NRPN refused'); bad((s) => { s.lanes[0].cc = 120; }, /controller/, 'channel-mode messages refused'); bad((s) => { s.lanes[0].cc = 7.5; }, /controller/, 'a fraction refused');
bad((s) => { s.lanes[0].curve = 'Z'; }, /curve/, 'unknown curve'); bad((s) => { s.lanes[0].lo = -1; }, /0-127/, 'low out of range'); bad((s) => { s.lanes[0].hi = 128; }, /0-127/, 'high out of range'); bad((s) => { s.lanes[1].cc = 11; }, /already driven/, 'two lanes on one controller'); bad((s) => { s.interp = 'cubic'; }, /interp/, 'unknown interp'); bad((s) => { s.span = 'bars'; }, /span/, 'unknown span'); bad((s) => { s.lanes = Array.from({ length: 17 }, (_, i) => ({ curve: 'E', cc: 20 + i, lo: 0, hi: 1, on: true })); }, /16 lanes/, 'too many lanes');
{ const s = JSON.parse(JSON.stringify(spec0)); s.lanes[1].cc = 11; s.lanes[1].on = false; eq(A.validateSpec(s), [], 'a lane that is switched off may share a controller'); }
ok(A.ccAllowed(11) && A.ccAllowed(1) && A.ccAllowed(74) && A.ccAllowed(91) && !A.ccAllowed(121) && !A.ccAllowed(-1), 'ccAllowed');

group('sample');
const n3 = [0, 1, 0.5]; eq([A.sample(n3, 0, 'linear'), A.sample(n3, 0.5, 'linear'), A.sample(n3, 1, 'linear'), A.sample(n3, 0.25, 'linear'), A.sample(n3, 0.75, 'linear')], [0, 1, 0.5, 0.5, 0.75], 'linear: waypoints at 0, 0.5, 1 and straight lines between');
eq([A.sample(n3, 0, 'step'), A.sample(n3, 0.32, 'step'), A.sample(n3, 0.34, 'step'), A.sample(n3, 0.67, 'step'), A.sample(n3, 1, 'step')], [0, 0, 1, 0.5, 0.5], 'step: each waypoint holds for an equal third'); eq(A.sample([0.7], 0.5, 'linear'), 0.7, 'one waypoint'); eq(A.sample([], 0.5, 'linear'), 0, 'none'); eq([A.sample(n3, -1, 'linear'), A.sample(n3, 9, 'linear')], [0, 0.5], 'clamped to the ends');

group('laneEvents');
const L = 480 * 4 * 64, ev = A.laneEvents(pts, lane('E'), spec0, L, 480);
eq(ev[0].tick, 0, 'the first event is at tick 0 (so the synth is set before the first note)'); ok(ev.every((e) => e.tick % 240 === 0 || pts.some((_, i) => Math.round(i / 45 * L) === e.tick)), 'on an eighth-note grid (ppq/2) or exactly at a waypoint'); ok(ev.every((e) => e.value >= 30 && e.value <= 110), 'within the lane range 30..110'); ok(ev.every((e, i) => i === 0 || e.value !== ev[i - 1].value), 'only changes are written');
ok(ev.every((e, i) => i === 0 || e.tick > ev[i - 1].tick), 'strictly increasing in time'); ok(ev[ev.length - 1].tick <= L, 'nothing after the end'); ok(ev.length > 40 && ev.length < 600, 'a sensible number of events (' + ev.length + ' for 64 bars)'); eq(A.laneEvents(pts, lane('E'), spec0, L, 480), ev, 'deterministic');
eq(ev.find((e) => e.tick === 0).value, 81, 'starts at the first waypoint (81)'); const peak = Math.max(...ev.map((e) => e.value)), low = Math.min(...ev.map((e) => e.value)); eq([low, peak], [30, 110], 'reaches both ends of the range');
const evc = A.laneEvents(pts, lane('Coherence'), spec0, L, 480); ok(evc.length < ev.length, 'the slow coherence lane has far fewer events than E (' + evc.length + ' vs ' + ev.length + ')'); eq(evc[0].value, 20, 'coherence starts low'); eq(evc[evc.length - 1].value, 89, 'and ends near the top (89 at the last grid step)');
const st2 = A.laneEvents(pts, lane('E'), Object.assign({}, spec0, { interp: 'step' }), L, 480); eq(st2[0].value, 81, 'step: first value'); ok(st2.length <= 46 + 1, 'step: at most one event per waypoint (' + st2.length + ')');
eq(A.laneEvents(pts, { curve: 'E', cc: 11, lo: 100, hi: 20, on: true }, spec0, L, 480).find((e) => e.tick === 0).value, 100 - Math.round(A.normalized(pts, 'E')[0] * 80), 'low above high inverts the lane');
eq(A.laneEvents([{ E: 0.5 }], lane('E'), spec0, 480, 480).map((e) => e.tick), [0], 'a one-waypoint arc: one event'); eq(A.laneEvents(pts, lane('E'), spec0, 1, 480)[0].tick, 0, 'a one-tick piece still starts'); eq(A.laneEvents(pts, lane('E'), spec0, 0, 480)[0].tick, 0, 'a zero-length piece does not loop forever');

group('applyLanes');
const mk = () => ({ ppq: 480, lengthTicks: 480 * 4 * 8, tracks: [
  { name: 'Lead', channel: 5, voiceId: 'lead', controllers: { 7: [{ tick: 0, value: 100, channel: 5 }], 91: [{ tick: 0, value: 16, channel: 5 }], 10: [{ tick: 0, value: 24, channel: 5 }] } },
  { name: 'Drums', channel: 9, voiceId: 'drums', controllers: { 7: [{ tick: 0, value: 100, channel: 9 }] } },
  { name: 'Source piano', channel: 0, controllers: { 7: [{ tick: 0, value: 90, channel: 0 }], 11: [{ tick: 0, value: 127, channel: 0 }, { tick: 960, value: 80, channel: 0 }] } }] });
const a1 = mk(), r1 = A.applyLanes(a1, pts, spec0); const lead = a1.tracks[0], drums = a1.tracks[1], src = a1.tracks[2];
eq(r1.lanes.map((l) => [l.curve, l.cc, l.tracks]), [['E', 11, 1], ['Coherence', 91, 1], ['P', 74, 1], ['B', 1, 1]], 'four lanes, each on the one pitched voice'); eq(r1.warnings, [], 'no warnings');
eq(Object.keys(lead.controllers).map(Number).sort((a, b) => a - b), [1, 7, 10, 11, 74, 91], 'the voice track gained CC 1, 11, 74, 91 and kept its own 7 and 10');
eq(lead.controllers[7], [{ tick: 0, value: 100, channel: 5 }], 'its volume is untouched'); eq(lead.controllers[10], [{ tick: 0, value: 24, channel: 5 }], 'its pan is untouched'); ok(lead.controllers[11].every((e) => e.lane === true && e.channel === 5), 'lane events are marked and on the voice’s channel');
ok(!lead.controllers[91].some((e) => e.value === 16 && !e.lane), 'the lane REPLACES the voice’s own static reverb while the arc is on'); eq(Object.keys(drums.controllers), ['7'], 'drums are not touched'); eq(src.controllers[11].length, 2, 'a source (backing) track is not touched'); ok(!src.controllers[11].some((e) => e.lane), 'and has no lane events');
const a2 = mk(); A.applyLanes(a2, pts, spec0); A.applyLanes(a2, pts, spec0); eq(a2.tracks[0].controllers[11], lead.controllers[11], 'applying twice does not duplicate events');
const a3 = mk(); const r3 = A.applyLanes(a3, pts, Object.assign({}, spec0, { enabled: false })); eq(a3.tracks[0].controllers[11], undefined, 'switched off: nothing is written'); eq(r3.lanes, [], 'and no lanes are reported');
const a4 = mk(); const r4 = A.applyLanes(a4, [], spec0); ok(/no arc is loaded/.test(r4.warnings[0]), 'switched on but no arc loaded: a warning, not a crash'); eq(a4.tracks[0].controllers[11], undefined, 'and nothing written');
const a5 = mk(); a5.lengthTicks = 0; ok(/no music yet/.test(A.applyLanes(a5, pts, spec0).warnings[0]), 'no music yet: a warning');
const a6 = mk(), s6 = JSON.parse(JSON.stringify(spec0)); s6.lanes[0].cc = 0; ok(/arc lanes skipped/.test(A.applyLanes(a6, pts, s6).warnings[0]), 'an invalid spec: skipped with the reason'); eq(a6.tracks[0].controllers[11], undefined, 'nothing written');
const a7 = mk(), s7 = JSON.parse(JSON.stringify(spec0)); s7.lanes[0].on = false; eq(A.applyLanes(a7, pts, s7).lanes.map((l) => l.cc), [91, 74, 1], 'a lane switched off is skipped');

group('summary (what the dashboard shows)');
const sm = A.summary(arc, 0, spec0, { file: 'x.xml' }); eq(sm.arc, { id: 'Anna_2026-09-17T000603.624Z', scene: 'GardenOfTheGoddess_Scene01', title: 'MCCF Constitutional Arc Export', agent: 'Anna', waypoints: 46, words: 940, modes: ['repair'], hasValence: false, hasUncertainty: false, hasReward: false }, 'the arc line');
eq(sm.stats.map((s) => s.curve), ['E', 'B', 'P', 'S', 'Coherence'], 'five curves'); eq(sm.stats[0].distinct, 43, 'with their stats'); eq(Object.keys(sm.curves), ['E', 'B', 'P', 'S', 'Coherence'], 'and their shapes'); ok(sm.curves.E.length === 46, '46 points (under the 120 cap)'); eq(sm.file, 'x.xml', 'extras are carried');
const big = { id: 'b', scene: '', title: '', cultivars: [{ agent: 'Z', id: '', points: Array.from({ length: 500 }, (_, i) => ({ step: i + 1, E: i / 499, B: 0, P: 0, S: 0, Coherence: 0, text: '', mode: '' })) }] }; const sb = A.summary(big, 0, spec0); eq(sb.curves.E.length, 120, 'a long arc is thinned to 120 points'); eq([sb.curves.E[0], sb.curves.E[119]], [0, 1], 'keeping both ends'); ok(JSON.stringify(sm).length < 20000, 'small enough to post often (' + JSON.stringify(sm).length + ' bytes)'); eq(JSON.parse(JSON.stringify(sm)), sm, 'plain JSON');
done();
