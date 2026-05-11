# MCCF Session Seed — V4 "The New York Rocket" — Day 7

**Repo:** https://github.com/artistinprocess/mccf  
**Last commit:** a7e99ca — Day 6 changes pushed and verified clean.

\---

## State at End of Day 6

### Completed This Session

**X3D Named File Directory**

* `static/x3d/` replaces single stomped `static/mccf\_scene.x3d`
* `mccf\_api.py`: `/static/x3d/<filename>` serve route, `/scene/x3d/upload` saves as `{scene\_name}.x3d` using `X-Scene-Name` header, `/scene/x3d/list` returns newest-first list
* `mccf\_scene\_composer.html`: `sendToLauncher()` passes `X-Scene-Name` header, success toast shows actual filename
* `mccf\_x3d\_loader.html`: X3D scene dropdown above arc dropdown, `x3dLoadFiles()` / `x3dFileChanged()`, canvas `src` set dynamically

**ROUTE Ordering — Hard Rule Enforced**

* ROUTEs must be last in X3D scene — VRML2.0 rule, X\_ITE enforces it strictly
* `buildInterp` split into `buildInterpNodes(path)` and `buildInterpRoutes(path)`
* `buildX3DString()` and `exportX3D()` both emit: all nodes → MCCFMaster Script → ROUTEs last
* Comment marker: `<!-- ═══ ROUTEs — must follow all DEF nodes ═══ -->`

**MFString Quoting Fixed**

* `NavigationInfo type`, FontStyle `family`/`justify`, Text `string` all use proper `'"VALUE"'` quoting
* Eliminates all X\_ITE XML Parser MFString warnings

**Ollama Conditional — Only Fills Blank Responses**

* `\_sceneArcAdvance()` now looks ahead: if a Question is immediately followed by a non-blank authored Response, records it as-is and skips Ollama
* Only Questions with no authored response following them go to Ollama
* Authored `Statement` lines pass through unchanged as before

**Voice Map Cleanup**

* `pb-voice-select` dropdown removed from loader entirely
* `pbSpeak()` uses `\_pbVoices\[0]` fallback (legacy single-line path only)
* `pbLoadVoices()` still populates `\_pbVoices` silently, invalidates `\_pbSceneVoiceMap` on reload
* `pbVoiceChanged()` simplified — no dropdown to show/hide

**`actor` Field Fixed in Scene XML Export**

* Was hardcoded `actor="ollama"` — now reads `run-adapter` dropdown value at export time

**`pb-voice-select` and Record Pace Field Removed**

* Pace field removed from Record tab UI — was redundant with per-waypoint pace in scene XML
* `\_sceneArcAdvance` step interval hardcoded to 2s

**`applyHotHouseData` agentMap Fixed**

* Was hardcoded `'The Steward' → 'Steward'` (old short-name convention)
* Now dynamically built from data keys using `safeId` regex — matches composer output exactly

**`qaLines` Field Name Bug Fixed**

* Loader was reading `wp.qa\_lines` (snake\_case) but server serializes as `wp.qaLines` (camelCase)
* Fixed to `wp.qaLines||wp.qa\_lines` — was silencing all multi-line waypoint dialogue

**`static/mccf\_full/` Cleanup**

* Accidentally committed codebase snapshot removed from repo

\---

## Active Bug — HIGH PRIORITY

### Second Waypoint Speech/Dwell Not Firing

**Symptom:** 3-waypoint scene plays waypoints 1 and 3, skips 2. Avatar travels through temple without pausing or speaking.

**Root cause identified:** `Arrival\_` Script fires `segmentArrived` outputOnly field in X3D, but the loader has no reliable listener. The server never advances its step counter for segment 2, so `pbUpdateDisplay` never fires TTS, so `pbReleaseDwell` is never called, so `Dwell\_Cindy\_1` never starts, so `Timer\_Cindy\_2` never fires.

