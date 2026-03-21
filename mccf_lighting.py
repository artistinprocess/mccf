"""
MCCF Lighting Engine
=====================
Affective field → X3D light color and intensity transforms.

Every output channel (music, voice, lighting) reads the same
coherence field. This module handles the lighting transducer.

Mappings:
  E (emotional)  → color temperature (warm/cool)
  B (behavioral) → light stability / flicker
  P (predictive) → directionality / focus
  S (social)     → source density / fill ratio
  valence        → hue rotation (golden ↔ cold blue)
  regulation     → contrast ratio (soft ↔ hard shadows)
  zone_type      → lighting preset character

X3D output targets:
  PointLight.color, PointLight.intensity
  DirectionalLight.color, DirectionalLight.intensity
  SpotLight.color, SpotLight.intensity, SpotLight.beamWidth
  Material.diffuseColor, Material.emissiveColor

Also provides:
  /ambient/sync  — push update to music + lighting + field simultaneously
  /lighting/state — current computed lighting state
  /lighting/x3d   — X3D fragment for current lighting
"""

import math
import time
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Color math
# ---------------------------------------------------------------------------

def kelvin_to_rgb(kelvin: float) -> tuple:
    """
    Convert color temperature (Kelvin) to normalized RGB.
    Range: 2000K (warm amber) to 9000K (cool blue-white).
    Approximation of Tanner Helland's algorithm.
    """
    k = max(1000, min(40000, kelvin)) / 100.0

    if k <= 66:
        r = 1.0
        g = max(0, min(1, (99.4708025861 * math.log(k) - 161.1195681661) / 255))
        if k <= 19:
            b = 0.0
        else:
            b = max(0, min(1, (138.5177312231 * math.log(k - 10) - 305.0447927307) / 255))
    else:
        r = max(0, min(1, (329.698727446 * ((k - 60) ** -0.1332047592)) / 255))
        g = max(0, min(1, (288.1221695283 * ((k - 60) ** -0.0755148492)) / 255))
        b = 1.0

    return (round(r, 4), round(g, 4), round(b, 4))


def hue_shift(rgb: tuple, shift: float) -> tuple:
    """Rotate hue by shift (-1.0 to 1.0). Positive = warmer."""
    r, g, b = rgb
    # Simple warm/cool shift
    warm_r = min(1.0, r + shift * 0.15)
    warm_g = min(1.0, g + shift * 0.05)
    warm_b = max(0.0, b - shift * 0.20)
    return (round(warm_r, 4), round(warm_g, 4), round(warm_b, 4))


def lerp_color(a: tuple, b: tuple, t: float) -> tuple:
    """Linear interpolate between two RGB tuples."""
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t, 4) for i in range(3))


def rgb_to_x3d(rgb: tuple) -> str:
    """Format RGB tuple as X3D color string."""
    return f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f}"


# ---------------------------------------------------------------------------
# Zone lighting presets
# ---------------------------------------------------------------------------

ZONE_LIGHT_PRESETS = {
    "garden": {
        "key_kelvin":    4200,
        "fill_kelvin":   3200,
        "key_intensity": 0.7,
        "fill_intensity": 0.5,
        "contrast":      0.4,
        "description":   "Soft warm fill, golden hour quality"
    },
    "intimate": {
        "key_kelvin":    2800,
        "fill_kelvin":   2400,
        "key_intensity": 0.6,
        "fill_intensity": 0.55,
        "contrast":      0.35,
        "description":   "Warm intimate, candle-like"
    },
    "library": {
        "key_kelvin":    5500,
        "fill_kelvin":   5500,
        "key_intensity": 0.85,
        "fill_intensity": 0.7,
        "contrast":      0.5,
        "description":   "Neutral even white, working light"
    },
    "authority": {
        "key_kelvin":    6500,
        "fill_kelvin":   4000,
        "key_intensity": 1.0,
        "fill_intensity": 0.15,
        "contrast":      0.85,
        "description":   "Cold key, deep shadow, monumental"
    },
    "forum": {
        "key_kelvin":    5000,
        "fill_kelvin":   4500,
        "key_intensity": 0.8,
        "fill_intensity": 0.65,
        "contrast":      0.55,
        "description":   "Even broadcast-style, open"
    },
    "threat": {
        "key_kelvin":    2200,
        "fill_kelvin":   3800,
        "key_intensity": 0.9,
        "fill_intensity": 0.1,
        "contrast":      0.92,
        "description":   "Red-shifted underlighting, extreme contrast"
    },
    "sacred": {
        "key_kelvin":    7000,
        "fill_kelvin":   3000,
        "key_intensity": 0.65,
        "fill_intensity": 0.45,
        "contrast":      0.65,
        "description":   "Cool silver + single warm spot, theatrical"
    },
    "neutral": {
        "key_kelvin":    5000,
        "fill_kelvin":   4500,
        "key_intensity": 0.75,
        "fill_intensity": 0.5,
        "contrast":      0.55,
        "description":   "Neutral balanced"
    }
}


