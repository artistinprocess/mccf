"""
Day 73 — tests for ChorusConfig.voice_actor + per-take Line capture
(priority queue item 4, seed doc §5.2).
"""

import sys
import time
import json
import subprocess

sys.path.insert(0, ".")

from mccf_chorus import (
    ChorusConfig, ChorusManager, parse_chorus_from_zone_xml,
    parse_chorus_from_zone_element,
)
import xml.etree.ElementTree as ET

failures = []


def check(label, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def wait_for_not_pending(mgr, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not mgr.state().get("pending"):
            return True
        time.sleep(0.05)
    return False


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

ZONE_XML_WITH_VOICE = """
<Zone id="temple">
  <Descriptor>An old temple.</Descriptor>
  <Chorus llm="stub" tone="oracular" voice_actor="Oracle" />
</Zone>
"""

ZONE_XML_NO_VOICE = """
<Zone id="garden">
  <Descriptor>A quiet garden.</Descriptor>
  <Chorus llm="stub" tone="reverent" />
</Zone>
"""

cfg_with_voice = parse_chorus_from_zone_xml(ZONE_XML_WITH_VOICE)
check("parses voice_actor attribute from <Chorus>", cfg_with_voice.voice_actor == "Oracle",
      f"got {cfg_with_voice.voice_actor!r}")
check("ChorusConfig.has_voice True when voice_actor set", cfg_with_voice.has_voice is True)

cfg_no_voice = parse_chorus_from_zone_xml(ZONE_XML_NO_VOICE)
check("voice_actor defaults to empty string when absent", cfg_no_voice.voice_actor == "")
check("ChorusConfig.has_voice False when voice_actor unset", cfg_no_voice.has_voice is False)

# ---------------------------------------------------------------------------
# ChorusManager: no voice_actor configured — base behavior unchanged
# ---------------------------------------------------------------------------

mgr1 = ChorusManager()
mgr1.set_config(cfg_no_voice)
mgr1.fire_chorus_from_transcript("[wp1] Cindy: \"test line\"", {"E": 0.5, "B": 0.5, "P": 0.5, "S": 0.5})
ok = wait_for_not_pending(mgr1)
check("firing completes (no voice_actor case)", ok)
state1 = mgr1.state()
check("state()['text'] populated (base overlay behavior unchanged)", bool(state1.get("text")))
check("state()['voice_line'] is None when config has no voice_actor", state1.get("voice_line") is None)
check("captured_lines() empty when no voice_actor ever configured", mgr1.captured_lines() == [])

# ---------------------------------------------------------------------------
# ChorusManager: voice_actor configured — capture on fire
# ---------------------------------------------------------------------------

mgr2 = ChorusManager()
mgr2.set_config(cfg_with_voice)
mgr2.fire_chorus_from_transcript("[wp1] Jack: \"the water is cold\"", {"E": 0.4, "B": 0.3, "P": 0.2, "S": 0.6})
ok = wait_for_not_pending(mgr2)
check("firing completes (voice_actor case)", ok)

state2 = mgr2.state()
voice_line = state2.get("voice_line")
check("state()['voice_line'] is a dict when voice_actor is set", isinstance(voice_line, dict))

if isinstance(voice_line, dict):
    check("voice_line.actor matches config.voice_actor", voice_line.get("actor") == "Oracle")
    check("voice_line.type is 'Statement'", voice_line.get("type") == "Statement")
    check("voice_line.mode is 'improv'", voice_line.get("mode") == "improv")
    check("voice_line.blocking is False", voice_line.get("blocking") is False)
    check("voice_line.trigger is arc-complete scoped to the zone",
          voice_line.get("trigger") == {"type": "arc-complete", "zone": "temple"},
          f"got {voice_line.get('trigger')}")
    check("voice_line.text is non-empty (the Chorus's own commentary)", bool(voice_line.get("text")))
    check("voice_line.id is present and non-empty", bool(voice_line.get("id")))

captured = mgr2.captured_lines()
check("captured_lines() has exactly 1 entry after 1 firing", len(captured) == 1, f"len={len(captured)}")
check("captured_lines() entry matches state()['voice_line']", captured[0] == voice_line if captured else False)

# ---------------------------------------------------------------------------
# ID uniqueness across multiple firings
# ---------------------------------------------------------------------------

mgr2.fire_chorus_from_transcript("[wp2] Jack: \"it is colder now\"", {"E": 0.3, "B": 0.3, "P": 0.2, "S": 0.5})
wait_for_not_pending(mgr2)
captured2 = mgr2.captured_lines()
check("captured_lines() has 2 entries after 2 firings", len(captured2) == 2, f"len={len(captured2)}")
if len(captured2) == 2:
    check("second firing gets a distinct id from the first",
          captured2[0]["id"] != captured2[1]["id"],
          f"{captured2[0]['id']} vs {captured2[1]['id']}")

# ---------------------------------------------------------------------------
# clear_captured_lines() doesn't touch the overlay state
# ---------------------------------------------------------------------------

pre_clear_text = mgr2.state().get("text")
mgr2.clear_captured_lines()
check("clear_captured_lines() empties captured_lines()", mgr2.captured_lines() == [])
check("clear_captured_lines() does not touch overlay text", mgr2.state().get("text") == pre_clear_text)

# ---------------------------------------------------------------------------
# Cross-language check: produced Line actually validates against the real
# dialogue-xml.js (not just "looks like the right shape" by eye).
# ---------------------------------------------------------------------------

if isinstance(voice_line, dict):
    node_script = """
    const D = require('./static_dialogue-xml.js');
    const line = JSON.parse(process.argv[1]);
    const result = D.validateDialogueLines([line]);
    if (!result.valid) {
      console.log('INVALID:' + JSON.stringify(result.errors));
      process.exit(1);
    }
    const xml = D.serializeDialogueBlock([line]);
    const full = '<Scene>' + xml + '</Scene>';
    const reparsed = D.parseDialogueBlock(full);
    if (reparsed.length !== 1 || reparsed[0].id !== line.id || reparsed[0].text !== line.text) {
      console.log('ROUNDTRIP_MISMATCH');
      process.exit(1);
    }
    console.log('OK');
    """
    try:
        result = subprocess.run(
            ["node", "-e", node_script, json.dumps(voice_line)],
            capture_output=True, text=True, timeout=10,
        )
        node_ok = result.returncode == 0 and result.stdout.strip() == "OK"
        check("Chorus-produced Line validates + round-trips through real dialogue-xml.js",
              node_ok, f"stdout={result.stdout.strip()!r} stderr={result.stderr.strip()!r}")
    except FileNotFoundError:
        print("[SKIP] Chorus-produced Line validates through dialogue-xml.js (node not found)")

# ---------------------------------------------------------------------------
# Flask endpoint wiring
# ---------------------------------------------------------------------------

from flask import Flask
from mccf_chorus import register_chorus_api

app = Flask(__name__)
mgr3 = register_chorus_api(app)
mgr3.set_config(cfg_with_voice)
client = app.test_client()

cfg_resp = client.get("/chorus/config").get_json()
check("/chorus/config reports has_voice_actor=True", cfg_resp.get("has_voice_actor") is True)
check("/chorus/config reports the voice_actor name", cfg_resp.get("voice_actor") == "Oracle")

lines_resp = client.get("/chorus/captured_lines").get_json()
check("/chorus/captured_lines returns empty list before any firing", lines_resp.get("lines") == [])

mgr3.fire_chorus_from_transcript("[wp1] X: \"hi\"", {"E": 0.5, "B": 0.5, "P": 0.5, "S": 0.5})
wait_for_not_pending(mgr3)
lines_resp2 = client.get("/chorus/captured_lines").get_json()
check("/chorus/captured_lines returns 1 line after a firing", len(lines_resp2.get("lines", [])) == 1)

clear_resp = client.post("/chorus/captured_lines/clear").get_json()
check("/chorus/captured_lines/clear returns cleared status", clear_resp.get("status") == "cleared")
lines_resp3 = client.get("/chorus/captured_lines").get_json()
check("/chorus/captured_lines empty after clear endpoint", lines_resp3.get("lines") == [])

# ---------------------------------------------------------------------------

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("All checks passed.")
