"""Tests for /ambient/arc/state (what the Ambient page is using; the dashboard reads it)."""
import json, os, sys, unittest, copy
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from flask import Flask
import mccf_ambient_api as api

CUR = ['E', 'B', 'P', 'S', 'Coherence']
GOOD = {'arc': {'id': 'x', 'scene': 'Garden', 'title': 'Anna arc', 'agent': 'Anna', 'waypoints': 7, 'words': 120, 'modes': ['dorian'], 'hasValence': True, 'hasUncertainty': False, 'hasReward': True},
        'stats': [{'curve': c, 'min': 0.1, 'max': 0.9, 'mean': 0.5, 'sd': 0.2, 'distinct': 5, 'range': 0.8, 'first': 0.1, 'last': 0.9, 'n': 7} for c in CUR],
        'curves': {c: [0, 0.5, 1] for c in CUR},
        'spec': {'enabled': True, 'interp': 'linear', 'span': 'whole', 'lanes': [{'curve': 'E', 'cc': 11, 'lo': 30, 'hi': 110, 'on': True}, {'curve': 'Coherence', 'cc': 91, 'lo': 20, 'hi': 90, 'on': False}]},
        'lanes': [{'curve': 'E', 'cc': 11, 'events': 40, 'tracks': 2}], 'file': 'a.xml', 'sha256': 'ab' * 32, 'source': 'song.mid', 'recipe': 'deadbeef', 'warnings': ['arc: x']}


