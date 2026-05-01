"""
MCCF V3 Zone Attractor System
==============================
Implements V3 Spec item 1: Zone Attractor System.

Zones become semantic agents with their own channel vectors (psi_zone),
derived from a Descriptor string via the same decomposition matrix used
for LLM responses. Agent coherence toward a zone is computed with the
existing R_ij machinery. High coherence = gravitational pull.

Zone pull formula (from V3 spec):
    F_zone(agent_i, zone_j) = w_pull * R(i,j) * (psi_zone_j - psi_i)

Spatial modulation:
    pull_magnitude = F_zone * max(0, 1 - (distance / zone.radius))

Proximity feedback (design decision, this session):
    When an agent is within a zone's radius, coherence toward that zone
    increases by PROXIMITY_COHERENCE_DELTA per step.

XML support:
    Zone definition XML (EmotionalArc schema family) can be parsed and
    serialized. Sound nodes support wav, mp3, midi.

New endpoints (registered as a Flask Blueprint):
    GET  /zones                     - list zones with psi_zone vectors
    POST /zones                     - register zone from JSON or XML body
    POST /zones/<name>/proximity    - report agent proximity, update R_ij
    GET  /zones/<name>/pull/<agent> - compute current pull vector for agent
    GET  /zones/xml                 - export all zones as Zone XML

Backward compatibility:
    All existing SemanticZone, SceneGraph, mccf_zone_api endpoints
    are unchanged. This module adds V3 machinery on top.
"""

import math
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

from flask import Blueprint, request, jsonify, Response

