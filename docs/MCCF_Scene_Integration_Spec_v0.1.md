# MCCF Scene Integration Spec — v0.1

*Day 75. Consolidates the architecture decisions reached while scoping
Timeline/Dialogue integration into `mccf_scene_composer.html`. This is a
design document, not a build log — status of what's already built and
verified lives in the Day 75 seed doc. Supersedes nothing yet; the actual
schema doc (`MCCF_Step_Track_Timeline_Schema_v0.1.md`) still governs the
`<Actor>/<Track>/<Step>/<Cue>` XML shape. This spec is about how that XML
becomes a real, playable X3D scene.*

---

## 1. The central decision: compile to native X3D, don't ship a JS runtime

`dispatcher.js` (the Timeline prototype's engine) is a pure JavaScript
polling loop — its own clock, `registerActor`/`addStep`, ticked via
`requestAnimationFrame`. It has never touched X_ITE, `TimeSensor`, or
`ROUTE`, and was built/tested entirely inside the standalone prototype
page.

`mccf_scene_composer.html`'s existing output is the opposite: every
system it already has — paths (`buildInterpNodes`), agents (`buildAX3D`),
free cameras (`buildFreeCamerasX3D`) — compiles to **native X3D**:
`TimeSensor` → `Interpolator` → `ROUTE` chains, `ProximitySensor`-driven
routes, IMPORT'd behavior timers from HAnim inline files. The file's own
label states the intent directly: *"Valid X3D 4.0 — opens in X_ITE."*
Nothing in the existing export pipeline depends on external JS at
playback time.

**Decision, confirmed by the author explicitly and by working precedent
already in the codebase:** Track/Step/Cue data compiles to native X3D —
`ROUTE`/`TimeSensor` where that reduces cleanly (declared/scene-start
timing), and a generated `<Script>` node where it doesn't (sensed-trigger
chains, collision arbitration, blend functions — logic that has no clean
ROUTE-only expression). `dispatcher.js`'s verb/trigger/collision/blend
semantics become the **spec** this generator reproduces natively, not a
file that ships at runtime.

**This is not hypothetical — it's already shipping.** `buildAX3D`'s sound
system already generates exactly this shape for ambient audio fading:

```
<Script DEF="SoundFader_<sid>" directOutput="true" mustEvaluate="true">
  <field accessType="inputOutput" type="SFTime" name="..."/>
  <![CDATA[
    function _ramp(from, to) { ... }
    function masterVolume(val, time) { ... }
  ]]>
</Script>
```

using `Browser.currentScene.getNamedNode(...)` / `.getField(...).setValue(...)`
— the real X3D 4.0 Script-node ECMAScript SAI, running inside X_ITE, no
external harness. A `TimelineDispatch_<sceneId>` Script node generated
the same way, reproducing dispatcher.js's verb/trigger/collision/blend
rules, is the direct extension of a pattern that already works in this
exact file.

### 1.1 SAI vs. Script — draw the line explicitly, per author instruction

> "We need a clear separation of SAI events and X3D script events. We
> don't add python for python's sake. If something can be done in the
> X3D scene graph, do it there."

- **X3D Script node (inside the scene graph)**: anything that's part of
  the scene's own behavior — trigger resolution, collision/arbitration,
  blend functions, field writes. This is `mustEvaluate`/`directOutput`
  Script content, authored/generated once, shipped inside the X3D file,
  runs identically whether the scene is opened by the composer's preview,
  a standalone X_ITE viewer, or (eventually) whatever ships to end users.
- **SAI from outside the scene (composer's own authoring UI)**: only for
  author-time concerns — scrubbing a preview, inspecting node state while
  editing, driving a camera during authoring. Never for anything the
  played scene needs to do on its own.
- **Python (`mccf_api.py` et al.)**: checked exhaustively this session —
  no existing timeline/event/cue/track/step logic exists there today, and
  none should be added for its own sake. Python's role stays what it
  already is: persistence (`/scene/save/scene`, `/scene/x3d/upload`),
  asset management, and the EBPS/Hothouse simulation (see §5) — not scene
  playback logic, which belongs in the X3D graph per the instruction
  above.

---

## 2. Camera: consolidate three generations of camera work, don't invent a fourth

Three real, independent bodies of camera work exist and need reconciling,
not replacing:

1. **The schema's `cameraType` enum** (`MCCF_Step_Track_Timeline_Schema_v0.1.md`
   §6): `fixed`/`orbit`/`track`/`pov`/`dolly` — five values, thin.
2. **The old events editor prototype's shot vocabulary**
   (`mccf_events_editor_prototype_2.html`, uploaded Day 75): `SHOT_MOVES`
   = `dolly_in`, `dolly_out`, `pan`, `tilt`, `orbit`, `crane_up`, `track`,
   `agent_orbit`, `agent_track`; `SHOT_ATTACHED` = `agent_eye`,
   `agent_side` — with real framing parameters (`subject`, `distance`,
   `hAngle`) the schema's enum has no room for at all. Confirmed richer.
