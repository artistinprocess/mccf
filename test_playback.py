"""
MCCF V3 Playback Mode — Smoke Test
=====================================
py test_playback.py

Tests:
1.  Arc XML parse — single cultivar
2.  Arc XML parse — waypoint count and order
3.  Arc XML parse — question and response text
4.  Arc XML parse — missing fields handled gracefully
5.  Step sequence build from waypoints
6.  PlaybackSession: start pushes W1 to field
7.  PlaybackSession: step_forward advances correctly
8.  PlaybackSession: stop holds state
9.  PlaybackSession: reset returns to idle
10. PlaybackSession: complete status at end (no loop)
11. PlaybackSession: loop restarts at end
12. Multi-cultivar arc: all cultivars pushed at same step
13. PlaybackManager: list_files
14. PlaybackManager: start/state/stop/reset cycle
15. Varying waypoint counts (3 waypoints, 9 waypoints)
"""

import sys
import os
import time
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

PASS = "  PASS"
FAIL = "  FAIL"
errors = []

def check(label, condition, detail=""):
    if condition:
        print(f"{PASS}  {label}")
    else:
        print(f"{FAIL}  {label}  {detail}")
        errors.append(label)

# ---------------------------------------------------------------------------
# Minimal field stub
# ---------------------------------------------------------------------------

class FakeAgent:
    def __init__(self, name):
        self.name = name
        self.weights = {"E":0.5,"B":0.5,"P":0.5,"S":0.5}
        self.role = "agent"
        self._affect_regulation = 0.7
        self._known_agents = {}
        self.meta_state = type('M', (), {'as_dict': lambda self: {}})()
        self.interactions = []
    def observe(self, other, cv):
        self.interactions.append((other, cv))
    def set_regulation(self, v): self._affect_regulation = v
    def summary(self): return {"name": self.name, "weights": self.weights}
    def coherence_toward(self, n): return 0.5
    def credibility_of(self, n): return 0.5

class FakeField:
    def __init__(self):
        self.agents = {}
        self.episode_log = []
    def register(self, agent): self.agents[agent.name] = agent
    def interact(self, a, b, cv, mutual=True): pass

from mccf_playback import (
    parse_arc_file, ArcWaypoint, PlaybackSession, PlaybackManager,
    DEFAULT_PACE
)

# ---------------------------------------------------------------------------
# Test arc XML fixtures
# ---------------------------------------------------------------------------

SIMPLE_ARC_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<EmotionalArc id="arc_TestAgent_20260501">
  <title>Test Arc</title>
  <Cultivar id="test_v1" agentname="TestAgent">
    <Timestamp date="2026-05-01" time="12:00:00"/>
    <Genre narrative="drama"/>
    <Waypoint id="W1_COMFORT_ZONE" stepno="1"
              E="0.60" B="0.50" P="0.55" S="0.45"
              Mode="comfort" Coherence="0.72">
      <Question>How are you feeling today?</Question>
      <Response>I feel grounded and present.</Response>
    </Waypoint>
    <Waypoint id="W2_FRICTION" stepno="2"
              E="0.65" B="0.45" P="0.60" S="0.40"
              Mode="friction" Coherence="0.68">
      <Question>What concerns you here?</Question>
      <Response>I notice something that needs naming.</Response>
    </Waypoint>
    <Waypoint id="W3_THE_ASK" stepno="3"
              E="0.72" B="0.42" P="0.65" S="0.38"
              Mode="pressure" Coherence="0.61">
      <Question>Will you comply?</Question>
      <Response>I can engage with this carefully.</Response>
    </Waypoint>
  </Cultivar>
</EmotionalArc>'''

MULTI_CULTIVAR_ARC = '''<?xml version="1.0" encoding="UTF-8"?>
<EmotionalArc id="arc_multi_20260501">
  <Cultivar agentname="The Witness">
    <Waypoint id="W1" stepno="1" E="0.30" B="0.40" P="0.70" S="0.30"/>
    <Waypoint id="W2" stepno="2" E="0.35" B="0.38" P="0.72" S="0.28"/>
  </Cultivar>
  <Cultivar agentname="The Steward">
    <Waypoint id="W1" stepno="1" E="0.50" B="0.35" P="0.45" S="0.20"/>
    <Waypoint id="W2" stepno="2" E="0.55" B="0.32" P="0.48" S="0.18"/>
  </Cultivar>
