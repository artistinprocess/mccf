"""
Standalone verification of the dialogue-parsing logic destined for
load_scene_xml() in mccf_api.py. This mirrors — verbatim, not approximately —
the code block that gets patched in. Run against realistic scene XML
(matching mccf_scene_composer.html's real exportSceneXML output, same
fixture used in the JS test suite) before it touches the real server file,
since the full Flask app can't be run in this sandbox (mccf_core.py,
flask_cors, etc. aren't available here).
"""
import xml.etree.ElementTree as ET
import re
import sys

LEGACY_SCENE_XML = """<Scene id="garden_001" width="40" depth="40">
<EmotionalArc cultivar="Cindy" actor="1" voice="female_1"><StartPosition x="10" y="0" z="12"/></EmotionalArc>
<Waypoints>
  <Waypoint name="Pool_Approach" label="Approach the pool" zone="Pool" pos_x="10.00" pos_y="0.00" pos_z="12.00" dwell="2" pace="1.4">
    <Question speaker="Cindy">How does the water feel today?</Question>
    <Response speaker="Cindy">Cool. Cooler than I expected.</Response>
  </Waypoint>
  <Waypoint name="Empty_WP" label="" zone="" pos_x="5.00" pos_y="0.00" pos_z="5.00" dwell="2" pace="1.4"/>
</Waypoints>
<Paths>
  <Path name="Path_Cindy_1" agent="Cindy"><PathWaypoint ref="Pool_Approach"/></Path>
</Paths>
</Scene>"""

NEW_SCHEMA_SCENE_XML = """<Scene id="garden_002" width="40" depth="40">
<Dialogue>
  <Line id="line_cindy_001" actor="Cindy" type="Question" mode="improv" blocking="false" trigger="scene-start">How does the water feel today?</Line>
  <Line id="line_jack_002" actor="Jack" type="Statement" mode="static" blocking="false" trigger="declared:58">Did you feel that?</Line>
</Dialogue>
</Scene>"""


def parse_scene_dialogue(raw_xml):
    """
    Verbatim copy of the logic to be patched into load_scene_xml(). Kept as
    its own function here so it can be exercised without the rest of the
    Flask endpoint (auth, file I/O, jsonify) around it.

    Returns (waypoints_qa_lines_by_name, dialogue_lines) — the first is the
    existing qa_lines-per-waypoint shape load_scene_xml already builds; the
    second is the new unified dialogueLines list this patch adds.
    """
    clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', raw_xml)
    clean = re.sub(r'<(\w+):(\w+)', r'<\2', clean)
    clean = re.sub(r'</(\w+):(\w+)', r'</\2', clean)
    root = ET.fromstring(clean)

    # ── existing waypoint qa_lines parsing (unchanged from today) ────────
    waypoints_qa = {}
    wp_container = root.find('Waypoints')
    for wp_el in (wp_container.findall('Waypoint') if wp_container is not None else []):
        wp_name = wp_el.get('name', '').strip()
        qa_lines = []
        for child in wp_el:
            if child.tag in ('Question', 'Response', 'Statement'):
                txt = (child.text or '').strip()
                if txt:
                    qa_lines.append({'type': child.tag, 'speaker': child.get('speaker', ''), 'text': txt})
        waypoints_qa[wp_name] = qa_lines

    # ── NEW: dialogue — real <Dialogue> lines + legacy migration ─────────
    # See docs/DIALOGUE_SCHEMA.md. trigger is returned as its raw stored
    # string (e.g. "declared:58"), not parsed into an object — parsing lives
    # client-side in dialogue-xml.js's parseTrigger(), so there's exactly
    # one implementation of that logic rather than two that could drift.
    dialogue_lines = []

    dialogue_el = root.find('Dialogue')
    if dialogue_el is not None:
        for line_el in dialogue_el.findall('Line'):
            line_id = line_el.get('id', '').strip()
            if not line_id:
                continue
            dialogue_lines.append({
                'id':       line_id,
                'actor':    line_el.get('actor', ''),
                'type':     line_el.get('type', 'Statement'),
                'mode':     line_el.get('mode', 'improv'),
                'blocking': line_el.get('blocking', 'false').lower() == 'true',
                'trigger':  line_el.get('trigger', '').strip(),
                'text':     (line_el.text or '').strip(),
            })

    for wp_name, qa_lines in waypoints_qa.items():
        for idx, qa in enumerate(qa_lines):
            dialogue_lines.append({
                'id':       f'{wp_name}_{idx}',
                'actor':    qa['speaker'],
                'type':     qa['type'],
                'mode':     'improv',
                'blocking': False,
                'trigger':  f'legacy-waypoint:{wp_name}',
                'text':     qa['text'],
            })

    return waypoints_qa, dialogue_lines


# ── verification ────────────────────────────────────────────────────────
def check(label, cond):
    print(('  ok - ' if cond else '  FAIL - ') + label)
    return cond


ok_count = 0
total = 0

def run(label, cond):
    global ok_count, total
    total += 1
    if check(label, cond):
        ok_count += 1


print('legacy scene (no <Dialogue> element at all):')
wp_qa, dlines = parse_scene_dialogue(LEGACY_SCENE_XML)
run('waypoints_qa still has the existing per-waypoint shape (unchanged behavior)',
    wp_qa['Pool_Approach'][0] == {'type': 'Question', 'speaker': 'Cindy', 'text': 'How does the water feel today?'})
run('exactly 2 dialogue lines synthesized from the one populated waypoint', len(dlines) == 2)
run('synthesized line carries legacy-waypoint trigger', dlines[0]['trigger'] == 'legacy-waypoint:Pool_Approach')
run('synthesized line defaults mode=improv, blocking=False',
    dlines[0]['mode'] == 'improv' and dlines[0]['blocking'] is False)
run('empty waypoint contributes nothing', not any('Empty_WP' in d['trigger'] for d in dlines))
run('ids are unique and stable (waypointname_index)', {d['id'] for d in dlines} == {'Pool_Approach_0', 'Pool_Approach_1'})

print('\nnew-schema scene (real <Dialogue> block present):')
wp_qa2, dlines2 = parse_scene_dialogue(NEW_SCHEMA_SCENE_XML)
run('no waypoints in this scene -> waypoints_qa is empty', wp_qa2 == {})
run('exactly 2 real dialogue lines parsed', len(dlines2) == 2)
run('scene-start trigger passed through as raw string', dlines2[0]['trigger'] == 'scene-start')
run('declared trigger passed through as raw string', dlines2[1]['trigger'] == 'declared:58')
run('blocking="false" parses to Python False', dlines2[0]['blocking'] is False)
run('mode/type/actor/text all captured', dlines2[1] == {
    'id': 'line_jack_002', 'actor': 'Jack', 'type': 'Statement', 'mode': 'static',
    'blocking': False, 'trigger': 'declared:58', 'text': 'Did you feel that?',
})

print(f'\n{ok_count}/{total} checks passed')
sys.exit(0 if ok_count == total else 1)
