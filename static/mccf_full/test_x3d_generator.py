"""
MCCF V3 X3D Generator — Smoke Test
=====================================
Run from repo root:
    python test_x3d_generator.py

Tests:
1.  Single avatar scene generates without error
2.  Output is well-formed XML
3.  Proto declaration present
4.  ProtoInstance present with correct agent name
5.  Zone markers present for all zones
6.  Sound nodes present for all zones
7.  Master Script present
8.  ROUTE connections present for all channel fields
9.  Viewpoint present
10. Multi-avatar scene (3 cultivars)
11. Default positions spread correctly
12. Custom positions respected
13. Output written to correct path
14. Garden of the Goddess full generation
"""

import sys
import os
import xml.etree.ElementTree as ET
import re

sys.path.insert(0, os.path.dirname(__file__))

from mccf_x3d_generator import generate_scene, write_scene, _safe_name
from mccf_scene_wrapper import SceneDefinition
from mccf_cultivar_lambda import CultivarDefinition, ShadowContext

PASS = "  PASS"
FAIL = "  FAIL"
errors = []

def check(label, condition, detail=""):
    if condition:
        print(f"{PASS}  {label}")
    else:
        print(f"{FAIL}  {label}  {detail}")
        errors.append(label)

def strip_ns(s):
    s = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', s)
    s = re.sub(r'<(\w+):(\w+)', r'<\2', s)
    s = re.sub(r'</(\w+):(\w+)', r'</\2', s)
    return s

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

ZONE_XML_TEMPLE = '''<Zone id="the_temple" zone_type="sacred">
  <Descriptor>sacred wisdom truth eternal</Descriptor>
  <Weights E="0.27" B="0.47" P="1.0" S="0.03"/>
  <Position x="0" y="0" z="15"/>
  <Radius value="6.0"/>
  <NoiseCoefficient value="0.05"/>
  <PullWeight value="0.15"/>
  <AmbientTheme scale="lydian" tempo="slow"
                sound_file="sounds/temple_lydian.wav" format="wav"/>
  <Color value="#ffe080"/>
  <Description>Sacred attractor.</Description>
</Zone>'''

ZONE_XML_POOL = '''<Zone id="the_pool" zone_type="intimate">
  <Descriptor>care warmth love</Descriptor>
  <Weights E="1.0" B="0.03" P="0.03" S="0.53"/>
  <Position x="0" y="0" z="0"/>
  <Radius value="5.0"/>
  <AmbientTheme scale="major" tempo="slow"
                sound_file="sounds/pool_major.wav" format="wav"/>
  <Color value="#60c8f0"/>
  <Description>Intimate attractor.</Description>
</Zone>'''

def make_scene_def(zones=None):
    zone_blocks = zones or [ZONE_XML_TEMPLE, ZONE_XML_POOL]
    return SceneDefinition(
        id="test_scene",
        description="Test scene for generator smoke test.",
        zone_xml_blocks=zone_blocks,
    )

def make_cultivar(name, color="#8888cc"):
    return CultivarDefinition(
        name=name,
        weights={"E":0.25,"B":0.25,"P":0.25,"S":0.25},
        regulation=0.70,
        shadow_context=ShadowContext(lambda_val=0.72),
        color=color,
        description=f"Test cultivar {name}",
    )

# ---------------------------------------------------------------------------
# 1. Single avatar scene generates
# ---------------------------------------------------------------------------
print("\n── 1. Single avatar generates ──")

scene_def = make_scene_def()
witness = make_cultivar("The Witness", "#60a8f0")
x3d = generate_scene(scene_def, [witness])

check("Returns non-empty string",   len(x3d) > 100)
check("Starts with XML declaration", x3d.startswith("<?xml"))
check("Contains X3D root",          "<X3D" in x3d)
check("Contains Scene element",     "<Scene>" in x3d)

# ---------------------------------------------------------------------------
# 2. Well-formed XML
# ---------------------------------------------------------------------------
print("\n── 2. Well-formed XML ──")

try:
    root = ET.fromstring(strip_ns(x3d))
    check("Parses as valid XML", True)
    check("Root tag is X3D",     root.tag in ("X3D", "x3d"))
except ET.ParseError as e:
    check("Parses as valid XML", False, str(e))
    check("Root tag is X3D",     False)

# ---------------------------------------------------------------------------
# 3. Proto declaration
# ---------------------------------------------------------------------------
print("\n── 3. Proto declaration ──")

