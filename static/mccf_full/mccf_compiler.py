"""
MCCF Text-to-Waypoint Compiler
================================
Converts scene prose into a complete X3D interpolator network:
  - TimeSensor (the conductor)
  - PositionInterpolator (spatial arc)
  - OrientationInterpolator (facing direction)
  - ScalarInterpolator (affect-driven float fields)
  - ROUTE statements connecting everything

Design notes:
  A creator typically routes a Viewpoint to a point sampler
  that writes XYZ to text. We have the waypoints.
  What we were missing was the TimeSensor.

  The TimeSensor is not just timing — it is dramaturgy.
  cycleInterval = total scene duration
  key[] = when each waypoint is reached (0.0-1.0 fraction)
  keyValue[] = what value is present at each key

  Interpolation curve shape is the expressive element:
  - EASE (smooth): grief, reflection, intimacy
  - LINEAR: anger, urgency, mechanical
  - SPIKE (fast-in slow-out): surprise, impact
  - SUSTAIN (slow-in fast-out): anticipation, release
  - OSCILLATE: conflict, indecision

  These are not aesthetic choices — they are affective parameters.
  The MCCF arousal and valence values drive curve selection.

Pipeline:
  Scene prose
      ↓ LLM extraction (structured JSON)
  SceneScript
      ↓ compile_scene()
  X3D interpolator network
      ↓ ROUTE statements
  Live X3D scene
"""

import json
import math
import time
import asyncio
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ScriptedBeat:
    """
    A single dramatic beat extracted from scene prose.
    Maps to one waypoint in the spatial arc.
    """
    name: str
    label: str                    # narrative label ("crosses to window")
    position: tuple               # (x, y, z) world coordinates
    orientation: tuple            # (ax, ay, az, angle) axis-angle rotation
    dwell_seconds: float          # how long the character holds this position
    approach_seconds: float       # travel time from previous beat
    emotional_register: str       # "grief" | "anger" | "joy" | "fear" | "neutral" | "conflict"
    arousal: float                # 0-1 from scene context
    valence: float                # -1 to 1 from scene context
    zone_type: str                # "garden" | "library" | "intimate" etc
    dialogue: Optional[str] = None  # optional spoken text at this beat
    action: Optional[str] = None    # optional stage direction


@dataclass
class SceneScript:
    """
    Complete dramatic scene extracted from prose.
    Contains all beats in sequence with character assignment.
    """
    scene_name: str
    character_name: str
    cultivar_name: str            # maps to MCCF constitutional cultivar
    beats: list                   # list of ScriptedBeat
    total_duration: float         # computed from beats
    loop: bool = False
    description: str = ""


@dataclass
class InterpolatorNetwork:
    """
    Complete X3D interpolator network for one character's scene arc.
    Ready to emit as X3D XML.
    """
    character_name: str
    timer_def: str                # DEF name for TimeSensor
    position_def: str             # DEF name for PositionInterpolator
    orientation_def: str          # DEF name for OrientationInterpolator
    scalar_defs: dict             # channel name → DEF name for ScalarInterpolators
    cycle_interval: float         # TimeSensor.cycleInterval in seconds
    keys: list                    # shared key fractions [0.0 ... 1.0]
    position_values: list         # list of (x,y,z) tuples
    orientation_values: list      # list of (ax,ay,az,angle) tuples
    scalar_values: dict           # channel → list of floats
    beat_labels: list             # narrative labels per key
    routes: list                  # ROUTE strings


# ---------------------------------------------------------------------------
# Interpolation curve shapes
# ---------------------------------------------------------------------------

CURVE_PROFILES = {
    # (easing_in, easing_out) — 0=linear, 1=full ease
    "LINEAR":   (0.0, 0.0),
    "EASE":     (0.5, 0.5),   # grief, reflection, intimacy
    "EASE_IN":  (0.5, 0.0),   # anticipation, building
    "EASE_OUT": (0.0, 0.5),   # release, arrival
    "SPIKE":    (0.8, 0.1),   # surprise, impact
    "SUSTAIN":  (0.1, 0.8),   # held tension, slow release
}

