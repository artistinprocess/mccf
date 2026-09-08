# MCCF Gesture Constellation System — Design Specification

Extends the current EBPS-driven gesture system from discrete,
single-winner activation toward fuzzy, loosely coupled behavioral
expression, per the design proposal at
`aiartistinprocess.blogspot.com/2026/09/mccf-gesture-constellation-design.html`.

Every mechanism below is marked **CONFIRMED** (exists in the codebase
today, verified by direct inspection — not assumed) or **NEW** (design
proposed here, not yet built). Nothing in this document asserts a file
or API behaves a certain way without that having been checked.

> EBPS describes the state space.
> Gestures provide the behavioral vocabulary.
> Constellations provide expressive combinations.
> Character determines how the vocabulary is spoken.

---

## 0. Prerequisite — X_ITE version upgrade

**Must happen before implementation begins, not alongside it.**

This project is pinned to X_ITE 11.6.0. The constellation staggering
mechanism (§5) should be built against `TimeSensor.cycleComplete`
(confirmed reference implementation in X_ITE 16.3 — see
`seed_note_xite_cycleComplete.md`), not against the fragile
`fraction_changed>=0.99` workaround already living in
`_wirePathTimerBehavior`. Building against the workaround now means
building the stagger logic twice — once fragile, once clean.

Before constellation work starts:
1. Confirm and pin the actual X_ITE version in use.
2. Re-verify all four documented 11.6-specific quirks against it:
   `getActiveViewpoint()` live-tracking, `canvas.browser.currentTime`,
   `startTime`/`stopTime` behavior-switching, bulk `MFVec3f`/`MFRotation`
   constructors.
3. Only then build §5 against `cycleComplete` directly.

---

## 1. EBPS activation ranges — **CONFIRMED, already built**

A gesture occupies a region of EBPS space rather than requiring an
exact value. This is not new design — it's the E_min/E_max/B_min/B_max/
P_min/P_max/S_min/S_max box-range trigger system already built for both
facial expressions (Character Creator's Face tab) and behavior clips
(`_heNewClipObj`'s flat E_min/E_max fields, matching what
`selectBehaviorClip`'s `conditionMet()` reads directly). No rework
needed here — constellations are built on top of this, not instead of it.

---

## 2. Gesture constellations — **NEW**

### 2a. Data model

A constellation is a named, mood-associated set of gesture references,
each with a weight and (§5) a typical activation lag:

```
Constellation: Curious
  eyebrow_raise    weight: 1.0   (strong)
  head_tilt        weight: 0.6   (medium)
  eye_focus        weight: 1.0   (strong)
  hand_open        weight: 0.6   (medium)
  lean_forward      weight: 0.3   (slight)
  smile             weight: 0.3   (slight)
```

Qualitative authored terms map to a numeric table, tunable, not fixed:
`strong=1.0, medium=0.6, slight=0.3` as a starting point.

Extends the existing trigger-range data — a constellation entry
references a gesture (an existing behavior clip or facial expression,
by name) plus a weight, not a new gesture definition. Lives alongside
`E_min`/`E_max`/`priority` in the same data model, not a parallel
structure.

### 2b. Selection — two-stage, not single-winner

Stage 1, **eligibility** (hard gate) — **reuses `SchemaConstraint`,
CONFIRMED live** at `/collapse/run` in `mccf_collapse.py`, registered
against the same `field` object everything else operates on. A
candidate constellation's associated EBPS region is checked against
the current zone/waypoint-derived `channel_floor`/`channel_ceiling`
via the existing `validate_cv()` pattern. Constellations that fail this
gate are excluded before anything probabilistic happens — not
penalized, excluded. This is the Dirac-style structural half of the
design.

Stage 2, **weighted selection within the eligible set** (§6, seeded) —
the Boltzmann-style open half. Among eligible constellations/gestures,
select and weight using the seeded PRNG, not `Math.random()` directly.

### 2c. Blending — facial and body are NOT symmetric, treat separately

**Facial constellations (build first — infrastructure is closer to
ready)**: multiple expressions' AU weight sets combine per-channel via
**max**, not sum or average:

```
final_AU[i] = max(gesture.weight * gesture.au_weights[i]
              for each simultaneously-active gesture)
```

Chosen over sum (avoids saturation when two active gestures both drive
the same AU) and over mean (avoids diluting one strong signal with
several weak ones). Transparent to debug — any AU's current value
always traces to one specific winning gesture.

**Body-gesture constellations (defer — no blending infrastructure
exists)**: behavior clips are discrete keyframe-animation timers with
no mechanism for running two simultaneously and combining their
output. Running two body clips "at once" today has no defined meaning.
**Explicitly out of scope for v1** — build and validate the facial
constellation concept first; body blending is separate, larger
engineering work, not a natural extension of the facial case.

---

## 3. Mood — **NEW**

Not a discrete label. A per-character filtered trajectory over the
existing EBPS signal — an envelope, not a classifier:

- **Susceptibility** — per-cultivar gain on how strongly external
  drivers move the mood filter.
- **Onset / offset** — separate, asymmetric time constants (a
  character who flares fast and cools slowly vs. one who's steady
  until a threshold, then collapses).
- **Drivers** — zone pressure, dialogue deltas, network coupler
  terms — all **CONFIRMED existing inputs**, already flowing into
  `field_tick`. Mood is an aggregation layer over signals that already
  exist, not a new input pipeline.

**Decision: no discrete mood name required for constellation lookup.**
A constellation triggers directly off the *smoothed* EBPS position,
using the same E_min/E_max trigger-range mechanism already built (§1)
— just fed a filtered signal instead of the instantaneous one. Avoids
inventing a mood-classification layer, keeps the fuzziness the design
proposal calls for actually fuzzy rather than quantizing partway
through the pipeline.

---

## 4. Character-specific expression — **NEW**

Per-cultivar bias multipliers on constellation gesture selection,
intensity, and timing — same mood, different character, different
expression. New authored fields per cultivar, alongside the
susceptibility/onset/offset params from §3. Natural home: extends
`CultivarDefinition` the same way `voice_name`/`voice_rate`/etc.
already do.

---

## 5. Stagger and timing — **NEW**, built on §0's upgrade

Timer fan-out kept in the API/polling layer (`applyHotHouseData()`,
**CONFIRMED** already does per-tick, per-agent, per-clip timer
enable/disable work every poll cycle) — not native X3D ROUTE fan-out,
which can't do this without extra delay-chain Script/TimeSensor
plumbing, the same class of complexity `cycleComplete` exists to avoid.

- **Not pure random jitter.** Per-gesture-type *typical lag*, authored
  once per gesture (same authoring weight as `priority` already
  carries) — e.g., gaze/attention shifts typically lead postural and
  hand gestures by a couple hundred milliseconds in real observed
  behavior. Jitter layers on top of this ordering, not instead of it.
- **"Stagger" means two different mechanisms, not one** — for body
  clips, a literal TimeSensor start-time offset. For facial
  expressions (already AU weight sums, per §2c), staggering is a
  weight ramp-in schedule — closer to a crossfade than a delay. Must
  be implemented as two distinct mechanisms; conflating them will
  produce a body-clip-shaped fix that doesn't transfer to the face.

---

## 6. Seeded randomness — **NEW**

Run-to-run variation is desired, not a flaw — explicit decision, humans
and actors both thrive on it. But every random draw in the stagger and
selection mechanisms uses a **seeded PRNG**, never `Math.random()`
directly.

- **Base/default seed** lives in scene control, including "unset =
  randomize" as a valid state.
- **The resolved seed actually used** for a given run is recorded in
  that run's own Scene Arc export (`/arc/export`, **CONFIRMED** already
  records ordered beats per run) — not just the scene default, since
  only a per-run record makes "re-run this exact run" possible.

Matters beyond naturalism: MCCF is also an evaluation instrument.
"Did this run diverge because of a real interaction effect, or because
the stagger rolled differently" needs to be an answerable question on
demand, without needing determinism as the default mode.

---

## 7. Context — **NEW selection input, reusing CONFIRMED infrastructure**

Context perturbs selection via the *same* two-stage structure as §2b:
`SchemaConstraint`'s zone/waypoint-derived floor/ceiling (**CONFIRMED
live**, `/collapse/run`) is the eligibility gate for which
constellations are structurally admissible given current zone and
waypoint position. Proximity feeds the weighted-selection stage,
same as it already feeds `field_tick`.

