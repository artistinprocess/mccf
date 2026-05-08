"""
MCCF V3 Scene XML Wrapper
==========================
Implements V3 Spec item 2: Scene XML Wrapper.

Two document types with separate lifecycles:

SceneDefinition  — reusable scene template authored in Scene Composer.
                   Contains zones, spatial layout, sound node references.
                   No agents, no arc data, no episode history.
                   Stable across episodes. Load once, reuse many times.

SceneEpisode     — per-run record produced by the arc runner.
                   References a SceneDefinition by scene_ref idref.
                   Contains one or more EmotionalArc elements, agent
                   assignments, mode, timestamp.
                   Historical record. Never modified after export.

Separation rationale:
    Scene geometry and zone configuration have a different lifecycle than
    episode records. A SceneDefinition can be shared across many episodes
    without copying zone data. SceneEpisode records what happened;
    SceneDefinition records where and under what conditions it could happen.

XML structure:

    SceneDefinition:
        <SceneDefinition id="garden_of_the_goddess" version="1.0"
                         created="2026-05-01" author="Len Bullard">
          <Description>...</Description>
          <ZoneSet>
            <Zone id="the_temple" zone_type="sacred">...</Zone>
            ...
          </ZoneSet>
          <!-- Optional: ZoneRef for externally-defined zones -->
          <ZoneRef href="zones/shared_temple.xml" zone_id="the_temple"/>
        </SceneDefinition>

    SceneEpisode:
        <SceneEpisode id="session_001"
                      scene_ref="garden_of_the_goddess"
                      timestamp="2026-05-01T20:00:00"
                      mode="improvisation"
                      version="1.0">
          <EmotionalArc cultivar="The Witness" actor="ollama"
                        voice="Microsoft David"/>
          <!-- multi-agent: additional EmotionalArc elements -->
        </SceneEpisode>

Backward compatibility:
    Existing bare EmotionalArc exports remain valid.
    The arc runner wraps them in SceneEpisode on export — existing files
    are not modified.

New endpoints (registered as Flask Blueprint):
    GET  /scene/definition              list loaded SceneDefinitions
    POST /scene/definition              load a SceneDefinition (JSON or XML)
    GET  /scene/definition/<id>         get a SceneDefinition
    GET  /scene/definition/<id>/xml     export SceneDefinition as XML
    GET  /scene/episode                 list SceneEpisodes
    POST /scene/episode                 create a SceneEpisode
    GET  /scene/episode/<id>            get a SceneEpisode
    GET  /scene/episode/<id>/xml        export SceneEpisode as XML
    POST /scene/episode/<id>/arc        attach an EmotionalArc to episode

Authors: Len Bullard, Claude Sonnet 4.6 (Tae)
V3 Spec v0.2, April 2026
"""

import re
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from flask import Blueprint, request, jsonify, Response

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MCCF_SCENE_NS  = "http://mccf.artistinprocess.com/scene/v3"
MCCF_ZONE_NS   = "http://mccf.artistinprocess.com/zones/v3"
SCHEMA_VERSION = "1.0"

VALID_MODES = {"improvisation", "playback", "live_theatre"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _strip_ns(xml_string: str) -> str:
    """Remove XML namespace declarations and prefixes for simple parsing."""
    clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', xml_string)
    clean = re.sub(r'<(\w+):(\w+)', r'<\2', clean)
    clean = re.sub(r'</(\w+):(\w+)', r'</\2', clean)
    return clean

def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line
                     for line in text.split("\n"))


# ---------------------------------------------------------------------------
# ZoneRef — pointer to an externally-defined zone file
# ---------------------------------------------------------------------------

@dataclass
class ZoneRef:
    """
    Optional lightweight reference to a zone defined in an external file.
    Allows SceneDefinitions to include zones without copying their XML.
    The loader resolves hrefs relative to the zones/ directory.
    """
    href: str       # relative path, e.g. "zones/shared_temple.xml"
    zone_id: str    # the Zone/@id inside that file

    def to_xml(self) -> str:
        return f'<ZoneRef href="{self.href}" zone_id="{self.zone_id}"/>'

    def to_dict(self) -> dict:
        return {"href": self.href, "zone_id": self.zone_id}

    @classmethod
    def from_element(cls, el: ET.Element) -> "ZoneRef":
        return cls(
            href=el.get("href", ""),
            zone_id=el.get("zone_id", ""),
        )


