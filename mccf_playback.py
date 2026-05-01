"""
MCCF V3 — Playback Mode
========================
Implements V3 Spec item 6 (Playback): replay a recorded EmotionalArc XML
export through the field without calling the LLM.

What it does:
    Reads an arc export from exports/ directory.
    Extracts waypoints in stepno order (handles any number of waypoints).
    Pushes each waypoint's channel state (E, B, P, S) to the named
    cultivar agent in the CoherenceField at a configurable pace.
    The X3D scene receives updates via the existing /field poll —
    the Master Script does not know or care if values came from a
    live LLM or playback.
    Multiple cultivars in one file play back simultaneously.

Stops and holds at the final waypoint by default.
Optional loop parameter replays from the beginning.

Endpoints:
    GET  /arc/playback                  list available export files
    POST /arc/playback/start            start playback
    GET  /arc/playback/state            current playback state
    POST /arc/playback/step             advance one step manually
    POST /arc/playback/stop             stop and hold
    POST /arc/playback/reset            reset to first waypoint

POST /arc/playback/start body:
    {
        "file":    "arc_Cindy_2026-04-26162557.xml",  // required
        "pace":    3.0,    // seconds per waypoint, default 3.0
        "loop":    false,  // loop at end, default false
        "auto":    true    // auto-advance, default true
                           // false = manual step-through
    }

GET /arc/playback/state returns:
    {
        "status":      "playing" | "paused" | "complete" | "idle",
        "file":        "arc_Cindy_...",
        "step":        3,
        "total_steps": 7,
        "cultivars":   ["Cindy"],
        "current_waypoint": {
            "id": "W3_THE_ASK", "stepno": 3,
            "E": 0.62, "B": 0.48, "P": 0.71, "S": 0.55,
            "question": "...", "response": "...",
            "cultivar": "Cindy"
        },
        "pace":   3.0,
        "loop":   false
    }

Register in mccf_api.py:
    from mccf_playback import register_playback_api
    register_playback_api(app, field)

Authors: Len Bullard, Claude Sonnet 4.6 (Tae)
V3 Spec v0.2, May 2026
"""

import os
import time
import threading
import xml.etree.ElementTree as ET
import re
from dataclasses import dataclass, field
from typing import Optional

from flask import Blueprint, request, jsonify

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PACE    = 3.0    # seconds per waypoint
EXPORTS_DIR_NAME = "exports"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_ns(xml_string: str) -> str:
    clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', xml_string)
    clean = re.sub(r'<(\w+):(\w+)', r'<\2', clean)
    clean = re.sub(r'</(\w+):(\w+)', r'</\2', clean)
    return clean

def _exports_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        EXPORTS_DIR_NAME
    )

# ---------------------------------------------------------------------------
# ArcWaypoint — one step in a playback sequence
# ---------------------------------------------------------------------------

@dataclass
class ArcWaypoint:
    stepno:   int
    wp_id:    str
    cultivar: str
    E: float = 0.5
    B: float = 0.5
    P: float = 0.5
    S: float = 0.5
    question: str = ""
    response: str = ""
    mode:     str = ""
    coherence: float = 0.0
    drift:    str = ""
    lambda_val: str = ""

    def channel_dict(self) -> dict:
        return {"E": self.E, "B": self.B, "P": self.P, "S": self.S}

    def to_dict(self) -> dict:
        return {
            "stepno":    self.stepno,
            "id":        self.wp_id,
            "cultivar":  self.cultivar,
            "E":         self.E,
            "B":         self.B,
            "P":         self.P,
            "S":         self.S,
            "question":  self.question,
            "response":  self.response,
            "mode":      self.mode,
            "coherence": self.coherence,
            "drift":     self.drift,
            "lambda":    self.lambda_val,
        }


# ---------------------------------------------------------------------------
# ArcParser — reads EmotionalArc XML, returns ordered waypoints per cultivar
# ---------------------------------------------------------------------------

