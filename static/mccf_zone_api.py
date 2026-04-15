"""
MCCF Zone + Waypoint API Extension
====================================
Add these routes to mccf_api.py.
Import: from mccf_zones import SceneGraph, make_zone, Waypoint, AgentPath, ResonanceEpisode, ZONE_PRESETS

Add to global state:
  scene = SceneGraph()

Endpoints added:
  GET/POST  /zone              list or create zone
  GET       /zone/<name>       zone detail + resonance
  DELETE    /zone/<name>       remove zone
  POST      /zone/<name>/episode  record episode at zone
  GET       /zone/presets      list available presets

  GET/POST  /waypoint          list or create waypoint
  POST      /path              create agent path
  GET       /path/<name>/arc   get affective arc for path

  GET       /scene             full scene summary
  GET       /scene/pressure    pressure at a given position
  GET       /export/x3d/zones  X3D zone visualization fragment
"""

from flask import Blueprint, request, jsonify
from mccf_zones import (
    SceneGraph, SemanticZone, make_zone,
    Waypoint, AgentPath, ResonanceEpisode,
    ZONE_PRESETS
)

zone_bp = Blueprint('zones', __name__)

# Inject scene reference after blueprint registration:
#   zone_bp.scene = scene
# Access via: zone_bp.scene

def get_scene() -> SceneGraph:
    return zone_bp.scene


# ---------------------------------------------------------------------------
# Zone endpoints
# ---------------------------------------------------------------------------

@zone_bp.route('/zone', methods=['GET'])
def list_zones():
    scene = get_scene()
    return jsonify({
        name: z.to_dict() for name, z in scene.zones.items()
    })


@zone_bp.route('/zone', methods=['POST'])
def create_zone():
    scene = get_scene()
    data = request.get_json()

    name     = data.get('name')
    location = tuple(data.get('location', [0, 0, 0]))
    radius   = float(data.get('radius', 3.0))
    preset   = data.get('preset', 'neutral')

    if not name:
        return jsonify({'error': 'name required'}), 400

    # Allow full custom bias or use preset
    channel_bias = data.get('channel_bias')
    # Derive zone_type and color from preset — even when custom bias is provided
    # The editor always sends channel_bias (even zeros), so we must use
    # preset to set zone_type, not rely on the caller sending zone_type.
    preset_data = ZONE_PRESETS.get(preset, ZONE_PRESETS['neutral'])
    resolved_zone_type = data.get('zone_type') or preset_data.get('zone_type', 'neutral')
    resolved_color     = data.get('color')     or preset_data.get('color', '#aaaaaa')

    if channel_bias:
        zone = SemanticZone(
            name=name,
            location=location,
            radius=radius,
            channel_bias=channel_bias,
            zone_type=resolved_zone_type,
            description=data.get('description', ''),
            color=resolved_color
        )
    else:
        zone = make_zone(name, location, radius, preset=preset,
                         description=data.get('description', ''),
                         color=resolved_color)

    scene.add_zone(zone)
    return jsonify({'status': 'created', 'zone': zone.to_dict()})


@zone_bp.route('/zone/<name>', methods=['GET'])
def get_zone(name):
    scene = get_scene()
    zone = scene.zones.get(name)
    if not zone:
        return jsonify({'error': 'not found'}), 404
    result = zone.to_dict()
    result['resonance_history'] = [
        {
            'timestamp': ep.timestamp,
            'agents': ep.agents_present,
            'outcome_delta': ep.outcome_delta,
            'intensity': ep.emotional_intensity,
            'valence': ep.valence,
            'label': ep.label
        }
        for ep in list(zone.resonance_history)[-10:]
    ]
    return jsonify(result)


@zone_bp.route('/zone/<name>', methods=['DELETE'])
def delete_zone(name):
    scene = get_scene()
    if name in scene.zones:
        del scene.zones[name]
        return jsonify({'status': 'deleted'})
    return jsonify({'error': 'not found'}), 404


