"""Scenario suite for hanim_export / hanim_joints. Usage: python3 run_scenarios.py <path-to-mccf_hanim_api.py>
Every scenario runs on a fresh scratch copy of Anna.x3d. Exit code = number of failed checks."""
import sys, os, json, filecmp, collections
from harness import *
import diff_x3d

API = sys.argv[1]
results = []

def check(scn, label, ok, detail=''):
    results.append((scn, label, bool(ok)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f'   <- {detail}' if detail and not ok else ''))

def no_change(sbx):
    r, a, c, A, B = diff_x3d.diff(sbx.orig, sbx.x3d)
    return not (r or a or c), (len(r), len(a), len(c), [k for k in r if k[0] != 'ROUTE'][:4])

def scenario(name):
    print(f'\n== {name}'); return Sandbox(API)

UNEDITED = lambda: [editor_clip(n, t) for n, t in ANNA_CLIPS]

# ---- T1: the first-click export: cultivar loaded, nothing edited (C2 + C3 -> S1/S2) -------------
sbx = scenario('T1  first click: 12 unedited clips exported, nothing edited')
st, d = sbx.export(UNEDITED())
a = sbx.audit()
check('T1', 'export accepted (HTTP 200)', st == 200, f'{st} {d}')
ok, det = no_change(sbx)
check('T1', 'avatar file structurally unchanged (no node added/removed/changed)', ok, det)
check('T1', 'Timer6 still exists and routed', 'Timer6' in a['timer_state'])
check('T1', '0 dangling ROUTE endpoints', a['dangling'] == [], a['dangling'])
check('T1', '14 routed clip timers, 106 EXPORTs, 1526 ROUTEs', (a['routed_clip_timers'], a['exports'], a['routes']) == (14, 106, 1526), (a['routed_clip_timers'], a['exports'], a['routes']))
cl = {c['name']: c['timerDEF'] for c in sbx.cultivar().behavior_clips}
check('T1', "cultivar timerDEFs unchanged (Bow stays 'BowTimer', Wait stays 'Timer6')", cl == dict(ANNA_CLIPS), cl)

# ---- T2: C1-corrupted payload: every timerDEF fabricated as <name>Timer (with spaces) -----------
sbx = scenario('T2  C1-style payload: every timerDEF fabricated from the clip name')
st, d = sbx.export([editor_clip(n, n + 'Timer') for n, _ in ANNA_CLIPS])
a = sbx.audit()
check('T2', 'export accepted', st == 200, f'{st} {d}')
ok, det = no_change(sbx)
check('T2', 'avatar file structurally unchanged', ok, det)
check('T2', '0 dangling ROUTE endpoints', a['dangling'] == [], a['dangling'])
cl = {c['name']: c['timerDEF'] for c in sbx.cultivar().behavior_clips}
check('T2', 'cultivar gained no fabricated DEFs (every timerDEF exists in the file)',
      all(t in (dict(ANNA_CLIPS).values()) or t == 'BowTimer' for t in cl.values()), cl)

# ---- T3: authored clip; joints keyed by NAME where name != DEF (S5); idempotent re-export -------
sbx = scenario('T3  authored clip, joint keyed by name (L_Thigh != DEF L-Thigh); export twice')
kfs = [dict(t=0.0, joints={'L_Thigh': [1, 0, 0, 0.0], 'Root': [0, 1, 0, 0.0]}),
       dict(t=0.5, joints={'L_Thigh': [1, 0, 0, 0.6], 'Root': [0, 1, 0, 0.2]}),
       dict(t=1.0, joints={'L_Thigh': [1, 0, 0, 0.0], 'Root': [0, 1, 0, 0.0]})]
