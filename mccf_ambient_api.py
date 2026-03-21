"""
MCCF Ambient Sync API
======================
Single endpoint that closes all perceptual loops simultaneously:

  POST /ambient/sync
    → updates MCCF field from voice/sensor data
    → computes music parameters
    → computes lighting state
    → returns all three in one response

  GET  /lighting/state    — current computed lighting
  GET  /lighting/scalars  — flat scalar dict for X3D routing
  GET  /lighting/x3d      — X3D fragment for current lighting
  GET  /ambient/state     — combined music + lighting + field state

This is the unified output bus. One coherence state.
Three simultaneous perceptual channels: sound, light, voice.
"""

import json
import time
from flask import Blueprint, request, jsonify

ambient_bp = Blueprint('ambient', __name__)

# Injected after registration:
#   ambient_bp.field   = CoherenceField
#   ambient_bp.scene   = SceneGraph
#   ambient_bp.registry = AdapterRegistry

_last_lighting = None
_last_music    = None


def _get_field():  return ambient_bp.field
def _get_scene():
    return ambient_bp.scene if hasattr(ambient_bp, 'scene') else None


# ---------------------------------------------------------------------------
# Ambient sync — the unified output bus
# ---------------------------------------------------------------------------

@ambient_bp.route('/ambient/sync', methods=['POST'])
def ambient_sync():
    """
    Master sync endpoint. Called by:
    - Voice agent on each utterance
    - X3D scene on sensor events
    - Ambient engine on its poll timer

    Body (all optional — uses last known state for missing fields):
    {
        "from_agent":    "Alice",
        "to_agent":      "AI",
        "position":      [x, y, z],
        "sensor_data":   { distance, dwell, velocity, gaze_angle },
        "audio_features": { pitch_variance, energy, ... },
        "record_episode": false,
        "outcome_delta":  0.0,
        "valence":        0.0
    }

    Returns:
    {
        "field":    { matrix, agents, echo_risks },
        "lighting": { LightState scalar dict },
        "music":    { music parameters },
        "voice":    { TTS voice params },
        "timestamp": float
    }
    """
    from mccf_lighting import compute_lighting, lighting_scalars
    from mccf_llm import affect_to_voice_params, prosody_to_channel_vector

    data       = request.get_json() or {}
    from_name  = data.get("from_agent")
    to_name    = data.get("to_agent")
    position   = data.get("position", [0, 0, 0])

    field = _get_field()
    scene = _get_scene()

    # Update field from sensor data if provided
    if from_name and to_name and from_name in field.agents and to_name in field.agents:
        sensor_data = data.get("sensor_data")
        audio_feats = data.get("audio_features")

        if sensor_data:
            from mccf_api import compute_channel_vector
            cv = compute_channel_vector(sensor_data)
            if scene:
                cv = scene.apply_zone_pressure(cv, tuple(position))
            field.interact(from_name, to_name, cv)

        if audio_feats:
            cv_audio = prosody_to_channel_vector(audio_feats)
            field.interact(from_name, to_name, cv_audio, mutual=False)

    # Record episode to zone if requested
    if data.get("record_episode") and scene and from_name:
        from mccf_zones import ResonanceEpisode
        ep = ResonanceEpisode(
            timestamp=time.time(),
            agents_present=[from_name, to_name] if to_name else [from_name],
            outcome_delta=float(data.get("outcome_delta", 0.0)),
            emotional_intensity=0.5,
            valence=float(data.get("valence", 0.0)),
            label=data.get("episode_label", "sync")
        )
        scene.record_episode_at(tuple(position), ep)

    # Build affective context
    affective_context = _build_affective_context(from_name or "", position)

    # Compute lighting
    field_dict = {
        "agents": {
            n: {
                "weights": a.weights,
                "role": a.role,
                "regulation": a._affect_regulation
            }
            for n, a in field.agents.items()
        },
        "matrix": field.field_matrix(),
        "echo_chamber_risks": field.echo_chamber_risk()
    }
    scene_dict = scene.scene_summary() if scene else {"zones": []}

    light_state = compute_lighting(affective_context, field_dict, scene_dict)
    scalars     = lighting_scalars(light_state)
    global _last_lighting
    _last_lighting = scalars

    # Compute music parameters
    music = _compute_music_params(affective_context, scene_dict)
    global _last_music
    _last_music = music

    # Compute voice params
    voice_params = affect_to_voice_params(affective_context)

    return jsonify({
        "field":     field_dict,
        "lighting":  scalars,
        "music":     music,
        "voice":     voice_params,
        "affect":    affective_context,
        "timestamp": time.time()
    })


def _build_affective_context(agent_name: str, position: list) -> dict:
    """Build unified affective context from field + scene."""
    field = _get_field()
    scene = _get_scene()

    agent  = field.agents.get(agent_name)
    matrix = field.field_matrix()
    row    = matrix.get(agent_name, {})

    coherence_scores = {k: v for k, v in row.items() if k != agent_name}
    avg_coh = sum(coherence_scores.values()) / max(1, len(coherence_scores))

    pos = tuple(position)
    zone_pressure = scene.zone_pressure_at(pos) if scene else {}
    active_zones  = [
        {"name": z.name, "type": z.zone_type, "color": z.color}
        for z in scene.active_zones_at(pos)
    ] if scene else []

    reg = agent._affect_regulation if agent else 1.0

    # Arousal: E channel pressure + inverse regulation
    E_pressure = zone_pressure.get("E", 0.0)
    arousal    = max(0, min(1, 0.5 + E_pressure + (1 - reg) * 0.2))

    # Valence: coherence + social zone pressure
    S_pressure = zone_pressure.get("S", 0.0)
    valence    = round((avg_coh - 0.5) * 1.5 + S_pressure * 0.3, 3)

    # Engagement: B channel + average coherence
    B_pressure = zone_pressure.get("B", 0.0)
    engagement = max(0, min(1, avg_coh * 0.6 + B_pressure * 0.3 + 0.3))

    return {
        "agent_name":         agent_name,
        "coherence_scores":   coherence_scores,
        "avg_coherence":      round(avg_coh, 4),
        "active_zones":       active_zones,
        "zone_pressure":      zone_pressure,
        "arousal":            round(arousal, 4),
        "valence":            round(valence, 4),
        "engagement":         round(engagement, 4),
        "regulation_state":   round(reg, 4),
        "coherence_to_other": round(avg_coh, 4),
        "position":           list(position),
        "timestamp":          time.time()
    }


