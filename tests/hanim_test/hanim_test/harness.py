"""Offline harness: runs the REAL hanim_export()/hanim_joints() endpoints (Flask test client)
against a scratch copy of Anna.x3d and a reconstructed Anna cultivar."""
import os, sys, json, shutil, tempfile, importlib.util, types
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = HERE
sys.path.insert(0, HERE)
ANNA_DEFAULT = os.environ.get('ANNA_X3D', os.path.join(HERE, 'Anna.x3d'))

import fake_cultivar_lambda
sys.modules['mccf_cultivar_lambda'] = fake_cultivar_lambda
from flask import Flask
import audit_x3d

# Anna's cultivar as reconstructed from the resume (12 clips, all loop:false, bounds 0-1):
# Bow -> BowTimer (export alias of Timer8); the 6 others -> their real routed timers;
# five whitespace stubs created by the old C1 bug. ASSUMPTION: exact 12-clip list inferred
# from the resume's description, not from the real cultivar_anna.xml.
ANNA_CLIPS = [
    ('Bow', 'BowTimer'), ('Fold Arms', 'Timer2'), ('Idle', 'Timer3'), ('Look Around', 'Timer4'),
    ('Sit', 'Timer5'), ('Wait', 'Timer6'), ('Walk', 'Timer7'),
    ('Fold Arms 2', 'Fold Arms 2Timer'), ('Idle 2', 'Idle 2Timer'), ('Look Around 2', 'Look Around 2Timer'),
    ('Sit 2', 'Sit 2Timer'), ('Walk 2', 'Walk 2Timer'),
]

def cultivar_clips():
    return [dict(name=n, timerDEF=t, loop=False, priority=i, cycleInterval=6.0,
                 E_min=0.0, E_max=1.0, B_min=0.0, B_max=1.0, P_min=0.0, P_max=1.0, S_min=0.0, S_max=1.0)
            for i, (n, t) in enumerate(ANNA_CLIPS)]

def load_api(path):
    spec = importlib.util.spec_from_file_location('mccf_hanim_api_under_test', path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m

class Sandbox:
    def __init__(self, api_path, anna_path=None):
        anna_path = anna_path or ANNA_DEFAULT
        self.dir = tempfile.mkdtemp(prefix='hanim_sbx_')
        os.makedirs(os.path.join(self.dir, 'static', 'avatars')); os.makedirs(os.path.join(self.dir, 'cultivars'))
        self.x3d = os.path.join(self.dir, 'static', 'avatars', 'Anna.x3d')
        shutil.copy2(anna_path, self.x3d)
        self.orig = os.path.join(self.dir, 'Anna.orig.x3d'); shutil.copy2(anna_path, self.orig)
        cd = fake_cultivar_lambda.CultivarDefinition(); cd.name = 'Anna'; cd.hanim_src = 'Anna.x3d'
        cd.behavior_clips = cultivar_clips(); cd.behavior_default = 'Bow'
        self.cult = os.path.join(self.dir, 'cultivars', 'cultivar_anna.xml')
        open(self.cult, 'w').write(cd.to_xml())
        self.api = load_api(api_path)
        self.api._hanim_base_dir = lambda: self.dir
        app = Flask(__name__); app.register_blueprint(self.api.hanim_bp); self.client = app.test_client()

    def export(self, clips, **extra):
        body = dict(cultivar='Anna', hanim_src='Anna.x3d', receptivity=dict(E=1, B=1, P=1, S=1),
                    expressions=[], au_weights={}, clips=clips, displacers=[])
        body.update(extra)
        r = self.client.post('/hanim/export', json=body)
        return r.status_code, r.get_json()

    def joints(self):
        return self.client.get('/hanim/joints?src=Anna.x3d').get_json()

    def cultivar(self):
        return fake_cultivar_lambda.CultivarDefinition.from_xml(open(self.cult).read())

    def audit(self, which='x3d'):
        return audit_x3d.audit(self.x3d if which == 'x3d' else self.orig, quiet=True)

def editor_clip(name, timerDEF, loop=False, keyframes=None, **kw):
    """What the editor sends for an UNEDITED clip today (C3): two empty default keyframes."""
    c = dict(name=name, timerDEF=timerDEF, cycleInterval=6.0, loop=loop, priority=0,
             keyframes=keyframes if keyframes is not None else [dict(t=0.0, joints={}), dict(t=1.0, joints={})],
             cv_conditions=dict(E_min=0, E_max=1, B_min=0, B_max=1, P_min=0, P_max=1, S_min=0, S_max=1))
    c.update(kw); return c
