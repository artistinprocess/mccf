"""Structural diff of two X3D files: elements by (tag, DEF/localDEF-AS/route-key) + attribute changes."""
import sys, collections
from audit_x3d import parse, local

def inventory(path, ignore_cam=True):
    root = parse(path); inv = {}
    for el in root.iter():
        t = local(el.tag)
        if t in ('X3D', 'Scene', 'head', 'meta', 'component'): continue
        if t == 'ROUTE': key = (t, el.get('fromNode'), el.get('fromField'), el.get('toNode'), el.get('toField'))
        elif t == 'EXPORT': key = (t, el.get('localDEF'), el.get('AS') or el.get('localDEF'))
        elif el.get('DEF'): key = (t, el.get('DEF'))
        else: continue
        if ignore_cam and any(str(x).startswith('CAM_') for x in key[1:]): continue
        inv[key] = dict(el.attrib)
    return inv

def diff(a, b):
    A, B = inventory(a), inventory(b)
    removed = sorted(set(A) - set(B)); added = sorted(set(B) - set(A))
    changed = sorted(k for k in set(A) & set(B) if A[k] != B[k])
    return removed, added, changed, A, B

if __name__ == '__main__':
    removed, added, changed, A, B = diff(sys.argv[1], sys.argv[2])
    print(f'removed={len(removed)} added={len(added)} attr-changed={len(changed)}')
    for label, lst in (('REMOVED', removed), ('ADDED', added)):
        c = collections.Counter(k[0] for k in lst); print(label, dict(c))
        for k in [x for x in lst if x[0] != 'ROUTE'][:12]: print('   ', k)
    for k in changed[:12]:
        print('CHANGED', k, {a: (A[k].get(a), B[k].get(a)) for a in set(A[k]) | set(B[k]) if A[k].get(a) != B[k].get(a)})
