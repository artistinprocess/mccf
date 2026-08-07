# MCCF Event Architecture — Scheduled vs. Sensed, and the Route Graph

**Day 81. Status: architecture agreed, mostly unbuilt.**
Origin: a guided test pass on the Day 80 Timeline/Dialogue editor build hit
two real failures (actor selection, type-persistence-on-reload) and froze
mid-test. The freeze itself turned out to be the less important finding —
the test forced a harder question that had been quietly limiting design for
longer than one build cycle: the editor was trying to put two fundamentally
different kinds of thing on one timeline, and that's the actual reason it
feels wrong to use, not just a layout problem.

---

## 1. The core insight

Events split into two kinds MCCF has been treating as one:

- **Scheduled events** — have an authored position in time because a human
  decided where they go: a camera cut, a gesture cue, a dialogue line tied
  to `scene-start`. A timeline is the right representation — it's asserting
  something true.
- **Sensed events** — fire when a condition becomes true during a given
  playthrough, not at an authored moment. Waypoint arrival, zone entry,
  anything condition-triggered. Putting these on a timeline asserts
  something false — a fixed position for something that doesn't have one.

This wasn't a new abstraction invented for this note — it was already
latent in `dialogue-xml.js`'s trigger types (`scene-start`/`touch`/`zone`/
`declared` vs. `sensed`), the schema just wasn't honored by the UI. The
read-only legacy-waypoint panel added Day 80 landed in the right place (off
the timeline, below it) more by luck than by this principle — a decent sign
the instinct was already correct before it was stated.

**Resolved directly:** are waypoint cues and timeline cues the same thing?
No — and this isn't a minor scoping call, it's the load-bearing distinction.
A recorded/authored path has a *known, fixed* duration (you set the timer's
cycle interval) — it can carry a duration bar on a timeline honestly. A
sensed walk's duration isn't decided until the walk happens — no timeline
representation of it can be honest. That's what actually separates the two
systems, not whether the path was hand-placed or captured.

---

## 2. Full trace of what exists today (verified against `mccf_x3d_loader.html`)

Six distinct pieces of machinery were found, in six different states.
Confirmed by reading the actual source, not inferred from behavior:

