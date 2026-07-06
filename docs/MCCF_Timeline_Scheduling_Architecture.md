# MCCF Timeline & Scheduling Architecture — Design Specification
## From Named Events to a Shared Scene Clock

**Version:** 1.0.0
**Prepared:** Day 65 — 2026-07-06
**Status:** DESIGN — not yet implemented
**Rule:** Author does not edit code. Claude delivers complete files only.
**Reference files:** `mccf_scene_composer.html`, `mccf_x3d_loader.html`, `mccf_events_editor_prototype_2.html`
**Companion specs:** `MCCF_Events_Editor_Architecture.md` (baked vs. runtime vessels — unchanged by this spec), `mccf_behavior_spec.md` and `MCCF_HAnim_Behavior_Activation_Spec.md` (EBPS-driven ambient behavior — unchanged by this spec)

---

## 1. Governing Principle

**This spec answers WHEN something happens. It does not answer WHAT it does, or WHY.**

Three specs now divide MCCF's runtime behavior along a clean seam:

| Question | Owned by | Stays as-is? |
|---|---|---|
| *What does a cue write to, and how?* (baked node vs. computed vessel) | `MCCF_Events_Editor_Architecture.md` | Yes — untouched |
| *Why does an agent's ambient posture/gait change?* (EBPS-driven clip selection) | `mccf_behavior_spec.md`, `MCCF_HAnim_Behavior_Activation_Spec.md` | Yes — untouched |
| *When does a discrete, authored moment fire?* (path segment start, camera cut, one-shot clip, dwell expiry) | **This spec** | New |

Nothing here replaces the vessel system or the field-driven behavior system. This spec exists because a fourth question — scheduling — was never given its own owner, and everything that borrowed pieces of the other three systems to answer it informally turned out to be fragile in the same way, independently, five separate times in one test session.

---

## 2. Problem Statement — What Day 65 Actually Found

Five distinct symptoms this session traced back to the same underlying gap: **there is no single, explicit, authoritative time axis for a scene arc.** Instead, "when" is answered by a scattered mix of trigger-string matching, coarse two-level ordering, and implicit event-chaining. Each mechanism works until it doesn't, and each failure mode was different enough to look like an unrelated bug until they were lined up together:

1. **Trigger-string mismatch.** Composer exported `trigger="WP1 arrive"` on two camera cues. The Loader's `_resolveWpTriggerNames()` only ever produces waypoint-name-based candidates (`"CindyBegin arrive"`, `"Cindy arrive"`) — never positional strings. The cues were dead on export, silently, with no error anywhere.

2. **Timeline flattening.** `_buildSceneData()` concatenated every path's waypoints into one flat sequence with artificial fixed spacing (`t = index * 8`), regardless of whether the underlying paths actually ran in parallel or in sequence. Two agents with `waypointOrder=1` (meaning *simultaneous*, confirmed by the engine's own rules) were shown in the Events Editor timeline as if one strictly preceded the other.

3. **Coarse two-level ordering.** `waypointOrder` only expresses "same number = simultaneous, higher number = wait for lower group to finish." There is no way to express "Salida starts 2 seconds after Cindy," or any relative timing finer than a binary group membership.

4. **Single-path tooling assumptions.** `_buildSceneData()`'s original first-path-only bug, the Paths list having no select/edit/delete UI at all, and Record Scene Arc's single `_sceneArcPath` global all independently assumed exactly one path per scene, because the tooling grew one agent at a time and nothing ever forced a reconciliation across paths.

5. **The dwell-release scoping bug.** `pbUpdateDisplay`'s "no dialogue at this waypoint — release the dwell" branch read a variable (`isX3DDriven`) that was only ever assigned in the sibling branch it was mutually exclusive with — so it was permanently `undefined`, and any waypoint with no authored dialogue stalled the entire arc forever. This one was a plain coding mistake, not an architecture flaw — but it is exactly the kind of mistake an implicit event-chain architecture invites: a single dead link anywhere in the chain silently stops everything downstream, with no visibility into where or why.

None of these are the same bug. All five are downstream of the same missing thing: **an explicit schedule that can be inspected, validated, and executed independently of chained callbacks and string matching.**

---

## 3. Scope