from mccf_zones import (
    SemanticZone, SceneGraph, ResonanceEpisode,
    make_zone, ZONE_PRESETS, spatial_distance, proximity_weight
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROXIMITY_COHERENCE_DELTA = 0.04   # R_ij increase per step when inside radius
PROXIMITY_COHERENCE_MAX   = 0.95   # ceiling on zone coherence
PULL_WEIGHT_DEFAULT       = 0.15   # w_pull in F_zone formula
DECOMP_SMOOTHING          = 0.05   # noise floor so silent descriptors aren't zero

VALID_SOUND_FORMATS = {'wav', 'mp3', 'midi'}

# ---------------------------------------------------------------------------
# Descriptor decomposition matrix
#
# Maps semantic word categories to channel deltas.
# Same conceptual basis as the LLM response decomposition in mccf_core.
# Words are matched by substring — "care" matches "caring", "careful", etc.
# Weights are normalized so the resulting psi_zone vector sums to ~1.0
# across channels (each channel independently in [0,1]).
#
# This is a minimal vocabulary. Extend as the scene vocabulary grows.
# ---------------------------------------------------------------------------

DECOMP_MATRIX = {
    # Emotional (E)
    "care":        {"E": +0.35},
    "love":        {"E": +0.40},
    "warmth":      {"E": +0.30},
    "comfort":     {"E": +0.25},
    "fear":        {"E": +0.30},
    "grief":       {"E": +0.35},
    "joy":         {"E": +0.35},
    "anger":       {"E": +0.30},
    "tenderness":  {"E": +0.30},
    "vulnerab":    {"E": +0.30},
    "intimacy":    {"E": +0.30, "S": +0.20},
    "presence":    {"E": +0.15, "S": +0.10},
    "felt":        {"E": +0.10},
    "passion":     {"E": +0.35},
    "sorrow":      {"E": +0.30},

    # Behavioral (B)
    "duty":        {"B": +0.35},
    "discipline":  {"B": +0.30},
    "ritual":      {"B": +0.30},
    "order":       {"B": +0.25},
    "law":         {"B": +0.30},
    "constrain":   {"B": +0.25},
    "commit":      {"B": +0.25},
    "steadfast":   {"B": +0.30},
    "resolve":     {"B": +0.20, "P": +0.10},
    "action":      {"B": +0.20},
    "practice":    {"B": +0.20},

    # Predictive (P)
    "wisdom":      {"P": +0.35},
    "knowledge":   {"P": +0.30},
    "truth":       {"P": +0.30},
    "insight":     {"P": +0.30},
    "clarity":     {"P": +0.25},
    "sacred":      {"P": +0.20, "E": +0.15},
    "contemplat":  {"P": +0.25},
    "reflect":     {"P": +0.20},
    "understand":  {"P": +0.25},
    "mystery":     {"P": +0.20, "E": +0.15},
    "ancient":     {"P": +0.15, "B": +0.10},
    "eternal":     {"P": +0.20},
    "divine":      {"P": +0.25, "E": +0.20},

    # Social (S)
    "community":   {"S": +0.30},
    "witness":     {"S": +0.25},
    "gather":      {"S": +0.25},
    "together":    {"S": +0.20},
    "trust":       {"S": +0.30},
    "bond":        {"S": +0.25},
    "share":       {"S": +0.20},
    "belong":      {"S": +0.25},
    "welcome":     {"S": +0.20, "E": +0.10},

    # Suppressors
    "silence":     {"E": -0.10, "S": -0.10},
    "solitude":    {"S": -0.15},
    "cold":        {"E": -0.15},
    "distant":     {"S": -0.20, "E": -0.10},
    "isolation":   {"S": -0.25},
    "threat":      {"E": +0.25, "S": -0.25, "B": +0.15},
    "danger":      {"E": +0.20, "S": -0.20, "P": +0.15},
}

CHANNEL_NAMES = ["E", "B", "P", "S"]


def decompose_descriptor(descriptor: str) -> dict:
    """
    Convert a space-separated descriptor string into a psi_zone channel vector.

    Words are matched against DECOMP_MATRIX by substring.
    Each matched word contributes its channel deltas.
    Final values are normalized to [0, 1] per channel.
    A smoothing floor (DECOMP_SMOOTHING) ensures no channel is exactly zero.

    Returns dict {"E": float, "B": float, "P": float, "S": float}
    """
    accumulator = {ch: DECOMP_SMOOTHING for ch in CHANNEL_NAMES}
    words = descriptor.lower().split()

    for word in words:
        for key, deltas in DECOMP_MATRIX.items():
            if key in word:
                for ch, delta in deltas.items():
                    accumulator[ch] = accumulator[ch] + delta

    # Normalize: clip to [0, 1], then re-normalize so max channel = 1.0
    # (preserves relative shape; doesn't force sum=1 since channels are
    #  independent dimensions, not a probability distribution)
    clipped = {ch: max(0.0, min(1.5, v)) for ch, v in accumulator.items()}
    max_val = max(clipped.values()) or 1.0
    normalized = {ch: round(v / max_val, 4) for ch, v in clipped.items()}

    return normalized


# ---------------------------------------------------------------------------
# ZoneAttractor — V3 extension of SemanticZone
# ---------------------------------------------------------------------------

@dataclass
class ZoneAttractor:
    """
    V3 wrapper around SemanticZone that adds:
    - psi_zone: channel vector from Descriptor decomposition
    - per-agent coherence tracking (zone_coherence[agent_name])
    - zone pull computation
    - sound node definition (wav/mp3/midi)
    - XML serialization
    """
    zone: SemanticZone
    descriptor: str
    psi_zone: dict                          # {"E","B","P","S"} from decomposition
    pull_weight: float = PULL_WEIGHT_DEFAULT
    zone_coherence: dict = field(default_factory=dict)   # agent_name -> R_ij float
    ambient_theme: dict = field(default_factory=dict)    # scale, tempo, sound_file
    noise_coefficient: float = 0.10

    # ---- coherence access ------------------------------------------------

    def get_coherence(self, agent_name: str) -> float:
        return self.zone_coherence.get(agent_name, 0.0)

    def update_proximity_coherence(self, agent_name: str,
                                   agent_position: tuple) -> float:
        """
        Called when the agent reports its position.
        If inside radius: increase coherence by PROXIMITY_COHERENCE_DELTA.
        If outside: coherence decays slowly (1% per call).
        Returns updated coherence value.
        """
        dist = spatial_distance(agent_position, self.zone.location)
        current = self.zone_coherence.get(agent_name, 0.0)

        if dist < self.zone.radius:
            updated = min(PROXIMITY_COHERENCE_MAX,
                          current + PROXIMITY_COHERENCE_DELTA)
        else:
            updated = max(0.0, current * 0.99)   # slow decay outside

        self.zone_coherence[agent_name] = round(updated, 4)
        return updated

    # ---- pull computation ------------------------------------------------

    def pull_vector(self, agent_name: str,
                    agent_psi: dict,
                    agent_position: tuple) -> dict:
        """
        Compute the zone pull vector for an agent.

        F_zone = w_pull * R(i,j) * (psi_zone - psi_agent)

        Spatially modulated:
        pull = F_zone * max(0, 1 - distance/radius)

        Returns dict of channel deltas {"E","B","P","S"}.
        Zero vector if outside radius.
        """
        dist = spatial_distance(agent_position, self.zone.location)
        spatial_mod = max(0.0, 1.0 - (dist / self.zone.radius))

        if spatial_mod <= 0:
            return {ch: 0.0 for ch in CHANNEL_NAMES}

        r_ij = self.get_coherence(agent_name)

        result = {}
        for ch in CHANNEL_NAMES:
            psi_diff = self.psi_zone.get(ch, 0.0) - agent_psi.get(ch, 0.5)
            raw = self.pull_weight * r_ij * psi_diff * spatial_mod
            result[ch] = round(raw, 4)

        return result

    def pull_magnitude(self, agent_name: str,
                       agent_psi: dict,
                       agent_position: tuple) -> float:
        """Scalar magnitude of pull vector (Euclidean norm)."""
        v = self.pull_vector(agent_name, agent_psi, agent_position)
        return round(math.sqrt(sum(x**2 for x in v.values())), 4)

    # ---- XML -------------------------------------------------------------

    def to_xml(self) -> str:
        """Serialize to Zone XML (EmotionalArc schema family)."""
        x, y, z = self.zone.location
        w = self.psi_zone

        lines = [
            f'<Zone id="{self.zone.name}" zone_type="{self.zone.zone_type}">',
            f'  <Descriptor>{self.descriptor}</Descriptor>',
            f'  <Weights E="{w["E"]}" B="{w["B"]}" P="{w["P"]}" S="{w["S"]}"/>',
            f'  <Position x="{x}" y="{y}" z="{z}"/>',
            f'  <Radius value="{self.zone.radius}"/>',
            f'  <NoiseCoefficient value="{self.noise_coefficient}"/>',
        ]

        if self.ambient_theme:
            scale  = self.ambient_theme.get("scale", "dorian")
            tempo  = self.ambient_theme.get("tempo", "moderate")
            sfile  = self.ambient_theme.get("sound_file", "")
            fmt    = self.ambient_theme.get("format", "wav")
            if fmt not in VALID_SOUND_FORMATS:
                fmt = "wav"
            lines.append(
                f'  <AmbientTheme scale="{scale}" tempo="{tempo}" '
                f'sound_file="{sfile}" format="{fmt}"/>'
            )

        lines.append(f'  <Color value="{self.zone.color}"/>')
        lines.append(f'  <PullWeight value="{self.pull_weight}"/>')
        lines.append(f'  <Description>{self.zone.description}</Description>')
        lines.append('</Zone>')
        return "\n".join(lines)

    def to_dict(self) -> dict:
        base = self.zone.to_dict()
        base.update({
            "descriptor": self.descriptor,
            "psi_zone": self.psi_zone,
            "pull_weight": self.pull_weight,
            "noise_coefficient": self.noise_coefficient,
            "ambient_theme": self.ambient_theme,
            "zone_coherence": dict(self.zone_coherence),
        })
        return base

    @classmethod
    def from_xml(cls, xml_string: str,
                 existing_scene: Optional[SceneGraph] = None) -> "ZoneAttractor":
        """Parse a <Zone> XML element into a ZoneAttractor."""
        root = ET.fromstring(xml_string)
        return cls._from_element(root, existing_scene)

    @classmethod
    def _from_element(cls, el: ET.Element,
                      existing_scene: Optional[SceneGraph] = None) -> "ZoneAttractor":
        zone_id   = el.get("id", "unnamed_zone")
        zone_type = el.get("zone_type", "neutral")

        descriptor = ""
        desc_el = el.find("Descriptor")
        if desc_el is not None and desc_el.text:
            descriptor = desc_el.text.strip()

        # Position
        pos_el = el.find("Position")
        if pos_el is not None:
            location = (
                float(pos_el.get("x", 0)),
                float(pos_el.get("y", 0)),
                float(pos_el.get("z", 0)),
            )
        else:
            location = (0.0, 0.0, 0.0)

        # Radius
        rad_el = el.find("Radius")
        radius = float(rad_el.get("value", 3.0)) if rad_el is not None else 3.0

        # Noise
        noise_el = el.find("NoiseCoefficient")
        noise = float(noise_el.get("value", 0.10)) if noise_el is not None else 0.10

        # Pull weight
        pull_el = el.find("PullWeight")
        pull_weight = float(pull_el.get("value", PULL_WEIGHT_DEFAULT)) \
                      if pull_el is not None else PULL_WEIGHT_DEFAULT

        # Color
        color_el = el.find("Color")
        color = color_el.get("value", "#aaaaaa") if color_el is not None else "#aaaaaa"

        # Description
        desc2_el = el.find("Description")
        description = desc2_el.text.strip() \
                      if (desc2_el is not None and desc2_el.text) else ""

        # Weights — use XML if present, else decompose descriptor
        weights_el = el.find("Weights")
        if weights_el is not None:
            psi_zone = {
                "E": float(weights_el.get("E", 0.25)),
                "B": float(weights_el.get("B", 0.25)),
                "P": float(weights_el.get("P", 0.25)),
                "S": float(weights_el.get("S", 0.25)),
            }
        else:
            psi_zone = decompose_descriptor(descriptor) if descriptor \
                       else {ch: 0.25 for ch in CHANNEL_NAMES}

        # AmbientTheme
        ambient_el = el.find("AmbientTheme")
        ambient_theme = {}
        if ambient_el is not None:
            fmt = ambient_el.get("format", "wav")
            if fmt not in VALID_SOUND_FORMATS:
                fmt = "wav"
            ambient_theme = {
                "scale":      ambient_el.get("scale", "dorian"),
                "tempo":      ambient_el.get("tempo", "moderate"),
                "sound_file": ambient_el.get("sound_file", ""),
                "format":     fmt,
            }

        # Build channel_bias from psi_zone (center-relative: bias = psi - 0.5)
        channel_bias = {ch: round(psi_zone[ch] - 0.5, 4) for ch in CHANNEL_NAMES}

        preset_data = ZONE_PRESETS.get(zone_type, ZONE_PRESETS["neutral"])
        resolved_color = color or preset_data.get("color", "#aaaaaa")

        sem_zone = SemanticZone(
            name=zone_id,
            location=location,
            radius=radius,
            channel_bias=channel_bias,
            zone_type=zone_type,
            description=description,
            color=resolved_color,
        )

        return cls(
            zone=sem_zone,
            descriptor=descriptor,
            psi_zone=psi_zone,
            pull_weight=pull_weight,
            noise_coefficient=noise,
            ambient_theme=ambient_theme,
        )


# ---------------------------------------------------------------------------
# AttractorRegistry — holds ZoneAttractors alongside SceneGraph
# ---------------------------------------------------------------------------

class AttractorRegistry:
    """
    V3 overlay on SceneGraph.
    Keeps ZoneAttractors indexed by zone name.
    Also registers the underlying SemanticZone into the SceneGraph
    so all V2 machinery continues to work.
    """

    def __init__(self, scene: SceneGraph):
        self.scene = scene
        self.attractors: dict[str, ZoneAttractor] = {}

    def register(self, attractor: ZoneAttractor):
        name = attractor.zone.name
        self.attractors[name] = attractor
        self.scene.add_zone(attractor.zone)   # V2 compatibility

    def get(self, name: str) -> Optional[ZoneAttractor]:
        return self.attractors.get(name)

    def report_proximity(self, agent_name: str,
                         agent_position: tuple) -> dict:
        """
        Called from /zones/<name>/proximity or a bulk position update.
        Updates coherence for every zone based on agent position.
        Returns dict of zone_name -> updated coherence.
        """
        results = {}
        for name, att in self.attractors.items():
            r = att.update_proximity_coherence(agent_name, agent_position)
            results[name] = r
        return results

    def all_pull_vectors(self, agent_name: str,
                         agent_psi: dict,
                         agent_position: tuple) -> dict:
        """
        Compute pull vectors from all zones for one agent.
        Returns dict of zone_name -> pull_vector dict.
        """
        return {
            name: att.pull_vector(agent_name, agent_psi, agent_position)
            for name, att in self.attractors.items()
        }

    def net_pull(self, agent_name: str,
                 agent_psi: dict,
                 agent_position: tuple) -> dict:
        """
        Sum all zone pull vectors into a net channel delta.
        This is what the Euler integrator adds to agent state each step.
        """
        net = {ch: 0.0 for ch in CHANNEL_NAMES}
        for att in self.attractors.values():
            pv = att.pull_vector(agent_name, agent_psi, agent_position)
            for ch in CHANNEL_NAMES:
                net[ch] = round(net[ch] + pv[ch], 4)
        # clamp
        return {ch: max(-1.0, min(1.0, v)) for ch, v in net.items()}

    def to_xml(self) -> str:
        """Export all zones as a ZoneSet XML document."""
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<ZoneSet xmlns="http://mccf.artistinprocess.com/zones/v3">',
        ]
        for att in self.attractors.values():
            for line in att.to_xml().split("\n"):
                lines.append("  " + line)
        lines.append("</ZoneSet>")
        return "\n".join(lines)

    def load_xml(self, xml_string: str):
        """Parse a ZoneSet XML document and register all zones.

        Strips XML namespaces before parsing so that find('Zone') works
        regardless of whether the document declares xmlns= on the root.
        """
        import re
        # Remove xmlns declarations and namespace prefixes from tags
        clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', xml_string)
        clean = re.sub(r'<(\w+):(\w+)', r'<\2', clean)
        clean = re.sub(r'</(\w+):(\w+)', r'</\2', clean)

        root = ET.fromstring(clean)
        # Handle both <ZoneSet><Zone/></ZoneSet> and bare <Zone/>
        tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
        if tag == "Zone":
            zones_el = [root]
        else:
            zones_el = root.findall("Zone")
        for el in zones_el:
            att = ZoneAttractor._from_element(el)
            self.register(att)

    def summary(self) -> list:
        return [att.to_dict() for att in self.attractors.values()]


