# MCCF Day 63 Seed — For Day 64

## Companion document, required
**`MCCF_Proto_Timeline_Architecture_Spec_v1_0.md` (v1.5) must be loaded alongside this seed.** This file summarizes and points to it; it does not replace it. The spec has the full reasoning behind every decision below — this seed is the "what to do next" layer on top.

---

## 1. Where the session started, where it ended

Started as a continuation of the camera system work (Phase 2 move shots incomplete, trigger vocabulary thin). Ended having: finished and verified all 22 camera shot types, found and fixed a real geometry bug in the shared look-at math, tested and confirmed the core PROTO architecture risk, decomposed the largest God-object cluster in the backend, designed (not built) a dialog/voice pipeline and traced real gaps in cross-scene emotional continuity, and reached a settled, simple rule for camera-object parenting. Long session — the density below reflects that, not padding.

## 2. Confirmed working — trust these, they were tested, not assumed

- **All 22 camera shot types** — static (7), relational (3), agent-attached (4), named_vp (1), move shots (7, including the previously-unimplemented dolly_in/out, pan, tilt, crane_up, and `agent_track` built parented-from-day-one). Verified via `CameraTestAll_scene.xml`, live in-editor testing, real `Shift`+`F8` capture comparison.
- **`_lookAtOrientation` geometry bug, found and fixed.** Every camera was aiming at the subject's ground/feet position (y=0) instead of eye height, baking a large hidden downward pitch into every shot that compounded with the authored `vAngle`. Fixed with a single `LOOK_AT_HEIGHT` constant inside the one shared function — traced against all six call sites before changing anything, verified by simulation before shipping, verified by live re-test after. All affected presets re-tuned, including worm's eye (`vAngle` 35→-15, since its old value was only "correct" by riding on the bug).
- **Preset corrections**: `extreme_closeup` distance 0.4→0.65, `over_shoulder` 0.8→1.2, `overhead` completely redesigned (was a useless nadir shot, redundant with baked avatar top-views; now an angled high shot with a horizontal offset, -47.5° total pitch, still dynamic/subject-tracking unlike a baked static view).
- **`mccf_hanim_api.py` extracted from `mccf_api.py`** — 6,101→2,776 lines in the main file. One contiguous, self-contained block (confirmed zero dependency on live app state before moving), 55/55 routes conserved, verified by diff not assumption.
- **The SAI-into-PROTO risk is resolved, not open.** Tested directly (`mccf_sai_proto_test.html`/`_scene.x3d`, two instances of one proto): internal DEF names are unreachable from outside (`getNamedNode` throws cleanly for all three), exposed interface fields work and are correctly instance-isolated. **PROTOs are now decided as required infrastructure**, not a direction pending a risk test.
- **A real trigger-resolution bug, found and fixed**, unrelated to cameras specifically: the path server identifies waypoint arrivals by `label`, not the XML `name` cues are authored against, and the old fallback (`stepno` indexed into a flat, document-order waypoint list) broke with more than one agent sharing the scene's waypoint pool. Fixed via a direct `label`→`name` map, demoted the old fallback to true last-resort.

## 3. Architecture decided this session — not proposals, decisions

**PROTOs are required**, composability is the point, "Lego blocks" per the author. See spec §2.2, §2.7.

**Naming convention, required going forward**: PascalCase node/proto type names, camelCase fields, no acronyms ever — motivated directly by the trigger-resolution bug above (`"SForw"` vs `"stewardForward"`). Applies to new work; not a mandate to rename existing production DEFs. Spec §2a.

**Division of labor**: server computes semantic/emotional field values (`ChannelVector`, coherence, drift) authoritatively; the client/SAI only ever reads and renders, never recomputes. Confirmed already the actual pattern in the Loader (traced, not assumed) — protos are the formal seam where this handoff happens. Spec §2.7.

**Three-class camera model, resolved**: (1) scene-root static/author-placed, unparented, covered by `named_vp`; (2) avatar-parented dynamic, proven by `agent_orbit`/`agent_track`, parented by Composer at export time — never baked into the H-Anim character asset; (3) free/world-space compute-once, unchanged, correct by design. Spec §5c.

**Resolved, last thing decided before the session closed**: traveling cameras are children of whatever transform they're tracking — **full stop, not a shot-type-scoped decision.** The earlier framing ("which of the 22 shot types should be parented") was the wrong question. The right rule has no exceptions carved out by shot type. Same rule applies to any future trackable non-avatar object (vehicles, planets, anything that moves and needs a following camera) — not scoped yet, no such object exists in the codebase today, don't assume the avatar-specific plumbing (`EmotionalArc`, waypoint-based position) transfers without checking first.

**How "parent everything that travels" stays cheap**: package each camera shot type as its own proto (or small family of protos). Referencing one in a scene becomes a `ProtoInstance` — a name plus overrides — not a repeated inline `Transform`+`TimeSensor`+`Interpolator` block. "Protos are cheap" isn't aspirational; a `ProtoInstance` costs the same whether there are 3 camera types or 30.

