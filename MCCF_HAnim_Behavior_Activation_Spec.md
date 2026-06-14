# MCCF HAnim Behavior Activation — Design Specification
## From Field Values to Scene Graph Motion

**Version:** 1.0.0  
**Prepared:** Day 23 — 2026-05-22  
**Status:** DESIGN COMPLETE — ready for implementation and W3C HAnim WG review  
**Reference files:** `mccf_x3d_loader.html`, `mccf_cultivar_lambda.py`, `mccf_hotHouse.py`  
**Avatar reference:** `JinLOA4Animated.x3d` (W3C HAnim examples repository)

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
Clip change            — stop all clips, start selected clip (mutual exclusion)
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

Evaluated on every hothouse poll tick (HOTHOUSE_MS interval, default 500ms) per agent.
Only fires SAI writes when the selected clip changes — not on every tick.

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
WalkTimer_Anna         // Anna's walk timer (same mesh, independent instance)
DefaultTimer_Cindy
DefaultTimer_Anna
```

**Implementation note for scene authoring:**
When an avatar is placed in the Scene Composer, the loader already renames
`Timer_1` → `Timer_1_{AgentSafeName}` and `Arrival_` nodes correspondingly.
The behavior clip TimeSensors (`DefaultTimer`, `WalkTimer`, etc.) must receive
the same suffixing treatment at placement time. This is a one-line addition to
the avatar placement code in `mccf_x3d_loader.html`.

---

## 6. Implementation Tasks

These are ordered by dependency. Each task is a discrete, testable unit.

---

### Task 1 — `mccf_cultivar_lambda.py`: `<Behaviors>` parse and serialize

**File:** `mccf_cultivar_lambda.py`  
**Effort:** Small — one session

**Add to `CultivarDefinition` dataclass:**
```python
# Behavior clip table — optional, loaded from <Behaviors> element
# List of dicts: {name, timerDEF, loop, priority, E_min, E_max, B_min, B_max,
#                 P_min, P_max, S_min, S_max}
behavior_clips: list = field(default_factory=list)
behavior_default: str = "Default"
```

**Add to `_from_element()`:**
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

**Add to `to_xml()`** (after `<HAnimFigure>` block):
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

**Add to `to_dict()`:**
```python
"behavior_clips":   self.behavior_clips,
"behavior_default": self.behavior_default,
```

**Add to `from_dict()`:**
```python
behavior_clips=data.get("behavior_clips", []),
behavior_default=data.get("behavior_default", "Default"),
```

---

### Task 2 — `mccf_x3d_loader.html`: TimeSensor suffix at avatar placement

**File:** `mccf_x3d_loader.html`  
**Effort:** Small — add to existing avatar placement code  
**Search target:** The section that renames `Timer_1` and `Arrival_` nodes
at placement (currently in `pbActivateX3DTimers` or avatar load callback).

When a LOA 4 HAnim avatar is placed, find all TimeSensor nodes whose DEF names
match the known behavior clip names and rename them with the agent suffix:

```javascript
const BEHAVIOR_TIMER_BASES = [
    'DefaultTimer','PitchTimer','YawTimer','RollTimer',
    'WalkTimer','RunTimer','JumpTimer','KickTimer'
];

function suffixBehaviorTimers(scene, agentSafeName) {
    BEHAVIOR_TIMER_BASES.forEach(function(base) {
        const node = scene.getNamedNode(base);
        if (node) {
            // X_ITE SAI: rename by setting DEF — confirm API before implementing
            // Fallback: maintain a JS map {baseName: instanceNode} per agent
            _behaviorTimerMap[agentSafeName] = _behaviorTimerMap[agentSafeName] || {};
            _behaviorTimerMap[agentSafeName][base] = node;
        }
    });
}
```

**Implementation note:** X_ITE's SAI may not expose a DEF rename API. The fallback
is to maintain a JS-side map `_behaviorTimerMap[agentSafeName][baseDEF] → node`
that resolves the correct instance without requiring a scene-graph rename. This is
the safer approach and should be implemented first. Confirm with X_ITE SAI docs
whether `node.DEF = newName` is supported.

---

### Task 3 — `mccf_x3d_loader.html`: `selectBehaviorClip()` and `applyBehaviorClip()`

**File:** `mccf_x3d_loader.html`  
**Effort:** Medium — one session  
**Location:** Add after `applyHotHouseData()`, call from `applyHotHouseData()`

**State variables to add (top of script):**
```javascript
let _agentCurrentClip    = {};   // {agentSafeName: clipName}
let _agentLastLoopClip   = {};   // {agentSafeName: clipName} — for oneshot return
let _agentClipHysteresis = {};   // {agentSafeName: {ch: lastBoundaryValue}}
let _behaviorTimerMap    = {};   // {agentSafeName: {timerDEF: node}}
let _agentBehaviorClips  = {};   // {agentSafeName: {clips:[], default:str}}
                                 // populated at arc/record time from cultivar API