def emotional_to_curve(register: str, arousal: float, valence: float) -> str:
    """
    Map emotional register + arousal/valence to interpolation curve.
    This is where affect becomes motion quality.
    """
    if register == "grief":
        return "EASE"           # slow, weighted movement
    if register == "anger":
        return "LINEAR"         # direct, unmodulated
    if register == "joy":
        return "EASE_OUT"       # buoyant arrival
    if register == "fear":
        return "SPIKE"          # fast approach, frozen hold
    if register == "conflict":
        return "SUSTAIN"        # reluctant, held tension
    if register == "intimacy":
        return "EASE"           # slow, deliberate approach
    if register == "surprise":
        return "SPIKE"
    if register == "anticipation":
        return "EASE_IN"

    # Fallback: derive from arousal/valence
    if arousal > 0.7:
        return "LINEAR" if valence < 0 else "EASE_OUT"
    if arousal < 0.3:
        return "EASE"
    return "EASE"


def apply_curve(t: float, curve: str) -> float:
    """
    Apply easing curve to linear fraction t (0-1).
    Returns modified fraction for use as interpolation weight.
    Used to generate intermediate key frames.
    """
    profile = CURVE_PROFILES.get(curve, CURVE_PROFILES["EASE"])
    ease_in, ease_out = profile

    # Cubic bezier approximation
    # ease_in controls acceleration from start
    # ease_out controls deceleration to end
    if ease_in == 0 and ease_out == 0:
        return t  # pure linear

    # Smoothstep blend
    smooth = t * t * (3 - 2 * t)
    if ease_in > 0 and ease_out > 0:
        return smooth * (ease_in + ease_out) / 2 + t * (1 - (ease_in + ease_out) / 2)
    if ease_in > 0:
        return t + (smooth - t) * ease_in
    return t + (smooth - t) * ease_out


# ---------------------------------------------------------------------------
# Timing calculator
# ---------------------------------------------------------------------------

def compute_keys(beats: list) -> tuple:
    """
    Convert beat approach/dwell times to normalized key fractions.

    Returns:
        keys: list of floats 0.0-1.0 (one per beat)
        total_duration: float seconds
        beat_times: list of floats (absolute seconds per beat)

    Structure per beat:
        [approach_seconds of travel][dwell_seconds of hold]

    The key fires at the START of the dwell — the moment of arrival.
    """
    total = sum(b.approach_seconds + b.dwell_seconds for b in beats)
    if total <= 0:
        total = len(beats) * 4.0  # fallback: 4 seconds per beat

    keys = []
    beat_times = []
    elapsed = 0.0

    for beat in beats:
        elapsed += beat.approach_seconds  # travel to this beat
        beat_times.append(elapsed)
        keys.append(round(elapsed / total, 6))
        elapsed += beat.dwell_seconds     # hold at this beat

    # Normalize to ensure last key <= 1.0
    if keys and keys[-1] > 1.0:
        scale = 1.0 / keys[-1]
        keys = [round(k * scale, 6) for k in keys]

    # Ensure first key is 0.0
    if keys and keys[0] > 0:
        keys = [0.0] + keys
        beat_times = [0.0] + beat_times

    return keys, total, beat_times


# ---------------------------------------------------------------------------
# Affect scalar mapping
# ---------------------------------------------------------------------------

def beat_to_scalars(beat: ScriptedBeat) -> dict:
    """
    Map a ScriptedBeat's emotional state to scalar channel values.
    These drive ScalarInterpolators connected to MCCF affect parameters.

    Returns dict of channel_name → float (0.0-1.0 or -1.0-1.0)
    """
    return {
        "arousal":    round(max(0.0, min(1.0, beat.arousal)), 4),
        "valence":    round(max(-1.0, min(1.0, beat.valence)), 4),
        # Derive E/B/P/S from emotional register + arousal/valence
        "E": round(max(0.0, min(1.0,
            0.5 + beat.arousal * 0.3 +
            (0.1 if beat.emotional_register in ["grief","intimacy","joy"] else 0)
        )), 4),
        "B": round(max(0.0, min(1.0,
            0.5 + (0.2 if beat.emotional_register in ["anger","conflict"] else 0) -
            (0.1 if beat.emotional_register in ["grief","fear"] else 0)
        )), 4),
        "P": round(max(0.0, min(1.0,
            0.5 - beat.arousal * 0.2 +
            (0.2 if beat.emotional_register in ["conflict","anticipation"] else 0)
        )), 4),
        "S": round(max(0.0, min(1.0,
            0.5 + (0.3 if beat.emotional_register == "intimacy" else 0) -
            (0.2 if beat.emotional_register in ["anger","fear"] else 0)
        )), 4),
        # Regulation: high arousal → lower regulation (less filtered)
        "regulation": round(max(0.2, min(1.0, 1.0 - beat.arousal * 0.4)), 4)
    }