# ---------------------------------------------------------------------------
# ArcRef — lightweight record of an EmotionalArc in a SceneEpisode
# ---------------------------------------------------------------------------

@dataclass
class ArcRef:
    """
    Reference to an EmotionalArc within a SceneEpisode.
    Stores the full arc XML inline (small documents) or a path to an
    external export file for large arc exports.
    """
    cultivar: str
    actor: str                          # ollama, anthropic, openai, stub, etc.
    voice: str = ""
    arc_file: str = ""                  # path to external EmotionalArc export
    inline_xml: str = ""               # or the arc XML inline

    def to_xml(self) -> str:
        attrs = f'cultivar="{self.cultivar}" actor="{self.actor}"'
        if self.voice:
            attrs += f' voice="{self.voice}"'
        if self.arc_file:
            attrs += f' arc_file="{self.arc_file}"'
        if self.inline_xml:
            return (f'<EmotionalArc {attrs}>\n'
                    f'{_indent(self.inline_xml, 2)}\n'
                    f'</EmotionalArc>')
        return f'<EmotionalArc {attrs}/>'

    def to_dict(self) -> dict:
        return {
            "cultivar": self.cultivar,
            "actor": self.actor,
            "voice": self.voice,
            "arc_file": self.arc_file,
            "has_inline_xml": bool(self.inline_xml),
        }

    @classmethod
    def from_element(cls, el: ET.Element) -> "ArcRef":
        inline = ""
        if len(el):   # has child elements — inline arc data
            inline = ET.tostring(el[0], encoding="unicode")
        return cls(
            cultivar=el.get("cultivar", ""),
            actor=el.get("actor", "stub"),
            voice=el.get("voice", ""),
            arc_file=el.get("arc_file", ""),
            inline_xml=inline,
        )


# ---------------------------------------------------------------------------
# SceneDefinition
# ---------------------------------------------------------------------------

