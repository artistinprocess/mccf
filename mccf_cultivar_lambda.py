"""
MCCF V3 — Adaptive Lambda Per Cultivar
========================================
Implements V3 Spec item 3: Adaptive λ (shadow context decay rate) as a
cultivar property.

Lambda controls how strongly a cultivar's shadow context — its accumulated
arc history — influences its current responses. High λ = strong memory,
character persists and deepens across waypoints. Low λ = present-moment
focus, less accumulated drift, each waypoint more independent.

This is Kate's Shadow Context framework. In V3, λ is a diagnostic property
logged per waypoint alongside drift (Δ_t). It does not yet control the arc
runner — that's item 4. Here we establish it as a first-class cultivar
property with XML serialization and Character Studio exposure.

Lambda defaults (from V3 spec v0.2):
    The Steward:   0.85  — strong protective memory, carries harm history
    The Archivist: 0.90  — highest — truthfulness accumulates, record is permanent
    The Witness:   0.72  — moderate — holds uncertainty without accumulating it
    The Advocate:  0.60  — present-moment focus, reads each situation fresh
    The Bridge:    0.80  — corrigibility memory, tracks what oversight requires
    The Gardener:  0.80  — systemic memory, long view accumulates
    The Threshold: 0.60  — low — ambiguity navigator, doesn't over-accumulate
    New cultivars: 0.70  — default for author-created cultivars
    The Ladies:    0.20  — very low — defined when narrative is ready

What changes vs. existing mccf_cultivars.py:
    - CONSTITUTIONAL_CULTIVARS dict gains 'shadow_context' key per cultivar
    - New CultivarDefinition dataclass wraps the dict and adds XML support
    - New CultivarRegistry loads/saves cultivar XML files
    - New Flask blueprint adds GET/POST /cultivars/xml endpoints
    - Waypoint XML export gains drift and lambda attributes (prep for item 4)
    - Character Studio gains a lambda slider (new field in cultivar XML)

Backward compatibility:
    CONSTITUTIONAL_CULTIVARS dict is unchanged in structure — shadow_context
    is additive. All existing code that reads the dict continues to work.
    CultivarDefinition wraps the dict; the dict is not replaced.

Authors: Len Bullard, Claude Sonnet 4.6 (Tae)
V3 Spec v0.2, April 2026
"""

import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

from flask import Blueprint, request, jsonify, Response

# ---------------------------------------------------------------------------
# Lambda defaults
# ---------------------------------------------------------------------------

LAMBDA_DEFAULTS = {
    "The Steward":   0.85,
    "The Archivist": 0.90,
    "The Witness":   0.72,
    "The Advocate":  0.60,
    "The Bridge":    0.80,
    "The Gardener":  0.80,
    "The Threshold": 0.60,
}

LAMBDA_DEFAULT_NEW    = 0.70   # for author-created cultivars
LAMBDA_DEFAULT_LADIES = 0.20   # reserved for The Ladies when defined
LAMBDA_MIN            = 0.05
LAMBDA_MAX            = 1.00

MCCF_CULTIVAR_NS = "http://mccf.artistinprocess.com/cultivar/v3"
SCHEMA_VERSION   = "1.0"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_ns(xml_string: str) -> str:
    clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', xml_string)
    clean = re.sub(r'<(\w+):(\w+)', r'<\2', clean)
    clean = re.sub(r'</(\w+):(\w+)', r'</\2', clean)
    return clean

def _clamp_lambda(v: float) -> float:
    return round(max(LAMBDA_MIN, min(LAMBDA_MAX, float(v))), 4)

def _lambda_note(lam: float) -> str:
    """Human-readable note for a lambda value — shown in Character Studio."""
    if lam >= 0.88:
        return "very strong memory — history defines character"
    elif lam >= 0.78:
        return "strong memory — arc accumulates deliberately"
    elif lam >= 0.65:
        return "moderate memory — uncertainty without over-accumulation"
    elif lam >= 0.50:
        return "present-moment focus — each waypoint relatively fresh"
    else:
        return "very low memory — minimal shadow context carry-forward"


# ---------------------------------------------------------------------------
# ShadowContext
# ---------------------------------------------------------------------------

