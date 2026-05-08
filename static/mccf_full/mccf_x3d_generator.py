"""
MCCF V3 X3D Scene Generator
=============================
Implements V3 Spec item 5 (Python side): generates a complete X3D scene
from a SceneDefinition and a list of CultivarDefinitions.

The generator produces a single X3D file that:
  - Inlines the MCCFAvatar Proto declaration
  - Places one ProtoInstance per cultivar with position, name, color
  - Places zone marker geometry at each zone location
  - Adds Sound nodes at zone centers with correct spatial parameters
  - Embeds the Master Script node with full routing table
  - Writes ROUTE connections for all channel fields

Output: static/mccf_scene.x3d  (default)
    — the path the existing mccf_x3d_loader.html expects.
    Override with output_path parameter.

Usage:
    from mccf_x3d_generator import generate_scene, write_scene
    from mccf_scene_wrapper import SceneDefinition
    from mccf_cultivar_lambda import CultivarDefinition

    scene_def = SceneDefinition.from_xml(open("scenes/garden_of_the_goddess_def.xml").read())
    cultivars = [CultivarDefinition.from_xml(open(f"cultivars/{name}.xml").read())
                 for name in ["the_witness"]]
    x3d = generate_scene(scene_def, cultivars)
    write_scene(x3d)  # writes to static/mccf_scene.x3d

The Master Script:
    Thin router only. Receives field state JSON from the MCCF backend
    via a timed poll (default 200ms). Writes channel values to each
    avatar's exposed fields via SAI. Does not compute pull or coherence.
    Falls back gracefully if the backend is unreachable.

Architecture constraint (from V3 spec, Grok review):
    The Script node is a state broadcaster only. All physics stay in Python.
    If the Script fails, mccf_x3d_loader.html can revert to direct polling.

Authors: Len Bullard, Claude Sonnet 4.6 (Tae)
V3 Spec v0.2, April 2026
"""

import os
import xml.etree.ElementTree as ET
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "static", "mccf_scene.x3d"
)

