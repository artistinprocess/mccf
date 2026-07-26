# MCCF Scene Placement Module Consolidation — v0.1

*Day 76. Companion to `MCCF_Camera_System_Spec_v1_3.md` and
`MCCF_Avatar_Camera_Rig_Manifest_Spec_v0.1.md`. Covers two decisions from
the same discussion: (1) whether/how to recover the old events editor's
live camera-position preview, and (2) the broader decision to stop
treating cameras/lights/FX/assets as separate placement tools and build
one scene-placement module instead.*

---

## 1. Live camera preview — root cause confirmed, fix is known

**The problem, as reported:** the old events editor's slider-driven
live-camera preview never reliably updated the X_ITE viewport, and there
were unresolved concerns about the X_ITE instance surviving tab close
without crashing the browser.

**Root cause, confirmed by reading the actual code (not inferred):**
`mccf_events_editor_prototype_2.html`'s preview write path is
```js
camXform.getField('translation').setValue(new X3D.SFVec3f(...));
camXform.getField('rotation').setValue(new X3D.SFRotation(...));
```
This is exactly the SAI pattern Camera System Spec v1.3 §4 documents as
**confirmed unreliable** during the Day 62 `agent_orbit` debugging work:
*"`getField().setValue()` was the path that initially failed to register
changes reliably for these particular fields in this codebase's usage
pattern — direct assignment is now the standardized convention."* The
Loader's own working camera code (static shots, `agent_orbit`) was
already fixed to use direct property assignment (`node.translation = …`)
and `addFieldCallback` (not the nonexistent `addFieldInterest`). The old
events editor's preview predates that fix and was never updated to match
it. **This is not an X_ITE limitation — it's a known, already-solved bug
pattern that never got backported into the preview code.**

**Crash risk — partially mitigated already, not fully.** A same-src guard
exists in `loadX3DViewport()`, added specifically because repeated
Events-tab visits were stacking unreleased WebGL contexts until the tab
crashed (confirmed in the code's own comment). But that guard only blocks
*redundant reloads of the identical URL* — it does nothing for genuine
teardown when the tab closes or a different scene loads. The concern
about tab-close needing explicit cleanup is real and only half-addressed
today.

### Decision

Recover the preview, don't rebuild it from scratch:
1. **Salvage the position-computation math as-is** — `_prevComputeCamPos`,
   `_prevLookAtOrientation`, and the per-shot-type field visibility logic
   are correct; the bug was never in the math.
2. **Rewrite only the SAI write path**, using the Loader's already-proven
   pattern: direct property assignment, `addFieldCallback` with
   mandatory try/catch around the callback body (per Camera Spec §4's
   safety note — an uncaught exception here can freeze unrelated scene
   state), and the `currentTime` fallback for `startTime`.
3. **Add explicit teardown, not just a same-src guard.** When the new
   Place module's camera/light/FX panel loses focus or closes, actively
   destroy the X_ITE instance (clear/remove the `<x3d-canvas>` element)
   rather than leaving it hidden for reuse. "Destroy on close, create on
   open" replaces "hide and hope," which is what caused the original
   crash.

This is scoped, known work — not an open research question.

---

## 2. Consolidate placement into one module

**Decision:** grid placement of cameras, effects, lights, and other
scene assets should not be separate tools/tabs. If the author is
building the scene, they should build it in one place — one module, one
mental model, not a different tool per thing being placed.

This extends, rather than replaces, work already done: Zones/Waypoints/
Paths/Cameras were already consolidated from four separate top-level tabs
into one Place tab with sub-navigation (confirmed in composer's own
`setMode()` comment: *"used to be four separate major tabs (four copies
of essentially the same grid-placement UI)"*). This decision generalizes
that same move to whatever comes next — Lights, FX/particle systems, and
generic scene assets/props all join the same Place module as additional
sub-tabs, sharing:

- the same grid/canvas, click-to-place interaction
- the same select/move/query toolbar already in use
- the same position/facing inspector pattern already proven for free
  cameras (image 5) — extended with type-appropriate fields per
  placeable kind (a light gets color/intensity/cone-angle instead of
  yaw/pitch, etc., but the placement mechanics are identical)
- the live-preview fix from §1, generalized: any placeable type with a
  meaningful "what does this look like right now" concern (camera
  framing, light falloff) gets the same direct-SAI-write preview pattern,
  not a bespoke one per type

**What doesn't move here, and stays separate on purpose:** Character
Creator (a standalone module already, confirmed by the author, iframed
into a tab for convenience only) and Events/Dialogue authoring (which
consumes what's been placed, per the Actor-discovery pipeline already
settled — placement has to happen before trigger authoring is
meaningful, not the same step).

## 3. Current Place tab architecture, confirmed by the author (Day 76)

Four sub-modules today — Zones, Waypoints, Paths, Cameras (free cameras
only) — each swaps out the editing context via the same top button row,
sharing one grid/canvas. Two things confirmed worth carrying forward and
one confirmed worth fixing:

- **Zones is the richest of the four today** — X3D asset inlining into a
  zone, zone sound, zone commands (Ollama-triggered rules), and a **zone
  cultivar** concept: a reusable zone *type*, definable once and reused
  across multiple scenes, distinct from a one-off zone instance. This is
  the same naming/pattern already established for characters (a
  Character Cultivar vs. a placed avatar instance) — worth keeping as
  precedent when Lights/FX join the module later: a "light cultivar"
  (reusable named preset) vs. a one-off placed light is the same shape,
  not a new idea to invent.
- **Free Camera's current scope is correct, not deficient.** It doesn't
  support agent-attached shot types (`agent_eye`/`agent_orbit`/etc.) —
  and per the Avatar Camera Rig decision, it shouldn't: those now belong
  to Character Creator's per-avatar authored rig, not the Place module's
  free/world-space camera class. Free Camera's job is exactly Camera
  Spec's "Class 3" (free/world-space, compute-once) — confirming this
  scoping explicitly so it isn't mistaken for a gap to close later.
- **Right-panel inconsistency is a confirmed, real problem to fix in the
  consolidation, not carry forward.** Each sub-module's right panel
  (values, Edit/Delete) is built independently today, inconsistently,
  and required dedicated code (`clearSel()` in composer, confirmed in
  source) just to stop a previous module's detail panel from persisting
  after switching sub-tabs. The consolidated module should have **one**
  right-panel pattern — same value-display/Edit/Delete shape — with only
  the type-specific fields inside it varying per placeable kind, not a
  different panel implementation per kind.

## 4. Scope decision: camera first

**Settled.** V1 of the consolidated module is camera-only — recovering
the live-preview fix (§1) and folding Free Camera into the new module's
standard shape (§3's right-panel pattern). Lights and FX join the same
module architecture once their specs exist/are in hand (lighting spec
not yet uploaded; FX has no spec at all yet, per earlier discussion).
Not a v1-does-everything move.

## 5. Open, not yet settled

- Per-type inspector field sets for Lights/FX/assets when their turn
  comes — blocked on `MCCF_Lighting_System_Spec_v0.1_DRAFT.md` (referenced
  repeatedly, still not actually uploaded) and on FX having no spec at
  all yet.
- Right-panel standardization (§3) — needs an actual field/shape design,
  not just the "one pattern, not several" principle stated here.