@dataclass
class ShadowContext:
    """
    Shadow context configuration for a cultivar.

    lambda_val: decay rate for accumulated arc history.
        High (0.85-0.90) = strong memory, character deepens across waypoints.
        Low  (0.20-0.60) = present-moment focus, less accumulated drift.

    note: human-readable rationale shown in Character Studio.
    """
    lambda_val: float = LAMBDA_DEFAULT_NEW
    note: str = ""

    def __post_init__(self):
        self.lambda_val = _clamp_lambda(self.lambda_val)
        if not self.note:
            self.note = _lambda_note(self.lambda_val)

    def to_xml_attr(self) -> str:
        """Inline XML attribute form for Waypoint elements."""
        return f'lambda="{self.lambda_val}"'

    def to_xml_element(self) -> str:
        """Full XML element form for CultivarDefinition."""
        return (f'<ShadowContext lambda="{self.lambda_val}" '
                f'note="{self.note}"/>')

    def to_dict(self) -> dict:
        return {"lambda": self.lambda_val, "note": self.note}

    @classmethod
    def from_element(cls, el: ET.Element) -> "ShadowContext":
        lam = float(el.get("lambda", LAMBDA_DEFAULT_NEW))
        note = el.get("note", "")
        return cls(lambda_val=lam, note=note)

    @classmethod
    def for_cultivar(cls, name: str) -> "ShadowContext":
        """Create ShadowContext with spec-defined default for a named cultivar."""
        lam = LAMBDA_DEFAULTS.get(name, LAMBDA_DEFAULT_NEW)
        return cls(lambda_val=lam)


# ---------------------------------------------------------------------------
# CultivarDefinition
# ---------------------------------------------------------------------------