class ArcState(unittest.TestCase):
    def setUp(self):
        app = Flask('t'); app.register_blueprint(api.ambient_bp); self.c = app.test_client(); os.environ.pop('MCCF_ALLOW_REMOTE_SAVE', None)
        self.c.post('/ambient/arc/state', json={'clear': True})
    def tearDown(self): os.environ.pop('MCCF_ALLOW_REMOTE_SAVE', None)
    def post(self, body, **kw): return self.c.post('/ambient/arc/state', data=json.dumps(body) if not isinstance(body, (bytes, str)) else body, content_type='application/json', **kw)

    def test_empty_at_first(self):
        j = self.c.get('/ambient/arc/state').get_json(); self.assertEqual((j['ok'], j['loaded'], j['state']), (True, False, None))
    def test_round_trip(self):
        r = self.post(GOOD); self.assertEqual(r.status_code, 200); self.assertTrue(r.get_json()['loaded'])
        j = self.c.get('/ambient/arc/state').get_json(); self.assertTrue(j['loaded']); self.assertTrue(j['updated'])
        s = j['state']; self.assertEqual(s['arc']['agent'], 'Anna'); self.assertEqual(len(s['stats']), 5); self.assertEqual(s['curves']['E'], [0, 0.5, 1]); self.assertEqual(s['spec']['lanes'][1]['on'], False)
        self.assertEqual(s['lanes'], [{'curve': 'E', 'cc': 11, 'events': 40, 'tracks': 2}]); self.assertEqual((s['file'], s['source'], s['recipe']), ('a.xml', 'song.mid', 'deadbeef'))
    def test_clear(self):
        self.post(GOOD); r = self.post({'clear': True}); self.assertEqual(r.status_code, 200); self.assertFalse(self.c.get('/ambient/arc/state').get_json()['loaded'])
    def test_only_known_fields_survive(self):
        b = copy.deepcopy(GOOD); b['evil'] = '<script>'; b['arc']['__proto__'] = 1; b['spec']['lanes'][0]['x'] = 'y'; self.post(b)
        s = self.c.get('/ambient/arc/state').get_json()['state']; self.assertNotIn('evil', s); self.assertNotIn('__proto__', s['arc']); self.assertNotIn('x', s['spec']['lanes'][0])
    def test_text_is_capped(self):
        b = copy.deepcopy(GOOD); b['arc']['title'] = 'T' * 5000; b['warnings'] = ['w' * 5000] * 50; self.post(b)
        s = self.c.get('/ambient/arc/state').get_json()['state']; self.assertEqual(len(s['arc']['title']), 200); self.assertEqual(len(s['warnings']), 10); self.assertEqual(len(s['warnings'][0]), 300)
    def test_bad_bodies_are_refused_and_change_nothing(self):
        self.post(GOOD)
        bad = []
        for mut in [lambda b: b.pop('arc'), lambda b: b.update(stats='x'), lambda b: b['stats'].append({'curve': 'Z'}), lambda b: b['curves'].update(Z=[0]), lambda b: b['curves'].update(E=[2]),
                    lambda b: b['curves'].update(E=[0] * 201), lambda b: b['curves'].update(E=['a']), lambda b: b['spec']['lanes'].append({'curve': 'E', 'cc': 300, 'lo': 0, 'hi': 1}),
                    lambda b: b['spec']['lanes'].append({'curve': 'Q', 'cc': 1, 'lo': 0, 'hi': 1}), lambda b: b['spec'].update(lanes=[{'curve': 'E', 'cc': 1, 'lo': 0, 'hi': 1}] * 17), lambda b: b.update(spec=[])]:
            b = copy.deepcopy(GOOD); mut(b); r = self.post(b); self.assertEqual(r.status_code, 400, r.get_data(as_text=True)); self.assertFalse(r.get_json()['ok'])
        for raw in ['not json', '[1,2]', '"s"', 'null', b'\xff\xfe']:
            self.assertEqual(self.post(raw).status_code, 400, repr(raw))
        self.assertEqual(self.c.get('/ambient/arc/state').get_json()['state']['arc']['agent'], 'Anna', 'the good state is still there')
    def test_nan_and_bool_are_not_numbers(self):
        b = copy.deepcopy(GOOD); b['stats'][0]['min'] = True; b['stats'][0]['max'] = None; r = self.post(json.dumps(b).replace('0.9', 'NaN', 1)); self.assertIn(r.status_code, (200, 400))
        if r.status_code == 200:
            s = self.c.get('/ambient/arc/state').get_json()['state']; self.assertIsNone(s['stats'][0]['min']); self.assertIsNone(s['stats'][0]['max'])
    def test_size_limit(self):
        b = copy.deepcopy(GOOD); b['file'] = 'x' * (300 * 1024); self.assertEqual(self.post(b).status_code, 413)
    def test_only_this_machine_may_post(self):
        r = self.post(GOOD, environ_overrides={'REMOTE_ADDR': '10.1.2.3'}); self.assertEqual(r.status_code, 403); self.assertFalse(self.c.get('/ambient/arc/state').get_json()['loaded'])
        self.assertEqual(self.c.get('/ambient/arc/state', environ_overrides={'REMOTE_ADDR': '10.1.2.3'}).status_code, 200)   # reading is open (the dashboard)
        os.environ['MCCF_ALLOW_REMOTE_SAVE'] = '1'; self.assertEqual(self.post(GOOD, environ_overrides={'REMOTE_ADDR': '10.1.2.3'}).status_code, 200)
    def test_clear_from_elsewhere_is_refused_too(self):
        self.post(GOOD); self.assertEqual(self.post({'clear': True}, environ_overrides={'REMOTE_ADDR': '8.8.8.8'}).status_code, 403); self.assertTrue(self.c.get('/ambient/arc/state').get_json()['loaded'])
    def test_what_the_page_sends_is_accepted(self):
        import subprocess
        out = subprocess.run(['node', '-e', "const A=require('./static/js/mccf_arc.js'),fs=require('fs');const arc=A.parseArc(fs.readFileSync('fixtures/arc_Anna_2026-09-17.xml','utf8'));"
            "console.log(JSON.stringify(A.summary(arc,0,A.defaultSpec(),{file:'a.xml',sha256:'a'.repeat(64),source:'s.mid',recipe:'abcd1234',lanes:[{curve:'E',cc:11,events:9,tracks:2}],warnings:[],updated:'now'})))"],
            capture_output=True, text=True, cwd=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
        self.assertEqual(out.returncode, 0, out.stderr); r = self.post(out.stdout); self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        s = self.c.get('/ambient/arc/state').get_json()['state']; self.assertEqual(s['arc']['agent'], 'Anna'); self.assertEqual(len(s['stats']), 5); self.assertEqual(len(s['spec']['lanes']), 4)

if __name__ == '__main__': unittest.main()