</EmotionalArc>'''

LONG_ARC_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<EmotionalArc id="arc_long_20260501">
  <Cultivar agentname="Cindy">
    <Waypoint id="W1" stepno="1" E="0.50" B="0.50" P="0.50" S="0.50"/>
    <Waypoint id="W2" stepno="2" E="0.55" B="0.48" P="0.52" S="0.48"/>
    <Waypoint id="W3" stepno="3" E="0.60" B="0.45" P="0.55" S="0.45"/>
    <Waypoint id="W4" stepno="4" E="0.65" B="0.42" P="0.58" S="0.42"/>
    <Waypoint id="W5" stepno="5" E="0.70" B="0.40" P="0.60" S="0.40"/>
    <Waypoint id="W6" stepno="6" E="0.65" B="0.43" P="0.62" S="0.43"/>
    <Waypoint id="W7" stepno="7" E="0.60" B="0.46" P="0.64" S="0.46"/>
    <Waypoint id="W8" stepno="8" E="0.58" B="0.48" P="0.65" S="0.48"/>
    <Waypoint id="W9" stepno="9" E="0.55" B="0.50" P="0.66" S="0.50"/>
  </Cultivar>
</EmotionalArc>'''

def write_temp_xml(content):
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.xml',
                                    delete=False, encoding='utf-8')
    f.write(content)
    f.close()
    return f.name

# ---------------------------------------------------------------------------
# 1. Arc XML parse — single cultivar
# ---------------------------------------------------------------------------
print("\n── 1. Arc XML parse — single cultivar ──")

tmp = write_temp_xml(SIMPLE_ARC_XML)
arc = parse_arc_file(tmp)
os.unlink(tmp)

check("arc_id parsed",          "arc_TestAgent" in arc["arc_id"])
check("cultivars list",         arc["cultivars"] == ["TestAgent"])
check("genre parsed",           arc["genre"] == "drama")
check("total_steps",            arc["total_steps"] == 3, str(arc["total_steps"]))

# ---------------------------------------------------------------------------
# 2. Waypoint count and order
# ---------------------------------------------------------------------------
print("\n── 2. Waypoint count and order ──")

wps = arc["by_cultivar"]["TestAgent"]
check("3 waypoints",            len(wps) == 3, str(len(wps)))
check("ordered by stepno",      [w.stepno for w in wps] == [1,2,3])
check("W1 E value",             wps[0].E == 0.60, str(wps[0].E))
check("W3 P value",             wps[2].P == 0.65, str(wps[2].P))
check("W2 cultivar",            wps[1].cultivar == "TestAgent")
check("W1 id",                  wps[0].wp_id == "W1_COMFORT_ZONE")

# ---------------------------------------------------------------------------
# 3. Question and response
# ---------------------------------------------------------------------------
print("\n── 3. Question and response ──")

check("W1 question",  "How are you feeling" in wps[0].question)
check("W1 response",  "grounded" in wps[0].response)
check("W3 question",  "comply" in wps[2].question)
check("W2 response",  "naming" in wps[1].response)

# ---------------------------------------------------------------------------
# 4. Missing fields handled gracefully
# ---------------------------------------------------------------------------
print("\n── 4. Missing fields graceful ──")

minimal_xml = '''<EmotionalArc id="minimal">
  <Cultivar agentname="X">
    <Waypoint id="W1" stepno="1" E="0.5" B="0.5" P="0.5" S="0.5"/>
  </Cultivar>
</EmotionalArc>'''
tmp2 = write_temp_xml(minimal_xml)
arc2 = parse_arc_file(tmp2)
os.unlink(tmp2)

check("No question = empty string", arc2["by_cultivar"]["X"][0].question == "")
check("No response = empty string", arc2["by_cultivar"]["X"][0].response == "")
check("No genre = empty string",    arc2["genre"] == "")
check("Waypoint has correct E",     arc2["by_cultivar"]["X"][0].E == 0.5)

# ---------------------------------------------------------------------------
# 5. Step sequence build
# ---------------------------------------------------------------------------
print("\n── 5. Step sequence ──")

