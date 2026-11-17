"""MCCF X3D editor launcher (default: Sunrize).

  GET  /x3dedit/config            -> {path, found, name, download}
  POST /x3dedit/config   {path}   -> saves the editor program path (blank = use the default search)
  POST /x3dedit/open     {file}   -> opens one X3D or glTF file in the editor (output kept in x3dedit_last.log)

One-way, like the Reaper launcher: MCCF starts the editor on the file and the editor saves it.
Only files inside the server's web folders (base, static, static/x3d, static/avatars) with an
.x3d/.x3dv/.x3dj/.gltf/.glb extension are opened. If the editor cannot be found the answer is
status "notfound" with a message and the download address; nothing is started.
"""
import os, re, json, glob, shutil, subprocess, time
from flask import jsonify, request

EXT = {'.x3d', '.x3dv', '.x3dj', '.gltf', '.glb'}
DOWNLOAD = 'https://create3000.github.io/sunrize/'
NAME = 'Sunrize'


def _candidates():
    home = os.path.expanduser('~')
    local = os.environ.get('LOCALAPPDATA', os.path.join(home, 'AppData', 'Local'))
    return [os.path.join(local, 'Programs', 'Sunrize', 'Sunrize.exe'),
            os.path.join(local, 'Programs', 'sunrize', 'Sunrize.exe'),
            r'C:\Program Files\Sunrize\Sunrize.exe',
            '/Applications/Sunrize.app/Contents/MacOS/Sunrize',
            '/opt/Sunrize/sunrize', '/usr/bin/sunrize', '/usr/local/bin/sunrize']


def _inner_program(prog):
    """A Windows Squirrel install puts a small launcher stub in <install>\\ and the real program in <install>\\app-<version>\\.
    The stub can exit at once when started from another program. When an app-* folder holds the same program, run that one."""
    base = os.path.dirname(prog)
    def ver(d):
        return [int(x) for x in re.findall(r'\d+', os.path.basename(d))]
    apps = sorted(glob.glob(os.path.join(base, 'app-*')), key=ver)
    for d in reversed(apps):
        c = os.path.join(d, os.path.basename(prog))
        if os.path.isfile(c):
            return c
    return ''


def register_x3dedit(app, here):
    cfg_path = os.path.join(here, 'x3dedit_config.json')
    roots = [here, os.path.join(here, 'static'), os.path.join(here, 'static', 'x3d'),
             os.path.join(here, 'static', 'avatars')]

    def get_cfg():
        try:
            return json.load(open(cfg_path, encoding='utf-8'))
        except Exception:
            return {}

    def program():
        p = get_cfg().get('path', '')
        if p and os.path.isfile(p):
            return p
        for c in _candidates():
            if os.path.isfile(c):
                return c
        return shutil.which('sunrize') or shutil.which('Sunrize') or ''

    def resolve(url):
        if not url or '://' in url or url.startswith('data:'):
            return ''
        rel = url.split('?')[0].replace('\\', '/').lstrip('/')
        rr = [os.path.realpath(x) for x in roots]
        for r in roots:
            p = os.path.realpath(os.path.join(r, rel))
            if os.path.isfile(p) and any(p.startswith(x + os.sep) for x in rr):
                return p
        return ''

    @app.route('/x3dedit/config', methods=['GET', 'POST'])
    def x3dedit_config():
        if request.method == 'POST':
            p = ((request.get_json(silent=True) or {}).get('path') or '').strip().strip('"')
            if p and not os.path.isfile(p):
                return jsonify({'status': 'error', 'error': 'No file at that path.'}), 400
            json.dump({'path': p}, open(cfg_path, 'w', encoding='utf-8'))
        return jsonify({'path': get_cfg().get('path', ''), 'found': program(), 'name': NAME, 'download': DOWNLOAD})

    @app.route('/x3dedit/open', methods=['POST'])
    def x3dedit_open():
        url = ((request.get_json(silent=True) or {}).get('file') or '').strip()
        if not url:
            return jsonify({'status': 'error', 'error': 'file required'}), 400
        if os.path.splitext(url.split('?')[0])[1].lower() not in EXT:
            return jsonify({'status': 'error', 'error': 'Not an X3D or glTF file.'}), 400
        p = resolve(url)
        if not p:
            return jsonify({'status': 'error', 'error': 'File not found inside the server folders: %s. Send the scene to the Launcher first if it has not been compiled.' % url}), 404
        prog = program()
        if not prog:
            return jsonify({'status': 'notfound',
                            'error': '%s has not been found. Install it from %s, or type the path to its program in the editor box and press Set.' % (NAME, DOWNLOAD),
                            'download': DOWNLOAD}), 200
        logp = os.path.join(here, 'x3dedit_last.log')
        try:
            lg = open(logp, 'wb')
            lg.write(('command: "%s" "%s"\n' % (prog, p)).encode('utf-8', 'replace')); lg.flush()
            run = _inner_program(prog) or prog
            env = dict(os.environ)
            env.pop('ELECTRON_RUN_AS_NODE', None)   # if set, an Electron program such as Sunrize runs as plain Node and fails at once
            lg.write(('running: "%s"\n' % run).encode('utf-8', 'replace')); lg.flush()
            proc = subprocess.Popen([run, p], stdout=lg, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, close_fds=True,
                                    cwd=os.path.dirname(run) or None, env=env)
        except Exception as e:
            return jsonify({'status': 'error', 'error': 'Could not start %s (%s): %s' % (NAME, prog, e)}), 500
        time.sleep(2.0)                     # an editor that fails to start usually exits within a moment
        code = proc.poll()
        if code is not None and code != 0:
            try:
                tail = open(logp, encoding='utf-8', errors='replace').read()[-600:]
            except Exception:
                tail = ''
            return jsonify({'status': 'error', 'error': '%s exited at once with code %s. Program: %s. Log (%s): %s' % (NAME, code, run, logp, tail.strip())}), 500
        note = ' [started %s, process %d; the editor can take several seconds to open]' % (run, proc.pid)
        if code == 0:
            note = ' [%s handed the file to a running editor window and exited; look for that window: %s]' % (prog, prog)
        return jsonify({'status': 'ok', 'opened': p + note, 'with': prog, 'pid': proc.pid})