**Attempted fix (Day 6, not yet working):**
`pbActivateX3DTimers` now tries to register `addFieldCallback` on `Arrival\_{agent}.segmentArrived` via `arrNode.getField('segmentArrived').addFieldCallback(name, fn)`. Falls back to 200ms polling if `addFieldCallback` unavailable. Neither confirmed working yet — session ended before verification.

**X\_ITE SAI uncertainty:** It is not confirmed whether X\_ITE supports `addFieldCallback` on `outputOnly` Script fields via the external SAI. The poll fallback may be the only reliable path.

**Diagnosis approach for next session:**

1. Deploy current loader, check Firefox F12 console for:

   * `pbActivateX3DTimers: wired segmentArrived callback on Arrival\_Cindy` — callback path
   * `pbActivateX3DTimers: addFieldCallback unavailable for Arrival\_Cindy — using poll fallback` — poll path
   * `segmentArrived callback: Arrival\_Cindy seg=1` or `segmentArrived poll: Arrival\_Cindy seg=1`
2. Also check X\_ITE editor console for `Arrival\_Cindy: arrived seg 1` — confirms X3D side is firing
3. If neither path fires, consider alternative: have `Arrival\_` Script write to a well-known scene node (e.g. a `StringSensor` or `IntegerTrigger`) that the loader polls via SAI

\---

## Known Issues — Priority Order

1. **Second waypoint dwell/speech** (HIGH) — see above
2. **Three voices clean verification** (MEDIUM) — needs working end-to-end first
3. **Waypoint path reorder UI** (MEDIUM) — up/down arrows on path waypoint list
4. **X3D export → server save** (LOW) — `exportX3D()` still downloads to browser; should POST to `/scene/x3d/upload` same as Send to Launcher
5. **`static/x3d/` not in git** (LOW) — directory created by API on first export; add `.gitkeep` if desired

\---

## Architecture — Confirmed Working

```
Play → SAI sets Timer\_{agent}\_1.startTime = browser.currentTime
     → Avatar travels segment 1
     → Timer\_1.cycleTime → ROUTE → Arrival\_{agent}.arrived
     → Arrival\_ script fires segmentArrived (outputOnly)
     → \[MISSING LINK] loader detects segmentArrived → calls pbStep()
     → Server advances step → pbUpdateDisplay fires TTS
     → TTS completes → pbReleaseDwell(agentSafeName)
     → SAI sets Arrival\_.releaseDwell = true
     → Arrival\_ script starts Dwell\_{agent}\_1
     → Dwell\_1.cycleTime → ROUTE → Timer\_{agent}\_2.startTime
     → Repeat for each segment
```

**X3D Build Order (enforced, never change):**

```
ProtoDeclares
NavigationInfo / Background / Lights / Viewpoints
Ground / Grid
Zones
Avatars
Animation nodes — all agents (buildInterpNodes: Interp, Timer, Dwell, Arrival\_, Kill\_)
MCCFMaster Script
══ ROUTEs — all agents (buildInterpRoutes) — ABSOLUTELY LAST ══
</Scene>
</X3D>
```

\---

## Immediate Roadmap — Ordered

1. **Fix second waypoint** (HIGH) — resolve segmentArrived listener
2. **Verify three voices** (MEDIUM) — clean end-to-end test
3. **Push clean working baseline to GitHub**
4. **x3d.py refactor on branch** — `git checkout -b x3d-python-refactor`, master stays runnable
5. **Character Creator** — after refactor is stable (see below)

\---

## Next Refactor — x3d.py Server-Side X3D Generation

**Evaluated Day 6.** Recommendation: move X3D file generation from JavaScript string-building in composer to Python using `pip install x3d` in `mccf\_api.py`.

**Why:**

* MFString quoting automatic (eliminates class of bugs)
* Type validation at build time (bad values caught before X\_ITE sees them)
* ROUTE ordering enforced structurally by placing `x3d.ROUTE()` objects last in children list
* Cleaner, auditable code

**How:**