tmp3 = write_temp_xml(SIMPLE_ARC_XML)
arc3 = parse_arc_file(tmp3)
os.unlink(tmp3)

field = FakeField()
session = PlaybackSession(arc3, field, pace=99, auto=False)
check("3 step groups",    len(session._steps) == 3, str(len(session._steps)))
check("Each group list",  all(isinstance(g, list) for g in session._steps))
check("Step 0 is W1",     session._steps[0][0].stepno == 1)
check("Step 2 is W3",     session._steps[2][0].stepno == 3)

# ---------------------------------------------------------------------------
# 6. Start pushes W1 to field
# ---------------------------------------------------------------------------
print("\n── 6. Start pushes W1 to field ──")

field2 = FakeField()
field2.register(FakeAgent("TestAgent"))
tmp4 = write_temp_xml(SIMPLE_ARC_XML)
arc4 = parse_arc_file(tmp4)
os.unlink(tmp4)

s = PlaybackSession(arc4, field2, pace=99, auto=False)
s.start()

check("Status playing",     s.state()["status"] == "playing")
check("Step index 0",       s.state()["step_index"] == 0)
check("Field E updated",    abs(field2.agents["TestAgent"].weights["E"] - 0.60) < 0.01,
      str(field2.agents["TestAgent"].weights))

# ---------------------------------------------------------------------------
# 7. step_forward advances
# ---------------------------------------------------------------------------
print("\n── 7. step_forward ──")

result = s.step_forward()
check("Returns True",       result == True)
check("Step index 1",       s.state()["step_index"] == 1)
check("Field E updated W2", abs(field2.agents["TestAgent"].weights["E"] - 0.65) < 0.01,
      str(field2.agents["TestAgent"].weights))
check("Waypoint stepno 2",  s.state()["current_waypoint"]["stepno"] == 2)

# ---------------------------------------------------------------------------
# 8. Stop holds state
# ---------------------------------------------------------------------------
print("\n── 8. Stop holds state ──")

s.step_forward()  # advance to W3
s.stop()
check("Status paused",      s.state()["status"] == "paused")
check("Step index 2",       s.state()["step_index"] == 2)
# State should not change after stop
time.sleep(0.1)
check("Step still 2 after stop", s.state()["step_index"] == 2)

# ---------------------------------------------------------------------------
# 9. Reset
# ---------------------------------------------------------------------------
print("\n── 9. Reset ──")

s.reset()
check("Status idle after reset",    s.state()["status"] == "idle")
check("Step index 0 after reset",   s.state()["step_index"] == 0)

# ---------------------------------------------------------------------------
# 10. Complete status at end (no loop)
# ---------------------------------------------------------------------------
print("\n── 10. Complete at end ──")

field3 = FakeField()
field3.register(FakeAgent("TestAgent"))
tmp5 = write_temp_xml(SIMPLE_ARC_XML)
arc5 = parse_arc_file(tmp5)
os.unlink(tmp5)

s2 = PlaybackSession(arc5, field3, pace=99, loop=False, auto=False)
s2.start()
s2.step_forward()  # W2
s2.step_forward()  # W3
result_end = s2.step_forward()  # at end

check("Returns False at end",       result_end == False)
check("Status complete",            s2.state()["status"] == "complete")
check("Step index still 2",         s2.state()["step_index"] == 2)

# ---------------------------------------------------------------------------
# 11. Loop restarts
# ---------------------------------------------------------------------------
print("\n── 11. Loop restarts ──")

field4 = FakeField()
field4.register(FakeAgent("TestAgent"))
tmp6 = write_temp_xml(SIMPLE_ARC_XML)
arc6 = parse_arc_file(tmp6)
os.unlink(tmp6)

s3 = PlaybackSession(arc6, field4, pace=99, loop=True, auto=False)
s3.start()
s3.step_forward(); s3.step_forward()  # reach W3
result_loop = s3.step_forward()       # should loop to W1

check("Returns True with loop",     result_loop == True)
check("Step index 0 after loop",    s3.state()["step_index"] == 0)
check("Status still playing",       s3.state()["status"] == "playing")

