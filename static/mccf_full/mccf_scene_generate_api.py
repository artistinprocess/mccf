"""
MCCF V3 Scene Generate API
============================
One endpoint: POST /scene/generate

Called by Scene Composer's "Generate Scene" button.
Reads a SceneDefinition from the scenes/ directory,
loads cultivar definitions, runs the X3D generator,
writes static/mccf_scene.x3d, returns status.

Flow:
    Scene Composer UI
        → POST /scene/generate {"scene_id": "garden_of_the_goddess",
                                 "cultivars": ["The Witness"],
                                 "api_url": "http://localhost:5000"}
        → reads scenes/garden_of_the_goddess_def.xml
        → loads cultivar definitions from registry or cultivars/ dir
        → generate_scene(scene_def, cultivar_defs, api_url)
        → write_scene(x3d, "static/mccf_scene.x3d")
        → returns {"status":"ok","output":"static/mccf_scene.x3d","lines":N}

    Launcher then loads static/mccf_scene.x3d as before.

Also provides:
    GET /scene/generate/scenes    — list available SceneDefinition files
    GET /scene/generate/cultivars — list available cultivar names

Register in mccf_api.py:
    from mccf_scene_generate_api import register_generate_api
    register_generate_api(app)

Authors: Len Bullard, Claude Sonnet 4.6 (Tae)
V3 Spec v0.2, April 2026
"""

import os
import glob

from flask import Blueprint, request, jsonify

from mccf_scene_wrapper import SceneDefinition
from mccf_cultivar_lambda import CultivarDefinition, CultivarRegistry, ShadowContext
from mccf_x3d_generator import generate_scene, write_scene, DEFAULT_OUTPUT_PATH

# ---------------------------------------------------------------------------
# Paths — relative to repo root
# ---------------------------------------------------------------------------

REPO_ROOT    = os.path.dirname(os.path.abspath(__file__))
SCENES_DIR   = os.path.join(REPO_ROOT, "scenes")
CULTIVARS_DIR = os.path.join(REPO_ROOT, "cultivars")
OUTPUT_PATH  = DEFAULT_OUTPUT_PATH   # static/mccf_scene.x3d

# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------

generate_bp = Blueprint("scene_generate", __name__)

# Shared cultivar registry — populated from CONSTITUTIONAL_CULTIVARS
# and any XML files in cultivars/ directory
_cultivar_registry: CultivarRegistry | None = None

def _get_registry() -> CultivarRegistry:
    global _cultivar_registry
    if _cultivar_registry is None:
        _cultivar_registry = CultivarRegistry()
        # Load any XML cultivar files from cultivars/ directory
        if os.path.isdir(CULTIVARS_DIR):
            for fpath in glob.glob(os.path.join(CULTIVARS_DIR, "*.xml")):
                try:
                    with open(fpath, encoding="utf-8") as f:
                        _cultivar_registry.load_xml(f.read())
                except Exception as e:
                    print(f"Warning: could not load cultivar {fpath}: {e}")
    return _cultivar_registry