clips = UNEDITED() + [editor_clip('Wave', 'WaveTimer', loop=False, keyframes=kfs)]
st, d = sbx.export(clips)
a1 = sbx.audit()
check('T3', 'export accepted', st == 200, f'{st} {d}')
check('T3', 'authored TimeSensor WaveTimer written + routed', 'WaveTimer' in a1['timer_state'])
check('T3', 'no dangling ROUTE endpoints (joint name mapped to DEF)', a1['dangling'] == [], a1['dangling'])
check('T3', 'no duplicate DEFs', a1['dup_defs'] == [], a1['dup_defs'])
snap1 = open(sbx.x3d, encoding='utf-8').read()
st, d = sbx.export(clips)
snap2 = open(sbx.x3d, encoding='utf-8').read()
a2 = sbx.audit()
check('T3', 're-export is idempotent (file text identical)', snap1 == snap2)
check('T3', 're-export: no duplicate DEFs / no dangling', a2['dup_defs'] == [] and a2['dangling'] == [], (a2['dup_defs'], a2['dangling']))
kfs2 = [dict(t=0.0, joints={'Root': [0, 1, 0, 0.0]}), dict(t=1.0, joints={'Root': [0, 1, 0, 0.9]})]
st, d = sbx.export(UNEDITED() + [editor_clip('Wave', 'WaveTimer', loop=False, keyframes=kfs2)])
a3 = sbx.audit()
check('T3', 're-authored with fewer joints: old interpolators removed, still 0 dangling', a3['dangling'] == [] and a3['dup_defs'] == [], (a3['dangling'], a3['dup_defs']))
check('T3', "cultivar has 'Wave' -> WaveTimer", {c['name']: c['timerDEF'] for c in sbx.cultivar().behavior_clips}.get('Wave') == 'WaveTimer')

# ---- T4: author ticks loop on Bow -> only that flag changes -------------------------------------
sbx = scenario('T4  loop checkbox on Bow (only the loop flag may change)')
c = UNEDITED(); c[0]['loop'] = True; c[0]['loop_edited'] = True
st, d = sbx.export(c)
r, ad, ch, A, B = diff_x3d.diff(sbx.orig, sbx.x3d)
check('T4', 'export accepted', st == 200, f'{st} {d}')
check('T4', 'exactly one change: Timer8.loop', not r and not ad and ch == [('TimeSensor', 'Timer8')], (r[:3], ad[:3], ch))
check('T4', 'Timer8.loop is now true', B.get(('TimeSensor', 'Timer8'), {}).get('loop') == 'true')
check('T4', "cultivar Bow keeps timerDEF 'BowTimer', loop=True", [ (x['timerDEF'], x['loop']) for x in sbx.cultivar().behavior_clips if x['name']=='Bow'] == [('BowTimer', True)])
sbx = scenario('T4b unedited loop: same payload WITHOUT loop_edited must not touch Timer8')
c = UNEDITED(); c[0]['loop'] = True          # e.g. discovery/default said True, author never touched it
st, d = sbx.export(c); ok, det = no_change(sbx)
check('T4b', 'file unchanged when loop was not edited by the author', ok, det)

# ---- T5: keyframes on a real routed clip must not overwrite it ------------------------------------
sbx = scenario('T5  author records keyframes on Anna\'s real Bow clip')
c = UNEDITED(); c[0]['keyframes'] = [dict(t=0.0, joints={'Root': [0, 1, 0, 0]}), dict(t=1.0, joints={'Root': [0, 1, 0, 1]})]
st, d = sbx.export(c); ok, det = no_change(sbx)
check('T5', 'real Bow timer untouched', ok, det)
check('T5', 'server warns the keyframes were ignored', any('ignored' in w for w in (d or {}).get('warnings', [])), (d or {}).get('warnings'))

# ---- T6: integrity gate stops a bad write (defence in depth, simulates the OLD bug) ------------
sbx = scenario('T6  integrity gate: simulate a writer that deletes a routed timer')
orig_fn = sbx.api._write_clip_nodes
def evil(scene_el, clips, routes):
    for el in list(scene_el):
        if el.get('DEF') == 'Timer6': scene_el.remove(el)
    return orig_fn(scene_el, clips, routes)
