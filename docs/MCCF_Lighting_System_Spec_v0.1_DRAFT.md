# MCCF Lighting System — v0.1 (DRAFT, pre-design)

*Day 76 revision: §4 widened to the full Camera Spec v1.3 X_ITE correction set, §6
corrected from "speculative idea" to "already-proven manifest pattern" per
`worked-manifests.js`'s `SCENE_FOG`, §7's tab-placement item cross-referenced to the
now-settled Place Module Consolidation spec. No other changes — still pre-design,
research not yet done.*

**Status: not a spec yet.** This document exists to record goals, constraints, and open
questions before any class design happens — following the same discipline the camera
system spec used (reason through the architecture before naming classes), but stopped
one step earlier here because lighting is genuinely new territory: cameras had 22
already-authored shot types to converge onto and a working proto pattern to copy.
Lighting starts with none of that. No shot vocabulary exists in Events Editor for
lights yet; no proto pattern is proven for anything but position/orientation of a
viewpoint. Don't let the camera spec's structure be copied prematurely — earn it.

**Explicitly deferred, on purpose:** a class model (à la the camera spec's Class
1/2/3). We don't know enough yet about what X_ITE actually supports to know where the
real seams are. Committing to a class model now would risk the same mistake the camera
system avoided by reasoning through H-Anim/Composer boundaries *before* building —
except here we don't yet have the equivalent boundary-defining facts in hand.

---

## 1. Why this exists

Same underlying motivation as the camera system: give scene authors expressive control
over mood and staging without hand-authoring raw X3D. Cameras solved "how do you look
at the scene"; lighting solves "how does the scene feel while you're looking at it."
The two are complementary, not overlapping — a lighting system that's aware of the
camera architecture (and can reuse its animation infrastructure) is a stated goal, not
just a coincidence of timing.

## 2. What we know for certain (X3D core spec, not X_ITE-specific)

X3D has exactly three light node types. Everything downstream has to compress into
these three, plus whatever animation infrastructure sits on top:

- **DirectionalLight** — parallel rays, no position, no falloff. Closest analog to an
  overall wash or "sun".
- **PointLight** — radiates from a point; has attenuation and radius. Closest analog to
  a practical, a bare bulb, or an omnidirectional fill.
- **SpotLight** — location + direction + `beamWidth`/`cutOffAngle` + attenuation.
  Closest analog to nearly every "focused beam" fixture type (PAR, Fresnel,
  ellipsoidal-minus-gobo, moving head, follow spot).

No native gobo/pattern projection. No native volumetric beam-in-fog rendering as a
per-light property (the `Fog` node affects the whole scene's render, not a specific
light's beam visibility). No native laser/coherent-beam primitive.

## 3. What the person is asking us to check before designing anything

Three concrete leads, not yet verified against X_ITE's actual implementation:

**a) Multi-axis rotation, not just yaw/pitch.** The camera protos composed orientation
as two nested single-axis Transforms (yaw then pitch) — a deliberate choice, since a
camera only ever needed to face somewhere, not spin freely. A moving-head-style light
swinging on a truss may need real arbitrary-axis rotation, which pushes toward
`OrientationInterpolator` (proper axis-angle / spherical interpolation between two
`SFRotation` keys) rather than reusing the camera's nested-Transform composition
unmodified. Open question: does X_ITE 11.6.0's `OrientationInterpolator`
implementation behave the way the spec says, or does it have the kind of gap the
proto/EXTERNPROTO and field-read asymmetry issues did? Needs direct testing, not
assumed from generic X3D knowledge — the project's own hard-won lesson from Day 64.

**b) Followers component (Chaser/Damper-family nodes).** X3D's Followers component
exists specifically for smoothed, eased following behavior — potentially a better fit
for a follow-spot than the hand-rolled per-tick retargeting `agent_track`'s camera
uses today, since a real follow spot operator doesn't snap to the target, they ease
toward it. Unknown: whether X_ITE implements this component at all, and if so, how
completely. Worth checking before assuming we'll hand-roll the same lerp pattern
cameras used — this may be a case where core X3D fills a real gap already, if X_ITE
supports it.

**c) Shaders.** X3D's Shaders component (`ComposedShader` / programmable GLSL) could,
in principle, open effects no light-node parameter alone can reach — a softer falloff
edge, a fake volumetric glow, something closer to a gobo-like effect via fragment
shader logic applied to affected geometry rather than the light itself. Completely
unknown at this point whether X_ITE's shader support is complete enough to be worth
building against, or a rabbit hole. Flagged as speculative, not planned.

None of (a), (b), (c) get designed against yet — they get *checked* against X_ITE's
actual docs and behavior first. Speculation above should be treated as "things worth
testing," not "things we've decided to build."

## 4. Research to do before any class design