def _load_scene_def(scene_id: str) -> SceneDefinition:
    """
    Load a SceneDefinition from scenes/<scene_id>_def.xml or scenes/<scene_id>.xml.
    Raises FileNotFoundError if neither exists.
    """
    candidates = [
        os.path.join(SCENES_DIR, f"{scene_id}_def.xml"),
        os.path.join(SCENES_DIR, f"{scene_id}.xml"),
        os.path.join(SCENES_DIR, f"{scene_id}.x3d"),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return SceneDefinition.from_xml(f.read())
    raise FileNotFoundError(
        f"Scene definition not found for '{scene_id}'. "
        f"Expected one of: {[os.path.basename(c) for c in candidates]}"
    )


def _resolve_cultivars(names: list) -> list:
    """
    Resolve cultivar names to CultivarDefinition objects.
    Looks up in the registry first, then cultivars/ XML files.
    Unknown names get a default definition with warning.
    """
    reg = _get_registry()
    result = []
    for name in names:
        defn = reg.get(name)
        if defn is None:
            # Try loading from file: cultivars/<safe_name>.xml
            safe = name.lower().replace(" ", "_").replace("the_", "")
            for fname in [f"{safe}.xml", f"the_{safe}.xml",
                          f"{name.lower().replace(' ', '_')}.xml"]:
                fpath = os.path.join(CULTIVARS_DIR, fname)
                if os.path.exists(fpath):
                    try:
                        with open(fpath, encoding="utf-8") as f:
                            defn = CultivarDefinition.from_xml(f.read())
                        reg.register(defn)
                        break
                    except Exception:
                        pass
        if defn is None:
            # Use a default placeholder — generator will place them
            print(f"Warning: cultivar '{name}' not found — using defaults")
            defn = CultivarDefinition(
                name=name,
                weights={"E": 0.25, "B": 0.25, "P": 0.25, "S": 0.25},
                regulation=0.70,
                shadow_context=ShadowContext(lambda_val=0.70),
                color="#8888cc",
                description=f"Placeholder for {name}",
            )
        result.append(defn)
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@generate_bp.route("/scene/generate", methods=["POST"])
def generate_scene_endpoint():
    """
    POST /scene/generate

    Body (JSON):
    {
        "scene_id":  "garden_of_the_goddess",   # required
        "cultivars": ["The Witness"],             # required, list of names
        "api_url":   "http://localhost:5000",     # optional, default localhost
        "output":    "static/mccf_scene.x3d",    # optional, override output path
        "positions": [[0,0,-3]]                   # optional, per-cultivar [x,y,z]
    }

    Returns:
    {
        "status": "ok",
        "scene_id": "garden_of_the_goddess",
        "output": "static/mccf_scene.x3d",
        "cultivars": ["The Witness"],
        "zones": 3,
        "lines": 412
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    scene_id  = data.get("scene_id")
    cultivar_names = data.get("cultivars", [])
    api_url   = data.get("api_url", "http://localhost:5000")
    output    = data.get("output", OUTPUT_PATH)
    positions = data.get("positions")  # list of [x,y,z] or None

    if not scene_id:
        return jsonify({"error": "scene_id required"}), 400
    if not cultivar_names:
        return jsonify({"error": "cultivars list required (at least one name)"}), 400

    # Load scene definition
    try:
        scene_def = _load_scene_def(scene_id)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"Scene definition parse error: {e}"}), 400

    # Resolve cultivars
    cultivar_defs = _resolve_cultivars(cultivar_names)

    # Convert positions to tuples if provided
    initial_positions = None
    if positions:
        try:
            initial_positions = [tuple(p) for p in positions]
        except Exception:
            pass

    # Generate
    try:
        x3d = generate_scene(
            scene_def=scene_def,
            cultivar_defs=cultivar_defs,
            api_url=api_url,
            initial_positions=initial_positions,
        )
    except Exception as e:
        return jsonify({"error": f"Scene generation failed: {e}"}), 500

    # Write
    try:
        written = write_scene(x3d, output)
    except Exception as e:
        return jsonify({"error": f"Could not write scene file: {e}"}), 500

    # Count zones from scene def for summary
    zone_count = len(scene_def.zone_xml_blocks) + len(scene_def.zone_refs)

    return jsonify({
        "status": "ok",
        "scene_id": scene_id,
        "output": os.path.relpath(written, REPO_ROOT),
        "cultivars": [cd.name for cd in cultivar_defs],
        "zones": zone_count,
        "lines": len(x3d.splitlines()),
        "message": f"Scene '{scene_id}' generated with "
                   f"{len(cultivar_defs)} avatar(s) and {zone_count} zone(s). "
                   f"Reload the launcher to see it."
    }), 200


@generate_bp.route("/scene/generate/scenes", methods=["GET"])
def list_scenes():
    """
    GET /scene/generate/scenes
    List available SceneDefinition files in scenes/ directory.
    Returns scene ids (filenames without _def.xml or .xml suffix).
    """
    if not os.path.isdir(SCENES_DIR):
        return jsonify({"scenes": []})

    scene_ids = []
    for fname in sorted(os.listdir(SCENES_DIR)):
        if fname.endswith("_def.xml"):
            scene_ids.append(fname[:-8])
        elif fname.endswith(".xml") and not fname.endswith("_def.xml"):
            scene_ids.append(fname[:-4])

    return jsonify({"scenes": scene_ids, "scenes_dir": SCENES_DIR})


@generate_bp.route("/scene/generate/cultivars", methods=["GET"])
def list_cultivars():
    """
    GET /scene/generate/cultivars
    List available cultivar names (registry + cultivars/ XML files).
    """
    reg = _get_registry()
    names = reg.all_names()

    # Also check cultivars/ directory for XML files not yet loaded
    file_names = []
    if os.path.isdir(CULTIVARS_DIR):
        for fname in sorted(os.listdir(CULTIVARS_DIR)):
            if fname.endswith(".xml"):
                file_names.append(fname[:-4])

    return jsonify({
        "cultivars": names,
        "cultivar_files": file_names,
    })


# ---------------------------------------------------------------------------
# Upload endpoint — receives X3D from Scene Composer, writes to static/
# ---------------------------------------------------------------------------

@generate_bp.route("/scene/x3d/upload", methods=["POST"])
def upload_x3d():
    """
    POST /scene/x3d/upload
    Receives an X3D document from the Scene Composer client and writes it
    to static/mccf_scene.x3d so the launcher can load it immediately.

    Body: X3D document (Content-Type: application/xml or text/plain)
    Returns: {"status":"ok", "output":"static/mccf_scene.x3d", "bytes": N}
    """
    x3d_bytes = request.data
    if not x3d_bytes:
        return jsonify({"error": "Empty body"}), 400

    output_path = OUTPUT_PATH
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(x3d_bytes)
    except Exception as e:
        return jsonify({"error": f"Could not write scene file: {e}"}), 500

    return jsonify({
        "status": "ok",
        "output": os.path.relpath(output_path, REPO_ROOT),
        "bytes": len(x3d_bytes),
        "message": "Scene written. Reload the launcher to view it."
    }), 200


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_generate_api(app) -> None:
    """
    Register the scene generate blueprint with a Flask app.

    Usage in mccf_api.py:
        from mccf_scene_generate_api import register_generate_api
        register_generate_api(app)

    That's all. The endpoint is then available at POST /scene/generate.
    """
    app.register_blueprint(generate_bp)
