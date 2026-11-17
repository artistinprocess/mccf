#!/usr/bin/env python3
"""MCCF as a read-only Web of Worlds (WoWAPI 0.0.1) participant.

publish   an exported MCCF scene  ->  a folder of static, content-addressed files (no server code needed to host it)
facade    a small Flask blueprint that serves that folder with the HTTP behaviour WoW asks for (ETag, HEAD, 304, 406, 405)

    python mccf_wow.py publish --x3d static/x3d/GardenOfTheGoddess_Scene01.x3d --out wow_publish \
                               [--scene-xml scenes/Garden/Garden_scene.xml] [--config publish.json]

Layout written:
    <out>/<scene>/assets/<name>-<hash8>.<ext>     immutable; the X3D is a copy whose url attributes point at these names
    <out>/<scene>/versions/<N>/wow.json           world, views, portals, spatial graph, asset table
    <out>/<scene>/current.json                    {"version": N, "digest": ...}

Only authored scene content is published.  Timers, interpolators, routes, scripts and prototypes (the cue machinery) are not
described anywhere in the output.  Nothing here writes, and the facade answers 405 to any method but GET, HEAD and OPTIONS.
"""
import argparse, hashlib, html, json, math, os, re, sys, datetime
import xml.etree.ElementTree as ET

MEDIA = {'.x3d': 'model/x3d+xml', '.x3dv': 'model/x3d-vrml', '.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json',
         '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg', '.mp4': 'video/mp4', '.png': 'image/png',
         '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.mid': 'audio/midi', '.midi': 'audio/midi'}
TAG = re.compile(r'<([A-Za-z][\w:.-]*)((?:\s+[\w:.-]+\s*=\s*(?:"[^"]*"|\'[^\']*\'))*)(\s*/?>)')       # a start tag, attribute values may hold '>'
URL_ATTR = re.compile(r'(\burl\s*=\s*)(\'[^\']*\'|"[^"]*")')
GENERATED = re.compile(r'_EC_')                                   # nodes the Composer writes for cues
DEFAULTS = {'public_prefixes': ['Avatar_', 'PlacedAsset_', 'Zone_', 'ZoneAsset_'], 'hidden_views': ['VP_Free', 'MCCF_TerrainCam'],
            'asset_base': '/wow/assets/'}
SAFE_NAME = re.compile(r'^[A-Za-z0-9._-]+$')


# ───────────────────────────── helpers ─────────────────────────────
def _rb(p):
    with open(p, 'rb') as f: return f.read()
def _rt(p, errors='strict'):
    with open(p, encoding='utf-8', errors=errors) as f: return f.read()
def _wb(p, b):
    with open(p, 'wb') as f: f.write(b)
def _wt(p, t):
    with open(p, 'w', encoding='utf-8') as f: f.write(t)
def _h8(b): return hashlib.sha256(b).hexdigest()[:8]
def _floats(s, n, dflt):
    try:
        v = [float(x) for x in re.split(r'[,\s]+', (s or '').strip()) if x != '']
        return v if len(v) == n else list(dflt)
    except ValueError:
        return list(dflt)
def _mf_strings(raw):
    """value of an X3D MFString attribute -> list of python strings (quoted items, or one bare item)"""
    s = html.unescape(raw).strip()
    items = [m.replace('\\"', '"') for m in re.findall(r'"((?:[^"\\]|\\.)*)"', s)]
    return items if items else ([s] if s else [])
def _mf_write(items): return "'" + ' '.join('"%s"' % i.replace('"', '\\"') for i in items).replace("'", '&apos;') + "'"
def _is_remote(u): return bool(re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', u)) or u.startswith('//')
def _mm(a, b): return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
def _ident(): return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
def _trans(t): m = _ident(); m[0][3], m[1][3], m[2][3] = t; return m
def _scale(s): m = _ident(); m[0][0], m[1][1], m[2][2] = s; return m
def _rot(r):
    x, y, z, a = r; n = math.sqrt(x * x + y * y + z * z)
    if n < 1e-12 or a == 0: return _ident()
    x, y, z = x / n, y / n, z / n; c, s = math.cos(a), math.sin(a); t = 1 - c
    return [[t * x * x + c, t * x * y - s * z, t * x * z + s * y, 0], [t * x * y + s * z, t * y * y + c, t * y * z - s * x, 0],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c, 0], [0, 0, 0, 1.0]]
