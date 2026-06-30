# MCCF Camera System Specification
## Version 1.3 — Day 62 (agent_orbit confirmed working; X_ITE SAI API corrections; baked-vs-runtime taxonomy extended)

---

## 1. Design Principles

- **Inline per-cue** — camera shot parameters live inside the cue that fires them. No separate camera library or named camera objects.
- **Runtime computed** — free-camera shot positions are calculated at playback time from the subject agent's current world position, written to `VP_Free`. Never baked into X3D at export time.
- **Agent-attached exception** — shots parented to an agent Transform (`agent_eye`, `agent_side`, `agent_orbit`) resolve by binding a named Viewpoint inside that agent's X3D Transform node, not by computing a free camera position. Same cue format, different resolution path in the Loader.
- **Parenting beats tracking** — if a shot needs to follow a moving subject indefinitely, the correct architecture is a baked Viewpoint inside the subject's own Transform, never a free camera that recomputes the subject's world position every frame. Confirmed Day 62 via `agent_orbit`. See §3a.
- **All transitions are explicit** — cut (TELEPORT) or fly (free camera interpolation). No X_ITE black-box transitions.
- **Terrain agnostic** — camera Y is always relative to subject Y + height offset. Terrain following is a NavigationInfo WALK concern, not a camera concern.

---

## 2. Shot Type Taxonomy

### Static Shots (runtime, free camera, VP_Free)
| Shot Type | Description | Default Distance | Default Height | Default H.Angle | Default V.Angle | Default Roll |
|---|---|---|---|---|---|---|
| `wide` | Full environment, subject small in frame | 12m | 3.0m | 0° | -15° | 0° |
| `medium` | Waist-up, background visible | 5m | 1.7m | 0° | -8° | 0° |
| `closeup` | Face/detail, background soft | 1.5m | 1.7m | 0° | -5° | 0° |
| `extreme_closeup` | Single feature, maximum tension | 0.4m | 1.7m | 0° | 0° | 0° |
| `overhead` | Straight down, strategic/abstract | 0m | 10m | 0° | -90° | 0° |
| `worms_eye` | Ground level looking up, scale/awe | 1.5m | 0.1m | 0° | +35° | 0° |
| `dutch` | Eye level, roll applied, unease/tension | 3m | 1.7m | 0° | -8° | ±25° |

### Relational Shots (runtime, free camera, computed once per cue-fire — DO NOT follow a moving subject)
| Shot Type | Description | Default Distance | Default Height | Default H.Angle | Notes |
|---|---|---|---|---|---|
| `over_shoulder` | Behind and offset, subject's POV implied | 0.8m | 1.6m | -20° | Camera behind subject, looking past ear toward scene |
| `profile` | 90° side view | 3m | 1.7m | 90° | Flatters movement, reveals silhouette |
| `two_shot` | Frames two agents together | computed | 1.7m | computed | Midpoint between subject and secondary agent |

**Day 62 design note:** `over_shoulder`, `profile`, and `two_shot` are candidates for conversion to the baked agent-attached pattern (§3a), the same way `orbit` was converted to `agent_orbit`. This conversion has been deliberately deferred — see §3b, Character Creator decision.

### Agent-Attached Shots (baked, parented inside the agent's own Transform)
| Shot Type | Description | Notes |
|---|---|---|
| `agent_eye` | Subject's own POV | Binds `VP_{agent}_Eye`, static local offset, no SAI position writes |
| `agent_side` | Fixed side cam on agent | Binds `VP_{agent}_Side`, static local offset, no SAI position writes |
| `agent_orbit` | Continuous circular orbit around the agent, follows it if it moves | Binds `VP_{agent}_Orbit`, animated via per-agent TimeSensor + interpolators driving a local-offset Transform. See §3a. |