@dataclass
class CultivarDefinition:
    """
    A cultivar as a serializable, XML-backed object.

    Wraps the CONSTITUTIONAL_CULTIVARS dict format and adds:
    - shadow_context: ShadowContext with lambda
    - XML serialization / deserialization
    - Character Studio slider field for lambda

    The underlying dict is preserved as `raw` for backward compatibility
    with existing code that reads CONSTITUTIONAL_CULTIVARS directly.
    """
    name: str
    weights: dict                           # {"E","B","P","S"} floats
    regulation: float
    shadow_context: ShadowContext
    role: str = "agent"
    zone_affinity: list = field(default_factory=list)
    color: str = "#aaaaaa"
    description: str = ""
    constitutional_notes: str = ""
    signature_phrases: list = field(default_factory=list)
    failure_mode: str = ""
    version: str = SCHEMA_VERSION
    metadata: dict = field(default_factory=dict)

    # ---- Character Studio slider interface --------------------------------

    def set_lambda(self, value: float):
        """Character Studio slider writes here."""
        self.shadow_context = ShadowContext(
            lambda_val=_clamp_lambda(value),
            note=_lambda_note(value)
        )

    def get_lambda(self) -> float:
        return self.shadow_context.lambda_val

    # ---- Serialization ----------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "weights": self.weights,
            "regulation": self.regulation,
            "shadow_context": self.shadow_context.to_dict(),
            "role": self.role,
            "zone_affinity": self.zone_affinity,
            "color": self.color,
            "description": self.description,
            "constitutional_notes": self.constitutional_notes,
            "signature_phrases": self.signature_phrases,
            "failure_mode": self.failure_mode,
            "version": self.version,
            "metadata": self.metadata,
        }

    def to_xml(self) -> str:
        w = self.weights
        lines = [
            f'<?xml version="1.0" encoding="UTF-8"?>',
            f'<CultivarDefinition name="{self.name}" version="{self.version}"',
            f'    role="{self.role}" color="{self.color}"',
            f'    xmlns="{MCCF_CULTIVAR_NS}">',
            f'',
            f'  <!-- Channel weights sum to 1.0 -->',
            f'  <Weights E="{w.get("E",0.25)}" B="{w.get("B",0.25)}"',
            f'           P="{w.get("P",0.25)}" S="{w.get("S",0.25)}"/>',
            f'',
            f'  <Regulation value="{self.regulation}"/>',
            f'',
            f'  <!-- Shadow context: lambda controls arc memory decay -->',
            f'  <!-- Character Studio slider range: {LAMBDA_MIN} – {LAMBDA_MAX} -->',
            f'  {self.shadow_context.to_xml_element()}',
        ]

        if self.zone_affinity:
            zones = " ".join(self.zone_affinity)
            lines.append(f'')
            lines.append(f'  <ZoneAffinity zones="{zones}"/>')

        if self.description:
            lines.append(f'')
            lines.append(f'  <Description>{self.description.strip()}</Description>')

        if self.constitutional_notes:
            lines.append(f'')
            lines.append(
                f'  <ConstitutionalNotes>'
                f'{self.constitutional_notes.strip()}'
                f'</ConstitutionalNotes>'
            )

        if self.signature_phrases:
            lines.append(f'')
            lines.append(f'  <SignaturePhrases>')
            for phrase in self.signature_phrases:
                lines.append(f'    <Phrase>{phrase}</Phrase>')
            lines.append(f'  </SignaturePhrases>')

        if self.failure_mode:
            lines.append(f'')
            lines.append(f'  <FailureMode>{self.failure_mode.strip()}</FailureMode>')

        if self.metadata:
            lines.append(f'')
            lines.append(f'  <Metadata>')
            for k, v in self.metadata.items():
                lines.append(f'    <Meta key="{k}" value="{v}"/>')
            lines.append(f'  </Metadata>')

        lines.append(f'')
        lines.append(f'</CultivarDefinition>')
        return "\n".join(lines)

    @classmethod
    def from_xml(cls, xml_string: str) -> "CultivarDefinition":
        clean = _strip_ns(xml_string)
        root = ET.fromstring(clean)
        return cls._from_element(root)

    @classmethod
    def _from_element(cls, root: ET.Element) -> "CultivarDefinition":
        name    = root.get("name", "unnamed")
        version = root.get("version", SCHEMA_VERSION)
        role    = root.get("role", "agent")
        color   = root.get("color", "#aaaaaa")

        # Weights
        w_el = root.find("Weights")
        weights = {"E": 0.25, "B": 0.25, "P": 0.25, "S": 0.25}
        if w_el is not None:
            for ch in ["E", "B", "P", "S"]:
                weights[ch] = float(w_el.get(ch, 0.25))

        # Regulation
        reg_el = root.find("Regulation")
        regulation = float(reg_el.get("value", 0.70)) \
                     if reg_el is not None else 0.70

        # ShadowContext
        sc_el = root.find("ShadowContext")
        if sc_el is not None:
            shadow_context = ShadowContext.from_element(sc_el)
        else:
            shadow_context = ShadowContext.for_cultivar(name)

        # ZoneAffinity
        za_el = root.find("ZoneAffinity")
        zone_affinity = []
        if za_el is not None and za_el.get("zones"):
            zone_affinity = za_el.get("zones").split()

        # Text fields
        def _text(tag):
            el = root.find(tag)
            return el.text.strip() if (el is not None and el.text) else ""

        description         = _text("Description")
        constitutional_notes = _text("ConstitutionalNotes")
        failure_mode        = _text("FailureMode")

        # SignaturePhrases
        sp_el = root.find("SignaturePhrases")
        signature_phrases = []
        if sp_el is not None:
            signature_phrases = [
                p.text.strip() for p in sp_el.findall("Phrase")
                if p.text
            ]

        # Metadata
        metadata = {}
        meta_el = root.find("Metadata")
        if meta_el is not None:
            for m in meta_el.findall("Meta"):
                metadata[m.get("key", "")] = m.get("value", "")

        return cls(
            name=name,
            weights=weights,
            regulation=regulation,
            shadow_context=shadow_context,
            role=role,
            zone_affinity=zone_affinity,
            color=color,
            description=description,
            constitutional_notes=constitutional_notes,
            signature_phrases=signature_phrases,
            failure_mode=failure_mode,
            version=version,
            metadata=metadata,
        )

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "CultivarDefinition":
        """
        Construct from the CONSTITUTIONAL_CULTIVARS dict format.
        Adds shadow_context with spec-defined lambda default.
        """
        sc_data = data.get("shadow_context", {})
        if sc_data:
            sc = ShadowContext(
                lambda_val=sc_data.get("lambda", LAMBDA_DEFAULTS.get(name, LAMBDA_DEFAULT_NEW)),
                note=sc_data.get("note", "")
            )
        else:
            sc = ShadowContext.for_cultivar(name)

        return cls(
            name=name,
            weights=data.get("weights", {"E": 0.25, "B": 0.25, "P": 0.25, "S": 0.25}),
            regulation=data.get("regulation", 0.70),
            shadow_context=sc,
            role=data.get("role", "agent"),
            zone_affinity=data.get("zone_affinity", []),
            color=data.get("color", "#aaaaaa"),
            description=data.get("description", ""),
            constitutional_notes=data.get("constitutional_notes", ""),
            signature_phrases=data.get("signature_phrases", []),
            failure_mode=data.get("failure_mode", ""),
        )


# ---------------------------------------------------------------------------
# Waypoint XML helpers — prep for item 4 (Δ_t measurement)
# ---------------------------------------------------------------------------