| # | System | Status |
|---|---|---|
| 1 | Step (`pbStepSession`) | **Confirmed broken**, self-documented in a Day 65 code comment: advances a server-side step counter and fires cues "as if" arrived, but never moves the avatar's Transform (normally driven by TimeSensor+PositionInterpolator, which a discrete step never runs). |
| 2 | `pbJumpToWaypoint` | Not a fix for #1 — an explicit Day 65 workaround, teleports the Transform directly for camera-cue testing only, no walk animation. |
| 3 | Play, single arc (`pbPlay`) | **Architecturally sound.** Code comment: *"auto:false — X3D segmentArrived callback drives step advancement; server auto-timer would race."* Genuinely scene-graph-native, event-driven off the walk's own completion signal. No evidence of the bug Step has. |
| 4 | Play All, multi-agent ordering (`pbPlayAll`/order groups) | Traced in full — group-transition logic (order assignment before activation, per-group state reset, completion detected by checking whether the *next* `Timer_` node genuinely exists in the scene graph) reads as **correct**. No bug found in this specific loop. If "can't play arcs in order" persists, the fault is downstream (`pbActivateX3DTimers`'s internals, untraced) or server-side, not here. |
| 5 | Zone-audio proximity (`spPollAvatarZones`) | Real `setInterval` SAI polling — genuinely the risky pattern, but scoped only to ambient zone audio, gated by `_spPlaybackLive`. Separate from 1–4. |
| 6 | Recorded paths (capture → export) | See §3 — four of five pipeline stages real and correct, final stage (playback consumption) never built. |

Also found along the way: `spPollAvatarZones` and the "does the next Timer
node exist" check in `_pbAdvanceSeg` confirm the same principle from
opposite directions — one is the anti-pattern (external polling racing
scene state), the other is the pattern done right, in the same file.

---

## 3. Recorded-path pipeline — traced end to end

- **Capture** (`mccf_events_editor_prototype_2.html`) — real, and
  self-corrected from an actual bug: first cut read
  `getActiveViewpoint().position/orientation` on a poll, by analogy with
  working precedent elsewhere. Day 78, tested directly rather than trusted:
  a bound Viewpoint's fields hold the *authored* value, not live
  navigation. Fixed by reading a dedicated `MCCF_PathRecorderProx`
  `ProximitySensor`'s `position_changed`/`orientation_changed` instead —
  the correct native mechanism, discovered independently on Day 78 by
  testing the assumption before building on it. Sampling stays a 100ms
  poll, correctly — continuous time-sampling for RDP decimation is a
  different job from discrete arrival detection, and polling is the right
  tool for it.
- **Build/decimate** (`path-recorder.js`) — real, pure, tested. RDP
  decimation against a tunable tolerance, no DOM/X3D dependency.
- **Round-trip through Composer** — real and complete. Validates on
  receipt, serializes `<RecordedPaths><RecordedPath>` on export, re-parses
  on reload.
- **Playback consumption** — **confirmed absent.** Zero references to
  `RecordedPath`/`MCCFPathRecorder` anywhere in the loader. Named in
  `path-recorder.js`'s own header as *"task 5"* and never built. Not a bug
  — a clean, unstarted stage.

**Resolved: a `RecordedPath` has four parts**, agreed directly:
orientation interpolator, position/spline interpolator, a Timer with an
authored cycle interval, and an agent assignment. Deliberately kept as a
*pairing* layered on top of the geometry rather than baked into
`RecordedPath` itself — `path-recorder.js`'s original design intent
(geometry reusable across objects, per its own header) stays intact. Speed
is an authoring-time choice (the timer's interval), not baked into the
capture — the same recorded flourish can be a brisk walk for one agent and
a wary approach for another.

**Trigger, resolved:** a recorded path's timer can be fired by the master
clock (a timeline cue) **or** routed from another event — a music cue
completing, for instance. The second case has no fixed clock position and
is explicitly not a timeline event — see §4.

---

## 4. The route graph

Evidence: a prior prototype screenshot (Events Composer S2) shows this
already partially designed, not just proposed fresh. Confirmed structure
from that screenshot:

- Nodes for both **scheduled sources** (`TimelineTrigger @0:12.4s`) and
  **sensed sources** (`ZoneEnter_Giparu`) sit in the *same* graph, same
  visual language — output ports feeding downstream consumer nodes
  (`CameraRig_Cindy`, `LightRig_Cindy`).
- Typed ports (SFTime, SFBool, SFColor shown), color-coded; only matching
  types connect.
- Fan-out allowed from any output; circular routes detected and blocked
  automatically.
- A 2D top-down map pane and a live X3D editing pane sit alongside the
  graph in the same tool.
- The Timeline panel below still exists, showing duration-bar tracks
  (Camera/Light/Behavior/Dialog/Audio) — the graph doesn't replace the
  timeline for genuinely scheduled content, it's where *triggers*,
  including non-clock ones, get authored and wired.

**Resolved — this is the bigger, correct scope, not a narrower one:** the
graph doesn't just add a UI for music-cue-style triggers alongside the
existing hardcoded order-sequencing (`_pbAgentCurrentOrder`,
`_pbArcComplete`, the hand-written wait-then-advance loop from §2 item 4).
It replaces that JS bookkeeping. "Order 1 complete" becomes a real,
author-visible output port routing into "order 2 start's" input port,
instead of a variable nobody can see without reading the file. The
sequencing logic stops being code that needs tracing (the way §2 item 4
just was, for an hour) and becomes something inspectable and editable
directly.

**Confirmed separate, deliberately: the Network tab (agent-to-agent
couplers) is NOT part of this graph, and won't converge into it.** Reasoning,
stated directly: couplers are a relationship network, part of the EBPS
emotional machinery — not a timed event. Screenshot evidence: the Network
tab already renders its own 2D grid (agents as points inside zones, dashed
strength-labeled links, the seven coupler checkboxes) — a different visual
logic (zone position matters; clock position doesn't) that has no reason to
share a canvas with the route graph.

**Named as a future bridge, explicitly not crossed yet:** once EBPS is
implemented per its own design doc (sequenced *after* this cueing cleanup
and the lighting subsystem), EBPS may become an explicit interface *within*
the route graph — a node type with typed ports the graph can read from and
write to — not a merge of the two authoring surfaces. The distinction
matters: the graph would gain an EBPS node type, not absorb Network's
authoring UI.

---

## 5. Open questions — genuinely unresolved, not decided by omission

- **Is a `TimelineTrigger` node's clock value graph-editable, or does the
  Timeline panel own it and the graph node just display it live?** Both
  panels are visible simultaneously in the prototype screenshot. If both
  can independently set the value, that's the exact "two places can
  disagree about the same fact" problem this whole redesign exists to
  avoid — worth pinning down before this gets built, not after.
- **The 2D map's dotted circles around agents** — editable proximity-sensor
  radii, or a read-only visualization of zones authored elsewhere? Not yet
  confirmed either way.
- **Overlap validation, resolved in principle, not in mechanism.** Agreed:
  timeline cues are absolute-clock, shown as filled duration bars so the
  author never has to guess whether two same-type events collide (a dialog
  can run while walking; walking can't run while running). Not yet
  specified: does Composer *refuse* to export overlapping same-type cues
  (hard validation, matching the existing `waypointOrder` hard-stop
  pattern), or is this advisory-only in the UI?

**Resolved since first written — by building, not by discussion:** the
field-exposure question (curated per-type manifest vs. free introspection)
is answered in `mccf_route_graph_prototype.html` — full per-type field
manifests, every exposedField a port, no curation, matching the reference
screenshot directly. Worth being honest that this was decided as a side
effect of building a prototype, not as a deliberate call made first — right
outcome, but noted here so it doesn't read as more considered than it was.

---

## 6. Explicitly deferred

- **Followers** — multiple agents on the same path at the same time,
  currently would land on top of each other; staggered timers work as a
  manual workaround. A non-parented camera-style following assignment was
  named as the likely eventual mechanism, deferred until there's a concrete
  need, not designed further now.
- **Full SAI field introspection** (if the field-exposure question above
  resolves toward "curated") — same treatment, named, not built.
- **The EBPS-as-graph-node bridge** (§4) — sequenced after EBPS itself is
  implemented, not before.

---

## 7. Two prototypes exist now — checked against §4's claims, real gaps found

`mccf_events_editor_prototype_3.html` (scheduled/timeline cues) and
`mccf_route_graph_prototype.html` (sensed/route graph) were built Day 81.
Checking them against this note's own §4 surfaced gaps worth recording
rather than letting the prototypes quietly stand in for the design:

- **`TimelineTrigger` was never built as a node type.** §4's own evidence
  from the S2 screenshot names both `TimelineTrigger @0:12.4s` (scheduled)
  and `ZoneEnter_Giparu` (sensed) as node types sitting in the same graph.
  The route graph prototype has `ProximitySensor` for the sensed half but
  nothing that turns an authored clock moment into a graph output port.
  Roughly half of what the note says this tool needs to represent is
  missing from it.
- **Not one integrated tool yet.** §4 describes a 2D map pane, a live X3D
  pane, the route graph, and a timeline strip together in one tool. What
  exists is two separate files with no bridge between them — the timeline
  prototype has no graph, the route graph prototype has no 2D map, no X3D
  view, and no timeline strip underneath it.
- **The order-group replacement claim is asserted, not demonstrated.**
  §4's central justification for building this graph at all: *"'Order 1
  complete' becomes a real, author-visible output port routing into
  'order 2 start's' input port."* No such example was built — nothing in
  the route graph prototype shows one path segment's completion feeding
  the next one's start. `RecordedPath.isActive` going false is close but
  wasn't wired to demonstrate it. Worth building explicitly before
  treating this justification as proven rather than plausible.
- **The route graph prototype has no save/export at all.** The timeline
  prototype at least attempts one (`mccf_production_cues`, no receiver
  yet — see its own file comments). The graph vanishes on refresh with
  nothing built toward persisting it.

None of this contradicts §1–§6 — the architecture itself held up. These are
gaps between the design and what got built toward it, worth closing before
either prototype is mistaken for more finished than it is.

---

## 8. What this unblocks, and what it doesn't yet

This note does not change any existing code, and neither do the two Day 81
prototypes built toward it (§7) — both are new, standalone files.
`mccf_x3d_loader.html`, `mccf_scene_composer.html`, and `path-recorder.js`
are exactly as verified in §2–§3 — Step is still broken, recorded-path
playback consumption still doesn't exist, `pbActivateX3DTimers`'s internals
are still untraced. What this note changes is the target: the next build
pass isn't "fix Step" or "finish task 5" against the existing timeline-
shaped model — it's building the route graph as the replacement mechanism,
which may make some of §2's six systems unnecessary rather than repaired.
Worth revisiting the "keep vs. simplify" question per-system once the
graph's remaining gaps (§7) are closed, not just the field-exposure model
that's already settled.
