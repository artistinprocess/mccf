# X3D Scene — Known Issues (V2.1 → V3)

## ✓ RESOLVED V2.1.9 — Root Cause Identified and Fixed (April 2026)

**All SAI visual failures traced to a single root cause:**

> X\_ITE 11.6.6 external SAI requires typed `X3D.` namespace constructors
> for all non-string field assignments. Plain JavaScript values (numbers,
> arrays) are silently accepted but do not trigger visual updates.

**Confirmed working patterns:**

```
// Scalar fields
node.intensity    = new X3D.SFFloat(0.9);    // ✓
node.transparency = new X3D.SFFloat(0.3);    // ✓

// Vector fields
node.translation  = new X3D.SFVec3f(x,y,z); // ✓

// Color fields
node.emissiveColor = new X3D.SFColor(r,g,b); // ✓

// String fields — plain array works without constructor
node.string = ["text"];                       // ✓

// Arrays for MFColor/MFVec3f — plain array works
node.color = [r, g, b];                       // ✓ (MFColor)
```

**Confirmed by John Carlson (X3DJSONLD):** "You would prefix classes with
X3D. in X\_ITE external (HTML) SAI."

**Status as of V2.1.9:**

* Avatar emissiveColor → `X3D.SFColor` ✓ colors live
* Avatar transparency → `X3D.SFFloat` ✓
* Avatar Transform translation → `X3D.SFVec3f` ✓ movement confirmed
* HotHouse polling → 3/3 agents, 12 nodes updated per cycle ✓
* Scene loads at correct brightness ✓
* Load time normal after pollLighting sync fix ✓

---

## Issue 1 — Light Node SAI (Partially Resolved)

**Status:** Light color arrays work. Light intensity SAI degrades scene.

Any `node.intensity = value` write to DirectionalLight or PointLight nodes
darkens the scene even with `X3D.SFFloat`. Light color array writes `[r,g,b]`
are accepted without degradation.

**Current approach:** All light intensity SAI disabled. Scene uses baked-in
intensity values. Color temperature is tracked in HUD (informational only).

**V2.2 fix:** Light Master Script Node inside `mccf_scene.x3d` receives
field state as a string via SAI, distributes to local lights using internal
X3D scripting. Bypasses external SAI for lights entirely.

---

## Issue 2 — global="true" Has No Effect on Root-Level Lights

**Status:** Open. Lights declared at Scene root with `global="true"` do not
illuminate geometry in child Transform nodes. Workaround: local PointLights
inside Transform wrappers (partially implemented via baked-in scene values).

---

## Issue 3 — SAI Type Constructors Require X3D. Prefix (RESOLVED)

**Status:** RESOLVED V2.1.9.

Confirmed by testing and John Carlson: all type constructors require `X3D.`
prefix in external SAI context. `new X3D.SFFloat()`, `new X3D.SFColor()`,
`new X3D.SFVec3f()` all work. Plain values silently ignored for typed fields.

---

## Issue 4 — PROTO IS Binding Type Mismatch Dropped Silently

**Status:** Open. IS/connect bindings from ProtoInterface SFString fields
to ProtoBody MFString fields are silently dropped at runtime. Confirmed
workaround: use MFString type for all Text node connections in PROTO fields.
All current PROTO IS bindings in `mccf_scene.x3d` use correct types.

---

## Issue 5 — SFString to MFString IS Connect Silently Dropped (RESOLVED)

**Status:** RESOLVED V2.1. All Text node `string=` attributes confirmed
correct MFString XML encoding. PROTO IS connect uses MFString type throughout.
No changes needed.

---

## Issue 6 — Light Intensity SAI Degrades Visual State

**Status:** Open. See Issue 1. `X3D.SFFloat` constructor does not resolve
intensity writes on light nodes — scene still darkens. Color writes work.
Root cause unknown — may be X\_ITE internal lighting pipeline behavior.

---

## Issue 7 — diffuseColor SAI Breaks Material Visual State (RESOLVED)

**Status:** RESOLVED V2.1.9 by root cause identification.

`bodyMat.diffuseColor = [r,g,b]` (plain array) was silently ignored.
`bodyMat.emissiveColor = new X3D.SFColor(r,g,b)` works correctly and
is now used for all avatar field-state color updates. Identity colors
preserved in baked-in diffuseColor (untouched by SAI).

---

## Issue 8 — pollLighting Hammering /ambient/sync

**Status:** RESOLVED V2.1.9.

`pollLighting()` was calling `/ambient/sync` POST on every 2-second cycle,
causing server load and slow browser response. Fixed: pollLighting now reads
cached `/lighting/scalars` only. Single sync POST fires once at startup.

---

## Summary — What Works in V2.1.9

