"""MCCF scene audio assets and the Reaper launcher.

  GET  /scene/names                  -> {scenes: [name, ...]}
  GET  /scene/audio_assets?scene=N   -> {scene, assets: [{kind, from, name, url, exists}], project}
  GET  /scene/registry[?format=xml]  -> every scene with its dm code and assets; usedBy maps an asset to its scenes
  GET  /reaper/config                -> {path, found}
  POST /reaper/config   {path}       -> saves the Reaper program path
  POST /reaper/open     {file}       -> opens one asset file in Reaper

Reaper edits and saves the file itself. MCCF only launches it, and only on files inside the
server's web folders (base, static, static/x3d) with an audio or project extension.
"""
import os, json, subprocess, sys
from flask import jsonify, request
from xml.etree import ElementTree as ET

AUDIO_EXT = {'.wav': 'audio', '.mp3': 'audio', '.ogg': 'audio', '.flac': 'audio',
             '.mid': 'midi', '.midi': 'midi', '.rpp': 'project'}
COMMON = [r'C:\Program Files\REAPER (x64)\reaper.exe', r'C:\Program Files\REAPER\reaper.exe',
          r'C:\Program Files (x86)\REAPER\reaper.exe', '/Applications/REAPER.app/Contents/MacOS/REAPER',
          '/usr/local/bin/reaper', '/opt/REAPER/reaper']

def _local(tag):
    return tag.split('}', 1)[-1] if isinstance(tag, str) else ''

