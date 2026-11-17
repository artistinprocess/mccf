"""
MCCF zone dynamics (DRAFT, 2026-11-11): zones and characters influence each other.

  zones -> characters   A character inside a zone is pulled toward the zone's live state (the room's ambience).
                         pull = pull_weight * coherence * (1 - distance/radius) * (zone_state - character_cv)
                         coherence ramps up while the character is inside and decays slowly outside (the V3 attractor numbers),
                         so a room takes hold gradually. The character's regulation still bounds how far it can move.
  characters -> zones   Characters inside a zone, or linked to it, move the zone's live state toward their own, weighted by
                         closeness and by loudness (the character's E channel). A loud person in a bar shifts the room more
                         than a quiet one. Left alone, the zone relaxes back to its authored baseline.

The authored <Weights> of a zone are its baseline; the live state starts there and returns there. Nothing here is random.
This module has no Flask and no engine imports; mccf_api.py feeds it and applies the result through the normal coupler tick.
"""
import math, re
import xml.etree.ElementTree as ET

CH = ('E', 'B', 'P', 'S')
PULL_WEIGHT = 0.15          # zone -> character, per tick (V3 attractor default)
RESPONSIVENESS = 0.08       # character -> zone, per tick
RESTORE = 0.03              # zone relaxes toward baseline, per tick
DEFAULT_LINK_STRENGTH = 0.5   # link strength at which the pull is exactly PULL_WEIGHT; stronger links pull proportionally more
COHERENCE_STEP = 0.04       # while inside (V3)
COHERENCE_MAX = 0.95
COHERENCE_DECAY = 0.99      # per tick while outside (V3)
LOUDNESS_FLOOR = 0.1        # a character with E near 0 still counts a little


def _clean(text):
    t = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', text)
    t = re.sub(r'<(\w+):(\w+)', r'<\2', t)
    return re.sub(r'</(\w+):(\w+)', r'</\2', t)


