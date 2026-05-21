"""
MCCF Greek Chorus / Marquee System — v1
========================================
Implements the Chorus zone extension designed in Day 12.

Architecture:
  - One Chorus per scene (Option A).  Schema supports future Option B via <Radius>.
  - Fires async at arc-complete (all active arcs _pbArcComplete=true).
  - Text display only — no TTS, no BroadcastChannel routing.
  - Other agents have no awareness of the Chorus.

Supported llm values:
  stub              — rotating canned responses, 1.5 s simulated delay (no LLM required)
  ollama:<model>    — POST http://localhost:11434/api/generate
  openai:<model>    — POST https://api.openai.com/v1/chat/completions (OPENAI_API_KEY env)

Display mode v1:
  overlay           — HTML <div id="chorus-overlay"> in mccf_x3d_loader.html

Display mode v2 (future):
  x3d               — SAI write to Text node + viewpoint cut

Module ownership (never duplicate logic in mccf_api.py or mccf_playback.py):
  <Chorus> XML parsing           — this module
  LLM dispatch                   — this module
  stub responses                 — this module
  /chorus/config endpoint        — this module
  fire_chorus()                  — this module

Constraints (Never Change):
  Chorus fires async — never blocks arc progression or TTS
  Chorus has no voice — text display only
  Chorus is not in voice map, arc dialogue, or BroadcastChannel
  mccf_chorus.py owns all Chorus logic
  Couplers write to expressive_cv only — unrelated to Chorus

Authors: Len Bullard, Claude Sonnet 4.6 (Tae)
MCCF V4, Day 13
"""

import os
import time
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

from flask import Blueprint, jsonify, request

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STUB_RESPONSES = [
    "They will not remember this conversation the same way.",
    "One of them already knows how this ends.",
    "The silence after was longer than it seemed.",
    "What was not said will matter more.",
    "This has happened before.  It will happen again.",
]

STUB_DELAY_S = 1.5

# Tone → brief system-prompt fragment used when no <Persona> is present
_TONE_PROMPTS = {
    "sardonic":  "You observe with cold wit.  Nothing surprises you.",
    "ominous":   "You sense what the participants cannot.  You speak in low, heavy certainties.",
    "reverent":  "You witness with quiet awe.  The moment matters.",
    "oracular":  "You speak in compressed images.  You do not explain.",
    "anxious":   "You feel the instability in what just passed.  Something is unresolved.",
}

# ---------------------------------------------------------------------------
# ChorusConfig — parsed from a Zone's <Chorus> element
# ---------------------------------------------------------------------------

@dataclass
class ChorusConfig:
    zone_id:       str
    zone_desc:     str          = ""
    llm:           str          = ""          # "" = mute; "stub"; "ollama:model"; "openai:model"
    tone:          str          = "oracular"
    max_tokens:    int          = 80
    display:       str          = "overlay"   # "overlay" | "x3d"
    persona:       str          = ""          # <Persona> text, overrides tone if set
    x3d_def:       str          = ""          # <MarqueeTarget x3d_def=...>
    viewpoint_def: str          = ""          # <MarqueeTarget viewpoint_def=...>

    @property
    def is_mute(self) -> bool:
        return not self.llm

    @property
    def is_stub(self) -> bool:
        return self.llm == "stub"


def parse_chorus_from_zone_element(zone_el: ET.Element) -> Optional[ChorusConfig]:
    """
    Extract a ChorusConfig from a parsed <Zone> XML element.
    Returns None if no <Chorus> child is present (mute zone — normal behavior).
    """
    chorus_el = zone_el.find("Chorus")
    if chorus_el is None:
        return None

    zone_id   = zone_el.get("id", "")
    desc_el   = zone_el.find("Descriptor")
    zone_desc = (desc_el.text or "").strip() if desc_el is not None else ""

    llm        = chorus_el.get("llm", "").strip()
    tone       = chorus_el.get("tone", "oracular").strip()
    max_tokens = int(chorus_el.get("max_tokens", 80))
    display    = chorus_el.get("display", "overlay").strip()

    persona_el = chorus_el.find("Persona")
    persona    = (persona_el.text or "").strip() if persona_el is not None else ""

    marquee_el   = chorus_el.find("MarqueeTarget")
    x3d_def      = marquee_el.get("x3d_def", "")      if marquee_el is not None else ""
    viewpoint_def= marquee_el.get("viewpoint_def", "") if marquee_el is not None else ""

    return ChorusConfig(
        zone_id=zone_id,
        zone_desc=zone_desc,
        llm=llm,
        tone=tone,
        max_tokens=max_tokens,
        display=display,
        persona=persona,
        x3d_def=x3d_def,
        viewpoint_def=viewpoint_def,
    )


