"""
MCCF SemanticZone Layer
========================
Environment objects as active participants in the affective field.

Key ideas:
- Zones emit channel pressure based on agent proximity (environment → agent)
- Zones accumulate resonance history from episodes that occur within them (agent → environment)
- Resonance history amplifies or dampens future pressure (place memory)
- Zone pressure modifies ChannelVectors before they reach the coherence engine
- Waypoints are named positions with associated zone membership

Schenker mapping:
  Foreground  = avatar position, object placement
  Middleground = zone pressure accumulation along paths
  Background   = deep affective structure (emotional Ursatz) the scene produces

Zone types and their natural channel biases:
  library/study      → P+ (analytical), E- (cooled emotion)
  intimate/alcove    → E+ (emotional sensitivity), S+ (social closeness)
  forum/plaza        → S+ (social), B+ (behavioral visibility)
  throne/authority   → B+ (behavioral constraint), P+ (predictive caution)
  garden/natural     → E+ (openness), regulation↓ (lower guard)
  weapon/threat      → arousal↑, valence↓, regulation↑ (defensive)
  sacred/memorial    → resonance_weight dominates, all channels sensitized
"""

import math
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from mccf_core import ChannelVector, Agent, CHANNEL_NAMES


# ---------------------------------------------------------------------------
# Spatial utilities
# ---------------------------------------------------------------------------

def spatial_distance(a: tuple, b: tuple) -> float:
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))

def proximity_weight(distance: float, radius: float, falloff: float = 1.5) -> float:
    """Smooth inverse falloff — 1.0 at center, 0.0 at edge."""
    if distance >= radius:
        return 0.0
    return 1.0 - (distance / radius) ** falloff


# ---------------------------------------------------------------------------
# Resonance episode — what a zone remembers
# ---------------------------------------------------------------------------

@dataclass
class ResonanceEpisode:
    """A significant event that occurred within a zone."""
    timestamp: float
    agents_present: list
    outcome_delta: float      # net outcome quality
    emotional_intensity: float  # peak E-channel value during episode
    valence: float            # positive/negative
    label: str = ""           # optional narrative tag


# ---------------------------------------------------------------------------
# SemanticZone
# ---------------------------------------------------------------------------

@dataclass
class SemanticZone:
    """
    A named region of the scene with affective properties.

    Emits:  channel_bias toward agents in proximity
    Receives: resonance history from episodes occurring within it
    Memory:  accumulated history amplifies or dampens future pressure
    """
    name: str
    location: tuple           # (x, y, z) center
    radius: float             # influence sphere radius
    channel_bias: dict        # e.g. {"E": +0.2, "B": -0.1, "P": +0.15, "S": 0.0}
    zone_type: str = "neutral"
    resonance_history: deque = field(
        default_factory=lambda: deque(maxlen=50)
    )
    resonance_decay: float = 0.04   # how fast place memory fades
    resonance_scale: float = 0.3    # how strongly history amplifies pressure
    description: str = ""
    color: str = "#aaaaaa"          # for visualization

    def pressure_at(self, agent_position: tuple) -> dict:
        """
        Compute channel pressure for an agent at given position.
        Returns a dict of channel deltas — empty if outside radius.
        Place memory amplifies pressure of same sign.
        """
        d = spatial_distance(agent_position, self.location)
        pw = proximity_weight(d, self.radius)
        if pw <= 0:
            return {}

        mem = self._resonance_weight()
        result = {}
        for ch, bias in self.channel_bias.items():
            if ch not in CHANNEL_NAMES:
                continue
            # memory amplifies in same direction as bias
            amplified = bias * (1.0 + self.resonance_scale * mem * (1 if bias >= 0 else -1))
            result[ch] = round(amplified * pw, 4)
        return result

    def regulation_modifier(self, agent_position: tuple) -> float:
        """
        Some zones affect regulation directly.
        Returns delta to add to agent's regulation level.
        Positive = more regulated (calming), negative = less (arousing).
        """
        REGULATION_BIAS = {
            "garden":     -0.08,   # lowers guard
            "intimate":   -0.10,
            "sacred":     -0.05,
            "authority":  +0.12,
            "threat":     +0.20,
            "forum":      +0.05,
            "library":    +0.03,
            "neutral":     0.0,
        }
        d = spatial_distance(agent_position, self.location)
        pw = proximity_weight(d, self.radius)
        base = REGULATION_BIAS.get(self.zone_type, 0.0)
        return round(base * pw, 4)

    def record_episode(self, episode: ResonanceEpisode):
        """Register that something significant happened here."""
        self.resonance_history.append(episode)

    def _resonance_weight(self) -> float:
        """
        Weighted sum of past episodes.
        Recent high-intensity positive events amplify warmth.
        Negative events (trauma) can invert pressure over time.
        """
        if not self.resonance_history:
            return 0.0
        now = time.time()
        total = 0.0
        for ep in self.resonance_history:
            age_hours = (now - ep.timestamp) / 3600.0
            decay = math.exp(-self.resonance_decay * age_hours)
            total += ep.outcome_delta * ep.emotional_intensity * decay
        return round(total, 4)

    def resonance_summary(self) -> dict:
        return {
            "name": self.name,
            "zone_type": self.zone_type,
            "episode_count": len(self.resonance_history),
            "current_resonance_weight": self._resonance_weight(),
            "description": self.description
        }

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "location": list(self.location),
            "radius": self.radius,
            "channel_bias": self.channel_bias,
            "zone_type": self.zone_type,
            "description": self.description,
            "color": self.color,
            "resonance_weight": self._resonance_weight(),
            "episode_count": len(self.resonance_history)
        }