@dataclass
class SceneDefinition:
    """
    Reusable scene template. Exported by Scene Composer.
    Contains zone configuration. No agents, no arc data.

    zone_xml_blocks: list of raw Zone XML strings (inline zones)
    zone_refs: list of ZoneRef (external zone files)
    """
    id: str
    version: str = SCHEMA_VERSION
    created: str = field(default_factory=lambda: _now_iso()[:10])
    author: str = ""
    description: str = ""
    zone_xml_blocks: list = field(default_factory=list)   # list of str
    zone_refs: list = field(default_factory=list)         # list of ZoneRef
    metadata: dict = field(default_factory=dict)          # extensible

    def to_xml(self) -> str:
        attrs = (
            f'id="{self.id}" version="{self.version}" '
            f'created="{self.created}"'
        )
        if self.author:
            attrs += f' author="{self.author}"'

        lines = [
            f'<?xml version="1.0" encoding="UTF-8"?>',
            f'<SceneDefinition {attrs}',
            f'    xmlns="{MCCF_SCENE_NS}">',
        ]

        if self.description:
            lines.append(f'  <Description>{self.description}</Description>')

        if self.zone_xml_blocks or self.zone_refs:
            lines.append('  <ZoneSet>')
            for zxml in self.zone_xml_blocks:
                for line in zxml.strip().split("\n"):
                    lines.append("    " + line)
            for zref in self.zone_refs:
                lines.append("    " + zref.to_xml())
            lines.append('  </ZoneSet>')

        if self.metadata:
            lines.append('  <Metadata>')
            for k, v in self.metadata.items():
                lines.append(f'    <Meta key="{k}" value="{v}"/>')
            lines.append('  </Metadata>')

        lines.append('</SceneDefinition>')
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "version": self.version,
            "created": self.created,
            "author": self.author,
            "description": self.description,
            "zone_count": len(self.zone_xml_blocks),
            "zone_refs": [z.to_dict() for z in self.zone_refs],
            "metadata": self.metadata,
        }

    @classmethod
    def from_xml(cls, xml_string: str) -> "SceneDefinition":
        clean = _strip_ns(xml_string)
        root = ET.fromstring(clean)

        scene_id  = root.get("id", f"scene_{uuid.uuid4().hex[:8]}")
        version   = root.get("version", SCHEMA_VERSION)
        created   = root.get("created", _now_iso()[:10])
        author    = root.get("author", "")

        desc_el = root.find("Description")
        description = desc_el.text.strip() \
                      if (desc_el is not None and desc_el.text) else ""

        zone_xml_blocks = []
        zone_refs = []

        zoneset_el = root.find("ZoneSet")
        if zoneset_el is not None:
            for child in zoneset_el:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag == "Zone":
                    zone_xml_blocks.append(ET.tostring(child, encoding="unicode"))
                elif tag == "ZoneRef":
                    zone_refs.append(ZoneRef.from_element(child))

        metadata = {}
        meta_el = root.find("Metadata")
        if meta_el is not None:
            for m in meta_el.findall("Meta"):
                metadata[m.get("key", "")] = m.get("value", "")

        return cls(
            id=scene_id,
            version=version,
            created=created,
            author=author,
            description=description,
            zone_xml_blocks=zone_xml_blocks,
            zone_refs=zone_refs,
            metadata=metadata,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "SceneDefinition":
        return cls(
            id=data.get("id", f"scene_{uuid.uuid4().hex[:8]}"),
            version=data.get("version", SCHEMA_VERSION),
            created=data.get("created", _now_iso()[:10]),
            author=data.get("author", ""),
            description=data.get("description", ""),
            zone_xml_blocks=data.get("zone_xml_blocks", []),
            zone_refs=[ZoneRef(**z) for z in data.get("zone_refs", [])],
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# SceneEpisode
# ---------------------------------------------------------------------------

@dataclass
class SceneEpisode:
    """
    Per-run record. Exported by the arc runner after a session.
    References a SceneDefinition by scene_ref idref.
    Contains arc references (one per agent/cultivar in the session).
    Never modified after export.
    """
    id: str
    scene_ref: str                              # SceneDefinition/@id
    timestamp: str = field(default_factory=_now_iso)
    mode: str = "improvisation"
    version: str = SCHEMA_VERSION
    arcs: list = field(default_factory=list)    # list of ArcRef
    notes: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.mode not in VALID_MODES:
            raise ValueError(
                f"Invalid mode '{self.mode}'. "
                f"Must be one of: {sorted(VALID_MODES)}"
            )

    def add_arc(self, arc: ArcRef):
        self.arcs.append(arc)

    def to_xml(self) -> str:
        attrs = (
            f'id="{self.id}" scene_ref="{self.scene_ref}" '
            f'timestamp="{self.timestamp}" mode="{self.mode}" '
            f'version="{self.version}"'
        )
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<SceneEpisode {attrs}',
            f'    xmlns="{MCCF_SCENE_NS}">',
        ]

        if self.notes:
            lines.append(f'  <Notes>{self.notes}</Notes>')

        for arc in self.arcs:
            for line in arc.to_xml().split("\n"):
                lines.append("  " + line)

        if self.metadata:
            lines.append('  <Metadata>')
            for k, v in self.metadata.items():
                lines.append(f'    <Meta key="{k}" value="{v}"/>')
            lines.append('  </Metadata>')

        lines.append('</SceneEpisode>')
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "scene_ref": self.scene_ref,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "version": self.version,
            "arc_count": len(self.arcs),
            "arcs": [a.to_dict() for a in self.arcs],
            "notes": self.notes,
            "metadata": self.metadata,
        }

    @classmethod
    def from_xml(cls, xml_string: str) -> "SceneEpisode":
        clean = _strip_ns(xml_string)
        root = ET.fromstring(clean)

        episode_id = root.get("id", f"episode_{uuid.uuid4().hex[:8]}")
        scene_ref  = root.get("scene_ref", "")
        timestamp  = root.get("timestamp", _now_iso())
        mode       = root.get("mode", "improvisation")
        version    = root.get("version", SCHEMA_VERSION)

        if mode not in VALID_MODES:
            mode = "improvisation"

        notes_el = root.find("Notes")
        notes = notes_el.text.strip() \
                if (notes_el is not None and notes_el.text) else ""

        arcs = []
        for el in root.findall("EmotionalArc"):
            arcs.append(ArcRef.from_element(el))

        metadata = {}
        meta_el = root.find("Metadata")
        if meta_el is not None:
            for m in meta_el.findall("Meta"):
                metadata[m.get("key", "")] = m.get("value", "")

        ep = cls(
            id=episode_id,
            scene_ref=scene_ref,
            timestamp=timestamp,
            mode=mode,
            version=version,
            notes=notes,
            metadata=metadata,
        )
        ep.arcs = arcs
        return ep

    @classmethod
    def from_dict(cls, data: dict) -> "SceneEpisode":
        ep = cls(
            id=data.get("id", f"episode_{uuid.uuid4().hex[:8]}"),
            scene_ref=data.get("scene_ref", ""),
            timestamp=data.get("timestamp", _now_iso()),
            mode=data.get("mode", "improvisation"),
            version=data.get("version", SCHEMA_VERSION),
            notes=data.get("notes", ""),
            metadata=data.get("metadata", {}),
        )
        for a in data.get("arcs", []):
            ep.arcs.append(ArcRef(**{k: v for k, v in a.items()
                                     if k in ArcRef.__dataclass_fields__}))
        return ep


