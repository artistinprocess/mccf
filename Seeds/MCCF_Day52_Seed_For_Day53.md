# MCCF Day 53 Session Seed — Handoff from Day 52

**Rule:** Author does not edit code. Claude delivers complete files only.
**GitHub:** Commit `fdd3835` on master — Day 52 complete. Clean.
**CRITICAL FIRST STEP EVERY SESSION: XML validation pass before any other work.**
**Version naming:** Current working build = **Saturn I** (in progress). Next release = **Saturn II**.

---

## System Status — End of Day 52

**Coupler system fully complete. Composer + API verified working.**

| Item | Result |
|------|--------|
| `mccf_couplers.py` — all 7 couplers (R,D,I,G,T,L,Int) | ✅ Complete (Day 15) |
| `AgentRuntimeState` ϕ/ϵ split + `apply_expressive_delta` + receptivity filter | ✅ Complete |
| `field_tick` orchestration + network topology parsing + Bayesian trust scaffolding | ✅ Complete |
| Composer Network UI — 7 coupler checkboxes with per-param panels | ✅ Complete Day 52 |
| Checkbox event bubble fix — no double-toggle | ✅ Complete Day 52 |
| XML export writes `couplers=` and `coupler_params=` attributes | ✅ Complete Day 52 |
| XML import reads new format; legacy `type=` links converted via typeMap | ✅ Complete Day 52 |
| `mccf_api.py` `_parse_network_links` reads `coupler_params` JSON | ✅ Complete Day 52 |
| `hanim_src` persisted in `EmotionalArc` XML export and restored on load | ✅ Complete Day 52 |
| Agent detail panel shows inbound couplers and authored params | ✅ Complete Day 52 |

---

## Bugs Fixed Day 52 — Permanent Record

| Bug | Root cause | Fix |
|-----|-----------|-----|
| Coupler params silently ignored | `_parse_network_links` always returned `coupler_params: {}` — never read XML attribute | Added `json.loads(link_el.get('coupler_params'))` in API parse loop |
| Composer wrote stale `type=` attribute | `exportSceneXML` Network block not updated from legacy format | Rewrote to emit `couplers=` and `coupler_params=` |
| Coupler checkbox double-toggle freeze | Checkbox click bubbled to parent div `onclick`, toggled state twice | `stopPropagation()` on checkbox; `toggleCoupler` checks `event.target` |
| `hanim_src` lost on scene reload | Never written to `<EmotionalArc>` XML | Added `hanim_src=` attribute to export; reads it back on restore |
| No coupler visibility for agent | Agent detail panel showed weights/position/avatar only | Added "Couplers Affecting This Agent" section populated from `networks` array |

---

## Working File State — End of Day 52

| File | Location | Status |
|------|----------|--------|
| `mccf_scene_composer.html` | `static/` | Day 52 — coupler UI complete, hanim_src persistence, agent coupler panel |
| `mccf_api.py` | root | Day 52 — coupler_params parsed from scene XML |
| `mccf_couplers.py` | root | Day 15 — all 7 couplers implemented, confirmed correct |
| `mccf_cultivar_lambda.py` | root | Day 15 — `<Receptivity>` parsing complete |
| `mccf_x3d_loader.html` | `static/` | Day 51 — all sound fixes, SAI proxy fixes |
| `testssound.x3d` | `static/x3d/` | Day 51 — no Convolver, correct MFString urls |
| `testssound_scene.xml` | `scenes/` | Day 52 — updated with `couplers=` Network block |

---

## Architecture Invariants — These Never Change

```
ϕ (constitutional_cv)  — written ONLY by arc/record. Never by couplers.
ϵ (expressive_cv)      — written ONLY by apply_expressive_delta().
observed_cv            — ϕ + ϵ clamped [0,1]. Couplers read this.
Receptivity            — filters delta BEFORE drift bound. Character property.
coupler_params         — authored in Composer, written to scene XML, parsed by API.
                         Couplers always fall back to hardcoded defaults if params absent.
SAI Script fields      — always use getField('name').setValue(v), never node.field = v
Node discovery         — always getNamedNode('DEF'), never enumerate namedNodes
```

---

## W3DC / Don Brutzman — WaypointInterpolator Contact (Day 52)

Don Brutzman (Web3D Consortium) responded to outreach about waypoint interpolation.
He has a working `WaypointInterpolatorPrototype.x3d` in the Savage archive:
- `https://www.web3d.org/x3d/content/examples/Savage/Tools/Animation/`
- Runtime JS computes PositionInterpolator + OrientationInterpolator from waypoint array
- Smooth turning: half rotation complete at waypoint, begins before, finishes after
- Per-leg durations or speed; configurable turning rate
- Known issue: pitch angles negated (browser-era workaround, Don willing to fix)

**Relevance to MCCF:** The turning-rate math feeds directly into the recorded path system
(Saturn I Priority 3). Once recorded paths exist, Don's orientation logic is needed to
generate smooth OrientationInterpolators from raw position sequences.

Email sent Day 52. Awaiting reply with source access and licensing confirmation.

---

## Saturn I — Priority Queue for Day 53

### Priority 0 — Convolver back in (correct architecture)
Current state: Convolver stripped from testssound.x3d. Audio graph is flat.

Correct X_ITE audio graph:
```xml
<AudioDestination>
  <Gain DEF="GainNode_<zoneKey>_Ambient" containerField="children" gain="0">
    <Convolver containerField="children" url='"media/convolver/Deep Space.wav"' normalize="true">
      <AudioClip containerField="children" url='"media/piano1.mp3"' loop="true" startTime="-1" stopTime="-2"/>
    </Convolver>
  </Gain>
</AudioDestination>
```
- SoundFader Script ramps `GainNode_<zoneKey>_Ambient.gain`
- Verify Convolver IR loads before enabling
- Check X_ITE docs for Gain node SAI field access pattern first