DEFAULT_API_URL   = "http://localhost:5000"
POLL_INTERVAL_MS  = 200      # field state poll interval
MAX_LEAN_RADIANS  = 0.28     # E-channel max forward tilt (~16 degrees)
MAX_APPROACH_M    = 2.0      # S-channel max Z translation in metres
STABILITY_MIN     = 0.88     # B-channel min Y scale (destabilised)
STABILITY_MAX     = 1.08     # B-channel max Y scale (grounded)
ZONE_MARKER_ALPHA = 0.55     # zone sphere transparency

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _xml_esc(s: str) -> str:
    return (str(s)
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

def _color_to_x3d(hex_color: str) -> str:
    """Convert #rrggbb to 'r g b' float string."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return "0.5 0.5 0.8"
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return f"{r/255:.3f} {g/255:.3f} {b/255:.3f}"

def _strip_ns(xml_string: str) -> str:
    clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', xml_string)
    clean = re.sub(r'<(\w+):(\w+)', r'<\2', clean)
    clean = re.sub(r'</(\w+):(\w+)', r'</\2', clean)
    return clean

def _safe_name(s: str) -> str:
    """Convert 'The Witness' → 'TheWitness' for DEF names."""
    return re.sub(r'[^A-Za-z0-9]', '', s.title().replace(' ', ''))


# ---------------------------------------------------------------------------
# Zone data extracted from SceneDefinition
# ---------------------------------------------------------------------------

def _parse_zones(scene_def) -> list:
    """
    Extract zone dicts from a SceneDefinition's zone_xml_blocks.
    Returns list of dicts with: id, zone_type, position, radius,
    color, scale (dorian/major/lydian), sound_file, format, description.
    """
    zones = []
    for zxml in scene_def.zone_xml_blocks:
        try:
            root = ET.fromstring(_strip_ns(zxml))
            zone_id   = root.get("id", "zone")
            zone_type = root.get("zone_type", "neutral")

            pos_el = root.find("Position")
            if pos_el is not None:
                pos = (float(pos_el.get("x",0)),
                       float(pos_el.get("y",0)),
                       float(pos_el.get("z",0)))
            else:
                pos = (0.0, 0.0, 0.0)

            rad_el = root.find("Radius")
            radius = float(rad_el.get("value", 3.0)) if rad_el else 3.0

            col_el = root.find("Color")
            color  = col_el.get("value","#888888") if col_el else "#888888"

            amb_el = root.find("AmbientTheme")
            scale      = amb_el.get("scale","dorian")      if amb_el is not None else "dorian"
            sound_file = amb_el.get("sound_file","")       if amb_el is not None else ""
            fmt        = amb_el.get("format","wav")        if amb_el is not None else "wav"

            desc_el = root.find("Description")
            desc = desc_el.text.strip() if (desc_el is not None and desc_el.text) else ""

            zones.append({
                "id": zone_id, "zone_type": zone_type,
                "position": pos, "radius": radius,
                "color": color, "scale": scale,
                "sound_file": sound_file, "format": fmt,
                "description": desc,
            })
        except Exception:
            continue
    return zones


# ---------------------------------------------------------------------------
# Proto declaration (inlined from mccf_avatar.proto.x3d)
# ---------------------------------------------------------------------------

def _proto_declaration() -> str:
    """
    Inline MCCFAvatar ProtoDeclare block.
    This is the complete Proto — no external file reference needed.
    The scene file is self-contained.
    """
    return """
    <!-- ═══════════════════════════════════════════════════
         MCCFAvatar Proto
         Channel-driven avatar skeleton.
         Replace Shape geometry with HAnimHumanoid when ready.
         ═══════════════════════════════════════════════════ -->
    <ProtoDeclare name="MCCFAvatar">
      <ProtoInterface>
        <field accessType="initializeOnly" type="SFString"  name="agentName"        value="Agent"/>
        <field accessType="initializeOnly" type="SFColor"   name="auraColor"        value="0.5 0.5 0.8"/>
        <field accessType="exposedField"   type="SFVec3f"   name="position"         value="0 0 0"/>
        <field accessType="exposedField"   type="SFFloat"   name="eLean"            value="0.0"/>
        <field accessType="exposedField"   type="SFFloat"   name="bStability"       value="1.0"/>
        <field accessType="exposedField"   type="SFFloat"   name="pOrientation"     value="0.0"/>
        <field accessType="exposedField"   type="SFFloat"   name="sApproach"        value="0.0"/>
        <field accessType="exposedField"   type="SFFloat"   name="arousal"          value="0.5"/>
        <field accessType="exposedField"   type="SFColor"   name="currentAuraColor" value="0.5 0.5 0.8"/>
        <field accessType="initializeOnly" type="SFBool"    name="showLabel"        value="true"/>
      </ProtoInterface>
      <ProtoBody>
        <Transform DEF="AvatarRoot">
          <IS><connect nodeField="translation" protoField="position"/></IS>
          <Transform DEF="ApproachTransform">
            <Transform DEF="OrientTransform">
              <Transform DEF="StabilityTransform">
                <Transform DEF="LeanTransform">
                  <Transform DEF="Body" translation="0 0.9 0">
                    <Shape>
                      <Appearance><Material DEF="BodyMaterial" diffuseColor="0.5 0.5 0.8" shininess="0.3"/></Appearance>
                      <Cylinder height="1.0" radius="0.25"/>
                    </Shape>
                    <Transform translation="0 0.75 0">
                      <Shape>
                        <Appearance><Material diffuseColor="0.8 0.75 0.7" shininess="0.2"/></Appearance>
                        <Sphere radius="0.20"/>
                      </Shape>
                    </Transform>
                    <Transform translation="-0.35 0.1 0" rotation="0 0 1 0.4">
                      <Shape><Appearance><Material diffuseColor="0.5 0.5 0.8"/></Appearance><Cylinder height="0.55" radius="0.07"/></Shape>
                    </Transform>
                    <Transform translation="0.35 0.1 0" rotation="0 0 1 -0.4">
                      <Shape><Appearance><Material diffuseColor="0.5 0.5 0.8"/></Appearance><Cylinder height="0.55" radius="0.07"/></Shape>
                    </Transform>
                    <Transform translation="-0.12 -0.85 0">
                      <Shape><Appearance><Material diffuseColor="0.4 0.4 0.7"/></Appearance><Cylinder height="0.65" radius="0.09"/></Shape>
                    </Transform>
                    <Transform translation="0.12 -0.85 0">
                      <Shape><Appearance><Material diffuseColor="0.4 0.4 0.7"/></Appearance><Cylinder height="0.65" radius="0.09"/></Shape>
                    </Transform>
                  </Transform>
                </Transform>
              </Transform>
            </Transform>
          </Transform>
          <Transform translation="0 0.9 0">
            <Shape DEF="AuraShape">
              <Appearance>
                <Material DEF="AuraMaterial" diffuseColor="0.5 0.5 0.8" transparency="0.75" emissiveColor="0.2 0.2 0.4"/>
              </Appearance>
              <Sphere radius="0.60"/>
            </Shape>
          </Transform>
          <Billboard axisOfRotation="0 1 0">
            <Transform translation="0 2.2 0">
              <Shape>
                <Appearance><Material emissiveColor="1 1 1"/></Appearance>
                <Text DEF="AgentLabel" string='"Agent"' solid="false">
                  <FontStyle size="0.18" justify='"MIDDLE" "MIDDLE"' family='"SANS"'/>
                </Text>
              </Shape>
            </Transform>
          </Billboard>
          <ProximitySensor DEF="AvatarProxSensor" center="0 0.9 0" size="3 3 3"/>
        </Transform>
      </ProtoBody>
    </ProtoDeclare>"""


# ---------------------------------------------------------------------------
# Master Script — the thin router
# ---------------------------------------------------------------------------

def _master_script(agents: list, zones: list, api_url: str) -> str:
    """
    Generate the Master Script node.

    agents: list of dicts with 'safe_name' (DEF-safe), 'name' (display)
    zones:  list of zone dicts from _parse_zones()
    api_url: MCCF backend URL

    The Script:
    - Polls /field every POLL_INTERVAL_MS milliseconds
    - Reads per-agent channel state from the response
    - Writes to each ProtoInstance's exposed fields via SAI
    - E  → eLean        (X-axis rotation angle, scaled to MAX_LEAN_RADIANS)
    - B  → bStability   (Y scale, mapped to STABILITY_MIN..STABILITY_MAX)
    - P  → pOrientation (Y-axis rotation angle)
    - S  → sApproach    (Z translation, scaled to MAX_APPROACH_M)
    - Arousal = (E*0.6 + S*0.4) mapped to 0.5..2.0
    - AuraColor = base cultivar color scaled by E intensity
    """

    # Build agent field declarations
    agent_fields = ""
    for ag in agents:
        sn = ag['safe_name']
        agent_fields += f"""
        <field accessType="outputOnly" type="SFFloat" name="{sn}_eLean"/>
        <field accessType="outputOnly" type="SFFloat" name="{sn}_bStability"/>
        <field accessType="outputOnly" type="SFFloat" name="{sn}_pOrientation"/>
        <field accessType="outputOnly" type="SFFloat" name="{sn}_sApproach"/>
        <field accessType="outputOnly" type="SFFloat" name="{sn}_arousal"/>
        <field accessType="outputOnly" type="SFColor" name="{sn}_auraColor"/>"""

    # Build per-agent update code
    agent_update_code = ""
    for ag in agents:
        sn   = ag['safe_name']
        name = ag['name']
        color = ag.get('color', '0.5 0.5 0.8')
        # color as JS array [r, g, b]
        parts = color.split()
        if len(parts) == 3:
            color_js = f"[{parts[0]}, {parts[1]}, {parts[2]}]"
        else:
            color_js = "[0.5, 0.5, 0.8]"
        agent_update_code += f"""
          // Agent: {name}
          var ag_{sn} = agentData['{name}'];
          if (ag_{sn}) {{
            var E_{sn} = ag_{sn}.E || 0.5;
            var B_{sn} = ag_{sn}.B || 0.5;
            var P_{sn} = ag_{sn}.P || 0.5;
            var S_{sn} = ag_{sn}.S || 0.5;
            {sn}_eLean        = E_{sn} * {MAX_LEAN_RADIANS};
            {sn}_bStability   = {STABILITY_MIN} + B_{sn} * ({STABILITY_MAX} - {STABILITY_MIN});
            {sn}_pOrientation = (P_{sn} - 0.5) * 1.57;
            {sn}_sApproach    = (S_{sn} - 0.5) * {MAX_APPROACH_M};
            var ar_{sn} = E_{sn} * 0.6 + S_{sn} * 0.4;
            {sn}_arousal = 0.5 + ar_{sn} * 1.5;
            var base_{sn} = {color_js};
            var ei_{sn} = 0.6 + E_{sn} * 0.4;
            {sn}_auraColor = new SFColor(
              Math.min(1.0, base_{sn}[0] * ei_{sn}),
              Math.min(1.0, base_{sn}[1] * ei_{sn}),
              Math.min(1.0, base_{sn}[2] * ei_{sn})
            );
          }}"""

    script_body = f"""
      function initialize() {{
        pollField();
      }}

      function pollField() {{
        try {{
          var req = new XMLHttpRequest();
          req.open('GET', '{api_url}/field', false);
          req.send();
          if (req.status === 200) {{
            var data = JSON.parse(req.responseText);
            updateAvatars(data);
          }}
        }} catch(e) {{
          // Backend unreachable — retain current values, try again next poll
        }}
        Browser.callLater({POLL_INTERVAL_MS}, pollField);
      }}

      function updateAvatars(fieldData) {{
        var agentData = {{}};
        // Flatten agent state from field response
        // /field returns agents dict with summary per agent
        var agents = fieldData.agents || {{}};
        for (var name in agents) {{
          var ag = agents[name];
          // Channel state from summary — weights are the current channel values
          var w = ag.weights || {{}};
          agentData[name] = {{
            E: w.E || 0.5,
            B: w.B || 0.5,
            P: w.P || 0.5,
            S: w.S || 0.5
          }};
        }}
        {agent_update_code}
      }}"""

    return f"""
    <!-- ═══════════════════════════════════════════════════
         MCCF Master Script
         Thin router: polls /field, writes to avatar fields.
         Does not compute pull or coherence — Python only.
         Falls back gracefully if backend unreachable.
         ═══════════════════════════════════════════════════ -->
    <Script DEF="MCCFMasterScript"
            directOutput="true"
            mustEvaluate="true">

      <field accessType="initializeOnly" type="SFString"
             name="apiUrl" value="{api_url}"/>
      {agent_fields}

      <![CDATA[ecmascript:
        {script_body}
      ]]>
    </Script>"""


# ---------------------------------------------------------------------------
# ProtoInstance per cultivar
# ---------------------------------------------------------------------------

def _proto_instance(cultivar_def, position: tuple, index: int) -> str:
    name       = cultivar_def.name
    safe_name  = _safe_name(name)
    color_hex  = cultivar_def.color if hasattr(cultivar_def, 'color') else "#8888cc"
    color_x3d  = _color_to_x3d(color_hex)
    px, py, pz = position

    return f"""
    <!-- Avatar: {name} -->
    <ProtoInstance name="MCCFAvatar" DEF="Avatar_{safe_name}">
      <fieldValue name="agentName"    value="{_xml_esc(name)}"/>
      <fieldValue name="auraColor"    value="{color_x3d}"/>
      <fieldValue name="position"     value="{px} {py} {pz}"/>
      <fieldValue name="showLabel"    value="true"/>
    </ProtoInstance>"""


# ---------------------------------------------------------------------------
# Zone marker geometry
# ---------------------------------------------------------------------------

def _zone_marker(zone: dict) -> str:
    """
    Translucent sphere at zone center showing zone radius.
    Color from zone definition. ProximitySensor at zone location.
    """
    x, y, z    = zone['position']
    radius     = zone['radius']
    color_x3d  = _color_to_x3d(zone['color'])
    zone_id    = zone['id']
    safe_id    = _safe_name(zone_id)
    desc       = _xml_esc(zone.get('description',''))

    return f"""
    <!-- Zone marker: {zone_id} -->
    <Transform DEF="ZoneMarker_{safe_id}" translation="{x} {y} {z}">
      <!-- Ground ring — visual indicator of zone radius -->
      <Transform translation="0 0.02 0" rotation="1 0 0 1.5708">
        <Shape>
          <Appearance>
            <Material diffuseColor="{color_x3d}"
                      transparency="0.70"
                      emissiveColor="{color_x3d}"/>
          </Appearance>
          <Disk2D outerRadius="{radius}" innerRadius="{radius * 0.92:.2f}"/>
        </Shape>
      </Transform>
      <!-- Zone center marker -->
      <Shape>
        <Appearance>
          <Material diffuseColor="{color_x3d}"
                    transparency="{ZONE_MARKER_ALPHA}"
                    emissiveColor="{color_x3d}"/>
        </Appearance>
        <Sphere radius="0.15"/>
      </Shape>
      <!-- ProximitySensor for zone entry/exit events -->
      <ProximitySensor DEF="ZoneProx_{safe_id}"
                       center="0 0 0"
                       size="{radius*2} {radius*2} {radius*2}"/>
    </Transform>"""


# ---------------------------------------------------------------------------
# Sound nodes
# ---------------------------------------------------------------------------

def _sound_node(zone: dict) -> str:
    """
    Spatial Sound node at zone center.
    AudioClip loops the zone ambient file if provided.
    If no sound file, node is present but AudioClip has empty url.
    """
    x, y, z   = zone['position']
    radius    = zone['radius']
    sound_url = zone.get('sound_file', '')
    zone_id   = zone['id']
    safe_id   = _safe_name(zone_id)
    fmt       = zone.get('format', 'wav')

    # X3D AudioClip url — relative to the scene file's location
    if sound_url:
        url_attr = f'url="../{sound_url}"'
    else:
        url_attr = 'url=""'

    return f"""
    <!-- Sound: {zone_id} ({zone.get('scale','')}) -->
    <Sound DEF="Sound_{safe_id}"
           location="{x} {y} {z}"
           maxBack="{radius:.1f}" maxFront="{radius:.1f}"
           minBack="{radius*0.3:.1f}" minFront="{radius*0.3:.1f}"
           spatialize="true"
           enabled="true">
      <AudioClip DEF="Clip_{safe_id}"
                 {url_attr}
                 loop="true"
                 startTime="-1"
                 stopTime="0"
                 description="{_xml_esc(zone_id)} ambient"/>
    </Sound>"""


# ---------------------------------------------------------------------------
# ROUTE connections
# ---------------------------------------------------------------------------

def _routes(agents: list) -> str:
    """
    ROUTE connections from Master Script output fields to
    ProtoInstance exposed fields.

    X3D SAI limitation: we cannot ROUTE directly to a ProtoInstance's
    exposed field by name in all implementations. The recommended pattern
    is to use the Script's outputOnly fields and ROUTE to the ProtoInstance.
    X_ITE supports this pattern.
    """
    lines = ["\n    <!-- ROUTE: Master Script → Avatar channel fields -->"]
    for ag in agents:
        sn = ag['safe_name']
        def_name = f"Avatar_{sn}"
        lines.append(
            f'    <ROUTE fromNode="MCCFMasterScript" fromField="{sn}_eLean"'
            f' toNode="{def_name}" toField="eLean"/>'
        )
        lines.append(
            f'    <ROUTE fromNode="MCCFMasterScript" fromField="{sn}_bStability"'
            f' toNode="{def_name}" toField="bStability"/>'
        )
        lines.append(
            f'    <ROUTE fromNode="MCCFMasterScript" fromField="{sn}_pOrientation"'
            f' toNode="{def_name}" toField="pOrientation"/>'
        )
        lines.append(
            f'    <ROUTE fromNode="MCCFMasterScript" fromField="{sn}_sApproach"'
            f' toNode="{def_name}" toField="sApproach"/>'
        )
        lines.append(
            f'    <ROUTE fromNode="MCCFMasterScript" fromField="{sn}_arousal"'
            f' toNode="{def_name}" toField="arousal"/>'
        )
        lines.append(
            f'    <ROUTE fromNode="MCCFMasterScript" fromField="{sn}_auraColor"'
            f' toNode="{def_name}" toField="currentAuraColor"/>'
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Viewpoint and navigation
# ---------------------------------------------------------------------------

def _viewpoint(scene_def) -> str:
    """Default viewpoint — positioned to see all zones."""
    return """
    <!-- Default viewpoint — sees full Garden scene -->
    <Viewpoint DEF="DefaultView"
               description="Garden of the Goddess"
               position="0 8 20"
               orientation="1 0 0 -0.38"
               fieldOfView="0.8"/>

    <!-- Director view — top down, useful for watching zone movement -->
    <Viewpoint DEF="DirectorView"
               description="Director — Top Down"
               position="0 25 0"
               orientation="1 0 0 -1.5708"
               fieldOfView="1.0"/>

    <NavigationInfo type='"EXAMINE" "ANY"'
                    speed="4"
                    headlight="true"/>"""


# ---------------------------------------------------------------------------
# Ground plane
# ---------------------------------------------------------------------------

def _ground_plane() -> str:
    return """
    <!-- Ground plane -->
    <Transform translation="0 0 0">
      <Shape>
        <Appearance>
          <Material diffuseColor="0.15 0.18 0.15"
                    specularColor="0.05 0.05 0.05"
                    shininess="0.1"
                    transparency="0.0"/>
        </Appearance>
        <Box size="60 0.04 60"/>
      </Shape>
    </Transform>

    <!-- Ambient sky background -->
    <Background skyColor="0.05 0.04 0.08"
                groundColor="0.10 0.12 0.10"/>

    <!-- Scene lighting -->
    <DirectionalLight direction="0.3 -1 -0.5"
                      intensity="0.7"
                      ambientIntensity="0.4"
                      color="1.0 0.97 0.90"/>"""


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_scene(scene_def,
                   cultivar_defs: list,
                   api_url: str = DEFAULT_API_URL,
                   initial_positions: Optional[list] = None) -> str:
    """
    Generate a complete X3D scene string.

    scene_def:         SceneDefinition object (from mccf_scene_wrapper)
    cultivar_defs:     list of CultivarDefinition objects (from mccf_cultivar_lambda)
    api_url:           MCCF backend URL for Master Script polling
    initial_positions: list of (x,y,z) tuples, one per cultivar.
                       Defaults to a spread along X axis at z=-2.

    Returns: complete X3D document as a string.
    """
    zones  = _parse_zones(scene_def)
    n      = len(cultivar_defs)

    # Default positions: spread agents along X, facing the scene
    if not initial_positions:
        if n == 1:
            initial_positions = [(0.0, 0.0, -3.0)]
        else:
            spread = 3.0
            initial_positions = [
                (-(n-1)*spread/2 + i*spread, 0.0, -3.0)
                for i in range(n)
            ]

    # Build agent list for Script and ROUTE generation
    agents = []
    for i, cd in enumerate(cultivar_defs):
        color_hex = cd.color if hasattr(cd, 'color') else "#8888cc"
        agents.append({
            "name":       cd.name,
            "safe_name":  _safe_name(cd.name),
            "color":      _color_to_x3d(color_hex),
            "color_hex":  color_hex,
        })

    scene_id  = getattr(scene_def, 'id', 'mccf_scene')
    scene_desc = getattr(scene_def, 'description', '')

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE X3D PUBLIC "ISO//Web3D//DTD X3D 4.0//EN"',
        '  "https://www.web3d.org/specifications/x3d-4.0.dtd">',
        f'<!-- MCCF V3 Scene: {_xml_esc(scene_id)} -->',
        f'<!-- {_xml_esc(scene_desc[:120])} -->',
        f'<!-- Generated by mccf_x3d_generator.py — do not edit by hand -->',
        '<X3D profile="Immersive" version="4.0">',
        '',
        '  <head>',
        f'    <meta name="title"   content="{_xml_esc(scene_id)}"/>',
        f'    <meta name="created" content="2026-04-30"/>',
        f'    <meta name="generator" content="mccf_x3d_generator.py V3"/>',
        '  </head>',
        '',
        '  <Scene>',
    ]

    # Proto declaration
    lines.append(_proto_declaration())

    # Viewpoint and environment
    lines.append(_viewpoint(scene_def))
    lines.append(_ground_plane())

    # Zone markers and sound nodes
    for zone in zones:
        lines.append(_zone_marker(zone))
        lines.append(_sound_node(zone))

    # Avatar ProtoInstances
    for i, cd in enumerate(cultivar_defs):
        pos = initial_positions[i] if i < len(initial_positions) else (0,0,0)
        lines.append(_proto_instance(cd, pos, i))

    # Master Script
    lines.append(_master_script(agents, zones, api_url))

    # ROUTE connections
    lines.append(_routes(agents))

    lines.append('')
    lines.append('  </Scene>')
    lines.append('</X3D>')

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Write to file
# ---------------------------------------------------------------------------

def write_scene(x3d_string: str,
                output_path: str = DEFAULT_OUTPUT_PATH) -> str:
    """
    Write the generated X3D to output_path.
    Creates parent directories if needed.
    Returns the output path.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(x3d_string)
    return output_path


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Quick generation test — produces static/mccf_scene.x3d from
    garden_of_the_goddess_def.xml and a single Witness cultivar.
    """
    import sys
    sys.path.insert(0, os.path.dirname(__file__))

    from mccf_scene_wrapper import SceneDefinition
    from mccf_cultivar_lambda import CultivarDefinition, ShadowContext

    # Load scene definition
    def_path = os.path.join(os.path.dirname(__file__),
                            "scenes", "garden_of_the_goddess_def.xml")
    if os.path.exists(def_path):
        with open(def_path) as f:
            scene_def = SceneDefinition.from_xml(f.read())
        print(f"Loaded SceneDefinition: {scene_def.id}")
    else:
        scene_def = SceneDefinition(id="garden_of_the_goddess",
                                    description="Test scene")
        print("SceneDefinition file not found — using minimal stub")

    # Single avatar: The Witness
    witness = CultivarDefinition(
        name="The Witness",
        weights={"E":0.20,"B":0.25,"P":0.35,"S":0.20},
        regulation=0.72,
        shadow_context=ShadowContext(lambda_val=0.72),
        color="#60a8f0",
        description="Epistemic humility, honest uncertainty.",
    )

    x3d = generate_scene(scene_def, [witness])
    out = write_scene(x3d)
    print(f"Scene written to: {out}")
    print(f"Lines: {len(x3d.splitlines())}")