**Dialog & voice pipeline, designed not built** (spec §5a): `DialogLine` proto (content: text, speaker, `voiceId`, `audioUrl`, `emotionalInterpreter`, `channelE/B/P/S`) separated from a `dialog`-track `Cue` (placement: references a `DialogLine`, carries `audioOffset` for drag-to-align sync correction). TTS is the permanent default for live-riffed lines, not just a fallback for missing recordings. `emotionalInterpreter` (which LLM persona's accrued affective habits anchor a character's emotional range) is a distinct field from `voiceId` (audio rendering) — corrected mid-session after a real misreading, don't repeat the conflation. Affect is expressed as the same `ChannelVector` shape already running live, not a disconnected free-text tag. Asset registry: SQLite, project-wide not per-scene, text-hash drift detection for stale recordings. **"Chorus's characters" (unifying live-riffed zone personas into the same casting registry) is flagged in the spec as author-intent, inferred not confirmed — do not build until confirmed.**

**Emotional continuity across scenes, traced not built** (spec §5.3): `DriftManager._get_history` already has continuation-shaped logic (reuses existing history if present) but is pure in-memory, no disk backing. The seed path (`cv_override`) always pulls from static pre-authored arc XML, never consults live history — this is why identical seed values appeared across repeated play/reset cycles in testing. Two small, scoped fixes close the gap: wire the seed path to check `DriftManager` first, and give `DriftManager` disk persistence (reuse the dialog pipeline's SQLite registry, key by character not scene).

## 4. Files produced this session

**Production code** (all verified — syntax-checked, diffed, or both):
- `mccf_x3d_loader.html` — move shots, `agent_track`, trigger-resolution fix, `_lookAtOrientation` fix
- `mccf_scene_composer.html` — `agent_track` vessel nodes, `loop`/`arcDepth`/`trackOffset` export+restore fixes
- `mccf_events_editor_prototype_2.html` — move shot UI, `agent_track` UI, preset corrections (extreme_closeup, over_shoulder, overhead, worms_eye)
- `mccf_api.py` — trimmed 6,101→2,776 lines
- `mccf_hanim_api.py` — new, extracted HAnim module

**Test/diagnostic artifacts**:
- `mccf_sai_proto_test.html` + `mccf_sai_proto_test_scene.x3d` — the SAI-into-proto test, keep for reference, the result is now load-bearing architecture
- `CameraTestAll_scene.xml` — all 22 camera types, one per waypoint, diagnostic order — reusable for regression testing once the proto library exists

**Design/reference**:
- `MCCF_Proto_Timeline_Architecture_Spec_v1_0.md` (v1.5) — the companion document, see above
- `MCCF_Zoom_Demo.pptx` — presentation deck, built from confirmed session content, not aspirational copy

## 5. Immediate next step, agreed but not started

**Convert `agent_orbit` into the first real camera proto.** Not new math — already tested, already correct — a pure repackaging exercise chosen specifically to prove the `ProtoInstance` pattern, the exposed-interface SAI contract, and proto-based parenting all at once, on something with zero remaining behavioral risk. Once that one is solid end-to-end, the other 21 shot types are the same pattern repeated, not 21 new designs. This needs: a new `EXTERNPROTO` file, Composer changes to emit a `ProtoInstance` instead of hand-written vessel XML, Loader changes to talk to the proto's exposed interface instead of raw internal DEFs.

## 6. Bug log carried forward, still not investigated

- **Exports Tab loader — slow, can crash Scene Composer tab.** Suspected cause (not confirmed): multiple X_ITE/WebGL instances not torn down on tab switch. This is the oldest unaddressed item in the log — flagged Day 62, still open at Day 63 close. If Day 64 has any slack, this is worth spending it on before more architecture.
- **Path arc loading** — Loader not finding new path arc files. Filed Day 63, not investigated.
- **Avatar scale** — grid confirmed 10 units per cell (not 1) via `buildGrid()` in Composer, not guessed. Rough photogrammetry suggested avatars may render ~3x taller than the ~1.7m assumed throughout the camera system. Author's call: fix proportions at the asset source, not a corrective `Transform scale` — deliberate choice to avoid a scale-patch that has to be remembered forever. Not otherwise acted on.

## 7. Two open, useful X_ITE findings worth keeping in reach

- **`Shift`+`F8`** copies the current viewpoint (position + orientation, no `jump` attribute) to clipboard — the actual mechanism behind all of tonight's camera capture-and-compare work. `Home`/`End`/`Page Up`/`Page Down` step through a scene's authored viewpoints in sequence.
- **X_ITE version gap**: production is pinned to v11.6.0; current release is v15.1.8. Not investigated, not urgent, flagged so it isn't silently forgotten — possibly relevant to some of the SAI quirks documented in the camera spec's known-issues section.

---

*Day 63 close. Session ran long and covered a lot of ground — camera system genuinely complete and verified, proto architecture's central risk resolved with evidence, several real bugs found by tracing rather than guessing. The crash/slowness thread is the one piece of unfinished business worth naming plainly: flagged at the top of the session, never diagnosed, still sitting there under an increasingly capable system.*