def _f(el, key, default):
    try:
        return float(el.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _val(zel, tag, default):
    e = zel.find(tag)
    return _f(e, 'value', default) if e is not None else default


def parse_zones(scene_xml_text):
    """Zone dicts from <Zones><Zone>. 'baseline' is the authored <Weights>."""
    try:
        root = ET.fromstring(_clean(scene_xml_text))
    except ET.ParseError:
        return []
    out = []
    for z in root.iter('Zone'):
        zid = (z.get('id') or '').strip()
        if not zid:
            continue
        w = z.find('Weights')
        base = {c: max(0.0, min(1.0, _f(w, c, 0.25))) if w is not None else 0.25 for c in CH}
        p = z.find('Position')
        loc = [_f(p, 'x', 0), 0.0, _f(p, 'z', 0)] if p is not None else [0.0, 0.0, 0.0]
        out.append({'id': zid, 'name': z.get('name', zid), 'zone_type': z.get('zone_type', ''),
                    'baseline': base, 'location': loc, 'radius': max(0.01, _val(z, 'Radius', 4.0)),
                    'pull_weight': _val(z, 'PullWeight', PULL_WEIGHT),
                    'responsiveness': _val(z, 'Responsiveness', RESPONSIVENESS),
                    'restore': _val(z, 'Restore', RESTORE)})
    return out


def parse_start_positions(scene_xml_text):
    """{character: [x,0,z]} from AgentPlacement / EmotionalArc StartPosition (the fallback when no live position is reported)."""
    try:
        root = ET.fromstring(_clean(scene_xml_text))
    except ET.ParseError:
        return {}
    pos = {}
    for el in list(root.findall('AgentPlacement')) + list(root.findall('EmotionalArc')):
        n = (el.get('cultivar') or '').strip(); sp = el.find('StartPosition')
        if n and sp is not None:
            pos[n] = [_f(sp, 'x', 0), 0.0, _f(sp, 'z', 0)]
    return pos


def normalise_links(links, agent_names, zone_ids):
    """The Composer writes a zone in a link by its bare id; the engine reads 'zone:<id>'.
    A name that is both a character and a zone id stays a character."""
    agents, zones = set(agent_names), set(zone_ids)
    def fix(n):
        if n.startswith('zone:') or n in agents:
            return n
        return 'zone:' + n if n in zones else n
    return [dict(l, **{'from': fix(l['from']), 'to': fix(l['to'])}) for l in links]


def _dist(a, b):
    return math.hypot(float(a[0]) - float(b[0]), float(a[2]) - float(b[2]))


class ZoneField:
    def __init__(self, zones):
        self.zones = {z['id']: z for z in zones}
        self.sig = repr([(z['id'], sorted(z['baseline'].items()), z['location'], z['radius'], z['pull_weight'], z['responsiveness'], z['restore']) for z in zones])
        self.state = {z['id']: dict(z['baseline']) for z in zones}
        self.coherence = {}          # (zone id, character) -> 0..COHERENCE_MAX
        self.last = {}               # last report

    @property
    def ids(self):
        return list(self.zones)

    def zone_dicts(self):
        """Zones in the shape field_tick reads: 'weights' is the LIVE state, so a zone link carries the room as it is now."""
        return [{'id': i, 'zone_type': z['zone_type'], 'weights': dict(self.state[i]), 'location': z['location'], 'radius': z['radius']}
                for i, z in self.zones.items()]

    def _spatial(self, z, pos):
        if pos is None:
            return 0.0
        return max(0.0, 1.0 - _dist(pos, z['location']) / z['radius'])

    def pulls(self, cvs, positions, links=None):
        """Zone -> character. Updates coherence, returns {character: {E,B,P,S}} (summed over zones). Uses the state as it is NOW.
        The strength of the authored link from the zone to the character scales the pull (DEFAULT_LINK_STRENGTH when there is no such link),
        so one authored relationship governs the avatar-zone influence."""
        ls = {}
        for l in (links or []):
            f, t = str(l.get('from', '')), str(l.get('to', ''))
            if f.startswith('zone:'):
                try: ls[(f[5:], t)] = max(ls.get((f[5:], t), 0.0), float(l.get('strength', DEFAULT_LINK_STRENGTH)))
                except (TypeError, ValueError): pass
        out = {n: {c: 0.0 for c in CH} for n in cvs}
        for zid, z in self.zones.items():
            for n, cv in cvs.items():
                key = (zid, n); pos = positions.get(n); sp = self._spatial(z, pos)
                cur = self.coherence.get(key, 0.0)
                self.coherence[key] = min(COHERENCE_MAX, cur + COHERENCE_STEP) if sp > 0 else cur * COHERENCE_DECAY
                if sp <= 0:
                    continue
                k = z['pull_weight'] * (ls.get(key, DEFAULT_LINK_STRENGTH) / DEFAULT_LINK_STRENGTH) * self.coherence[key] * sp
                for c in CH:
                    out[n][c] += k * (self.state[zid][c] - cv[c])
        return {n: {c: round(v, 4) for c, v in d.items()} for n, d in out.items()}

    def update(self, cvs, positions, links):
        """Character -> zone. Moves each zone's state toward its weighted occupants and linked characters, then relaxes toward baseline."""
        report = {}
        for zid, z in self.zones.items():
            w = {}
            for n, cv in cvs.items():
                sp = self._spatial(z, positions.get(n))
                if sp > 0:
                    w[n] = w.get(n, 0.0) + sp * max(LOUDNESS_FLOOR, cv['E'])
            for l in links:                                   # an authored link from a character to this zone counts wherever the character is
                if l['to'] == 'zone:' + zid and l['from'] in cvs:
                    w[l['from']] = w.get(l['from'], 0.0) + float(l.get('strength', 1.0)) * max(LOUDNESS_FLOOR, cvs[l['from']]['E'])
            total = sum(w.values()); st = self.state[zid]
            if total > 0:
                inf = z['responsiveness'] * min(1.0, total)
                for c in CH:
                    target = sum(w[n] * cvs[n][c] for n in w) / total
                    st[c] += inf * (target - st[c])
            for c in CH:
                st[c] += z['restore'] * (z['baseline'][c] - st[c])
                st[c] = round(max(0.0, min(1.0, st[c])), 4)
            report[zid] = {'name': z['name'], 'zone_type': z.get('zone_type', ''), 'baseline': dict(z['baseline']), 'state': dict(st),
                           'influence': {n: round(v, 4) for n, v in sorted(w.items())},
                           'inside': sorted(n for n in cvs if self._spatial(z, positions.get(n)) > 0)}
        self.last = report
        return report

    def report(self):
        return self.last or {zid: {'name': z['name'], 'zone_type': z.get('zone_type', ''), 'baseline': dict(z['baseline']), 'state': dict(self.state[zid]), 'influence': {}, 'inside': []}
                             for zid, z in self.zones.items()}


_fields = {}        # scene key -> ZoneField
_positions = {}     # scene key -> {character: [x,y,z]} last reported


def get_field(key, zones, reset=False):
    f = _fields.get(key)
    new = ZoneField(zones)
    if reset or f is None or f.sig != new.sig:
        _fields[key] = f = new
    return f


def merge_positions(key, reported, start):
    cur = _positions.setdefault(key, {})
    for n, p in (reported or {}).items():
        try:
            cur[n] = [float(p[0]), float(p[1]) if len(p) > 2 else 0.0, float(p[-1])]
        except (TypeError, ValueError, IndexError):
            pass
    out = dict(start or {}); out.update(cur)
    return out