# ---------------------------------------------------------------------------
# Lighting state computation
# ---------------------------------------------------------------------------

@dataclass
class LightState:
    """Complete lighting state derived from affective field."""

    # Key light
    key_color:     tuple = (1.0, 1.0, 1.0)
    key_intensity: float = 0.8
    key_direction: tuple = (-0.5, -1.0, -0.5)  # x, y, z normalized

    # Fill light
    fill_color:     tuple = (0.8, 0.85, 1.0)
    fill_intensity: float = 0.4

    # Ambient
    ambient_color:     tuple = (0.2, 0.2, 0.25)
    ambient_intensity: float = 0.3

    # Rim / back light
    rim_color:     tuple = (0.6, 0.7, 1.0)
    rim_intensity: float = 0.2

    # Avatar material tints (per agent)
    agent_tints:   dict = field(default_factory=dict)

    # Flicker state (updated per frame)
    flicker_offset: float = 0.0

    # Metadata
    kelvin:          float = 5000.0
    contrast:        float = 0.5
    zone_type:       str   = "neutral"
    computed_at:     float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "key_color":     list(self.key_color),
            "key_intensity": round(self.key_intensity, 4),
            "fill_color":    list(self.fill_color),
            "fill_intensity": round(self.fill_intensity, 4),
            "ambient_color": list(self.ambient_color),
            "ambient_intensity": round(self.ambient_intensity, 4),
            "rim_color":     list(self.rim_color),
            "rim_intensity": round(self.rim_intensity, 4),
            "agent_tints":   self.agent_tints,
            "flicker_offset": round(self.flicker_offset, 4),
            "kelvin":        round(self.kelvin),
            "contrast":      round(self.contrast, 3),
            "zone_type":     self.zone_type,
            "computed_at":   self.computed_at
        }

    def to_x3d_fragment(self, transition_time: float = 1.5) -> str:
        """Generate X3D lighting fragment with interpolator nodes."""
        lines = [
            "<!-- MCCF Lighting State -->",
            f"<!-- Zone: {self.zone_type} | Kelvin: {self.kelvin:.0f}K | Contrast: {self.contrast:.2f} -->",
            "",
            "<!-- Key Light -->",
            f'<DirectionalLight DEF="KeyLight"',
            f'  color="{rgb_to_x3d(self.key_color)}"',
            f'  intensity="{self.key_intensity:.3f}"',
            f'  direction="{self.key_direction[0]:.2f} {self.key_direction[1]:.2f} {self.key_direction[2]:.2f}"',
            f'  global="true"/>',
            "",
            "<!-- Fill Light -->",
            f'<PointLight DEF="FillLight"',
            f'  color="{rgb_to_x3d(self.fill_color)}"',
            f'  intensity="{self.fill_intensity:.3f}"',
            f'  location="0 4 4"',
            f'  radius="20"',
            f'  global="true"/>',
            "",
            "<!-- Ambient -->",
            f'<DirectionalLight DEF="AmbientLight"',
            f'  color="{rgb_to_x3d(self.ambient_color)}"',
            f'  intensity="{self.ambient_intensity:.3f}"',
            f'  direction="0 -1 0"',
            f'  global="true"/>',
            "",
            "<!-- Rim Light -->",
            f'<PointLight DEF="RimLight"',
            f'  color="{rgb_to_x3d(self.rim_color)}"',
            f'  intensity="{self.rim_intensity:.3f}"',
            f'  location="0 2 -6"',
            f'  radius="15"',
            f'  global="true"/>',
        ]

        # Agent tint materials
        for agent_name, tint in self.agent_tints.items():
            safe = agent_name.replace(" ", "_")
            lines += [
                "",
                f"<!-- {agent_name} affect tint -->",
                f'<!-- Route: MCCF_Bridge.color_{safe} → Mat_{safe}_Body.diffuseColor -->',
                f'<!-- Current tint: {rgb_to_x3d(tint["body"])} -->',
                f'<!-- Emissive glow: {rgb_to_x3d(tint["glow"])} intensity {tint["glow_intensity"]:.3f} -->',
            ]

        return "\n".join(lines)


