"""
MCCF V4 — Playback Mode (Day 17 — Concurrent Arc Firing)
=========================================================
Implements V3 Spec item 6 (Playback): replay a recorded EmotionalArc XML
export through the field without calling the LLM.

What it does:
    Reads arc export files from scenes/<scene_name>/arcs/<take_name>/
    (Day 67 directory redesign — previously a flat exports/ directory,
    now retired; see _scenes_root()/_iter_arc_files() below).
    Extracts waypoints in stepno order (handles any number of waypoints).
    Pushes each waypoint's channel state (E, B, P, S) to the named
    cultivar agent in the CoherenceField at a configurable pace.
    The X3D scene receives updates via the existing /field poll —
    the Master Script does not know or care if values came from a
    live LLM or playback.
    Multiple cultivars in one file play back simultaneously.
    Multiple arc files play back concurrently in separate sessions.

Stops and holds at the final waypoint by default.
Optional loop parameter replays from the beginning.

Endpoints:
    GET  /arc/playback                  list available export files
    POST /arc/playback/start            start playback (one arc)
    POST /arc/playback/start/all        start ALL arcs simultaneously
    GET  /arc/playback/state            state of all active sessions
    GET  /arc/playback/state/<sid>      state of one session
    POST /arc/playback/step             advance one step (all sessions or one)
    POST /arc/playback/stop             stop all sessions
    POST /arc/playback/stop/<sid>       stop one session
    POST /arc/playback/reset            reset all sessions
    POST /arc/playback/reset/<sid>      reset one session

POST /arc/playback/start body:
    {
        "file":       "arc_Cindy_2026-04-26162557.xml",  // required
        "session_id": "Cindy",   // optional; defaults to path_name from file
        "pace":       3.0,
        "loop":       false,
        "auto":       false      // false = X3D segmentArrived drives steps
    }

POST /arc/playback/step body (optional):
    {
        "session_id": "Cindy"    // omit to step ALL active sessions
    }

GET /arc/playback/state returns:
    {
        "sessions": {
            "Cindy":   { status, file, step, total_steps, cultivars,
                         current_waypoint, pace, loop, auto },
            "Steward": { ... }
        },
        "active_count": 2
    }

Register in mccf_api.py:
    from mccf_playback import register_playback_api
    register_playback_api(app, field)

Authors: Len Bullard, Claude Sonnet 4.6 (Tae)
V4 Day 17, May 2026
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_ns(xml_string: str) -> str:
    clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', xml_string)
    clean = re.sub(r'<(\w+):(\w+)', r'<\2', clean)
    clean = re.sub(r'</(\w+):(\w+)', r'</\2', clean)
    return clean

def _scenes_root() -> str:
    """
    Day 67 directory redesign: arc files live under scenes/<scene_name>/
    arcs/<take_name>/, written by arc_export_save() in mccf_api.py. This
    replaces the old flat exports/ directory that this module was built
    against (Day 17) — exports/ is retired and nothing writes to it anymore,
    so any lookup against it will always come back empty regardless of what
    the author has actually recorded.
    """
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'scenes'
    )

def _iter_arc_files(scene_filter: str = None, take_filter: str = None):
    """
    Walk scenes/<scene>/arcs/<take>/arc_*.xml, yielding
    (filepath, fname, scene_dir_name, take_dir_name) tuples, newest-first
    within each take directory. Mirrors arc_playback_list()'s walk in
    mccf_api.py exactly — same filename filter (arc_ prefix, .xml suffix),
    same directory shape — so both stay in agreement about what counts as
    an arc file and where it lives.
    """
    scenes_root = _scenes_root()
    if not os.path.isdir(scenes_root):
        return
    scene_dirs = [scene_filter] if scene_filter else \
        [d for d in os.listdir(scenes_root)
         if os.path.isdir(os.path.join(scenes_root, d))]
    for scene_dir_name in scene_dirs:
        arcs_root = os.path.join(scenes_root, scene_dir_name, 'arcs')
        if not os.path.isdir(arcs_root):
            continue
        take_dirs = [take_filter] if take_filter else os.listdir(arcs_root)
        for take_dir_name in take_dirs:
            take_path = os.path.join(arcs_root, take_dir_name)
            if not os.path.isdir(take_path):
                continue
            fnames = sorted(
                [f for f in os.listdir(take_path)
                 if f.endswith('.xml') and f.startswith('arc_')],
                key=lambda f: os.path.getmtime(os.path.join(take_path, f)),
                reverse=True
            )
            for fname in fnames:
                yield (os.path.join(take_path, fname), fname,
                       scene_dir_name, take_dir_name)

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
    qa_lines: list = None   # [{type, speaker, text}, ...] — full sequence
    mode:     str = ""
    coherence: float = 0.0
    drift:    str = ""
    lambda_val: str = ""
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0

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
            "qa_lines":  self.qa_lines or [],
            "mode":      self.mode,
            "coherence": self.coherence,
            "drift":     self.drift,
            "lambda":    self.lambda_val,
            "pos_x":     self.pos_x,
            "pos_y":     self.pos_y,
            "pos_z":     self.pos_z,
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
                # Prefer the "name" attribute (scene XML waypoint name, e.g. "w2").
                # "id" in old arc files may be uppercased/mangled (e.g. "WAYPT2", "W2").
                # Fall back to id if name is absent (legacy arcs).
                wp_id     = wp_el.get("name") or wp_el.get("id", f"W{stepno}"),
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

            qa_lines = []
            for child in wp_el:
                if child.tag in ("Question", "Response", "Statement"):
                    txt = (child.text or "").strip()
                    if txt:
                        qa_lines.append({
                            "type":    child.tag,
                            "speaker": child.get("speaker", ""),
                            "text":    txt,
                        })
            wp.qa_lines = qa_lines
            # Legacy single fields — first Question / last Response
            q_items = [l for l in qa_lines if l["type"] == "Question"]
            r_items = [l for l in qa_lines if l["type"] == "Response"]
            wp.question = q_items[0]["text"]  if q_items else ""
            wp.response = r_items[-1]["text"] if r_items else ""
            wp.pos_x = float(wp_el.get("pos_x", 0.0))
            wp.pos_y = float(wp_el.get("pos_y", 0.0))
            wp.pos_z = float(wp_el.get("pos_z", 0.0))

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
                 auto: bool = True,
                 chorus_callback=None,
                 arc_xml_str: str = ""):
        self.arc_data       = arc_data
        self.field          = field
        self.pace           = pace
        self.loop           = loop
        self.auto           = auto
        self.filename       = arc_data.get("arc_id", "unknown")
        # Chorus: callback is chorus_manager.fire_chorus(arc_xml_str, cv).
        # Stored here so _auto_advance can fire it without importing ChorusManager.
        self._chorus_cb     = chorus_callback   # callable(arc_xml_str, cv) | None
        self._arc_xml_str   = arc_xml_str       # raw XML text for transcript assembly

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
                    self._fire_chorus_if_configured()
                return
            self._current_step_idx += 1
            self._apply_current_step()
            self._schedule_next()

    def _cancel_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _fire_chorus_if_configured(self):
        """
        Fire the Chorus callback after arc completes.
        Async — callback runs in its own daemon thread (ChorusManager handles threading).
        CV assembled from the final waypoint of the primary cultivar.
        """
        if not self._chorus_cb or not self._arc_xml_str:
            return
        try:
            # Build CV from the last step's primary waypoint
            last_wps = self._steps[-1] if self._steps else []
            primary  = last_wps[0] if last_wps else None
            cv = {"E": primary.E, "B": primary.B,
                  "P": primary.P, "S": primary.S} if primary else {}
            self._chorus_cb(self._arc_xml_str, cv)
        except Exception as e:
            print(f"Playback chorus fire error: {e}")

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
    Manages concurrent PlaybackSessions keyed by session_id.

    session_id defaults to the path_name extracted from the arc filename.
    Starting a second arc with the same session_id replaces the first.
    Starting arcs with different session_ids runs them concurrently.

    All mutating operations are protected by a per-manager lock.
    Individual session state reads are lock-free (session._lock is used
    by PlaybackSession itself for thread safety).
    """

    def __init__(self, field):
        self.field = field
        self._sessions: dict = {}          # session_id -> PlaybackSession
        self._lock = threading.Lock()
        self.chorus_callback = None        # set by register_chorus_api after wiring

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _session_id_from_file(self, filename: str, arc_data: dict) -> str:
        """Derive a session_id from arc metadata. Prefers path_name from arc."""
        # Try arc_id first (may contain path info from filename)
        arc_id = arc_data.get("arc_id", "")
        # arc_id is the filename without .xml; extract path_name portion
        base = arc_id
        if base.startswith("arc_"):
            base = base[4:]
        ts_match = re.search(r'^(.*?)_(\d{4}.*)$', base)
        if ts_match:
            return ts_match.group(1)
        # Fallback: first cultivar name
        cultivars = arc_data.get("cultivars", [])
        return cultivars[0] if cultivars else base or filename

    def list_files(self, scene_name: str = None, take_name: str = None) -> list:
        """
        List arc XML files under scenes/<scene>/arcs/<take>/, optionally
        scoped to one scene and/or one take. Omitting scene_name lists
        every arc across every scene (parity with the old exports/-wide
        behavior, useful for an admin view) — callers driving actual
        playback (the Loader) are expected to pass scene_name.
        """
        files = []
        for fpath, fname, scene_dir_name, take_dir_name in _iter_arc_files(scene_name, take_name):
            size = os.path.getsize(fpath)
            # Quick peek at cultivar name and step count
            cultivar = ""
            steps    = 0
            raw = ""
            try:
                with open(fpath, encoding="utf-8") as f:
                    raw = f.read(2000)  # read first 2KB only
                m = re.search(r'agentname="([^"]+)"', raw)
                if m:
                    cultivar = m.group(1)
                steps = len(re.findall(r'<Waypoint ', raw))
            except Exception:
                pass
            # Extract path_name: prefer XML attribute, fall back to filename parse
            path_name = ""
            try:
                pn_match = re.search(r'path_name="([^"]+)"', raw)
                if pn_match:
                    path_name = pn_match.group(1)
            except Exception:
                pass
            if not path_name:
                # Filename parse: arc_{pathName}_{YYYY...}.xml
                base = fname[4:] if fname.startswith("arc_") else fname
                base = base[:-4] if base.endswith(".xml") else base
                ts_match = re.search(r'^(.*?)_(\d{4}[\-:T]\d{2}.*)$', base)
                path_name = ts_match.group(1) if ts_match else base

            # Extract first waypoint position for reset fallback
            first_wp = None
            try:
                m_wp = re.search(r'<Waypoint[^>]*pos_x="([^"]+)"[^>]*pos_y="([^"]+)"[^>]*pos_z="([^"]+)"', raw)
                if m_wp:
                    first_wp = {"pos_x": m_wp.group(1), "pos_y": m_wp.group(2), "pos_z": m_wp.group(3)}
            except Exception:
                pass

            files.append({
                "filename":      fname,
                "size":          size,
                "cultivar":      cultivar,
                "path_name":     path_name,
                # scene_name/take_name come from the directory itself, not a
                # trusted XML attribute — same "scoping is the directory
                # listing" principle as mccf_api.py's arc_playback_list().
                "scene_name":    scene_dir_name,
                "take_name":     take_dir_name,
                "steps_seen":    steps,
                "first_waypoint": first_wp,
                "mtime":         os.path.getmtime(fpath),
            })

        # Dedup: keep only the newest file per (scene, take, path_name) —
        # rescoped from the old global path_name dedup, which would have
        # silently dropped legitimate arcs whenever two different scenes
        # happened to share a path_name. Within one take, still keep only
        # the latest recording of a given path.
        files.sort(key=lambda f: f["mtime"], reverse=True)
        seen_keys: set = set()
        deduped = []
        for entry in files:
            key = (entry["scene_name"], entry["take_name"], entry["path_name"].strip().lower())
            if key not in seen_keys:
                seen_keys.add(key)
                deduped.append(entry)
        return deduped

    def start(self, filename: str, pace: float = DEFAULT_PACE,
              loop: bool = False, auto: bool = True,
              session_id: str = None, scene_name: str = None,
              take_name: str = None) -> dict:
        # The Loader only ever sends a bare filename (see pbPlay() in
        # mccf_x3d_loader.html), so resolve it by searching the nested tree.
        # scene_name/take_name narrow the search when the caller has them —
        # optional, since arc filenames carry a per-second timestamp and are
        # effectively unique in practice even across scenes.
        filepath = None
        for fpath, fname, _sd, _td in _iter_arc_files(scene_name, take_name):
            if fname == filename:
                filepath = fpath
                break
        if filepath is None:
            raise FileNotFoundError(f"Arc file not found under scenes/: {filename}")

        arc_data = parse_arc_file(filepath)
        if not arc_data["waypoints"]:
            raise ValueError(f"No waypoints found in {filename}")

        try:
            with open(filepath, encoding="utf-8") as f:
                arc_xml_str = f.read()
        except Exception:
            arc_xml_str = ""

        # Determine session_id
        sid = (session_id or "").strip()
        if not sid:
            sid = self._session_id_from_file(filename, arc_data)

        with self._lock:
            if sid in self._sessions:
                self._sessions[sid].stop()
            session = PlaybackSession(
                arc_data=arc_data,
                field=self.field,
                pace=pace,
                loop=loop,
                auto=auto,
                chorus_callback=self.chorus_callback,
                arc_xml_str=arc_xml_str,
            )
            self._sessions[sid] = session
            session.start()

        result = session.state()
        result["session_id"] = sid
        return result

    def start_all(self, pace: float = DEFAULT_PACE,
                  loop: bool = False, auto: bool = False,
                  scene_name: str = None, take_name: str = None) -> dict:
        """
        Start all arc files simultaneously, optionally scoped to one scene
        (and take). Uses newest file per (scene, take, path_name) — same
        dedup as list_files(). scene_name should always be passed by the
        Loader now that arcs are scene-nested; omitting it starts every arc
        across every scene at once, which is almost never what "Play All"
        means once more than one scene has recorded arcs.
        """
        files = self.list_files(scene_name=scene_name, take_name=take_name)
        started = {}
        for f in files:
            try:
                state = self.start(
                    filename=f["filename"],
                    pace=pace,
                    loop=loop,
                    auto=auto,
                    session_id=f.get("path_name") or None,
                    scene_name=f.get("scene_name"),
                    take_name=f.get("take_name"),
                )
                sid = state.get("session_id", f.get("path_name", f["filename"]))
                started[sid] = state
            except Exception as e:
                sid = f.get("path_name", f["filename"])
                started[sid] = {"status": "error", "error": str(e)}
        return {"sessions": started, "started": list(started.keys())}

    def _state_unlocked(self, session_id: str = None) -> dict:
        """
        Build state dict WITHOUT acquiring self._lock.
        Called only from methods that already hold the lock.
        """
        if session_id:
            sess = self._sessions.get(session_id)
            if not sess:
                return {"status": "idle", "session_id": session_id,
                        "message": f"No session '{session_id}'."}
            result = sess.state()
            result["session_id"] = session_id
            return result
        all_states = {}
        for sid, sess in self._sessions.items():
            s = sess.state()
            s["session_id"] = sid
            all_states[sid] = s
        active = sum(1 for s in all_states.values()
                     if s.get("status") in ("playing", "paused"))
        return {"sessions": all_states, "active_count": active}

    def state(self, session_id: str = None) -> dict:
        """
        Return state dict.
        session_id=None  → { sessions: {sid: state, ...}, active_count: N }
        session_id=X     → state for session X, or idle if not found.
        """
        with self._lock:
            return self._state_unlocked(session_id)

    def stop(self, session_id: str = None) -> dict:
        """Stop one or all sessions."""
        with self._lock:
            if session_id:
                sess = self._sessions.get(session_id)
                if not sess:
                    return {"status": "idle", "session_id": session_id}
                sess.stop()
                result = sess.state()
                result["session_id"] = session_id
                return result
            for sess in self._sessions.values():
                sess.stop()
            return self._state_unlocked()

    def step(self, session_id: str = None) -> dict:
        """
        Advance one step.
        session_id=None → advance ALL active sessions, return aggregate state.
        session_id=X    → advance session X only.
        """
        with self._lock:
            if session_id:
                sess = self._sessions.get(session_id)
                if not sess:
                    return {"status": "idle", "session_id": session_id,
                            "error": f"No session '{session_id}'"}
                sess.step_forward()
                result = sess.state()
                result["session_id"] = session_id
                return result
            for sess in self._sessions.values():
                if sess._status == PlaybackSession.STATUS_PLAYING:
                    sess.step_forward()
            return self._state_unlocked()

    def reset(self, session_id: str = None) -> dict:
        """Reset one or all sessions."""
        with self._lock:
            if session_id:
                sess = self._sessions.get(session_id)
                if not sess:
                    return {"status": "idle", "session_id": session_id}
                sess.reset()
                result = sess.state()
                result["session_id"] = session_id
                return result
            for sess in self._sessions.values():
                sess.reset()
            return self._state_unlocked()


