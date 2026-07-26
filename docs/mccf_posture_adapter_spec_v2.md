# MCCF Affect-to-Posture Adapter — Handoff Spec (v2)

**Status:** design only, nothing built yet.
**Purpose of this doc:** enough context for a fresh chat (no memory of this
conversation) to implement this correctly on the first pass. This version
supersedes the earlier one — everything from the original is preserved
below, with an appendix added covering asset-generation and clothing
architecture discussion that happened after the original was written.

---

## 1. Naming disambiguation (read this first)

MCCF already uses the word "adapter" for something unrelated:
`mccf_llm.py` has `StubAdapter` / `AnthropicAdapter` / `OpenAIAdapter` /
`OllamaAdapter` / `GoogleAdapter` — these are LLM backends for text
generation (currently a local LLaMA model via Ollama is what's actually
in use for real-time dialogue — see Appendix, §A.5). **This spec is not
that.** Suggest calling this new piece the **posture adapter** or
**affect-to-posture layer** in code/naming to avoid collision. It has zero
interaction with which LLM is generating dialogue; it only consumes the
affect vector.

---

## 2. Problem statement

MCCF's affect state (`valence`, `arousal`, `regulation` — from
`CoherenceField`/`Agent`, computed in `mccf_hotHouse.py`'s EmotionalField)
already drives several observable channels:

- `mccf_lighting.py` — affect → lighting params
- `mccf_energy.py` — affect → moral topology / Boltzmann action scoring
- `mccf_ambient_api.py` / neoriemannian — affect → music params

It does **not** currently drive the avatar's body. A grieving agent gets
dim lighting and slow music, but stands in rest pose. This spec closes that
gap: **affect state → joint rotation deltas**, applied to whatever HAnim
avatar is currently loaded for that persona/cultivar.

This is the embodied counterpart to the Laban-effort-quality idea from
earlier design work: weight/time/space/flow qualities → joint stiffness
and offset, expressed here as concrete per-joint rotation deltas.

---

## 3. Why this is tractable without ML (do not build a trained model for v1)

An earlier design pass explored implementing this using Hugging Face
PEFT-style low-rank adapters (LoRA), prompted by a Google AI Studio
transcript about applying PEFT's `BaseTuner`/`BaseTunerLayer` machinery to
HAnim joint animation. That approach was rejected for v1:

- PEFT's Tuner classes exist to swap layers inside pretrained transformer
  checkpoints — not applicable here, and several code paths in that
  transcript don't actually run as written (unimplemented abstract methods,
  invented-looking `x3d` package API calls).
- MCCF doesn't have (yet) a labeled training set of reference poses per
  affect state, so there's nothing to train a low-rank residual against.
- The problem MCCF actually has — generalizing across differently-named
  imported skeletons — is **already solved** by existing infrastructure
  (see §4). A neural net isn't needed to get that generalization; the
  joint-map resolution step already provides it.

**v1 is a deterministic function.** A trained/blended version is a
plausible v2 (see §7) once named reference poses exist.

---

## 4. Existing infrastructure this must reuse (do not reinvent)

All in `mccf_hanim_api.py` (HAnim Editor backend):

| Piece | What it does |
|---|---|
| `_detect_naming_convention(joint_defs)` | Classifies an imported skeleton's naming: `mixamo`, `blender_dot`, `blender_under`, `gltf_hyphen`, `hanim`, `unknown` |
| `_build_joint_map(joint_defs, convention)` | Builds `{raw_def: canonical_hanim_name}`, e.g. `mixamorig:LeftArm → l_shoulder` |
| `_write_cultivar_joint_map()` / `_read_cultivar_joint_map()` | Persists that map as `<JointMap convention="...">` inside the cultivar XML, keyed per avatar |
| `/hanim/joints` route | Returns the joint tree already resolved to canonical HAnim 2.0 names via the cultivar's JointMap, regardless of source rig |
| `_joint_region(name)` | Classifies a (canonical or raw) joint name into `spine` / `left_arm` / `right_arm` / `left_leg` / `right_leg` / `other` |
| `_update_image_texture_url()` | Already exists — repoints a texture on an avatar (prefers `DEF` containing `TextureAtlas`, the Jin convention). Not yet read in depth; likely relevant to skin/texture swap, separate from the clothing-swap architecture in Appendix §A.4 |

