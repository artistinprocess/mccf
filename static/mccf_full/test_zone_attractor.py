"""
MCCF V3 Zone Attractor — Smoke Test
=====================================
Run from the repo root:
    python test_zone_attractor.py

Tests:
1. Descriptor decomposition produces expected channel dominance
2. ZoneAttractor builds from JSON-equivalent kwargs
3. Zone pull formula: F = w_pull * R(i,j) * (psi_zone - psi_agent)
4. Proximity coherence increases when inside radius, decays when outside
5. Net pull from three Garden zones
6. XML round-trip (serialize → parse → verify)
7. Garden of the Goddess XML file loads correctly

No Flask server needed. No Ollama needed.
"""

import sys
import math
import os

# Allow running from repo root with zones/ dir present
sys.path.insert(0, os.path.dirname(__file__))

from mccf_zones import SemanticZone, SceneGraph
from mccf_zone_attractor import (
    decompose_descriptor, ZoneAttractor, AttractorRegistry,
    CHANNEL_NAMES, PROXIMITY_COHERENCE_DELTA
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
# 1. Descriptor decomposition
# ---------------------------------------------------------------------------
print("\n── 1. Descriptor decomposition ──")

temple_desc = "sacred wisdom truth eternal divine clarity ancient ritual order contemplation"
temple_psi = decompose_descriptor(temple_desc)
print(f"       Temple psi_zone: {temple_psi}")
check("Temple: P dominant", temple_psi["P"] >= 0.80, str(temple_psi))
check("Temple: E < P",      temple_psi["E"] < temple_psi["P"])
check("Temple: B raised",   temple_psi["B"] > 0.30)

pool_desc = "care vulnerability warmth comfort intimacy presence felt tenderness love welcome bond"
pool_psi = decompose_descriptor(pool_desc)
print(f"       Pool psi_zone:   {pool_psi}")
check("Pool: E dominant", pool_psi["E"] >= 0.80, str(pool_psi))
check("Pool: S raised",   pool_psi["S"] > 0.50)
check("Pool: B low",      pool_psi["B"] < 0.30)

lib_desc = "knowledge wisdom truth insight understanding reflect commit practice steadfast ancient mystery"
lib_psi = decompose_descriptor(lib_desc)
print(f"       Library psi_zone:{lib_psi}")
check("Library: P dominant",  lib_psi["P"] >= 0.80, str(lib_psi))
check("Library: B raised",    lib_psi["B"] > 0.50)

# ---------------------------------------------------------------------------
# 2. ZoneAttractor construction
# ---------------------------------------------------------------------------
print("\n── 2. ZoneAttractor construction ──")

sem = SemanticZone(
    name="the_temple",
    location=(0, 0, 15),
    radius=6.0,
    channel_bias={ch: round(temple_psi[ch] - 0.5, 4) for ch in CHANNEL_NAMES},
    zone_type="sacred",
    color="#ffe080",
)
temple_att = ZoneAttractor(
    zone=sem,
    descriptor=temple_desc,
    psi_zone=temple_psi,
    pull_weight=0.15,
    noise_coefficient=0.05,
    ambient_theme={"scale": "lydian", "tempo": "slow",
                   "sound_file": "sounds/temple_lydian.wav", "format": "wav"},
)
check("ZoneAttractor created",   temple_att is not None)
check("psi_zone stored",         temple_att.psi_zone["P"] >= 0.80)
check("ambient format accepted", temple_att.ambient_theme["format"] == "wav")

# ---------------------------------------------------------------------------
# 3. Pull formula
# ---------------------------------------------------------------------------
print("\n── 3. Pull formula ──")

# Agent at pool center with low P (analytically naive character)
pool_sem = SemanticZone(
    name="the_pool",
    location=(0, 0, 0),
    radius=5.0,
    channel_bias={ch: round(pool_psi[ch] - 0.5, 4) for ch in CHANNEL_NAMES},
    zone_type="intimate",
    color="#60c8f0",
)
pool_att = ZoneAttractor(zone=pool_sem, descriptor=pool_desc, psi_zone=pool_psi)

# Set coherence manually to simulate a well-acquainted agent
pool_att.zone_coherence["Persephone"] = 0.80
agent_psi = {"E": 0.30, "B": 0.50, "P": 0.50, "S": 0.30}
agent_pos_inside = (0, 0, 1.0)   # 1 meter from pool center, inside radius=5

pull = pool_att.pull_vector("Persephone", agent_psi, agent_pos_inside)
print(f"       Pull vector (inside): {pull}")

# Expected: E pull positive (agent E=0.30, pool E=0.95, so pulls up)
# Formula: w_pull * R * (psi_zone - psi_agent) * spatial_mod
expected_E_sign = pool_psi["E"] - agent_psi["E"]  # should be positive
check("Pull E positive (pool pulls toward warmth)", pull["E"] > 0, str(pull))
check("Pull S positive (pool pulls toward social)", pull["S"] > 0, str(pull))

# Agent outside radius — pull should be zero
agent_pos_outside = (0, 0, 20.0)  # 20m away, radius=5
pull_out = pool_att.pull_vector("Persephone", agent_psi, agent_pos_outside)
check("Pull zero outside radius", all(v == 0.0 for v in pull_out.values()), str(pull_out))

# Zero coherence agent — pull should be zero even inside radius
pull_zero_r = pool_att.pull_vector("Stranger", agent_psi, agent_pos_inside)
check("Pull zero with zero coherence", all(v == 0.0 for v in pull_zero_r.values()), str(pull_zero_r))

# ---------------------------------------------------------------------------
# 4. Proximity coherence feedback
# ---------------------------------------------------------------------------
print("\n── 4. Proximity coherence feedback ──")

temple_att.zone_coherence.clear()
pos_inside  = (0, 0, 14.0)  # inside temple radius=6
pos_outside = (0, 0, 30.0)  # outside

# 5 steps inside — coherence should climb
r = 0.0
for _ in range(5):
    r = temple_att.update_proximity_coherence("Demeter", pos_inside)
print(f"       Coherence after 5 steps inside: {r:.4f}")
check("Coherence increases inside radius",
      r > 0.0, f"got {r}")
check("Coherence increases by ~delta*5",
      abs(r - PROXIMITY_COHERENCE_DELTA * 5) < 0.01, f"got {r}")

# 1 step outside — should decay
r_after = temple_att.update_proximity_coherence("Demeter", pos_outside)
check("Coherence decays outside radius", r_after < r, f"{r_after} vs {r}")

# ---------------------------------------------------------------------------
# 5. AttractorRegistry — net pull from three zones
# ---------------------------------------------------------------------------
print("\n── 5. AttractorRegistry net pull ──")

scene = SceneGraph()
registry = AttractorRegistry(scene)

lib_sem = SemanticZone(
    name="the_library",
    location=(-10, 0, 8),
    radius=5.0,
    channel_bias={ch: round(lib_psi[ch] - 0.5, 4) for ch in CHANNEL_NAMES},
    zone_type="library",
    color="#60a8f0",
)
lib_att = ZoneAttractor(zone=lib_sem, descriptor=lib_desc, psi_zone=lib_psi)

registry.register(temple_att)
registry.register(pool_att)
registry.register(lib_att)

check("Registry has 3 zones", len(registry.attractors) == 3)
check("SceneGraph synced",    len(scene.zones) == 3)

# Agent equidistant from all three, moderate coherence
for att in registry.attractors.values():
    att.zone_coherence["Persephone"] = 0.60

midpoint = (0, 0, 7.5)   # roughly between pool and temple
agent_psi2 = {"E": 0.50, "B": 0.50, "P": 0.50, "S": 0.50}

net = registry.net_pull("Persephone", agent_psi2, midpoint)
print(f"       Net pull at midpoint: {net}")
check("Net pull computed (dict with 4 channels)",
      set(net.keys()) == set(CHANNEL_NAMES))

bulk = registry.report_proximity("Persephone", midpoint)
check("Bulk proximity updates all zones", len(bulk) == 3)

# ---------------------------------------------------------------------------
# 6. XML round-trip
# ---------------------------------------------------------------------------
print("\n── 6. XML round-trip ──")

xml_out = temple_att.to_xml()
print(f"       Temple XML (first 120 chars): {xml_out[:120]}...")
check("XML starts with <Zone",      xml_out.strip().startswith("<Zone"))
check("XML contains Descriptor",    "<Descriptor>" in xml_out)
check("XML contains AmbientTheme",  "AmbientTheme" in xml_out)
check("XML contains lydian",        "lydian" in xml_out)
check("XML contains wav format",    'format="wav"' in xml_out)

# Parse it back
att2 = ZoneAttractor.from_xml(xml_out)
check("Round-trip: zone name preserved",  att2.zone.name == "the_temple")
check("Round-trip: zone_type preserved",  att2.zone.zone_type == "sacred")
check("Round-trip: P dominant",           att2.psi_zone["P"] >= 0.80)
check("Round-trip: ambient format wav",   att2.ambient_theme.get("format") == "wav")

# ZoneSet round-trip
zoneset_xml = registry.to_xml()
check("ZoneSet XML starts with ZoneSet",
      "<ZoneSet" in zoneset_xml)

scene2 = SceneGraph()
reg2 = AttractorRegistry(scene2)
reg2.load_xml(zoneset_xml)
check("ZoneSet round-trip: 3 zones loaded", len(reg2.attractors) == 3)

# ---------------------------------------------------------------------------
# 7. Garden of the Goddess XML file
# ---------------------------------------------------------------------------
print("\n── 7. Garden of the Goddess XML ──")

xml_path = os.path.join(os.path.dirname(__file__), "garden_of_the_goddess.xml")
if os.path.exists(xml_path):
    with open(xml_path) as f:
        gotg_xml = f.read()

    scene3 = SceneGraph()
    reg3 = AttractorRegistry(scene3)
    reg3.load_xml(gotg_xml)

    check("Garden XML loads 3 zones", len(reg3.attractors) == 3)
    check("the_temple present",  "the_temple"  in reg3.attractors)
    check("the_pool present",    "the_pool"    in reg3.attractors)
    check("the_library present", "the_library" in reg3.attractors)

    t = reg3.attractors["the_temple"]
    p = reg3.attractors["the_pool"]
    l = reg3.attractors["the_library"]

    check("Temple P dominant in garden XML", t.psi_zone["P"] >= 0.80)
    check("Pool E dominant in garden XML",   p.psi_zone["E"] >= 0.80)
    check("Library P dominant in garden XML", l.psi_zone["P"] >= 0.80)

    check("Temple lydian scale",  t.ambient_theme.get("scale") == "lydian")
    check("Pool major scale",     p.ambient_theme.get("scale") == "major")
    check("Library dorian scale", l.ambient_theme.get("scale") == "dorian")
else:
    print(f"  SKIP  garden_of_the_goddess.xml not found at {xml_path}")

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