* New `/scene/x3d/build` endpoint accepts scene JSON, returns built/validated X3D
* Composer POSTs scene data as JSON; server builds X3D with x3d.py, saves to `static/x3d/`
* JavaScript `buildX3DString`, `buildInterpNodes`, `buildInterpRoutes`, `buildAX3D`, `buildZX3D` etc. become thin data-collection only
* `mccf\_x3d\_generator.py` (exists in repo history in deleted `mccf\_full/`) may be a useful reference

**Branch discipline:** refactor on `x3d-python-refactor`, merge to master only when end-to-end verified.

\---

## Future Feature — Cultivar Character Creator

**Concept:** Expand the agent field editor into a full character creator. The LLM is not a Swiss clock character — it is a live probabilistic agent. To maintain coherent identity during improvisation, it needs initialization geometry: not just an emotional state vector, but the narrative history that produced it.

**Theoretical basis:** See blog post — https://aiartistinprocess.blogspot.com/2026/05/mccf-backstory-as-initialization.html

The Salida incident (LLM objected to being called by a different name) demonstrates that even minimal identity initialization creates a weak attractor. The character creator strengthens that attractor by adding the causal history behind the emotional vector.

Backstory is not lore. It is a generative constraint system — it narrows the probability distribution of responses while preserving improvisational flexibility. This is what professional actors have known for decades. The character creator makes that technique available to authors composing MCCF scenes.

### Four Initialization Layers

**Layer 1 — Identity Anchors**

* Name, role, relation to other characters in scene
* First-person self-description: "I am The Steward. I have kept this garden for thirty years."
* This is the attractor that fired during the Salida incident

**Layer 2 — Formative History**

* 3-5 key events that shaped the emotional geometry — not biography, specific scenes
* Example: "I watched the grove flood in 1998 and could not stop it. Since then I do not trust plans."
* These justify the E/B/P/S initialization vector — the backstory and the math should agree

**Layer 3 — Behavioral Couplers**

* Trigger → response patterns: what destabilizes, what restores
* Attachment patterns: who they protect, who they distrust, why
* Linguistic signature: rhythm, vocabulary register, things they never say
* Example: "I use sarcasm as defense against betrayal, not for dominance"

**Layer 4 — Scene Context**

* What they know about the current situation
* What they want from this scene
* What they are concealing

### How It Assembles

All four layers collapse into a structured system prompt sent to Ollama at the start of recording. The E/B/P/S vector is the mathematical state; the system prompt is the narrative that justifies it. Both initialized together.

```
You are The Steward. \[Layer 1]
Your history: \[Layer 2]
You respond to pressure by: \[Layer 3]
In this scene: \[Layer 4]
Your current emotional state is: reserved, watchful, slightly hopeful.
Speak in short declarative sentences. Do not explain yourself unless asked twice.
```

### UI Changes

Expand the agent editor into tabs:

* **Field** — existing E/B/P/S sliders (unchanged)
* **Identity** — name, role, first-person self-description
* **History** — 3-5 formative event text fields (label: "A moment that shaped you")
* **Couplers** — trigger/response pairs, attachment declarations
* **Voice** — linguistic signature, things never said, speaking rhythm
* **Scene** — what they know, want, and conceal in this specific scene

### Schema

All character creator data serializes into the scene XML as a `<Cultivar>` block per agent:

```xml
<Cultivar name="The Steward" actor="ollama" voice="Microsoft Mark">
  <Identity>I am The Steward. I have kept this garden for thirty years.</Identity>
  <History>
    <Event>I watched the grove flood in 1998 and could not stop it.</Event>
    <Event>My predecessor left without explanation in 2003.</Event>
  </History>
  <Couplers>
    <Trigger stimulus="broken promises" response="withdrawal and silence"/>
    <Attachment target="Cindy" type="protective"/>
  </Couplers>
  <Voice signature="short declarative sentences" never="apology or self-explanation"/>
  <SceneContext want="to understand why they have returned" conceal="my fear that I failed"/>
  <EmotionalArc E="0.25" B="0.65" P="0.40" S="0.55"/>
</Cultivar>
```

