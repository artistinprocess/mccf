# MCCF Seed — H-Anim Facial Displacement, Resumed at Plan A

**Date of this seed:** Sept 2026, after a two-day facial-animation investigation
**Status:** Wall cleared. Real mechanism confirmed working. Resuming Plan A —
full H-Anim FACS on Anna, via the correct, standard mechanism.

---

## The one thing to know before anything else

**`HAnimDisplacer` works as a direct child of `HAnimJoint`**, with
`coordIndex` referencing `HAnimHumanoid.skinCoord` *sparsely* — no
`HAnimSegment` needed, no mesh segmentation needed, works on a single
combined skinned mesh exactly like Anna's. Driven by a plain
`ScalarInterpolator` → `ROUTE` → the displacer's own `weight` field. No
Script required for the basic mechanism.

This is confirmed three independent ways:
1. **Official W3DC reference example** (`JoeKickAnimation.x3d`,
   Web3D.org's own hosted archive) uses exactly this pattern for a
   skull-tip displacer on a single-skin CAESAR-based avatar.
2. **John Carlson (H-Anim WG) confirmed it directly**, in writing, on
   the x3d-public list: *"HAnimJoint has a displacers field. The
   HAnimDisplacer.coordIndex field is pointed at HAnimHumanoid.skinCoord
   field. coordIndex references the skinCoord sparsely."*
3. **Tested and confirmed working on Anna's own real asset**, with real
   extracted AU data — `l_eyebrow_joint` got a displacer using real
   AU1+AU2 deltas, loaded in Character Creator's H-Anim Editor, and the
   brow visibly moved. See `Anna_displacer_test2.x3d` in this package —
   that file is proof, not a claim.

**What this means for the two days before this confirmation:** the
physical mesh-segmentation approach (duplicating the mouth region into
a separate piece, cutting a hole, blending boundary normals, re-skinning)
was real, working engineering — but unnecessary. It solved a problem
that had a much simpler, standard, spec-correct solution the whole
time. That earlier work (`Anna_mouth_final.x3d`, the `.blend` with the
separated mouth piece) is **superseded — don't build on it further.**
The Blender skills and lessons from it aren't wasted, but the actual
artifact isn't the path forward anymore.

---

## What's proven and ready to reuse right now

### 1. Real AU displacement data — `anna_au_deltas.json`
All 9 AUs, each as `{vertex_index: [dx, dy, dz], ...}`, real deltas
extracted directly from Blender's actual shape-key data via the glTF
export, already verified against Desktop's own reported peak values
(exact match, e.g. AU12's 0.012343 displacement confirmed to full
precision).

```
AU4_BrowLowerer            844 vertices
AU12_LipCornerPuller       443 vertices
AU2_OuterBrowRaiser        762 vertices
AU15_LipCornerDepressor    443 vertices
AU9_NoseWrinkler           381 vertices
AU6_CheekRaiser            469 vertices
AU1_InnerBrowRaiser        557 vertices
AU26_JawDrop_LipCorrective 271 vertices
AU5_UpperLidRaiser         232 vertices
```

Vertex indices are in the **glTF/skinCoord shared numbering** — confirmed
1:1 identical between Anna's glTF export and the X3D's actual rendered
`Coordinate` array (spot-checked at 5 points across the full index
range, exact match every time). Any index in this file can be used
directly as a `coordIndex` value against Anna's real skin mesh, no
remapping needed.

### 2. Base mesh — `anna_base_mesh_points.json`
All 6640 real rest-pose vertex positions, same numbering as above.
Needed to compute a displacer's `displacements` field (which are
deltas, not absolute positions — already true in the AU data above,
this file is for anything that needs the actual rest coordinates too).

### 3. Proven working X3D — `Anna_displacer_test2.x3d`
The actual file that demonstrated the mechanism works. One
`HAnimDisplacer` (`l_eyebrow_raise_test`) under `l_eyebrow_joint`,
self-driving test animation via `TimeSensor`/`ScalarInterpolator`. Use
this as the literal template for every additional AU — same structure,
different joint, different `coordIndex`/`displacements`, different DEF
name.