def parse_chorus_from_zone_xml(zone_xml_str: str, target_zone_id: str = None) -> Optional[ChorusConfig]:
    """
    Parse a <Chorus> config from a Zone XML string.

    If target_zone_id is given, find that specific zone.
    Otherwise return the first zone that carries a <Chorus> element.
    Returns None if no Chorus-bearing zone is found.
    """
    import re
    # Strip namespaces
    clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', zone_xml_str)
    clean = re.sub(r'<(\w+):(\w+)',  r'<\2',  clean)
    clean = re.sub(r'</(\w+):(\w+)', r'</\2', clean)

    try:
        root = ET.fromstring(clean)
    except ET.ParseError:
        return None

    # Root may be <ZoneSet> or <Zone>
    if root.tag == "Zone":
        zone_els = [root]
    else:
        zone_els = root.findall(".//Zone")

    for zone_el in zone_els:
        if target_zone_id and zone_el.get("id") != target_zone_id:
            continue
        cfg = parse_chorus_from_zone_element(zone_el)
        if cfg is not None:
            return cfg

    return None


# ---------------------------------------------------------------------------
# Transcript builder
# ---------------------------------------------------------------------------

def build_transcript(arc_xml_str: str) -> str:
    """
    Walk Waypoints in stepno order, emit dialog elements in document order.
    Speaker attribute on each element preferred; falls back to arc agentname.
    """
    import re
    clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', arc_xml_str)
    clean = re.sub(r'<(\w+):(\w+)',  r'<\2',  clean)
    clean = re.sub(r'</(\w+):(\w+)', r'</\2', clean)

    try:
        root = ET.fromstring(clean)
    except ET.ParseError:
        return ""

    # Resolve arc-level agent name
    cultivar_el = root.find(".//Cultivar")
    agentname   = cultivar_el.get("agentname", "Unknown") if cultivar_el is not None else "Unknown"

    lines = []
    waypoints = root.findall(".//Waypoint")
    waypoints.sort(key=lambda w: int(w.get("stepno", 0)))

    for wp in waypoints:
        label = wp.get("name", wp.get("id", ""))
        for elem in wp:
            if elem.tag not in ("Question", "Response", "Statement"):
                continue
            txt = (elem.text or "").strip()
            if not txt:
                continue
            speaker = elem.get("speaker", "") or agentname
            lines.append(f"[{label}] {speaker}: \"{txt}\"")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM dispatch
# ---------------------------------------------------------------------------

_stub_index = 0
_stub_lock  = threading.Lock()


def _call_stub(config: ChorusConfig, transcript: str, cv: dict) -> str:
    global _stub_index
    time.sleep(STUB_DELAY_S)
    with _stub_lock:
        idx = _stub_index % len(STUB_RESPONSES)
        _stub_index += 1
    return STUB_RESPONSES[idx]


def _build_system_prompt(config: ChorusConfig) -> str:
    if config.persona:
        persona_text = config.persona
    else:
        persona_text = _TONE_PROMPTS.get(config.tone,
            "You observe the scene.  You are detached, precise.")
    return (
        f"{persona_text}\n"
        f"Respond in {config.max_tokens} tokens or fewer.\n"
        "Do not summarize.  Do not address the characters.  Observe.\n"
        "Speak to the audience only."
    )