### Stability Metrics (future)

To measure character coherence over time, arc-to-arc comparison data is needed:

* Identity consistency under perturbation
* Emotional recovery half-life
* Resistance to semantic drift
* Linguistic signature continuity
* Value and goal persistence

**Schema note:** Design the `<Cultivar>` block to support arc-to-arc comparison from the start. The character creator data must persist across sessions, not just within a single arc.

Cultivar initialization geometry

&#x20;   → emotional trajectory through scene

&#x20;   → gesture selection (H-Anim)

&#x20;   → path selection (zone attractor field)

&#x20;   → dialogue generation (LLM with character context)

&#x20;   → arc recording

&#x20;   → stability metrics across sessions

\---

## Working File Manifest

|File|Location|Status|
|-|-|-|
|mccf\_scene\_composer.html|static/|Day 6 — current|
|mccf\_x3d\_loader.html|static/|Day 6 — current|
|mccf\_api.py|repo root|Day 6 — current|
|mccf\_playback.py|repo root|unchanged|
|mccf\_constitutional.html|static/|V2 — do not touch|

\---

## Key Constraints — Never Change

* Avatar names late-bound: `safeId = name.replace(/\[^A-Za-z0-9\_]/g,'\_')`
* SAI: `avatarNode.translation = new X3D.SFVec3f(x, y, z)`
* `/voice/speak` → SSE stream, not JSON
* Files: HTML → static/, Python → repo root
* Constitutional navigator (mccf\_constitutional.html) is V2 — do not touch
* `applyArcCV` is confirmed working SAI path — BroadcastChannel mccf\_arc
* TTS: Browser Web Speech API only. ElevenLabs deferred to Big Demo
* Edge has richer voice library than Firefox — use Edge for TTS testing (but Edge has no F12 console — use Firefox for debugging)
* sceneConfig default: width=40, depth=40 meters
* Arc XML root carries `scene="scene\_name"` attribute
* ROUTEs MUST be last in X3D scene — enforced in buildX3DString and exportX3D

\---

## Coordinate System

Composer canvas: world meters = X3D scene units.  
Arc XML pos\_x/pos\_z are world meters, directly used in X3D SAI translation.  
Y hardcoded 0 — elevation grid deferred.

\---

## Dialogue XML — Three-Way Taxonomy

|Type|LLM Call|TTS|XML Element|Use|
|-|-|-|-|-|
|Question|Only if no authored Response follows|Yes|`<Question speaker="">`|Sent to Ollama only when blank|
|Response|No|Yes|`<Response speaker="">`|Scripted or Ollama reply|
|Statement|No|Yes|`<Statement speaker="">`|Monologue / internal / prayer|

Ollama only called for Questions with no authored Response immediately following.

\---

## Deferred (Post Big Demo)

* Elevation grid Y coordinate support
* H-Anim figure integration
* ElevenLabs TTS
* Follower pattern (multiple avatars, offset startTime)
* Gesture system
* Camera dynamics

\---

## Operation Order for Testing

1. `ollama serve` + `py mccf\_api.py`
2. Hard-reload composer and loader (Ctrl+Shift+R)
3. Load existing scene from Export tab dropdown
4. Verify agents, waypoints, paths loaded correctly
5. Export X3D → Send to Launcher (saves to `static/x3d/{scene\_name}.x3d`)
6. Record Scene Arc → select path → Record
7. After recording → Refresh in loader → select new arc and new X3D scene
8. Loader: voice checkbox ON → Play
9. Watch Firefox F12 console for:

   * `pbActivateX3DTimers: wired segmentArrived callback on Arrival\_Cindy`
   * OR: `pbActivateX3DTimers: addFieldCallback unavailable — using poll fallback`
   * `segmentArrived callback/poll: Arrival\_Cindy seg=1`
   * `pbReleaseDwell: released dwell for Cindy`
