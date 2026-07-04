# MCCF Events Editor — Architecture Specification
## Version 1.1 — Day 60 (camera vessel confirmed; coordinate system; X3D SAI notes)

---

## Purpose

This document defines the division of labor between the Events Editor, the Scene Composer, and the X3D Loader for all event cue types — current and planned. It exists because the camera system revealed a recurring architectural ambiguity: when does an event cue bind a named node that is **already in the X3D file**, and when does it instruct the **runtime to compute and drive something**? Getting this wrong produces subtle bugs that compound as new event types are added.

Read this before implementing any new cue type or extending an existing one.

---

## 1. The Core Distinction — Baked vs Runtime

Every event cue that affects the 3D scene falls into one of two categories. This is not a preference — it is a structural property of what the cue targets.

### Baked

A **baked** cue targets a named node that the X3D author explicitly placed in the scene file at export time. The Loader's job is simply to find that node by name and change a property on it. The node's existence, position, and configuration are entirely the author's responsibility — the Loader is just a trigger.

The Loader never writes structural data (position, geometry, hierarchy) to a baked node. It only writes scalar state: `set_bind`, `intensity`, `visibilityRange`, `skyColor`, etc.

### Runtime

A **runtime** cue instructs the Loader to compute something and apply it to a **generic vessel node** — a node that exists solely as a writable target for the runtime system. The vessel has no meaningful authored state. Its position, orientation, or other properties are fully overwritten by the Loader at the moment the cue fires.

The author never names the vessel node in the cue. They describe what they want (a shot type, a fog density, an animation) and the Loader decides which vessel to use and what to write to it.

---

## 2. The Vessel Principle

A vessel is a node in the X3D scene whose authored values are irrelevant — it exists only so the Loader has a SAI-writable target. Vessels are:

- Added to every exported scene by the Composer automatically
- Never exposed to the author in the Events Editor UI
- Never named in cue data
- Identifiable by a reserved DEF prefix or name convention

**Current vessels:**

| Vessel | DEF name | SAI target | Used by |
|---|---|---|---|
| Free camera | `VP_Free` | `CAM_Free_Transform` (parent Transform) | All runtime camera shots |
| Scene fog | `SceneFog` | `SceneFog` directly | Fog cues (baked by convention, may become vessel) |
| Scene background | `SceneBG` | `SceneBG` directly | Background cues (baked by convention, may become vessel) |

**The VP_Free / CAM_Free_Transform pattern (confirmed Day 60):**

X3D Viewpoint `position` and `orientation` are **output** fields — they report camera state to the scene graph; SAI writes to them are ignored by X_ITE. The correct SAI pattern for a repositionable camera is:

```xml
<Transform DEF="CAM_Free_Transform" translation="0 0 0" rotation="0 1 0 0.0001">
  <Viewpoint DEF="VP_Free" description="Free Camera" position="0 0 0" orientation="0 1 0 0.0001" jump="true"/>
</Transform>
```

- The Loader writes `CAM_Free_Transform.translation` and `CAM_Free_Transform.rotation` via SAI
- These are normal input fields — X_ITE processes them correctly
- VP_Free is at local origin inside the Transform; its world position is entirely determined by the Transform
- `set_bind = true` is called on VP_Free (not on the Transform) to activate the camera
- VP_Free must have a non-zero authored orientation (even `0 1 0 0.0001`) — a zero-angle rotation produces a degenerate state in X_ITE and the viewport renders black
- VP_Free is excluded from the Loader's viewpoint toolbar but visible in X_ITE's own menu as "Free Camera"

Phase 2 animated shots (`orbit`, `dolly_in`, etc.) will drive `CAM_Free_Transform` continuously via TimeSensor interpolators — same vessel, same bind point, animated rather than one-shot.

**Planned vessels (Phase 2+):**

| Vessel | DEF name | Used by |
|---|---|---|
| Animated camera interpolators | `CAM_PosInterp`, `CAM_OriInterp`, `CAM_Timer` | Move shots (orbit, dolly, etc.) |
| Semantic field overlay | TBD | Semantic/emotional animation track |

The Composer is responsible for emitting all vessel nodes into every exported X3D file. The Loader is responsible for driving them. Neither the author nor the Events Editor cue schema should ever reference a vessel by name.

---

## 3. Track-by-Track Classification

### Camera track

| Shot type | Category | Loader action | Node |
|---|---|---|---|
| `agent_eye`, `agent_side` | **Baked** | `_bindNamedViewpoint('VP_{agent}_{Eye\|Side}')` | Named VP inside agent Transform — authored, parented, rides with avatar |
| `cue.viewpoint` set (any value) | **Baked** | `_bindNamedViewpoint(cue.viewpoint)` | Any named VP the author explicitly placed in the scene |
| `wide`, `medium`, `closeup`, `extreme_closeup`, `overhead`, `worms_eye`, `dutch`, `over_shoulder`, `profile`, `two_shot` | **Runtime** | Compute position from cue params, write to `VP_Free` via SAI, bind | `VP_Free` vessel |
| `dolly_in`, `dolly_out`, `pan`, `tilt`, `orbit`, `crane_up`, `track` | **Runtime** (Phase 2) | Drive `VP_Free` via TimeSensor interpolators | `VP_Free` + interpolator vessels |