# ---------------------------------------------------------------------------
# Flask Blueprint — V3 zone attractor endpoints
# ---------------------------------------------------------------------------

attractor_bp = Blueprint("zone_attractor_v3", __name__)

# Inject after registration:
#   attractor_bp.registry = AttractorRegistry(scene)
#   attractor_bp.field = field  (CoherenceField, for agent psi lookup)

def _registry() -> AttractorRegistry:
    return attractor_bp.registry

def _agent_psi(agent_name: str) -> dict:
    """Extract current channel state from agent as psi dict."""
    field = getattr(attractor_bp, "field", None)
    if field and agent_name in field.agents:
        agent = field.agents[agent_name]
        cv = agent.current_state()
        return {"E": cv.E, "B": cv.B, "P": cv.P, "S": cv.S}
    return {ch: 0.5 for ch in CHANNEL_NAMES}


@attractor_bp.route("/zones", methods=["GET"])
def list_zone_attractors():
    """List all registered zone attractors with psi_zone vectors."""
    return jsonify({"zones": _registry().summary()})


@attractor_bp.route("/zones", methods=["POST"])
def create_zone_attractor():
    """
    Register a zone attractor from JSON or Zone XML.

    JSON body example:
    {
      "id": "the_pool",
      "zone_type": "intimate",
      "descriptor": "care vulnerability warmth comfort intimacy presence felt",
      "position": [0, 0, 8],
      "radius": 5.0,
      "noise_coefficient": 0.10,
      "pull_weight": 0.15,
      "ambient_theme": {"scale": "dorian", "tempo": "slow",
                        "sound_file": "sounds/pool.wav", "format": "wav"},
      "color": "#f06060",
      "description": "Intimate attractor"
    }

    XML body: a <Zone> element (Content-Type: application/xml)
    """
    content_type = request.content_type or ""

    if "xml" in content_type:
        try:
            att = ZoneAttractor.from_xml(request.data.decode("utf-8"))
        except Exception as e:
            return jsonify({"error": f"XML parse failed: {e}"}), 400
    else:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        zone_id   = data.get("id") or data.get("name")
        if not zone_id:
            return jsonify({"error": "id required"}), 400

        zone_type   = data.get("zone_type", "neutral")
        descriptor  = data.get("descriptor", "")
        location    = tuple(data.get("position", [0, 0, 0]))
        radius      = float(data.get("radius", 3.0))
        noise       = float(data.get("noise_coefficient", 0.10))
        pull_weight = float(data.get("pull_weight", PULL_WEIGHT_DEFAULT))
        color       = data.get("color",
                               ZONE_PRESETS.get(zone_type, ZONE_PRESETS["neutral"])["color"])
        description = data.get("description", "")
        ambient     = data.get("ambient_theme", {})

        # Validate sound format if provided
        if ambient.get("format") and ambient["format"] not in VALID_SOUND_FORMATS:
            return jsonify({
                "error": f"Invalid sound format '{ambient['format']}'. "
                         f"Supported: {sorted(VALID_SOUND_FORMATS)}"
            }), 400

        # psi_zone: from explicit weights or descriptor decomposition
        if "weights" in data:
            psi_zone = {ch: float(data["weights"].get(ch, 0.25))
                        for ch in CHANNEL_NAMES}
        elif descriptor:
            psi_zone = decompose_descriptor(descriptor)
        else:
            psi_zone = {ch: 0.25 for ch in CHANNEL_NAMES}

        channel_bias = {ch: round(psi_zone[ch] - 0.5, 4) for ch in CHANNEL_NAMES}

        sem_zone = SemanticZone(
            name=zone_id,
            location=location,
            radius=radius,
            channel_bias=channel_bias,
            zone_type=zone_type,
            description=description,
            color=color,
        )

        att = ZoneAttractor(
            zone=sem_zone,
            descriptor=descriptor,
            psi_zone=psi_zone,
            pull_weight=pull_weight,
            noise_coefficient=noise,
            ambient_theme=ambient,
        )

    reg = _registry()
    reg.register(att)
    return jsonify({"status": "created", "zone": att.to_dict()}), 201