### Priority 1 — Master volume ceiling in SoundFader
Current state: `spSetFader('masterVolume', v)` writes `AudioDestination.gain` directly.
Ramp ignores master ceiling on zone entry.

Fix options:
- Pass `masterVolume` as declared `inputOnly SFFloat` on SoundFader Script — ramp uses as ceiling
- Or: re-apply master scale after ramp completes

### Priority 2 — Scene-level ProximitySensor (Saturn I begin)
```xml
<ProximitySensor DEF="ProximitySensor_Scene" size="1000 1000 1000" enabled="true"/>
```
- Scene root, no parent Transform, world coordinates
- Loader: register SAI field callbacks on `position_changed` and `orientation_changed`
- Gate: only active when recording is enabled

### Priority 3 — Recorded path system
Full design in `MCCF_RecordedPath_Design.md`. Sequence:
1. ProximitySensor_Scene in composer export (Priority 2 above)
2. SAI callbacks in `navStartRecord()` / `navStopRecord()`
3. `navProcessRecording()` with RDP decimation
4. Record toolbar in loader UI
5. `RecordedSegment` in scene XML / composer export
6. OrientationInterpolator emission — use Don Brutzman's turning-rate math when available
7. Stage view curve overlay in composer

### Priority 4 — Relational Dynamics Extensions (from `MCCF_Relational_Dynamics_Extension_Spec.md`)
Prerequisite: coupler system working (ϵ drifting from ϕ confirmed) ✅

Implementation order per spec:
1. **Attentional Filter** — done (receptivity in `apply_expressive_delta`) ✅
2. **Emotional Salience Memory** — next: extend `_arc_coherence_history` with
   `salience`, `phase_fired`, `eps_delta`, `timestamp` fields. One session.
3. **Bayesian Trust** — requires salience memory. One to two sessions.
4. **Controlled Forgetting** — requires salience + trust. One session.

### Priority 5 — Dope Sheet: camera cut track
Composer Cinematics tab — Viewpoint pins on timeline, camera cuts at waypoint arrivals.

### Priority 6 — VRML library triage
When author places library above project root.

### Priority 7 — GitHub housekeeping
Consider `.gitignore` additions:
- `exports/` — arc XML accumulates rapidly
- `static/x3d/media/soundeffects/` — large collection, not core code

---

## Known Bugs Carried Forward

| Bug | Where | Notes |
|-----|-------|-------|
| Master volume mid-ramp override | loader / SoundFader Script | Ramp ignores master ceiling. Priority 1. |
| testScene3.x3d SoundFader no playing gate | testScene3.x3d | Old export. Regenerate from composer. |
| Arc waypoints in reverse order | loader / arc recorder | WAYPT3→WAYPT2→WAYPT1 in arc XML. Low priority. |
| `_pivotAgentToSegment` cache miss | loader | Cache keyed `id_N`, lookup uses int. Cosmetic. |
| `BodyMat_Cindy` not found | loader | Material node missing from Cindy X3D. Cosmetic. |
| `pbPushPosition: no cultivar in wp` | loader | Empty terminal waypoint. Minor. |
| Zone ID leaks into LLM context | API / prompt | `soundtestzonw` visible to LLM. Pass human-readable label only. |
| Coupler tick not yet wired to scene arc | loader | `/couplers/tick` endpoint exists; not called from loader yet. Saturn I. |

---

## Sound Engine Architecture (permanent record — confirmed working Day 51)

```
Track 1: Music    — scene root AudioDestination, loop=author-set, SAI-started on Play
Track 2: Ambient  — inside Zone Transform, Gain gain=0, SoundFader Script ramps on enter/exit
                    Gate: SoundFader ignores isActive until loader sends playing=true via SAI
                    Target Day 53: Convolver in chain, Gain node as volume control point
Track 3: Bed      — scene root AudioDestination, enabled=false at load, SAI enables on Play
Track 4: Dwell    — inside Zone Transform, loop=false, SAI fires on dwell timer expiry
```

---

## The Reaper Vision (keep visible)

Same machine, loopback, near-zero latency.
Zone enter → Reaper region plays.
Tension → CC11 modulates live instrument.
Dwell → one-shot sample fires.
Musicians become scene operators.
The DAW is the mixing desk for the world.

---

## Bigger Picture (updated Day 52)

1. **Convolver + Gain node** — Day 53 first ← warm-up task
2. **Master volume ceiling in SoundFader** — Day 53
3. **Saturn I: Scene ProxSensor + recorded path** — Day 53–54
4. **Relational Dynamics: Salience Memory** — Day 53–54
5. **Saturn I: Dope Sheet camera track** — Day 54
6. **VRML library triage** — when author places files
7. **ElevenLabs integration** — gate: sound stable ✅
8. **Avatar scaling fix** — Salida/Jack mismatch
9. **Character prompt authoring** — Salida brief (200 words)
10. **Reaper bridge testing**
11. **Scene player script** — headless playback
12. **User's Guide + System Manual**
13. **Multi-avatar collision behaviour**
14. **Coupler tick wired to scene arc in loader**

---

*GitHub current: commit `fdd3835` — Saturn I in progress.*
*Day 52: Coupler system complete end-to-end. Composer + API verified. Don Brutzman contact made.*
*Day 53 launch: Convolver + Gain node, master volume polish, Saturn I ProxSensor begins.*