**Rule:** `_bindNamedViewpoint` is only ever called from the baked paths. `_executeStaticCameraShot` and (future) `_executeMoveShot` are only ever called from the runtime paths. These functions must never cross-call. An unrecognised shot type warns and skips — VP_Free is never bound as a fallback.

---

### Light track

| Cue field | Category | Loader action | Node |
|---|---|---|---|
| `cue.node` names a light | **Baked** | `scene.getNamedNode(cue.node).intensity = value` | Author-placed light node with that DEF |

Light cues are currently always baked. The author must know the DEF name of the light they want to change. There is no runtime-computed light system yet.

**Future consideration:** if procedural lighting is added (e.g. "light follows subject"), the same baked/runtime distinction applies — the author would select a shot-style description, and the Loader would drive a vessel light node.

---

### Fog track

| Category | Loader action | Node |
|---|---|---|
| Currently **baked by convention** | `scene.getNamedNode('SceneFog').visibilityRange = value` | Author must include a `SceneFog` DEF in their scene |

Note: `SceneFog` is currently a convention (author must add it), not a Composer-emitted vessel. If the Composer is updated to always emit a SceneFog node, it becomes a true vessel.

---

### Background track

Same status as Fog — baked by convention on `SceneBG`. Vessel promotion pending Composer work.

---

### Behavior track

| Cue fields | Category | Loader action | Node |
|---|---|---|---|
| `cue.agent` + `cue.clip` | **Baked** | `switchBehaviorTimer(agent, clip)` | Agent TimeSensor/Script nodes authored in X3D |

Behavior cues are fully baked — they address authored TimeSensor nodes inside the agent's X3D subtree by the clip name convention. The Loader routes to `switchBehaviorTimer`, which looks up the named timer node.

---

### Semantic / Emotional animation track (Phase 2+)

This is the track most likely to introduce new architectural ambiguity. Notes for when it is designed:

The EBPS field values (E/B/P/S) are runtime data — they come from the server, not from the X3D file. Any visual encoding of these fields (color overlays, spatial distortion, particle density, shader parameters) will be driven by the Loader against vessel nodes emitted by the Composer. The author does not configure the vessel — they configure the mapping (e.g. "when E > 0.6, intensity ramps to 0.9 over 2s").

This is a **runtime track** end to end. There are no baked nodes to bind. The cue schema will describe thresholds and mappings, not node names. Designing this track without the baked/runtime distinction clearly in mind risks encoding node names in cue data — which would be wrong.

---

## 4. What Goes in a Cue — The Rule

A cue's data schema should describe **what the author wants**, not **how the Loader implements it**.

**Correct:**
```xml
<Cue shot="medium" subject="Cindy" distance="5" height="1.7"/>
```
The author said: medium shot on Cindy. The Loader decides VP_Free is the mechanism.

**Wrong:**
```xml
<Cue shot="medium" viewpoint="VP_Free" subject="Cindy"/>
```
The author has now named the implementation vessel. This breaks the abstraction — if the runtime camera vessel is ever renamed or replaced, cue data breaks. It also makes it impossible for the Loader to distinguish "author wants a named baked VP" from "author wants a computed shot."

**Correct:**
```xml
<Cue viewpoint="VP_Cindy_Overview"/>
```
The author named a specific authored VP they want bound. No shot params needed.

**Wrong:**
```xml
<Cue shot="medium" viewpoint="VP_Cindy_Overview"/>
```
Ambiguous. Two different routing systems are both indicated. One will silently win. This is the exact bug that triggered this document.

---

## 5. The Composer's Responsibilities

The Composer is the gatekeeper between the Events Editor and the X3D file. Its responsibilities in this architecture:

1. **Emit all vessel nodes** into every exported X3D — `VP_Free`, and future vessels. Authors should not need to add these manually.
2. **Never write vessel node names into cue data.** The serialization of camera cues must not include `viewpoint="VP_Free"` or any other vessel name — only authored VP names (for baked cues) or no viewpoint field at all (for runtime cues).
3. **Suppress legacy `viewpoint=` on shot= cues.** When a cue has a `shot=` value (runtime path), the Composer must not also write `viewpoint=` (Day 60 fix: `if (cue.viewpoint && !cue.shot)`).
4. **Maintain the vessel list.** As new vessel types are added, the Composer X3D export is the single place they are added to every scene. The Loader can then assume they exist.

---

## 6. The Loader's Responsibilities

