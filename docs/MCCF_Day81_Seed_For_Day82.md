# MCCF Day 81 Seed — For Day 82

**Status: Events/Timeline/Route Graph merge built and validated, not yet
tested live. Everything below it is queued, not started.**

Roadmap agreed today, in order: **finish and test today's merge → Dialogue
editor (separate module) → Lighting subsystem → wire up EBPS.** Each step
gates the next — don't jump ahead.

---

## 1. What actually happened today, in order

Started from a guided test pass on the Day 80 Timeline/Dialogue build.
Two real bugs (actor-selection, type-persistence-on-reload) surfaced a
much bigger problem: the editor was putting two fundamentally different
kinds of thing — authored-time events and condition-fired events — on one
timeline. That reframing became the day's actual work:

1. **Traced all six pieces of existing playback machinery** in
   `mccf_x3d_loader.html` against real code, not guesses — Step confirmed
   broken (self-documented Day 65 gap: never moves the avatar Transform),
   Play confirmed sound, Play-All's order-group sequencer traced clean
   (no bug found in the loop itself), recorded-path pipeline confirmed
   4-of-5 stages built with playback consumption the missing one.
2. **Named the real distinction:** scheduled events (authored position in
   time, honest on a timeline) vs. sensed events (condition-fired,
   dishonest on a timeline). Full writeup in
   `MCCF_Event_Architecture_Route_Graph_Design_Note.md`.
3. **Built two prototypes** against that split, then **merged two of the
   three tools back together** per today's own late-session correction —
   see §2.