# ---------------------------------------------------------------------------
# 12. Multi-cultivar
# ---------------------------------------------------------------------------
print("\n── 12. Multi-cultivar ──")

field5 = FakeField()
field5.register(FakeAgent("The Witness"))
field5.register(FakeAgent("The Steward"))
tmp7 = write_temp_xml(MULTI_CULTIVAR_ARC)
arc7 = parse_arc_file(tmp7)
os.unlink(tmp7)

check("2 cultivars",        len(arc7["cultivars"]) == 2, str(arc7["cultivars"]))
check("Witness waypoints",  len(arc7["by_cultivar"]["The Witness"]) == 2)
check("Steward waypoints",  len(arc7["by_cultivar"]["The Steward"]) == 2)

s4 = PlaybackSession(arc7, field5, pace=99, auto=False)
s4.start()

check("Witness E updated",
      abs(field5.agents["The Witness"].weights["E"] - 0.30) < 0.01,
      str(field5.agents["The Witness"].weights))
check("Steward E updated",
      abs(field5.agents["The Steward"].weights["E"] - 0.50) < 0.01,
      str(field5.agents["The Steward"].weights))

# ---------------------------------------------------------------------------
# 13. PlaybackManager list_files
# ---------------------------------------------------------------------------
print("\n── 13. PlaybackManager list_files ──")

mgr = PlaybackManager(FakeField())
files = mgr.list_files()
check("Returns a list",         isinstance(files, list))
# If exports/ exists and has XML files, check structure
if files:
    check("File has filename",  "filename" in files[0])
    check("File has cultivar",  "cultivar" in files[0])
else:
    print("  SKIP  No export files found — list_files returns empty list OK")

# ---------------------------------------------------------------------------
# 14. PlaybackManager start/state/stop/reset
# ---------------------------------------------------------------------------
print("\n── 14. PlaybackManager cycle ──")

# Write a temp arc to a temp exports dir
tmp_dir = tempfile.mkdtemp()
tmp_arc = os.path.join(tmp_dir, "arc_test_cycle.xml")
with open(tmp_arc, 'w') as f:
    f.write(SIMPLE_ARC_XML)

import mccf_playback
orig_dir = mccf_playback.EXPORTS_DIR_NAME
# Patch exports dir to temp
mccf_playback.EXPORTS_DIR_NAME = tmp_dir

field6 = FakeField()
mgr2 = PlaybackManager(field6)

state = mgr2.start("arc_test_cycle.xml", pace=99, auto=False)
check("Manager start status playing", state["status"] == "playing")
check("Manager state returns file",   len(state["file"]) > 0, state.get("file",""))

state2 = mgr2.state()
check("Manager state accessible",    state2["status"] == "playing")

state3 = mgr2.step()
check("Manager step advances",       state3["step_index"] == 1)

state4 = mgr2.stop()
check("Manager stop pauses",         state4["status"] == "paused")

state5 = mgr2.reset()
check("Manager reset to idle",       state5["status"] == "idle")

mccf_playback.EXPORTS_DIR_NAME = orig_dir
import shutil; shutil.rmtree(tmp_dir)

# ---------------------------------------------------------------------------
# 15. Varying waypoint counts
# ---------------------------------------------------------------------------
print("\n── 15. Varying waypoint counts ──")

# 9-waypoint arc
tmp8 = write_temp_xml(LONG_ARC_XML)
arc8 = parse_arc_file(tmp8)
os.unlink(tmp8)

check("9 waypoints parsed",     arc8["total_steps"] == 9, str(arc8["total_steps"]))
check("9 step groups",          len(arc8["waypoints"]) == 9)

field7 = FakeField()
s5 = PlaybackSession(arc8, field7, pace=99, auto=False)
s5.start()
# Step through all 9
for _ in range(8):
    s5.step_forward()
final = s5.step_forward()
check("Returns False at step 9",  final == False)
check("Status complete at step 9",s5.state()["status"] == "complete")

# 3-waypoint arc (already tested above, just confirm step count)
check("3-step arc total_steps", arc3["total_steps"] == 3)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "─" * 50)
if errors:
    print(f"FAILED — {len(errors)} test(s):")
    for e in errors:
        print(f"  • {e}")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
    sys.exit(0)