sbx.api._write_clip_nodes = evil
before_bytes = open(sbx.x3d, 'rb').read(); before_cult = open(sbx.cult).read()
st, d = sbx.export(UNEDITED())
check('T6', 'export refused with HTTP 409', st == 409, f'{st}')
check('T6', 'message names the dangling Timer6', 'Timer6' in json.dumps(d), d)
check('T6', 'avatar + cultivar files byte-identical (nothing written)', open(sbx.x3d, 'rb').read() == before_bytes and open(sbx.cult).read() == before_cult)

# ---- T7: backups survive two exports in a row --------------------------------------------------
sbx = scenario('T7  two exports in a row keep the original recoverable')
sbx.export(UNEDITED()); sbx.export(UNEDITED())
bdir = os.path.join(sbx.dir, 'static', 'avatars', 'backups')
snaps = sorted(os.listdir(bdir)) if os.path.isdir(bdir) else []
check('T7', 'two timestamped avatar backups exist', len([s for s in snaps if s.startswith('Anna.x3d.')]) == 2, snaps)
# the .bak is the previous generation (overwritten) — the oldest timestamped copy must still equal the ORIGINAL upload
oldest = sorted((os.path.join(bdir, s) for s in snaps if s.startswith('Anna.x3d.')), key=os.path.getmtime)
check('T7', 'oldest timestamped backup == original Anna.x3d', bool(oldest) and open(oldest[0], 'rb').read() == open(sbx.orig, 'rb').read())

# ---- T8: camera rig contract ------------------------------------------------------------------------
sbx = scenario('T8  camera rig: absent = untouched; explicit {} = replaced')
sbx.export(UNEDITED())
cam = [k for k in diff_x3d.inventory(sbx.x3d, ignore_cam=False) if str(k[1]).startswith('CAM_')]
cam0 = [k for k in diff_x3d.inventory(sbx.orig, ignore_cam=False) if str(k[1]).startswith('CAM_')]
check('T8', 'no cameraRig in payload -> CAM_* rig nodes preserved', len(cam) == len(cam0) and len(cam0) > 0, (len(cam), len(cam0)))
sbx.export(UNEDITED(), cameraRig={})
cam2 = [k for k in diff_x3d.inventory(sbx.x3d, ignore_cam=False) if str(k[1]).startswith('CAM_')]
check('T8', "explicit cameraRig {} still replaces the rig (existing contract kept)", len(cam2) == 0, len(cam2))

# ---- T9: discovery (S3) ---------------------------------------------------------------------------
sbx = scenario('T9  /hanim/joints discovery')
j = sbx.joints(); cl = j['clips']
real = [c for c in cl if not c.get('hollow', False)] if 'hollow' in cl[0] else None
check('T9', 'clips carry routes/hollow/exported_as', real is not None)
if real is not None:
    check('T9', '14 real (routed) timers, 82 hollow', (len(real), len(cl) - len(real)) == (14, 82), (len(real), len(cl) - len(real)))
    bytd = {c['timerDEF']: c for c in cl}
    check('T9', 'Timer8 (bow, no loop attr) reports loop=false; Timer7 (walk, loop=true) reports true',
          bytd['Timer8']['loop'] is False and bytd['Timer7']['loop'] is True, (bytd['Timer8']['loop'], bytd['Timer7']['loop']))
    check('T9', "Timer8 exported_as ['BowTimer']", bytd['Timer8']['exported_as'] == ['BowTimer'], bytd['Timer8']['exported_as'])

bad = [r for r in results if not r[2]]
print(f"\n{'-'*60}\n{len(results) - len(bad)}/{len(results)} checks passed" + (f"  — FAILED: {[b[1] for b in bad]}" if bad else ''))
sys.exit(len(bad))