1. **Route by cue content, not by fallthrough.** Every routing path must require an explicit positive condition to enter. No implicit defaults. No "everything else goes to VP_Free."
2. **Maintain explicit whitelists** for each category of shot/cue type. Unknown values warn and skip — they never silently activate a vessel.
3. **Never expose vessel names** in log output that could mislead the author into thinking they should name vessels in cues. Log the shot type and subject, not the vessel name.
4. **Clear all vessel state on Stop/Reset.** Vessels hold runtime-computed state; that state must not persist across playback sessions.

---

## 7. The Events Editor's Responsibilities

1. **Never show vessel node names** in dropdowns, inspector fields, or any author-facing UI.
2. **The shot type list is the author's vocabulary** for runtime camera. It maps to behavior, not to implementation nodes.
3. **Named VP selection** (baked path) is a separate UI element from shot type selection. The two must not be combined in a way that produces both `shot=` and `viewpoint=` in the same cue (the Day 60 bug root cause in the Events Editor was `applyShotPreset` not clearing `cue.viewpoint`).
4. **Future tracks follow the same pattern:** the author describes intent; the inspector fields encode intent; vessel names never appear.

---

## 8. X3D Coordinate System and SAI Conventions

These caused real bugs in Day 60 development and must be understood before writing any camera or spatial code.

### Coordinate system

X3D uses a **right-handed coordinate system**:
- **+X** — right
- **+Y** — up
- **+Z** — toward the viewer (out of the screen)
- **-Z** — into the scene (the direction a camera faces by default)

**A camera at the origin looks down -Z.** This is the most common source of orientation bugs.

### Camera orientation — the -Z convention

X3D cameras face -Z by default. To compute a yaw angle that makes a camera at position `camPos` face a target at `targetPos`:

```javascript
var dx = targetPos[0] - camPos[0];
var dz = targetPos[2] - camPos[2];
// CORRECT — negate to aim -Z axis at target:
var yaw = Math.atan2(-dx, -dz);

// WRONG — this aims +Z at target (camera faces away):
var yaw = Math.atan2(dx, dz);
```

The negation is not intuitive. It cost a full test cycle in Day 60. Comment it clearly whenever it appears.

### Rotations — axis-angle format

X3D rotations are `[ax, ay, az, angle]` where `(ax, ay, az)` is a unit axis vector and `angle` is in radians.

- Identity rotation: `0 1 0 0` (Y axis, zero angle) — but see degenerate state note below
- Pure yaw left 90°: `0 1 0 1.5708`
- Pure pitch down: `1 0 0 -0.4` (negative = nose down)

**Degenerate state:** X_ITE (and some other X3D browsers) mishandle a Viewpoint with `orientation="0 1 0 0"` (zero angle) — the viewport may render black. Use `0 1 0 0.0001` as a near-identity that avoids this. This affects authored Viewpoint nodes; it does not affect Transform rotation fields.

### SAI field write rules

Not all X3D fields are writable via SAI:
- `Transform.translation`, `Transform.rotation`, `Transform.scale` — **writable** ✓
- `Viewpoint.position`, `Viewpoint.orientation` — **output only**, SAI writes ignored ✗
- `Viewpoint.set_bind` — **writable** (event-in) ✓
- `PointLight.intensity`, `Fog.visibilityRange` — **writable** ✓
- `AudioClip.startTime`, `AudioClip.stopTime` — **writable** ✓

When a Viewpoint needs to be repositioned at runtime, wrap it in a Transform and write to the Transform. Never write to Viewpoint position/orientation directly.

---

## 9. Adding a New Track Type — Checklist

When a new event track is designed, answer these questions before writing any code:

1. **Is this baked or runtime?**
   - Baked: the author must know what named node they are targeting. The node exists in the X3D file because the author or the Composer put it there.
   - Runtime: the Loader computes what to do from cue parameters and drives a vessel node.
   - If both: you have two separate cue subtypes, not one. Separate them in the schema.

2. **If runtime: what is the vessel node?**
   - Name it. Add it to the Composer's X3D export. Add it to this document's vessel table.
   - Confirm the Composer always emits it. The Loader should warn at scene load if the vessel is missing.

3. **Does the cue schema contain any node names?**
   - If yes, and they are vessel names: remove them. Vessel names belong in the Loader, not in cue data.
   - If yes, and they are baked node names the author chose: that is correct. The author owns those names.

4. **What happens on Stop/Reset?**
   - Baked nodes: usually no cleanup needed (they stay at whatever state the cue left them).
   - Vessel nodes: must be reset. Add cleanup to the Stop/Reset handler alongside `_agentCurrentStep = {}` etc.

5. **What is the unrecognised-value behaviour?**
   - Always: warn and skip. Never silently activate a vessel or bind a node.

---

*Day 60. Baked vs Runtime. Vessels are implementation, not author vocabulary.*
*Day 60 confirmed: CAM_Free_Transform + VP_Free pattern working. _lookAtOrientation -Z convention fixed. Static computed shots verified in live playback.*