| Feature | Status | Method |
| --- | --- | --- |
| Avatar emissiveColor | ✓ Working | `X3D.SFColor` |
| Avatar transparency | ✓ Working | `X3D.SFFloat` |
| Avatar translation | ✓ Working | `X3D.SFVec3f` |
| Text node string | ✓ Working | plain array |
| Light color | ✓ Working | plain array |
| Light intensity | ✗ Breaks scene | pending Script Node |
| diffuseColor | ✗ Use emissive instead | plain array ignored |
| ProximitySensor | Untested | in scene, fires on position |

## What Is Next (V2.2)

**V2.2 Light Master Script Node** — internal X3D Script node receives
JSON string from JavaScript, distributes color+intensity to local lights.
Bypasses all external SAI for lighting.

**V2.2 Avatar motion** — `X3D.SFVec3f` translation confirmed working.
HotHouse ψ vectors can drive avatar position. Proximity sensors will fire
on position changes. Real-time simulation layer is viable.

**Reported to:** Holger Selig (X\_ITE maintainer), John Carlson (X3DJSONLD),
W3D Consortium public list, AI Working Group.

---

*Last updated: April 2026 — V2.1.9*
*Len Bullard / Claude Sonnet 4.6*

---

---

# V3 "The New York Rocket" — Carry-Forward Items (May 2026)

Items deferred during V3 build sessions. Fetch this file at the start of
each session to ensure nothing is lost across chat boundaries.

---

## V3-1 — mccf_api.py Integration (NOT YET DONE)

**Status:** Pending. Three new V3 modules need one-line registrations in
`mccf_api.py`. Do NOT edit the file manually. Tae will provide a complete
replacement file at the start of the next integration session.

Lines to add (for reference only — wait for replacement file):

```python
from mccf_scene_generate_api import register_generate_api
from mccf_zone_attractor import register_attractor_api, AttractorRegistry
from mccf_scene_wrapper import register_scene_api
from mccf_cultivar_lambda import register_cultivar_api
from mccf_drift import DriftManager
```

**Do not edit mccf_api.py until Tae provides the complete replacement.**

---

## V3-2 — mccf_cultivars.py Patch (NOT YET DONE)

**Status:** Pending. Two lines needed at the bottom of `mccf_cultivars.py`
to inject λ (shadow context decay) into the existing cultivar dict.

```python
from mccf_cultivar_lambda import patch_cultivars_dict
CONSTITUTIONAL_CULTIVARS = patch_cultivars_dict(CONSTITUTIONAL_CULTIVARS)
```

**Do not edit mccf_cultivars.py until Tae provides the complete replacement.**

---

## V3-3 — Scene Composer: Load Existing SceneDefinition

**Status:** Deferred. The Scene Composer has no dropdown to load an existing
SceneDefinition from `scenes/`. Currently you can only create from scratch.
Needed for consistent reuse of named scenes across episodes.

**What is needed:** A dropdown in the Scene tab that lists files in `scenes/`,
loads the selected SceneDefinition, and populates zones and scene config from it.
Endpoint exists: `GET /scene/generate/scenes`.

---

## V3-4 — X3D Loader Redesign (Scene Dropdown)

**Status:** Deferred. The launcher (`mccf_x3d_loader.html`) hardwires
`static/mccf_scene.x3d`. It needs a dropdown to select from available
generated scenes, matching the multi-scene architecture.

**Decision already made:** Dropdown selector (not URL parameter).
**Do after:** V3-1 and V3-2 integration pass are complete and stable.

---

## V3-5 — exportX3D / buildX3DString Refactor

**Status:** Technical debt from V3 build session. `buildX3DString()` and
`exportX3D()` in `mccf_scene_composer.html` duplicate the same X3D build
logic. Refactor: `exportX3D()` should call `buildX3DString()` then download.
One function, two callers. Low risk, clean.

---

## V3-6 — Coherence Decrease in Zones

**Status:** Deferred by design decision. Currently proximity to a zone only
increases R_ij coherence toward it. High-pressure negative episodes in a
zone should erode coherence (decrease R_ij). Valence-weighted coherence
decay: negative episodes decrease R_ij, positive ones increase it.

**Connection:** Uses existing ResonanceEpisode valence field. Small addition
to `mccf_zone_attractor.py` `update_proximity_coherence()`.

---

## V3-7 — H-Anim Avatar Integration

**Status:** Deferred — waiting for example file. Placeholder geometry
(cylinders and spheres) currently in `mccf_avatar.proto.x3d` and in
`mccf_scene_composer.html` `buildAX3D()`.

**What to do:** When H-Anim example is available, replace the body
Transform children in the MCCFAvatar Proto body with HAnimHumanoid.
The Master Script and generator do not change — they address only the
outer Transform stack (LeanTransform, StabilityTransform, etc.).

**Contact:** John Carlson, Don Brutzman (Naval Postgraduate School).
**Reference:** V3 SPEC item 5, mccf_avatar.proto.x3d.

---

## V3-8 — Sign Language / Gesture Triggering

