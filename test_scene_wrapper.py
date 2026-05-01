"""
MCCF V3 Scene Wrapper — Smoke Test
====================================
Run from the repo root:
    python test_scene_wrapper.py

Tests:
1. SceneDefinition from dict
2. SceneDefinition XML round-trip
3. SceneEpisode creation and validation
4. SceneEpisode XML round-trip
5. SceneRegistry: definition required before episode
6. SceneRegistry: episodes_for_scene filter
7. Garden of the Goddess definition XML file loads
8. SceneEpisode references the definition cleanly
9. Mode validation
10. ZoneRef serialization
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from mccf_scene_wrapper import (
    SceneDefinition, SceneEpisode, SceneRegistry,
    ArcRef, ZoneRef, VALID_MODES
)

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
# 1. SceneDefinition from dict
# ---------------------------------------------------------------------------
print("\n── 1. SceneDefinition from dict ──")

defn = SceneDefinition(
    id="garden_of_the_goddess",
    author="Len Bullard",
    description="Three zones.",
    zone_xml_blocks=['<Zone id="the_temple" zone_type="sacred"/>'],
)
check("id preserved",          defn.id == "garden_of_the_goddess")
check("author preserved",      defn.author == "Len Bullard")
check("zone_xml_blocks count", len(defn.zone_xml_blocks) == 1)
check("to_dict works",         defn.to_dict()["zone_count"] == 1)

# ---------------------------------------------------------------------------
# 2. SceneDefinition XML round-trip
# ---------------------------------------------------------------------------
print("\n── 2. SceneDefinition XML round-trip ──")

xml_out = defn.to_xml()
check("XML contains SceneDefinition", "<SceneDefinition" in xml_out)
check("XML contains ZoneSet",         "<ZoneSet>" in xml_out)
check("XML contains xmlns",           "xmlns=" in xml_out)
check("XML contains author",          'author="Len Bullard"' in xml_out)

defn2 = SceneDefinition.from_xml(xml_out)
check("Round-trip: id",          defn2.id == "garden_of_the_goddess")
check("Round-trip: author",      defn2.author == "Len Bullard")
check("Round-trip: description", "Three zones" in defn2.description)
check("Round-trip: zone count",  len(defn2.zone_xml_blocks) == 1)

# ---------------------------------------------------------------------------
# 3. SceneEpisode creation
# ---------------------------------------------------------------------------
print("\n── 3. SceneEpisode creation ──")

ep = SceneEpisode(
    id="session_001",
    scene_ref="garden_of_the_goddess",
    mode="improvisation",
    notes="First Garden session.",
)
ep.add_arc(ArcRef(cultivar="The Witness", actor="ollama", voice="Microsoft David"))
ep.add_arc(ArcRef(cultivar="The Steward", actor="ollama"))

check("episode id",       ep.id == "session_001")
check("scene_ref",        ep.scene_ref == "garden_of_the_goddess")
check("mode",             ep.mode == "improvisation")
check("arc count",        len(ep.arcs) == 2)
check("arc cultivar",     ep.arcs[0].cultivar == "The Witness")
check("arc voice",        ep.arcs[0].voice == "Microsoft David")

d = ep.to_dict()
check("to_dict arc_count",   d["arc_count"] == 2)
check("to_dict scene_ref",   d["scene_ref"] == "garden_of_the_goddess")

# ---------------------------------------------------------------------------
# 4. SceneEpisode XML round-trip
# ---------------------------------------------------------------------------
print("\n── 4. SceneEpisode XML round-trip ──")

ep_xml = ep.to_xml()
check("XML contains SceneEpisode",    "<SceneEpisode" in ep_xml)
check("XML contains scene_ref",       'scene_ref="garden_of_the_goddess"' in ep_xml)
check("XML contains EmotionalArc",    "<EmotionalArc" in ep_xml)
check("XML contains The Witness",     "The Witness" in ep_xml)
check("XML contains improvisation",   'mode="improvisation"' in ep_xml)
check("XML contains xmlns",           "xmlns=" in ep_xml)

ep2 = SceneEpisode.from_xml(ep_xml)
check("Round-trip: id",         ep2.id == "session_001")
check("Round-trip: scene_ref",  ep2.scene_ref == "garden_of_the_goddess")
check("Round-trip: mode",       ep2.mode == "improvisation")
check("Round-trip: arc count",  len(ep2.arcs) == 2)
check("Round-trip: cultivar 0", ep2.arcs[0].cultivar == "The Witness")
check("Round-trip: cultivar 1", ep2.arcs[1].cultivar == "The Steward")
check("Round-trip: notes",      "First Garden" in ep2.notes)

# ---------------------------------------------------------------------------
# 5. SceneRegistry: definition required before episode
# ---------------------------------------------------------------------------
print("\n── 5. Registry: definition required before episode ──")

reg = SceneRegistry()
try:
    reg.create_episode(scene_ref="nonexistent_scene")
    check("Raises on missing definition", False, "no exception raised")
except ValueError as e:
    check("Raises on missing definition", "not loaded" in str(e), str(e))

reg.register_definition(defn)
ep3 = reg.create_episode(scene_ref="garden_of_the_goddess", mode="playback")
check("Episode created after definition loaded", ep3 is not None)
check("Episode in registry",                     reg.get_episode(ep3.id) is not None)

# ---------------------------------------------------------------------------
# 6. episodes_for_scene filter
# ---------------------------------------------------------------------------
print("\n── 6. episodes_for_scene filter ──")

defn_b = SceneDefinition(id="other_scene")
reg.register_definition(defn_b)
ep4 = reg.create_episode(scene_ref="other_scene")
ep5 = reg.create_episode(scene_ref="garden_of_the_goddess")

garden_eps = reg.episodes_for_scene("garden_of_the_goddess")
other_eps  = reg.episodes_for_scene("other_scene")

check("Garden has 2 episodes",  len(garden_eps) == 2, str(len(garden_eps)))
check("Other has 1 episode",    len(other_eps) == 1)

summary = reg.summary()
check("Summary has definitions key",    "definitions" in summary)
check("Summary has episode_count",      summary["episode_count"] == 3)

# ---------------------------------------------------------------------------
# 7. Garden of the Goddess definition XML file
# ---------------------------------------------------------------------------
print("\n── 7. Garden of the Goddess definition XML file ──")

def_path = os.path.join(os.path.dirname(__file__), "garden_of_the_goddess_def.xml")
if os.path.exists(def_path):
    with open(def_path) as f:
        gotg_xml = f.read()

    reg2 = SceneRegistry()
    defn_gotg = reg2.load_definition_xml(gotg_xml)

    check("ID loaded",           defn_gotg.id == "garden_of_the_goddess")
    check("Author loaded",       defn_gotg.author == "Len Bullard")
    check("3 zones loaded",      len(defn_gotg.zone_xml_blocks) == 3, str(len(defn_gotg.zone_xml_blocks)))
    check("Description present", len(defn_gotg.description) > 10)
    check("Metadata loaded",     defn_gotg.metadata.get("default_mode") == "improvisation")

    # Zone XML blocks contain expected zone ids
    all_zone_xml = " ".join(defn_gotg.zone_xml_blocks)
    check("the_temple in zones",  "the_temple"  in all_zone_xml)
    check("the_pool in zones",    "the_pool"    in all_zone_xml)
    check("the_library in zones", "the_library" in all_zone_xml)

    # Re-export round-trip
    re_export = defn_gotg.to_xml()
    defn_gotg2 = SceneDefinition.from_xml(re_export)
    check("Re-export round-trip: id",         defn_gotg2.id == "garden_of_the_goddess")
    check("Re-export round-trip: zone count", len(defn_gotg2.zone_xml_blocks) == 3)
else:
    print(f"  SKIP  garden_of_the_goddess_def.xml not found at {def_path}")

# ---------------------------------------------------------------------------
# 8. Full flow: definition → episode → arc → XML export
# ---------------------------------------------------------------------------
print("\n── 8. Full flow: definition → episode → arc → export ──")

reg3 = SceneRegistry()
with open(def_path) as f:
    reg3.load_definition_xml(f.read())

ep_full = reg3.create_episode(
    scene_ref="garden_of_the_goddess",
    mode="improvisation",
    notes="Persephone enters the garden.",
)
ep_full.add_arc(ArcRef(
    cultivar="The Witness",
    actor="ollama",
    voice="Microsoft David",
    arc_file="exports/witness_session_001.xml",
))

full_xml = ep_full.to_xml()
check("Full flow XML valid",        "<SceneEpisode" in full_xml)
check("Full flow arc_file present", "witness_session_001" in full_xml)
check("Full flow scene_ref",        "garden_of_the_goddess" in full_xml)

# Load it back
ep_loaded = SceneEpisode.from_xml(full_xml)
check("Full flow round-trip: arc_file", ep_loaded.arcs[0].arc_file == "exports/witness_session_001.xml")

# ---------------------------------------------------------------------------
# 9. Mode validation
# ---------------------------------------------------------------------------
print("\n── 9. Mode validation ──")

for valid_mode in VALID_MODES:
    try:
        ep_m = SceneEpisode(id="x", scene_ref="y", mode=valid_mode)
        check(f"Mode '{valid_mode}' accepted", True)
    except ValueError:
        check(f"Mode '{valid_mode}' accepted", False)

try:
    SceneEpisode(id="x", scene_ref="y", mode="interpretive_dance")
    check("Invalid mode raises ValueError", False)
except ValueError:
    check("Invalid mode raises ValueError", True)

# ---------------------------------------------------------------------------
# 10. ZoneRef serialization
# ---------------------------------------------------------------------------
print("\n── 10. ZoneRef serialization ──")

zref = ZoneRef(href="zones/shared_temple.xml", zone_id="the_temple")
zref_xml = zref.to_xml()
check("ZoneRef XML contains href",    'href="zones/shared_temple.xml"' in zref_xml)
check("ZoneRef XML contains zone_id", 'zone_id="the_temple"' in zref_xml)

# SceneDefinition with zone_refs
defn_with_ref = SceneDefinition(
    id="scene_with_refs",
    zone_refs=[zref],
)
ref_xml = defn_with_ref.to_xml()
check("SceneDefinition with ZoneRef exports", "ZoneRef" in ref_xml)

defn_with_ref2 = SceneDefinition.from_xml(ref_xml)
check("ZoneRef round-trip: count", len(defn_with_ref2.zone_refs) == 1)
check("ZoneRef round-trip: href",  defn_with_ref2.zone_refs[0].href == "zones/shared_temple.xml")

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