**Consequence for this spec:** the posture adapter should speak *only* in
canonical HAnim 2.0 names (`humanoid_root`, `vl5`, `vt12`, `vt6`, `vc4`,
`skullbase`, `l_hip`, `r_shoulder`, etc.) — never in a specific rig's raw
`def` string. Translating canonical name → this-avatar's-actual-def is a
lookup against that avatar's stored `<JointMap>`, already implemented.
This is what makes the adapter rig-agnostic for free, **and** — per
Appendix §A.4 — means the same posture adapter works unmodified across
every clothing/outfit variant of a given character, since all outfit
files share the same skeleton and therefore the same JointMap.

**Known gap to check separately (not this spec's job to fix):**
`_MIXAMO_TO_HANIM` maps the main bone chain plus finger segments, but not
Mixamo's twist/roll bones (`mixamorig:LeftForeArmRoll`, etc.). Those come
back `joints_unmapped` / region `other` and won't be reachable by name.
Irrelevant to posture adapter design (it only ever targets named canonical
joints) but worth fixing separately if some imports look "dead" in areas
those twist bones cover.

**Live pose delivery mechanism, already built (editor side):**
`character_creator.html` does not edit X3D files or drive
`OrientationInterpolator` playback for live posing. It posts messages of
shape:

```js
hePoseSendSAI({ type: 'setJointRotation', joint: <DEF>, rotation: [x, y, z, angleRad] })
```

to a preview iframe, which does:

```js
browser.currentScene.getNamedNode(DEF).rotation = new X3D.SFRotation(x, y, z, angle);
```

This is the SAI (Scene Access Interface) live-write pattern. The posture
adapter's output should be delivered the same way — same message shape,
same live SAI write — just computed from affect state instead of a mouse
drag on a slider.

**Existing preset system to model this on:** the editor already has named
"joint group presets" — a primary joint plus related joints, proportional
scaling, axis sign-flip, all driven by one slider set. The posture adapter
is architecturally the same shape: a named function that emits
`{canonical_joint_name: rotation_delta}`, just with affect state as the
continuous input instead of a slider position.

---

## 5. Open questions — MUST resolve before writing integration code

**5.1 — Live scene channel (carried over from v1, still unresolved).**
How does `mccf_lighting.py` (or ambient/energy) currently reach a *live*
running scene? Everything confirmed in §4 is about the *editor's* preview
iframe. It is not yet established whether:

(a) lighting/ambient/energy already push live updates to a running MCCF
scene via some channel (websocket, SSE, polling endpoint) — in which case
the posture adapter should ride that same channel, or

(b) those affect-driven params only take effect at compile/export time via
`mccf_compiler.py` (baked into the X3D file, not live) — in which case
"live" posture modulation may not be architecturally possible yet either,
and this spec's scope may need to shrink to "posture baked at compile
time" rather than "posture updates in real time as affect drifts."

**Do not proceed with a live-SAI integration design until this is
confirmed.** Ask the user directly; do not assume.

**5.2 — Cultivar-to-avatar binding (new, from follow-up discussion —
see Appendix §A.6).** Is the character-in-scene entry in the Scene
Composer's XML schema structured so that "which cultivar" (emotion vector)
and "which avatar/body Inline reference" are already independent sibling
fields? Or is the avatar currently hard-bound to the cultivar in a way
that would need loosening to support per-scene outfit changes? This
doesn't block the posture adapter itself, but it determines whether the
broader "same character, different outfit per scene" goal this spec's
work sits inside is already fully supported or needs one small schema
addition. Check the relevant XML schema / Proto declaration directly
rather than assuming either way.

---

## 6. Functional spec (v1, deterministic)

### Input
```
affect = {
    "valence":    float,  # -1.0 .. 1.0
    "arousal":    float,  #  0.0 .. 1.0
    "regulation": float,  #  0.0 .. 1.0
}
```
Source: whatever field on `Agent`/`CoherenceField` currently holds this —
confirm exact attribute names/getters in `mccf_core.py` / `mccf_hotHouse.py`
before wiring (not yet verified against live code in this spec). Note per
Appendix §A.6: cultivars are the *initial* emotion-vector settings used
when a character is created — confirm whether the live affect state this
adapter reads is the same field, or a runtime-evolved value that starts
from the cultivar but diverges over the scene/story.

### Output
```
{ canonical_hanim_name: [x, y, z, angle_delta_rad], ... }
```
A sparse dict — only joints this function actually modifies (spine chain,
shoulders, head at minimum; do not attempt all ~146 LOA4 joints in v1).

### Reference starting point
The earlier design sketch (`affect_to_hanim_posture()`, from prior
session) is a reasonable v1 skeleton:

```python
def affect_to_posture(valence, arousal, regulation) -> dict:
    pelvis_y_offset = -0.02 * (1 - valence) * arousal
    thorax_flex     =  0.15 * (1 - valence) * (1 - regulation)
    return {
        "humanoid_root": {"translation_delta": [0, pelvis_y_offset, 0]},
        "vl5":           {"rotation_delta": [1, 0, 0, thorax_flex]},
        "vc4":           {"rotation_delta": [1, 0, 0, thorax_flex * 0.5]},
        "skullbase":     {"rotation_delta": [1, 0, 0, thorax_flex * 0.3]},
    }
```
This needs: (a) translation-delta support alongside rotation-delta (SAI
write for translation is a different field than rotation — confirm
editor/runtime supports writing `translation` live, not just `rotation`),
(b) expansion to shoulders/arms if a shrug/openness dimension is wanted,
(c) tuning, which will be iterative/by-eye against the actual avatar.

### Two modes to support (confirm both are wanted, or just one)
- **Continuous** — small per-tick deltas layered on top of current pose,
  as affect drifts. Rides whatever live channel §5.1 resolves to.
- **Discrete** — a named held pose triggered on a state transition (e.g.
  entering grief), reusing the editor's existing group-preset data shape.
  Could ship even if §5.1 resolves to "compile-time only," since a
  discrete pose can be baked into a compiled clip — which fits this
  project's actual use case (authored story scenes, not a live game —
  see Appendix §A.3) better than the continuous mode may.

