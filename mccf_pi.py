"""MCCF Programmed Instruction (PI) server side.

  GET  /pi/lessons                  -> {lessons: [{file, title, dm, issue}]}
  GET  /pi/lesson?file=NAME.xml     -> the lesson XML
  POST /pi/lesson {xml}             -> saves static/pi/lessons/<DmCode>.xml (backup first)
  GET  /pi/media                    -> {files: [...]} in static/pi/media
  POST /pi/media (multipart: file)  -> adds an image or video to static/pi/media
  POST /pi/log   {session}          -> appends one finished or running session to pi_logs/<lesson dm>.jsonl
  GET  /pi/log?lesson=DM            -> {sessions: [...]}
  GET  /pi/report?lesson=DM         -> PI Performance Report and Analysis data for the Dashboard

Lessons live in static/pi/lessons/*.xml (schema: xmlschemas/mccf_pi.xsd). Reference images and other lesson
media live in static/pi/media/. Logs live in pi_logs/ beside this file, one JSON line per session; a session
that is posted again with the same id replaces its earlier line. Nothing else is written.
"""
import os, re, json, glob
from xml.etree import ElementTree as ET
from flask import jsonify, request, Response

NS = '{http://mccf.artistinprocess.com/pi/v1}'
DM_RE = re.compile(r'^[A-Z0-9]{3,5}-[A-Z]-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}[A-Z]-[0-9]{3}[A-Z]-[A-Z]$')
FLAG_RATE, FLAG_MIN = 0.25, 8        # a frame is flagged above 25% misses over at least 8 sessions
PATH_ORDER = ['none', 'retest', 'review', 'reteach']