3. **Composer's own already-working camera PROTO library**
   (`mccf_scene_composer.html` `buildFreeCamerasX3D`, ~line 3053 on):
   `<ExternProtoDeclare>` for `AgentOrbitCamera`, `AgentTrackCamera`,
   `FreeCamera`, sourced from `protos/mccf_camera_protos.x3d` — real,
   shipping X3D protos, not a design on paper. Names overlap suspiciously
   well with the old events editor's shot vocabulary (`agent_orbit`,
   `agent_track`) — likely the same lineage, worth confirming directly
   against `mccf_camera_protos.x3d` next session (not yet in hand).

**Working hypothesis, to confirm next session**: the schema's `cameraType`
attribute should map onto `ProtoInstance` selections against the existing
`mccf_camera_protos.x3d` library rather than inventing camera logic from
scratch — the Track/Step camera row becomes authoring surface over protos
that already exist and already work, not a new camera engine.

**Explicitly not carried forward**: the old events editor's embedded
X_ITE preview (`x_ite@11.6.0` via CDN, live SAI-driven viewport) and its
left-pane grid camera-positioning UI. Author confirmed both are being
retired — the preview caused tab crashes, the grid editor "was not very
functional." Camera/light *positioning* is being handled by the
grid-drop-in system in the scene/zone editor instead (§3), not rebuilt
here.

---

## 3. Modularity: PROTO everything that can be a PROTO

> "Any item that can be a proto should be. Modularity is very important
> to composability and extensibility in X3D."

Confirmed existing precedent for this principle already in the codebase:
- `<ProtoDeclare name="MCCFAgent">` / `<ProtoDeclare name="MCCFZone">` —
  real, already shipping.
- `<ExternProtoDeclare>` camera library (§2) — real, already shipping.
- Avatars: inlined from an avatars directory via `<Inline url="...">` +
  IMPORT/EXPORT of HAnim behavior timers (`buildAX3D`).
- Scene geometry / X3D assets: also inlined via `<Inline url="...">`
  (`az.url` pattern, ~line 3152).

**New, load-bearing fact for this integration, from the author directly**:
*"avatars have parented cameras as defaults in their protos."* If an
avatar's own PROTO already declares a child camera by convention, then a
Track/Step camera with `cameraType="pov"` (or `agent_eye`/`agent_side`
per §2) targeting that avatar may not need new machinery at all — it may
just need to reference the camera **already present as a child of that
avatar's own proto instance**, rather than the schema inventing a
separate POV-camera mechanism. This needs the Character Creator and an
actual avatar file to confirm (see seed doc file list) — flagged as a
hypothesis, not yet verified, deliberately not overreaching past what's
confirmed.

**Implication for the Track/Step schema itself**: any new track-kind
content this integration introduces (camera cuts, light behavior once
that track kind is unblocked) should default to "instantiate/reference an
existing proto" over "author raw X3D nodes inline," matching the
project's own stated modularity value — not just for camera, but as a
standing rule for whatever comes next.

---

## 4. Actor ↔ existing composer entities — reconciliation needed, not yet resolved

The schema's `<Actor>` concept (name, type, parent, field map, tracks)
doesn't cleanly map onto composer's existing `placedAgents` object today:

- `placedAgents[name]` today = `{position, color, hanim_src, hanim_loa,
  behavior_clips}` — geometric placement + H-Anim figure assignment. No
  concept of a field map, tracks, or trigger-driven behavior at all.
- Non-avatar Actor types the schema already covers (`SceneFog`, `Door`,
  `Camera`, `Audio`, `Movie` — see the Ground Tremor worked example) have
  **no equivalent in composer's data model whatsoever** — composer's
  `zones`/`paths`/`placedAgents`/`placedCameras` don't cover props, fog,
  doors, or ambient audio/movie actors whose fields need affect-driven
  writes.

**Open question, unresolved, needs an explicit author decision (see seed
doc §3)**: does Track/Step data attach directly onto `placedAgents`
entries (avatars gain tracks in place), with a **new, parallel entity**
for the non-avatar Actor types the schema already needs (fog/door/camera/
audio/movie) — or is there a unifying "Actor" layer above both that
composer doesn't have yet and needs to grow? This is the single largest
open data-model question blocking real integration work and should be
the first thing resolved next session, before writing any generator code.

---

## 5. Priority: this all serves the EBPS/Hothouse system, not the other way around

> "Pay attention to the EBPS hothouse and emotion system. It is the
> cherry on top of our system, and the reason we built it."