- **X_ITE documentation pass** — confirm actual support (not spec-assumed support) for:
  `OrientationInterpolator`, the Followers component, `ComposedShader`/GLSL shaders.
  Day 76 revision, widened per review: don't scope the carried-over lesson to field-
  access asymmetry alone. Camera System Spec v1.3 §4 documents a fuller set of X_ITE
  11.6.0-specific corrections, every one of which cost real debugging time on the
  camera system and should be assumed to apply the moment lighting needs any
  TimeSensor/Interpolator-driven animation (a swinging moving-head light, a flicker/
  strobe) — not rediscovered per-node-type a third time:
  - `canvas.browser.currentTime` returns 0 in this X_ITE build; every `startTime`
    write needs the `performance.now()` fallback.
  - TimeSensor/Transform scalar fields: direct property assignment
    (`node.field = value`), not `.getField().setValue()` — the latter was the
    Events Editor's actual live-preview bug, confirmed Day 76.
  - MF (multi-value) fields — `key`/`keyValue` on any Interpolator — need indexed
    array assignment, never a bulk `X3D.MFFloat(...)`/`X3D.MFVec3f(...)` constructor
    (these don't exist in X_ITE's public API).
  - `ROUTE` targets into a `Transform`'s `translation`/`rotation` need the `set_`
    prefix regardless of the bare field-table listing.
  - `addFieldCallback` (not `addFieldInterest`, which doesn't exist and throws) is
    the only real listener API, and every callback body must wrap its own logic in
    try/catch — an uncaught exception inside one aborts X_ITE's whole event-
    processing batch for that tick, which can stall unrelated scene state.
  Apply this list to `SpotLight.direction`/`.color`/`.intensity` and to whatever
  vessel Transform ends up driving a moving light, on the assumption every one of
  these gotchas recurs until proven otherwise for that specific node type.
- **Personal library + W3DC (Web3D Consortium) examples** — look for existing
  X3D/X_ITE lighting patterns other authors have already solved, especially anything
  touching moving lights, gobo-adjacent tricks, or Follower-based smoothing. No point
  re-deriving something the X3D community has already worked out.
- **Empirical light-count ceiling** — untested assumption, flagged last time and still
  unresolved: how many simultaneous active lights X_ITE handles before frame rate or
  memory pressure degrades. Given the project's existing "two X_ITE instances → memory
  pressure" history, don't assume unlimited scaling — place a realistic number early
  and watch it, before any class design assumes N lights per scene is free.

## 5. Provisionally out of scope (subject to revisit, not permanently closed)

- **Gobo/pattern projection** — no native per-light texture projection in X3D; faking
  it by texturing lit surfaces breaks the moment the subject moves. Same category of
  call as lasers: not impossible, disproportionate for what it'd buy.
- **Lasers** — no coherent-beam rendering primitive; closest approximation (animated
  line geometry) doesn't read as a laser. Skip.
- **Unbounded strobe frequency** — real photosensitivity concern for anyone actually
  watching the rendered scene, not a hypothetical one. If strobe is built at all, it
  needs a hard frequency ceiling and probably a reduced-motion-style toggle, not an
  open author-set field.

## 6. Zone-affect-biased light color/intensity — not speculative, already a proven pattern

**Day 76 revision:** this was originally flagged as a speculative, on-brand idea.
It isn't speculative — it's the same manifest shape `worked-manifests.js`'s `SCENE_FOG`
already implements and ships, end to end, through `field-map.js`'s serializer and
`dispatcher.js`'s `set()`/blend arbitration:

```js
{ name: 'visibility', reach: 'affect-writable', channel: 'tension',
  curve: 'inverse', range: '2000 – 80', arbitration: 'replace' },
{ name: 'color', reach: 'affect-writable', channel: 'valence',
  curve: 'custom', arbitration: 'replace' },
```

A light placed inside a zone taking color/intensity bias from that zone's dominant
channel — grief-heavy zones trending cool and dim, joy-heavy zones trending warm and
bright — is the identical shape: an `affect-writable` field, a named channel, a curve,
an arbitration rule. This isn't a new mechanism to invent once the research in §4
lands; it's applying an already-validated manifest pattern to a new `actorType: 'Light'`.
The open work is naming the right fields/channels/curves for a light (probably
`intensity`↔arousal or ↔valence, `color`↔valence per the Fog precedent above), not
proving the mechanism works — it already does.

## 7. Explicitly not decided in this document

- ~~Whether lights get their own Composer tab/sub-tab or live inside the new
  consolidated Place tab~~ — **settled elsewhere, Day 76**, not still open here:
  `MCCF_Scene_Placement_Module_Consolidation_v0.1.md` decided lights join the
  consolidated Place module once this research lands, camera-first for v1. Cross-
  referenced, not re-decided in this document.
- Any proto names, field sets, or class boundaries.
- Whether move-shot infrastructure (`_computeParametricMoveKeyframes`) gets reused
  as-is, adapted, or bypassed in favor of native Followers/Interpolators once (4a)/(4b)
  are answered.
- Events Editor cue vocabulary for lighting — doesn't exist yet in any form.

---

*v0.1 — goals and open questions only. Next revision should follow the X_ITE docs pass
and library/W3DC survey, at which point class design becomes possible instead of
premature.*