@zone_bp.route('/zone/<name>/episode', methods=['POST'])
def record_zone_episode(name):
    """Record a significant episode at a named zone."""
    scene = get_scene()
    zone = scene.zones.get(name)
    if not zone:
        return jsonify({'error': 'zone not found'}), 404
    data = request.get_json()
    ep = ResonanceEpisode(
        timestamp=data.get('timestamp', __import__('time').time()),
        agents_present=data.get('agents', []),
        outcome_delta=float(data.get('outcome_delta', 0.0)),
        emotional_intensity=float(data.get('emotional_intensity', 0.5)),
        valence=float(data.get('valence', 0.0)),
        label=data.get('label', '')
    )
    zone.record_episode(ep)
    return jsonify({
        'status': 'recorded',
        'resonance_weight': zone._resonance_weight()
    })


@zone_bp.route('/zone/presets', methods=['GET'])
def list_presets():
    return jsonify({
        k: {
            'channel_bias': v['channel_bias'],
            'zone_type':    v['zone_type'],
            'color':        v['color'],
            'description':  v['description']
        }
        for k, v in ZONE_PRESETS.items()
    })


# ---------------------------------------------------------------------------
# Pressure query
# ---------------------------------------------------------------------------

@zone_bp.route('/scene/pressure', methods=['GET'])
def pressure_at():
    """
    GET /scene/pressure?x=0&y=0&z=0
    Returns total zone pressure at a position.
    """
    scene = get_scene()
    x = float(request.args.get('x', 0))
    y = float(request.args.get('y', 0))
    z = float(request.args.get('z', 0))
    pos = (x, y, z)
    pressure = scene.zone_pressure_at(pos)
    active = [
        {'name': z.name, 'type': z.zone_type, 'color': z.color}
        for z in scene.active_zones_at(pos)
    ]
    return jsonify({
        'position': [x, y, z],
        'channel_pressure': pressure,
        'active_zones': active
    })


# ---------------------------------------------------------------------------
# Waypoint endpoints
# ---------------------------------------------------------------------------

@zone_bp.route('/waypoint', methods=['GET'])
def list_waypoints():
    scene = get_scene()
    return jsonify({
        name: wp.to_dict() for name, wp in scene.waypoints.items()
    })


@zone_bp.route('/waypoint', methods=['POST'])
def create_waypoint():
    scene = get_scene()
    data = request.get_json()
    name = data.get('name')
    if not name:
        return jsonify({'error': 'name required'}), 400

    wp = Waypoint(
        name=name,
        position=tuple(data.get('position', [0, 0, 0])),
        label=data.get('label', ''),
        dwell_time=float(data.get('dwell_time', 2.0)),
        next_waypoint=data.get('next_waypoint')
    )
    scene.add_waypoint(wp)

    # Annotate with current zone pressures
    predicted = wp.predicted_pressure(list(scene.zones.values()))
    return jsonify({
        'status': 'created',
        'waypoint': wp.to_dict(),
        'predicted_pressure': predicted
    })


# ---------------------------------------------------------------------------
# Path endpoints
# ---------------------------------------------------------------------------

@zone_bp.route('/path', methods=['POST'])
def create_path():
    scene = get_scene()
    data = request.get_json()
    name       = data.get('name')
    agent_name = data.get('agent')
    wp_names   = data.get('waypoints', [])

    if not name or not agent_name:
        return jsonify({'error': 'name and agent required'}), 400

    waypoints = []
    for wpn in wp_names:
        wp = scene.waypoints.get(wpn)
        if not wp:
            return jsonify({'error': f'waypoint not found: {wpn}'}), 404
        waypoints.append(wp)

    path = AgentPath(
        name=name,
        agent_name=agent_name,
        waypoints=waypoints,
        loop=data.get('loop', False)
    )
    scene.add_path(path)
    return jsonify({'status': 'created', 'path': path.to_dict()})