def register_reaper(app, here):
    cfg_path = os.path.join(here, 'reaper_config.json')
    roots = [here, os.path.join(here, 'static'), os.path.join(here, 'static', 'x3d')]

    def get_cfg():
        try:
            return json.load(open(cfg_path, encoding='utf-8'))
        except Exception:
            return {}

    def reaper_program():
        p = get_cfg().get('path', '')
        if p and os.path.isfile(p):
            return p
        for c in COMMON:
            if os.path.isfile(c):
                return c
        return ''

    def resolve(url):
        """Map a scene URL to a real file inside the web folders, or '' if there is none."""
        if not url or '://' in url or url.startswith('data:'):
            return ''
        rel = url.replace('\\', '/').lstrip('/')
        for r in roots:
            p = os.path.realpath(os.path.join(r, rel))
            if os.path.isfile(p) and any(p.startswith(os.path.realpath(x) + os.sep) or p == os.path.realpath(x) for x in roots):
                return p
        return ''

    def scene_file(name):
        safe = ''.join(c if (c.isalnum() or c in '_-') else '_' for c in name or '')
        p = os.path.join(here, 'scenes', safe, safe + '_scene.xml')
        return safe, p

    @app.route('/scene/names')
    def scene_names():
        root = os.path.join(here, 'scenes')
        out = []
        if os.path.isdir(root):
            for d in sorted(os.listdir(root)):
                if not d.startswith('_') and os.path.isfile(os.path.join(root, d, d + '_scene.xml')):
                    out.append(d)
        return jsonify({'scenes': out})

    def collect_assets(root):
        assets, seen = [], set()

        def walk(el, owner):
            tag = _local(el.tag)
            name = el.get('id') or el.get('name') or el.get('cultivar') or owner
            for k in ('url', 'file', 'src'):
                u = el.get(k)
                if not u:
                    continue
                ext = os.path.splitext(u.split('?')[0])[1].lower()
                if ext in AUDIO_EXT and (u, tag) not in seen:
                    seen.add((u, tag))
                    assets.append({'kind': AUDIO_EXT[ext], 'from': tag, 'name': name or '', 'url': u,
                                   'exists': bool(resolve(u))})
            for ch in el:
                walk(ch, name)
        walk(root, '')
        return assets

    def project_of(safe):
        d = os.path.join(here, 'scenes', safe)
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if f.lower().endswith('.rpp'):
                return {'file': 'scenes/%s/%s' % (safe, f)}
        return None

    @app.route('/scene/audio_assets')
    def scene_audio_assets():
        safe, path = scene_file(request.args.get('scene', ''))
        if not os.path.isfile(path):
            return jsonify({'status': 'error', 'error': 'scene not found'}), 404
        try:
            tree = ET.parse(path)
        except Exception as e:
            return jsonify({'status': 'error', 'error': 'scene could not be read: %s' % e}), 400
        return jsonify({'scene': safe, 'dm': tree.getroot().get('dm', ''),
                        'assets': collect_assets(tree.getroot()), 'project': project_of(safe)})

    @app.route('/scene/registry')
    def scene_registry():
        """Every scene with its DM code (the optional dm attribute on the scene root) and the
        audio, MIDI and project files it uses. Built by scanning the scene files on each call, so it
        cannot go stale. ?format=xml returns it as a document; nothing is written to disk."""
        root = os.path.join(here, 'scenes')
        scenes, by_asset = [], {}
        for d in sorted(os.listdir(root)) if os.path.isdir(root) else []:
            path = os.path.join(root, d, d + '_scene.xml')
            if d.startswith('_') or not os.path.isfile(path):
                continue
            try:
                r = ET.parse(path).getroot()
            except Exception:
                scenes.append({'scene': d, 'dm': '', 'title': d, 'error': 'unreadable', 'assets': []})
                continue
            assets = collect_assets(r)
            scenes.append({'scene': d, 'dm': r.get('dm', ''), 'title': r.get('title', '') or r.get('name', '') or d,
                           'assets': assets, 'project': project_of(d)})
            for a in assets:
                by_asset.setdefault(a['url'], []).append(d)
        if request.args.get('format') == 'xml':
            out = ET.Element('SceneAssetRegistry')
            for sc in scenes:
                e = ET.SubElement(out, 'Scene', {'name': sc['scene'], 'dm': sc['dm'], 'title': sc['title']})
                for a in sc['assets']:
                    ET.SubElement(e, 'Asset', {'kind': a['kind'], 'url': a['url'], 'from': a['from'],
                                               'name': a['name'], 'exists': str(a['exists']).lower()})
            from flask import Response
            return Response(ET.tostring(out, encoding='unicode'), mimetype='application/xml')
        return jsonify({'scenes': scenes, 'usedBy': by_asset})

    @app.route('/reaper/config', methods=['GET', 'POST'])
    def reaper_config():
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
            p = (data.get('path') or '').strip().strip('"')
            if p and not os.path.isfile(p):
                return jsonify({'status': 'error', 'error': 'No file at that path.'}), 400
            json.dump({'path': p}, open(cfg_path, 'w', encoding='utf-8'))
        prog = reaper_program()
        return jsonify({'path': get_cfg().get('path', ''), 'found': prog})

    @app.route('/reaper/open', methods=['POST'])
    def reaper_open():
        data = request.get_json(silent=True) or {}
        url = (data.get('file') or '').strip()
        if not url:
            return jsonify({'status': 'error', 'error': 'file required'}), 400
        ext = os.path.splitext(url)[1].lower()
        if ext not in AUDIO_EXT:
            return jsonify({'status': 'error', 'error': 'Not an audio, MIDI or project file.'}), 400
        p = resolve(url)
        if not p:
            return jsonify({'status': 'error', 'error': 'File not found inside the server folders: %s' % url}), 404
        prog = reaper_program()
        try:
            if prog:
                subprocess.Popen([prog, p])
            elif hasattr(os, 'startfile'):
                os.startfile(p)          # Windows: the program associated with the file type
            else:
                return jsonify({'status': 'error', 'error': 'Reaper program not found. Set its path.'}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'error': 'Could not start Reaper: %s' % e}), 500
        return jsonify({'status': 'ok', 'opened': p, 'with': prog or 'file association'})
