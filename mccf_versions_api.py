"""Scene history and drafts for the Composer / Events Editor.

Layout (nothing outside these paths is touched; the live files stay exactly where the Loader and Composer already read them):
    scenes/<scene>/<scene>_scene.xml          the live scene wrapper (events, zones, placements)
    static/x3d/<scene>.x3d                    the live X3D
    scenes/<scene>/versions/<NNNN>/           one earlier state: the same two files + meta.json
    scenes/<scene>__draft__<label>/ ...       a DRAFT is simply a scene named  <scene>__draft__<label>  (same files, same tools can open it)
                                              the Loader's list (/scene/x3d/list) leaves drafts out, so Play All never picks one up by accident

History is automatic: just before a save overwrites a scene, the state about to be lost is copied into versions/ (hook_before_write).
A manual "Save version" names the CURRENT state.  Restore copies an old state back over the live files, after saving the current state first,
so a restore can itself be undone.  Promote copies a draft over its base scene (again after saving the base's current state).

Routes (all JSON):
    GET  /scene/versions?scene=NAME                      -> {current, versions:[...newest first], drafts:[...]}
    POST /scene/versions/save      {scene, label?, note?}  name the current state
    POST /scene/versions/restore   {scene, n}
    POST /scene/drafts/promote     {draft}
    POST /scene/drafts/discard     {draft}                 moved to scenes/_trash/, not deleted
Writes are accepted from this machine only (MCCF_ALLOW_REMOTE_SAVE=1 lifts that), like the other save routes.
"""
import hashlib
import json
import os
import re
import shutil
import time

from flask import Blueprint, jsonify, request

DRAFT_MARK = '__draft__'
COALESCE_SECONDS = 4           # the two writes of one export (x3d, then scene xml) are one version, not two
KEEP_AUTO = 60                 # automatic versions kept per scene (named ones are never pruned)
_SAFE = re.compile(r'[^A-Za-z0-9_\-]')


def safe(s):
    """Same sanitiser as mccf_api._safe_path_component: the folder name and the .x3d name must stay the same string."""
    s = _SAFE.sub('_', (s or '').strip())
    return s or 'unnamed'


def is_draft(name):
    return DRAFT_MARK in (name or '')


def split_draft(name):
    base, _, label = (name or '').partition(DRAFT_MARK)
    return base, label