---

## 7. Explicit non-goals for v1

- No PyTorch, no Hugging Face PEFT, no trained model of any kind.
- No dependency on the `x3d` Python package or any code from the Gemini
  AI Studio transcript that originated this idea — that transcript's code
  was illustrative/non-functional and should not be copied.
- No attempt to cover all LOA4 joints — start with spine chain + head,
  expand only if the result looks incomplete.
- No fix to the Mixamo twist-bone mapping gap (§4) — separate task.
- No new mesh/avatar generation work of any kind — that's a fully separate
  concern (Appendix §A) and this adapter should be designed to work
  identically regardless of how the avatar file was produced.

## 8. Plausible v2 (only after v1 ships and looks under-expressive)

Once a few named reference poses exist (authored by hand through the
existing editor, e.g. "grief," "confidence," "fear"), a low-rank *blend*
across those hand-authored poses, weighted by affect similarity, is a
legitimate lightweight upgrade — literally a weighted sum of preset
deltas by joint name, no training required. A learned residual (small
regression, not a full PEFT/LoRA stack) is a further-out option if
blending named presets still isn't expressive enough, and only becomes
viable once there's a real labeled pose dataset to fit against.

---

## 9. What to bring into the next session

- This document.
- Confirmation (from the user) of the answer to §5.1 and §5.2.
- Confirmation of exact affect-state accessor names in `mccf_core.py` /
  `mccf_hotHouse.py`.