**Explicitly out of scope**: genre-grammar validated beat sequencing
(hamartia→peripeteia→anagnorisis structural checking). Checked
directly — `mccf_compiler.py` is real and does real work (beats→X3D
interpolators via `ScriptedBeat`/`compile_scene()`, with a working
emotional_register→arousal/valence→E/B/P/S mapping) but has no
genre-grammar validation layer. `DOMAINS.md` itself flags this as
"v2 research," not a present capability — confirmed accurate by
inspection, not oversold. Worth keeping in view for later: the
constitutional arc's own Dirac-outer/Boltzmann-inner framing (waypoint
sequence as required structure, in-waypoint response as open selection)
is a good conceptual fit for constellations too, but it's future work,
not this spec.

---

## 8. Authoring — **NEW UI, existing pattern**

Character Creator, extending the trigger-range panels built for facial
expressions and behavior clips — same visual/interaction pattern, new
panel for constellation membership (gesture + weight + typical lag) and
the §3/§4 per-character mood parameters (susceptibility, onset/offset,
bias multipliers).

---

## Implementation order

1. X_ITE version upgrade + quirk re-verification (§0) — blocks
   everything else.
2. Facial constellation blending only (§2c) — smallest, most tractable
   proof of the whole concept; body-gesture blending explicitly
   deferred.
3. Seeded PRNG infrastructure (§6) — cheap now, expensive to retrofit;
   build before anything else generates unseeded randomness.
4. Mood as filtered EBPS trajectory (§3), triggering existing
   trigger-range mechanism on the smoothed signal.
5. `SchemaConstraint`-based eligibility gate (§2b/§7) — wiring an
   existing, live mechanism to a new candidate type.
6. Stagger (§5), built against `cycleComplete`.
7. Character-specific bias (§4).
8. Character Creator authoring UI (§8).
9. Body-gesture blending infrastructure — separate future spec, not
   part of this one.

## Explicitly deferred, not forgotten

- Body-gesture constellation blending (no infrastructure; §2c).
- Genre-grammar beat-sequence validation (§7; real design exists in
  `DOMAINS.md`, correctly marked there as v2 research).
- The perception-loop idea from the original proposal (internal state
  → constellation → independently testable *perceived* state) —
  genuinely promising, directly relevant to validating EBPS as a
  measurement instrument rather than assuming its readings are ground
  truth, but not scoped into this implementation pass.