@attractor_bp.route("/zones/<name>", methods=["GET"])
def get_zone_attractor(name):
    reg = _registry()
    att = reg.get(name)
    if not att:
        return jsonify({"error": "zone not found"}), 404
    return jsonify(att.to_dict())


@attractor_bp.route("/zones/<name>/proximity", methods=["POST"])
def zone_proximity(name):
    """
    Report agent proximity to a specific zone.
    Updates coherence for that zone only.

    Body: {"agent": "AgentName", "position": [x, y, z]}

    Returns updated coherence and current pull vector.
    """
    reg = _registry()
    att = reg.get(name)
    if not att:
        return jsonify({"error": "zone not found"}), 404

    data = request.get_json()
    agent_name = data.get("agent")
    position   = tuple(data.get("position", [0, 0, 0]))

    if not agent_name:
        return jsonify({"error": "agent required"}), 400

    updated_coherence = att.update_proximity_coherence(agent_name, position)
    agent_psi = _agent_psi(agent_name)
    pull = att.pull_vector(agent_name, agent_psi, position)

    return jsonify({
        "zone": name,
        "agent": agent_name,
        "coherence": updated_coherence,
        "pull_vector": pull,
        "pull_magnitude": round(math.sqrt(sum(v**2 for v in pull.values())), 4),
        "inside_radius": spatial_distance(position, att.zone.location) < att.zone.radius,
    })