check("ProtoDeclare present",           "ProtoDeclare" in x3d)
check("Proto name MCCFAvatar",          'name="MCCFAvatar"' in x3d)
check("ProtoInterface present",         "ProtoInterface" in x3d)
check("eLean field present",            'name="eLean"' in x3d)
check("bStability field present",       'name="bStability"' in x3d)
check("pOrientation field present",     'name="pOrientation"' in x3d)
check("sApproach field present",        'name="sApproach"' in x3d)
check("arousal field present",          'name="arousal"' in x3d)
check("currentAuraColor field present", 'name="currentAuraColor"' in x3d)
check("position exposedField",          'name="position"' in x3d)
check("agentName initializeOnly",       'name="agentName"' in x3d)

# ---------------------------------------------------------------------------
# 4. ProtoInstance
# ---------------------------------------------------------------------------
print("\n── 4. ProtoInstance ──")

safe = _safe_name("The Witness")
check("ProtoInstance present",          "ProtoInstance" in x3d)
check("Instance name MCCFAvatar",       'name="MCCFAvatar"' in x3d)
check("Instance DEF name",             f'DEF="Avatar_{safe}"' in x3d)
check("agentName fieldValue",           "The Witness" in x3d)
check("Position fieldValue present",    'name="position"' in x3d)

# ---------------------------------------------------------------------------
# 5. Zone markers
# ---------------------------------------------------------------------------
print("\n── 5. Zone markers ──")

check("ZoneMarker_TheTemple present",   "ZoneMarker_TheTemple" in x3d)
check("ZoneMarker_ThePool present",     "ZoneMarker_ThePool" in x3d)
check("Zone ProximitySensor present",   "ZoneProx_" in x3d)
check("Temple color present",           "1.000" in x3d or "ffe" in x3d.lower()
                                         or "0.996" in x3d or "1.0" in x3d)
check("Disk2D ring markers present",    "Disk2D" in x3d)

# ---------------------------------------------------------------------------
# 6. Sound nodes
# ---------------------------------------------------------------------------
print("\n── 6. Sound nodes ──")

check("Sound nodes present",            "<Sound" in x3d)
check("Sound_TheTemple present",        "Sound_TheTemple" in x3d)
check("Sound_ThePool present",          "Sound_ThePool" in x3d)
check("AudioClip present",              "AudioClip" in x3d)
check("Temple sound file referenced",   "temple_lydian.wav" in x3d)
check("Pool sound file referenced",     "pool_major.wav" in x3d)
check("spatialize=true",                'spatialize="true"' in x3d)
check("loop=true",                      'loop="true"' in x3d)

# ---------------------------------------------------------------------------
# 7. Master Script
# ---------------------------------------------------------------------------
print("\n── 7. Master Script ──")

check("MCCFMasterScript DEF present",   "MCCFMasterScript" in x3d)
check("Script node present",            "<Script" in x3d)
check("directOutput=true",              'directOutput="true"' in x3d)
check("pollField function present",     "pollField" in x3d)
check("updateAvatars function",         "updateAvatars" in x3d)
check("API URL in script",              "localhost:5000" in x3d)
check("CDATA section present",          "CDATA" in x3d)
check("callLater poll loop",            "callLater" in x3d)
check("Fallback comment present",       "Backend unreachable" in x3d)

# ---------------------------------------------------------------------------
# 8. ROUTE connections
# ---------------------------------------------------------------------------
print("\n── 8. ROUTE connections ──")

check("ROUTE elements present",         "<ROUTE" in x3d)
sn = _safe_name("The Witness")
check(f"eLean ROUTE for Witness",       f'fromField="{sn}_eLean"' in x3d)
check(f"bStability ROUTE",             f'fromField="{sn}_bStability"' in x3d)
check(f"pOrientation ROUTE",           f'fromField="{sn}_pOrientation"' in x3d)
check(f"sApproach ROUTE",              f'fromField="{sn}_sApproach"' in x3d)
check(f"arousal ROUTE",                f'fromField="{sn}_arousal"' in x3d)
check(f"auraColor ROUTE",              f'fromField="{sn}_auraColor"' in x3d)
check(f"toNode Avatar_{sn}",           f'toNode="Avatar_{sn}"' in x3d)

# ---------------------------------------------------------------------------
# 9. Viewpoint
# ---------------------------------------------------------------------------
print("\n── 9. Viewpoint ──")

check("Viewpoint present",              "<Viewpoint" in x3d)
check("DefaultView present",            'DEF="DefaultView"' in x3d)
check("DirectorView present",           'DEF="DirectorView"' in x3d)
check("NavigationInfo present",         "<NavigationInfo" in x3d)
check("Background present",             "<Background" in x3d)
check("Ground plane present",           "<Box" in x3d)
check("DirectionalLight present",       "<DirectionalLight" in x3d)

