# MCCF Day 73 — Seed for Day 74

*Written at ~90% session limit. Priority queue items 1–6 from the Day 72
seed doc are DONE and delivered. This session then moved into real
integration work — reading the actual composer/API, fixing real
(not hypothetical) bugs found by testing against them, and now stands at
the start of "make the Dialogue Editor + upcoming Timeline Editor actually
fit the real system," which is real, multi-day work that shouldn't be
rushed into the last 10% of a session.*

## Status banner

- ✅ Priority queue items 1–6 (calibration fix, schema additions,
  arc-complete trigger, Chorus voice_actor, Kate export/import XML
  revision, real Dialogue Editor tool) — all delivered, all tested.
- ✅ Two real integration bugs found and fixed by actually reading the
  real `mccf_api.py`/`mccf_scene_composer.html` (not guessing):
  1. Dialogue Editor's server load/save was wired against a guessed
     contract — wrong HTTP method, wrong body shape. Fixed against the
     confirmed real contract.
  2. `mccf_api.py`'s `load_scene_xml()` silently dropped
     `tagSource`/`audioFile`/`audioSource` from its JSON response — fixed.
- ⬜ **Full integration pass** — just started. 7 more real files landed
  this session (see below) but weren't read yet; that's the first task
  for Day 74.
- ⬜ **Timeline editor** (build schedule item 5b) — not started. Real
  prototype now in hand (see below).

## What's actually been delivered (all in outputs, all tested)

| File | What it is | Tests |
|---|---|---|
| `mccf_voice_api.py` | Calibration bug fixed (raw hit-count arousal/engagement, hedging no longer mis-tagged) | 25/25 |
| `static/js/dialogue-xml.js` | ttsText/tagSource/audioFile/audioSource, arc-complete trigger, Kate export/import (XML, not bracket) | 27+13 |
| `static/js/dispatcher.js` | arc-complete trigger, shared collision-policy helper | 13/13 |
| `mccf_chorus.py` | `ChorusConfig.voice_actor`, per-take Line capture | 27/27 |
| `static/mccf_dialogue_editor.html` | Real tool, wired to real `/voice/preview`, real dialogue-xml.js, real (confirmed, not guessed) scene load/save contract | 51/51 jsdom |
| `mccf_api.py` | `load_scene_xml()` now returns all four Day-73 dialogue fields | 18/18 |

All test files are alongside in `tests/`.

## Files now on hand, NOT YET READ (Day 74 starts here)

Uploaded this session, confirmed received intact, not yet opened:

- `MCCF_Actor_Architecture_Design_v0.2.md` (28KB) — the actual design doc
  `dispatcher.js` implements. I've only worked from secondhand summaries
  of this until now.
- `mccf_core.py` (61KB) — `Agent`, `ChannelVector`, `CoherenceField`,
  `Librarian`, `Gardener`. Needed to actually run `mccf_api.py` for real
  (this session had to extract one function via `ast` instead, because
  this and ~12 other modules weren't available).
- `mccf_timeline_dialogue_prototype_v2.html` (55KB) — the Day 71 prototype,
  confirmed to exist. Direct visual/interaction reference for the Timeline
  editor, same role the Dialogue prototype played for item 5a/6.
- `mccf_llm.py` (27KB) — `AdapterRegistry`.
- `mccf_hanim_api.py` (145KB) — large; presumably H-Anim clip/gesture
  registration, relevant to the Timeline's gesture lane.
- `mccf_zones.py` (17KB) + `mccf_zone_api.py` (13KB, shown in full this
  turn) — `SceneGraph`, `SemanticZone`, `Waypoint`, `AgentPath`,
  `ResonanceEpisode`, `ZONE_PRESETS`. **One thing already visible from
  `mccf_zone_api.py`'s own inline comment**, worth flagging immediately:
  a real, already-identified bug — `POST /path` used to read
  `data.get('agent')` while the composer's `createPath()`/`savePathEdit()`
  actually sends `agent_name`, so **every path create/edit from the
  Composer silently 400'd and never reached `scene.add_path()`** — paths
  only ever lived in client-side memory or XML restore, never the
  server-side `SceneGraph`. The comment says this was already fixed in
  the copy uploaded (reads `agent_name` now) — worth confirming that fix
  is genuinely in place and didn't regress, early in Day 74.

Still not received: the other ~7 modules `mccf_api.py` imports
(`mccf_zone_attractor.py`, `mccf_scene_wrapper.py`, `mccf_cultivar_lambda.py`,
`mccf_scene_generate_api.py`, `mccf_drift.py`, `mccf_collapse.py`,
`mccf_neoriemannian.py`, `mccf_energy.py`) — lower priority, look
unrelated to dialogue/timeline (sound/harmony/collapse subsystems), not
blocking.

## Open architectural question, still unresolved

`dispatcher.js` (build item 3) has **zero XML persistence** — no
`<Step>`/`<Track>` schema exists anywhere seen yet, and it's never been
wired into `mccf_api.py` or the Composer server-side. Before real Timeline
editor work can start, need to determine: does a Step/Track schema already
exist (design doc, or drafted elsewhere — `MCCF_Actor_Architecture_Design_v0.2.md`
may answer this, unread as of this doc), or does this need a schema-design
pass first, the same sequencing Dialogue's item 5a went through before its
editor could exist. **First thing to check in Day 74**, now that the design
doc is in hand.

## Recommended Day 74 opening move

1. Read `MCCF_Actor_Architecture_Design_v0.2.md` — answers the Step/Track
   schema question above, and lets prior work (dispatcher.js, the trigger
   vocabulary) be checked against the actual source instead of secondhand
   summaries.
2. Skim `mccf_core.py` enough to actually boot `mccf_api.py` for real in a
   test environment — turns every future fix from "extract via `ast` and
   hope" into "run the real server and hit it."
3. Confirm the `/path` `agent_name` fix mentioned above is genuinely intact.
4. Then: Timeline editor, informed by the real prototype and the real schema
   question's answer — likely starts with schema design (dialogue-xml.js's
   `5a` pattern) before any UI work, per the build schedule's own estimate
   (4–5 days) and dependency chain (needs 5a's wiring pattern — done; item 3
   — done; item 4a's multi-writer arbitration — done).

No code changes attempted this turn — everything above is inventory and
planning only, to leave a clean stopping point.
