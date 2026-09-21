#!/usr/bin/env python3
"""
MCCF Field-Parity Checker — CultivarDefinition

Catches the exact bug shape that cost most of a day in Sept 2026:
CultivarDefinition has one dataclass definition and SEVEN independently
hand-written representations of the same fields (to_dict, to_xml,
_from_element, from_dict, post_cultivar_xml's inline constructor, the
bulk GET response dict, plus the legacy-schema reader). Any of those
can silently drop a field with zero error, zero warning — exactly what
happened to `portrait` and, separately, `receptivity`.

This script parses the real source file with Python's `ast` module
(not regex, not eyeballing) and:
  1. Gets ground truth: the dataclass's actual field names, from
     `dataclasses.fields()` on the imported class.
  2. Finds every `CultivarDefinition(...)` constructor call site in the
     file via AST, and extracts each call's keyword argument names.
  3. Finds the two hand-built dict literals (`to_dict()`'s return dict
     and `get_cultivars_xml()`'s bulk-list dict) and extracts their
     string keys.
  4. Reports, per site, which dataclass fields are missing — the exact
     class of gap this file exists to catch mechanically instead of by
     hand-reading during a debugging session.

Deliberately does NOT check to_xml()/_from_element()'s field coverage
via AST (their field references are `self.<field>` / free-standing
local variables inside long procedural functions, not a single
extractable structure the way a constructor call or dict literal is).
Those two are the ones least likely to silently drop a field in
practice anyway (to_xml only ever runs against a fully-constructed
object with every field already present; _from_element degrades
gracefully to per-field defaults). The constructor call sites and the
hand-built response dicts are where actual data loss happens — that's
what this checks.

Usage:
    python3 check_cultivar_field_parity.py mccf_cultivar_lambda.py

Exit code 0 = every checked site has every field (or explicitly,
documented-as-intentional exclusions — see EXPECTED_GAPS below).
Exit code 1 = a real, undocumented gap was found.
"""

import ast
import sys
import dataclasses
import importlib.util


# Fields that specific sites are EXPECTED not to include, with the
# reason why — server/schema-controlled fields that client-facing
# constructors legitimately never accept. Anything NOT listed here that
# turns out missing is treated as a real bug, not a judgment call this
# script has to make each run.
EXPECTED_GAPS = {
    "post_cultivar_xml": {
        "version": "server/schema-controlled, not client-settable by design",
        "metadata": "internal/administrative, not exposed to any client UI",
    },
    "_load_from_disk": {
        # The OLD <EmotionalArc><Cultivar> schema branch, kept for
        # read-only backward compatibility. Genuinely predates several
        # of these fields — "Old schema has no behavior table — empty
        # by design" is the source's own comment for one of these; the
        # same reasoning extends to every field that schema never had.
        "behavior_clips": "legacy schema predates this field entirely",
        "behavior_default": "legacy schema predates this field entirely",
        "constitutional_notes": "legacy schema predates this field entirely",
        "hanim_loa": "legacy schema predates this field entirely",
        "hanim_src": "legacy schema predates this field entirely",
        "metadata": "legacy schema predates this field entirely",
        "receptivity": "legacy schema predates this field entirely",
        "role": "legacy schema predates this field entirely",
        "version": "legacy schema predates this field entirely",
        "zone_affinity": "legacy schema predates this field entirely",
    },
    "get_cultivars_xml dict literal": {
        # Confirmed (grep against mccf_character_creator.html, Sept
        # 2026) that Character Creator never reads any of these five
        # from the bulk list response — this is a deliberate lighter
        # summary view for populating the sidebar list, not an attempt
        # at a full record. Genuinely different from the portrait/
        # receptivity gaps, which WERE fields the client actively
        # needed and silently lost.
        "role": "bulk list is an intentional summary view; unused by any client",
        "shadow_context": "bulk list is an intentional summary view; unused by any client",
        "version": "bulk list is an intentional summary view; unused by any client",
        "metadata": "bulk list is an intentional summary view; unused by any client",
        "zone_affinity": "bulk list is an intentional summary view; unused by any client",
        "constitutional_notes": "bulk list is an intentional summary view; unused by any client",
    },
}

# Deliberate renames between the dataclass's real field name and the
# wire-format key some sites use instead — NOT gaps, just aliasing this
# script's exact-name matching can't see on its own. Applied before
# diffing so a rename doesn't masquerade as a dropped field.
KNOWN_ALIASES = {
    "agentname": "name",
    "phrases": "signature_phrases",
    "disposition": "description",  # deliberate field reuse, see CultivarDefinition.description's own docs
}