# ---------------------------------------------------------------------------
# Flask Blueprint
# ---------------------------------------------------------------------------

playback_bp = Blueprint("playback_v3", __name__)

def _mgr() -> PlaybackManager:
    return playback_bp.manager


@playback_bp.route("/arc/playback", methods=["GET"])
def list_playback_files():
    """
    List available arc files.
    ?scene_name=X          — scope to one scene's arcs/ tree
    ?scene_name=X&take_name=Y — scope to one scene, one take
    Omitting scene_name lists every arc across every scene.
    """
    scene_name = request.args.get("scene_name", "").strip() or None
    take_name  = request.args.get("take_name", "").strip() or None
    return jsonify({
        "files":       _mgr().list_files(scene_name=scene_name, take_name=take_name),
        "scenes_dir":  _scenes_root(),
    })


@playback_bp.route("/arc/playback/start", methods=["POST"])
def start_playback():
    """
    Start playback of one arc export file.

    Body: {
        "file":       "arc_Cindy_2026-04-26162557.xml",  // required
        "session_id": "Cindy",    // optional; defaults to path_name
        "pace":       3.0,
        "loop":       false,
        "auto":       false       // false = X3D segmentArrived drives steps
    }
    """
    data = request.get_json() or {}
    filename = data.get("file")
    if not filename:
        return jsonify({"error": "file required"}), 400

    pace       = float(data.get("pace", DEFAULT_PACE))
    loop       = bool(data.get("loop", False))
    auto       = bool(data.get("auto", False))
    session_id = data.get("session_id", "").strip() or None

    try:
        state = _mgr().start(filename, pace=pace, loop=loop,
                             auto=auto, session_id=session_id)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Playback start failed: {e}"}), 500

    return jsonify({"status": "started", "state": state})