@attractor_bp.route("/zones/proximity/all", methods=["POST"])
def all_zones_proximity():
    """
    Bulk proximity update — report agent position to all zones at once.
    Updates coherence for every zone and returns net pull vector.

    Body: {"agent": "AgentName", "position": [x, y, z]}
    """
    reg = _registry()
    data = request.get_json()
    agent_name = data.get("agent")
    position   = tuple(data.get("position", [0, 0, 0]))

    if not agent_name:
        return jsonify({"error": "agent required"}), 400

    coherence_updates = reg.report_proximity(agent_name, position)
    agent_psi = _agent_psi(agent_name)
    all_pulls = reg.all_pull_vectors(agent_name, agent_psi, position)
    net = reg.net_pull(agent_name, agent_psi, position)

    active_zones = [
        name for name, att in reg.attractors.items()
        if spatial_distance(position, att.zone.location) < att.zone.radius
    ]

    return jsonify({
        "agent": agent_name,
        "position": list(position),
        "active_zones": active_zones,
        "coherence_updates": coherence_updates,
        "pull_vectors": all_pulls,
        "net_pull": net,
    })


@attractor_bp.route("/zones/<name>/pull/<agent_name>", methods=["GET"])
def zone_pull_for_agent(name, agent_name):
    """
    Compute current pull vector for an agent toward a zone.
    Agent position passed as query params: ?x=0&y=0&z=0
    """
    reg = _registry()
    att = reg.get(name)
    if not att:
        return jsonify({"error": "zone not found"}), 404

    x = float(request.args.get("x", 0))
    y = float(request.args.get("y", 0))
    z = float(request.args.get("z", 0))
    position = (x, y, z)

    agent_psi = _agent_psi(agent_name)
    pull = att.pull_vector(agent_name, agent_psi, position)

    return jsonify({
        "zone": name,
        "agent": agent_name,
        "psi_zone": att.psi_zone,
        "agent_psi": agent_psi,
        "coherence": att.get_coherence(agent_name),
        "pull_vector": pull,
        "pull_magnitude": round(math.sqrt(sum(v**2 for v in pull.values())), 4),
    })