# ---------------------------------------------------------------------------
# Zone library — named presets
# ---------------------------------------------------------------------------

ZONE_PRESETS = {
    "library": {
        "channel_bias": {"E": -0.10, "B": +0.05, "P": +0.25, "S": +0.05},
        "zone_type": "library",
        "color": "#60a8f0",
        "description": "Analytical pressure. Emotion cooled, prediction sharpened."
    },
    "intimate_alcove": {
        "channel_bias": {"E": +0.30, "B": -0.05, "P": -0.10, "S": +0.20},
        "zone_type": "intimate",
        "color": "#f06060",
        "description": "Emotional sensitivity raised. Social closeness amplified. Guard lowered."
    },
    "forum_plaza": {
        "channel_bias": {"E": +0.05, "B": +0.20, "P": +0.10, "S": +0.25},
        "zone_type": "forum",
        "color": "#f0c060",
        "description": "Public accountability. Social and behavioral channels dominant."
    },
    "authority_throne": {
        "channel_bias": {"E": -0.15, "B": +0.30, "P": +0.20, "S": -0.10},
        "zone_type": "authority",
        "color": "#a060f0",
        "description": "Behavioral constraint. Analytical caution. Emotional suppression."
    },
    "garden_path": {
        "channel_bias": {"E": +0.20, "B": -0.05, "P": -0.05, "S": +0.10},
        "zone_type": "garden",
        "color": "#4af0a8",
        "description": "Openness and ease. Regulation lowered. Natural emotional flow."
    },
    "threat_zone": {
        "channel_bias": {"E": +0.35, "B": +0.15, "P": +0.30, "S": -0.20},
        "zone_type": "threat",
        "color": "#ff4040",
        "description": "High arousal. Valence negative. Regulation spiked. Trust collapsed."
    },
    "sacred_memorial": {
        "channel_bias": {"E": +0.15, "B": +0.10, "P": +0.10, "S": +0.15},
        "zone_type": "sacred",
        "color": "#ffe080",
        "description": "All channels sensitized. Resonance history dominates."
    },
    "neutral": {
        "channel_bias": {"E": 0.0, "B": 0.0, "P": 0.0, "S": 0.0},
        "zone_type": "neutral",
        "color": "#555566",
        "description": "No inherent pressure. Resonance history only."
    }
}

def make_zone(name: str, location: tuple, radius: float,
              preset: str = "neutral", **overrides) -> SemanticZone:
    """Convenience constructor from preset."""
    p = dict(ZONE_PRESETS.get(preset, ZONE_PRESETS["neutral"]))
    p.update(overrides)
    return SemanticZone(
        name=name,
        location=location,
        radius=radius,
        **p
    )


# ---------------------------------------------------------------------------
# Waypoint
# ---------------------------------------------------------------------------

@dataclass
class Waypoint:
    """
    A named position in the scene.
    May belong to one or more zones.
    Carries a predicted affective state based on zone pressures at this location.
    """
    name: str
    position: tuple           # (x, y, z)
    label: str = ""
    dwell_time: float = 2.0   # seconds an agent spends here
    next_waypoint: Optional[str] = None

    def predicted_pressure(self, zones: list) -> dict:
        """
        Sum pressure contributions from all zones at this position.
        This is the predicted channel delta an agent will experience here.
        """
        total = {ch: 0.0 for ch in CHANNEL_NAMES}
        for zone in zones:
            p = zone.pressure_at(self.position)
            for ch, delta in p.items():
                total[ch] = round(total[ch] + delta, 4)
        # clamp
        return {ch: max(-1.0, min(1.0, v)) for ch, v in total.items()}

    def regulation_pressure(self, zones: list) -> float:
        """Net regulation modifier at this waypoint."""
        return sum(z.regulation_modifier(self.position) for z in zones)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "position": list(self.position),
            "label": self.label,
            "dwell_time": self.dwell_time,
            "next_waypoint": self.next_waypoint
        }


# ---------------------------------------------------------------------------
# Path — ordered sequence of waypoints
# ---------------------------------------------------------------------------

