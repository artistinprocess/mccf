"""MCCF reports. One registry, one shape, shown in the Dashboard's Reports panel.

  GET /reports        -> {reports: [{id, title, description}]}
  GET /reports/<id>   -> {id, title, level, summary, items: [{level, text}]}
level is 'ok', 'warn' or 'error'. To add a report, write a function that returns
(summary, items) and add it to REPORTS."""
import os, sys, json, glob
from flask import jsonify
from lxml import etree

def _find(root, name):
    for el in root:
        if isinstance(el.tag, str) and etree.QName(el).localname == name:
            return el
    return None

def _worst(items):
    lv = {i['level'] for i in items}
    return 'error' if 'error' in lv else 'warn' if 'warn' in lv else 'ok'

def register_reports(app, here, honor_getter=None, validate_text=None):
    def scene_validation():
        items, checked, skipped, flagged = [], 0, 0, set()
        root = os.path.join(here, 'scenes')
        for path in sorted(glob.glob(os.path.join(root, '*', '*_scene.xml'))):
            name = os.path.relpath(path, root)
            if os.path.basename(os.path.dirname(path)).startswith('_'):
                continue
            try:
                r = validate_text(open(path, encoding='utf-8').read()) if validate_text else None
            except Exception as e:
                items.append({'level': 'error', 'text': '%s: could not be checked (%s)' % (name, e)}); flagged.add(name); continue
            if r is None:
                return 'The validator is not installed on this server.', [{'level': 'warn', 'text': 'Copy the xmlschemas folder beside mccf_api.py.'}]
            if any('Not a Scene document' in w for w in r['warnings']):
                skipped += 1; continue      # a wrapper or other file, not a scene
            checked += 1
            for m in r['errors']:   items.append({'level': 'error', 'text': '%s: %s' % (name, m)}); flagged.add(name)
            for m in r['warnings']: items.append({'level': 'warn',  'text': '%s: %s' % (name, m)}); flagged.add(name)
        if not checked and not skipped: return 'No saved scenes found.', []
        msg = '%d scene(s) checked; %d with findings.' % (checked, len(flagged))
        if skipped: msg += ' %d other file(s) skipped (wrappers, not scenes).' % skipped
        return msg, items

    def cultivars():
        items, n = [], 0
        for path in sorted(glob.glob(os.path.join(here, 'cultivars', '*.xml'))):
            n += 1; f = os.path.basename(path)
            try: root = etree.parse(path).getroot()
            except Exception as e:
                items.append({'level': 'error', 'text': '%s: not readable, so it is skipped at load (%s). Fix the XML or remove the file.' % (f, e)}); continue
            if etree.QName(root).localname != 'CultivarDefinition':
                items.append({'level': 'warn', 'text': '%s: not a cultivar definition (root is %s), so it is not loaded as a character.' % (f, etree.QName(root).localname)}); continue
            w = _find(root, 'Weights')
            try:
                tot = sum(float(w.get(k)) for k in 'EBPS')
                if abs(tot - 1) > 0.02: items.append({'level': 'warn', 'text': '%s: channel weights sum to %.2f, not 1.0.' % (f, tot)})
            except Exception:
                items.append({'level': 'error', 'text': '%s: Weights missing or not numbers.' % f})
            rg = _find(root, 'Regulation')
            try:
                if not 0 <= float(rg.get('value')) <= 1: items.append({'level': 'warn', 'text': '%s: regulation outside 0 to 1.' % f})
            except Exception:
                items.append({'level': 'error', 'text': '%s: Regulation missing or not a number.' % f})
            sc = _find(root, 'ShadowContext')
            try:
                if not 0.05 <= float(sc.get('lambda')) <= 1: items.append({'level': 'warn', 'text': '%s: shadow lambda outside 0.05 to 1.' % f})
            except Exception:
                items.append({'level': 'error', 'text': '%s: ShadowContext lambda missing or not a number.' % f})
        if not n: return 'No cultivar files found.', [{'level': 'warn', 'text': 'Expected cultivar_*.xml in the cultivars folder.'}]
        return '%d cultivar file(s) checked.' % n, items

    def lexicon():
        items, n = [], 0
        folder = os.path.join(here, 'lexicon_packs')
        try:
            from mccf_voice_api import _validate_pack_for_upload as chk
        except Exception as e:
            return 'The voice module is not available.', [{'level': 'error', 'text': str(e)}]
        for path in sorted(glob.glob(os.path.join(folder, '*.json'))):
            n += 1; f = os.path.basename(path)
            try: err = chk(json.load(open(path, encoding='utf-8')))
            except Exception as e: err = 'not readable JSON (%s)' % e
            if err: items.append({'level': 'error', 'text': '%s: %s' % (f, err)})
        return '%d lexicon pack(s) checked.' % n, items

    def honor():
        h = honor_getter() if honor_getter else {}
        if not h: return 'No honor data yet. It builds up while a scene is running.', []
        items = []
        for name, v in sorted(h.items()):
            lvl = 'warn' if v['mu'] < 0.4 and v['ticks'] >= 10 else 'ok'
            items.append({'level': lvl, 'text': '%s: honor %.2f over %d ticks (drift %.0f%% of the limit).' % (name, v['mu'], v['ticks'], v['drift_ratio'] * 100)})
        return '%d character(s) tracked.' % len(h), items

    REPORTS = {
        'scene-validation': ('Scene validation', 'Every saved scene, checked for form, references, ranges and missing files.', scene_validation),
        'cultivars': ('Cultivars', 'Every cultivar file: readable, a real character, weights and settings in range.', cultivars),
        'lexicon-packs': ('Lexicon packs', 'Every pack file in the lexicon folder, checked as an upload would be.', lexicon),
        'honor': ('Honor', 'Each running character\'s kept-word score. Read only.', honor),
    }

    @app.route('/reports', methods=['GET'])
    def reports_list():
        return jsonify({'reports': [{'id': k, 'title': v[0], 'description': v[1]} for k, v in REPORTS.items()]})

    @app.route('/reports/<rid>', methods=['GET'])
    def reports_run(rid):
        if rid not in REPORTS: return jsonify({'error': 'no such report'}), 404
        title, _, fn = REPORTS[rid]
        try: summary, items = fn()
        except Exception as e: return jsonify({'id': rid, 'title': title, 'level': 'error', 'summary': 'The report failed to run.', 'items': [{'level': 'error', 'text': str(e)}]})
        return jsonify({'id': rid, 'title': title, 'level': _worst(items), 'summary': summary, 'items': items})