class Store:
    def __init__(self, root):
        self.root = root
        self.scenes = os.path.join(root, 'scenes')
        self.x3d = os.path.join(root, 'static', 'x3d')
        self._hooked = {}

    # ---- paths ----
    def xml_path(self, scene):
        return os.path.join(self.scenes, scene, scene + '_scene.xml')

    def x3d_path(self, scene):
        return os.path.join(self.x3d, scene + '.x3d')

    def vdir(self, scene):
        return os.path.join(self.scenes, scene, 'versions')

    # ---- helpers ----
    @staticmethod
    def _read(path):
        try:
            with open(path, 'rb') as f:
                return f.read()
        except OSError:
            return None

    @staticmethod
    def _write(path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp_%d' % os.getpid()
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)

    @staticmethod
    def _sha(xml, x3d):
        h = hashlib.sha256()
        h.update(xml or b''); h.update(b'\0'); h.update(x3d or b'')
        return h.hexdigest()

    @staticmethod
    def _summary(xml):
        t = (xml or b'').decode('utf-8', 'replace')
        return {'cues': len(re.findall(r'<(?:Cue|EventCue)\b', t)),                       # the Composer writes <EventCues><Cue .../></EventCues> 'zones': len(re.findall(r'<Zone\b', t)),
                'agents': len(re.findall(r'<EmotionalArc\b', t)), 'waypoints': len(re.findall(r'<Waypoint\b', t))}

    def _numbers(self, scene):
        d = self.vdir(scene)
        if not os.path.isdir(d):
            return []
        return sorted(int(n) for n in os.listdir(d) if n.isdigit() and os.path.isdir(os.path.join(d, n)))

    def _meta(self, scene, n):
        try:
            with open(os.path.join(self.vdir(scene), '%04d' % n, 'meta.json'), encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    # ---- history ----
    def snapshot(self, scene, kind='auto', label='', note=''):
        """Copy the live files into the next version.  None when there is nothing to keep (no files, or identical to the newest version)."""
        scene = safe(scene)
        xml, x3d = self._read(self.xml_path(scene)), self._read(self.x3d_path(scene))
        if xml is None and x3d is None:
            return None
        sha = self._sha(xml, x3d)
        nums = self._numbers(scene)
        last = self._meta(scene, nums[-1]) if nums else None
        if last and last.get('sha') == sha:                                # unchanged since the newest version: only a name can be added
            if label and not last.get('label'):
                last['label'] = label; last['note'] = note or last.get('note', '')
                self._write(os.path.join(self.vdir(scene), '%04d' % nums[-1], 'meta.json'), json.dumps(last, indent=1).encode('utf-8'))
            return last
        n = (nums[-1] + 1) if nums else 1
        d = os.path.join(self.vdir(scene), '%04d' % n)
        if xml is not None: self._write(os.path.join(d, scene + '_scene.xml'), xml)
        if x3d is not None: self._write(os.path.join(d, scene + '.x3d'), x3d)
        meta = {'n': n, 'kind': kind, 'label': label or '', 'note': note or '', 't': time.time(), 'sha': sha,
                'hasXml': xml is not None, 'hasX3d': x3d is not None, 'bytes': len(xml or b'') + len(x3d or b'')}
        meta.update(self._summary(xml))
        self._write(os.path.join(d, 'meta.json'), json.dumps(meta, indent=1).encode('utf-8'))
        self._prune(scene)
        return meta

    def before_write(self, scene):
        """Called by the save routes just before they overwrite a scene file.  One export writes two files (the x3d, then the scene xml) a moment
        apart; only the FIRST write keeps a version, so the pair is never stored as a half-old, half-new mixture."""
        scene = safe(scene); now = time.time()
        recent = now - self._hooked.get(scene, 0) < COALESCE_SECONDS
        self._hooked[scene] = now
        return None if recent else self.snapshot(scene, 'auto')

    def _prune(self, scene):
        autos = [n for n in self._numbers(scene) if (self._meta(scene, n) or {}).get('kind') == 'auto' and not (self._meta(scene, n) or {}).get('label')]
        for n in autos[:-KEEP_AUTO]:
            shutil.rmtree(os.path.join(self.vdir(scene), '%04d' % n), ignore_errors=True)

    def listing(self, scene):
        scene = safe(scene)
        xml, x3d = self._read(self.xml_path(scene)), self._read(self.x3d_path(scene))
        sha = self._sha(xml, x3d) if (xml is not None or x3d is not None) else None
        versions = []
        for n in reversed(self._numbers(scene)):
            m = self._meta(scene, n)
            if m: versions.append(m)
        cur = None
        if sha is not None:
            mt = max([os.path.getmtime(p) for p in (self.xml_path(scene), self.x3d_path(scene)) if os.path.exists(p)] or [0])
            cur = {'sha': sha, 'mtime': mt, 'hasXml': xml is not None, 'hasX3d': x3d is not None, 'sameAsNewestVersion': bool(versions and versions[0]['sha'] == sha)}
            cur.update(self._summary(xml))
        return {'scene': scene, 'isDraft': is_draft(scene), 'base': split_draft(scene)[0], 'current': cur, 'versions': versions, 'drafts': self.drafts(split_draft(scene)[0])}

    def restore(self, scene, n):
        scene = safe(scene)
        meta = self._meta(scene, n)
        if not meta:
            raise KeyError('no version %s of %s' % (n, scene))
        d = os.path.join(self.vdir(scene), '%04d' % n)
        xml, x3d = self._read(os.path.join(d, scene + '_scene.xml')), self._read(os.path.join(d, scene + '.x3d'))
        self.snapshot(scene, 'auto', note='before restoring version %d' % n)      # so a restore can be undone
        if xml is not None: self._write(self.xml_path(scene), xml)
        if x3d is not None: self._write(self.x3d_path(scene), x3d)
        return meta

    # ---- drafts ----
    def drafts(self, base):
        out = []
        if not os.path.isdir(self.scenes):
            return out
        for name in sorted(os.listdir(self.scenes)):
            b, label = split_draft(name)
            if label and b == base and os.path.isfile(self.xml_path(name)):
                out.append({'name': name, 'label': label, 'mtime': os.path.getmtime(self.xml_path(name)), 'cues': self._summary(self._read(self.xml_path(name)))['cues']})
        out.sort(key=lambda d: -d['mtime'])
        return out

    def promote(self, draft):
        draft = safe(draft)
        base, label = split_draft(draft)
        if not label or not base:
            raise ValueError('%s is not a draft' % draft)
        xml, x3d = self._read(self.xml_path(draft)), self._read(self.x3d_path(draft))
        if xml is None:
            raise KeyError('draft %s has no scene file' % draft)
        self.snapshot(base, 'auto', note='before promoting draft "%s"' % label)
        def rename(b):                                                         # the draft's own name inside the files becomes the base name
            return b.replace(draft.encode('utf-8'), base.encode('utf-8')) if b is not None else None
        self._write(self.xml_path(base), rename(xml))
        if x3d is not None: self._write(self.x3d_path(base), rename(x3d))
        return {'base': base, 'label': label}

    def discard(self, draft):
        draft = safe(draft)
        if not is_draft(draft):
            raise ValueError('only drafts can be discarded')
        trash = os.path.join(self.scenes, '_trash', '%s-%d' % (draft, int(time.time())))
        os.makedirs(trash, exist_ok=True)
        sd = os.path.join(self.scenes, draft)
        if os.path.isdir(sd): shutil.move(sd, os.path.join(trash, 'scene'))
        if os.path.isfile(self.x3d_path(draft)): shutil.move(self.x3d_path(draft), os.path.join(trash, draft + '.x3d'))
        return trash


def register_versions_api(app, root):
    """Call once from mccf_api.py:  versions = register_versions_api(app, os.path.dirname(os.path.abspath(__file__)))"""
    store = Store(root)
    bp = Blueprint('scene_versions', __name__)

    def _guard():
        if os.environ.get('MCCF_ALLOW_REMOTE_SAVE') != '1' and request.remote_addr not in ('127.0.0.1', '::1'):
            return jsonify({'ok': False, 'error': 'only this machine may change scene versions'}), 403
        return None

    def _body():
        b = request.get_json(silent=True)
        return b if isinstance(b, dict) else {}

    @bp.route('/scene/versions', methods=['GET'])
    def versions_list():
        scene = request.args.get('scene', '').strip()
        if not scene:
            return jsonify({'ok': False, 'error': 'scene required'}), 400
        out = store.listing(scene); out['ok'] = True
        return jsonify(out)

    @bp.route('/scene/versions/save', methods=['POST'])
    def versions_save():
        g = _guard()
        if g: return g
        b = _body(); scene = (b.get('scene') or '').strip()
        if not scene: return jsonify({'ok': False, 'error': 'scene required'}), 400
        m = store.snapshot(scene, 'named', label=str(b.get('label') or '')[:80], note=str(b.get('note') or '')[:300])
        if m is None: return jsonify({'ok': False, 'error': 'nothing saved for %s yet: export it first' % safe(scene)}), 404
        return jsonify({'ok': True, 'version': m})

    @bp.route('/scene/versions/restore', methods=['POST'])
    def versions_restore():
        g = _guard()
        if g: return g
        b = _body(); scene = (b.get('scene') or '').strip()
        try: n = int(b.get('n'))
        except (TypeError, ValueError): return jsonify({'ok': False, 'error': 'n required'}), 400
        try: m = store.restore(scene, n)
        except KeyError as e: return jsonify({'ok': False, 'error': str(e.args[0])}), 404
        return jsonify({'ok': True, 'restored': m, 'scene': safe(scene)})

    @bp.route('/scene/drafts/promote', methods=['POST'])
    def drafts_promote():
        g = _guard()
        if g: return g
        try: r = store.promote(_body().get('draft', ''))
        except ValueError as e: return jsonify({'ok': False, 'error': str(e)}), 400
        except KeyError as e: return jsonify({'ok': False, 'error': str(e.args[0])}), 404
        r['ok'] = True
        return jsonify(r)

    @bp.route('/scene/drafts/discard', methods=['POST'])
    def drafts_discard():
        g = _guard()
        if g: return g
        try: t = store.discard(_body().get('draft', ''))
        except ValueError as e: return jsonify({'ok': False, 'error': str(e)}), 400
        return jsonify({'ok': True, 'movedTo': os.path.relpath(t, root)})

    app.register_blueprint(bp)
    app.mccf_versions = store
    return store
