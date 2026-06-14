# MCCF Day 26 Session Handoff
**Generated:** 2026-05-25 end of Day 26
**Repo:** https://github.com/artistinprocess/mccf — branch `master`
**Rule:** Author does not edit code. Claude delivers complete files only.

---

## What Was Accomplished Today

### 1. Relational Dynamics — all four extensions implemented
Spec: `MCCF_Relational_Dynamics_Extension_Spec.md`

**Extension 1 — Attentional Filter**
- `AgentRuntimeState` gains `receptivity` field `{E, B, P, S}` in [0,1]
- `apply_expressive_delta()` scales each incoming delta by `receptivity[ch]` before drift bound
- `arc/record` loads receptivity from request body or cultivar registry on each waypoint

**Extension 2 — Emotional Salience Memory**
- `_compute_salience()` helper: coherence delta + eps_delta + phase bonus → [0,1]
- `_arc_coherence_history` entries extended with `salience`, `phase_fired`, `eps_delta`, `timestamp`
- `couplers/tick` backfills `phase_fired=True` and recomputes salience on phase transition

**Extension 3 — Bayesian Trust as Dynamic Link Strength**
- `_link_trust` dict: `(src, tgt)` → Beta(α, β) prior
- `_get_link_trust()` / `_update_link_trust()` helpers
- `field_tick()` uses `strength_eff = authored × (1 + μ - 0.5)`
  - μ=0.5 (no history) → authored strength unchanged
  - μ→1.0 (convergent) → up to 1.5× authored
  - μ→0.0 (divergent) → down to 0.5× authored
- `couplers/tick` response includes `trust` block per directed link
- Trust panel added to loader field overlay (▶ trust toggle, bar + signed % modifier)

**Extension 4 — Controlled Forgetting**
- `_compute_arc_residue()`: salience-weighted Ebbinghaus decay → {E,B,P,S} delta
- `POST /arc/residue` endpoint: opt-in per scene via `continuity: true`
- NOT yet wired into `_seedArcRecord` in loader — deliberate, requires `<Continuity/>` scene opt-in

**Files modified:** `mccf_api.py`, `mccf_cultivar_lambda.py`, `mccf_x3d_loader.html`

**Confirmed working:** Trust panel displays in loader overlay. Phase transition fires at
tick 5 (mean_sim=0.9967) when Cindy and The Gardener share similar constitutional vectors.
Trust at ±0% after 3 ticks — expected, convergence threshold not yet crossed at this scene scale.

**Known calibration note:** Phase transition threshold (0.85) met trivially when two agents
have similar CVs. May need to require a *change* in similarity rather than just a high value.

---

### 2. HAnim Editor Spec — written and submitted to W3DC H-Anim WG
File: `MCCF_HAnim_Editor_Spec.md`

Three-tab browser-based authoring tool integrated as overlay in Character Creator.
Covers: Skin (UV atlas swap), Pose/Gesture (joint rotation keyframing), Face (FACS displacers).

Five questions submitted to WG for review:
1. SAI `weight` write confirmation across X3D browsers
2. LOA level recommendation for portable clips
3. Clip portability format — `<Behaviors>` element as candidate standard
4. Normative FACS-to-displacer mapping
5. UV atlas layout standardization

Companion blog post also written: `mccf_affective_auditing_blog.md`
— positions MCCF as auditable affective architecture for LLM safety.
Both documents sent to W3DC H-Anim WG and circulated.

---

### 3. HAnim Editor Phase 1 — implemented and confirmed working
**File:** `static/mccf_character_creator.html`

The HAnim Editor is a full-screen overlay launched from the Avatar Geometry section
of the Character Creator via **✦ Open HAnim Editor →** button. Button is disabled until
a figure is loaded; enables automatically on `onHAnimFileSelected` success or `loadForm`.

**Skin tab (Phase 1 — fully live):**
- Drop zone: PNG/JPG drag-and-drop or file picker
- Canvas thumbnail loads actual atlas from `/static/avatars/` with colour-block fallback
- Direct URL input with Apply/Reset
- Atlas region map (6 regions colour-coded)
- AI generation guidance panel
- On export: data URL skins uploaded via `POST /hanim/skin_upload` first, then `POST /hanim/export`

**Face tab (Phase 1 — fully live):**
- 23 FACS AU sliders (Jin displacer set, confirmed X_ITE compatible)
- 7 Ekman presets with calibrated AU weights
- Expression save/recall with active AU summary display
- Receptivity sliders for E/B/P/S channels (MCCF channel colours)
- Expressions and receptivity included in export payload

**Pose/Gesture tab (Phase 2 stub):**
- Placeholder panel with full Phase 2 feature list
- "Phase 2 →" button toasts phase note

**Status bar:** live status text, dirty indicator, Export button