```

**Core selection function:**
```javascript
function selectBehaviorClip(agentSafeName, cv) {
    const config = _agentBehaviorClips[agentSafeName];
    if (!config || !config.clips || !config.clips.length) return;

    const clips   = config.clips;
    const defName = config.default || 'Default';
    const HYST    = 0.03;

    function conditionMet(clip) {
        for (const ch of ['E','B','P','S']) {
            const val = cv[ch] || 0;
            const minKey = ch+'_min', maxKey = ch+'_max';
            if (clip[minKey] !== undefined && val < clip[minKey] - HYST) return false;
            if (clip[maxKey] !== undefined && val > clip[maxKey] + HYST) return false;
        }
        return true;
    }

    const oneshots = clips.filter(c => !c.loop  && conditionMet(c));
    const loopers  = clips.filter(c =>  c.loop  && conditionMet(c))
                          .sort((a,b) => (b.priority||0) - (a.priority||0));

    let selected;
    if (oneshots.length) {
        selected = oneshots.sort((a,b) => (b.priority||0) - (a.priority||0))[0];
    } else if (loopers.length) {
        selected = loopers[0];
    } else {
        selected = clips.find(c => c.name === defName) || clips[0];
    }

    if (!selected) return;

    const current = _agentCurrentClip[agentSafeName];
    if (current === selected.name) return;  // no change — skip SAI write

    applyBehaviorClip(agentSafeName, selected, current);
}
```

**Clip activation function:**
```javascript
function applyBehaviorClip(agentSafeName, clip, previousClipName) {
    const timerMap = _behaviorTimerMap[agentSafeName];
    if (!timerMap) return;

    const scene = canvas.browser.currentScene;
    const now   = _x3dNow(agentSafeName) || (performance.now() / 1000);

    // Stop all other clips
    Object.entries(timerMap).forEach(function([base, node]) {
        if (node && base !== clip.timerDEF) {
            try { node.stopTime = now + 0.01; } catch(e) {}
        }
    });

    // Start selected clip
    const targetNode = timerMap[clip.timerDEF];
    if (!targetNode) {
        console.warn('applyBehaviorClip: timer not found:', clip.timerDEF, agentSafeName);
        return;
    }

    try {
        targetNode.loop      = clip.loop;
        targetNode.startTime = now + 0.05;   // 50ms ahead — X_ITE timing safety margin
    } catch(e) {
        console.warn('applyBehaviorClip: SAI write failed:', e);
        return;
    }

    // State tracking
    if (clip.loop) {
        _agentLastLoopClip[agentSafeName] = clip.name;
    } else {
        // Oneshot: schedule return to last loop clip after cycleInterval
        // cycleInterval must be read from node or stored in clip definition
        const duration = (targetNode.cycleInterval || 5.5) * 1000;
        setTimeout(function() {
            const returnTo = _agentLastLoopClip[agentSafeName];
            if (returnTo && _agentCurrentClip[agentSafeName] === clip.name) {
                const config = _agentBehaviorClips[agentSafeName];
                const returnClip = (config.clips || []).find(c => c.name === returnTo);
                if (returnClip) applyBehaviorClip(agentSafeName, returnClip, clip.name);
            }
        }, duration + 100);
    }

    _agentCurrentClip[agentSafeName] = clip.name;
    console.log('behavior:', agentSafeName, previousClipName, '→', clip.name);
}
```

**Integration into `applyHotHouseData()`:**

After the existing material node writes (BodyMat_, GazeMat_, etc.), add:

```javascript
// Behavior clip selection from observed_cv
// observed_cv is available from _lastFieldData; hotHouse data provides the
// same channel values through morphWeight_emotion / animationSpeed etc.
const fieldAgents = (window._lastFieldData || {}).agents || {};
const agentFieldData = fieldAgents[agentName];
if (agentFieldData && agentFieldData.observed_cv) {
    selectBehaviorClip(suffix, agentFieldData.observed_cv);
}
// Fallback: construct cv from hotHouse channels if observed_cv not available
else {
    const cv = {
        E: d.morphWeight_emotion || 0.25,
        B: d.animationSpeed      || 0.25,
        P: d.gazeDirectness      || 0.25,
        S: d.socialProximity     || 0.25
    };
    selectBehaviorClip(suffix, cv);
}
```

---

### Task 4 — Load behavior clips at arc/record time

**File:** `mccf_x3d_loader.html`  
**Effort:** Small — add to `_seedArcRecord()`  
**Purpose:** Populate `_agentBehaviorClips[safeName]` before playback begins

When `_seedArcRecord()` calls `GET /cultivars/{name}` to get the cultivar definition,
the response now includes `behavior_clips` and `behavior_default` (Task 1). Store them:

```javascript
// Inside _seedArcRecord() after cultivar fetch:
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
// Start DefaultTimer immediately so avatar is animated before first waypoint
const timerMap = _behaviorTimerMap[agentSafeName] || {};
const defNode  = timerMap['DefaultTimer'];
if (defNode) {
    defNode.loop      = true;
    defNode.startTime = _x3dNow(agentSafeName) || (performance.now() / 1000);
    _agentCurrentClip[agentSafeName]  = 'Default';
    _agentLastLoopClip[agentSafeName] = 'Default';
}
```

---

### Task 5 — Reset cleanup

**File:** `mccf_x3d_loader.html`  
**Effort:** Trivial — add to `pbReset()`

```javascript
// In pbReset(), after _pbCbGeneration++:
_agentCurrentClip    = {};
_agentLastLoopClip   = {};
_agentClipHysteresis = {};
// Do NOT clear _behaviorTimerMap or _agentBehaviorClips —
// those are populated at placement/arc-record and survive reset.
```

---

### Task 6 — Author Cindy's `<Behaviors>` table

**File:** `Cindy.xml` (cultivar XML in cultivars/ directory)  
**Effort:** Authoring — no code  
**Purpose:** First live test of the behavior system

Cindy's character: moderate-E, active, socially engaged. She moves. She should
walk when behaviorally activated, stand attentively when calm, shift casually when idle.

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

### Task 7 — Author Anna's `<Behaviors>` table

**File:** `Anna.xml` (new cultivar XML, created when Anna is authored in Scene Composer)  
**Effort:** Authoring — no code  
**Character:** The Librarian. Delivers the opening monologue. Stationary. Postural.
High-P. Low-B threshold for movement. She should almost never walk; when she does
it is deliberate. Her behavioral range is attentive stance to formal address.

```xml
<Behaviors default="Default">
  <Clip name="Default"   timerDEF="DefaultTimer" B_max="0.50"                  loop="true"  priority="0"/>
  <Clip name="Address"   timerDEF="PitchTimer"   B_min="0.40" B_max="0.80"
                                                  P_min="0.60"                  loop="true"  priority="1"/>
  <Clip name="Walk"      timerDEF="WalkTimer"     B_min="0.80"                 loop="true"  priority="2"/>