def _neg(v): return [-x for x in v]
def local_matrix(translation, rotation, scale, scale_orientation, center):
    """X3D Transform:  T * C * R * SR * S * -SR * -C ;  returned as 16 numbers, COLUMN-major (the glTF `matrix` convention)"""
    m = _mm(_trans(translation), _trans(center)); m = _mm(m, _rot(rotation)); m = _mm(m, _rot(scale_orientation))
    m = _mm(m, _scale(scale)); so = list(scale_orientation); so[3] = -so[3]; m = _mm(m, _rot(so)); m = _mm(m, _trans(_neg(center)))
    return [round(m[r][c], 9) + 0.0 for c in range(4) for r in range(4)]


# ───────────────────────────── assets ─────────────────────────────
class Assets:
    """Copies every referenced file into <scene>/assets under a name that carries a hash of its bytes."""
    def __init__(self, out_assets, base):
        self.dir, self.base, self.by_src, self.table, self.missing, self.warnings, self._busy = out_assets, base, {}, [], [], [], set()
        os.makedirs(self.dir, exist_ok=True)

    def publish_file(self, src, role='dependency'):
        src = os.path.abspath(src)
        if src in self.by_src: return self.by_src[src]
        if src in self._busy:
            self.warnings.append('reference cycle at %s; left as authored' % os.path.basename(src)); return None
        self._busy.add(src)
        try:
            data = _rb(src); ext = os.path.splitext(src)[1].lower()
            if ext == '.x3d': data = self.rewrite_x3d(data.decode('utf-8'), os.path.dirname(src)).encode('utf-8')
            stem = re.sub(r'[^A-Za-z0-9._-]+', '_', os.path.splitext(os.path.basename(src))[0]) or 'asset'
            fname = '%s-%s%s' % (stem, _h8(data), ext)
            path = os.path.join(self.dir, fname)
            if not os.path.exists(path): _wb(path, data)
            rec = {'id': len(self.table) + 1, 'file': fname, 'uri': self.base + fname, 'mediaType': MEDIA.get(ext, 'application/octet-stream'),
                   'bytes': len(data), 'etag': '"%s"' % hashlib.sha256(data).hexdigest(), 'role': role, 'source': os.path.basename(src)}
            self.table.append(rec); self.by_src[src] = rec; return rec
        finally:
            self._busy.discard(src)

    def rewrite_x3d(self, text, base_dir):
        """every url="..." on every node except Anchor (an Anchor is a link out, not a dependency) that names a file here is republished"""
        def one(m):
            items = _mf_strings(m.group(2)[1:-1]); out, changed = [], False
            for it in items:
                if not it or _is_remote(it): out.append(it); continue
                path, _, frag = it.partition('#'); src = os.path.normpath(os.path.join(base_dir, path))
                if not path or not os.path.isfile(src):
                    if path and it not in self.missing: self.missing.append(it)
                    out.append(it); continue
                rec = self.publish_file(src)
                if rec is None: out.append(it); continue
                out.append(rec['file'] + ('#' + frag if frag else '')); changed = True
            return m.group(1) + (_mf_write(out) if changed else m.group(2))
        def tag(m):
            if m.group(1) == 'Anchor': return m.group(0)
            return '<' + m.group(1) + URL_ATTR.sub(one, m.group(2)) + m.group(3)
        return TAG.sub(tag, text)