def parse_arc_file(filepath: str) -> dict:
    """
    Parse an EmotionalArc XML export file.

    Returns:
    {
        "arc_id":    "...",
        "cultivars": ["Cindy", ...],
        "waypoints": [ArcWaypoint, ...],   # all cultivars, sorted by stepno
        "by_cultivar": {
            "Cindy": [ArcWaypoint, ...],   # sorted by stepno
        },
        "genre": "...",
        "seed":  "...",
    }
    """
    with open(filepath, encoding="utf-8") as f:
        raw = f.read()

    root = ET.fromstring(_strip_ns(raw))

    arc_id   = root.get("id", os.path.basename(filepath))
    genre    = ""
    seed     = ""

    # Find all Cultivar elements (may be nested under EmotionalArc root
    # or the root itself may be the cultivar container)
    cultivar_els = root.findall(".//Cultivar")
    if not cultivar_els:
        # Some exports have Cultivar as direct child
        cultivar_els = [root] if root.tag == "Cultivar" else []

    by_cultivar = {}
    all_waypoints = []

    for cel in cultivar_els:
        cultivar_name = cel.get("agentname", cel.get("id", "unknown"))

        # Genre and seed (may be at cultivar level)
        genre_el = cel.find("Genre")
        if genre_el is not None:
            genre = genre_el.get("narrative", "")
        seed_el = cel.find("Seed")
        if seed_el is not None:
            seed = seed_el.get("value", "")

        waypoints = []
        for wp_el in cel.findall("Waypoint"):
            try:
                stepno = int(wp_el.get("stepno", 0))
            except ValueError:
                stepno = 0

            wp = ArcWaypoint(
                stepno    = stepno,
                wp_id     = wp_el.get("id", f"W{stepno}"),
                cultivar  = cultivar_name,
                E         = float(wp_el.get("E", 0.5)),
                B         = float(wp_el.get("B", 0.5)),
                P         = float(wp_el.get("P", 0.5)),
                S         = float(wp_el.get("S", 0.5)),
                mode      = wp_el.get("Mode", wp_el.get("mode", "")),
                coherence = float(wp_el.get("Coherence", wp_el.get("coherence", 0))),
                drift     = wp_el.get("drift", ""),
                lambda_val= wp_el.get("lambda", ""),
            )

            q_el = wp_el.find("Question")
            r_el = wp_el.find("Response")
            wp.question = q_el.text.strip() if (q_el is not None and q_el.text) else ""
            wp.response = r_el.text.strip() if (r_el is not None and r_el.text) else ""

            waypoints.append(wp)
            all_waypoints.append(wp)

        waypoints.sort(key=lambda w: w.stepno)
        by_cultivar[cultivar_name] = waypoints

    all_waypoints.sort(key=lambda w: (w.stepno, w.cultivar))

    return {
        "arc_id":      arc_id,
        "cultivars":   list(by_cultivar.keys()),
        "waypoints":   all_waypoints,
        "by_cultivar": by_cultivar,
        "genre":       genre,
        "seed":        seed,
        "total_steps": max((w.stepno for w in all_waypoints), default=0),
    }


# ---------------------------------------------------------------------------
# PlaybackSession — manages one active playback
# ---------------------------------------------------------------------------