# ---------------------------------------------------------------------------
# Core compiler
# ---------------------------------------------------------------------------

def compile_scene(script: SceneScript) -> InterpolatorNetwork:
    """
    Compile a SceneScript into a complete X3D InterpolatorNetwork.

    This is the hat trick: story beats → TimeSensor + interpolators.
    """
    name = script.character_name.replace(" ", "_")
    scene = script.scene_name.replace(" ", "_")

    # DEF names
    timer_def    = f"Timer_{name}_{scene}"
    pos_def      = f"PosInterp_{name}_{scene}"
    ori_def      = f"OriInterp_{name}_{scene}"
    scalar_defs  = {
        ch: f"Scalar_{ch}_{name}_{scene}"
        for ch in ["arousal", "valence", "E", "B", "P", "S", "regulation"]
    }

    # Compute timing
    keys, total_duration, beat_times = compute_keys(script.beats)

    # If first beat has no approach time, insert a hold at position 0
    beats = script.beats
    if not beats:
        raise ValueError("SceneScript has no beats")

    # Build interpolator value arrays
    position_values    = []
    orientation_values = []
    scalar_value_arrays = {ch: [] for ch in scalar_defs}
    beat_labels        = []
    curve_labels       = []

    for beat in beats:
        position_values.append(beat.position)
        orientation_values.append(beat.orientation)
        scalars = beat_to_scalars(beat)
        for ch in scalar_value_arrays:
            scalar_value_arrays[ch].append(scalars.get(ch, 0.5))
        beat_labels.append(beat.label)
        curve_labels.append(
            emotional_to_curve(beat.emotional_register, beat.arousal, beat.valence)
        )

    # Pad keys to match values if needed
    while len(keys) < len(position_values):
        keys.append(1.0)
    keys = keys[:len(position_values)]

    # Build ROUTE statements
    avatar_def = f"Avatar_{name}"
    mat_def    = f"Mat_{name}_Body"
    routes = [
        # Time → interpolators
        f'<ROUTE fromNode="{timer_def}" fromField="fraction_changed" '
        f'toNode="{pos_def}" toField="set_fraction"/>',

        f'<ROUTE fromNode="{timer_def}" fromField="fraction_changed" '
        f'toNode="{ori_def}" toField="set_fraction"/>',

        # Position → avatar transform
        f'<ROUTE fromNode="{pos_def}" fromField="value_changed" '
        f'toNode="{avatar_def}" toField="translation"/>',

        # Orientation → avatar transform
        f'<ROUTE fromNode="{ori_def}" fromField="value_changed" '
        f'toNode="{avatar_def}" toField="rotation"/>',
    ]

    # Scalar interpolator routes → MCCF bridge
    for ch, def_name in scalar_defs.items():
        routes.append(
            f'<ROUTE fromNode="{timer_def}" fromField="fraction_changed" '
            f'toNode="{def_name}" toField="set_fraction"/>'
        )
        routes.append(
            f'<ROUTE fromNode="{def_name}" fromField="value_changed" '
            f'toNode="MCCF_Bridge" toField="{ch}_{name}"/>'
        )

    return InterpolatorNetwork(
        character_name=script.character_name,
        timer_def=timer_def,
        position_def=pos_def,
        orientation_def=ori_def,
        scalar_defs=scalar_defs,
        cycle_interval=total_duration,
        keys=keys,
        position_values=position_values,
        orientation_values=orientation_values,
        scalar_values=scalar_value_arrays,
        beat_labels=beat_labels,
        routes=routes
    )