10. Watch X\_ITE editor console for:

    * `Arrival\_Cindy: arrived seg 1`
    * `Arrival\_Cindy: released dwell Dwell\_Cindy\_1`

\---

## State at End of Day 6

### Completed This Session

**X3D Named File Directory**

* `static/x3d/` replaces single stomped `static/mccf\_scene.x3d`
* `mccf\_api.py`: `/static/x3d/<filename>` serve route, `/scene/x3d/upload` saves as `{scene\_name}.x3d` using `X-Scene-Name` header, `/scene/x3d/list` returns newest-first list
* `mccf\_scene\_composer.html`: `sendToLauncher()` passes `X-Scene-Name` header, success toast shows actual filename
* `mccf\_x3d\_loader.html`: X3D scene dropdown above arc dropdown, `x3dLoadFiles()` / `x3dFileChanged()`, canvas `src` set dynamically

**ROUTE Ordering — Hard Rule Enforced**

* ROUTEs must be last in X3D scene — VRML2.0 rule, X\_ITE enforces it strictly
* `buildInterp` split into `buildInterpNodes(path)` and `buildInterpRoutes(path)`
* `buildX3DString()` and `exportX3D()` both emit: all nodes → MCCFMaster Script → ROUTEs last
* Comment marker: `<!-- ═══ ROUTEs — must follow all DEF nodes ═══ -->`

**MFString Quoting Fixed**

* `NavigationInfo type`, FontStyle `family`/`justify`, Text `string` all use proper `'"VALUE"'` quoting
* Eliminates all X\_ITE XML Parser MFString warnings

**Ollama Conditional — Only Fills Blank Responses**

* `\_sceneArcAdvance()` now looks ahead: if a Question is immediately followed by a non-blank authored Response, records it as-is and skips Ollama
* Only Questions with no authored response following them go to Ollama
* Authored `Statement` lines pass through unchanged as before

**Voice Map Cleanup**

* `pb-voice-select` dropdown removed from loader entirely
* `pbSpeak()` uses `\_pbVoices\[0]` fallback (legacy single-line path only)
* `pbLoadVoices()` still populates `\_pbVoices` silently, invalidates `\_pbSceneVoiceMap` on reload
* `pbVoiceChanged()` simplified — no dropdown to show/hide

**`actor` Field Fixed in Scene XML Export**

* Was hardcoded `actor="ollama"` — now reads `run-adapter` dropdown value at export time

**`pb-voice-select` and Record Pace Field Removed**

* Pace field removed from Record tab UI — was redundant with per-waypoint pace in scene XML
* `\_sceneArcAdvance` step interval hardcoded to 2s

**`applyHotHouseData` agentMap Fixed**

* Was hardcoded `'The Steward' → 'Steward'` (old short-name convention)
* Now dynamically built from data keys using `safeId` regex — matches composer output exactly

**`qaLines` Field Name Bug Fixed**

* Loader was reading `wp.qa\_lines` (snake\_case) but server serializes as `wp.qaLines` (camelCase)
* Fixed to `wp.qaLines||wp.qa\_lines` — was silencing all multi-line waypoint dialogue

**`static/mccf\_full/` Cleanup**

* Accidentally committed codebase snapshot removed from repo

\---

## Active Bug — HIGH PRIORITY

### Second Waypoint Speech/Dwell Not Firing

**Symptom:** 3-waypoint scene plays waypoints 1 and 3, skips 2. Avatar travels through temple without pausing or speaking.

**Root cause identified:** `Arrival\_` Script fires `segmentArrived` outputOnly field in X3D, but the loader has no reliable listener. The server never advances its step counter for segment 2, so `pbUpdateDisplay` never fires TTS, so `pbReleaseDwell` is never called, so `Dwell\_Cindy\_1` never starts, so `Timer\_Cindy\_2` never fires.