@playback_bp.route("/arc/playback/start/all", methods=["POST"])
def start_all_playback():
    """
    Start ALL arc files simultaneously, optionally scoped to one scene.

    Body (optional): { "pace": 3.0, "loop": false, "auto": false,
                        "scene_name": "newDirectoryTestScene",
                        "take_name": "2026-07-11T2042" }
    Returns: { sessions: { session_id: state, ... }, started: [...] }
    """
    data = request.get_json() or {}
    pace = float(data.get("pace", DEFAULT_PACE))
    loop = bool(data.get("loop", False))
    auto = bool(data.get("auto", False))
    scene_name = (data.get("scene_name") or "").strip() or None
    take_name  = (data.get("take_name") or "").strip() or None

    result = _mgr().start_all(pace=pace, loop=loop, auto=auto,
                               scene_name=scene_name, take_name=take_name)
    return jsonify(result)


@playback_bp.route("/arc/playback/state", methods=["GET"])
def playback_state():
    """
    Get playback state.
    ?session_id=X  → state for session X only.
    (no param)     → { sessions: {sid: state, ...}, active_count: N }
    """
    session_id = request.args.get("session_id", "").strip() or None
    return jsonify(_mgr().state(session_id))


@playback_bp.route("/arc/playback/state/<session_id>", methods=["GET"])
def playback_state_by_id(session_id):
    """Get state for a specific session."""
    return jsonify(_mgr().state(session_id))


@playback_bp.route("/arc/playback/step", methods=["POST"])
def playback_step():
    """
    Advance one step.
    Body: { "session_id": "Cindy" }  → step session Cindy only.
    Body: {}                          → step ALL active sessions.
    """
    data = request.get_json() or {}
    session_id = data.get("session_id", "").strip() or None
    return jsonify(_mgr().step(session_id))


@playback_bp.route("/arc/playback/stop", methods=["POST"])
def stop_playback():
    """
    Stop playback.
    Body: { "session_id": "Cindy" }  → stop session Cindy only.
    Body: {}                          → stop ALL sessions.
    """
    data = request.get_json() or {}
    session_id = data.get("session_id", "").strip() or None
    return jsonify(_mgr().stop(session_id))


@playback_bp.route("/arc/playback/reset", methods=["POST"])
def reset_playback():
    """
    Reset to first waypoint.
    Body: { "session_id": "Cindy" }  → reset session Cindy only.
    Body: {}                          → reset ALL sessions.
    """
    data = request.get_json() or {}
    session_id = data.get("session_id", "").strip() or None
    return jsonify(_mgr().reset(session_id))


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