# ---------------------------------------------------------------------------
# X3D emitter
# ---------------------------------------------------------------------------

def emit_x3d(network: InterpolatorNetwork,
             loop: bool = False,
             enabled: bool = True) -> str:
    """
    Emit a complete X3D interpolator network as XML string.
    Ready to paste into an X3D scene or write to a .x3d file.
    """
    lines = []
    name = network.character_name.replace(" ", "_")

    lines.append(f'\n<!-- ═══ {network.character_name} — Scene Arc ═══ -->')
    lines.append(f'<!-- Total duration: {network.cycle_interval:.1f}s -->')
    lines.append(f'<!-- Beats: {len(network.keys)} -->')
    for i, label in enumerate(network.beat_labels):
        lines.append(
            f'<!--   Beat {i+1}: {label} '
            f'(key={network.keys[i]:.4f}, '
            f't={network.cycle_interval * network.keys[i]:.1f}s) -->'
        )
    lines.append('')

    # TimeSensor — the conductor
    lines.append(f'<TimeSensor DEF="{network.timer_def}"')
    lines.append(f'  cycleInterval="{network.cycle_interval:.3f}"')
    lines.append(f'  loop="{str(loop).lower()}"')
    lines.append(f'  enabled="{str(enabled).lower()}"/>')
    lines.append('')

    # PositionInterpolator
    pos_keys = " ".join(f"{k:.6f}" for k in network.keys)
    pos_vals = " ".join(
        f"{p[0]:.4f} {p[1]:.4f} {p[2]:.4f}"
        for p in network.position_values
    )
    lines.append(f'<PositionInterpolator DEF="{network.position_def}"')
    lines.append(f'  key="{pos_keys}"')
    lines.append(f'  keyValue="{pos_vals}"/>')
    lines.append('')

    # OrientationInterpolator
    ori_keys = pos_keys  # same timing
    ori_vals = " ".join(
        f"{o[0]:.4f} {o[1]:.4f} {o[2]:.4f} {o[3]:.4f}"
        for o in network.orientation_values
    )
    lines.append(f'<OrientationInterpolator DEF="{network.orientation_def}"')
    lines.append(f'  key="{ori_keys}"')
    lines.append(f'  keyValue="{ori_vals}"/>')
    lines.append('')

    # ScalarInterpolators — one per affect channel
    for ch, def_name in network.scalar_defs.items():
        vals = " ".join(f"{v:.4f}" for v in network.scalar_values[ch])
        lines.append(f'<ScalarInterpolator DEF="{def_name}"')
        lines.append(f'  key="{pos_keys}"')
        lines.append(f'  keyValue="{vals}"/>')
        lines.append(f'<!-- {ch}: {vals} -->')
        lines.append('')

    # ROUTE statements
    lines.append('<!-- ROUTES -->')
    for route in network.routes:
        lines.append(route)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM extraction — prose → SceneScript
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """You are a scene compiler for an X3D theatre system.

Extract the dramatic beats from this scene description and return ONLY valid JSON.
No preamble, no markdown fences, just the JSON object.

For each beat identify:
- name: short identifier (no spaces)
- label: narrative stage direction ("crosses to window", "turns away", etc)
- position: [x, y, z] world coordinates. Use the scene's spatial logic.
  Stage left = negative X, stage right = positive X,
  upstage = negative Z, downstage = positive Z, Y=0 is floor.
- orientation: [axis_x, axis_y, axis_z, angle_radians] facing direction.
  Facing audience = [0,1,0,0]. Turn left = [0,1,0,1.57]. Turn right = [0,1,0,-1.57].
- dwell_seconds: how long the character holds this position
- approach_seconds: travel time from previous beat (0 for first beat)
- emotional_register: one of: grief, anger, joy, fear, conflict, intimacy, surprise, anticipation, neutral
- arousal: 0.0-1.0 (intensity of activation)
- valence: -1.0 to 1.0 (negative=bad, positive=good)
- zone_type: one of: garden, library, intimate, forum, authority, threat, sacred, neutral
- dialogue: exact words spoken at this beat (null if none)
- action: physical action description (null if none)

Return this JSON structure:
{
  "scene_name": "...",
  "character_name": "...",
  "cultivar_name": "...",  // one of: The Witness, The Steward, The Advocate, The Bridge, The Archivist, The Gardener, The Threshold
  "description": "...",
  "loop": false,
  "beats": [ ... ]
}

Choose cultivar based on the character's dominant disposition in this scene.
Be precise about timing — dwell and approach times should feel right for the emotional register.
Grief moves slowly. Anger moves quickly. Fear freezes.
"""