def load_dataclass_fields(source_path, class_name):
    """Import the real module and read its actual dataclass fields —
    ground truth from the live class, not a hand-copied list that could
    itself drift from the source."""
    spec = importlib.util.spec_from_file_location("mccf_cultivar_lambda", source_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cls = getattr(mod, class_name)
    return {f.name for f in dataclasses.fields(cls)}


def find_constructor_call_sites(tree, class_name):
    """Find every `ClassName(...)` call anywhere in the file, tagged
    with the enclosing function name for a readable report."""
    sites = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.func_stack = []

        def visit_FunctionDef(self, node):
            self.func_stack.append(node.name)
            self.generic_visit(node)
            self.func_stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == class_name:
                kwargs = {kw.arg for kw in node.keywords if kw.arg is not None}
                label = self.func_stack[-1] if self.func_stack else "(module level)"
                sites.append((f"{label} (line {node.lineno})", kwargs))
            self.generic_visit(node)

    Visitor().visit(tree)
    return sites


def find_dict_literal_sites(tree, class_name, ground_truth, min_overlap=8):
    """Find hand-built dict literals that are actually serializing a
    full CultivarDefinition record — NOT any dict literal loosely
    matched by function name. Two real precision requirements, both
    added after the first draft of this script produced false
    positives on its own first run:

      1. Class-scoped: `to_dict`/`to_xml`-named methods only count when
         the enclosing class is literally CultivarDefinition — this
         file also has a ShadowContext.to_dict(), an unrelated method
         that happens to share the name and was being matched by the
         first draft's name-only heuristic.
      2. Overlap-filtered: a dict literal only counts as
         "cultivar-shaped" if at least `min_overlap` of its keys
         actually appear in the ground-truth field set. Without this,
         small unrelated dicts (error responses, partial lookups) in
         any loosely-matched function got flagged as if they were
         missing twenty fields they were never meant to have.
    """
    sites = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.func_stack = []
            self.class_stack = []

        def visit_ClassDef(self, node):
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def visit_FunctionDef(self, node):
            self.func_stack.append(node.name)
            self.generic_visit(node)
            self.func_stack.pop()

        def visit_Dict(self, node):
            label = self.func_stack[-1] if self.func_stack else "(module level)"
            enclosing_class = self.class_stack[-1] if self.class_stack else None
            keys = {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            overlap = keys & ground_truth

            is_method_match = label == "to_dict" and enclosing_class == class_name
            is_overlap_match = len(overlap) >= min_overlap

            if keys and (is_method_match or is_overlap_match):
                where = f"{enclosing_class}.{label}" if enclosing_class else label
                sites.append((f"{where} dict literal (line {node.lineno})", keys))
            self.generic_visit(node)

    Visitor().visit(tree)
    return sites


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)

    source_path = sys.argv[1]
    class_name = "CultivarDefinition"

    print(f"Loading ground truth: {class_name} from {source_path}")
    ground_truth = load_dataclass_fields(source_path, class_name)
    print(f"  {len(ground_truth)} real fields: {', '.join(sorted(ground_truth))}\n")

    with open(source_path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=source_path)

    all_sites = []
    all_sites += [
        (f"{label} (constructor call)", kwargs)
        for label, kwargs in find_constructor_call_sites(tree, class_name)
    ]
    all_sites += find_dict_literal_sites(tree, class_name, ground_truth)

    had_failure = False

    for site_label, present_fields in all_sites:
        # Resolve known aliases: if the site uses a wire-format alias
        # instead of the real field name, treat the field as present.
        resolved_present = set(present_fields)
        for alias, real_name in KNOWN_ALIASES.items():
            if alias in present_fields:
                resolved_present.add(real_name)

        missing = ground_truth - resolved_present
        # Strip documented, intentional exclusions for this site
        func_key = site_label.split(" (")[0]
        expected = EXPECTED_GAPS.get(func_key, {})
        real_missing = {f for f in missing if f not in expected}

        status = "OK" if not real_missing else "GAP FOUND"
        print(f"[{status}] {site_label}")
        if expected:
            for f, reason in expected.items():
                if f in missing:
                    print(f"    (expected exclusion) {f}: {reason}")
        if real_missing:
            had_failure = True
            for f in sorted(real_missing):
                print(f"    MISSING: {f}")
        print()

    if had_failure:
        print("FAIL — one or more sites are missing fields the dataclass actually has.")
        print("Either add the field to that site, or add it to EXPECTED_GAPS with a")
        print("stated reason if the exclusion is genuinely intentional.")
        sys.exit(1)
    else:
        print("PASS — every checked site accounts for every dataclass field")
        print("(directly, or via a documented, intentional exclusion).")
        sys.exit(0)


if __name__ == "__main__":
    main()