def _compute_music_params(affective_context: dict, scene_dict: dict) -> dict:
    """
    Derive music parameters from affective context.
    Mirrors the logic in mccf_ambient.html fieldToMusic().
    """
    E   = affective_context.get("arousal", 0.5)
    val = affective_context.get("valence", 0.0)
    reg = affective_context.get("regulation_state", 0.7)
    coh = affective_context.get("avg_coherence", 0.5)
    zp  = affective_context.get("zone_pressure", {})
    zones = affective_context.get("active_zones", [])

    tension  = E * 0.6 + (1 - coh) * 0.4
    B        = zp.get("B", 0.0)
    P        = zp.get("P", 0.0)
    S        = zp.get("S", 0.0)

    tempo    = int(50 + E * 70 * (1 - reg * 0.25))

    zone_type = "neutral"
    if zones:
        z0 = zones[0]
        zone_type = z0.get("type", "neutral") if isinstance(z0, dict) else "neutral"

    ZONE_SCALES = {
        "library": "dorian", "intimate": "major",
        "forum": "mixolydian", "authority": "phrygian",
        "garden": "pentatonic", "threat": "locrian",
        "sacred": "lydian", "neutral": "pentatonic"
    }

    if tension > 0.7:    mode = "locrian"
    elif tension > 0.5:  mode = "phrygian"
    else:                mode = ZONE_SCALES.get(zone_type, "pentatonic")

    return {
        "tension":            round(tension, 3),
        "rhythm_stability":   round(0.5 + B * 0.5, 3),
        "melodic_resolution": round(0.5 + P * 0.5, 3),
        "texture_density":    round(0.3 + S * 0.5 + coh * 0.2, 3),
        "tempo":              tempo,
        "mode":               mode,
        "zone_type":          zone_type,
        "arousal":            round(E, 3),
        "valence":            round(val, 3),
        "avg_coherence":      round(coh, 3)
    }


# ---------------------------------------------------------------------------
# Lighting endpoints
# ---------------------------------------------------------------------------

@ambient_bp.route('/lighting/state', methods=['GET'])
def lighting_state():
    if not _last_lighting:
        return jsonify({"error": "no lighting state yet — call /ambient/sync first"}), 404
    return jsonify(_last_lighting)


@ambient_bp.route('/lighting/scalars', methods=['GET'])
def lighting_scalars_endpoint():
    """
    Flat scalar dict ready for direct routing to X3D field values.
    Poll this from the X3D Script node's initialize() or on a TimeSensor.
    """
    if not _last_lighting:
        return jsonify({"error": "no data"}), 404
    return jsonify(_last_lighting)


@ambient_bp.route('/lighting/x3d', methods=['GET'])
def lighting_x3d():
    """X3D fragment for current lighting state."""
    if not _last_lighting:
        return "<!-- No lighting state yet -->", 200, {"Content-Type": "application/xml"}

    from mccf_lighting import LightState
    # Reconstruct LightState from scalars
    ls = LightState(
        key_color       = tuple(_last_lighting.get("key_color", [1,1,1])),
        key_intensity   = _last_lighting.get("key_intensity", 0.8),
        key_direction   = tuple(_last_lighting.get("key_direction", [-0.5,-1,-0.5])),
        fill_color      = tuple(_last_lighting.get("fill_color", [0.8,0.85,1])),
        fill_intensity  = _last_lighting.get("fill_intensity", 0.4),
        ambient_color   = tuple(_last_lighting.get("ambient_color", [0.2,0.2,0.25])),
        ambient_intensity = _last_lighting.get("ambient_intensity", 0.3),
        rim_color       = tuple(_last_lighting.get("rim_color", [0.6,0.7,1])),
        rim_intensity   = _last_lighting.get("rim_intensity", 0.2),
        agent_tints     = _last_lighting.get("agent_tints", {}),
        flicker_offset  = _last_lighting.get("flicker_amplitude", 0.0),
        kelvin          = _last_lighting.get("kelvin_normalized", 0.5) * 7000 + 2000,
        contrast        = _last_lighting.get("contrast", 0.5),
        zone_type       = _last_lighting.get("zone_type", "neutral")
    )
    return ls.to_x3d_fragment(), 200, {"Content-Type": "application/xml"}


@ambient_bp.route('/ambient/state', methods=['GET'])
def ambient_state():
    """Combined music + lighting + field state."""
    field = _get_field()
    return jsonify({
        "field": {
            "matrix":      field.field_matrix(),
            "echo_risks":  field.echo_chamber_risk(),
            "agent_count": len(field.agents)
        },
        "lighting": _last_lighting or {},
        "music":    _last_music    or {},
        "timestamp": time.time()
    })