</Behaviors>
```

Design note: Anna's `B_max="0.50"` for Default means she stays in idle stance
for the bottom half of the B range. Her `Walk` threshold is 0.80 — very high.
During monologue delivery the field will push her P up and keep B moderate,
landing her in `Address` (PitchTimer — forward lean, attentive posture).
She walks to her final waypoint under path control; behavioral B-driven walking
is suppressed until her field shifts dramatically.

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

The following questions are appropriate for review by the HAnim Working Group
(Don Brutzman, NPS, W3C HAnim):

### 8.1 TimeSensor mutual exclusion via SAI

The MCCF approach stops all TimeSensors then starts the selected one. Is there
a preferred HAnim pattern for runtime clip switching via SAI that avoids the
brief frame gap between stop and start? Specifically: does `stopTime = now+0.01`
followed by `startTime = now+0.05` guarantee a clean transition in compliant
X3D browsers, or is there a blending mechanism available at LOA 4?

### 8.2 DEF renaming via SAI

For multi-instance scenes (two agents sharing the same HAnim file), MCCF needs
to address each agent's TimeSensor instances independently. The current design
uses a JS-side map rather than SAI DEF renaming. Is there a supported SAI
mechanism for addressing nodes by instance in X3D 4.0? Relevant to X_ITE
(Holger Seelig, Savage Studio) as well.

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
4. SAI write path: `displacerNode.displacements = [...]` or `weight` field write

Estimated effort: one weekend for editor module, one session for MCCF integration.
Not on critical path for Anna's monologue — behavioral clip selection alone is
sufficient for the opening scene.

---

## 10. Implementation Order and Session Estimate

| Task | File | Estimated effort | Dependency |
|---|---|---|---|
| 1 | `mccf_cultivar_lambda.py` — `<Behaviors>` parse/serialize | 1 session | none |
| 2 | `mccf_x3d_loader.html` — timer suffix at placement | 0.5 session | none |
| 3 | `mccf_x3d_loader.html` — `selectBehaviorClip()` + `applyBehaviorClip()` | 1 session | Tasks 1, 2 |
| 4 | `mccf_x3d_loader.html` — load clips at arc/record | 0.5 session | Tasks 1, 3 |
| 5 | `mccf_x3d_loader.html` — reset cleanup | trivial | Task 3 |
| 6 | Author Cindy's `<Behaviors>` table | authoring only | Tasks 1–5 |
| 7 | Author Anna's `<Behaviors>` table | authoring only | Task 6 (verify against Cindy) |

**Total estimated: 3 sessions** to full behavior activation on both Cindy and Anna.

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
  ├── Hothouse polling loop → material node writes (BodyMat_, GazeMat_, etc.)
  └── Behavior selection loop ← NEW (this spec)
            ↓
      selectBehaviorClip(agentSafeName, observed_cv)
            ↓
      applyBehaviorClip → SAI writes → TimeSensor.startTime / stopTime
            ↓
JinLOA4Animated.x3d — TimeSensors own keyframe data, drive RotationInterpolators
            ↓
      HAnim joint rotations → visible avatar motion
```

The emotional field drives the selection. The HAnim file owns the motion.
MCCF never writes a joint rotation directly.

---

*End of specification. Prepared Day 23 — 2026-05-22.*  
*For session continuity, paste alongside the Day 23 handoff at the start of the implementation session.*
