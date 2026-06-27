# MCCF Camera System Specification
## Version 1.0 — Day 58

---

## 1. Design Principles

- **Inline per-cue** — camera shot parameters live inside the cue that fires them. No separate camera library or named camera objects.
- **Runtime computed** — shot positions are calculated at playback time from the subject agent's current world position. Never baked into X3D at export time.
- **Agent-attached exception** — shots parented to an agent Transform (`agent_eye`, `agent_side`) resolve by binding the named Viewpoint inside that agent's X3D Transform node, not by computing a free camera position. Same cue format, different resolution path in the Loader.
- **All transitions are explicit** — cut (TELEPORT) or fly (free camera interpolation). No X_ITE black-box transitions.
- **Terrain agnostic** — camera Y is always relative to subject Y + height offset. Terrain following is a NavigationInfo WALK concern, not a camera concern.

---

## 2. Shot Type Taxonomy

### Static Shots
| Shot Type | Description | Default Distance | Default Height | Default H.Angle | Default V.Angle | Default Roll |
|---|---|---|---|---|---|---|
| `wide` | Full environment, subject small in frame | 12m | 3.0m | 0° | -15° | 0° |
| `medium` | Waist-up, background visible | 5m | 1.7m | 0° | -8° | 0° |
| `closeup` | Face/detail, background soft | 1.5m | 1.7m | 0° | -5° | 0° |
| `extreme_closeup` | Single feature, maximum tension | 0.4m | 1.7m | 0° | 0° | 0° |
| `overhead` | Straight down, strategic/abstract | 0m | 10m | 0° | -90° | 0° |
| `worms_eye` | Ground level looking up, scale/awe | 1.5m | 0.1m | 0° | +35° | 0° |
| `dutch` | Eye level, roll applied, unease/tension | 3m | 1.7m | 0° | -8° | ±25° |

### Relational Shots (require subject agent)
| Shot Type | Description | Default Distance | Default Height | Default H.Angle | Notes |
|---|---|---|---|---|---|
| `over_shoulder` | Behind and offset, subject's POV implied | 0.8m | 1.6m | -20° | Camera behind subject, looking past ear toward scene |
| `profile` | 90° side view | 3m | 1.7m | 90° | Flatters movement, reveals silhouette |
| `two_shot` | Frames two agents together | computed | 1.7m | computed | Midpoint between subject and secondary agent |
| `agent_eye` | Subject's own POV | 0m | 0m | 0° | Binds `VP_{agent}_Eye` inside agent Transform |
| `agent_side` | Fixed side cam on agent | 0m | 0m | 0° | Binds `VP_{agent}_Side` inside agent Transform |

### Camera Moves (free camera, interpolated)
| Shot Type | Description | Key Parameters |
|---|---|---|
| `dolly_in` | Push toward subject | start distance, end distance, duration |
| `dolly_out` | Pull back from subject | start distance, end distance, duration |
| `pan` | Rotate horizontally in place | start h.angle, end h.angle, duration |
| `tilt` | Rotate vertically in place | start v.angle, end v.angle, duration |
| `orbit` | Circular path around subject | radius, start angle, end angle, duration |
| `crane_up` | Arc upward and back | start height, end height, arc depth, duration |
| `track` | Lateral move parallel to subject | start offset, end offset, duration |

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
```

### Agent-attached shots
```xml
  shot="agent_eye"
  subject="Cindy"
  <!-- distance/height/angle fields ignored — VP inside Transform is used -->
```

---

## 4. Runtime Resolution (Loader)

### Step 1 — Identify shot category
- If `shot` is `agent_eye` or `agent_side` → **agent-attached path**
- If `shot` is a move type (`dolly_in`, `orbit`, etc.) → **interpolated path**
- Otherwise → **static computed path**

### Step 2a — Agent-attached path
```
vpName = "VP_" + subject + "_Eye"  (or "_Side")
vpNode = scene.getNamedNode(vpName)
vpNode.set_bind = true
```

### Step 2b — Static computed path
```
subjectPos = getAgentWorldPosition(subject)
camPos = computeStaticPosition(subjectPos, distance, height, hAngle)
lookAt  = computeLookAt(camPos, subjectPos, vAngle)
orient  = lookAtToOrientation(lookAt)

if roll != 0:
  orient = applyRoll(orient, roll)

VP_Free.position    = camPos
VP_Free.orientation = orient

if transition == "cut":
  VP_Free.set_bind = true   // NavigationInfo TELEPORT handles instant cut

if transition == "fly":
  startPos = currentCameraPosition()
  startOri = currentCameraOrientation()
  beginFlyInterpolation(startPos, startOri, camPos, orient, flyDuration)