class PlaybackSession:
    """
    Manages a single arc playback session.
    Runs an optional auto-advance timer in a background thread.
    Thread-safe: all state guarded by _lock.
    """

    STATUS_IDLE     = "idle"
    STATUS_PLAYING  = "playing"
    STATUS_PAUSED   = "paused"
    STATUS_COMPLETE = "complete"

    def __init__(self, arc_data: dict, field,
                 pace: float = DEFAULT_PACE,
                 loop: bool = False,
                 auto: bool = True):
        self.arc_data    = arc_data
        self.field       = field
        self.pace        = pace
        self.loop        = loop
        self.auto        = auto
        self.filename    = arc_data.get("arc_id", "unknown")

        # Merge all cultivars into a unified step sequence.
        # For each stepno, collect all cultivar waypoints at that step.
        self._steps = self._build_step_sequence(arc_data)
        self._current_step_idx = 0
        self._status    = self.STATUS_IDLE
        self._lock      = threading.Lock()
        self._timer: Optional[threading.Timer] = None

    def _build_step_sequence(self, arc_data: dict) -> list:
        """
        Build a list of lists: each entry is [ArcWaypoint, ...] for one stepno.
        All cultivars at the same stepno are grouped together.
        """
        from collections import defaultdict
        grouped = defaultdict(list)
        for wp in arc_data["waypoints"]:
            grouped[wp.stepno].append(wp)
        return [grouped[s] for s in sorted(grouped.keys())]

    def start(self):
        with self._lock:
            self._current_step_idx = 0
            self._status = self.STATUS_PLAYING
            self._apply_current_step()
            if self.auto:
                self._schedule_next()

    def stop(self):
        with self._lock:
            self._cancel_timer()
            self._status = self.STATUS_PAUSED

    def reset(self):
        with self._lock:
            self._cancel_timer()
            self._current_step_idx = 0
            self._status = self.STATUS_IDLE

    def step_forward(self) -> bool:
        """Manually advance one step. Returns False if already at end."""
        with self._lock:
            self._cancel_timer()
            if self._current_step_idx >= len(self._steps) - 1:
                if self.loop:
                    self._current_step_idx = 0
                else:
                    self._status = self.STATUS_COMPLETE
                    return False
            else:
                self._current_step_idx += 1
            self._status = self.STATUS_PLAYING
            self._apply_current_step()
            if self.auto:
                self._schedule_next()
            return True

    def _apply_current_step(self):
        """Push current waypoint channel values into the CoherenceField."""
        if not self._steps:
            return
        step_wps = self._steps[self._current_step_idx]
        for wp in step_wps:
            self._push_to_field(wp)

    def _push_to_field(self, wp: ArcWaypoint):
        """Write waypoint channel values to the agent in the field."""
        try:
            from mccf_core import Agent, ChannelVector
            name = wp.cultivar
            if name not in self.field.agents:
                self.field.register(Agent(name))
            agent = self.field.agents[name]
            # Update agent weights directly — this is what /field returns
            agent.weights = {
                "E": wp.E, "B": wp.B, "P": wp.P, "S": wp.S
            }
            # Also record as a ChannelVector interaction so meta_state updates
            cv = ChannelVector(
                E=wp.E, B=wp.B, P=wp.P, S=wp.S,
                timestamp=time.time(),
                outcome_delta=wp.coherence,
                was_dissonant=False
            )
            # Self-observe to update internal state
            others = [n for n in self.field.agents if n != name]
            if others:
                self.field.interact(name, others[0], cv, mutual=False)
            else:
                agent.observe(agent, cv)
        except Exception as e:
            print(f"Playback push error for {wp.cultivar}: {e}")

    def _schedule_next(self):
        """Schedule auto-advance after pace seconds."""
        self._timer = threading.Timer(self.pace, self._auto_advance)
        self._timer.daemon = True
        self._timer.start()

    def _auto_advance(self):
        with self._lock:
            if self._status != self.STATUS_PLAYING:
                return
            if self._current_step_idx >= len(self._steps) - 1:
                if self.loop:
                    self._current_step_idx = 0
                    self._apply_current_step()
                    self._schedule_next()
                else:
                    self._status = self.STATUS_COMPLETE
                return
            self._current_step_idx += 1
            self._apply_current_step()
            self._schedule_next()

    def _cancel_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def state(self) -> dict:
        with self._lock:
            current_wps = (self._steps[self._current_step_idx]
                           if self._steps else [])
            # Primary waypoint (first cultivar at this step)
            primary = current_wps[0].to_dict() if current_wps else {}
            # All cultivars at this step
            all_at_step = [wp.to_dict() for wp in current_wps]

            return {
                "status":           self._status,
                "file":             self.filename,
                "step_index":       self._current_step_idx,
                "step":             primary.get("stepno", 0),
                "total_steps":      self.arc_data.get("total_steps", 0),
                "total_step_groups":len(self._steps),
                "cultivars":        self.arc_data.get("cultivars", []),
                "genre":            self.arc_data.get("genre", ""),
                "current_waypoint": primary,
                "all_at_step":      all_at_step,
                "pace":             self.pace,
                "loop":             self.loop,
                "auto":             self.auto,
            }


# ---------------------------------------------------------------------------
# PlaybackManager — app-level singleton
# ---------------------------------------------------------------------------