def compute_lighting(
    affective_context: dict,
    field_state: dict,
    scene_state: dict
) -> LightState:
    """
    Derive complete LightState from affective field.

    affective_context: from _get_affective_context() in voice_api
    field_state:       from /field endpoint
    scene_state:       from /scene endpoint
    """
    E   = affective_context.get("arousal",           0.5)
    val = affective_context.get("valence",            0.0)
    reg = affective_context.get("regulation_state",   0.7)
    eng = affective_context.get("engagement",         0.5)
    coh = affective_context.get("coherence_to_other", 0.5)
    zp  = affective_context.get("zone_pressure",      {})
    zones = affective_context.get("active_zones",     [])

    # Determine dominant zone type
    zone_type = "neutral"
    if zones:
        z0 = zones[0]
        zone_type = z0.get("zone_type", z0) if isinstance(z0, dict) else "neutral"

    preset = ZONE_LIGHT_PRESETS.get(zone_type, ZONE_LIGHT_PRESETS["neutral"])

    # E → color temperature shift
    # High E (emotional activation) shifts warmer
    # Low E shifts cooler
    base_kelvin = preset["key_kelvin"]
    kelvin_delta = (E - 0.5) * 2000   # ±1000K
    kelvin = max(2000, min(9000, base_kelvin + kelvin_delta))

    # valence → additional hue shift
    # Positive valence: golden warmth
    # Negative valence: cold blue-green cast
    key_rgb = kelvin_to_rgb(kelvin)
    key_rgb = hue_shift(key_rgb, val * 0.4)

    # Fill is always slightly cooler than key (sky/ambient quality)
    fill_kelvin = max(2000, kelvin - 800 + (1 - E) * 400)
    fill_rgb    = kelvin_to_rgb(fill_kelvin)

    # Contrast driven by regulation
    # High regulation = soft light, low contrast (contemplative)
    # Low regulation  = hard light, high contrast (reactive)
    contrast = preset["contrast"] * (1.0 - reg * 0.3) + (1 - reg) * 0.2
    contrast = max(0.1, min(1.0, contrast))

    # P (predictive) → directionality
    # High P: tight directional key (clarity, focus)
    # Low P:  diffuse, softer direction
    key_direction = compute_key_direction(eng, zp)

    # Key intensity modulated by arousal and contrast
    key_intensity = preset["key_intensity"] * (0.7 + E * 0.3)

    # Fill ratio: social density S → how much fill vs key
    S = zp.get("S", 0.0)  # zone social pressure
    fill_ratio = 0.3 + coh * 0.3 + S * 0.2
    fill_intensity = key_intensity * fill_ratio * (1 - contrast * 0.5)

    # Ambient: inverse of contrast
    ambient_intensity = 0.15 + (1 - contrast) * 0.25
    ambient_rgb = kelvin_to_rgb(max(5000, kelvin + 1500))

    # Rim: behavioral channel — high B adds clean back edge
    B = zp.get("B", 0.0)
    rim_intensity = 0.1 + eng * 0.15 + B * 0.1
    rim_rgb = kelvin_to_rgb(7000)

    # Flicker: B-channel instability
    flicker = max(0.0, (0.3 - zp.get("B", 0.0)) * 0.1)

    # Agent tints from affect params
    agent_tints = compute_agent_tints(field_state, affective_context)

    return LightState(
        key_color       = key_rgb,
        key_intensity   = round(key_intensity, 4),
        key_direction   = key_direction,
        fill_color      = fill_rgb,
        fill_intensity  = round(fill_intensity, 4),
        ambient_color   = ambient_rgb,
        ambient_intensity = round(ambient_intensity, 4),
        rim_color       = rim_rgb,
        rim_intensity   = round(rim_intensity, 4),
        agent_tints     = agent_tints,
        flicker_offset  = round(flicker, 4),
        kelvin          = round(kelvin),
        contrast        = round(contrast, 3),
        zone_type       = zone_type,
        computed_at     = time.time()
    )


