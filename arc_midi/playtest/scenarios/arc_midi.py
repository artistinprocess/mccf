NAME = 'arc_midi'
DESCRIPTION = """Emotional arc -> MIDI controllers: the server answers /ambient/arc/state, the Ambient Workshop has its "Emotional arc -> MIDI" section and the Player can take controller lanes,
and the Dashboard has its "Arc -> MIDI" panel showing what the server holds. READS ONLY (nothing is posted or saved). To see the panel filled, load an arc in the Ambient Workshop first (with its own MIDI file)
and then run this scenario: it reports what the Dashboard shows and checks it agrees with the server."""
DEFAULTS = {
    'dashboard': '',         # path of the dashboard page; empty = try /static/mccf_dashboard.html, then /mccf_dashboard.html
}


def run(t):
    o = t.opts
    with t.step('the server answers /ambient/arc/state'):
        t.goto('/static/mccf_ambient.html')
        t.wait_for(lambda: t.page.evaluate("typeof Workshop === 'object' && Workshop !== null"), timeout=30, label='the Ambient Workshop')
        r = t.page.evaluate("() => fetch('/ambient/arc/state').then(async r => ({ status: r.status, body: await r.json().catch(() => null) }))")
        t.expect('GET /ambient/arc/state answers 200 (if 404, mccf_ambient_api.py is not the patched one)', r['status'] == 200, str(r['status']))
        body = r.get('body') or {}
        t.expect('and says whether an arc is loaded', body.get('ok') is True and isinstance(body.get('loaded'), bool), str(body)[:200])
        held = (body.get('state') or {}) if body.get('loaded') else None
        t.note('server holds an arc', bool(held))
        if held: t.note('arc', {'agent': held['arc'].get('agent'), 'lanes': [(l['curve'], l['cc'], l['on']) for l in held['spec']['lanes']], 'enabled': held['spec']['enabled'], 'updated': body.get('updated')})
    with t.step('the Ambient Workshop has the arc section'):
        has = t.page.evaluate("() => ({ mod: typeof window.MccfArc === 'object' && !!window.MccfArc, fn: typeof Workshop.arcLoad === 'function' && typeof Workshop.arcLane === 'function', "
                              "lanes: (() => { try { return typeof eval('themePlayer').setLanes === 'function'; } catch (e) { return false; } })() })")
        t.expect('mccf_arc.js is loaded', has['mod'], str(has)); t.expect('the Workshop has the arc functions (the page is the patched one)', has['fn'], str(has))
        t.expect('the Player can take controller lanes (mccf_midi.js is the patched one)', has['lanes'], str(has))
        t.page.evaluate("Workshop.render()"); txt = t.page.inner_text('#workshop-panel')
        t.expect('the Workshop panel shows the section (once a MIDI file is loaded; before that it only shows how to start)', 'Emotional arc' in txt or 'Load a MIDI file' in txt, txt[:120])
        t.shot('ambient workshop')
    with t.step('the Dashboard has the Arc panel'):
        paths = [o['dashboard']] if o['dashboard'] else ['/static/mccf_dashboard.html', '/mccf_dashboard.html']
        got = None
        for p in paths:
            resp = t.page.goto(t.url(p) if hasattr(t, 'url') else t.base + p)
            if resp and resp.status == 200: got = p; break
        t.expect('the dashboard page opens (tried %s)' % ', '.join(paths), got is not None, 'none returned 200: pass --opt dashboard=/path')
        if got:
            t.wait_for(lambda: t.page.evaluate("!!document.getElementById('panel-arc')"), timeout=15, label='the Arc panel')
            t.wait(3)
            tag = t.page.inner_text('#arc-tag').strip().lower(); txt = t.page.inner_text('#panel-arc')
            t.expect('the panel is there', 'arc' in txt.lower())
            if held:
                want = 'in use' if held['spec']['enabled'] else 'switched off'
                t.expect('with an arc on the server the panel says "%s" (it says "%s")' % (want, tag), tag == want, tag)
                t.expect('and shows the character %s' % held['arc'].get('agent'), (held['arc'].get('agent') or '') in t.page.inner_text('#arc-kv'))
                n = t.page.evaluate("document.querySelectorAll('#arc-stats tr[data-curve]').length"); t.expect('one row per channel (%d)' % len(held['stats']), n == len(held['stats']), str(n))
                m = t.page.evaluate("document.querySelectorAll('#arc-lanes tr[data-cc]').length"); t.expect('one row per lane (%d)' % len(held['spec']['lanes']), m == len(held['spec']['lanes']), str(m))
            else:
                t.expect('with no arc on the server the panel says so', tag == 'no arc' and 'no arc loaded' in txt.lower(), tag)
            t.expect('the panel fits on screen', t.page.evaluate("(() => { const r = document.getElementById('panel-arc').getBoundingClientRect(); return r.bottom <= innerHeight + 1 && r.width >= innerWidth - 2; })()"))
            t.shot('dashboard arc panel')