4. **Read a real historical VRML avatar** (`kamala01b.wrl`, a Blaxxun-era
   PROTO) — confirmed the "declared interface" pattern already worked
   once, in your own prior work, and found the likely origin of this
   project's own "Welder-style displacement" language (a `DEF Welder
   Script` doing exactly that job, by hand, decades before the modern
   TimeSensor/ROUTE version of the same idea).
5. **Read `mccf_character_creator.html` and `mccf_hanim_api.py`,
   confirmed a real, half-built bridge:** every gesture clip already
   carries authored `cv_conditions` (E/B/P/S min/max bounds), and the
   write path (Character Creator → hanim API → cultivar XML) is real and
   complete. Nothing reads it. Confirmed by exhaustive search, not
   assumed — this is the literal missing link between EBPS (already live)
   and embodiment (not yet reached), sitting there half-finished.

---

## 2. Current file state — what's live, what's dead

| File | Status |
|---|---|
| `mccf_scene_composer.html` | ✅ Updated. Nav: Scene·Place·Actors·Characters·**Events**·**Route Graph**·Network·Record Scene Arc·Export. Timeline is no longer a separate tab. |
| `mccf_events_editor_prototype_2.html` | ✅ **This is the real deliverable.** Same filename Composer already pointed to. Left pane: Cameras (editable placement, unchanged) + Agents (new, read-only context). Right pane: dispatches placement editor / agent summary / cue editor. Bottom pane: full Timeline strip (camera/light/gesture/path cues, master clock, duration bars). |
| `mccf_route_graph_prototype.html` | ✅ Standalone tab. Node types: Transform, ProximitySensor, TimeSensor, RecordedPath, TimelineTrigger (references Events' saved cues, doesn't duplicate them), AudioClip, TouchSensor. Drag-to-connect, type-checked, cycle-rejected, compatible-port highlighting. Saves/restores via Composer (survives tab switches, not yet reaching X3D). |
| `mccf_events_editor_prototype_3.html` | ❌ **Dead.** Was the fused everything-in-one-file version, superseded twice over. Don't deploy. |
| `mccf_timeline_prototype.html` | ❌ **Dead.** Was the split-out standalone Timeline tab; absorbed back into `_prototype_2` per today's merge decision. Don't deploy. |
| `mccf_timeline_dialogue_prototype_v2.html` | ❌ **Retired**, not loaded by any tab. Dialogue becomes its own module — see §4. |

All four active/changed files passed the same validation pass (HTML tag
balance, JS syntax check, duplicate-function-declaration sweep) before
being handed over. Caught and fixed for real, not left in: a missing
`preventDefault()` that was causing Route Graph's connection-drag to
sometimes fail and triggering a text-highlight artifact; a duplicate
`id="mode-events"` div; a scene-refresh bug that would have wiped an
agent selection every time fresh data arrived; a `mccf_ready` handshake
gap that meant Route Graph's initial load only worked by accident.
**None of this has been run in an actual browser yet** — that's the first
thing Day 82 needs to do.

---

## 3. Immediate next step — test the merge, then wire the leftover gaps

- [ ] Open Composer, load a real scene, click Events — confirm Agents
      section renders, camera placement editing still works exactly as
      before, adding a cue at the playhead works, cue editor round-trips
      correctly.
- [ ] Click Route Graph — confirm live agent/camera/zone/recordedPath
      names populate the instance dropdowns (not seed data). Author a
      cue in Events, **save it**, switch to Route Graph, add a
      `TimelineTrigger` — confirm it shows up only after the Events-side
      save, not before.
- [ ] Confirm both tabs survive a tab-switch without losing state, and
      that Route Graph's own graph survives an actual page reload (the
      persistence fix from earlier today).
- [ ] **Known, deliberate gap, not a bug to chase:** nothing authored in
      either tool reaches exported X3D yet. Same shape as recorded-path
      playback — real data, no consumer. Worth deciding whether that
      consumption step is worth building before or after the dialogue
      module, once the UI itself is confirmed solid.

---

## 4. Then: the Dialogue editor, as its own separate module

Explicitly not a revival of `mccf_timeline_dialogue_prototype_v2.html` —
that combined dialogue with scheduled production cues in one tool, which
was part of what made it hard to use. Whatever gets built next should
stay separate from Events/Timeline/Route Graph, on its own terms. No
design work done on this yet beyond the decision that it's separate —
that's Day 82 (or later)'s job to actually shape.

---

## 5. Then: Lighting subsystem

Not started, not designed. Existing placeholders ("Lights: not yet
implemented") sit in both the Stage panel and the Timeline's light-cue
target field in the merged Events tool — those are real stub points
already waiting, not something to invent from scratch.

---

## 6. Then: wire up EBPS

The big one, and today surfaced real groundwork for it that wasn't known
to exist before today:

- **The confirmed live layer** (Day 81 consolidated note, still
  accurate): Trust (Ext. 1), Salience (Ext. 2), Attentional Filter
  (Ext. 4) all genuinely fire during real playback, confirmed against
  `mccf_x3d_loader.html`'s actual call sites, not assumed. Controlled
  Forgetting (Ext. 3, residue) remains real, correct, and unexecuted —
  `/arc/residue` still has no caller.
- **The new finding, ready to be picked up:** `cv_conditions`
  (E/B/P/S-bounded gesture eligibility) is authored, persisted, and
  completely unread. This is very plausibly where EBPS and embodiment
  should first actually touch — a live agent's current E/B/P/S deciding
  which of its available gesture clips is eligible, rather than gestures
  being purely manually triggered as they are today.
- **The still-open architecture:** the Observation Model / Evidence
  Object / `PersistenceField` design from the Kate exchange
  (`MCCF_Observation_Model_Architecture_Note.md`) — proposed, agreed,
  zero lines built. Worth revisiting once EBPS wiring is actually on the
  table, not before.

---

## 7. Loose thread, worth naming so it isn't lost

**The avatar proto-interface question is real and still unresolved.**
Confirmed today: Character Creator already builds real H-Anim joint
keyframes (solid, no rework needed) but wraps nothing in a declared
`ProtoInterface` — gestures are reached by `timerDEF` string convention,
same as always. The camera rigs (`mccf_camera_protos.x3d`) already do
this properly; avatars don't yet. `kamala01b.wrl` is a real, working
precedent for exactly this pattern (a consolidated `set_gesture` selector
instead of N raw eventIns, meaningful eventOuts for signaling state
outward, private internal dispatch logic) — worth returning to when
avatar interfaces actually get designed, not before. Not blocking
anything in §3–§5, but don't let it get lost either.

---

Good session — thank you for saying so, means a lot given how much
ground this one covered. Go handle the wedding. Bridezilla and dread now,
a good story later — they always are. See you at Day 82.