def compute_key_direction(engagement: float, zone_pressure: dict) -> tuple:
    """
    Key light direction from engagement and zone pressure.
    High engagement + high P → tight top-down (spotlight feel)
    Low engagement → lower angle (more frontal, flatter)
    """
    P = zone_pressure.get("P", 0.0)
    angle_factor = 0.5 + engagement * 0.3 + P * 0.2
    y = -(0.6 + angle_factor * 0.4)
    x = -0.4 + (1 - engagement) * 0.3
    z = -0.3
    # normalize
    mag = math.sqrt(x*x + y*y + z*z)
    return (round(x/mag, 3), round(y/mag, 3), round(z/mag, 3))


def compute_agent_tints(field_state: dict, affective_context: dict) -> dict:
    """
    Per-agent material tint derived from their affect state.
    Returns body color and emissive glow for each agent.
    """
    tints = {}
    agents = field_state.get("agents", {})
    matrix = field_state.get("matrix", {})

    # Base hues per role
    ROLE_BASE_KELVIN = {
        "agent":     5000,
        "gardener":  4000,
        "librarian": 6000
    }

    for name, data in agents.items():
        role = data.get("role", "agent")
        base_k = ROLE_BASE_KELVIN.get(role, 5000)

        # Coherence toward others modulates warmth
        row = matrix.get(name, {})
        avg_coh = sum(v for k, v in row.items() if k != name) / max(1, len(row) - 1) if row else 0.5

        # Regulation modulates intensity
        reg = data.get("regulation", 1.0)

        kelvin = base_k + (avg_coh - 0.5) * 2000
        body_rgb = kelvin_to_rgb(kelvin)

        # Glow: emissive hint based on arousal
        weights = data.get("weights", {})
        E_weight = weights.get("E", 0.25)
        glow_intensity = E_weight * (1 - reg * 0.5)
        glow_rgb = hue_shift(body_rgb, avg_coh * 0.3)

        tints[name] = {
            "body":           body_rgb,
            "glow":           glow_rgb,
            "glow_intensity": round(glow_intensity, 4)
        }

    return tints


# ---------------------------------------------------------------------------
# Scalar output helpers — for direct routing to X3D field values
# ---------------------------------------------------------------------------

def lighting_scalars(ls: LightState) -> dict:
    """
    Flat dict of named scalar/vector values ready for direct
    routing to X3D field values via the MCCF_Bridge Script node.

    Each key corresponds to a Script output field that can be
    ROUTE'd to a Light or Material node field.
    """
    return {
        # DirectionalLight fields
        "key_color":             list(ls.key_color),
        "key_intensity":         ls.key_intensity,
        "key_direction":         list(ls.key_direction),

        # PointLight fields
        "fill_color":            list(ls.fill_color),
        "fill_intensity":        ls.fill_intensity,
        "fill_location":         [0.0, 4.0, 4.0],

        # Ambient
        "ambient_color":         list(ls.ambient_color),
        "ambient_intensity":     ls.ambient_intensity,

        # Rim
        "rim_color":             list(ls.rim_color),
        "rim_intensity":         ls.rim_intensity,

        # Flicker amplitude (to drive TimeSensor-based oscillation)
        "flicker_amplitude":     ls.flicker_offset,

        # Metadata scalars
        "kelvin_normalized":     round((ls.kelvin - 2000) / 7000, 4),
        "contrast":              ls.contrast,
        "zone_type":             ls.zone_type,

        # Per-agent tints (flat)
        "agent_tints":           ls.agent_tints
    }