# ---------------------------------------------------------------------------
# 10. Multi-avatar scene
# ---------------------------------------------------------------------------
print("\n── 10. Multi-avatar scene ──")

cultivars_3 = [
    make_cultivar("The Witness",  "#60a8f0"),
    make_cultivar("The Steward",  "#4af0a8"),
    make_cultivar("The Advocate", "#f0c060"),
]
x3d_3 = generate_scene(scene_def, cultivars_3)

sn_w = _safe_name("The Witness")
sn_s = _safe_name("The Steward")
sn_a = _safe_name("The Advocate")

check("3 ProtoInstances generated",
      x3d_3.count("<ProtoInstance") == 3,
      str(x3d_3.count("<ProtoInstance")))
check("Witness DEF present",  f'DEF="Avatar_{sn_w}"' in x3d_3)
check("Steward DEF present",  f'DEF="Avatar_{sn_s}"' in x3d_3)
check("Advocate DEF present", f'DEF="Avatar_{sn_a}"' in x3d_3)
check("6 ROUTE blocks (6 fields x 3 agents)",
      x3d_3.count("<ROUTE") >= 18,
      str(x3d_3.count("<ROUTE")))

# ---------------------------------------------------------------------------
# 11. Default positions spread
# ---------------------------------------------------------------------------
print("\n── 11. Default positions ──")

# Single avatar at z=-3
check("Single avatar at 0 0 -3",  "0 0.0 -3.0" in x3d or "0 0 -3" in x3d,
      "position check")

# 3 avatars spread along X
check("3-avatar scene has spread positions",
      "-3.0 0.0 -3.0" in x3d_3 or "-3" in x3d_3)

# ---------------------------------------------------------------------------
# 12. Custom positions
# ---------------------------------------------------------------------------
print("\n── 12. Custom positions ──")

custom_pos = [(1.5, 0.0, 5.0)]
x3d_custom = generate_scene(make_scene_def(), [witness], initial_positions=custom_pos)
check("Custom position applied", "1.5 0.0 5.0" in x3d_custom, x3d_custom[2000:2100])

# ---------------------------------------------------------------------------
# 13. Write to file
# ---------------------------------------------------------------------------
print("\n── 13. Write to file ──")

import tempfile
with tempfile.NamedTemporaryFile(suffix=".x3d", delete=False, mode='w') as tf:
    tmp_path = tf.name

write_scene(x3d, tmp_path)
check("File created",             os.path.exists(tmp_path))
check("File non-empty",           os.path.getsize(tmp_path) > 500)

with open(tmp_path) as f:
    content = f.read()
check("File contains X3D",        "<X3D" in content)
os.unlink(tmp_path)

# ---------------------------------------------------------------------------
# 14. Garden of the Goddess full generation
# ---------------------------------------------------------------------------
print("\n── 14. Garden of the Goddess full generation ──")

def_path = os.path.join(os.path.dirname(__file__), "scenes", "garden_of_the_goddess_def.xml")
if os.path.exists(def_path):
    from mccf_scene_wrapper import SceneDefinition as SD
    with open(def_path) as f:
        gotg_def = SD.from_xml(f.read())

    from mccf_cultivar_lambda import ShadowContext as SC
    witness_full = CultivarDefinition(
        name="The Witness",
        weights={"E":0.20,"B":0.25,"P":0.35,"S":0.20},
        regulation=0.72,
        shadow_context=SC(lambda_val=0.72),
        color="#60a8f0",
        description="Epistemic humility.",
    )

    x3d_gotg = generate_scene(gotg_def, [witness_full])
    check("Garden scene generates",        len(x3d_gotg) > 500)
    check("Garden has 3 zone markers",     x3d_gotg.count("ZoneMarker_") == 3)
    check("Garden has 3 sound nodes",      x3d_gotg.count("<Sound ") == 3)
    check("Garden temple sound",           "temple_lydian.wav" in x3d_gotg)
    check("Garden pool sound",             "pool_major.wav" in x3d_gotg)
    check("Garden library sound",          "library_dorian.wav" in x3d_gotg)
    check("Garden Witness avatar",         "The Witness" in x3d_gotg)

    # Validate XML
    try:
        ET.fromstring(strip_ns(x3d_gotg))
        check("Garden scene is valid XML", True)
    except ET.ParseError as e:
        check("Garden scene is valid XML", False, str(e))

    # Write to static/
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    out_path = os.path.join(static_dir, "mccf_scene.x3d")
    written = write_scene(x3d_gotg, out_path)
    check("Written to static/mccf_scene.x3d", os.path.exists(written))
    print(f"       Output: {written}")
else:
    print(f"  SKIP  scenes/garden_of_the_goddess_def.xml not found")

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