# ───────────────────────────── scene description ─────────────────────────────
def _scene_duration(xml_path):
    if not xml_path or not os.path.isfile(xml_path): return None
    t = _rt(xml_path, errors='replace'); end = None
    for m in re.finditer(r'<Cue\b[^>]*>', t):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(0)))
        try: e = float(a.get('t0', 0)) + float(a.get('dur', 0))
        except ValueError: continue
        end = e if end is None else max(end, e)
    return None if end is None else round(end, 3)

def describe(root, rewritten_text, assets, cfg, scene_name, duration):
    """-> (world, views, portals, spatial, node_root)"""
    scene = root.find('Scene')
    title = next((m.get('content') for m in root.iter('meta') if m.get('name') == 'title' and m.get('content')), scene_name)
    prefixes, hidden = tuple(cfg['public_prefixes']), set(cfg['hidden_views'])
    by_file = {r['file']: r for r in assets.table}
    views, portals, ids = [], [], {'node': 1}

    def first_asset(el):
        for c in el.iter('Inline'):
            for u in _mf_strings(c.get('url') or ''):
                rec = by_file.get(u.partition('#')[0])
                if rec: return rec['uri']
        return None

    def walk(el, parent_node):
        for c in el:
            if c.tag in ('ProtoDeclare', 'ExternProtoDeclare', 'Script'): continue
            if c.tag in ('Viewpoint', 'OrthoViewpoint') and c.get('DEF') and c.get('DEF') not in hidden and not GENERATED.search(c.get('DEF')):
                views.append({'id': len(views) + 1, 'x-mccf': {'def': c.get('DEF'), 'label': c.get('description') or c.get('DEF'), 'kind': c.tag,
                              'localPose': {'frame': 'scene-local', 'units': 'm', 'up': '+y', 'position': _floats(c.get('position'), 3, [0, 0, 10 if c.tag == 'Viewpoint' else 0]),
                                            'orientation': _floats(c.get('orientation'), 4, [0, 0, 1, 0])}}})
            if c.tag == 'Anchor':
                urls = [u for u in _mf_strings(c.get('url') or '') if u and not u.startswith('#')]
                if urls: portals.append({'id': len(portals) + 1, 'x-mccf': {'label': c.get('description') or c.get('DEF') or urls[0], 'target': urls[0], 'source': 'Anchor'}})
            node = parent_node
            if c.tag == 'Transform' and c.get('DEF') and c.get('DEF').startswith(prefixes) and not GENERATED.search(c.get('DEF')):
                t, r, s = _floats(c.get('translation'), 3, [0, 0, 0]), _floats(c.get('rotation'), 4, [0, 0, 1, 0]), _floats(c.get('scale'), 3, [1, 1, 1])
                so, ce = _floats(c.get('scaleOrientation'), 4, [0, 0, 1, 0]), _floats(c.get('center'), 3, [0, 0, 0])
                ids['node'] += 1
                node = {'id': ids['node'], 'label': c.get('DEF'), 'names': [c.get('DEF')], 'parent': parent_node['id'],
                        'localTransform': local_matrix(t, r, s, so, ce), 'x-mccf': {'transform': {'translation': t, 'rotation': r, 'scale': s}}, 'children': []}
                uri = first_asset(c)
                if uri: node['spatialAssetURI'] = uri
                parent_node['children'].append(node)
            walk(c, node)

    root_node = {'id': 1, 'label': title, 'names': [], 'localTransform': [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], 'children': []}
    walk(scene, root_node)
    for p in cfg.get('portals', []):
        x = {'label': p.get('label') or p.get('target'), 'target': p['target'], 'source': 'config'}
        for k in ('entry', 'condition'):
            if p.get(k): x[k] = p[k]
        if p.get('position'): x['localPose'] = {'frame': 'scene-local', 'units': 'm', 'up': '+y', 'position': p['position']}
        portals.append({'id': len(portals) + 1, 'x-mccf': x})

    nav = next((m for m in root.iter('NavigationInfo')), None)
    content = {'label': title, 'duration': duration}
    for k in ('age_restriction', 'license', 'cost'):
        if cfg.get(k) is not None: content[k] = cfg[k]
    world = {'content': {k: v for k, v in content.items() if v is not None},
             'presence': {k: v for k, v in {'navigation': ', '.join(_mf_strings(nav.get('type') or '')) if nav is not None else None}.items() if v},
             'technology': {'runtime': 'X3D %s (X_ITE) with the MCCF cue runtime' % (root.get('version') or '')},
             'users': {'active_user_count': 0, 'total_user_count': 0},
             'views': {'view_count': len(views)}, 'portals': {'portal_count': len(portals)}}
    spatial = {'id': 1, 'rootNodeID': 1}
    return world, views, portals, spatial, root_node