def _build_user_prompt(config: ChorusConfig, transcript: str, cv: dict) -> str:
    e = cv.get("E", 0.5)
    b = cv.get("B", 0.5)
    p = cv.get("P", 0.5)
    s = cv.get("S", 0.5)
    zone_label = f'"{config.zone_id}"'
    if config.zone_desc:
        zone_label += f" ({config.zone_desc})"
    return (
        f'The following scene just concluded in zone {zone_label}.\n\n'
        f'{transcript}\n\n'
        f'The emotional field at arc end:\n'
        f'  E={e:.3f} B={b:.3f} P={p:.3f} S={s:.3f}\n\n'
        'Offer your observation.'
    )


def _call_ollama(config: ChorusConfig, transcript: str, cv: dict) -> str:
    import urllib.request, json
    _, model = config.llm.split(":", 1)
    system   = _build_system_prompt(config)
    user     = _build_user_prompt(config, transcript, cv)
    payload  = json.dumps({
        "model":  model,
        "prompt": f"{system}\n\n{user}",
        "stream": False,
        "options": {"num_predict": config.max_tokens},
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return (data.get("response") or "").strip()


def _call_openai(config: ChorusConfig, transcript: str, cv: dict) -> str:
    import urllib.request, json
    _, model  = config.llm.split(":", 1)
    api_key   = os.environ.get("OPENAI_API_KEY", "")
    system    = _build_system_prompt(config)
    user      = _build_user_prompt(config, transcript, cv)
    payload   = json.dumps({
        "model": model,
        "max_tokens": config.max_tokens,
        "messages": [
            {"role": "system",  "content": system},
            {"role": "user",    "content": user},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return (data["choices"][0]["message"]["content"] or "").strip()


def _dispatch_llm(config: ChorusConfig, transcript: str, cv: dict) -> str:
    """Route to the correct LLM backend.  Returns the response text."""
    if config.is_stub:
        return _call_stub(config, transcript, cv)
    llm = config.llm.lower()
    if llm.startswith("ollama:"):
        return _call_ollama(config, transcript, cv)
    if llm.startswith("openai:"):
        return _call_openai(config, transcript, cv)
    raise ValueError(f"Unknown llm provider: {config.llm!r}")


# ---------------------------------------------------------------------------
# ChorusManager — singleton, wired at app startup
# ---------------------------------------------------------------------------

class ChorusManager:
    """
    Holds the active scene's Chorus config and the most-recent response.
    fire_chorus() runs async — never blocks the caller.

    Usage in mccf_api.py:
        from mccf_chorus import ChorusManager
        chorus_manager = ChorusManager()
        chorus_manager.set_config(config)        # called from zone-load path
        chorus_manager.fire_chorus(arc_xml, cv)  # called from playback arc-complete hook

    Display:
        Client polls GET /chorus/state to pick up new text.
        chorus-overlay div in mccf_x3d_loader.html renders the text.
    """

    def __init__(self):
        self._config:   Optional[ChorusConfig] = None
        self._last:     dict = {"text": "", "zone_id": "", "timestamp": 0, "pending": False}
        self._lock = threading.Lock()

    # ── Configuration ────────────────────────────────────────────────────

    def set_config(self, config: Optional[ChorusConfig]):
        """Set or clear the active Chorus config for the current scene."""
        with self._lock:
            self._config = config
            if config:
                print(f"  Chorus: configured for zone={config.zone_id} llm={config.llm} display={config.display}")
            else:
                print("  Chorus: cleared (mute scene)")

    def get_config(self) -> Optional[ChorusConfig]:
        with self._lock:
            return self._config

    def load_config_from_scene_xml(self, scene_xml_str: str):
        """
        Parse the active scene XML for a <Zone> carrying <Chorus>.
        Called whenever a scene loads.  Clears config if no Chorus zone found.
        """
        import re
        # Scene XML embeds <Zones><Zone ...><Chorus ...> — parse directly
        clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', scene_xml_str)
        clean = re.sub(r'<(\w+):(\w+)',  r'<\2',  clean)
        clean = re.sub(r'</(\w+):(\w+)', r'</\2', clean)
        try:
            root = ET.fromstring(clean)
        except ET.ParseError:
            self.set_config(None)
            return

        zones_el = root.find("Zones")
        if zones_el is None:
            self.set_config(None)
            return

        for zone_el in zones_el.findall("Zone"):
            cfg = parse_chorus_from_zone_element(zone_el)
            if cfg is not None:
                self.set_config(cfg)
                return

        self.set_config(None)

    # ── Firing ───────────────────────────────────────────────────────────

    def fire_chorus(self, arc_xml_str: str, cv: dict):
        """
        Async entry point called from arc-complete hook in mccf_playback / loader.
        Does nothing if no config or mute.
        Fires in a daemon thread — never blocks TTS or arc progression.
        """
        with self._lock:
            config = self._config

        if config is None or config.is_mute:
            return

        with self._lock:
            if self._last.get("pending"):
                # Previous Chorus still in flight — skip this trigger.
                print("  Chorus: previous response still pending — skipping")
                return
            self._last["pending"] = True

        t = threading.Thread(target=self._run_chorus, args=(config, arc_xml_str, cv), daemon=True)
        t.start()

    def _run_chorus(self, config: ChorusConfig, arc_xml_str: str, cv: dict):
        try:
            transcript = build_transcript(arc_xml_str)
            if not transcript:
                print("  Chorus: empty transcript — skipping LLM call")
                return
            print(f"  Chorus: calling {config.llm} for zone={config.zone_id}")
            text = _dispatch_llm(config, transcript, cv)
            print(f"  Chorus response: {text[:80]!r}{'…' if len(text)>80 else ''}")
            with self._lock:
                self._last = {
                    "text":       text,
                    "zone_id":    config.zone_id,
                    "viewpoint":  config.viewpoint_def,
                    "display":    config.display,
                    "timestamp":  time.time(),
                    "pending":    False,
                }
        except Exception as e:
            print(f"  Chorus error: {e}")
            with self._lock:
                self._last["pending"] = False

    def fire_chorus_from_transcript(self, transcript: str, cv: dict):
        """
        Async entry point for client-driven (X3D auto:false) playback.
        Receives a pre-assembled plain-text transcript from the loader —
        no arc file lookup, no XML parsing.
        Does nothing if no config or mute.
        """
        with self._lock:
            config = self._config

        if config is None or config.is_mute:
            return

        with self._lock:
            if self._last.get("pending"):
                print("  Chorus: previous response still pending — skipping")
                return
            self._last["pending"] = True

        t = threading.Thread(
            target=self._run_chorus_from_transcript,
            args=(config, transcript, cv),
            daemon=True,
        )
        t.start()

    def _run_chorus_from_transcript(self, config: ChorusConfig, transcript: str, cv: dict):
        try:
            print(f"  Chorus: calling {config.llm} for zone={config.zone_id} "
                  f"({len(transcript.splitlines())} transcript lines)")
            text = _dispatch_llm(config, transcript, cv)
            print(f"  Chorus response: {text[:80]!r}{'…' if len(text)>80 else ''}")
            with self._lock:
                self._last = {
                    "text":       text,
                    "zone_id":    config.zone_id,
                    "viewpoint":  config.viewpoint_def,
                    "display":    config.display,
                    "timestamp":  time.time(),
                    "pending":    False,
                }
        except Exception as e:
            print(f"  Chorus error: {e}")
            with self._lock:
                self._last["pending"] = False

    # ── State ────────────────────────────────────────────────────────────

    def state(self) -> dict:
        with self._lock:
            return dict(self._last)

    def clear(self):
        with self._lock:
            self._last = {"text": "", "zone_id": "", "timestamp": 0, "pending": False}


# ---------------------------------------------------------------------------
# Flask Blueprint — /chorus endpoints
# ---------------------------------------------------------------------------

chorus_bp = Blueprint("chorus_v1", __name__)

def _mgr() -> ChorusManager:
    return chorus_bp.manager


@chorus_bp.route("/chorus/load", methods=["POST"])
def chorus_load():
    """
    POST /chorus/load  { "scene_name": "garden_002" }
    Called by mccf_x3d_loader.html when a scene file is selected.
    Finds the matching scene XML and loads Chorus config from it.
    Returns the active config (or {"active": false} if not found).
    """
    import os as _os
    data       = request.get_json() or {}
    scene_name = data.get("scene_name", "").strip()
    if not scene_name:
        return jsonify({"active": False, "reason": "no scene_name"}), 200

    scenes_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "scenes")
    candidates = [
        _os.path.join(scenes_dir, scene_name + "_scene.xml"),
        _os.path.join(scenes_dir, scene_name + ".xml"),
    ]
    mgr = _mgr()
    for cpath in candidates:
        if _os.path.exists(cpath):
            with open(cpath, encoding="utf-8") as f:
                mgr.load_config_from_scene_xml(f.read())
            cfg = mgr.get_config()
            if cfg:
                return jsonify({"active": True, "zone_id": cfg.zone_id, "llm": cfg.llm})
            return jsonify({"active": False, "reason": "no Chorus zone in scene XML"})
    return jsonify({"active": False, "reason": f"scene XML not found for: {scene_name}"}), 200


@chorus_bp.route("/chorus/fire", methods=["POST"])
def chorus_fire():
    """
    POST /chorus/fire
    Client-side arc-complete hook for X3D-driven playback (auto:false mode).

    Body: {
        "transcript":  "...",   // plain-text scene transcript assembled by the loader
        "cv":          { "E": 0.12, "B": 0.09, "P": 0.11, "S": 0.08 },
        "scene_name":  "garden_001"
    }

    The loader accumulates every line of dialogue as it plays and sends the
    full transcript directly — no file lookup, no reload.  The Chorus LLM
    receives exactly what the audience heard.

    Legacy "arc_file" key is accepted for backward-compat but ignored when
    "transcript" is present.
    Returns immediately — does not wait for LLM.
    """
    data = request.get_json() or {}

    mgr = _mgr()
    if mgr.get_config() is None:
        return jsonify({"status": "skipped", "reason": "no chorus config"}), 200

    transcript = data.get("transcript", "").strip()
    if not transcript:
        return jsonify({"status": "skipped", "reason": "empty transcript"}), 200

    cv_raw = data.get("cv") or {}
    cv = {
        "E": float(cv_raw.get("E", 0.5)),
        "B": float(cv_raw.get("B", 0.5)),
        "P": float(cv_raw.get("P", 0.5)),
        "S": float(cv_raw.get("S", 0.5)),
    }

    mgr.fire_chorus_from_transcript(transcript, cv)
    return jsonify({"status": "fired"}), 200


@chorus_bp.route("/chorus/state", methods=["GET"])
def chorus_state():
    """
    GET /chorus/state
    Returns the most recent Chorus text and metadata.
    Polled by mccf_x3d_loader.html to drive the overlay.

    Response:
    {
        "text":      "What was not said will matter more.",
        "zone_id":   "temple",
        "viewpoint": "ChorusView_Temple",
        "display":   "overlay",
        "timestamp": 1716000000.0,
        "pending":   false
    }
    """
    return jsonify(_mgr().state())


@chorus_bp.route("/chorus/clear", methods=["POST"])
def chorus_clear():
    """POST /chorus/clear — dismiss the overlay text."""
    _mgr().clear()
    return jsonify({"status": "cleared"})


@chorus_bp.route("/chorus/config", methods=["GET"])
def chorus_config():
    """GET /chorus/config — active Chorus config (for diagnostics)."""
    cfg = _mgr().get_config()
    if cfg is None:
        return jsonify({"active": False})
    return jsonify({
        "active":       True,
        "zone_id":      cfg.zone_id,
        "llm":          cfg.llm,
        "tone":         cfg.tone,
        "max_tokens":   cfg.max_tokens,
        "display":      cfg.display,
        "has_persona":  bool(cfg.persona),
        "viewpoint":    cfg.viewpoint_def,
        "x3d_def":      cfg.x3d_def,
    })


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_chorus_api(app, manager: ChorusManager = None) -> ChorusManager:
    """
    Register the chorus blueprint.  Creates a ChorusManager if not supplied.

    In mccf_api.py:
        from mccf_chorus import register_chorus_api
        chorus_manager = register_chorus_api(app)
    """
    if manager is None:
        manager = ChorusManager()
    chorus_bp.manager = manager
    app.register_blueprint(chorus_bp)
    return manager
