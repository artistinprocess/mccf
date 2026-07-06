# MCCF HAnim Behavior Activation — Design Specification
## From Field Values to Scene Graph Motion

**Version:** 1.2.0
**Prepared:** Day 23 — 2026-05-22
**Updated:** Day 61 — 2026-06-28 — authored override, Fallback Principle, persistence notes added
**Updated:** Day 65 — 2026-07-06 — corrected SAI mechanism throughout (see §0), resolved §8.1, added live-test confirmation
**Status:** Tasks 1–5 implemented and confirmed live (Day 65). Tasks 6b/6c partially designed, not yet built.
**Reference files:** `mccf_x3d_loader.html`, `mccf_cultivar_lambda.py`, `mccf_hotHouse.py`
**Avatar reference:** `JinLOA4Animated.x3d` (W3C HAnim examples repository)
**Companion spec:** `MCCF_Timeline_Scheduling_Architecture.md` (Day 65) — governs *when* authored behavior overrides fire; this spec governs *why* the field selects a clip and *how* the SAI write happens. The two are independent; do not conflate them.

---

## 0. Day 65 Correction Notice — Read This First

**Every code sample in this document originally used `startTime`/`stopTime` to switch behavior timers. This was wrong, and the error persisted through the Day 61 revision despite being empirically contradicted five weeks earlier.**

`mccf_behavior_spec.md` (Day 25) already stated plainly: *"`enabled=true/false` is the ONLY working SAI mechanism in X_ITE. `startTime`, `stopTime` do NOT work for behavior switching. Do not use them."* The actual shipped code in `mccf_x3d_loader.html` has always used `enabled=true/false` and carries this exact comment at the site of every write:

```javascript
// MECHANISM (confirmed Day 25): enabled=true/false is the correct SAI path.
// startTime/stopTime do NOT work in X_ITE for behavior switching.
```

This document's Task 3/4 pseudocode, however, still specified `targetNode.startTime = now + 0.05` and `node.stopTime = now + 0.01` as of the Day 61 update — and §8.1 posed the already-answered question to the W3C HAnim WG as if it were still open. Every code sample below has been corrected to match what was actually built and confirmed working. If you are implementing from an older printed or cached copy of this document, discard it — the mechanism it describes does not work.

This is also, independently, a caution worth stating plainly: a design doc surviving a dated "Updated" revision without being checked against the thing it describes is exactly how this kind of drift happens. Treat any code sample in any MCCF spec as provisional until cross-checked against the actual shipped file, not as settled fact because it has a version number.

---

## 1. Governing Principle

**MCCF activates behaviors in the scene graph. It does not write them.**

HAnim keyframe animation data — walk cycles, idle poses, gesture clips — lives entirely
in the X3D file authored by the HAnim modeler. MCCF's role is to read the agent's current
emotional field values (`observed_cv`) and select which named clip is currently appropriate.
This is a director calling a cue, not a puppeteer driving joints.

This separation means:

- HAnim authors work in HAnim editors, not MCCF
- MCCF authors set emotional thresholds, not joint rotations
- The same HAnim file can serve multiple cultivars in the same scene
- Improving the HAnim file never requires touching MCCF code

**Facial animation uses HAnim Displacers, not joint rotation.** The `l/r_eyelid_joint`,
`l/r_eyebrow_joint`, and `temporomandibular` joints present in `JinLOA4Animated.x3d`
are structural anchors; actual facial deformation in a production LOA 4 character requires
`HAnimDisplacer` nodes with `CoordinateInterpolator` targets. Displacer activation is a
separate design task (see Section 9). This spec covers **behavioral clip selection only**.

---

## 2. Scope and Constraints

### In scope for this spec
- `<Behaviors>` element: XML schema for cultivar behavior clip tables
- `behavior_clips` field: `CultivarDefinition` dataclass addition
- `mccf_cultivar_lambda.py`: parse and serialize `<Behaviors>`
- `mccf_x3d_loader.html`: `selectBehaviorClip()` function and hothouse polling integration
- Multi-instance timer naming convention for shared-mesh agents
- Cindy's reference `<Behaviors>` table (first authored example)
- Anna's `<Behaviors>` table (Librarian / monologue-delivery profile)

### Out of scope for this spec
- HAnim Displacer facial animation (Section 9 — future spec)
- HAnim editor module for Character Creator (future sprint)
- LOA 2 static avatar behavior (deferred — not needed now)
- `<Receptivity>` extension from the Relational Dynamics spec
  (independent track, does not block behavior activation)
- **Scheduling/timing of authored overrides** — see `MCCF_Timeline_Scheduling_Architecture.md` (Day 65). That spec governs *when* an authored cue fires; this spec governs *what* fires and *why* the field would have chosen something else.

### Architecture invariants — never violated
These carry forward from the Day 23 session handoff and are restated here for
reviewer context:

```
waypointOrder (SFInt32, initializeOnly) — REQUIRED on every Path
constitutional_cv (phi)  — written ONLY by arc/record
expressive_cv (eps)      — written ONLY by couplers
observed_cv              — phi + eps clamped [0,1]
SAI avatar position:     avatarNode.translation = new X3D.SFVec3f(x, y, z)
All Timers/Dwells:       enabled="false" in X3D file at load time
ROUTEs MUST be last in X3D scene
```