async def extract_from_prose(
    scene_prose: str,
    adapter_id: str = "stub",
    api_key: str = "",
    model: str = ""
) -> SceneScript:
    """
    Use LLM to extract SceneScript from scene prose.
    Returns a SceneScript ready for compile_scene().
    """
    from mccf_llm import AdapterRegistry

    adapter = AdapterRegistry.get(adapter_id, api_key=api_key, model=model)

    messages = [{"role": "user", "content": scene_prose}]
    neutral_persona = {
        "name": "Scene Compiler",
        "role": "agent",
        "description": "Extracts dramatic beats from scene prose. Returns only JSON."
    }
    neutral_context = {
        "arousal": 0.5, "valence": 0.0,
        "regulation_state": 1.0,
        "coherence_scores": {},
        "active_zones": [], "zone_pressure": {}
    }

    full = ""
    async for token in adapter.complete(
        messages=messages,
        affective_context=neutral_context,
        persona=neutral_persona,
        params={"max_tokens": 1500, "temperature": 0.2}
    ):
        full += token

    return _parse_scene_script(full)


def _parse_scene_script(raw: str) -> SceneScript:
    """Parse LLM JSON output into SceneScript."""
    clean = raw.strip()
    if "```" in clean:
        parts = clean.split("```")
        for part in parts:
            if part.strip().startswith("{"):
                clean = part.strip()
                break

    try:
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        # Return a minimal fallback script
        return _fallback_script(f"JSON parse error: {e}")

    beats = []
    for b in data.get("beats", []):
        try:
            beat = ScriptedBeat(
                name=str(b.get("name", f"beat_{len(beats)}")),
                label=str(b.get("label", "moves")),
                position=tuple(float(v) for v in b.get("position", [0,0,0])),
                orientation=tuple(float(v) for v in b.get("orientation", [0,1,0,0])),
                dwell_seconds=float(b.get("dwell_seconds", 3.0)),
                approach_seconds=float(b.get("approach_seconds", 2.0)),
                emotional_register=str(b.get("emotional_register", "neutral")),
                arousal=float(b.get("arousal", 0.5)),
                valence=float(b.get("valence", 0.0)),
                zone_type=str(b.get("zone_type", "neutral")),
                dialogue=b.get("dialogue"),
                action=b.get("action")
            )
            beats.append(beat)
        except (KeyError, TypeError, ValueError):
            continue

    if not beats:
        return _fallback_script("No valid beats extracted")

    return SceneScript(
        scene_name=str(data.get("scene_name", "scene")),
        character_name=str(data.get("character_name", "Character")),
        cultivar_name=str(data.get("cultivar_name", "The Threshold")),
        beats=beats,
        total_duration=sum(b.approach_seconds + b.dwell_seconds for b in beats),
        loop=bool(data.get("loop", False)),
        description=str(data.get("description", ""))
    )


def _fallback_script(reason: str) -> SceneScript:
    """Minimal fallback when extraction fails."""
    return SceneScript(
        scene_name="fallback",
        character_name="Character",
        cultivar_name="The Threshold",
        beats=[
            ScriptedBeat(
                name="center", label="stands at center",
                position=(0.0, 0.0, 0.0),
                orientation=(0.0, 1.0, 0.0, 0.0),
                dwell_seconds=4.0, approach_seconds=0.0,
                emotional_register="neutral",
                arousal=0.5, valence=0.0, zone_type="neutral"
            )
        ],
        total_duration=4.0,
        description=f"Fallback script: {reason}"
    )