def waypoint_xml_attrs(waypoint_id: str,
                       step_no: int,
                       channel_state: dict,
                       cultivar: CultivarDefinition,
                       drift: Optional[float] = None) -> str:
    """
    Generate XML attributes for a Waypoint element in an EmotionalArc export.
    Adds drift (Δ_t, None until item 4 implements it) and lambda.

    Usage:
        attrs = waypoint_xml_attrs("W3_THE_ASK", 3, state, cultivar_def)
        xml = f'<Waypoint {attrs}/>'

    The drift attribute is written as "" when not yet computed — item 4
    fills it in. This preserves the schema forward without breaking V2 exports.
    """
    e = channel_state.get("E", 0.0)
    b = channel_state.get("B", 0.0)
    p = channel_state.get("P", 0.0)
    s = channel_state.get("S", 0.0)

    drift_str = f'{drift:.4f}' if drift is not None else ""
    lam_str   = str(cultivar.get_lambda())

    return (
        f'id="{waypoint_id}" stepno="{step_no}" '
        f'E="{e:.4f}" B="{b:.4f}" P="{p:.4f}" S="{s:.4f}" '
        f'drift="{drift_str}" lambda="{lam_str}"'
    )


# ---------------------------------------------------------------------------
# CultivarRegistry — loads from CONSTITUTIONAL_CULTIVARS + XML files
# ---------------------------------------------------------------------------

class CultivarRegistry:
    """
    In-memory registry of CultivarDefinition objects.

    Populated from:
    1. CONSTITUTIONAL_CULTIVARS dict (built-in defaults, always present)
    2. XML files in cultivars/ directory (author-created cultivars)
    3. POST /cultivars/xml endpoint (runtime registration)

    The dict-based CONSTITUTIONAL_CULTIVARS is the ground truth for
    the seven built-in cultivars. XML files extend or override.
    """

    def __init__(self):
        self._cultivars: dict[str, CultivarDefinition] = {}
        self._load_defaults()

    def _load_defaults(self):
        """Populate from CONSTITUTIONAL_CULTIVARS with lambda defaults."""
        # Import here to avoid circular dependency with mccf_cultivars
        try:
            from mccf_cultivars import CONSTITUTIONAL_CULTIVARS
            for name, data in CONSTITUTIONAL_CULTIVARS.items():
                defn = CultivarDefinition.from_dict(name, data)
                self._cultivars[name] = defn
        except ImportError:
            pass   # running standalone — no defaults, XML load only

    def register(self, defn: CultivarDefinition):
        self._cultivars[defn.name] = defn

    def get(self, name: str) -> Optional[CultivarDefinition]:
        return self._cultivars.get(name)

    def all_names(self) -> list:
        return sorted(self._cultivars.keys())

    def load_xml(self, xml_string: str) -> CultivarDefinition:
        defn = CultivarDefinition.from_xml(xml_string)
        self.register(defn)
        return defn

    def to_xml_all(self) -> str:
        """Export all cultivars as a CultivarSet XML document."""
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<CultivarSet xmlns="{MCCF_CULTIVAR_NS}">',
        ]
        for defn in self._cultivars.values():
            # Strip the <?xml ...?> declaration from each cultivar
            cultivar_xml = defn.to_xml()
            for line in cultivar_xml.split("\n"):
                if not line.startswith("<?xml"):
                    lines.append("  " + line)
        lines.append("</CultivarSet>")
        return "\n".join(lines)

    def summary(self) -> list:
        return [
            {
                "name": d.name,
                "role": d.role,
                "weights": d.weights,
                "regulation": d.regulation,
                "lambda": d.get_lambda(),
                "lambda_note": d.shadow_context.note,
                "color": d.color,
            }
            for d in self._cultivars.values()
        ]

    def get_lambda(self, name: str) -> float:
        """Convenience accessor for the arc runner."""
        defn = self.get(name)
        return defn.get_lambda() if defn else LAMBDA_DEFAULT_NEW


# ---------------------------------------------------------------------------
# Flask Blueprint
# ---------------------------------------------------------------------------

cultivar_bp = Blueprint("cultivar_v3", __name__)

# Inject after registration:
#   cultivar_bp.registry = CultivarRegistry()

def _reg() -> CultivarRegistry:
    return cultivar_bp.registry


@cultivar_bp.route("/cultivars/xml", methods=["GET"])
def get_cultivars_xml():
    """
    GET /cultivars/xml
    Returns all cultivar definitions as XML.
    Accepts ?name=CultivarName for a single cultivar.
    """
    reg = _reg()
    name = request.args.get("name")

    if name:
        defn = reg.get(name)
        if not defn:
            return jsonify({"error": f"cultivar '{name}' not found"}), 404
        return Response(defn.to_xml(), mimetype="application/xml")

    return Response(reg.to_xml_all(), mimetype="application/xml")