### 4. EBPS Driver system — `mccf_ebps_protos.x3d` + `ebps_driver_test_scene.x3d`
Separate, also-proven infrastructure: `EBPSDriver` PROTO (pure E/B/P/S
carrier) plus two example connectors (`EBPSToLight`, confirmed live —
watched a real light pulse; `EBPSToFaceController`, built with the same
corrected syntax but **not yet live-tested** — see open items).

**Real bug, found and fixed, worth remembering:** `IS` connecting a
`ProtoInterface` field to an internal `Script`'s field must be **one
single `<IS>` block, positioned as a direct child of the Script node**
— not nested separately inside each `<field>` element. The wrong
version (IS nested per-field) parses without error but silently never
fires events. Confirmed correct structure against a real Holger Seelig
reference example. Both connectors in `mccf_ebps_protos.x3d` now use
the correct pattern.

---

## Real, honest open items

1. **`EBPSToFaceController` connector — built, not live-tested.**
   `EBPSToLight` proved the pattern works; the face connector uses the
   identical corrected structure but hasn't fired in anger. Test before
   trusting it in a real scene.

2. **Architecture question worth resolving early this session:** now
   that `HAnimDisplacer.weight` can be driven directly, does
   `FaceController` still need to go through a `CoordinateInterpolator`
   intermediate (`AnimationAdapter_<name>`, the Cindy pattern), or
   should it just look up the `HAnimDisplacer` node by name and set its
   `weight` field directly — simpler, one fewer node type involved.
   Worth deciding before wiring more AUs, not after.

3. **Character Creator's "Morph Driver" panel will still show
   everything MISSING.** Its discovery code (`_discoverFaceCoords()` in
   `mccf_hanim_api.py`) only checks for the `FaceCoords`/`Coord_<region>`
   pattern (Cindy's old approach) — it has no awareness of
   `HAnimDisplacer` at all yet. The mechanism works regardless; the UI
   just won't reflect it until that discovery code is extended. Real,
   scoped follow-up work, not urgent, not blocking.

4. **Only `l_eyebrow` has been built as a real displacer so far.**
   Eight more AUs (and the other eyebrow/eyelid side) are sitting ready
   in `anna_au_deltas.json`, same template, same process — just not
   done yet.

5. **Where the resolved-versus-scene-default seed and the FaceController
   `au_weight * 0.5` scaling factor came from is worth re-checking**
   before assuming it's still the right constant — that `0.5` was
   Cindy's own calibration, not necessarily right for Anna's geometry
   scale.

---

## The actual next steps, in order

1. Reply to John Carlson on the list if not already done — confirm the
   fix worked, thank him. (May already be done by the time this seed
   is read — check first.)
2. Decide the `FaceController`-vs-direct-displacer architecture
   question (#2 above).
3. Build displacers for the remaining 8 AUs using the exact template
   from `Anna_displacer_test2.x3d`, real data from `anna_au_deltas.json`
   — mechanical repetition of a now-proven pattern, not R&D.
4. Live-test `EBPSToFaceController` the same way `EBPSToLight` was
   tested — confirm before trusting it.
5. Wire EBPS state → the real displacers, on Cindy or Anna, toward the
   actual demo (Anna's monologue, Cindy reacting in the audience).
6. Optionally: extend `_discoverFaceCoords()` to recognize the
   `HAnimDisplacer` pattern so Character Creator's own UI stops showing
   a false "MISSING" status for a mechanism that's actually working.

---

## Files in this package

```
SEED_facial_displacer_breakthrough.md   — this document
anna_au_deltas.json                      — real per-vertex deltas, all 9 AUs
anna_base_mesh_points.json               — real rest-pose mesh, 6640 points
Anna_displacer_test2.x3d                 — proven working file, the template
mccf_ebps_protos.x3d                     — EBPSDriver + connectors (IS bug fixed)
ebps_driver_test_scene.x3d               — proven EBPS test scene
```

Also still needed from earlier sessions, not re-included here (unchanged,
already correct): the H-Anim joint-naming normalize map in
`mccf_hanim_api.py`, `mccf.xsd` (published schema), Cindy's real
reference file (`cindy_hanim.x3d`) for the `FaceController` Script's
exact real code if rebuilding it from scratch is ever needed.