- `mccf_hanim_api.py` (already reviewed, referenced throughout above) if
  deeper joint-map/SAI details are needed again.
- Whichever XML schema/Proto declaration defines a character-in-scene
  entry, if §5.2 is being resolved in that session.

---
---

# Appendix A — Context from follow-up discussion

Everything below happened in conversation *after* the original spec (§1–9
above) was written, prompted by a broader question about how hard other
"generative adapters" would be to build. It's included here because it
reframes some assumptions worth knowing before touching avatar files, even
though none of it changes the posture-adapter design itself.

## A.1 — Two different difficulty classes of "generative adapter"

The original question was whether adapters for auto-generating X3D scene
assets, or generating H-Anim models from photos, are hard to write. The
answer splits cleanly in two:

- **Layout/composition generation** (placing/parameterizing known
  primitives — buildings from a footprint, terrain, camera/lighting
  scaffolding) is tractable with an LLM, because it's structured-markup
  generation against a known schema — the same category of thing the
  scene compiler already does (LLM extraction of beats →
  `TimeSensor`/`PositionInterpolator` structures via `mccf_compiler.py`).
  Not a new kind of problem for this project.
- **Novel mesh generation** (an actual new 3D shape/character from a text
  description or photo) is a hard, distinct ML research problem —
  text-to-3D diffusion, NeRF/Gaussian-splat reconstruction, meshification.
  Not something to build in-house. The practical path is: use an existing
  third-party generator, then write a *converter* that brings its output
  into the X3D/HAnim pipeline — mirroring exactly what already exists for
  Mixamo ingestion.

**Photo → rigged H-Anim model specifically** bifurcates the same way:
photo → rigged mesh is a hard research problem, currently dominated by
**SMPL/SMPL-X** parametric human body models as the backbone (used by
Meshcapade, and by newer VLM-driven single-photo pipelines like
SmartAvatar, 2025). Rigged-mesh → H-Anim/X3D, by contrast, is *not* a new
problem — it's the same problem already solved for Mixamo, and would just
need one more naming-convention table (`smpl` alongside the existing
`mixamo`/`blender_dot`/`gltf_hyphen` entries in `_build_joint_map()`),
plus one more heuristic branch in `_detect_naming_convention()`. Not
pursued further since it wasn't the actual goal (see A.3).

## A.2 — Auto-rig tool landscape (checked live, May 2026)

A 2026 comparison (Tripo, Meshy, Cascadeur, AccuRig, Mixamo tested against
each other) found:

- **Meshy's** auto-rig uses non-standard names for spine and clavicle
  bones; standard retargeters don't auto-detect them. Writing a bespoke
  naming table for Meshy's own rig would carry similar guesswork to what
  Mixamo's table already required once.
- **Tripo's** rig output uses a standard biped layout and recognizable
  bone naming, and now ships a direct T-pose export option specifically
  to make handoff to Mixamo frictionless.
- Community practice already treats "generate mesh anywhere, then rig via
  Mixamo" as the standard, battle-tested move.

**Recommendation that followed:** route Meshy/Tripo output through
Mixamo's own auto-rigger as an extra hop, rather than ingesting either
tool's proprietary rig names directly. That way the existing, mature
`_MIXAMO_TO_HANIM` table (which already covers the full chain including
fingers) is reused with zero new mapping code, instead of writing and
validating a bespoke table per generator tool.

## A.3 — The actual production pipeline in use (confirmed directly)

This is **not** a game engine / real-time pipeline — MCCF is being used to
animate authored stories. Confirmed chain currently in use:

```
Meshy / Tripo  →  mesh
    →  Blender (Claude, via MCP bridge, handles the "fiddly bits")
    →  export glTF from Blender
    →  X_ITE: open glTF, Save As → X3D
    →  (this is the file that then goes through the existing
        hanim_ingest / hanim_ingest-mixamo pipeline)
```

The `gltf_hyphen` naming-convention branch in `_detect_naming_convention`/
`_build_joint_map` was **written for exactly this chain** (its own code
comment references "X_ITE saves glTF joints with hyphens and
skeletalConfiguration='GLTF'") — so this isn't unmapped territory in
principle.

**Open risk flagged, not yet resolved — needs one real test file:**
if the mesh's bones originated as Mixamo names
(`mixamorig:LeftArm`, colon-prefixed) and went through Blender import →
glTF export → X_ITE Save As X3D, it's unverified what the bone name
becomes on the other side. Colons aren't valid X3D `DEF` characters (the
existing code already sanitizes for this elsewhere, replacing `:` and `-`
with `_` when building `WireInterp_` names) — so if the round-trip
produces something like `mixamorig_LeftArm` (underscore, no colon, no
hyphen), it matches **neither** of `_detect_naming_convention`'s two
current signals (colon-count → `mixamo`; hyphen/`-L`/`-R` pattern →
`gltf_hyphen`) and would silently fall into `unknown` — meaning
`_build_joint_map` maps nothing for it, with no error raised.

**Action item for next session, before building anything further on
this:** run one real mesh through the actual chain above and inspect the
resulting joint `DEF` list (same way `mccf_hanim_api.py` was reviewed
directly) rather than assuming the existing convention detection handles
it.

**Also flagged, explicitly unverified:** inlining glTF directly (skipping
"Save As X3D") was mentioned as a possible shortcut. This should be
treated as a separate, riskier path, not an equivalent one — the entire
joint pipeline (`_walk_joints`, `HAnimJoint`/`DEF` parsing, SAI
`getNamedNode(DEF)` calls the editor and any future posture adapter
depend on) requires real X3D `HAnimJoint` elements with `DEF` attributes
in the document tree. Whether an `Inline`-referenced glTF scene exposes
its joints as SAI-addressable named X3D nodes at all — versus rendering
as an opaque rigged mesh with no addressable skeleton from X3D's side —
is exactly the unverified part. **Do not build the posture adapter (or
anything else depending on JointMap/SAI) against Inline-glTF until this
is specifically confirmed.** "Save As X3D" is the path everything else
already built assumes.

## A.4 — Clothing/outfit architecture (the actual stated goal)

Principal goal, stated directly: **better-looking, consistent avatars —
specifically, the same character wearing different clothing across
different scenes.**

This splits into a hard half to avoid and an easy half to lean into:

- **Hard, and not worth chasing:** re-generating the "same" character
  from a generator multiple times and hoping identity is preserved.
  Diffusion-based generators (2D or 3D) don't have a stable notion of
  identity across separate runs without extra machinery (reference-image
  conditioning, per-character fine-tuning, IP-Adapter-style techniques).
  Don't fight the tools against their grain.
- **Easy, and the actual answer:** generate the character **once**,
  commit to that mesh + rig as the permanent canonical asset, never
  regenerate it. Then:
  - "Different skins" was clarified to mean **different clothing that
    changes silhouette** (armor vs. gown vs. casual wear), not just
    texture/material variation on the same geometry.
  - Since this is authored-story work, not a real-time game, there is
    **no need for live in-scene garment swapping.** The simpler,
    correct-for-this-use-case approach: each outfit is a **separate,
    complete avatar file** that happens to share the identical skeleton.
  - Practically: skin each garment mesh to the *same* armature as the
    canonical body (Blender's automatic-weights / weight-transfer
    tooling — no new technology needed), then export each outfit variant
    through the exact same pipeline already in use (Blender/MCP → glTF →
    X_ITE → Save As X3D).
  - Because every outfit variant shares identical joint names and
    hierarchy, running each through the existing ingest pipeline
    produces **the same JointMap already established for that
    character** — this is not new per-outfit mapping work, just
    re-running ingestion on a file where geometry changed and bones
    didn't. This is also why the posture adapter (main body of this
    spec) needs no outfit-awareness at all — it targets canonical joint
    names, which are identical across every outfit file for a character.
  - "Outfit swap," architecturally, is then just **which avatar file a
    scene points its Inline at** — not a new mechanism, a new *use* of
    Inlines that already exist (see A.5).