### In scope — discrete, authored moments on a shared clock
- Path segment start and expected arrival time (derived from waypoint distance ÷ pace, already computed correctly today — this spec makes it explicit and inspectable rather than implicit in a TimeSensor's `cycleInterval`)
- Dwell duration at a waypoint
- Camera cues (both baked and runtime — see Events Editor Architecture doc; only *when* changes here, never *what*)
- One-shot behavior clips authored via the Events Editor's behavior track (Jump, Kick — see HAnim spec §6b, "Authored Behavior Override")
- Dialogue line display/highlight timing in the Events Editor (not TTS itself — TTS duration is not knowable in advance and must remain reactive)

### Explicitly out of scope — stays reactive, not scheduled
- **EBPS-driven ambient behavior selection** (`selectBehaviorClip()`, hysteresis, priority resolution — HAnim spec §4). This is deliberately continuous and field-reactive by design (the Fallback Principle, HAnim spec §6a: *"the author scripts the peaks, the field handles the texture"*). Forcing this onto a fixed clock would delete the exact property that makes it valuable.
- **Zone proximity and inter-agent proximity events** (Behavior spec §4.2, §4.3). You cannot schedule the moment an avatar wanders into a zone — it is runtime-detected by definition, and must stay that way.
- **TTS itself.** Actual speech duration depends on the browser's speech engine and cannot be predicted or locked to a clock value. What *can* be scheduled is the dialogue's *intended* start time as an authoring aid (for the Events Editor timeline display) — not its actual real-time completion, which remains reactive exactly as it is today (`pbSpeakQALines`'s `onComplete` callback).

This split matters enough to restate plainly: **this spec only touches things an author explicitly places in time. It never touches anything the field or the runtime decides on its own.**

---

## 4. The Scene Clock

One authoritative time value per arc run: **`t`, seconds elapsed since the arc's Play/Play All was invoked, monotonic, never paused except by an explicit Pause action.**

### 4.1 Where it lives

The Director (per `mccf_behavior_spec.md`'s Composer/Director split) is the authoritative owner. The server already tracks session state per cultivar (`sessions[sid].state`); this spec adds one scene-wide clock value alongside it, not per-cultivar. The Loader reads it; it does not own it, consistent with the existing division of labor (Composer authors, Director owns runtime state, Loader executes SAI writes).

### 4.2 Why server-authoritative, not client-authoritative

Record Scene Arc already writes recorded rows through `/arc/record` to the server. A client-side clock (e.g. `performance.now()`) would drift from whatever the server considers canonical the moment more than one browser tab, or a recorded-vs-live distinction, enters the picture — which it already has (Record Scene Arc vs. live Play All are two different code paths reading the same arc data today). One clock, one owner, avoids a second class of desync bug this spec would otherwise just be inventing.

### 4.3 What it does not replace

The X3D `TimeSensor` nodes that actually drive `PositionInterpolator`s and HAnim joints keep doing exactly what they do today — X3D owns motion, per the HAnim spec's Governing Principle (§1: *"MCCF activates behaviors in the scene graph. It does not write them."*). The scene clock's job is only to tell the Loader **when** to flip `enabled=true` on the timer that was already going to do the work. This is additive scheduling logic sitting in front of the existing, working SAI mechanism — not a replacement for it.

---

## 5. Data Model Additions

### 5.1 Path segments — explicit, not implied

Today, a segment's duration is implied by `Timer_{Agent}_{N}`'s `cycleInterval`, itself computed by Composer from `distance ÷ pace` at export time (confirmed correct by hand this session: Salida's leg computed to 4.01s, Cindy's to 5.38s, both matching their respective `TimeSensor`s exactly). This spec does not change that computation. It makes the *result* explicit and queryable ahead of time, rather than only discoverable by reading a `TimeSensor`'s authored `cycleInterval` after the fact:

```xml
<Path name="path_cindy" agent="Cindy" waypointOrder="1">
  <PathWaypoint ref="WP_CindyBegin" start_t="0.0"   duration="2.0"/>
  <PathWaypoint ref="WP_Cindy"      start_t="2.0"   duration="5.38"/>
</Path>
<Path name="path_salida" agent="Salida" waypointOrder="2">
  <PathWaypoint ref="WP_AnnaBegin"  start_t="7.38"  duration="2.0"/>
  <PathWaypoint ref="WP_Anna"       start_t="9.38"  duration="4.01"/>
</Path>
```

`start_t` for a path's first waypoint is derived from its `waypointOrder` group: order-1 paths start at `t=0`; an order-2 path's start is the maximum completion time (`start_t + duration` across all waypoints) of every order-1 path. This is a direct, mechanical translation of the existing "same number fires simultaneously, higher number waits" rule into real numbers — **`waypointOrder` is not being removed.** It remains the author-facing concept (it's simpler to type `2` than to compute a start time by hand); Composer computes the actual `start_t` values from it at export time, the same way it already computes `duration` from pace and distance today.

### 5.2 Cues — additive, not a replacement for triggers

A cue keeps its existing `trigger` field (event-based, string-matched — unchanged, still resolved via `_resolveWpTriggerNames()`). This spec adds two new optional fields:

```xml
<Cue shot="medium" subject="Cindy" start_t="2.0" duration="4"/>
```

A cue may specify **either** `trigger` (fires when that named event occurs, timing not predetermined) **or** `start_t`/`duration` (fires at an exact scene-clock value, regardless of what triggered it) — **never both.** This mirrors the Events Editor Architecture doc's existing "What Goes in a Cue" rule (§4) almost exactly: *"Ambiguous. Two different routing systems are both indicated. One will silently win."* The same failure mode that motivated that rule for `shot=`/`viewpoint=` applies identically here, so the same discipline applies: one mechanism per cue, enforced at the schema level, not left as an implicit precedence rule for the Loader to guess at.

**Migration note:** every existing cue with only a `trigger` field continues to work completely unchanged. Nothing in this spec requires re-authoring cues that don't need exact-time control. `start_t`/`duration` is for cases where "the moment this specific event happens to fire" isn't precise enough — e.g. a camera cut that must land exactly 2 seconds into a segment regardless of dwell-time variance.

### 5.3 What Composer must compute and emit

This is Composer's responsibility, matching the existing pattern from the Events Editor Architecture doc (§5, "The Composer's Responsibilities" — emit vessels, never let cue data reference implementation details):

1. Compute `start_t` for every `PathWaypoint`, given `waypointOrder` groups and each segment's pace/distance-derived duration.
2. Provide these values to the Events Editor via the same `mccf_scene_data` postMessage bridge already in place (Day 65: this bridge was fixed this session — see below).
3. Never require the author to type a `start_t` by hand for path-derived timing. Only cues authored directly in the Events Editor with explicit clock placement (dragging on the timeline, or a "snap to computed segment start" action — extending the existing "Snap to WP" button already in the UI) produce authored `start_t` values.

---

## 6. Multi-Agent Representation — Swim Lanes

Per the Day 65 discussion: **one row per agent/path, sharing a single horizontal time axis**, rather than the current flat concatenation of every path's waypoints into one sequence.

```
t=0                2.0        7.38       9.38        13.39
Cindy   [ CindyBegin dwell ][====walk====]
Salida                              [ AnnaBegin dwell ][====walk====]
```

This is a direct visual encoding of exactly what `waypointOrder` groups already mean — order-1 lanes start together at `t=0`; an order-2 lane's bar visibly begins only after every order-1 lane's bar ends. No new authoring concept is introduced; this is the existing group-order rule finally rendered honestly instead of flattened into a misleading single sequence. Cues attach to whichever lane's time range they fall within, or float independently above all lanes if they're scene-wide (e.g. a wide establishing shot with no single subject).

Order-groups with more than two levels stack the same way: order-3 waits for the latest-finishing order-2 lane, and so on — this is unchanged from today's engine behavior, just given a visual home.

---

## 7. Loader Responsibilities

The Loader's actual SAI-writing code does not need to change in kind — `_switchBehaviorTimer`, `applyBehaviorClip`, path `TimeSensor.enabled` writes all stay exactly as they are (per §4.3 above). What changes is **what decides when to call them.**

Today: a chain of callbacks. `pbUpdateDisplay` → TTS completion (or the dwell-release fallback, until Day 65's fix) → `pbReleaseDwell` → `arr.startFromLoader` → X3D Arrival script → `Timer_N.enabled=true` → `fraction_changed>=0.99` → next step. Each link depends on the previous one firing correctly; a single broken link (as Day 65 found) stalls everything after it with no visibility into where the chain stopped.

Proposed: a single dispatch loop, driven by the scene clock, checking "what has a `start_t` at or before now that hasn't fired yet" and firing it — independently, per agent, per cue. A broken or missing schedule entry for one agent cannot silently stall another agent's independent entries, because there is no shared callback chain between them to break. This is the concrete, structural reason the Day 65 dwell-release bug class becomes far less likely under this model — not because the code would be bug-free, but because a single dead branch would only affect the one scheduled item it belongs to, not every downstream event chained after it.

**Important boundary:** this dispatch loop schedules *when to flip a switch*. It is never the thing computing HAnim joint motion, camera vessel math, or field values — those stay exactly where the Events Editor Architecture and HAnim specs already put them.

---

## 8. Events Editor Responsibilities

1. Render swim lanes per §6, reading `start_t`/`duration` from `mccf_scene_data` the same way it already reads agents/viewpoints/triggers (Day 65 fix: this bridge was dead all session due to the `_sceneXmlLoaded` gate; now fixed).
2. A cue's inspector gains a mode toggle: **Event-triggered** (existing `trigger` dropdown, unchanged) or **Clock-triggered** (`start_t`/`duration` fields, or drag-on-timeline). Mutually exclusive per §5.2.
3. Never show `start_t` as an editable field for path-segment bars themselves — those are Composer-computed, read-only in the Events Editor, exactly as vessel names are never author-editable per the Events Editor Architecture doc's Vessel Principle (§2). The author edits `waypointOrder` and pace/dwell in Composer; the Events Editor visualizes the result.

---

## 9. What Does Not Change — Restated

To prevent scope creep the first time someone implements this:

- The baked/runtime vessel distinction (Events Editor Architecture doc, §1–§8) — **untouched.**
- EBPS-driven ambient behavior selection, hysteresis, the Fallback Principle (HAnim spec §4, §6a) — **untouched.**
- Zone and inter-agent proximity event detection (Behavior spec §4.2, §4.3) — **untouched, stays runtime-detected.**
- `enabled=true/false` as the SAI mechanism for behavior timers — **untouched, already correct** (see HAnim spec changelog, Day 65).
- Path `TimeSensor`/`PositionInterpolator` mechanics — **untouched.** This spec adds a scheduling layer in front of them; it does not touch how they move an avatar once told to start.

---

## 10. Migration and Implementation Order

| Task | File | Effort | Dependency |
|---|---|---|---|
| 1 | Composer: compute `start_t` per `PathWaypoint` from `waypointOrder` + pace/distance at export | `mccf_scene_composer.html` | 1 session | none |
| 2 | Composer: emit `start_t`/`duration` in `mccf_scene_data` payload | `mccf_scene_composer.html` | 0.5 session | Task 1 |
| 3 | Events Editor: swim-lane rendering per agent/path | `mccf_events_editor_prototype_2.html` | 1–2 sessions | Task 2 |
| 4 | Events Editor: cue inspector mode toggle (event- vs. clock-triggered) | `mccf_events_editor_prototype_2.html` | 0.5 session | none |
| 5 | Loader: scene-clock dispatch loop for clock-triggered cues | `mccf_x3d_loader.html` | 1 session | Task 4 |
| 6 | Loader: path-segment scheduling read from `start_t` (display/validation only — actual segment start still fires via existing dwell-release chain until Task 7) | `mccf_x3d_loader.html` | 0.5 session | Task 1 |
| 7 | Loader: replace dwell-release callback chain with dispatch-loop-driven segment starts | `mccf_x3d_loader.html` | 1–2 sessions | Task 6 |

Tasks 1–4 are additive and low-risk — nothing existing breaks if they land alone (event-triggered cues and the current dwell-release chain keep working exactly as-is). Task 7 is the only task that touches the existing playback mechanism's control flow and should be tested in isolation before being relied on for a real scene.

**Total estimated: 5–8 sessions**, matching the effort scale of the HAnim behavior spec's own estimate for a comparable amount of new surface area.

---

## 11. Known Non-Issues (carry forward)

Same list as the other two specs — none of these are affected by this spec:
- `ambient/sync 500` — `mccf_lighting` module missing, not in scope
- `lighting/scalars 404` — same
- AudioContext gesture warning — browser policy, harmless
- `HAnimHumanoid.segments deprecated` — cosmetic
- Tracking Prevention blocked jsdelivr — cookie policy, harmless

## 12. Still Open, Not Addressed by This Spec

Carried forward from Day 65 testing, unrelated to scheduling:
- `TestSubjectA` phantom cultivar appearing in `pbActivateX3DTimers` cultivar lists — cause unknown, not reproduced in any scene/arc file inspected
- Dialogue content bug ("Named VP" spoken instead of authored text) — needs Characters/dialogue-authoring source or server code to diagnose further
- Salida's behavior timers failing `getImportedNode` resolution — isolated to `SalidaAnimations_repaired_test.x3d` not matching the TimeSensor/EXPORT structure `cindy_hanim.x3d` has; asset repair, not a design or scheduling issue
- Tab-crash reports, suspected related to multiple scene loads — not yet investigated

---

*Day 65. Named events and coarse ordering get you surprisingly far — until two agents need to move at once. Give the scene a clock.*
