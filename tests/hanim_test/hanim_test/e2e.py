"""2x2: {original,patched} client payload x {original,patched} server. Scenario = author loads Anna,
ticks Loop on Bow (the click that started the trouble), presses Export."""
import json, sys, os
from harness import *
import diff_x3d
if len(sys.argv) != 3: sys.exit('usage: python3 e2e.py <ORIGINAL mccf_hanim_api.py> <PATCHED mccf_hanim_api.py>   (needs payload_original.json / payload_patched.json - see run_all.sh)')
ORIG, PATCH = sys.argv[1], sys.argv[2]
def run(client_payload, server):
    sbx = Sandbox(server)
    body = json.load(open(client_payload))
    body['cultivar'] = 'Anna'          # set by the character shelf in the real UI (not driven in jsdom)
    assert body.get('hanim_src'), body.get('hanim_src')
    r = sbx.client.post('/hanim/export', json=body)
    st = r.status_code; d = r.get_json()
    a = sbx.audit()
    r_, ad, ch, A, B = diff_x3d.diff(sbx.orig, sbx.x3d)
    cl = {c['name']: c['timerDEF'] for c in sbx.cultivar().behavior_clips}
    lost = [k[1] for k in r_ if k[0] in ('TimeSensor', 'EXPORT')]
    return dict(http=st, routed_timers=a['routed_clip_timers'], dangling=a['dangling'], removed=len(r_), added=len(ad),
                attr_changed=[k[1] for k in ch], timers_lost=lost,
                bad_cultivar_refs=[f'{n}->{t}' for n, t in cl.items() if t not in dict(ANNA_CLIPS).values() and t != 'BowTimer'],
                cultivar_changed={n: t for n, t in cl.items() if dict(ANNA_CLIPS).get(n) != t})
print(f"{'client':9s} {'server':9s} | result")
for cn, cp in (('original', os.path.join(HERE,'payload_original.json')), ('patched', os.path.join(HERE,'payload_patched.json'))):
    for sn, sp in (('original', ORIG), ('patched', PATCH)):
        r = run(cp, sp)
        healthy = r['http'] == 200 and not r['dangling'] and not r['timers_lost'] and not r['bad_cultivar_refs'] and not r['cultivar_changed'] and r['routed_timers'] == 14
        print(f"{cn:9s} {sn:9s} | {'HEALTHY' if healthy else 'DAMAGED'}  http={r['http']} routed_timers={r['routed_timers']}/14 dangling={r['dangling']} lost={r['timers_lost']} attr_changed={r['attr_changed']}")
        if r['bad_cultivar_refs'] or r['cultivar_changed']: print(f"{'':20s}   cultivar: bad_refs={r['bad_cultivar_refs']} changed={r['cultivar_changed']}")