**Attempted fix (Day 6, not yet working):**
`pbActivateX3DTimers` now tries to register `addFieldCallback` on `Arrival\_{agent}.segmentArrived` via `arrNode.getField('segmentArrived').addFieldCallback(name, fn)`. Falls back to 200ms polling if `addFieldCallback` unavailable. Neither confirmed working yet — session ended before verification.

**X\_ITE SAI uncertainty:** It is not confirmed whether X\_ITE supports `addFieldCallback` on `outputOnly` Script fields via the external SAI. The poll fallback may be the only reliable path.

**Diagnosis approach for next session:**

1. Deploy current loader, check Firefox F12 console for:

   * `pbActivateX3DTimers: wired segmentArrived callback on Arrival\_Cindy` — callback path
   * `pbActivateX3DTimers: addFieldCallback unavailable for Arrival\_Cindy — using poll fallback` — poll path
   * `segmentArrived callback: Arrival\_Cindy seg=1` or `segmentArrived poll: Arrival\_Cindy seg=1`
2. Also check X\_ITE editor console for `Arrival\_Cindy: arrived seg 1` — confirms X3D side is firing
3. If neither path fires, consider alternative: have `Arrival\_` Script use a different mechanism to signal the loader (e.g. modify a shared scene node value that the loader polls via SAI)

**Alternative architecture to consider:**
Rather than relying on SAI field callbacks, the loader could poll `Arrival\_{agent}` node's `segmentArrived` value directly on a fast interval (already partially implemented in fallback). Or: the `Arrival\_` script could write to a well-known scene node (e.g. a `StringSensor` or `IntegerTrigger`) that is easier to observe.

\---

## Known Issues — Priority Order

1. **Second waypoint dwell/speech** (HIGH) — see above
2. **Three voices clean verification** (MEDIUM) — needs working end-to-end first
3. **Waypoint path reorder UI** (MEDIUM) — up/down arrows on path waypoint list
4. **X3D export → server save** (LOW) — `exportX3D()` still downloads to browser; should POST to `/scene/x3d/upload` same as Send to Launcher
5. **`static/x3d/` not in git** (LOW) — directory created by API on first export; add `.gitkeep` if desired

\---

## Architecture — Confirmed Working

```
Play → SAI sets Timer\_{agent}\_1.startTime = browser.currentTime
     → Avatar travels segment 1
     → Timer\_1.cycleTime → ROUTE → Arrival\_{agent}.arrived
     → Arrival\_ script fires segmentArrived (outputOnly)
     → \[MISSING LINK] loader detects segmentArrived → calls pbStep()
     → Server advances step → pbUpdateDisplay fires TTS
     → TTS completes → pbReleaseDwell(agentSafeName)
     → SAI sets Arrival\_.releaseDwell = true
     → Arrival\_ script starts Dwell\_{agent}\_1
     → Dwell\_1.cycleTime → ROUTE → Timer\_{agent}\_2.startTime
     → Repeat for each segment
```

**X3D Build Order (enforced, never change):**

```
ProtoDeclares
NavigationInfo / Background / Lights / Viewpoints
Ground / Grid
Zones
Avatars
Animation nodes — all agents (buildInterpNodes: Interp, Timer, Dwell, Arrival\_, Kill\_)
MCCFMaster Script
══ ROUTEs — all agents (buildInterpRoutes) — ABSOLUTELY LAST ══
</Scene>
</X3D>
```

\---

## Next Phase — x3d.py Server-Side X3D Generation

**Evaluated Day 6.** Recommendation: move X3D file generation from JavaScript string-building in composer to Python using `pip install x3d` in `mccf\_api.py`.

**Why:**

* MFString quoting automatic (eliminates class of bugs)
* Type validation at build time (bad values caught before X\_ITE sees them)
* ROUTE ordering enforced structurally by placing `x3d.ROUTE()` objects last in children list
* Cleaner, auditable code

**How:**