Additional invariant introduced by this spec:

```
Behavior clip selection — driven by observed_cv, never by phi or eps alone
Timer instance names   — suffixed with _AgentSafeName for multi-instance scenes
Behavior state         — tracked per agent in JS, not in Python
Clip change            — enabled=false on all others, enabled=true on selected (mutual exclusion)
```

---

## 3. HAnim File Analysis — JinLOA4Animated.x3d

This is the reference LOA 4 file and the current basis for the `JinLOA4` avatar
used by Cindy and all future LOA 4 agents in the MCCF garden_001 / hypoborea_001 scene.

### 3.1 TimeSensor inventory

Eight named `TimeSensor` nodes, all `loop='true'`, all disabled at load time:

| DEF name | cycleInterval | Semantic |
|---|---|---|
| `DefaultTimer` | 6.0 s | Idle/stand — breathing, weight shift |
| `PitchTimer` | 5.73 s | Forward/backward lean — attentive stand |
| `YawTimer` | 10.0 s | Side-to-side sway — casual orientation |
| `RollTimer` | 10.0 s | Roll motion — relaxed or uncertain |
| `WalkTimer` | 2.5 s | Walk cycle |
| `RunTimer` | (not set) | Run cycle |
| `JumpTimer` | 5.5 s | Jump — high arousal |
| `KickTimer` | 5.5 s | Kick — high-energy action |

### 3.2 Joint groups relevant to MCCF channels

**Spine and posture (P channel):**
`vl5, vl4, vl3, vl2, vl1` (lumbar), `vt12–vt1` (thoracic), `vc7–vc1` (cervical)

**Head and orientation (S channel):**
`skullbase`, `humanoid_root` (whole-body yaw/facing)

**Face structurally present (E channel — Displacer required for deformation):**
`l_eyelid_joint`, `r_eyelid_joint`, `l_eyeball_joint`, `r_eyeball_joint`,
`l_eyebrow_joint`, `r_eyebrow_joint`, `temporomandibular`

**Hands (E channel — gesture expressiveness):**
Full finger hierarchy both hands — `l/r_metacarpophalangeal_1–5`,
`l/r_carpal_proximal/distal_interphalangeal_2–5`

### 3.3 Existing control mechanism in JinLOA4Animated.x3d

The file ships with `TouchSensor` nodes (`Stand_Touch`, `Walk_Touch`, etc.) that
fire `touchTime → set_startTime` / `touchTime → set_stopTime` ROUTEs for mutual
exclusion between clips. MCCF replaces this user-click mechanism with SAI writes
from the loader's behavior selection function. The ROUTEs remain in the file and
are harmless; the `TouchSensor` nodes become inactive during MCCF playback.