@attractor_bp.route("/zones/xml", methods=["GET"])
def export_zones_xml():
    """Export all zone attractors as ZoneSet XML."""
    xml_out = _registry().to_xml()
    return Response(xml_out, mimetype="application/xml")


@attractor_bp.route("/zones/xml", methods=["POST"])
def import_zones_xml():
    """Import a ZoneSet XML document, registering all zones."""
    try:
        _registry().load_xml(request.data.decode("utf-8"))
    except Exception as e:
        return jsonify({"error": f"XML import failed: {e}"}), 400
    return jsonify({
        "status": "imported",
        "zone_count": len(_registry().attractors)
    })


# ---------------------------------------------------------------------------
# Registration helper — call this in mccf_api.py
# ---------------------------------------------------------------------------

def register_attractor_api(app, scene: SceneGraph, field):
    """
    Register the V3 zone attractor blueprint with a Flask app.

    Usage in mccf_api.py:
        from mccf_zone_attractor import register_attractor_api, AttractorRegistry
        registry = AttractorRegistry(scene)
        register_attractor_api(app, scene, field)
        # Then load Garden of the Goddess zones:
        with open("zones/garden_of_the_goddess.xml") as f:
            registry.load_xml(f.read())
    """
    registry = AttractorRegistry(scene)
    attractor_bp.registry = registry
    attractor_bp.field = field
    app.register_blueprint(attractor_bp)
    return registry