* New `/scene/x3d/build` endpoint accepts scene JSON, returns built/validated X3D
* Composer POSTs scene data as JSON; server builds X3D with x3d.py, saves to `static/x3d/`
* JavaScript `buildX3DString`, `buildInterpNodes`, `buildInterpRoutes`, `buildAX3D`, `buildZX3D` etc. become thin data-collection only
* `mccf\_x3d\_generator.py` (exists in repo history in deleted `mccf\_full/`) may be a useful reference

**This is a refactor session — scope appropriately.**

\---

## Working File Manifest

|File|Location|Status|
|-|-|-|
|mccf\_scene\_composer.html|static/|Day 6 — current|
|mccf\_x3d\_loader.html|static/|Day 6 — current|
|mccf\_api.py|repo root|Day 6 — current|
|mccf\_playback.py|repo root|unchanged|
|mccf\_constitutional.html|static/|V2 — do not touch|

\---

## Key Constraints — Never Change

* Avatar names late-bound: `safeId = name.replace(/\[^A-Za-z0-9\_]/g,'\_')`
* SAI: `avatarNode.translation = new X3D.SFVec3f(x, y, z)`
* `/voice/speak` → SSE stream, not JSON
* Files: HTML → static/, Python → repo root
* Constitutional navigator (mccf\_constitutional.html) is V2 — do not touch
* `applyArcCV` is confirmed working SAI path — BroadcastChannel mccf\_arc
* TTS: Browser Web Speech API only. ElevenLabs deferred to Big Demo
* Edge has richer voice library than Firefox — use Edge for TTS testing (but Edge has no F12 console — use Firefox for debugging)
* sceneConfig default: width=40, depth=40 meters
* Arc XML root carries `scene="scene\_name"` attribute
* ROUTEs MUST be last in X3D scene — enforced in buildX3DString and exportX3D

\---

## Coordinate System

Composer canvas: world meters = X3D scene units.  
Arc XML pos\_x/pos\_z are world meters, directly used in X3D SAI translation.  
Y hardcoded 0 — elevation grid deferred.

\---

## Dialogue XML — Three-Way Taxonomy

|Type|LLM Call|TTS|XML Element|Use|
|-|-|-|-|-|
|Question|Only if no authored Response follows|Yes|`<Question speaker="">`|Sent to Ollama only when blank|
|Response|No|Yes|`<Response speaker="">`|Scripted or Ollama reply|
|Statement|No|Yes|`<Statement speaker="">`|Monologue / internal / prayer|

Ollama only called for Questions with no authored Response immediately following.

\---

## Deferred (Post Big Demo)

* Elevation grid Y coordinate support
* H-Anim figure integration
* ElevenLabs TTS
* Follower pattern (multiple avatars, offset startTime)
* Gesture system
* Camera dynamics
* LLM as Agent (actor="ollama" on any agent)
* Per-agent Ollama persona (agent name → system prompt identity)
* W3DC x3d.py full refactor (evaluated Day 6 — ready to implement)

\---

## Operation Order for Testing

1. `ollama serve` + `py mccf\_api.py`
2. Hard-reload composer and loader (Ctrl+Shift+R)
3. Load existing scene from Export tab dropdown
4. Verify agents, waypoints, paths loaded correctly
5. Export X3D → Send to Launcher (saves to `static/x3d/{scene\_name}.x3d`)
6. Record Scene Arc → select path → Record
7. After recording → Refresh in loader → select new arc and new X3D scene
8. Loader: voice checkbox ON → Play
9. Watch Firefox F12 console for:

   * `pbActivateX3DTimers: wired segmentArrived callback on Arrival\_Cindy`
   * OR: `pbActivateX3DTimers: addFieldCallback unavailable — using poll fallback`
   * `segmentArrived callback/poll: Arrival\_Cindy seg=1`
   * `pbReleaseDwell: released dwell for Cindy`
10. Watch X\_ITE editor console for:

    * `Arrival\_Cindy: arrived seg 1`
    * `Arrival\_Cindy: released dwell Dwell\_Cindy\_1`