EBPS = the four affect channels (`E`/`B`/`P`/`S`) already load-bearing
throughout the codebase — `ChannelVector` in `mccf_core.py`, zone pressure
application in `mccf_zone_api.py`'s `/sensor/spatial`, and the
`channelE`/`channelB`/`channelP`/`channelS`/`emotionalInterpreter`
dialogue-affect fields added to `dialogue-xml.js` on Day 74. The
"Hothouse" simulation (`mccf_hotHouse.py`, `mccf_couplers.py`,
`mccf_drift.py`, `mccf_neoriemannian.py`, `mccf_core.py`) is the actual
research core of this project.

**Explicit reminder for whoever picks this up next**: the Timeline/Track/
Step visual-authoring work this session focused on is scaffolding *for*
that system, not a replacement priority. Every field-map `arbitration`
rule (`replace`/`blend`/`track-wins`), every `affect-writable` field, and
the dialogue affect-tagging work all exist specifically so the EBPS field
simulation has somewhere to land its output inside a played scene. Scene
integration work should keep asking "does this make it easier for the
Hothouse system's output to actually reach the screen," not treat
Timeline/camera/dialogue authoring as the end in itself. If a design
choice ever trades off between Timeline-authoring convenience and EBPS
field expressiveness, EBPS wins.

---

## 6. Recommended approach: module-by-module review, not a big-bang integration

> "It probably will be worth our time to review the Scene Creator modules
> one at a time and see what we can consolidate. So a module-by-module
> review is needed."

Composer (`mccf_scene_composer.html`, 5035 lines, single inline script,
no external module boundaries today) has at minimum these distinct
subsystems, each with its own state and `buildXXX()` export function:

| Subsystem | State | Export function(s) |
|---|---|---|
| Zones | `zones{}` | `buildZX3D` |
| Agents (avatars) | `placedAgents{}` | `buildAX3D` |
| Paths | `paths{}`, `waypoints{}` | `buildInterpNodes` |
| Free cameras | `placedCameras` (referenced, not yet traced) | `buildFreeCamerasX3D` |
| Ambient audio | (inline within agent/zone export) | `SoundFader_*` Script gen |
| Character Creator | separate file, iframed | n/a — own export path, not yet traced |

Recommended order for next session's module-by-module pass — cheapest/
highest-signal first:

1. **Camera** — most prior art already exists across three sources (§2),
   likely the fastest to actually consolidate into one coherent system.
2. **Actor/Agent reconciliation** — blocking everything else (§4); needs
   an explicit decision before generator code can be written for any
   other track kind.
3. **Character Creator + avatar PROTO structure** — needed to confirm the
   parented-camera-in-proto hypothesis (§3) and to understand what
   "avatars have parented cameras as defaults" actually looks like in a
   real file.
4. **Dialogue** — schema/`dialogue-xml.js` already solid and verified;
   mostly a question of how a `<Dialogue>` block's audio/TTS output
   reaches X3D `Sound`/`AudioClip` nodes, likely following the same
   `SoundFader_*` Script pattern already proven for ambient audio.
5. **Fog/prop/generic `set`-verb tracks** — needs the Actor-reconciliation
   answer from step 2 first; probably the most mechanical once that's
   settled.
6. **Light** — stays explicitly deferred; `MCCF_Lighting_System_Spec_v0.1_DRAFT.md`
   already calls this blocked on an X_ITE capabilities research pass this
   spec doesn't attempt to resolve.

---

## 7. What's already solid and shouldn't be re-litigated

Carried forward from Day 75's verification work, all confirmed by actual
execution (jsdom + real-browser testing), not assumption:

- `MCCF_Step_Track_Timeline_Schema_v0.1.md` — the `<Actor>/<Track>/<Step>/
  <Cue>` XML shape itself. Stable; this integration consumes it, doesn't
  redesign it (camera's richer vocabulary from §2 is an *extension* of
  the existing `cameraType` attribute's value space, not a schema
  rewrite).
- `dispatcher.js` — its verb/trigger/collision/blend *semantics* are the
  spec for the native-X3D generator (§1); the file itself isn't what
  ships, but isn't wasted work — every rule in it needs a native-X3D
  equivalent, and having a tested JS reference to check the generator's
  output against is exactly what makes that generator verifiable.
- `dialogue-xml.js`, `field-map.js`, `timeline-xml.js`,
  `worked-manifests.js` — all bug-fixed and verified this session; no
  known issues.
- `mccf_timeline_dialogue_prototype_v2.html` — both tabs (Timeline,
  Dialogue) fully functional and verified, including the trigger-editor
  UI and copyable scrub-time panel added this session. Useful as an
  **authoring/preview tool** going forward even after the compile-to-X3D
  pipeline exists — it's how someone would build a Track/Step scene
  before exporting it through the new composer-side generator. Not being
  deprecated by this integration.