# ---------------------------------------------------------------------------
# Full pipeline — prose → X3D string
# ---------------------------------------------------------------------------

async def prose_to_x3d(
    scene_prose: str,
    adapter_id: str = "stub",
    api_key: str = "",
    model: str = ""
) -> tuple:
    """
    Complete pipeline: scene prose → X3D interpolator network.

    Returns (x3d_string, scene_script, interpolator_network)
    so the caller has access to all intermediate representations.
    """
    script  = await extract_from_prose(scene_prose, adapter_id, api_key, model)
    network = compile_scene(script)
    x3d     = emit_x3d(network, loop=script.loop)
    return x3d, script, network


# ---------------------------------------------------------------------------
# Flask API endpoints
# ---------------------------------------------------------------------------

def make_compiler_api(field_ref=None):
    from flask import Blueprint, request, jsonify
    import asyncio

    compiler_bp = Blueprint('compiler', __name__)

    @compiler_bp.route('/compile/prose', methods=['POST'])
    def compile_prose():
        """
        POST scene prose, receive X3D interpolator network.

        Body:
        {
            "prose":      "Scene description...",
            "adapter_id": "anthropic",
            "api_key":    "sk-...",
            "model":      ""
        }

        Returns:
        {
            "x3d":     "<!-- X3D XML string -->",
            "script":  { SceneScript as dict },
            "network": { InterpolatorNetwork summary }
        }
        """
        data       = request.get_json()
        prose      = data.get("prose", "")
        adapter_id = data.get("adapter_id", "stub")
        api_key    = data.get("api_key", "")
        model      = data.get("model", "")

        if not prose.strip():
            return jsonify({"error": "prose required"}), 400

        loop = asyncio.new_event_loop()
        try:
            x3d, script, network = loop.run_until_complete(
                prose_to_x3d(prose, adapter_id, api_key, model)
            )
        finally:
            loop.close()

        return jsonify({
            "x3d": x3d,
            "script": {
                "scene_name":      script.scene_name,
                "character_name":  script.character_name,
                "cultivar_name":   script.cultivar_name,
                "total_duration":  script.total_duration,
                "beat_count":      len(script.beats),
                "description":     script.description,
                "beats": [
                    {
                        "name":               b.name,
                        "label":              b.label,
                        "position":           list(b.position),
                        "dwell_seconds":      b.dwell_seconds,
                        "approach_seconds":   b.approach_seconds,
                        "emotional_register": b.emotional_register,
                        "arousal":            b.arousal,
                        "valence":            b.valence,
                        "dialogue":           b.dialogue,
                        "action":             b.action
                    }
                    for b in script.beats
                ]
            },
            "network": {
                "timer_def":      network.timer_def,
                "cycle_interval": network.cycle_interval,
                "keys":           network.keys,
                "beat_labels":    network.beat_labels
            }
        })

    @compiler_bp.route('/compile/direct', methods=['POST'])
    def compile_direct():
        """
        POST a pre-structured SceneScript (no LLM needed),
        receive X3D interpolator network.
        Useful when beats are already known from MCCF waypoint editor.
        """
        data = request.get_json()
        try:
            beats = [
                ScriptedBeat(
                    name=b["name"],
                    label=b["label"],
                    position=tuple(b["position"]),
                    orientation=tuple(b.get("orientation", [0,1,0,0])),
                    dwell_seconds=float(b.get("dwell_seconds", 3.0)),
                    approach_seconds=float(b.get("approach_seconds", 2.0)),
                    emotional_register=b.get("emotional_register", "neutral"),
                    arousal=float(b.get("arousal", 0.5)),
                    valence=float(b.get("valence", 0.0)),
                    zone_type=b.get("zone_type", "neutral"),
                    dialogue=b.get("dialogue"),
                    action=b.get("action")
                )
                for b in data.get("beats", [])
            ]
            script = SceneScript(
                scene_name=data.get("scene_name", "scene"),
                character_name=data.get("character_name", "Character"),
                cultivar_name=data.get("cultivar_name", "The Threshold"),
                beats=beats,
                total_duration=sum(b.approach_seconds + b.dwell_seconds for b in beats),
                loop=data.get("loop", False),
                description=data.get("description", "")
            )
            network = compile_scene(script)
            x3d     = emit_x3d(network, loop=script.loop)
            return jsonify({"x3d": x3d, "cycle_interval": network.cycle_interval})
        except (KeyError, TypeError, ValueError) as e:
            return jsonify({"error": str(e)}), 400

    @compiler_bp.route('/compile/waypoints', methods=['POST'])
    def compile_from_waypoints():
        """
        Convert MCCF waypoints (already in the scene graph) directly
        to a TimeSensor + interpolator network.
        Bridges the waypoint editor to the animation compiler.

        Body:
        {
            "character_name": "Alice",
            "cultivar_name":  "The Steward",
            "waypoint_names": ["W1_COMFORT_ZONE", "W2_FIRST_FRICTION", ...],
            "arc_data":       [ ... ]  // from /path/<name>/arc endpoint
        }
        """
        data           = request.get_json()
        character_name = data.get("character_name", "Character")
        cultivar_name  = data.get("cultivar_name", "The Threshold")
        arc_data       = data.get("arc_data", [])

        if not arc_data:
            return jsonify({"error": "arc_data required"}), 400

        # Convert arc steps to ScriptedBeats
        beats = []
        for i, step in enumerate(arc_data):
            pos = step.get("position", [0, 0, 0])
            ch  = step.get("channel_state", {})

            # Derive emotional register from channel state
            E = ch.get("E", 0.5)
            B = ch.get("B", 0.5)
            valence_proxy = (ch.get("S", 0.5) - 0.5) * 2

            if E > 0.7:
                register = "grief" if valence_proxy < 0 else "joy"
            elif B > 0.7:
                register = "conflict" if E > 0.5 else "neutral"
            else:
                register = "neutral"

            beat = ScriptedBeat(
                name=step.get("waypoint", f"beat_{i}"),
                label=step.get("label", f"Station {i+1}"),
                position=(float(pos[0]), float(pos[1]), float(pos[2])),
                orientation=(0.0, 1.0, 0.0, 0.0),
                dwell_seconds=3.0,
                approach_seconds=0.0 if i == 0 else 2.5,
                emotional_register=register,
                arousal=float(E),
                valence=float(valence_proxy),
                zone_type=step.get("zones_active", ["neutral"])[0]
                          if step.get("zones_active") else "neutral"
            )
            beats.append(beat)

        script = SceneScript(
            scene_name="constitutional_arc",
            character_name=character_name,
            cultivar_name=cultivar_name,
            beats=beats,
            total_duration=sum(b.approach_seconds + b.dwell_seconds for b in beats),
            loop=False,
            description=f"{character_name} constitutional arc"
        )

        network = compile_scene(script)
        x3d     = emit_x3d(network, loop=False)

        return jsonify({
            "x3d":            x3d,
            "cycle_interval": network.cycle_interval,
            "beat_count":     len(beats),
            "keys":           network.keys
        })

    return compiler_bp


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    # Example: a scene from The Garden
    SAMPLE_PROSE = """
    The Lady crosses from the garden entrance toward the council chamber door.
    She is carrying news that will not be welcome.

    She pauses at the fountain — a moment of gathering herself,
    the water sound covering her stillness.

    Then she moves to the threshold of the chamber, stops,
    and turns back once toward the garden — a last look
    at the open air before entering the confined space of authority.

    She faces the door, takes a breath, and enters.
    """

    async def demo():
        print("Text-to-Waypoint Compiler Demo")
        print("=" * 50)

        # Using stub adapter for demo (no API key needed)
        x3d, script, network = await prose_to_x3d(
            SAMPLE_PROSE,
            adapter_id="stub"
        )

        print(f"\nScene: {script.scene_name}")
        print(f"Character: {script.character_name}")
        print(f"Cultivar: {script.cultivar_name}")
        print(f"Duration: {script.total_duration:.1f}s")
        print(f"Beats: {len(script.beats)}")
        print(f"\nKeys: {network.keys}")
        print(f"\nX3D output:\n{x3d}")

    asyncio.run(demo())