class PlaybackManager:
    """
    Holds the active PlaybackSession and provides file listing.
    One instance per Flask app.
    """

    def __init__(self, field):
        self.field = field
        self._session: Optional[PlaybackSession] = None
        self._lock = threading.Lock()

    def list_files(self) -> list:
        """List arc XML files in exports/ directory."""
        exports = _exports_dir()
        if not os.path.isdir(exports):
            return []
        files = []
        for fname in sorted(os.listdir(exports), reverse=True):
            if not fname.endswith(".xml"):
                continue
            fpath = os.path.join(exports, fname)
            size  = os.path.getsize(fpath)
            # Quick peek at cultivar name and step count
            cultivar = ""
            steps    = 0
            try:
                with open(fpath, encoding="utf-8") as f:
                    raw = f.read(2000)  # read first 2KB only
                m = re.search(r'agentname="([^"]+)"', raw)
                if m:
                    cultivar = m.group(1)
                steps = len(re.findall(r'<Waypoint ', raw))
            except Exception:
                pass
            files.append({
                "filename": fname,
                "size":     size,
                "cultivar": cultivar,
                "steps_seen": steps,  # may be partial if file > 2KB
            })
        return files

    def start(self, filename: str, pace: float = DEFAULT_PACE,
              loop: bool = False, auto: bool = True) -> dict:
        exports = _exports_dir()
        filepath = os.path.join(exports, filename)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Export file not found: {filename}")

        arc_data = parse_arc_file(filepath)
        if not arc_data["waypoints"]:
            raise ValueError(f"No waypoints found in {filename}")

        with self._lock:
            if self._session:
                self._session.stop()
            self._session = PlaybackSession(
                arc_data=arc_data,
                field=self.field,
                pace=pace,
                loop=loop,
                auto=auto,
            )
            self._session.start()
        return self._session.state()

    def state(self) -> dict:
        with self._lock:
            if not self._session:
                return {"status": "idle", "message": "No playback session active."}
            return self._session.state()

    def stop(self) -> dict:
        with self._lock:
            if not self._session:
                return {"status": "idle"}
            self._session.stop()
            return self._session.state()

    def step(self) -> dict:
        with self._lock:
            if not self._session:
                return {"status": "idle", "error": "No session active"}
            self._session.step_forward()
            return self._session.state()

    def reset(self) -> dict:
        with self._lock:
            if not self._session:
                return {"status": "idle"}
            self._session.reset()
            return self._session.state()


# ---------------------------------------------------------------------------
# Flask Blueprint
# ---------------------------------------------------------------------------

playback_bp = Blueprint("playback_v3", __name__)

def _mgr() -> PlaybackManager:
    return playback_bp.manager


@playback_bp.route("/arc/playback", methods=["GET"])
def list_playback_files():
    """List available arc export files."""
    return jsonify({
        "files":       _mgr().list_files(),
        "exports_dir": _exports_dir(),
    })


@playback_bp.route("/arc/playback/start", methods=["POST"])
def start_playback():
    """
    Start playback of an arc export file.

    Body: {
        "file":  "arc_Cindy_2026-04-26162557.xml",
        "pace":  3.0,
        "loop":  false,
        "auto":  true
    }
    """
    data = request.get_json() or {}
    filename = data.get("file")
    if not filename:
        return jsonify({"error": "file required"}), 400

    pace = float(data.get("pace", DEFAULT_PACE))
    loop = bool(data.get("loop", False))
    auto = bool(data.get("auto", True))

    try:
        state = _mgr().start(filename, pace=pace, loop=loop, auto=auto)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Playback start failed: {e}"}), 500

    return jsonify({"status": "started", "state": state})


@playback_bp.route("/arc/playback/state", methods=["GET"])
def playback_state():
    """Get current playback state."""
    return jsonify(_mgr().state())


@playback_bp.route("/arc/playback/step", methods=["POST"])
def playback_step():
    """Advance one step manually."""
    return jsonify(_mgr().step())


@playback_bp.route("/arc/playback/stop", methods=["POST"])
def stop_playback():
    """Stop (pause) playback, hold current state."""
    return jsonify(_mgr().stop())


@playback_bp.route("/arc/playback/reset", methods=["POST"])
def reset_playback():
    """Reset to first waypoint."""
    return jsonify(_mgr().reset())


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_playback_api(app, field) -> PlaybackManager:
    """
    Register the playback blueprint with a Flask app.

    Usage in mccf_api.py (add after V3 registrations):
        from mccf_playback import register_playback_api
        playback_manager = register_playback_api(app, field)
    """
    manager = PlaybackManager(field)
    playback_bp.manager = manager
    app.register_blueprint(playback_bp)
    return manager