## A.5 — Confirmed current MCCF architecture (not previously stated this
explicitly in this spec)

- Avatars are brought into scenes via **Inlines and Protos** — already a
  modular architecture, confirmed directly by the user. This is why A.4's
  "one file per outfit" approach requires no new plumbing: pointing an
  Inline at a different avatar file *is* the outfit-swap mechanism.
- **Cultivars** are the **initial emotion-vector settings** used when a
  character is created (designed in an earlier, separate session, per the
  user) — easy to adjust, and more can be added. Important distinction
  for §6's Input section: confirm whether the *live* affect state the
  posture adapter reads is this same cultivar-seeded value evolving at
  runtime, or something else.
- Scene composition uses **custom XML schemas** defining "all the bits
  that can change," authored via a **Scene Composer**, with an **X3D
  Loader** that builds the actual scene by reading those generated XML
  instances on export. Described by the user as "old school but it
  works," and it runs on localhost.
- **Dialogue generation currently uses a local LLaMA model** (via the
  `OllamaAdapter` in `mccf_llm.py`) in real time — this is the "LLM
  adapter" sense of the word disambiguated in §1, unrelated to the
  posture adapter this spec is about.

## A.6 — Open question this raises (also listed as §5.2 above)

Does the Scene Composer's XML schema already treat "which cultivar" and
"which avatar/body Inline" as independent sibling fields on a
character-in-scene entry — meaning a persona can keep one cultivar across
scenes while wearing different outfit files, or vice versa — or is the
avatar currently hard-bound to the cultivar in a way that would need
loosening? Not yet checked against the actual schema/Proto declaration.
Doesn't block the posture adapter, but blocks confirming A.4's outfit
architecture is fully supported today versus needing one small addition.

## A.7  Kate Comments (ChatGPT)

I think this is a very good handoff specification. More importantly, it demonstrates something that many design documents fail to do: it clearly distinguishes architectural decisions from implementation details. That makes it much more likely that another developer—or another AI session—will produce something compatible with the existing MCCF architecture rather than reinventing it.

Here are the parts that stand out to me.

What is particularly strong

The first section, the naming disambiguation, is excellent. Calling out that MCCF already has "adapter" classes for LLM backends avoids one of the most common AI implementation mistakes: matching on familiar names instead of understanding intent. Renaming this component to "posture adapter" or "affect-to-posture layer" is exactly the right move.

The specification also does an excellent job of defining scope.

It says, in effect:

"We already have affect. We already have avatars. We only need the deterministic mapping between them."

That is a remarkably clean problem statement.

The biggest architectural insight

To me, the most important realization in the document is this:

The JointMap already solved the generalization problem.

That eliminates an enormous amount of unnecessary complexity.

Many people immediately jump to machine learning whenever they see different skeletons.

But your architecture already provides

Raw skeleton
      ↓
JointMap
      ↓
Canonical HAnim
      ↓
Posture adapter
      ↓
Avatar

The adapter therefore lives entirely in canonical HAnim space.

That is exactly where it belongs.

The decision to avoid ML

I agree with the rejection of LoRA for v1.

Not because LoRA is a bad technique—it isn't—but because it solves the wrong problem.

LoRA answers

"How do I efficiently modify a neural network?"

Your problem is

"Given an affect vector, what posture should the body adopt?"