def register_pi(app, here):
    lessons_dir = os.path.join(here, 'static', 'pi', 'lessons')

    @app.after_request
    def _no_stale_static(resp):
        """Pages and scripts under /static are revalidated on every load, so an installed update is never hidden by the browser cache."""
        if request.path.startswith('/static/') and request.path.lower().endswith(('.html', '.js', '.css', '.xml', '.xsd')):
            resp.headers['Cache-Control'] = 'no-cache'
        return resp
    logs_dir = os.path.join(here, 'pi_logs')

    def safe_name(n):
        n = os.path.basename(n or '')
        return n if re.match(r'^[A-Za-z0-9._-]+\.xml$', n) else ''

    @app.route('/pi/lessons')
    def pi_lessons():
        out = []
        for f in sorted(glob.glob(os.path.join(lessons_dir, '*.xml'))):
            try:
                m = ET.parse(f).getroot().find(NS + 'Meta')
                out.append({'file': os.path.basename(f), 'title': (m.findtext(NS + 'Title') or ''),
                            'dm': (m.findtext(NS + 'DmCode') or ''), 'issue': (m.findtext(NS + 'Issue') or '')})
            except Exception:
                out.append({'file': os.path.basename(f), 'title': os.path.basename(f), 'dm': '', 'issue': '', 'error': 'unreadable'})
        return jsonify({'lessons': out})

    @app.route('/pi/lesson')
    def pi_lesson():
        n = safe_name(request.args.get('file'))
        p = os.path.join(lessons_dir, n) if n else ''
        if not p or not os.path.isfile(p):
            return jsonify({'status': 'error', 'error': 'lesson not found'}), 404
        return Response(open(p, encoding='utf-8').read(), mimetype='application/xml')

    media_dir = os.path.join(here, 'static', 'pi', 'media')
    backup_dir = os.path.join(lessons_dir, '_backup')
    MEDIA_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm')

    REG_COLS = ['icn', 'issue', 'caption', 'tool', 'scene_or_data', 'used_in_dm', 'used_in_title', 'used_where',
                'date_shot', 'shot_by', 'status']

    def read_register():
        """registers/graphics_register.csv -> {icn: row}. A missing or unreadable file is an empty register."""
        import csv
        p = os.path.join(here, 'registers', 'graphics_register.csv')
        try:
            with open(p, newline='', encoding='utf-8-sig') as fh:
                rows = {r['icn']: r for r in csv.DictReader(fh) if r.get('icn')}
            for r in rows.values():   # older registers carry the old tool names
                r['tool'] = {'Ambient Engine': 'Ambient Composer', 'Help/PI': 'Programmed Instruction', 'Help PI': 'Programmed Instruction'}.get(r.get('tool'), r.get('tool'))
            return rows
        except Exception:
            return {}

    TOOLS = [('AMB', 'Ambient Composer'), ('CMP', 'Scene Composer'), ('LDR', 'X3D Loader'), ('PI', 'Programmed Instruction'),
             ('DSH', 'Dashboard'), ('GDE', 'Guide'), ('GEN', 'General')]

    def write_register(reg):
        """Write the whole register (dict icn -> row) to registers/graphics_register.csv. The old file is kept as .bak."""
        import csv, shutil
        d = os.path.join(here, 'registers'); os.makedirs(d, exist_ok=True)
        p = os.path.join(d, 'graphics_register.csv'); tmp = p + '.tmp'
        with open(tmp, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, REG_COLS); w.writeheader()
            for r in reg.values():
                w.writerow({k: r.get(k, '') for k in REG_COLS})
        if os.path.exists(p):
            shutil.copy2(p, p + '.bak')
        os.replace(tmp, p)

    def next_icn(code):
        """Next free ICN number for a tool code, looking at the register and at the files in static/pi/media."""
        top = 0
        pat = re.compile(r'^ICN-MCCF-' + re.escape(code) + r'-([0-9]{4})-')
        names = list(read_register().keys())
        if os.path.isdir(media_dir):
            names += os.listdir(media_dir)
        for n in names:
            m = pat.match(n)
            if m:
                top = max(top, int(m.group(1)))
        return 'ICN-MCCF-%s-%04d-001' % (code, top + 1)

    def check_caption(c):
        c = (c or '').strip()
        if len(c) < 8:
            return c, 'The caption is required. Say what the picture shows, in at least 8 characters.'
        if len(c) > 300:
            return c, 'The caption is too long (300 characters at most).'
        return c, ''

    @app.route('/pi/graphics/tools')
    def pi_graphics_tools():
        return jsonify({'tools': [{'code': c, 'name': n} for c, n in TOOLS]})

    @app.route('/pi/graphics/next')
    def pi_graphics_next():
        code = (request.args.get('tool') or '').upper()
        if code not in dict(TOOLS):
            return jsonify({'status': 'error', 'error': 'choose a tool'}), 400
        return jsonify({'icn': next_icn(code)})

    @app.route('/pi/graphics', methods=['POST'])
    def pi_graphics_set():
        """Add or change one register row. Body: icn, tool (code), caption, scene_or_data, shot_by, status."""
        import datetime
        b = request.get_json(silent=True) or {}
        icn = (b.get('icn') or '').strip(); code = (b.get('tool') or '').upper(); errs = []
        reg = read_register()
        have_file = os.path.isdir(media_dir) and any(os.path.splitext(n)[0] == icn for n in os.listdir(media_dir))
        if not icn or not (have_file or icn in reg):
            errs.append('There is no image called "%s" in static/pi/media.' % icn)
        if code not in dict(TOOLS):
            errs.append('Choose which tool the picture shows.')
        cap, e = check_caption(b.get('caption'))
        if e:
            errs.append(e)
        if b.get('status') and b['status'] not in ('current', 'retake', 'superseded'):
            errs.append('Status must be current, retake or superseded.')
        if errs:
            return jsonify({'status': 'error', 'error': ' '.join(errs), 'errors': errs}), 400
        r = reg.get(icn) or {'icn': icn, 'issue': icn_of(icn + '.x')[1], 'date_shot': datetime.date.today().isoformat(), 'status': 'current'}
        r.update({'tool': dict(TOOLS)[code], 'caption': cap, 'scene_or_data': (b.get('scene_or_data') or '').strip()[:120]})
        if (b.get('shot_by') or '').strip():
            r['shot_by'] = b['shot_by'].strip()[:60]
        if b.get('status'):
            r['status'] = b['status']
        reg[icn] = r
        try:
            write_register(reg)
        except Exception as ex:
            return jsonify({'status': 'error', 'error': 'The register could not be saved: %s' % ex}), 500
        return jsonify({'status': 'ok', 'icn': icn})

    def lesson_uses():
        """{media file: [{dm, title, frame}]} read from every lesson in static/pi/lessons."""
        uses = {}
        for f in sorted(glob.glob(os.path.join(lessons_dir, '*.xml'))):
            try:
                root = ET.parse(f).getroot()
                m = root.find(NS + 'Meta')
                dm, title = (m.findtext(NS + 'DmCode') or '').strip(), (m.findtext(NS + 'Title') or '').strip()
                for fr in root.iter():
                    if fr.tag in (NS + 'Step', NS + 'Question'):
                        for md in fr.findall(NS + 'Media'):
                            fn = md.get('file') or ''
                            if fn:
                                uses.setdefault(fn, []).append({'dm': dm, 'title': title, 'frame': fr.get('title') or fr.get('id') or ''})
            except Exception:
                continue
        return uses

    def icn_of(name):
        m = re.match(r'^(ICN-[A-Z0-9]+-[A-Z0-9]+-[0-9]{4})-([0-9]{3})', name)
        return (m.group(0), m.group(2)) if m else ('', '')

    def graphics_info(names):
        """For each media file: its register caption and the lessons that use it."""
        reg, uses = read_register(), lesson_uses()
        out = {}
        for n in names:
            icn, _ = icn_of(n)
            r = reg.get(os.path.splitext(n)[0]) or {}
            out[n] = {'icn': os.path.splitext(n)[0] if icn else '', 'caption': r.get('caption', ''), 'registered': bool(r),
                      'used': uses.get(n, [])}
        return out

    @app.route('/pi/graphics.csv')
    def pi_graphics_csv():
        """The graphics register as CSV, used-by columns filled in from the lessons. Files in static/pi/media that are not yet
        in the register get a row too (status 'unregistered'); register rows whose file is absent stay as they are."""
        import csv, io
        names = sorted(n for n in os.listdir(media_dir) if n.lower().endswith(MEDIA_EXT)) if os.path.isdir(media_dir) else []
        reg, uses = read_register(), lesson_uses()
        stems = {os.path.splitext(n)[0]: n for n in names}
        rows = []
        for icn, r in reg.items():
            row = {k: r.get(k, '') for k in REG_COLS}
            fn = stems.get(icn)
            if fn is not None:
                u = uses.get(fn, [])
                if u:
                    def merge(col, vals):
                        have = [v for v in (row[col] or '').split('; ') if v]
                        row[col] = '; '.join(have + [v for v in vals if v not in have])
                    merge('used_in_dm', sorted({x['dm'] for x in u}))
                    merge('used_in_title', sorted({x['title'] for x in u}))
                    merge('used_where', [x['frame'] for x in u])
                    row['status'] = 'current' if row['status'] in ('', 'unused', 'unregistered') else row['status']
                elif row['status'] in ('', 'current'):
                    row['status'] = 'unused'
            rows.append(row)
        for stem, fn in stems.items():
            if stem not in reg:
                u = uses.get(fn, [])
                rows.append({'icn': stem, 'issue': icn_of(fn)[1], 'caption': '', 'tool': '', 'scene_or_data': '',
                             'used_in_dm': '; '.join(sorted({x['dm'] for x in u})), 'used_in_title': '; '.join(sorted({x['title'] for x in u})),
                             'used_where': '; '.join(x['frame'] for x in u), 'date_shot': '', 'shot_by': '', 'status': 'unregistered'})
        buf = io.StringIO(); w = csv.DictWriter(buf, REG_COLS); w.writeheader(); w.writerows(rows)
        return Response(buf.getvalue(), mimetype='text/csv',
                        headers={'Content-Disposition': 'attachment; filename=graphics_register.csv'})

    def upload_icn(f):
        """Upload with a register entry: the file is stored under the next free ICN for the chosen tool."""
        import datetime
        code = (request.form.get('tool') or '').upper(); errs = []
        if not f or not f.filename:
            errs.append('Choose a picture or video file.')
        else:
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in MEDIA_EXT:
                errs.append('That file type is not accepted. Use ' + ', '.join(MEDIA_EXT) + '.')
        if code not in dict(TOOLS):
            errs.append('Choose which tool the picture shows.')
        cap, e = check_caption(request.form.get('caption'))
        if e:
            errs.append(e)
        data = b''
        if not errs:
            data = f.read(16 * 1024 * 1024 + 1)
            if not data:
                errs.append('The file is empty.')
            elif len(data) > 16 * 1024 * 1024:
                errs.append('The file is larger than 16 MB.')
        if errs:
            return jsonify({'status': 'error', 'error': ' '.join(errs), 'errors': errs}), 400
        icn = next_icn(code); final = icn + ext
        os.makedirs(media_dir, exist_ok=True)
        path = os.path.join(media_dir, final)
        with open(path, 'wb') as fh:
            fh.write(data)
        reg = read_register()
        reg[icn] = {'icn': icn, 'issue': '001', 'caption': cap, 'tool': dict(TOOLS)[code],
                    'scene_or_data': (request.form.get('scene') or '').strip()[:120], 'used_in_dm': '', 'used_in_title': '', 'used_where': '',
                    'date_shot': datetime.date.today().isoformat(), 'shot_by': (request.form.get('who') or 'author').strip()[:60], 'status': 'current'}
        try:
            write_register(reg)
        except Exception as ex:
            os.remove(path)
            return jsonify({'status': 'error', 'error': 'The register could not be saved, so the file was not kept: %s' % ex}), 500
        return jsonify({'status': 'ok', 'file': final, 'icn': icn})

    @app.route('/pi/media', methods=['GET', 'POST'])
    def pi_media():
        """GET lists static/pi/media. POST (multipart field 'file') adds one image or video; an existing name is not overwritten."""
        if request.method == 'GET':
            names = []
            if os.path.isdir(media_dir):
                names = sorted(n for n in os.listdir(media_dir) if n.lower().endswith(MEDIA_EXT))
            return jsonify({'files': names, 'info': graphics_info(names)})
        f = request.files.get('file')
        if request.form.get('tool') is not None:
            return upload_icn(f)
        if not f or not f.filename:
            return jsonify({'status': 'error', 'error': 'no file was sent'}), 400
        name = re.sub(r'[^A-Za-z0-9._-]+', '_', os.path.basename(f.filename)).strip('._')
        if not name or not name.lower().endswith(MEDIA_EXT):
            return jsonify({'status': 'error', 'error': 'only ' + ', '.join(MEDIA_EXT) + ' files are accepted'}), 400
        data = f.read(16 * 1024 * 1024 + 1)
        if len(data) > 16 * 1024 * 1024:
            return jsonify({'status': 'error', 'error': 'the file is larger than 16 MB'}), 400
        os.makedirs(media_dir, exist_ok=True)
        base, ext = os.path.splitext(name)
        n, final = 1, name
        while os.path.exists(os.path.join(media_dir, final)):
            n += 1
            final = '%s_%d%s' % (base, n, ext)
        with open(os.path.join(media_dir, final), 'wb') as fh:
            fh.write(data)
        return jsonify({'status': 'ok', 'file': final})

    @app.route('/pi/lesson', methods=['POST'])
    def pi_lesson_save():
        """Save a lesson as static/pi/lessons/<DmCode>.xml. The file must be well-formed PILesson XML with a valid DM code.
        An existing file is first copied to lessons/_backup/<DmCode>_<time>.xml (the last 10 are kept)."""
        xml = (request.get_json(silent=True) or {}).get('xml', '')
        if not isinstance(xml, str) or len(xml) > 2 * 1024 * 1024:
            return jsonify({'status': 'error', 'error': 'no lesson text, or it is larger than 2 MB'}), 400
        try:
            root = ET.fromstring(xml.encode('utf-8'))
        except ET.ParseError as e:
            return jsonify({'status': 'error', 'error': 'not well-formed XML: %s' % e}), 400
        if root.tag != NS + 'PILesson':
            return jsonify({'status': 'error', 'error': 'the root element must be PILesson in the PI namespace'}), 400
        m = root.find(NS + 'Meta')
        dm = (m.findtext(NS + 'DmCode') if m is not None else '') or ''
        dm = dm.strip()
        if not DM_RE.match(dm):
            return jsonify({'status': 'error', 'error': 'Meta/DmCode is missing or not a valid data module code'}), 400
        os.makedirs(lessons_dir, exist_ok=True)
        target = os.path.join(lessons_dir, dm + '.xml')
        backup = None
        if os.path.isfile(target):
            import time, shutil
            os.makedirs(backup_dir, exist_ok=True)
            backup = os.path.join(backup_dir, '%s_%s.xml' % (dm, time.strftime('%Y%m%d_%H%M%S')))
            shutil.copy2(target, backup)
            old = sorted(glob.glob(os.path.join(backup_dir, dm + '_*.xml')))
            for p in old[:-10]:
                try:
                    os.remove(p)
                except OSError:
                    pass
        tmp = target + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            fh.write(xml)
        os.replace(tmp, target)
        return jsonify({'status': 'ok', 'file': dm + '.xml', 'backup': os.path.basename(backup) if backup else None})

    def log_path(dm):
        return os.path.join(logs_dir, dm + '.jsonl') if DM_RE.match(dm or '') else ''

    def read_sessions(dm):
        p = log_path(dm)
        out = []
        if p and os.path.isfile(p):
            for line in open(p, encoding='utf-8'):
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        rec['end'] = _clean_end(rec.get('end'))    # older lines hold the text "None" for an unfinished session
                        out.append(rec)
                    except Exception:
                        pass
        return out

    @app.route('/pi/log', methods=['GET', 'POST'])
    def pi_log():
        if request.method == 'GET':
            if not log_path(request.args.get('lesson')):
                return jsonify({'status': 'error', 'error': 'lesson must be a DM code'}), 400
            return jsonify({'sessions': read_sessions(request.args.get('lesson'))})
        s = request.get_json(silent=True) or {}
        dm, sid = s.get('lesson', ''), str(s.get('id', ''))
        if not log_path(dm) or not sid:
            return jsonify({'status': 'error', 'error': 'session needs a lesson DM code and an id'}), 400
        clean = {'id': sid[:64], 'learner': str(s.get('learner', ''))[:80], 'lesson': dm, 'issue': str(s.get('issue', ''))[:16],
                 'start': str(s.get('start', ''))[:32], 'end': _clean_end(s.get('end')),
                 'path': s.get('path') if s.get('path') in PATH_ORDER else 'none', 'attempts': []}
        for a in (s.get('attempts') or [])[:500]:
            clean['attempts'].append({'frame': str(a.get('frame', ''))[:32], 'kind': 'question' if a.get('kind') == 'question' else 'check',
                                      'response': str(a.get('response', ''))[:32], 'correct': bool(a.get('correct')),
                                      'seconds': float(a.get('seconds') or 0), 'at': str(a.get('at', ''))[:32],
                                      'remedial': a.get('remedial') if a.get('remedial') in PATH_ORDER else None})
        os.makedirs(logs_dir, exist_ok=True)
        keep = [x for x in read_sessions(dm) if x.get('id') != clean['id']]
        keep.append(clean)
        with open(log_path(dm), 'w', encoding='utf-8') as fh:
            for x in keep:
                fh.write(json.dumps(x) + '\n')
        return jsonify({'status': 'ok', 'sessions': len(keep)})

    @app.route('/pi/report')
    def pi_report():
        dm = request.args.get('lesson', '')
        if not log_path(dm):
            return jsonify({'status': 'error', 'error': 'lesson must be a DM code'}), 400
        return jsonify(build_report(dm, read_sessions(dm)))


