"""
MCCF Scene Generate API — Smoke Test
======================================
Run from repo root:
    py test_scene_generate_api.py

Tests the generate endpoint logic directly (no Flask server needed).
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(__file__))

# Set up minimal scenes dir for test
os.makedirs("scenes", exist_ok=True)
os.makedirs("static", exist_ok=True)

from mccf_scene_generate_api import (
    _load_scene_def, _resolve_cultivars, _get_registry
)
from mccf_x3d_generator import generate_scene, write_scene
from mccf_scene_wrapper import SceneDefinition

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
# 1. Scene loading
# ---------------------------------------------------------------------------
print("\n── 1. Scene loading ──")

# Garden def should exist from yesterday's work
try:
    defn = _load_scene_def("garden_of_the_goddess")
    check("Garden definition loaded",   defn.id == "garden_of_the_goddess")
    check("Garden has 3 zones",         len(defn.zone_xml_blocks) == 3,
          str(len(defn.zone_xml_blocks)))
except FileNotFoundError as e:
    check("Garden definition loaded",   False, str(e))
    check("Garden has 3 zones",         False)

# Non-existent scene
try:
    _load_scene_def("nonexistent_scene_xyz")
    check("Raises on missing scene",    False, "no exception raised")
except FileNotFoundError:
    check("Raises on missing scene",    True)

# ---------------------------------------------------------------------------
# 2. Cultivar resolution
# ---------------------------------------------------------------------------
print("\n── 2. Cultivar resolution ──")

cultivars = _resolve_cultivars(["The Witness"])
check("The Witness resolved",       len(cultivars) == 1)
check("Name preserved",             cultivars[0].name == "The Witness")
check("Has color",                  len(cultivars[0].color) > 0)
check("Has lambda",                 cultivars[0].get_lambda() > 0)

# Unknown cultivar gets placeholder
unknown = _resolve_cultivars(["Persephone"])
check("Unknown cultivar gets placeholder",  len(unknown) == 1)
check("Unknown name preserved",             unknown[0].name == "Persephone")

# Multiple cultivars
multi = _resolve_cultivars(["The Witness", "The Steward", "The Advocate"])
check("3 cultivars resolved",       len(multi) == 3)
names = [c.name for c in multi]
check("All names present",          "The Witness" in names and "The Steward" in names)

# ---------------------------------------------------------------------------
# 3. Full generation flow (simulating the endpoint)
# ---------------------------------------------------------------------------
print("\n── 3. Full generation flow ──")

scene_def = _load_scene_def("garden_of_the_goddess")
cultivar_defs = _resolve_cultivars(["The Witness"])

x3d = generate_scene(
    scene_def=scene_def,
    cultivar_defs=cultivar_defs,
    api_url="http://localhost:5000",
)

check("X3D generated",              len(x3d) > 100)
check("Contains Witness avatar",    "The Witness" in x3d)
check("Contains zone markers",      "ZoneMarker_" in x3d)
check("Contains Master Script",     "MCCFMasterScript" in x3d)
check("Contains sound nodes",       "<Sound" in x3d)

# Write to static/
out = write_scene(x3d, "static/mccf_scene.x3d")
check("Written to static/",         os.path.exists(out))
check("File is non-empty",          os.path.getsize(out) > 500)

# ---------------------------------------------------------------------------
# 4. List scenes
# ---------------------------------------------------------------------------
print("\n── 4. List available scenes ──")

import glob
scenes_dir = os.path.join(os.path.dirname(__file__), "scenes")
scene_files = []
if os.path.isdir(scenes_dir):
    for fname in os.listdir(scenes_dir):
        if fname.endswith("_def.xml") or fname.endswith(".xml"):
            scene_files.append(fname)

check("scenes/ directory exists",   os.path.isdir(scenes_dir))
check("Garden file present",        any("garden" in f for f in scene_files),
      str(scene_files))

# ---------------------------------------------------------------------------
# 5. Cultivar registry
# ---------------------------------------------------------------------------
print("\n── 5. Cultivar registry ──")

reg = _get_registry()
names = reg.all_names()
check("Registry accessible",          isinstance(names, list))

# These only exist if mccf_cultivars.py is present in the environment
for expected in (["The Witness", "The Steward", "The Advocate"] if names else []):
    check(f"{expected} in registry", expected in names, str(names))

# ---------------------------------------------------------------------------
# 6. Multi-cultivar generation
# ---------------------------------------------------------------------------
print("\n── 6. Multi-cultivar generation ──")

multi_defs = _resolve_cultivars(["The Witness", "The Steward"])
x3d_multi = generate_scene(scene_def, multi_defs, api_url="http://localhost:5000")

check("2-avatar scene generates",   len(x3d_multi) > 100)
check("Both avatars present",       "The Witness" in x3d_multi and
                                     "The Steward" in x3d_multi)
check("2 ProtoInstances",           x3d_multi.count("<ProtoInstance") == 2,
      str(x3d_multi.count("<ProtoInstance")))

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