Note (Day 65): the file's own internal ROUTE mechanism uses `startTime`/`stopTime`
between its own TouchSensor and TimeSensor nodes — that is a different code path
(pure X3D event routing, evaluated inside the browser's own event graph) from an
*external SAI script* writing to those same fields from JavaScript. The former
works; the latter, per Day 25, does not reliably drive a clean switch in X_ITE.
This is not a contradiction — it is two different mechanisms sharing field names.

---

## 4. The `<Behaviors>` XML Element

### 4.1 Schema

Added as an optional child of `<CultivarDefinition>`. Default if absent: `DefaultTimer`
runs continuously (equivalent to current behavior — no regression).

```xml
<Behaviors default="Default">
  <Clip name="Default"  timerDEF="DefaultTimer"  B_max="0.30"                   loop="true"  priority="0"/>
  <Clip name="Attentive" timerDEF="PitchTimer"   B_min="0.25" B_max="0.55"
                                                  P_min="0.50"                   loop="true"  priority="1"/>
  <Clip name="Casual"   timerDEF="YawTimer"      B_min="0.25" B_max="0.55"
                                                  P_max="0.50"                   loop="true"  priority="1"/>
  <Clip name="Walk"     timerDEF="WalkTimer"     B_min="0.50" B_max="0.78"      loop="true"  priority="2"/>
  <Clip name="Run"      timerDEF="RunTimer"      B_min="0.78" B_max="0.92"      loop="true"  priority="3"/>
  <Clip name="Jump"     timerDEF="JumpTimer"     B_min="0.90"                   loop="false" priority="4"/>
  <Clip name="Kick"     timerDEF="KickTimer"     E_min="0.80"                   loop="false" priority="4"/>
</Behaviors>
```

### 4.2 Attribute semantics

| Attribute | Required | Type | Meaning |
|---|---|---|---|
| `name` | yes | string | Human label for author reference |
| `timerDEF` | yes | string | Base DEF name of the TimeSensor in the HAnim file |
| `B_min` / `B_max` | no | float [0,1] | B channel range for this clip |
| `E_min` / `E_max` | no | float [0,1] | E channel range for this clip |
| `P_min` / `P_max` | no | float [0,1] | P channel range for this clip |
| `S_min` / `S_max` | no | float [0,1] | S channel range for this clip |
| `loop` | no | bool | Whether the timer loops (`true`) or fires once (`false`) |
| `priority` | no | int | Tiebreak when multiple clips match; higher wins |

**Omitted min/max attributes are unconstrained** — `B_max="0.30"` with no `B_min`
means B in [0.0, 0.30]. A clip with no channel constraints matches always (catch-all).

**`loop="false"` clips** (Jump, Kick) fire once when their condition is entered,
play to completion, then return control to the last `loop="true"` clip. The loader
tracks this via the `_agentLastLoopClip` state variable.

**`default` attribute on `<Behaviors>`** names the catch-all clip that plays when
no other clip's conditions are met. Defaults to `"Default"` which maps to `DefaultTimer`.

### 4.3 Selection algorithm

Evaluated whenever field state (`observed_cv`) updates for an agent. Only fires
SAI writes when the selected clip changes — not on every update.

```
function selectBehaviorClip(agentName, observed_cv, clips, defaultClipName):

  cv = observed_cv   // {E, B, P, S} floats in [0,1]

  // Separate one-shot and looping candidates
  oneshots  = clips where loop=false and conditions met
  loopers   = clips where loop=true  and conditions met, sorted by priority desc

  if oneshots is non-empty:
      best = highest priority oneshot
      if best != _agentCurrentClip[agentName]:
          fireClip(agentName, best, oneshot=true)
      return

  if loopers is non-empty:
      best = loopers[0]
  else:
      best = defaultClip

  if best.name != _agentCurrentClip[agentName]:
      switchToClip(agentName, best)
```

**Condition test for a single clip:**
```
function clipConditionMet(clip, cv):
  for each channel constraint [E, B, P, S]:
      if clip.{ch}_min defined and cv[ch] < clip.{ch}_min: return false
      if clip.{ch}_max defined and cv[ch] > clip.{ch}_max: return false
  return true
```

### 4.4 Hysteresis

To prevent rapid clip switching at threshold boundaries, a **hysteresis band of ±0.03**
is applied. Once a clip is active, it remains active until the relevant CV value
has moved at least 0.03 past the boundary that would trigger a switch. This is
implemented as a per-agent boundary memory, not as a change to the authored thresholds.

Confirmed in the shipped implementation as a widened condition window on the
*currently playing* clip only (`_BEHAV_HYST`), rather than a separately tracked
per-channel boundary-memory object — functionally equivalent, simpler to implement.

---

## 5. Multi-Instance Timer Naming

When two agents share the same HAnim file (e.g. both use `JinLOA4Animated.x3d`),
the scene contains two instances of each TimeSensor node. They must be addressed
independently. The naming convention follows the existing MCCF pattern for all
agent-scoped nodes:

**Convention:** `{BaseTimerDEF}_{AgentSafeName}`

Where `AgentSafeName` is the agent's name with non-alphanumeric characters replaced
by underscores — identical to the `safeId` already computed in the loader for
`BodyMat_`, `GazeMat_`, `Arrival_`, `Timer_`, etc.

**Examples:**
```
WalkTimer_Cindy        // Cindy's walk timer
WalkTimer_Salida       // Salida's walk timer (independent instance, different avatar file)
DefaultTimer_Cindy
DefaultTimer_Salida
```

**Implementation note (Day 65 confirmed):** the scene X3D declares these as
`IMPORT ... AS` aliases from each agent's Inline HAnim file:

```xml
<IMPORT inlineDEF="HAnim_Cindy"  exportedDEF="WalkTimer" AS="WalkTimer_Cindy"/>
<IMPORT inlineDEF="HAnim_Salida" exportedDEF="WalkTimer" AS="WalkTimer_Salida"/>
```

The Loader resolves these via `scene.getImportedNode(base + '_' + agentSafeName)`
in a retry loop (`pbActivateX3DTimers`), building the `_behaviorTimerMap[agentSafeName]`
JS-side map described below. This is the approach this document's original Task 2
flagged as the safer fallback if DEF-renaming wasn't supported by X_ITE's SAI — it
was not, and the fallback is what was built.

**Day 65 live-test finding:** this mechanism resolved correctly for Cindy on the
first attempt in a real Play All run, mapping all eight timer bases immediately.
The identical code path failed all twenty retry attempts for Salida in the same
run. Since the code, timing, and scene context were identical between the two
agents, this isolates the defect to the content of Salida's underlying HAnim file
(`SalidaAnimations_repaired_test.x3d`) — it very likely does not expose the same
TimeSensor/EXPORT structure `cindy_hanim.x3d` does. **This is an asset-repair task,
not a defect in the mechanism described in this section**, which is now confirmed
working end-to-end for at least one real agent in a real scene.

---

## 6. Implementation Tasks

These are ordered by dependency. Each task is a discrete, testable unit.

**Status as of Day 65: Tasks 1–5 are implemented and confirmed working in the
shipped `mccf_x3d_loader.html` (verified by direct code inspection and by a live
Play All test showing Cindy's full clip chain — timer mapping, DefaultTimer start,
walk/idle switching via `_wirePathTimerBehavior` — functioning correctly). The
task descriptions below are retained for reference and because the corrected SAI
mechanism (§0) applies to all of them; treat this section as documentation of what
was built, not a to-do list, except where marked otherwise.**

---

### Task 1 — `mccf_cultivar_lambda.py`: `<Behaviors>` parse and serialize

**File:** `mccf_cultivar_lambda.py`
**Status:** Implemented (Day 65 confirms `behavior_clips` arriving correctly via the cultivar API and populating `_agentBehaviorClips` at arc-record time)

**`CultivarDefinition` dataclass:**
```python
# Behavior clip table — optional, loaded from <Behaviors> element
# List of dicts: {name, timerDEF, loop, priority, E_min, E_max, B_min, B_max,
#                 P_min, P_max, S_min, S_max}
behavior_clips: list = field(default_factory=list)
behavior_default: str = "Default"
```

**`_from_element()`:**
```python
beh_el = root.find("{*}Behaviors")
behavior_default = "Default"
behavior_clips = []
if beh_el is not None:
    behavior_default = beh_el.get("default", "Default")
    for clip_el in beh_el.findall("{*}Clip"):
        clip = {
            "name":      clip_el.get("name", ""),
            "timerDEF":  clip_el.get("timerDEF", "DefaultTimer"),
            "loop":      clip_el.get("loop", "true").lower() == "true",
            "priority":  int(clip_el.get("priority", 0)),
        }
        for ch in ("E", "B", "P", "S"):
            for bound in ("min", "max"):
                key = f"{ch}_{bound}"
                val = clip_el.get(key)
                if val is not None:
                    clip[key] = float(val)
        behavior_clips.append(clip)
```

**`to_xml()`** (after `<HAnimFigure>` block):
```python
if self.behavior_clips:
    lines.append('')
    lines.append(f'  <Behaviors default="{self.behavior_default}">')
    for clip in self.behavior_clips:
        attrs = f'name="{clip["name"]}" timerDEF="{clip["timerDEF"]}"'
        for ch in ("E", "B", "P", "S"):
            for bound in ("min", "max"):
                key = f"{ch}_{bound}"
                if key in clip:
                    attrs += f' {key}="{clip[key]}"'
        attrs += f' loop="{"true" if clip["loop"] else "false"}"'
        attrs += f' priority="{clip["priority"]}"'
        lines.append(f'    <Clip {attrs}/>')
    lines.append('  </Behaviors>')
```

**`to_dict()` / `from_dict()`:**
```python
"behavior_clips":   self.behavior_clips,
"behavior_default": self.behavior_default,
```

---

### Task 2 — `mccf_x3d_loader.html`: TimeSensor resolution at avatar placement

**File:** `mccf_x3d_loader.html`
**Status:** Implemented, as the `getImportedNode` retry-loop approach (see §5) rather than the DEF-rename approach originally proposed here — confirmed working for Cindy, confirmed failing for Salida due to avatar-file content (§5).

```javascript
var BEHAVIOR_TIMER_BASES = [
    'DefaultTimer','PitchTimer','YawTimer','RollTimer',
    'WalkTimer','RunTimer','JumpTimer','KickTimer'
];
```

The safer fallback flagged in the original version of this task — a JS-side map
resolved via `getImportedNode` rather than a DEF-rename API — is what was built,
inside `pbActivateX3DTimers`, populating `_behaviorTimerMap[agentSafeName][base]`.

---

### Task 3 — `mccf_x3d_loader.html`: `selectBehaviorClip()` and `applyBehaviorClip()`

**File:** `mccf_x3d_loader.html`
**Status:** Implemented, confirmed working for Cindy Day 65. **Mechanism corrected from the original Task 3 text — see §0.**

**State variables (as shipped):**
```javascript
var _agentCurrentClip    = {};   // {agentSafeName: clipName}
var _agentLastLoopClip   = {};   // {agentSafeName: clipName} — for oneshot return
var _behaviorTimerMap    = {};   // {agentSafeName: {timerDEF: node}}
var _agentBehaviorClips  = {};   // {agentSafeName: {clips:[], default:str}}
                                  // populated at _seedArcRecord (first waypoint per cultivar)
```

**Core selection function (as shipped):**
```javascript
function selectBehaviorClip(agentSafeName, cv) {
  var config = _agentBehaviorClips[agentSafeName];
  if (!config || !config.clips || !config.clips.length) return;

  var clips   = config.clips;
  var defName = config.default || 'Default';
  var current = _agentCurrentClip[agentSafeName];

  function conditionMet(clip) {
    var chs = ['E','B','P','S'];
    for (var i = 0; i < chs.length; i++) {
      var ch = chs[i];
      var val = (cv && cv[ch] !== undefined) ? cv[ch] : 0.25;
      var minKey = ch + '_min', maxKey = ch + '_max';
      var hyst = (clip.name === current) ? _BEHAV_HYST : 0;   // widen for currently-playing clip
      if (clip[minKey] !== undefined && val < clip[minKey] - hyst) return false;
      if (clip[maxKey] !== undefined && val > clip[maxKey] + hyst) return false;
    }
    return true;
  }

  var oneshots = clips.filter(function(c) { return !c.loop  && conditionMet(c); });
  var loopers  = clips.filter(function(c) { return  c.loop  && conditionMet(c); });
  loopers.sort(function(a,b) { return (b.priority||0) - (a.priority||0); });

  var selected;
  if (oneshots.length) {
    oneshots.sort(function(a,b) { return (b.priority||0) - (a.priority||0); });
    selected = oneshots[0];
  } else if (loopers.length) {
    selected = loopers[0];
  } else {
    selected = clips.find(function(c) { return c.name === defName; }) || clips[0];
  }

  if (!selected) return;
  if (selected.name === current) return;   // no change — skip SAI write

  applyBehaviorClip(agentSafeName, selected);
}
```

**Clip activation function (as shipped — CORRECTED mechanism):**
```javascript
function applyBehaviorClip(agentSafeName, clip) {
  var timerMap = _behaviorTimerMap[agentSafeName];
  if (!timerMap) return;

  // MECHANISM (confirmed Day 25): enabled=true/false is the correct SAI path.
  // startTime/stopTime do NOT work in X_ITE for behavior switching.
  Object.keys(timerMap).forEach(function(base) {
    if (base !== clip.timerDEF) {
      try { timerMap[base].enabled = false; } catch(e) {}
    }
  });

  var targetNode = timerMap[clip.timerDEF];
  if (!targetNode) {
    console.warn('applyBehaviorClip: timer not found:', clip.timerDEF, agentSafeName);
    return;
  }

  try {
    targetNode.enabled = true;
  } catch(e) {
    console.warn('applyBehaviorClip: SAI write failed for', agentSafeName, clip.timerDEF, e);
    return;
  }

  var previous = _agentCurrentClip[agentSafeName] || '(none)';
  _agentCurrentClip[agentSafeName] = clip.name;

  if (clip.loop) {
    _agentLastLoopClip[agentSafeName] = clip.name;
  } else {
    // Oneshot: fire once, then return to last looping clip
    var returnTo  = _agentLastLoopClip[agentSafeName] || 'Default';
    var duration  = 5500;   // conservative fallback if cycleInterval unavailable
    try {
      var ci = targetNode.cycleInterval;
      if (ci && ci > 0) duration = Math.round(ci * 1000);
    } catch(e) {}
    setTimeout(function() {
      if (_agentCurrentClip[agentSafeName] !== clip.name) return;
      var config = _agentBehaviorClips[agentSafeName];
      if (!config) return;
      var returnClip = (config.clips || []).find(function(c) { return c.name === returnTo; });
      if (returnClip) applyBehaviorClip(agentSafeName, returnClip);
    }, duration + 150);
  }
}
```

---

### Task 4 — Load behavior clips at arc/record time

**File:** `mccf_x3d_loader.html`
**Status:** Implemented — confirmed by Day 65 console trace showing `behavior_clips` fetched from `GET /cultivars/<name>` and populating `_agentBehaviorClips` before playback.

When `_seedArcRecord()` calls `GET /cultivars/{name}`, the response includes
`behavior_clips` and `behavior_default` (Task 1). Stored as:

```javascript
if (cultivarData.behavior_clips && cultivarData.behavior_clips.length) {
    _agentBehaviorClips[agentSafeName] = {
        clips:   cultivarData.behavior_clips,
        default: cultivarData.behavior_default || 'Default'
    };
} else {
    // No behavior table: default to DefaultTimer always running
    _agentBehaviorClips[agentSafeName] = {
        clips: [{ name:'Default', timerDEF:'DefaultTimer', loop:true, priority:0 }],
        default: 'Default'
    };
}
// Start DefaultTimer immediately (CORRECTED mechanism — enabled, not startTime)
var timerMap = _behaviorTimerMap[agentSafeName] || {};
var defNode  = timerMap['DefaultTimer'];
if (defNode) {
    defNode.enabled = true;
    _agentCurrentClip[agentSafeName]  = 'Default';
    _agentLastLoopClip[agentSafeName] = 'Default';
}
```

---

### Task 5 — Reset cleanup

**File:** `mccf_x3d_loader.html`
**Status:** Implemented.

```javascript
// In pbReset()/pbPlayAll's state reset, before a new run:
_agentCurrentClip    = {};
_agentLastLoopClip   = {};
// Do NOT clear _behaviorTimerMap or _agentBehaviorClips —
// those are populated at placement/arc-record and survive reset.
```

---

### Task 6 — Author Cindy's `<Behaviors>` table

**File:** `Cindy.xml` (cultivar XML)
**Status:** Confirmed live Day 65 — Cindy's clip chain fired correctly in a real Play All run.

```xml
<Behaviors default="Default">
  <Clip name="Default"   timerDEF="DefaultTimer" B_max="0.30"                  loop="true"  priority="0"/>
  <Clip name="Attentive" timerDEF="PitchTimer"   B_min="0.25" B_max="0.55"
                                                  P_min="0.50"                  loop="true"  priority="1"/>
  <Clip name="Casual"    timerDEF="YawTimer"      B_min="0.25" B_max="0.55"
                                                  P_max="0.50"                  loop="true"  priority="1"/>
  <Clip name="Walk"      timerDEF="WalkTimer"     B_min="0.50" B_max="0.80"    loop="true"  priority="2"/>
  <Clip name="Run"       timerDEF="RunTimer"      B_min="0.80" B_max="0.92"    loop="true"  priority="3"/>
  <Clip name="Jump"      timerDEF="JumpTimer"     B_min="0.90"                 loop="false" priority="4"/>
</Behaviors>
```

---

### Task 7 — Author Salida's / Anna's `<Behaviors>` table

**File:** cultivar XML for whichever agent is authored as the second character
**Status:** Design note retained from the original "Anna" naming; the actual second
agent placed and tested Day 65 was Salida. Same profile intent applies to whichever
cultivar fills this narrative role — stationary, postural, high-P, low-B threshold
for movement.

```xml
<Behaviors default="Default">
  <Clip name="Default"   timerDEF="DefaultTimer" B_max="0.50"                  loop="true"  priority="0"/>
  <Clip name="Address"   timerDEF="PitchTimer"   B_min="0.40" B_max="0.80"
                                                  P_min="0.60"                  loop="true"  priority="1"/>
  <Clip name="Walk"      timerDEF="WalkTimer"     B_min="0.80"                 loop="true"  priority="2"/>
</Behaviors>
```

Design note: `B_max="0.50"` for Default means the character stays in idle stance
for the bottom half of the B range. The `Walk` threshold at `0.80` is deliberately
high — during monologue delivery the field pushes P up and keeps B moderate,
landing in `Address` (PitchTimer — forward lean, attentive posture). Path-driven
walking to a waypoint is unaffected by this table (X3D `TimeSensor.enabled` for
path segments is a separate mechanism from field-driven behavioral walking,
per §1) — this table only governs *ambient* posture between path segments.

---

## 6a. The Fallback Principle — Field as Default Performer

This principle governs the relationship between authored behavior triggers and
field-driven clip selection. It is the behavioral analog of the LLM fallback
in the dialog system:

> **If no behavior is authored for this moment, the field decides.**

In the dialog system: if no response is authored for a waypoint question, the
LLM answers from the cultivar's constitutional profile. The field provides the
voice. In the behavior system: if no clip is authored for this moment, the
field-driven `selectBehaviorClip()` selects from the `<Behaviors>` table. The
field provides the body.

This means:

- A sparsely authored scene has a living, responsive avatar — the field fills
  the gaps between scripted moments with emotionally continuous motion
- A densely authored scene has precise narrative control — authored cues fire
  at story beats, field-driven selection handles everything between
- The same scene replayed with a different field trajectory produces visually
  different performances even with identical authored cues — the body is
  always responsive to accumulated emotional state

**The author scripts the peaks. The field handles the texture.**

This inverts the usual game engine authoring model, where everything is
scripted and the engine handles physics. In MCCF, the field is the default
performer and the author is the exception-handler.

**Day 65 note:** this principle is the reason `MCCF_Timeline_Scheduling_Architecture.md`
explicitly excludes ambient behavior selection from its scope. A shared scene
clock is for authored, discrete moments — putting the field's continuous,
reactive texture onto a fixed clock would delete the exact property this
section describes as the point of the system.

---

### 6b. Authored Behavior Override — Events Editor Integration

The Events Editor behavior track fires explicit clip selections at authored
moments. These must take priority over field-driven selection for their
duration, then yield back to the field.

**Status: designed, not yet implemented.** When built, its *firing moment* should
route through the scene-clock dispatch mechanism in `MCCF_Timeline_Scheduling_Architecture.md`
rather than the trigger-string mechanism shown below, if precise timing matters
for the cue. The `_agentAuthoredClip` override mechanism itself (what happens once
it fires) is unaffected by which scheduling path invokes it.

#### State variable

```javascript
// {agentSafeName: {timerDEF, clipName, expiresAt}}
// Set by authored cue; cleared when expiresAt is passed.
// selectBehaviorClip() checks this first on every evaluation.
var _agentAuthoredClip = {};
```

#### Priority rule

```
function selectBehaviorClip(agentSafeName, cv):

  // 1. Authored override — check first, always wins
  var override = _agentAuthoredClip[agentSafeName];
  if (override && Date.now() < override.expiresAt):
      if override.clipName != _agentCurrentClip[agentSafeName]:
          applyBehaviorClip(agentSafeName, override)
      return

  // 2. Field-driven selection — runs when no authored override is active
  ... (existing algorithm, section 4.3) ...
```

#### Authored cue fires via EventCues behavior track

```javascript
// cue = { track:'behavior', agent:'Cindy', clip:'JumpTimer',
//          dur:3, delay:0, trigger:'w2 arrive' }   // or start_t/duration — see Timeline spec
function _fireBehaviorEventCue(cue) {
  var safeName = (cue.agent||'').replace(/[^A-Za-z0-9_]/g,'_');
  var durationMs = ((cue.dur || 2) + (cue.delay || 0)) * 1000;
  _agentAuthoredClip[safeName] = {
    timerDEF:  cue.clip,
    clipName:  cue.clip,
    expiresAt: Date.now() + durationMs
  };
  // enabled=true, not startTime — mechanism corrected per §0
  applyBehaviorClip(safeName, { timerDEF: cue.clip, loop: true });
}
```

#### Expiry and return

When the override expires, `selectBehaviorClip()` falls through to field-driven
selection on the next evaluation. No explicit "return to last clip" call is needed —
the field simply resumes selecting. Consistent with the one-shot clip return
mechanism already in section 4.3.

#### Mutual exclusion with field-driven one-shots

If a field-driven one-shot (Jump, Kick) fires while an authored override is active,
the one-shot is suppressed — the authored cue holds. One-shots can only fire from
field selection when no authored override is present.

---

### 6c. Persistence and Accrual — Planned Extension

The Chorus fires at scene end as an independent observer summarizing the full
field transcript. This output is the natural accumulator for cross-scene memory.

**Planned architecture (not yet implemented):**

- `chorus_log` table: keyed by scene/arc, stores Chorus summary text and final
  field values (EBPS) at scene end
- Scene N+1 seed: Chorus summary from Scene N injected into the system prompt
  context for the LLM at arc/record time — field arrives already shaped by
  what the Chorus witnessed
- Constitutional drift: field setpoints (φ) accumulate small offsets from
  high-tension episodes across arcs — a cultivar who experienced sustained
  high-E scenes arrives in new scenes with a slightly elevated E baseline
- Chorus as conscience: accumulated Chorus summaries compressed and reinjected
  as long-term context — the observer's memory becomes part of the scene's
  moral atmosphere

This is the behavioral analog of persistent memory in dialog systems. The field
has a past. Characters don't remember explicitly — they arrive in a field already
shaped by accumulated experience.

**Implementation order:** dialog persistence first (simpler), then field
persistence, then Chorus accrual as the synthesis layer.

**Note for future sessions:** This is new territory. Integration of an LLM as
a continuous field observer whose accumulated output shapes subsequent scene
state has no established precedent in interactive 3D. The design rules are
being written here.

---

## 7. Cultivar Profile Implications for Behavior

The HotHouse archetypes in `mccf_hotHouse.py` establish ideology vectors that
directly inform how behavior thresholds should be set in `<Behaviors>`.
This table documents the intended mapping for future cultivar authors:

| Cultivar | ideology.B | Typical B range in scene | Walk threshold | Movement character |
|---|---|---|---|---|
| Cindy | ~ 0.35 (active) | 0.2 – 0.6 | 0.50 | Moves readily |
| Anna (Librarian) | ~ 0.25 (deliberate) | 0.2 – 0.5 | 0.80 | Stationary during speech |
| The Steward | 0.25 (ideology) | 0.1 – 0.4 | 0.70 | Slow, purposeful |
| The Archivist | 0.40 (structured) | 0.3 – 0.6 | 0.65 | Methodical |
| The Gardener | TBD | TBD | 0.55 | Moderate |

The same HAnim mesh can represent all of these. The `<Behaviors>` table
determines what the field value means for each character's body.

---

## 8. W3C HAnim WG Review Points

### 8.1 TimeSensor mutual exclusion via SAI — RESOLVED Day 65

~~Is there a preferred HAnim pattern for runtime clip switching via SAI that
avoids the brief frame gap between stop and start? Does `stopTime`/`startTime`
guarantee a clean transition?~~

**This question is withdrawn.** It was already answered empirically on Day 25,
five weeks before the Day 61 revision of this document still posed it as open:
`startTime`/`stopTime` do not work reliably for this purpose in X_ITE.
`enabled=true` / `enabled=false` does, cleanly, with no observed frame-gap
artifact across live testing including a real two-agent Play All run on Day 65.
No WG input is needed on this point. Left here, struck through, as a record of
the correction rather than a live question.

### 8.2 DEF renaming via SAI

For multi-instance scenes (two agents sharing the same HAnim file), MCCF needs
to address each agent's TimeSensor instances independently. The current design
uses a JS-side map (`_behaviorTimerMap`, resolved via `getImportedNode` against
`IMPORT ... AS` aliases declared in the scene X3D) rather than SAI DEF renaming.
Confirmed working Day 65 for at least one agent (Cindy) in live testing. Is
there a supported SAI mechanism for addressing nodes by instance in X3D 4.0
that would be more direct than the IMPORT/AS + retry-resolution approach
currently in use? Relevant to X_ITE (Holger Seelig, Savage Studio) as well.

### 8.3 Displacer activation for facial expression

The MCCF E channel is intended to drive facial expressiveness. `JinLOA4Animated.x3d`
has structural face joints but no `HAnimDisplacer` nodes. What is the recommended
LOA 4 approach for adding runtime-accessible facial expression in 2026? Are there
reference files in the HAnim examples repository that demonstrate displacer
activation via SAI? This is the next HAnim design task after behavioral clip
selection is working.

### 8.4 Behavioral clip authoring workflow

MCCF intends to add a HAnim editor module to the Character Creator tool.
The minimum capability needed is: author keyframe pose clips per behavioral
state, assign TimeSensor names, export a complete LOA 4 X3D file with the
correct TimeSensor/RotationInterpolator/ROUTE structure matching the
`JinLOA4Animated.x3d` pattern. Is there an existing open-source LOA 4
editor or reference workflow the WG would recommend as a starting point?

**Day 65 relevance:** this question has gained urgency. Salida's behavior-timer
resolution failure (§5) is very likely traceable to `SalidaAnimations_repaired_test.x3d`
not matching the reference structure — a concrete, live example of exactly the
gap this question is asking about. A reliable authoring workflow that guarantees
structural conformance would have prevented this specific defect.

---

## 9. Future: Displacer Facial Animation (Deferred)

HAnim facial animation at LOA 4 uses `HAnimDisplacer` nodes, not joint rotations.
A `HAnimDisplacer` targets a specific `HAnimSegment`'s `Coordinate` node and
applies weighted displacement vectors to simulate skin deformation for expressions
like brow raise, lid closure, and jaw open.

The MCCF E channel will eventually activate facial displacers in addition to
(or instead of) behavioral clip selection. The architecture is the same:
MCCF reads `observed_cv.E` and activates a named displacer or interpolator;
the actual displacement data lives in the HAnim file.

This design task requires:
1. A reference LOA 4 HAnim file with displacer nodes (to be obtained from WG or authored)
2. An HAnim editor module in Character Creator to author displacement shapes
3. A `<FacialExpressions>` element in the cultivar XML (analogous to `<Behaviors>`)
4. SAI write path: `displacerNode.displacements = [...]` or `weight` field write —
   confirm against the Day 25/65 finding before assuming any specific field-write
   pattern works; test empirically before writing it into a spec as settled.

Estimated effort: one weekend for editor module, one session for MCCF integration.
Not on critical path for the opening scene — behavioral clip selection alone is
sufficient.

---

## 10. Implementation Order and Session Estimate

| Task | File | Status (Day 65) | Dependency |
|---|---|---|---|
| 1 | `mccf_cultivar_lambda.py` — `<Behaviors>` parse/serialize | Done | none |
| 2 | `mccf_x3d_loader.html` — timer resolution at placement | Done | none |
| 3 | `mccf_x3d_loader.html` — `selectBehaviorClip()` + `applyBehaviorClip()` | Done | Tasks 1, 2 |
| 4 | `mccf_x3d_loader.html` — load clips at arc/record | Done | Tasks 1, 3 |
| 5 | `mccf_x3d_loader.html` — reset cleanup | Done | Task 3 |
| 6 | Cindy's `<Behaviors>` table | Done, confirmed live | Tasks 1–5 |
| 7 | Second agent's `<Behaviors>` table | Authored; agent's own HAnim asset needs repair (§5) | Task 6 |
| 8 | `_fireBehaviorEventCue()` + `_agentAuthoredClip` override | Designed, not built | Tasks 3, 4 |
| 9 | Events Editor — verify behavior track cue fires override correctly | Blocked on Task 8 | Task 8 |
| 10 | Villain constitutional profiles | Not started | Tasks 6, 7 |
| 11 | Chorus persistence / cross-scene accrual | Not started | Tasks 1–9 |

**Remaining estimated: 2–3 sessions** for Tasks 8–9 (authored override), assuming
the Timeline spec's scheduling layer lands first or alongside. Tasks 10–11 remain
separate design sessions, not blocked by implementation.

---

## 11. Known Non-Issues (carry forward from Day 23 handoff)

- `VP_Overview not found` on load — cosmetic, X_ITE
- `ambient/sync 500` — ModuleNotFoundError: No module named 'mccf_lighting'
- `lighting/scalars 404`
- AudioContext gesture warning from X_ITE
- MS audio 48khz reset
- Jin.png local file path error — cosmetic

These do not affect behavior activation.

---

## 12. Architecture Context — Where This Fits in MCCF

```
Novel / scene intent
      ↓
Scene Composer — place agents, author paths, set waypointOrder
      ↓
Cultivar XML   — weights, regulation, voice, HAnimFigure, Behaviors ← THIS SPEC
      ↓
mccf_api.py    — arc/record seeds ϕ; couplers evolve ϵ; observed_cv = ϕ+ϵ
      ↓
mccf_x3d_loader.html
  ├── Playback sequencer (waypointOrder, dwells, TTS, Chorus)
  │     — WHEN this fires: MCCF_Timeline_Scheduling_Architecture.md (Day 65)
  ├── Hothouse polling loop → material node writes (BodyMat_, GazeMat_, etc.)
  └── Behavior selection loop ← THIS SPEC
            ↓
      selectBehaviorClip(agentSafeName, observed_cv)
            ↓
      applyBehaviorClip → SAI writes → TimeSensor.enabled = true/false
            ↓
JinLOA4Animated.x3d (or per-agent equivalent) — TimeSensors own keyframe data,
drive RotationInterpolators
            ↓
      HAnim joint rotations → visible avatar motion
```

The emotional field drives the selection. The HAnim file owns the motion.
MCCF never writes a joint rotation directly.

---

*End of specification. Prepared Day 23 — 2026-05-22.*
*Updated Day 61 — 2026-06-28: Added §6a Fallback Principle, §6b Authored Override,*
*§6c Persistence/Accrual notes, villain constitutional profiles task, updated implementation table.*
*Updated Day 65 — 2026-07-06: Corrected SAI mechanism from startTime/stopTime to enabled=true/false*
*throughout (§0) — the original text contradicted mccf_behavior_spec.md's Day 25 finding and the*
*actual shipped code. Resolved §8.1. Confirmed Tasks 1–6 working live for Cindy. Isolated Salida's*
*behavior-timer failure to avatar-file content, not this mechanism. Cross-referenced the new*
*MCCF_Timeline_Scheduling_Architecture.md for scheduling concerns, out of scope here.*