### Camera Moves (runtime, free camera, interpolated — Phase 2)
| Shot Type | Description | Key Parameters | Status |
|---|---|---|---|
| `orbit` | Circular path around a *fixed world point*, computed once at cue-fire time | radius, start angle (full 360° sweep), duration, loop | Implemented (free/world-space variant) |
| `dolly_in` | Push toward subject | start distance, end distance, duration | Not yet implemented |
| `dolly_out` | Pull back from subject | start distance, end distance, duration | Not yet implemented |
| `pan` | Rotate horizontally in place | start h.angle, end h.angle, duration | Not yet implemented |
| `tilt` | Rotate vertically in place | start v.angle, end v.angle, duration | Not yet implemented |
| `crane_up` | Arc upward and back | start height, end height, arc depth, duration | Not yet implemented |
| `track` | Lateral move parallel to subject | start offset, end offset, duration | Not yet implemented — best remaining candidate for agent-attached conversion, since it explicitly tracks a moving subject |

**Important distinction (Day 62):** the free/world-space `orbit` move shot circles a *fixed point in space*, captured once when the cue fires. If the subject moves during the orbit, the camera does **not** follow — it keeps circling the original point. This is architecturally correct and intentional for `orbit`; if subject-following is wanted, use `agent_orbit` instead. These are two different shot types with overlapping names in concept only — never conflate them in code or documentation.

---

## 3. Cue Data Schema

### All camera cues (common fields)
```xml
<Cue
  type="camera"
  trigger="w2 arrive"
  delay="0"
  t="0"
  dur="2"
  label="closeup Cindy"

  shot="closeup"
  subject="Cindy"

  transition="cut"
  flyDuration="1.5"

  distance="1.5"
  height="1.7"
  hAngle="0"
  vAngle="-5"
  roll="0"
/>
```

### Two-shot additional field
```xml
  subject2="The Witness"
```

### Move shots additional fields
```xml
  distanceEnd="8.0"
  hAngleEnd="90"
  vAngleEnd="-20"
  heightEnd="6.0"
  loop="true"
```
`loop` applies to `orbit` and `agent_orbit`. Other move shots ignore it (single play-through, hold last frame).

### Agent-attached shots (eye/side)
```xml
  shot="agent_eye"
  subject="Cindy"
  <!-- distance/height/angle fields ignored — VP inside Transform is used -->
```

### Agent-attached orbit
```xml
  shot="agent_orbit"
  subject="Cindy"
  distance="8.6"      <!-- orbit radius -->
  height="3.2"        <!-- orbit height above avatar local origin -->
  hAngle="0"          <!-- start angle -->
  vAngle="-8"          <!-- look-down tilt -->
  dur="4"             <!-- one full revolution, in seconds -->
  loop="true"         <!-- repeat indefinitely until next camera cue -->
```
No `hAngleEnd` — agent_orbit always sweeps a full 360°. No `transition` — always a continuous animated bind, cut/fly is not a meaningful choice.

---

## 3a. Agent-Attached Architecture (confirmed Day 62)

This is the authoritative pattern for any shot that must follow a moving subject indefinitely. It replaces runtime world-position tracking entirely.

### The principle
A Viewpoint parented inside an avatar's own Transform inherits that avatar's world position and orientation automatically, via ordinary X3D scene-graph semantics — exactly the way `VP_Cindy_Eye` has always worked. No JavaScript polling of the avatar's current position is needed, and none should be written. If a shot's camera math ever reads the subject's world position more than once (i.e. continuously, frame-by-frame, to "follow" it), that is the signal the shot belongs in this category, not in the free/world-space `VP_Free` system.

