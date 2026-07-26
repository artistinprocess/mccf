"""
Day 73 — test for the tagSource/audioFile/audioSource fix to
mccf_api.py's load_scene_xml() (fixing the gap flagged when the Dialogue
Editor's server wiring was corrected against the real API).

mccf_api.py imports ~13 other MCCF modules not present in this session
(mccf_core, mccf_zones, mccf_llm, mccf_collapse, etc.), so it can't be
fully imported and run here. Rather than stub all of those, or hand-copy
the function under test (which could silently drift from the real file),
this extracts load_scene_xml's actual source via the ast module and execs
it in an isolated namespace with just the few names it actually touches:
request, jsonify, os, and _scene_filepath. This tests the real code.
"""

import ast
import os
import sys
import tempfile
import shutil

failures = []


def check(label, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def extract_function_source(filepath, func_name):
    with open(filepath, encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return ast.get_source_segment(source, node)
    raise ValueError(f"{func_name} not found in {filepath}")


def run():
    func_src = extract_function_source("mccf_api.py", "load_scene_xml")
    assert func_src, "extraction failed"

    # ── minimal fixture scene tree, written to a temp dir load_scene_xml ──
    # ── can read via a stubbed _scene_filepath ─────────────────────────────
    tmp_dir = tempfile.mkdtemp()
    try:
        scene_xml = """<?xml version="1.0"?>
<Scene id="test_scene" width="40" depth="40">
  <Waypoints>
    <Waypoint name="wp1" label="WP1" zone="pool" pos_x="1" pos_z="2">
      <Question speaker="Cindy">Legacy question?</Question>
    </Waypoint>
  </Waypoints>
  <Dialogue>
    <Line id="line_full" actor="Cindy" type="Statement" mode="static" blocking="false" trigger="scene-start" ttsText="[thoughtful] Full line." tagSource="authored" audioFile="audio/line_full.mp3" audioSource="recorded">Full line.</Line>
    <Line id="line_bare" actor="Jack" type="Statement" mode="improv" blocking="false" trigger="zone:Pool">Bare line, no tag or audio.</Line>
  </Dialogue>
</Scene>
"""
        filename = "test_scene_scene.xml"
        with open(os.path.join(tmp_dir, filename), "w", encoding="utf-8") as f:
            f.write(scene_xml)

        # ── stub the handful of names load_scene_xml actually touches ──────
        class StubRequest:
            @staticmethod
            def get_json():
                return {"filename": filename}

        captured = {}

        def stub_jsonify(d):
            captured["result"] = d
            return d

        class StubAppConfig:
            @staticmethod
            def get(key, default=None):
                return None  # no chorus manager — load_scene_xml wraps this in try/except

        class StubApp:
            config = StubAppConfig()

        def stub_scene_filepath(fn):
            return os.path.join(tmp_dir, os.path.basename(fn))

        namespace = {
            "request": StubRequest(),
            "jsonify": stub_jsonify,
            "os": os,
            "_scene_filepath": stub_scene_filepath,
            "app": StubApp(),
        }

        exec(compile(func_src, "mccf_api.py::load_scene_xml", "exec"), namespace)
        namespace["load_scene_xml"]()

        result = captured.get("result")
        check("function executed and returned a result", result is not None)
        if result is None:
            print("\nCould not proceed — extraction/exec failed")
            sys.exit(1)

        lines_by_id = {l["id"]: l for l in result["dialogueLines"]}

        # ── real <Dialogue> line with all four Day-73 fields set ───────────
        full = lines_by_id.get("line_full")
        check("line_full present in dialogueLines", full is not None)
        if full:
            check("line_full.ttsText correct", full.get("ttsText") == "[thoughtful] Full line.")
            check("line_full.tagSource correct (raw string, not parsed)", full.get("tagSource") == "authored")
            check("line_full.audioFile correct", full.get("audioFile") == "audio/line_full.mp3")
            check("line_full.audioSource correct (raw string, not parsed)", full.get("audioSource") == "recorded")

        # ── real <Dialogue> line with none of the four fields set ──────────
        bare = lines_by_id.get("line_bare")
        check("line_bare present in dialogueLines", bare is not None)
        if bare:
            check("line_bare.ttsText is None when absent", bare.get("ttsText") is None)
            check("line_bare.tagSource is None when absent", bare.get("tagSource") is None)
            check("line_bare.audioFile is None when absent", bare.get("audioFile") is None)
            check("line_bare.audioSource is None when absent", bare.get("audioSource") is None)

        # ── legacy-migrated line — must NEVER carry these four fields ──────
        legacy = lines_by_id.get("wp1_0")
        check("legacy-migrated line (wp1_0) present in dialogueLines", legacy is not None)
        if legacy:
            check("legacy line trigger is legacy-waypoint:wp1", legacy.get("trigger") == "legacy-waypoint:wp1")
            check("legacy line ttsText is None (never touched by migration)", legacy.get("ttsText") is None)
            check("legacy line tagSource is None (never touched by migration)", legacy.get("tagSource") is None)
            check("legacy line audioFile is None (never touched by migration)", legacy.get("audioFile") is None)
            check("legacy line audioSource is None (never touched by migration)", legacy.get("audioSource") is None)

        # ── regression: fields untouched by this fix still correct ────────
        check("regression: trigger still returned as raw string", full and full.get("trigger") == "scene-start")
        check("regression: sceneConfig still present", result.get("sceneConfig", {}).get("name") == "test_scene")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All checks passed.")


if __name__ == "__main__":
    run()
