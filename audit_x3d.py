"""audit_x3d.py — structural audit of an H-Anim X3D avatar file (resume section 8)."""
import sys, re, collections
import xml.etree.ElementTree as ET

def local(tag): return tag.rsplit('}', 1)[-1]

def parse(path):
    raw = open(path, 'r', encoding='utf-8').read()
    lines = [l for l in raw.splitlines(keepends=True)
             if not l.strip().startswith('<?xml') and not l.strip().startswith('<!DOCTYPE')]
    return ET.fromstring(''.join(lines))

def audit(path, quiet=False):
    root = parse(path)
    defs, timers, routes, exports, imports = {}, [], [], [], []
    displacers = 0
    for el in root.iter():
        t = local(el.tag)
        d = el.get('DEF')
        if d:
            defs.setdefault(d, []).append(t)
        if t == 'TimeSensor': timers.append(el)
        elif t == 'ROUTE': routes.append(el.attrib)
        elif t == 'EXPORT': exports.append(el.attrib)
        elif t == 'IMPORT': imports.append(el.attrib)
        elif t == 'HAnimDisplacer': displacers += 1
    defset = set(defs)
    dangling = sorted({e for r in routes for e in (r.get('fromNode'), r.get('toNode')) if e not in defset})
    bad_exports = sorted({e['localDEF'] for e in exports if e.get('localDEF') not in defset})
    as_names = collections.Counter((e.get('AS') or e.get('localDEF')) for e in exports)
    dup_as = sorted(k for k, v in as_names.items() if v > 1)
    dup_defs = sorted(k for k, v in defs.items() if len(v) > 1)
    ws_defs = sorted(k for k in defset if re.search(r'\s', k))
    routed_timers = {r['fromNode'] for r in routes if r.get('fromField') == 'fraction_changed'}
    timer_state = {}
    for ts in timers:
        d = ts.get('DEF')
        if d in routed_timers and not d.startswith('WireTimer_'):
            timer_state[d] = {k: ts.get(k) for k in ('loop', 'enabled', 'startTime', 'stopTime', 'cycleInterval', 'description')}
    res = dict(timesensors=len(timers), wire_timers=sum(1 for t in timers if (t.get('DEF') or '').startswith('WireTimer_')),
               routed_clip_timers=len(timer_state), exports=len(exports), routes=len(routes),
               dangling=dangling, bad_exports=bad_exports, dup_export_as=dup_as, dup_defs=dup_defs,
               whitespace_defs=ws_defs, displacers=displacers, timer_state=timer_state)
    if not quiet:
        for k, v in res.items():
            if k == 'timer_state': continue
            print(f'{k:20s} {v}')
        print('routed clip timers:')
        for d, s in sorted(timer_state.items()):
            print('  ', d, s)
    return res

if __name__ == '__main__':
    audit(sys.argv[1])