# ---------------------------------------------------------------------------
# SceneRegistry — in-memory store for definitions and episodes
# ---------------------------------------------------------------------------

class SceneRegistry:
    """
    In-memory store for SceneDefinitions and SceneEpisodes.
    Definitions are keyed by id (reused across sessions).
    Episodes are keyed by id (append-only, historical records).
    """

    def __init__(self):
        self.definitions: dict[str, SceneDefinition] = {}
        self.episodes: dict[str, SceneEpisode] = {}

    # -- definitions --------------------------------------------------------

    def register_definition(self, defn: SceneDefinition):
        self.definitions[defn.id] = defn

    def get_definition(self, scene_id: str) -> Optional[SceneDefinition]:
        return self.definitions.get(scene_id)

    def load_definition_xml(self, xml_string: str) -> SceneDefinition:
        defn = SceneDefinition.from_xml(xml_string)
        self.register_definition(defn)
        return defn

    # -- episodes -----------------------------------------------------------

    def create_episode(self, scene_ref: str, mode: str = "improvisation",
                       notes: str = "", **kwargs) -> SceneEpisode:
        if scene_ref not in self.definitions:
            raise ValueError(
                f"SceneDefinition '{scene_ref}' not loaded. "
                f"Load it before creating an episode."
            )
        ep = SceneEpisode(
            id=f"episode_{uuid.uuid4().hex[:8]}",
            scene_ref=scene_ref,
            mode=mode,
            notes=notes,
            **kwargs,
        )
        self.episodes[ep.id] = ep
        return ep

    def get_episode(self, episode_id: str) -> Optional[SceneEpisode]:
        return self.episodes.get(episode_id)

    def load_episode_xml(self, xml_string: str) -> SceneEpisode:
        ep = SceneEpisode.from_xml(xml_string)
        self.episodes[ep.id] = ep
        return ep

    def episodes_for_scene(self, scene_id: str) -> list:
        return [ep for ep in self.episodes.values()
                if ep.scene_ref == scene_id]

    def summary(self) -> dict:
        return {
            "definitions": {k: v.to_dict()
                            for k, v in self.definitions.items()},
            "episode_count": len(self.episodes),
            "episodes_by_scene": {
                sid: [ep.id for ep in self.episodes_for_scene(sid)]
                for sid in self.definitions
            },
        }


# ---------------------------------------------------------------------------
# Flask Blueprint
# ---------------------------------------------------------------------------

scene_bp = Blueprint("scene_v3", __name__)

# Inject after registration:
#   scene_bp.registry = SceneRegistry()

def _reg() -> SceneRegistry:
    return scene_bp.registry


# ── SceneDefinition endpoints ──────────────────────────────────────────────

@scene_bp.route("/scene/definition", methods=["GET"])
def list_definitions():
    reg = _reg()
    return jsonify({
        "definitions": [d.to_dict() for d in reg.definitions.values()]
    })


@scene_bp.route("/scene/definition", methods=["POST"])
def create_definition():
    """
    Load a SceneDefinition from XML or JSON.
    XML body: Content-Type application/xml
    JSON body: {id, description, author, zone_xml_blocks, zone_refs, metadata}
    """
    reg = _reg()
    content_type = request.content_type or ""

    if "xml" in content_type:
        try:
            defn = reg.load_definition_xml(request.data.decode("utf-8"))
        except Exception as e:
            return jsonify({"error": f"XML parse failed: {e}"}), 400
    else:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON or XML body required"}), 400
        if not data.get("id"):
            return jsonify({"error": "id required"}), 400
        try:
            defn = SceneDefinition.from_dict(data)
            reg.register_definition(defn)
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    return jsonify({"status": "loaded", "definition": defn.to_dict()}), 201


@scene_bp.route("/scene/definition/<scene_id>", methods=["GET"])
def get_definition(scene_id):
    defn = _reg().get_definition(scene_id)
    if not defn:
        return jsonify({"error": "not found"}), 404
    return jsonify(defn.to_dict())