**Status:** Open question, not yet a build item. John Carlson asked whether
MCCF can support sign language. Architecturally yes — channel outputs (E, B,
P, S) map naturally to gesture vocabularies. E drives upper body and facial
expression, B drives posture and grounding, P drives gaze and orientation,
S drives reach and proximity. Sign language is a high-resolution version of
that same mapping.

**Cannot answer fully until:** H-Anim integration is working and we have
runtime experience with gesture triggering at the channel level.

**File and revisit** after V3-7.

---

## V3-9 — Performance Modes (Items 6, 7, 8 of V3 Spec)

**Status:** Not yet started. Remaining V3 build items:

- **Item 6:** Three performance modes (Playback, Improvisation, Live Theatre).
  Playback first — reads existing EmotionalArc XML, no LLM calls.
  New endpoint: `GET /arc/playback`.
- **Item 7:** Spatial sound activation logic. Sound nodes are already in the
  generated scene. Need activation/deactivation based on ProximitySensor
  events from the Master Script.
- **Item 8:** Garden of the Goddess scene completion — characters, narrative
  design, cultivar assignments. Len's authoring work.

**Start with Item 6 (Playback mode) at the next build session.**

---

## V3-10 — HTML Files in Repo Root

**Status:** Cleanup deferred. Several HTML files (`mccf_constitutional.html`,
`mccf_editor.html`, `mccf_launcher.html`, `mccf_x3d_loader.html`, etc.) sit
in the repo root but should be in `static/`. Moving them risks breaking
inter-file path references that are currently working.

**Do after V3 is complete:** Move all HTML to `static/`, verify all links,
push as a single cleanup commit.

---

*V3 section added: May 2026*
*Len Bullard / Claude Sonnet 4.6 (Tae)*

---

## V3 Session 2 — New Issues (May 2026)

---

## V3-11 — Playback: Avatar Does Not Translate Through Waypoints

**Status:** Open. Waypoints in arc XML have `pos_x`, `pos_y`, `pos_z`
attributes. Playback currently pushes channel state (E, B, P, S) to the
field but does not push position to the avatar Transform. Avatar stays
at its initial placement during playback.

**Fix:** In `mccf_playback.py` `_push_to_field()`, extract pos_x/pos_y/pos_z
from the ArcWaypoint and update the agent's position in the field so the
Master Script routes it to the avatar's Transform translation.

---

## V3-12 — Playback: No Voice Activation

**Status:** Open. Playback displays Q&A text but does not speak it.
The original waypoint editor had TTS with voice selection and on/off toggle.
Playback needs the same.

**What is needed:**
- Toggle in the playback panel: voice on/off
- Voice selector dropdown (same voices as constitutional navigator)
- On each waypoint advance, speak the response text via Web Speech API
  if voice is enabled

---

## V3-13 — Playback Panel: Text Too Small to Read

**Status:** Open. Question and response text in the playback panel
is too small, especially response text which can be long.
Panel needs larger font or scrollable/expandable text area for Q&A display.

---

## V3-14 — Waypoint Editor: No Question Field on Waypoints

**Status:** Open. Questions currently only exist in arc export XML
(recorded during a live arc run). Scene Composer waypoints have no
question field — there is no way to author questions for waypoints
in advance. Improvisation mode needs authored questions at each waypoint
to prompt the LLM.

**What is needed:**
- Question text field in the waypoint form in Scene Composer
- Question stored in waypoint XML on export
- Question available to the arc runner when stepping through waypoints
  in Improvisation mode

---

*V3 Session 2 additions: May 2026*
*Len Bullard / Claude Sonnet 4.6 (Tae)*

---

## V3 Session 3 — New Issues (May 2026)

---

## V3-15 — Loader/Scene Mismatch: Old Node Names vs V3 Scene

**Status:** Blocking. The X3D loader (`mccf_x3d_loader.html`) was written
for the old scene and looks for nodes named `GlobalField`, `BodyMat_Steward`,
`Pos_Steward` etc. The V3 scene generated by `mccf_x3d_generator.py` uses
different node names: `Avatar_TheWitness`, zone markers, MCCFAvatar Proto.

**Decision needed before fixing:**
Should we keep the old scene and make the generator produce compatible node
names (Path A), or commit to the V3 scene and update the loader to use V3
node names (Path B, the right long-term direction)?

**Errors seen in console:**
- `Named node 'BodyMat_Steward' not found`
- `Named node 'GlobalField' not found`
- Both fire on every poll cycle

**What works regardless:** Playback voice, text display, file selection.
Avatar position push not yet confirmed working due to node name mismatch.

---

## V3-16 — Avatar Position During Playback Not Confirmed

**Status:** Open. `pbPushPosition()` uses `canvas.browser.currentScene`
and tries `Avatar_<name>` (V3) then `Pos_<name>` (old) node names.
Not yet tested against a working scene because of V3-15.
Cindy arc exports use old `Pos_Cindy` naming. Revisit after V3-15 resolved.

---

*V3 Session 3 additions: May 2026*
*Len Bullard / Claude Sonnet 4.6 (Tae)*