@zone_bp.route('/path/<name>/arc', methods=['GET'])
def get_arc(name):
    """
    Compute the affective arc — emotional state at each waypoint.
    This is the Schenkerian middleground read of the path.
    """
    scene = get_scene()
    arc = scene.arc_for_path(name)
    if not arc:
        return jsonify({'error': 'path not found or empty'}), 404
    return jsonify({'path': name, 'arc': arc})


@zone_bp.route('/path', methods=['GET'])
def list_paths():
    scene = get_scene()
    return jsonify({
        name: p.to_dict() for name, p in scene.paths.items()
    })


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

@zone_bp.route('/scene', methods=['GET'])
def get_scene_summary():
    return jsonify(get_scene().scene_summary())


@zone_bp.route('/export/x3d/zones', methods=['GET'])
def export_zones_x3d():
    x3d = get_scene().export_x3d_zones()
    return x3d, 200, {'Content-Type': 'application/xml'}


# ---------------------------------------------------------------------------
# Enhanced sensor endpoint (zone-aware version)
# Replaces /sensor in mccf_api.py with zone pressure injection
# ---------------------------------------------------------------------------

@zone_bp.route('/sensor/spatial', methods=['POST'])
def spatial_sensor():
    """
    Zone-aware sensor endpoint.
    In addition to standard sensor data, accepts agent positions
    and applies zone pressure before feeding to coherence engine.

    Body adds:
      "from_position": [x, y, z]
      "to_position":   [x, y, z]
      "record_episode": bool  (whether to write episode to zones)
    """
    import time as _time
    from mccf_core import ChannelVector
    # Access field and other globals via blueprint
    field  = zone_bp.field
    scene  = zone_bp.scene

    data       = request.get_json()
    from_name  = data.get('from_agent')
    to_name    = data.get('to_agent')
    from_pos   = tuple(data.get('from_position', [0, 0, 0]))
    to_pos     = tuple(data.get('to_position',   [0, 0, 0]))

    # Auto-register agents
    for name in [from_name, to_name]:
        if name and name not in field.agents:
            from mccf_core import Agent
            field.register(Agent(name))

    if not from_name or not to_name:
        return jsonify({'error': 'from_agent and to_agent required'}), 400

    # Build base channel vector from sensor data
    from mccf_api import compute_channel_vector, affect_params_from_agent
    cv = compute_channel_vector(data.get('sensor_data', {}))

    # Apply zone pressure from agent's position
    cv_pressured = scene.apply_zone_pressure(cv, from_pos)

    # Apply regulation modifier from zones
    reg_delta = scene.zone_pressure_at(from_pos)  # used for context
    agent = field.agents[from_name]
    zone_reg = sum(
        z.regulation_modifier(from_pos)
        for z in scene.active_zones_at(from_pos)
    )
    if abs(zone_reg) > 0.01:
        new_reg = max(0.0, min(1.0, agent._affect_regulation + zone_reg * 0.1))
        agent.set_regulation(new_reg)

    field.interact(from_name, to_name, cv_pressured,
                   mutual=data.get('mutual', True))

    # Optionally record episode at zone
    if data.get('record_episode', False):
        ep = ResonanceEpisode(
            timestamp=_time.time(),
            agents_present=[from_name, to_name],
            outcome_delta=float(data.get('outcome_delta', 0.0)),
            emotional_intensity=cv_pressured.E,
            valence=float(data.get('valence', 0.0)),
            label=data.get('episode_label', '')
        )
        scene.record_episode_at(from_pos, ep)

    params = affect_params_from_agent(field.agents[from_name], to_name)
    params.update({
        'timestamp': _time.time(),
        'from_agent': from_name,
        'to_agent': to_name,
        'from_position': list(from_pos),
        'zone_pressure_applied': {
            ch: round(cv_pressured.__dict__[ch] - cv.__dict__[ch], 4)
            for ch in ['E','B','P','S']
        },
        'active_zones': [
            z.name for z in scene.active_zones_at(from_pos)
        ]
    })
    return jsonify(params)