### Per-avatar baked nodes (emitted by Composer for every avatar)
```xml
<Transform DEF="Avatar_{name}" translation="x 0 z">
  ...avatar body/HAnim figure...

  <Viewpoint DEF="VP_{name}_Eye"   .../>
  <Viewpoint DEF="VP_{name}_Side"  .../>

  <Transform DEF="CAM_OrbitXform_{name}" translation="0 3.2 8.6" rotation="0 1 0 0">
    <Viewpoint DEF="VP_{name}_Orbit" description="{name} Orbit"
               position="0 0 0" orientation="0 1 0 0.0001" jump="true"/>
  </Transform>
  <TimeSensor DEF="CAM_OrbitTimer_{name}" cycleInterval="4" loop="false" enabled="false"/>
  <PositionInterpolator    DEF="CAM_OrbitPosInterp_{name}" key="0" keyValue="0 3.2 8.6"/>
  <OrientationInterpolator DEF="CAM_OrbitOriInterp_{name}" key="0" keyValue="0 1 0 0.0001"/>
</Transform>

<!-- Static ROUTEs, scoped per-agent, emitted alongside the nodes above -->
<ROUTE fromNode="CAM_OrbitTimer_{name}"     fromField="fraction_changed" toNode="CAM_OrbitPosInterp_{name}" toField="set_fraction"/>
<ROUTE fromNode="CAM_OrbitTimer_{name}"     fromField="fraction_changed" toNode="CAM_OrbitOriInterp_{name}" toField="set_fraction"/>
<ROUTE fromNode="CAM_OrbitPosInterp_{name}" fromField="value_changed"    toNode="CAM_OrbitXform_{name}"     toField="set_translation"/>
<ROUTE fromNode="CAM_OrbitOriInterp_{name}" fromField="value_changed"    toNode="CAM_OrbitXform_{name}"     toField="set_rotation"/>
```