**Two server endpoints NOT YET IMPLEMENTED** (needed for Export to work):
- `POST /hanim/skin_upload` — receives `{cultivar, data_url}`, saves image to `static/avatars/`, returns `{path}`
- `POST /hanim/export` — receives full payload, writes HAnim X3D + cultivar XML atomically

---

## Start Day 27 Here

### Immediate: Wire the two export endpoints

Add to `mccf_api.py`:

```python
@app.route('/hanim/skin_upload', methods=['POST'])
def hanim_skin_upload():
    # Receives {cultivar, data_url}
    # Saves image to static/avatars/<cultivar>_skin.png
    # Returns {status, path}

@app.route('/hanim/export', methods=['POST'])
def hanim_export():
    # Receives {cultivar, hanim_src, skin_url, receptivity,
    #           expressions, au_weights, clips, displacers}
    # 1. Updates ImageTexture url in HAnim X3D file
    # 2. Updates <Receptivity> in cultivar XML
    # 3. Writes <Behaviors> from clips list (Phase 2 will populate)
    # 4. Atomic write — backs up both files first
    # Returns {status, hanim_path, cultivar_path, clips_written}
```

For Phase 1, the X3D write only needs to update the `url` attribute on the
`ImageTexture` DEF matching `JinLOA4TextureAtlas` (or the first `ImageTexture` node).
The cultivar XML write updates `<Receptivity>` and `<HAnimFigure src=.../>`.

### Then: HAnim Editor Phase 2 — Pose/Gesture

Replace the stub panel with working joint controls:

1. `GET /hanim/joints?src=<path>` endpoint — parse joint hierarchy from X3D, return
   `[{name, def, center, parent}]` array. Already have the X3D file on disk.

2. Joint hierarchy tree panel (left side of pose tab, grouped by body region)

3. Rotation sliders per selected joint — four sliders (x/y/z axis + angle)
   - SAI write via postMessage to X_ITE iframe: `{type:'setJointRotation', joint, rotation}`
   - X_ITE preview page needs a listener for this message

4. Keyframe record button — stores `{t, joints:{name:[ax,ay,az,angle]}}` in session state

5. Timeline bar — three default keyframes at t=0, t=0.5, t=1.0; draggable markers

6. Clip list — name, cycleInterval, loop, priority, CV conditions

7. Export: serialize to `OrientationInterpolator` + `TimeSensor` + `ROUTE` blocks

**Architecture note for Phase 2 SAI:**
The X_ITE iframe preview at `/avatar/preview?src=...` needs to accept `postMessage`
from the parent window to write joint rotations. Add a `message` event listener to the
preview page that calls:
```javascript
browser.currentScene.getNamedNode(jointDEF).rotation = new X3D.SFRotation(...)
```
This is the same SAI pattern confirmed working for behavior timers in the loader.

---

## Current File State

| File | Status | Notes |
|------|--------|-------|
| `mccf_api.py` | ✅ Deployed | Relational Dynamics all 4 extensions live |
| `mccf_cultivar_lambda.py` | ✅ Deployed | `<Receptivity>` parse/serialize added |
| `mccf_x3d_loader.html` | ✅ Deployed | Trust panel live in field overlay |
| `mccf_character_creator.html` | ✅ Deployed | HAnim Editor Phase 1 overlay live |
| `MCCF_HAnim_Editor_Spec.md` | ✅ Written | Submitted to W3DC H-Anim WG |
| `mccf_affective_auditing_blog.md` | ✅ Written | Ready to publish |
| `mccf_api.py` `/hanim/skin_upload` | ❌ Not implemented | Needed for skin export |
| `mccf_api.py` `/hanim/export` | ❌ Not implemented | Needed for all exports |

---

## Architecture Invariants (unchanged)

- `enabled=true/false` is the ONLY SAI mechanism for behavior timers in X_ITE
- `Timer_N.isActive=true` → Walk; `fraction_changed>=0.99` → Default
- ϕ written only by `arc/record`; ϵ written only by `apply_expressive_delta()`
- Trust modifies `strength_eff`, never agent state
- Salience stored in history, never applied to ϕ or ϵ directly
- `TimeSensor` DEF convention: `{ClipName}Timer`
- ROUTEs MUST be last in X3D scene file
- All behavior Timers: `enabled="false"` in HAnim X3D file
- `var API = 'http://localhost:5000'` in all HTML files
- HAnim export writes both X3D and cultivar XML atomically

---

## Reference Documents (upload at session start if needed)

- `MCCF_HAnim_Editor_Spec.md` — full Phase 2/3 design
- `MCCF_HAnim_Behavior_Activation_Spec.md` — behavior system spec
- `MCCF_Relational_Dynamics_Extension_Spec.md` — Relational Dynamics spec
- `mccf_api.py` — current server (for endpoint additions)
- `mccf_cultivar_lambda.py` — cultivar model (for export endpoint)
- `mccf_character_creator.html` — for Phase 2 pose tab work