Those are completely different questions.

Without a corpus of labeled poses there is nothing meaningful to train.

A deterministic mapping is simpler, explainable, debuggable, and artist-tunable.

The SAI integration

This is another strong design choice.

Rather than inventing another animation mechanism, you're reusing the editor's existing pathway:

affect

↓

posture adapter

↓

canonical joints

↓

JointMap

↓

actual DEF names

↓

setJointRotation

↓

SAI

↓

running avatar

That keeps the runtime consistent with the editor.

I would preserve that principle.

One section I would expand

The one thing I think deserves a little more structure is the posture model itself.

Currently the document maps

valence
arousal
regulation

directly to joint rotations.

I would insert one intermediate abstraction.

Instead of

affect

↓

joint rotations

consider

affect

↓

body qualities

↓

joint rotations

where body qualities might include

compression
expansion

verticality

head orientation

shoulder openness

torso flexion

motion stiffness

center of gravity

breathing amplitude

Then each body quality drives several joints.

For example

Compression

↓

pelvis
vl5
vt12
vc4
head

instead of each joint independently reading valence.

This gives artists somewhere intuitive to tune behavior.

Why this matters

Suppose later you decide

confidence

should lift the chest more.

Instead of changing five equations you modify

expansion = f(valence, regulation)

Everything downstream updates automatically.

That separation mirrors the rest of MCCF's layered architecture.

I would add limits

I'd also recommend introducing explicit clamps.

For example

thorax_flex =
    clamp(
        0.18 * (1-valence)*(1-regulation),
        -0.25,
         0.25
    )

Otherwise several channels accumulating together could slowly produce anatomically impossible postures.

One missing concept

Because MCCF is fundamentally temporal, I'd strongly recommend making the posture adapter stateful.

Instead of

rotation = f(affect)

I'd make it

target posture = f(affect)

current posture +=
    α (target-current)

or

current += dt * damping

That produces easing automatically.

Otherwise every affect update snaps the skeleton.

Lighting can snap.

Music can jump.

Bodies rarely should.

Section 5

I think this is exactly the right place to stop.

The unanswered question is

How does affect currently reach the runtime?

Until that is answered, everything else is speculation.

I especially like that the document explicitly says

Ask the user. Do not assume.

That prevents a future implementation from accidentally inventing an entire messaging subsystem.

The v2 discussion

The most interesting part, in my opinion, isn't the learned residual.

It's the weighted preset blending.

Suppose you eventually author

Confidence
Fear
Grief
Curiosity
Calm
Excitement

Then posture becomes

Pose =
0.42 Confidence +
0.31 Calm +
0.27 Curiosity

That is effectively a low-dimensional posture basis.

It is interpretable.

Artists can edit it.

It can be version-controlled.

It works with canonical HAnim names.

And it provides labeled data if you later decide to fit a learned residual.

Ironically, if a machine learning model ever becomes worthwhile, this deterministic system will have generated exactly the training corpus it needs.

One idea that aligns well with MCCF

One addition I would seriously consider is treating the posture adapter as another field in the same architectural sense as lighting, music, and energy. Rather than a standalone utility, it could expose an interface like:

Affect
   ↓
EmbodimentField
   ├── LightingAdapter
   ├── MusicAdapter
   ├── EnergyAdapter
   └── PostureAdapter

This keeps all affect-driven modalities conceptually parallel. If you later add facial expressions, gaze control, breathing, or gesture generation, they become additional embodiment adapters rather than special cases.

Overall, I would rate this handoff document as 9.5/10. It's unusually disciplined about scope, reuses existing infrastructure instead of duplicating it, and clearly separates what is known from what still needs confirmation. The only substantive enhancement I'd recommend before implementation is introducing an intermediate layer of body qualities between affect and joint rotations, plus temporal smoothing, so the posture behavior remains coherent, tunable, and extensible as MCCF grows.