These three Viewpoints (`Eye`, `Side`, `Orbit`) are currently **generic and identical across every avatar** — they are added uniformly by the Composer's `buildAvatarX3D` function regardless of which character is being exported. They are not part of any individual avatar's authored asset (e.g. Cindy's H-Anim file does not itself define a camera rig). See §3b for why per-avatar customization of this set is deferred rather than built now.

### Loader resolution — `_executeAgentOrbit(cue)`
1. Resolve `subjectSafe` from `cue.subject` (sanitized to match DEF naming).
2. Compute 37 keyframes (0°–360°, every 10°) as a **relative offset around local origin `[0,0,0]`** — never the subject's world position. This is the key difference from the free-orbit math: there is no `subjectPos` lookup at all, because the parent Transform already places the math in the right coordinate space.
3. Write keyframes to `CAM_OrbitPosInterp_{name}` / `CAM_OrbitOriInterp_{name}` via indexed array assignment (§4, SAI API corrections).
4. Snap `CAM_OrbitXform_{name}` to the keyframe-0 position, bind `VP_{name}_Orbit` (instant TELEPORT to orbit start — intentional, matches the authored start angle).
5. One rAF later, set `CAM_OrbitTimer_{name}.startTime` (with the `currentTime` fallback, §4) and `.enabled = true`.
6. Routing: the static XML ROUTEs are also re-asserted via `Browser.addRoute()` at cue-fire time as a defensive measure — confirmed harmless to call redundantly, and removes any dependency on whether the static XML ROUTEs parsed correctly in a given X_ITE build.

### Stop/Reset
`pbStopX3DTimers` iterates `window._avatarNodeNames` and disables every agent's `CAM_OrbitTimer_{name}`, not just a single global timer. This is necessary because, unlike the free camera system (one `CAM_Timer` for the whole scene), agent-attached orbit is genuinely per-avatar and multiple avatars can be orbiting simultaneously.

---

## 3b. Character Creator Decision (Day 62 — held, not yet implemented)

Initial Day 62 discussion proposed extending the agent-attached pattern to `over_shoulder`, `profile`, and reframing `two_shot` as an over-the-shoulder variant aimed at a second subject. Two implementation paths were considered:

1. **Composer-baked, generic defaults** — add `OverShoulder`/`Profile` to the same uniform per-avatar set the Composer already emits (identical offsets for every avatar, no per-character authoring).
2. **Character Creator-authored, per-avatar** — since Character Creator already has the avatar loaded for editing, let the author interactively position and save each avatar's own camera rig there, the same tier as the avatar's behavior clip set (idle/walk/run/kick). This would make camera shots part of the avatar's own asset definition rather than a scene-export-time addition, and would allow different avatars (or avatar *types* — adult vs child proportions, human vs creature) to have meaningfully different default framings.

**Decision: held for testing before implementation.** Option 2 is the architecturally preferred direction — it correctly separates "what shots exist for this character" (an avatar-asset concern) from "when and how they're used in a scene" (an Events Editor concern) — but it requires Character Creator UI work that has not yet been scoped. Do not implement `over_shoulder`/`profile` as Composer-baked generic shots in the meantime; that would create a second migration later when Character Creator work begins. The existing free/world-space versions of `over_shoulder` and `profile` (§2, Relational Shots) remain the only implementation until this is revisited.

---

## 4. X_ITE SAI API — Corrections Confirmed Day 62

The following were incorrectly assumed or fabricated during initial orbit implementation and cost significant debugging time. These are now confirmed against official X_ITE documentation and/or working code elsewhere in this codebase. Treat this section as authoritative over any earlier spec version or training-data assumption about X3D/VRML SAI conventions.

### `canvas.browser.currentTime` returns 0 in this X_ITE build
Confirmed broken in the installed X_ITE version (11.6.0 at time of writing). Every `startTime` write on any TimeSensor must use the fallback already established elsewhere in the Loader:
```javascript
var t0 = (canvas.browser.currentTime && canvas.browser.currentTime > 0)
  ? canvas.browser.currentTime : (performance.now() / 1000);
node.startTime = t0;
```
This was the root cause of the Day 62 "orbit snaps to start position and freezes" bug. The symptom was deceptive: keyframes were correct, the ROUTE chain was correct, the TimeSensor was even reporting `isActive` correctly — but `fraction_changed` evaluated to `NaN` on every tick because `startTime` was silently `0`, and the interpolator always returned keyframe 0 as a result. Diagnosing this required isolating each link in the chain with field callbacks (see below) rather than assuming any single component was at fault.

### TimeSensor and Transform fields — direct property assignment, not `getField().setValue()`
Confirmed working pattern, consistent everywhere else in this codebase:
```javascript
node.enabled        = true;
node.loop            = true;
node.cycleInterval   = 4;
node.startTime       = t0;
```
NOT `node.getField('enabled').setValue(true)`. Both forms exist in the X_ITE API, but `getField().setValue()` was the path that initially failed to register changes reliably for these particular fields in this codebase's usage pattern — direct assignment is now the standardized convention for all scalar (SF) field writes outside of one exception: see below.

### MF (multi-value) fields — indexed assignment, never a bulk constructor
```javascript
// CORRECT — confirmed against official X_ITE GitHub README example
interpolator.key.length      = 0;       // truncate stale authored values first
interpolator.keyValue.length = 0;
for (var i = 0; i <= STEPS; i++) {
  interpolator.key[i]      = fractionValue;
  interpolator.keyValue[i] = new X3D.SFVec3f(x, y, z);
}

// WRONG — these constructors do not exist in X_ITE's public API; fabricated, never worked
interpolator.key.setValue(new X3D.MFFloat(...values));
interpolator.keyValue.setValue(new X3D.MFVec3f(...sfvec3fArray));
```
This was the second major bug of the day. `X3D.MFFloat`/`X3D.MFVec3f`/`X3D.MFRotation` bulk constructors were assumed by analogy to the SF types but do not exist anywhere in this codebase's working code nor in official X_ITE examples. The correct API treats `key` and `keyValue` as plain indexable arrays (`X3DArrayField`), assigned element-by-element. `array.length = 0` is the confirmed way to clear stale values before repopulating — assigning to `array[i]` beyond current length auto-expands the array per the X_ITE Field Services reference.

### `Transform.translation`/`.rotation` ROUTE targets use the `set_` prefix
```xml
<ROUTE fromNode="PosInterp" fromField="value_changed" toNode="SomeTransform" toField="set_translation"/>
```
This was a point of genuine confusion: the Transform node's own field table lists `translation`/`rotation` as `[in,out]` with no documented `set_translation` alias. However, the official X_ITE "Animating Transforms" tutorial's own canonical worked example routes into `set_translation`/`set_rotation` explicitly, and this is the form that was ultimately confirmed working. Use the `set_` prefix for all ROUTE targets into Transform fields, regardless of what the bare field-table listing implies.

### `Browser.addRoute(sourceNode, sourceField, destinationNode, destinationField)` is a real, documented SAI method
Confirmed in the official X_ITE Browser Services reference (Legacy VRML Methods section). Useful as a defensive, idempotent-safe way to assert a ROUTE programmatically at runtime in addition to whatever static ROUTEs exist in the exported X3D — removes dependency on whether static XML `<ROUTE>` parsing succeeded for a given node ordering or X_ITE build quirk. Both the free-orbit and agent-orbit implementations now call this redundantly alongside the static XML ROUTEs.

### `addFieldCallback(key, fieldName, callback)` — the correct live-value diagnostic/listener API
```javascript
node.addFieldCallback('myUniqueKey', 'fraction_changed', function(value) {
  // value is ALREADY the plain current value — no .getValue() method exists on it
  console.log(value);
});
```
Confirmed against the official Field Services reference and against pre-existing working usage elsewhere in this codebase (behavior timer polling). `addFieldInterest` — initially guessed by analogy to other 3D engine APIs — does not exist in X_ITE and throws `e.getId is not a function` if called.

**Critical safety note:** the callback body is invoked synchronously by X_ITE from inside its own event-processing loop (`X3DRoutingContext.processEvents`). An uncaught exception inside the callback body aborts that entire event-processing batch, which can stall unrelated scene state — this was observed directly on Day 62, when a malformed diagnostic callback caused the avatar's walk animation to freeze mid-scene, even though the camera system and the avatar system are otherwise unrelated. Every `addFieldCallback` callback body must wrap its own logic in try/catch; the registration call (`addFieldCallback(...)` itself) being wrapped in try/catch is not sufficient, since that only protects against registration failure, not runtime callback failure.

**Stale-key warning:** X_ITE ignores `addFieldCallback` if the same key is registered twice on the same node/field — relevant if a cue can fire more than once per session (e.g. `agent_orbit` firing again later for the same avatar). Diagnostic-only callbacks used for one-time debugging should be removed once the underlying bug is fixed, rather than left in production code, both for this reason and for the synchronous-exception risk above.

---

## 5. Position Computation Formulas

```javascript
// All angles in degrees, converted to radians internally

function computeStaticPosition(subjectPos, distance, height, hAngleDeg) {
  var hRad = hAngleDeg * Math.PI / 180;
  return [
    subjectPos[0] + distance * Math.sin(hRad),
    subjectPos[1] + height,
    subjectPos[2] + distance * Math.cos(hRad)
  ];
}

function computeOrientation(camPos, targetPos, vAngleDeg) {
  // Vector from camera to target, apply vertical angle offset
  // Returns X3D axis-angle [ax, ay, az, angle]
  // Confirmed -Z convention — see §6.
}

function computeOrbitKeyframes(subjectPos, radius, startDeg, steps) {
  // Full 360° sweep, 37 steps (every 10°) confirmed sufficient for smooth playback.
  // subjectPos is [0,0,0] for agent_orbit (local-space, parented) —
  // a non-zero world position for the free/world-space orbit move shot.
}
```

---

## 6. VP_Free Node (X3D) — Free/World-Space Camera Vessel

A single free-floating Viewpoint at scene root, emitted by Composer X3D export, used by all static shots and the free/world-space `orbit`/move shots:

```xml
<Transform DEF="CAM_Free_Transform" translation="0 0 0" rotation="0 1 0 0">
  <Viewpoint DEF="VP_Free" description="Free Camera"
             position="0 0 0" orientation="0 1 0 0.0001" jump="true"/>
</Transform>

<TimeSensor DEF="CAM_Timer" cycleInterval="4" loop="false" enabled="false"/>
<PositionInterpolator    DEF="CAM_PosInterp" key="0" keyValue="0 0 0"/>
<OrientationInterpolator DEF="CAM_OriInterp" key="0" keyValue="0 1 0 0.0001"/>

<ROUTE fromNode="CAM_Timer"     fromField="fraction_changed" toNode="CAM_PosInterp" toField="set_fraction"/>
<ROUTE fromNode="CAM_Timer"     fromField="fraction_changed" toNode="CAM_OriInterp" toField="set_fraction"/>
<ROUTE fromNode="CAM_PosInterp" fromField="value_changed"    toNode="CAM_Free_Transform" toField="set_translation"/>
<ROUTE fromNode="CAM_OriInterp" fromField="value_changed"    toNode="CAM_Free_Transform" toField="set_rotation"/>
```

`VP_Free` is a **vessel node** — it exists solely as a SAI-writable target for the runtime camera system. Its authored position and orientation are irrelevant; they are overwritten by the Loader at the moment a runtime cue fires.

**Rules for VP_Free:**
- The Composer emits it, `CAM_Timer`, and both interpolators into every exported X3D scene automatically.
- The author never sees it, names it, or selects it in the Events Editor.
- It never appears in cue data (`viewpoint="VP_Free"` in a cue is always wrong).
- The Loader only binds VP_Free as a consequence of a static or move shot type — never as a default or fallback.
- VP_Free is excluded from the Loader's viewpoint toolbar (`_vpExclude`) so the author cannot accidentally bind it manually.
- On Stop/Reset, VP_Free's bind state and `CAM_Timer` are cleared alongside all other runtime state.
- `VP_Free.key`/`VP_Free.keyValue` initial authored placeholders must be valid X3D values (e.g. `key="0" keyValue="0 0 0"`), never empty strings — an empty string is not a parseable MFFloat/MFVec3f and may cause the Loader's first SAI write to that node to silently fail depending on X_ITE's strictness for malformed initial field state.

**Orientation computation — X3D -Z convention:**

X3D cameras face -Z by default. The look-at yaw must negate the direction vector:

```javascript
// To face camera at camPos toward targetPos:
var yaw = Math.atan2(-(targetPos[0]-camPos[0]), -(targetPos[2]-camPos[2]));
// NOT: Math.atan2(dx, dz)  ← that aims +Z at target (camera faces away)
```

This convention applies identically inside `agent_orbit`'s local-space math — the only difference is `targetPos` is `[0,0,0]` (local origin) rather than a world-space subject position.

---

## 7. Events Editor — Inspector Fields by Shot Type

| Field | Static shots | Relational | Move shots (free) | agent_eye / agent_side | agent_orbit |
|---|---|---|---|---|---|
| Shot type | ✓ | ✓ | ✓ | ✓ | ✓ |
| Subject | ✓ | ✓ | ✓ | ✓ | ✓ |
| Subject 2 | — | two_shot only | — | — | — |
| Transition / fly duration | ✓ | ✓ | always fly | — | — (always animated bind) |
| Distance | ✓ | ✓ | start only | — | ✓ (= orbit radius) |
| Distance End | — | — | ✓ | — | — (always full 360°) |
| Height | ✓ | ✓ | ✓ | — | ✓ |
| Height End | — | — | ✓ | — | — |
| H. Angle | ✓ | ✓ | start only | — | ✓ (= start angle) |
| H. Angle End | — | — | ✓ | — | — |
| V. Angle | ✓ | ✓ | ✓ | — | ✓ |
| Roll | dutch only | — | — | — | — |
| Loop | — | — | orbit/agent_orbit only | — | ✓ |
| Delay | ✓ | ✓ | ✓ | ✓ | ✓ |

`agent_orbit` is functionally a hybrid: baked routing (like agent_eye/agent_side, in the dropdown's "attached" group) but with move-shot-style framing and timing fields, since unlike eye/side it has continuous animated state. It is excluded from `SHOT_ATTACHED` (which zeroes all framing fields) but included in `SHOT_MOVES` (which shows framing-as-start-values and the loop checkbox) and a dedicated `SHOT_AGENT_ORBIT` set (which suppresses the now-meaningless `*End` fields and cut/fly transition radios that a generic move shot would otherwise show).

---

## 8. Stage Canvas — Camera Visualization

When a camera cue is selected in the Events Editor:
- Agent positions drawn at their waypoint locations (grayed, non-interactive)
- Camera position shown as a small **square icon** (existing style)
- **FOV cone** drawn from camera position toward subject: apex = camera, opening angle ~40°, length proportional to distance
- Cone color matches transition type: cool blue = cut, amber = fly
- Move shots show a **curved arc** instead of a static cone
- Dragging the cone apex on canvas updates `hAngle` in the inspector (future enhancement)

---

## 9. Open Items / Future

| Item | Notes |
|---|---|
| Character Creator camera authoring | Held Day 62 — see §3b. Per-avatar camera rig as an asset-tier concern, parallel to behavior clips. |
| `over_shoulder` / `profile` agent-attached conversion | Deferred pending §3b decision |
| `two_shot` as over-the-shoulder variant aimed at subject2 | Deferred pending §3b decision — position parented to subject A, rotation computed toward subject2 at cue-fire time |
| `track` agent-attached conversion | Best remaining candidate after `over_shoulder`/`profile` — genuinely needs to follow a moving subject from the side |
| `dolly_in` / `dolly_out` / `pan` / `tilt` / `crane_up` | Not yet implemented (Phase 2 continues) |
| Rack focus simulation | CSS blur on X_ITE iframe overlay — deferred |
| True lens FOV zoom | `fieldOfView` SAI write reliability TBD in X_ITE |
| Crossfade dissolve | Fade-to-black + cut + fade-in via HTML overlay — deferred |
| Terrain-aware height | `getHeightAt(x,z)` heightmap lookup — Saturn III |
| Drag-to-position on stage canvas | Click/drag cone apex to set hAngle — future |

---

## 10. Routing Rules (Loader Implementation)

The `_fireCameraEventCue` function uses explicit whitelists to enforce the baked/runtime boundary. Extended Day 62 to add the `agent_orbit` branch, which must be checked alongside (not merged into) the `agent_eye`/`agent_side` branch since its execution path is meaningfully different (continuous animated bind, not a one-shot `set_bind`).

```javascript
// Baked cameras — Loader binds a named authored node, or drives a per-agent animated rig
// 1. agent_eye / agent_side  →  _bindNamedViewpoint('VP_{subject}_{Eye|Side}')
// 2. agent_orbit             →  _executeAgentOrbit(cue) — binds VP_{subject}_Orbit,
//                                drives CAM_OrbitTimer_{subject} + per-agent interpolators
// 3. cue.viewpoint set       →  _bindNamedViewpoint(cue.viewpoint)

// Runtime cameras — Loader drives VP_Free vessel via SAI
// 4. _STATIC_SHOTS[shot]     →  _executeStaticCameraShot(cue)
// 5. _MOVE_SHOTS[shot]       →  _executeMoveShot(cue)  [orbit implemented; others Phase 2]

// No match — warn and skip. VP_Free is never bound as a fallback.
var _STATIC_SHOTS = {
  wide, medium, closeup, extreme_closeup, overhead,
  worms_eye, dutch, over_shoulder, profile, two_shot
};
var _MOVE_SHOTS = {
  dolly_in, dolly_out, pan, tilt, orbit, crane_up, track
};
// agent_orbit is checked explicitly, not via a whitelist object — see _fireCameraEventCue.
```

`_bindNamedViewpoint`, `_executeAgentOrbit`, `_executeStaticCameraShot`, and `_executeMoveShot` are strictly separated — they never cross-call. Adding a new shot type requires adding it to the appropriate whitelist (or an explicit branch, for hybrid cases like `agent_orbit`); the routing logic itself does not change.

### Stop/Reset — per-agent timer cleanup
```javascript
// Free camera (singular)
CAM_Timer.enabled = false;

// Agent-attached orbit (per-avatar — iterate every avatar in the scene)
window._avatarNodeNames.forEach(function(avatarDEF) {
  var safeName = avatarDEF.replace(/^Avatar_/, '');
  var orbitTimer = scene.getNamedNode('CAM_OrbitTimer_' + safeName);
  if (orbitTimer) orbitTimer.enabled = false;
});
```
This is a structural difference from the free camera system worth remembering when adding future agent-attached move types: anything per-avatar needs a Stop/Reset loop over all avatars, not a single cleanup call.

---

## Camera Cue Quick Tutorial

The basic idea: you're placing moments in time where the camera cuts or moves to a specific shot. Each cue says when it fires (trigger), what shot it takes, and who it's looking at.

**Step 1 — Add a camera cue.** Click + Add cue in the toolbar. A new cue appears on the Camera track at the current playhead position. The inspector on the right shows its properties.

**Step 2 — Set the trigger.** The Trigger dropdown at the top of the inspector is the most important field. `w2 arrive` means the shot fires when the navigator arrives at Waypoint 2. This is how camera cuts sync to story beats — no manual timing needed.

**Step 3 — Pick a shot type.** The Shot Type dropdown is grouped:
- **Static** — Wide, Medium, Close-Up, etc. Camera floats at a computed position relative to the subject, world-space, one-time.
- **Relational** — Over Shoulder, Profile, Two Shot. Camera positions itself relative to how the subject is facing, world-space, one-time.
- **Agent POV** — Eye, Side, and Orbit. Eye and Side use the Viewpoints already built into the agent's Transform — the most reliable shots for live playback. Orbit continuously circles the agent and follows it if it moves, using the same parented-Viewpoint principle.
- **Camera Moves** — Dolly, Pan, Orbit (free/world-space), etc. These drive the free camera interpolator. Note: the free "Orbit" in this group circles a fixed point and does not follow a moving subject — for that, use Agent Orbit instead.

Changing the shot type auto-fills the framing sliders with sensible defaults.

**Step 4 — Pick a subject.** Select which agent the shot is about. The stage canvas on the left updates to show a blue cone (cut) or amber cone (fly) from the computed camera position toward that agent.

**Step 5 — Transition.** `cut` = instant teleport. `fly` = smooth interpolated move. The fly duration slider appears when fly is selected. Agent Orbit has no transition choice — it is always a continuous animated bind.

**Step 6 — Framing sliders.**
- Distance — how far the camera is from the subject (orbit radius, for Agent Orbit)
- Height — camera Y above ground (1.7m = eye level)
- H. Angle — horizontal angle around the subject (0° = in front, 90° = left side, -90° = right side; start angle for Agent Orbit)
- V. Angle — tilt (negative = looking down slightly, which is normal for most shots)
- Roll — only appears for Dutch Angle shots
- Loop — appears for Orbit and Agent Orbit only; repeats continuously until the next camera cue fires

**Step 7 — Delay.** Under Timing, delay fires the cue N seconds after the trigger. So `w2 arrive` + delay 2.0s = shot fires 2 seconds after arriving at WP2.

**Step 8 — Export.** Export cues sends everything to the Composer, which saves it to the scene XML. The Loader picks it up on next play.

---

*Day 58. Inline per-cue. Runtime computed. Free camera for moves. Agent-attached for POV shots.*
*Day 60. Camera routing rewritten (baked/runtime split). CAM_Free_Transform pattern confirmed. _lookAtOrientation -Z fix. Static computed shots verified in live playback.*
*Day 61. Named VP UI. Camera preview (live slider feedback). Avatar persistence fixed.*
*Day 62. agent_orbit implemented and confirmed working in live playback — camera follows a moving avatar indefinitely via Transform parenting, no position tracking required. Major X_ITE SAI API corrections discovered during debugging: currentTime=0 bug, direct property assignment for SF fields, indexed assignment for MF fields, set_ prefix required on Transform ROUTE targets, addFieldCallback as the correct (not addFieldInterest) diagnostic API, callback-body exception safety. Per-agent baked viewpoint set (Eye/Side/Orbit) now dynamically enumerated by Composer rather than hardcoded per-scene. Character Creator camera-authoring architecture proposed and deliberately held pending testing — see §3b.*