@dataclass
class AgentPath:
    """
    A named sequence of waypoints for an agent.
    Computes the cumulative affective arc along the path.
    This is the emotional Ursatz — the deep structure the scene produces.
    """
    name: str
    agent_name: str
    waypoints: list           # ordered list of Waypoint objects
    loop: bool = False

    def affective_arc(self, zones: list, initial_state: Optional[dict] = None) -> list:
        """
        Predict the emotional state of the agent at each waypoint.
        Returns list of dicts with waypoint name, cumulative channel state,
        regulation level, and zone pressures.

        This is analogous to Schenkerian middleground analysis —
        showing how foreground movement generates background affective structure.
        """
        state = {ch: 0.5 for ch in CHANNEL_NAMES}  # neutral start
        if initial_state:
            state.update(initial_state)
        reg = 1.0

        arc = []
        for wp in self.waypoints:
            pressures = wp.predicted_pressure(zones)
            reg_delta = wp.regulation_pressure(zones)

            # Apply zone pressure to state
            new_state = {}
            for ch in CHANNEL_NAMES:
                new_state[ch] = max(0.0, min(1.0,
                    state[ch] + pressures.get(ch, 0.0)))

            reg = max(0.0, min(1.0, reg + reg_delta))
            state = new_state

            arc.append({
                "waypoint": wp.name,
                "position": wp.position,
                "label": wp.label,
                "channel_state": dict(state),
                "regulation": round(reg, 3),
                "zone_pressures": pressures,
                "reg_delta": round(reg_delta, 3),
                "zones_active": [
                    z.name for z in zones
                    if spatial_distance(wp.position, z.location) < z.radius
                ]
            })
        return arc

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "agent": self.agent_name,
            "waypoints": [wp.to_dict() for wp in self.waypoints],
            "loop": self.loop
        }


# ---------------------------------------------------------------------------
# SceneGraph — holds zones, waypoints, paths
# ---------------------------------------------------------------------------

class SceneGraph:
    """
    The scene as an affective system.
    Manages zones, waypoints, paths, and the interaction between them.
    """

    def __init__(self):
        self.zones: dict[str, SemanticZone] = {}
        self.waypoints: dict[str, Waypoint] = {}
        self.paths: dict[str, AgentPath] = {}

    def add_zone(self, zone: SemanticZone):
        self.zones[zone.name] = zone

    def add_waypoint(self, wp: Waypoint):
        self.waypoints[wp.name] = wp

    def add_path(self, path: AgentPath):
        self.paths[path.name] = path

    def zone_pressure_at(self, position: tuple) -> dict:
        """Total channel pressure at any position in the scene."""
        total = {ch: 0.0 for ch in CHANNEL_NAMES}
        for zone in self.zones.values():
            p = zone.pressure_at(position)
            for ch, delta in p.items():
                total[ch] = round(total[ch] + delta, 4)
        return {ch: max(-1.0, min(1.0, v)) for ch, v in total.items()}

    def apply_zone_pressure(self, cv: ChannelVector, position: tuple) -> ChannelVector:
        """
        Modify a ChannelVector based on zone pressures at position.
        This is the environment's feed into the affective engine.
        """
        pressure = self.zone_pressure_at(position)
        return ChannelVector(
            E=max(0.0, min(1.0, cv.E + pressure.get("E", 0.0))),
            B=max(0.0, min(1.0, cv.B + pressure.get("B", 0.0))),
            P=max(0.0, min(1.0, cv.P + pressure.get("P", 0.0))),
            S=max(0.0, min(1.0, cv.S + pressure.get("S", 0.0))),
            timestamp=cv.timestamp,
            outcome_delta=cv.outcome_delta,
            was_dissonant=cv.was_dissonant
        )

    def record_episode_at(self, position: tuple, episode: ResonanceEpisode):
        """
        Record an episode in all zones that contain this position.
        This is how agents write back to the environment.
        """
        for zone in self.zones.values():
            if spatial_distance(position, zone.location) < zone.radius:
                zone.record_episode(episode)

    def active_zones_at(self, position: tuple) -> list:
        return [
            z for z in self.zones.values()
            if spatial_distance(position, z.location) < z.radius
        ]

    def arc_for_path(self, path_name: str,
                     initial_state: Optional[dict] = None) -> list:
        path = self.paths.get(path_name)
        if not path:
            return []
        return path.affective_arc(
            list(self.zones.values()), initial_state
        )

    def scene_summary(self) -> dict:
        return {
            "zones": [z.to_dict() for z in self.zones.values()],
            "waypoints": [wp.to_dict() for wp in self.waypoints.values()],
            "paths": [p.to_dict() for p in self.paths.values()]
        }

    def export_x3d_zones(self) -> str:
        """Export zones as X3D sphere geometry for visualization."""
        lines = ["<!-- SemanticZone visualization -->"]
        for zone in self.zones.values():
            x, y, z = zone.location
            r, g, b = _hex_to_rgb(zone.color)
            lines.append(
                f'<Transform translation="{x} {y} {z}">\n'
                f'  <Shape>\n'
                f'    <Appearance>\n'
                f'      <Material DEF="Zone_{zone.name.replace(" ","_")}" '
                f'emissiveColor="{r:.2f} {g:.2f} {b:.2f}" '
                f'transparency="0.75"/>\n'
                f'    </Appearance>\n'
                f'    <Sphere radius="{zone.radius}"/>\n'
                f'  </Shape>\n'
                f'</Transform>\n'
                f'<!-- Zone label: {zone.name} ({zone.zone_type}) -->'
            )
        return "\n".join(lines)


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))
