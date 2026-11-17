"""
mccf_effects_registry.py -- DM code registry for saved Effect Assets (assemblies).

Code format:  ISSUER-E-CC-NN-00-00A-040A-D
  e.g.        MCCF-E-20-01-00-00A-040A-D
  ISSUER  model identification code. MCCF for the project's own assemblies,
          otherwise the author's own 3 to 5 letter code (uppercase letters
          and digits). Keeps two authors from ever issuing the same code.
  E       effect assembly (the User's Guide uses A).
  CC      category chosen at save: 10 timing and triggers, 20 camera,
          30 light, 40 audio, 50 movement and paths, 90 other (default).
  NN      serial 01 to 99 per issuer and category, issued in order.
  00-00A-040A-D  fixed, as in the Guide.

Registry file: effects_registry.json beside the effects library. A code is
retired, never reused or renumbered. Pure stdlib; no Flask here.
"""
import json, os, re, threading, time

CATEGORIES = {
    '10': 'timing and triggers', '20': 'camera', '30': 'light',
    '40': 'audio', '50': 'movement and paths', '90': 'other',
}
DEFAULT_CATEGORY = '90'
DEFAULT_ISSUER = 'MCCF'
_TAIL = '00-00A-040A-D'
_ISSUER_RE = re.compile(r'^[A-Z0-9]{3,5}$')
_lock = threading.Lock()


class RegistryError(Exception):
    pass


def _path(effects_root):
    return os.path.join(effects_root, 'effects_registry.json')


def load(effects_root):
    p = _path(effects_root)
    if not os.path.isfile(p):
        return {'entries': []}
    with open(p, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data.setdefault('entries', [])
    return data


def _save(effects_root, data):
    os.makedirs(effects_root, exist_ok=True)
    tmp = _path(effects_root) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, _path(effects_root))


def make_code(issuer, category, serial):
    return '%s-E-%s-%02d-%s' % (issuer, category, serial, _TAIL)


def clean_issuer(issuer):
    issuer = (issuer or DEFAULT_ISSUER).strip().upper()
    if not _ISSUER_RE.match(issuer):
        raise RegistryError('issuer must be 3 to 5 letters or digits')
    return issuer


def clean_category(category):
    category = str(category or DEFAULT_CATEGORY).strip()
    if category not in CATEGORIES:
        raise RegistryError('category must be one of ' + ', '.join(sorted(CATEGORIES)))
    return category


def issue(effects_root, filename, title, category=None, issuer=None):
    """Return the entry for this file. A file already registered (active) keeps
    its code; otherwise the next free serial for issuer+category is issued."""
    issuer = clean_issuer(issuer)
    category = clean_category(category)
    with _lock:
        data = load(effects_root)
        for e in data['entries']:
            if e['file'] == filename and e['status'] == 'active':
                e['title'] = title
                e['updated'] = time.strftime('%Y-%m-%dT%H:%M:%S')
                _save(effects_root, data)
                return dict(e, reused=True)
        used = [e['serial'] for e in data['entries']
                if e['issuer'] == issuer and e['category'] == category]
        serial = (max(used) + 1) if used else 1
        if serial > 99:
            raise RegistryError('category %s is full for issuer %s (99 codes)' % (category, issuer))
        entry = {
            'code': make_code(issuer, category, serial),
            'issuer': issuer, 'category': category, 'serial': serial,
            'file': filename, 'title': title, 'status': 'active',
            'created': time.strftime('%Y-%m-%dT%H:%M:%S'),
        }
        data['entries'].append(entry)
        _save(effects_root, data)
        return dict(entry, reused=False)


def retire(effects_root, code):
    with _lock:
        data = load(effects_root)
        for e in data['entries']:
            if e['code'] == code and e['status'] == 'active':
                e['status'] = 'retired'
                e['retired'] = time.strftime('%Y-%m-%dT%H:%M:%S')
                _save(effects_root, data)
                return e
    raise RegistryError('no active entry with code ' + code)


def stamp(content, entry):
    """Write dmCode and issuer meta tags into the X3D head, replacing old ones."""
    content = re.sub(r'\s*<meta\s+name="(dmCode|issuer)"[^>]*/>', '', content)
    tags = '\n  <meta name="dmCode" content="%s"/>\n  <meta name="issuer" content="%s"/>' % (
        entry['code'], entry['issuer'])
    if '<head>' in content:
        return content.replace('<head>', '<head>' + tags, 1)
    return content


def codes_by_file(effects_root):
    return {e['file']: e['code'] for e in load(effects_root)['entries'] if e['status'] == 'active'}
