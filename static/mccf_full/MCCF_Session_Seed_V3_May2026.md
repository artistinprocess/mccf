# MCCF Session Seed — V3 "The New York Rocket" — May 2026 (Updated)

## State
V3 scene arc recording working. Files in `static/`: `mccf_scene_composer.html`, `mccf_x3d_loader.html`. Python: `mccf_api.py`, `mccf_playback.py`. Dirs: `scenes/`, `zones/`, `exports/`.

## Repo
https://github.com/artistinprocess/mccf

---

## Completed This Session

### UI Fixes — Scene Composer
- **Q/R textarea invisible** — root cause was `overflow:hidden` on row div clipping hit area. Fixed by restructuring `renderWPQALines()` into a two-row card layout: type+speaker+delete on row 1, textarea full-width on row 2.
- **Speaker field** — changed from free-text input to `<select>` dropdown populated from `Object.keys(placedAgents)` at render time.
- **Live sync** — added `oninput`/`onchange` handlers to all three fields (type, speaker, textarea) so data is captured keystroke-by-keystroke without needing a re-render.

### Dialogue Line Types — Three-Way Taxonomy
Added `Statement` as a third dialogue type alongside `Question` and `Response`. Implemented as a distinct XML element `<Statement speaker="...">` for clean XSLT selectability.

| Type | LLM Call | TTS | XML Element | Use |
|------|----------|-----|-------------|-----|
| Question | Yes | Yes | `<Question speaker="">` | Directed at another agent — LLM responds |
| Response | No | Yes | `<Response speaker="">` | Scripted reply |
| Statement | No | Yes | `<Statement speaker="">` | Monologue / internal / prayer — no reply |

All three elements carry optional `speaker` attribute. Multiple Statements in sequence are fully supported and recommended for ElevenLabs streaming (one element = one API call when EL is integrated).

### Arc Export — path_name Fix
- `mccf_api.py` `arc_export_save()` now reads `path_name` from POST body and uses it as filename base: `arc_{path_slug}_{timestamp}.xml`
- `path_name` written as attribute on `<Cultivar>` element: `agentname="Cindy" path_name="CindyPath"`
- `mccf_playback.py` `list_files()` reads `path_name` from XML attribute first, falls back to filename parse
- **Note:** existing arc files written before this session only contain agent name — they will display agent name in dropdown, which is correct given available data.

### Arc XML — Full qaLines Support
- `_sceneArcAdvance()` now reads `wp.qaLines` (full sequence) instead of legacy `wp.question` single field
- Question lines → LLM call via `/voice/speak` SSE stream
- Response and Statement lines → recorded as-is, no LLM call
- `_sceneArcRows` carries full `qaLines` array per waypoint for export
- `mccf_api.py` writes all qaLines as individual XML elements with speaker attributes
- Legacy `question`/`response` single fields preserved in parallel for backward compat

### Playback — mccf_playback.py
- `ArcWaypoint` dataclass gains `qa_lines: list` field
- Parser reads all `<Question>`, `<Response>`, `<Statement>` child elements in order, captures `speaker` attribute
- `to_dict()` includes `qa_lines` list so loader receives full sequence
- Legacy `question`/`response` string fields still populated (first Q / last R)

### Playback — mccf_x3d_loader.html
- `pbSpeakQALines()` — chains utterances via `utt.onend`, assigns consistent voice per speaker name using `_pbSpeakerVoiceMap` (persists across steps for stable voice assignment)
- Statements display with em-dash prefix (`— speaker: text`), Questions with `Q:`, Responses in R field
- Poll interval tightened to `pace/3` (was `pace/2` capped at 2s) to avoid missing step display
- **Refresh / Clear buttons** added to arc dropdown — Refresh repopulates and auto-selects newest arc, Clear resets selection
- Auto-selects newest arc on load (server returns newest-first)

---

## Outstanding Bugs

### Path traversal goes off-grid during playback
- Coordinate mismatch between composer canvas and X3D scene
- Waypoint 2 position may appear skipped visually (polling now tighter — retest)
- Diagnosis: check X= Z= values in loader step display during playback
- Root cause likely composer canvas scale vs X3D world units
- **Must Export → Send to Launcher before recording arc**

### Viewpoints VP1–VP7 not found
- Loader buttons hardcoded to VP1–VP7 but composer scene uses `VP_{zoneId}`
- Fix: add VP1–VP7 named viewpoints to composer X3D export, OR make loader VP buttons dynamic from scene

### Reset Position — empty if no arc loaded
- `window._avatarNodeNames` only populated from arc file metadata
- If no arc loaded yet, reset does nothing

---

## Key Constraints — Never Change
- Avatar names late-bound: `safeId = name.replace(/[^A-Za-z0-9_]/g,'_')`
- SAI: `avatarNode.translation = new X3D.SFVec3f(x, y, z)`
- `/voice/speak` → SSE stream, not JSON
- Files: HTML → `static/`, Python → repo root
- Constitutional navigator (`mccf_constitutional.html`) is V2 — do not touch
- `applyArcCV` is the confirmed working SAI path — BroadcastChannel `mccf_arc`
- TTS: Browser Web Speech API only. ElevenLabs deferred to Big Demo. Edge has richer voice library than Firefox.

---

## Architectural Decisions Confirmed

### XML State Architecture
Scene state kept in separate XML files/namespaces (scene, zones, arcs). Revisit namespace consolidation after Big Demo — not urgent.

### Dialogue Element Taxonomy
Three sibling XML elements — `<Question>`, `<Response>`, `<Statement>` — all with optional `speaker` attribute, all carrying text content. Clean for XSLT. One element = one EL API call when EL is integrated.

### ElevenLabs — Deferred, Design Ready
When EL arrives:
- Each `<Statement>` / `<Response>` = one EL streaming call
- Author controls sentence chunking by adding multiple Statement lines — no auto-split needed
- Voice assignment per speaker stored in scene XML `<Agent>` element → EL voice ID
- `voice_settings` driven by field vectors: E→expressiveness, B→stability, P→similarity_boost, S→style

### Vector → Performance Mapping (Big Demo Priority)
**The killer demo:** same scene, same path, same dialogue recorded twice with different field states — agents perform differently because E/B/P/S drives voice and gesture, not scripted emotion tags.

- **Vector → Voice (EL):** `voice_settings` mapped from E/B/P/S per waypoint — already in XML
- **Vector → Gesture (X3D):** BroadcastChannel `mccf_arc` already pushes CV values to loader on every step. Loader needs `cvToGesture(cv)` mapping field state → HAnim/interpolator DEF names in X3D scene
- This is the MCCF doing what it claims — constitutional vectors driving performance, not scripting it

---

## Operation Order for Testing
1. `ollama serve` + `py mccf_api.py`
2. Composer: Scene → Apply Grid
3. Agents → Refresh → place agents with voice
4. Waypoints → place with Q/A/Statement lines
5. Paths → create path
6. Export → Send to Launcher
7. Open loader in separate tab, wait for scene load
8. Composer → Record Scene Arc tab → run
9. Loader → select arc (auto-selects newest) → Play Scene Arc