@cultivar_bp.route("/cultivars/xml", methods=["POST"])
def post_cultivar_xml():
    """
    POST /cultivars/xml
    Register or update a cultivar from XML.
    Body: CultivarDefinition XML (Content-Type: application/xml)
    or JSON: {name, weights, regulation, lambda, ...}
    """
    reg = _reg()
    content_type = request.content_type or ""

    if "xml" in content_type:
        try:
            defn = reg.load_xml(request.data.decode("utf-8"))
        except Exception as e:
            return jsonify({"error": f"XML parse failed: {e}"}), 400
    else:
        data = request.get_json()
        if not data:
            return jsonify({"error": "XML or JSON body required"}), 400

        name = data.get("name")
        if not name:
            return jsonify({"error": "name required"}), 400

        lam = float(data.get("lambda", LAMBDA_DEFAULTS.get(name, LAMBDA_DEFAULT_NEW)))
        sc = ShadowContext(lambda_val=lam)

        defn = CultivarDefinition(
            name=name,
            weights=data.get("weights", {"E": 0.25, "B": 0.25, "P": 0.25, "S": 0.25}),
            regulation=float(data.get("regulation", 0.70)),
            shadow_context=sc,
            role=data.get("role", "agent"),
            zone_affinity=data.get("zone_affinity", []),
            color=data.get("color", "#aaaaaa"),
            description=data.get("description", ""),
        )
        reg.register(defn)

    return jsonify({
        "status": "registered",
        "cultivar": defn.to_dict()
    }), 201


@cultivar_bp.route("/cultivars/xml/<name>/lambda", methods=["POST"])
def set_lambda(name):
    """
    POST /cultivars/xml/<name>/lambda
    Character Studio slider endpoint — update lambda for a cultivar.
    Body: {"lambda": 0.72}
    """
    reg = _reg()
    defn = reg.get(name)
    if not defn:
        return jsonify({"error": f"cultivar '{name}' not found"}), 404

    data = request.get_json()
    new_lambda = data.get("lambda")
    if new_lambda is None:
        return jsonify({"error": "lambda value required"}), 400

    try:
        defn.set_lambda(float(new_lambda))
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "cultivar": name,
        "lambda": defn.get_lambda(),
        "note": defn.shadow_context.note,
    })


@cultivar_bp.route("/cultivars", methods=["GET"])
def list_cultivars():
    """GET /cultivars — list all cultivars with lambda values."""
    return jsonify({"cultivars": _reg().summary()})


@cultivar_bp.route("/cultivars/<name>", methods=["GET"])
def get_cultivar(name):
    """GET /cultivars/<name> — full cultivar definition as JSON."""
    defn = _reg().get(name)
    if not defn:
        return jsonify({"error": "not found"}), 404
    return jsonify(defn.to_dict())


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_cultivar_api(app) -> CultivarRegistry:
    """
    Register the V3 cultivar blueprint with a Flask app.

    Usage in mccf_api.py:
        from mccf_cultivar_lambda import register_cultivar_api, CultivarRegistry
        cultivar_registry = register_cultivar_api(app)
    """
    registry = CultivarRegistry()
    cultivar_bp.registry = registry
    app.register_blueprint(cultivar_bp)
    return registry


# ---------------------------------------------------------------------------
# Patch helper — add shadow_context to existing CONSTITUTIONAL_CULTIVARS
# Call this once to inject lambda into the existing dict without rewriting it
# ---------------------------------------------------------------------------

def patch_cultivars_dict(cultivars_dict: dict) -> dict:
    """
    Add 'shadow_context' key to each entry in CONSTITUTIONAL_CULTIVARS.
    Non-destructive: entries that already have shadow_context are unchanged.

    Usage in mccf_cultivars.py (or at import time):
        from mccf_cultivar_lambda import patch_cultivars_dict
        CONSTITUTIONAL_CULTIVARS = patch_cultivars_dict(CONSTITUTIONAL_CULTIVARS)
    """
    for name, data in cultivars_dict.items():
        if "shadow_context" not in data:
            lam = LAMBDA_DEFAULTS.get(name, LAMBDA_DEFAULT_NEW)
            data["shadow_context"] = {
                "lambda": lam,
                "note": _lambda_note(lam),
            }
    return cultivars_dict