def publish(x3d_path, out_dir, config=None, scene_xml=None, now=None):
    cfg = dict(DEFAULTS); cfg.update(config or {})
    scene = re.sub(r'[^A-Za-z0-9._-]+', '_', os.path.splitext(os.path.basename(x3d_path))[0])
    sdir = os.path.join(out_dir, scene); assets = Assets(os.path.join(sdir, 'assets'), cfg['asset_base'])
    # the scene itself is an asset: publish_file rewrites its url attributes and names it by hash
    scene_rec = assets.publish_file(x3d_path, role='scene')
    published_text = _rt(os.path.join(assets.dir, scene_rec['file']))
    root = ET.fromstring(re.sub(r'<!DOCTYPE[^>]*>', '', published_text, count=1).encode('utf-8'))
    world, views, portals, spatial, node_root = describe(root, published_text, assets, cfg, scene, _scene_duration(scene_xml))
    world['x-mccf'] = {'scene': scene, 'sceneAsset': scene_rec['uri'], 'sceneAssetEtag': scene_rec['etag'], 'generator': 'MCCF Scene Composer'}
    doc = {'world': world, 'views': views, 'portals': portals, 'spatial': spatial, 'nodes': node_root, 'assets': assets.table,
           'report': {'missing': assets.missing, 'warnings': assets.warnings}}
    digest = hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()
    cur_path = os.path.join(sdir, 'current.json'); cur = json.loads(_rt(cur_path)) if os.path.isfile(cur_path) else None
    if cur and cur.get('digest') == digest:
        return {'scene': scene, 'version': cur['version'], 'unchanged': True, 'missing': assets.missing, 'assets': len(assets.table)}
    version = (cur['version'] + 1) if cur else 1
    doc['world']['content']['version'] = version
    doc['world']['x-mccf']['published'] = (now or datetime.datetime.now(datetime.timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ')
    vdir = os.path.join(sdir, 'versions', str(version)); os.makedirs(vdir, exist_ok=True)
    _wt(os.path.join(vdir, 'wow.json'), json.dumps(doc, indent=2, ensure_ascii=False))
    _wt(cur_path, json.dumps({'version': version, 'digest': digest}))
    return {'scene': scene, 'version': version, 'unchanged': False, 'missing': assets.missing, 'assets': len(assets.table), 'dir': sdir}


# ───────────────────────────── the read-only facade ─────────────────────────────
def register_wow(app, root, scene, app_url=None, serve_root=False):
    """Add the WoW endpoints to a Flask app.  `root` is the --out folder of `publish`.  GET/HEAD/OPTIONS only."""
    from flask import Blueprint, jsonify, request, abort, make_response, send_file, redirect
    bp = Blueprint('wow_' + scene, __name__); sdir = os.path.join(root, scene)

    def current():
        p = os.path.join(sdir, 'current.json')
        if not os.path.isfile(p): abort(404)
        return json.loads(_rt(p))['version']

    def load(pinned):
        v = pinned if pinned is not None else current()
        p = os.path.join(sdir, 'versions', str(v), 'wow.json')
        if not os.path.isfile(p): abort(404)
        return json.loads(_rt(p)), v

    def ver():
        q = request.args.get('v')
        if q is None: return None
        if not q.isdigit(): abort(400)
        return int(q)

    def send(obj, pinned):
        body = json.dumps(obj, ensure_ascii=False, indent=1).encode('utf-8')
        r = make_response(body); r.mimetype = 'application/json'; r.set_etag(hashlib.sha256(body).hexdigest())
        r.headers['Cache-Control'] = 'public, max-age=31536000, immutable' if pinned is not None else 'no-cache'
        return r.make_conditional(request)

    def find(n, i):
        if n['id'] == i: return n
        for c in n.get('children', []):
            f = find(c, i)
            if f: return f

    @bp.after_request
    def headers(r):
        r.headers['Access-Control-Allow-Origin'] = '*'; r.headers['Access-Control-Expose-Headers'] = 'ETag'
        r.headers['X-Content-Type-Options'] = 'nosniff'; return r

    if serve_root and app_url:
        @bp.route('/')
        def home(): return redirect(app_url, code=302)       # no fragment in Location: the browser keeps #join / #follow / #preview

    @bp.route('/wow/world')
    def world():
        pv = ver(); d, v = load(pv); return send(d['world'], pv)

    @bp.route('/wow/view/<int:i>')
    def view(i):
        pv = ver(); d, v = load(pv)
        if not 1 <= i <= len(d['views']): abort(404)
        return send(d['views'][i - 1], pv)

    @bp.route('/wow/portal/<int:i>')
    def portal(i):
        pv = ver(); d, v = load(pv)
        if not 1 <= i <= len(d['portals']): abort(404)
        return send(d['portals'][i - 1], pv)

    @bp.route('/wow/spatial/<int:i>')
    def spatial(i):
        pv = ver(); d, v = load(pv)
        if i != d['spatial']['id']: abort(404)
        return send(d['spatial'], pv)

    @bp.route('/wow/spatial/<int:i>/node/<int:n>')
    def node(i, n):
        pv = ver(); d, v = load(pv)
        f = find(d['nodes'], n) if i == d['spatial']['id'] else None
        if f is None: abort(404)
        return send(f, pv)

    @bp.route('/wow/user/<int:i>')
    def user(i):                                             # no identity is stored or trusted: every visitor is anonymous
        r = make_response(json.dumps({'error': 'this world keeps no user records'})); r.mimetype = 'application/json'; r.status_code = 404; return r

    def asset_rec(name):
        if not SAFE_NAME.match(name): abort(404)
        d, v = load(None)
        for a in d['assets']:
            if a['file'] == name: return a
        for vd in sorted(os.listdir(os.path.join(sdir, 'versions')), key=int, reverse=True):      # an older version's asset is still served
            for a in json.loads(_rt(os.path.join(sdir, 'versions', vd, 'wow.json')))['assets']:
                if a['file'] == name: return a
        abort(404)

    @bp.route('/wow/assets/<name>')
    def asset(name):
        a = asset_rec(name)
        if request.accept_mimetypes and request.accept_mimetypes.best_match([a['mediaType']]) is None: abort(406)
        r = send_file(os.path.join(sdir, 'assets', a['file']), mimetype=a['mediaType'], conditional=False)
        r.headers['ETag'] = a['etag']; r.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return r.make_conditional(request)

    @bp.route('/wow/assets/<name>/wow/asset')
    def asset_status(name):
        a = asset_rec(name)
        return send({'content': {'label': a['source'], 'version': 1}, 'x-mccf': {k: a[k] for k in ('uri', 'mediaType', 'bytes', 'etag', 'role')}}, 1)

    app.register_blueprint(bp)
    return bp


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0]); sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('publish'); p.add_argument('--x3d', required=True); p.add_argument('--out', default='wow_publish')
    p.add_argument('--scene-xml'); p.add_argument('--config')
    a = ap.parse_args(argv)
    cfg = json.loads(_rt(a.config)) if a.config else {}
    r = publish(a.x3d, a.out, cfg, a.scene_xml)
    print(json.dumps(r, indent=2))
    if r['missing']: print('WARNING: %d referenced file(s) not found and left as authored: %s' % (len(r['missing']), ', '.join(r['missing'])), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