@scene_bp.route("/scene/definition/<scene_id>/xml", methods=["GET"])
def export_definition_xml(scene_id):
    defn = _reg().get_definition(scene_id)
    if not defn:
        return jsonify({"error": "not found"}), 404
    return Response(defn.to_xml(), mimetype="application/xml")


# ── SceneEpisode endpoints ─────────────────────────────────────────────────

@scene_bp.route("/scene/episode", methods=["GET"])
def list_episodes():
    reg = _reg()
    scene_filter = request.args.get("scene_ref")
    if scene_filter:
        eps = reg.episodes_for_scene(scene_filter)
    else:
        eps = list(reg.episodes.values())
    return jsonify({"episodes": [ep.to_dict() for ep in eps]})


@scene_bp.route("/scene/episode", methods=["POST"])
def create_episode():
    """
    Create a SceneEpisode.
    XML body: Content-Type application/xml — loads a full SceneEpisode doc
    JSON body: {scene_ref, mode, notes, arcs: [{cultivar, actor, voice}]}
    """
    reg = _reg()
    content_type = request.content_type or ""

    if "xml" in content_type:
        try:
            ep = reg.load_episode_xml(request.data.decode("utf-8"))
        except Exception as e:
            return jsonify({"error": f"XML parse failed: {e}"}), 400
    else:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON or XML body required"}), 400

        scene_ref = data.get("scene_ref")
        if not scene_ref:
            return jsonify({"error": "scene_ref required"}), 400

        try:
            ep = reg.create_episode(
                scene_ref=scene_ref,
                mode=data.get("mode", "improvisation"),
                notes=data.get("notes", ""),
                metadata=data.get("metadata", {}),
            )
            for arc_data in data.get("arcs", []):
                ep.add_arc(ArcRef(
                    cultivar=arc_data.get("cultivar", ""),
                    actor=arc_data.get("actor", "stub"),
                    voice=arc_data.get("voice", ""),
                    arc_file=arc_data.get("arc_file", ""),
                ))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    return jsonify({"status": "created", "episode": ep.to_dict()}), 201


@scene_bp.route("/scene/episode/<episode_id>", methods=["GET"])
def get_episode(episode_id):
    ep = _reg().get_episode(episode_id)
    if not ep:
        return jsonify({"error": "not found"}), 404
    return jsonify(ep.to_dict())


@scene_bp.route("/scene/episode/<episode_id>/xml", methods=["GET"])
def export_episode_xml(episode_id):
    ep = _reg().get_episode(episode_id)
    if not ep:
        return jsonify({"error": "not found"}), 404
    return Response(ep.to_xml(), mimetype="application/xml")


@scene_bp.route("/scene/episode/<episode_id>/arc", methods=["POST"])
def attach_arc(episode_id):
    """
    Attach an EmotionalArc to an existing episode.
    Body: {cultivar, actor, voice, arc_file} or inline arc XML.
    """
    ep = _reg().get_episode(episode_id)
    if not ep:
        return jsonify({"error": "episode not found"}), 404

    content_type = request.content_type or ""
    if "xml" in content_type:
        try:
            el = ET.fromstring(_strip_ns(request.data.decode("utf-8")))
            arc = ArcRef.from_element(el)
        except Exception as e:
            return jsonify({"error": f"XML parse failed: {e}"}), 400
    else:
        data = request.get_json()
        if not data:
            return jsonify({"error": "body required"}), 400
        arc = ArcRef(
            cultivar=data.get("cultivar", ""),
            actor=data.get("actor", "stub"),
            voice=data.get("voice", ""),
            arc_file=data.get("arc_file", ""),
        )

    ep.add_arc(arc)
    return jsonify({"status": "attached", "episode": ep.to_dict()})


@scene_bp.route("/scene", methods=["GET"])
def scene_summary():
    return jsonify(_reg().summary())


# ---------------------------------------------------------------------------
# Registration helper — call this in mccf_api.py
# ---------------------------------------------------------------------------

def register_scene_api(app) -> SceneRegistry:
    """
    Register the V3 scene blueprint with a Flask app.

    Usage in mccf_api.py:
        from mccf_scene_wrapper import register_scene_api
        scene_registry = register_scene_api(app)

        # Load Garden of the Goddess definition at startup:
        with open("scenes/garden_of_the_goddess_def.xml") as f:
            scene_registry.load_definition_xml(f.read())
    """
    registry = SceneRegistry()
    scene_bp.registry = registry
    app.register_blueprint(scene_bp)
    return registry