def _clean_end(v):
    """An unfinished session has no end time. None, '', 'None' and 'null' all mean that."""
    if v is None:
        return None
    t = str(v).strip()
    return None if t.lower() in ('', 'none', 'null') else t[:32]


def _secs(a, b):
    from datetime import datetime
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
    except Exception:
        return None


def build_report(dm, sessions):
    n = len(sessions)
    done = [s for s in sessions if s.get('end')]
    times = [t for t in (_secs(s.get('start'), s.get('end')) for s in done) if t is not None and t >= 0]
    frames = {}
    for s in sessions:
        seen = {}
        for a in s.get('attempts', []):
            f = frames.setdefault(a['frame'], {'frame': a['frame'], 'kind': a['kind'], 'sessions': 0, 'missed': 0, 'attempts': 0, 'seconds': 0.0, 'responses': {}})
            f['attempts'] += 1
            f['seconds'] += a.get('seconds') or 0
            seen[a['frame']] = seen.get(a['frame'], False) or not a['correct']
            if not a['correct'] and a.get('response'):
                f['responses'][a['response']] = f['responses'].get(a['response'], 0) + 1
        for fr, missed in seen.items():
            frames[fr]['sessions'] += 1
            frames[fr]['missed'] += 1 if missed else 0
    rows = []
    for f in frames.values():
        rate = f['missed'] / f['sessions'] if f['sessions'] else 0
        rows.append({'frame': f['frame'], 'kind': f['kind'], 'sessions': f['sessions'], 'missRate': round(rate, 3),
                     'meanSeconds': round(f['seconds'] / f['attempts'], 1) if f['attempts'] else 0,
                     'commonWrong': sorted(f['responses'], key=lambda k: -f['responses'][k])[:3],
                     'flagged': rate > FLAG_RATE and f['sessions'] >= FLAG_MIN})
    rows.sort(key=lambda r: -r['missRate'])
    paths = {}
    for s in sessions:
        p = s.get('path') or 'none'
        e = paths.setdefault(p, {'path': p, 'sessions': 0, 'finished': 0})
        e['sessions'] += 1
        e['finished'] += 1 if s.get('end') else 0
    notes = []
    for r in rows:
        if r['flagged']:
            w = (' Most common wrong answer: %s.' % r['commonWrong'][0]) if r['commonWrong'] else ''
            notes.append('Frame %s is missed in %d%% of sessions.%s Rewrite the instruction or add a frame.' % (r['frame'], round(r['missRate'] * 100), w))
    if n and n < FLAG_MIN:
        notes.append('Only %d session%s so far; a frame is flagged only after %d.' % (n, '' if n == 1 else 's', FLAG_MIN))
    return {'lesson': dm, 'sessions': n, 'finished': len(done),
            'finishedPct': round(100 * len(done) / n) if n else 0,
            'meanSecondsToFinish': round(sum(times) / len(times), 1) if times else None,
            'flaggedFrames': sum(1 for r in rows if r['flagged']),
            'frames': rows, 'paths': sorted(paths.values(), key=lambda p: PATH_ORDER.index(p['path'])), 'analysis': notes,
            'flagRule': 'miss rate above %d%% over at least %d sessions' % (FLAG_RATE * 100, FLAG_MIN)}