```

### Step 2c — Interpolated move path
```
// Same as static but fires two keyframes through TimeSensor
// Start = current camera or computed start position
// End   = computed end position from distanceEnd/hAngleEnd etc.
// TimeSensor.cycleInterval = flyDuration
```

### Step 3 — Cancel pending moves on Stop/Reset
```
clearAllCameraTimers()
stopTimeSensor()
VP_Free.set_bind = false
bindDefaultViewpoint()
```

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
}

function computeOrbitKeyframes(subjectPos, radius, startDeg, endDeg, steps) {
  // Returns array of positions along arc for PositionInterpolator keys
}
```

---

## 6. VP_Free Node (X3D)

A single free-floating Viewpoint at scene root, emitted by Composer X3D export:

```xml
<Viewpoint DEF="VP_Free"
  description="Free Camera"
  position="0 5 10"
  orientation="1 0 0 -0.4"
  jump="true"/>
```

The Loader holds a reference to this node and drives it directly via SAI for all static computed and interpolated shots. It is never bound by the author — only by the camera cue system.

---

## 7. Events Editor — Inspector Fields by Shot Type

| Field | Static shots | Relational | Move shots | Agent-attached |
|---|---|---|---|---|
| Shot type | ✓ | ✓ | ✓ | ✓ |
| Subject | ✓ | ✓ | ✓ | ✓ |
| Subject 2 | — | two_shot only | — | — |
| Transition / fly duration | ✓ | ✓ | always fly | — |
| Distance | ✓ | ✓ | start only | — |
| Distance End | — | — | ✓ | — |
| Height | ✓ | ✓ | ✓ | — |
| Height End | — | — | ✓ | — |
| H. Angle | ✓ | ✓ | start only | — |
| H. Angle End | — | — | ✓ | — |
| V. Angle | ✓ | ✓ | ✓ | — |
| Roll | dutch only | — | — | — |
| Delay | ✓ | ✓ | ✓ | ✓ |

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
| Rack focus simulation | CSS blur on X_ITE iframe overlay — deferred |
| True lens FOV zoom | `fieldOfView` SAI write reliability TBD in X_ITE |
| Crossfade dissolve | Fade-to-black + cut + fade-in via HTML overlay — deferred |
| Terrain-aware height | `getHeightAt(x,z)` heightmap lookup — Saturn III |
| Camera preview in X_ITE | Bind VP_Free in Loader preview mode on inspector change — future |
| Drag-to-position on stage canvas | Click/drag cone apex to set hAngle — future |

---

Camera Cue Quick Tutorial
The basic idea: You're placing moments in time where the camera cuts or moves to a specific shot. Each cue says when it fires (trigger), what shot it takes, and who it's looking at.
Step 1 — Add a camera cue

Click + Add cue in the toolbar. A new cue appears on the Camera track at the current playhead position. The inspector on the right shows its properties.
Step 2 — Set the trigger

The Trigger dropdown at the top of the inspector is the most important field. w2 arrive means the shot fires when the navigator arrives at Waypoint 2. This is how camera cuts sync to story beats — no manual timing needed.
Step 3 — Pick a shot type

The Shot Type dropdown is grouped:

Static — Wide, Medium, Close-Up, etc. Camera floats at a computed position relative to the subject.
Relational — Over Shoulder, Profile, Two Shot. Camera positions itself relative to how the subject is facing.
Agent POV — Eye and Side use the Viewpoints already built into the agent's Transform in X3D. These are the most reliable shots for live playback.
Camera Moves — Dolly, Pan, Orbit etc. These will drive the free camera interpolator when the Loader implementation is complete.

Changing the shot type auto-fills the framing sliders with sensible defaults.
Step 4 — Pick a subject

Select which agent the shot is about. The stage canvas on the left updates to show a blue cone (cut) or amber cone (fly) from the computed camera position toward that agent.
Step 5 — Transition

cut = instant teleport (what we fixed today with TELEPORT). fly = smooth interpolated move (Loader implementation coming). The fly duration slider appears when fly is selected.
Step 6 — Framing sliders

Distance — how far the camera is from the subject
Height — camera Y above ground (1.7m = eye level)
H. Angle — horizontal angle around the subject (0° = in front, 90° = left side, -90° = right side)
V. Angle — tilt (negative = looking down slightly, which is normal for most shots)
Roll — only appears for Dutch Angle shots

Step 7 — Delay

Under Timing, delay fires the cue N seconds after the trigger. So w2 arrive + delay 2.0s = shot fires 2 seconds after arriving at WP2.
Step 8 — Export

Export cues ↗ sends everything to the Composer which saves it to the scene XML. The Loader picks it up on next play.

*Day 58. Inline per-cue. Runtime computed. Free camera for moves. Agent-attached for POV shots.*
