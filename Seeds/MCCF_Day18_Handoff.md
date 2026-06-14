# MCCF Session Seed — V4 "The New York Rocket" — Day 18 Handoff
Repo: https://github.com/artistinprocess/mccf
Last commit basis: Day 17b

---

## What Was Accomplished Day 18

### Architecture Change — Self-Contained Arrival Scripts
**Problem solved:** Shared `MCCFMaster.startAgent` SFString field caused race condition
when two agents fired simultaneously — second assignment overwrote first, Steward never moved.

**Solution:** Each `Arrival_X` script now owns its full movement chain:
- `startFromLoader` (SFTime inputOnly) — JS entry point replacing MCCFMaster.startAgent
- `advanceSeg` (SFInt32 inputOnly) — JS sends completed seg number; Arrival starts next timer
- No shared SFString bus. N-agent safe.
- MCCFMaster retained for future cross-agent/zone/network signals only.

**Files changed:**
- `garden_001.x3d` — new Arrival script architecture (deployed to static/x3d/)
- `mccf_x3d_loader.html` — new pbReleaseDwell, _pbAdvanceSeg, speech lock, session routing

---

## Current State — What Works

✅ Both Cindy and The Steward move simultaneously without collision
✅ Both move smoothly (interpolation working — time passed via SFTime)
✅ Voice fires correctly (Edge 48khz audio setting required — MS hardware issue)
✅ Dialogue displays in panel
✅ Chorus fires when both agents complete (allDone= true)
✅ Per-session step routing (each agent steps its own server session)
✅ Global speech lock (_pbSpeechLock) prevents voice interleaving
✅ Display appends per-cultivar dialogue in pbPlayAll mode

---

## Current State — What Still Needs Fixing

### 1. Reset does not work for replay
**Symptom:** After Reset + Play All, log cuts off at `pbPlayAll: called` — fetch to
`/arc/playback/start/all` hangs or returns stale data.

**Root cause:** The last fix added `/arc/playback/reset` before `/arc/playback/start/all`
in pbPlayAll, but this may not be enough if server sessions are in an error state.
Also: `_pbResetViaKillScript` derives agent names from `_x3dTimerActive` which is cleared
before Kill scripts fire — this was fixed but may have regressed.

**What to check:**
- After arc completes, does `/arc/playback/reset` return 200?
- Does `/arc/playback/start/all` after reset return fresh sessions?
- Add console log of the reset response in pbPlayAll before start/all

### 2. Zone voices not firing
**Symptom:** `_fireZoneCommand: no scene XML command — using default reflect for Cindy OnEnter pool`
should appear but zone Ollama calls aren't audible.

**Root cause:** `_waypointZoneMap` populates correctly but WP1 zone fire happens
before zone data is fully loaded on first parse. Default command fallback was added
but needs verification that `/zone/command` call is completing and TTS is playing response.

### 3. Voice ordering
**Status:** Global `_pbSpeechLock` added — whichever agent speaks first holds the lock,
second agent queues. Works correctly but means dialogues are fully sequential not overlapping.
This is the right behavior for authored dramatic scenes. No further action needed unless
author wants configurable overlap.

---

## Architecture Invariants (Never Change)
```
constitutional_cv (phi) — written ONLY by arc/record
expressive_cv (eps)     — written ONLY by couplers
mccf_couplers.py        — owns all coupler math
field_tick()            — compute ALL deltas then apply ALL
observed_cv             — phi + eps clamped [0,1]
```

## Persistent Technical Rules
```
SAI: avatarNode.translation = new X3D.SFVec3f(x, y, z)
/voice/speak -> SSE stream not JSON
Files: HTML -> static/, Python -> repo root
ROUTEs MUST be last in X3D scene
GitHub branch is master not main
All Timers/Dwells: enabled="false" in X3D
isActive=FALSE is arrival signal NOT cycleTime
startFromLoader (SFTime) fired by JS with performance.now()/1000 + 0.1
advanceSeg (SFInt32) fired by _pbAdvanceSeg after dwell expires
Arrival scripts are self-contained — no MCCFMaster for movement
_pbSpeechLock / _pbSpeechQueue — global speech serializer
_pbCultivarSessionMap — {safeName: session_id} set by pbPlayAll
_pbExpectedAgents — count for allDone detection
_pbLastArcFiles — for Chorus firing
pbReset and pbStop send Content-Type:application/json body:'{}' (415 fix)
_pbStepInFlight is dict {sessionId: bool}
_pbLastSpoken/_pbLastStepKey/_pbSpeakToken are dicts keyed by cultivar safe name
Zone commands serialised via _zoneCommandQueue
pbSpeakQALines(qaLines, onComplete, cultivarKey) — cultivarKey required
_pbArcComplete is dict {safeName: bool} — NOT a global bool
```

## X3D Arrival Script Template (for new agents)
```xml
<!-- Animation nodes: AgentName — segments=N -->
<PositionInterpolator DEF="Interp_AgentName_1" key="0 1" keyValue="x1 y1 z1 x2 y2 z2"/>
<TimeSensor DEF="Timer_AgentName_1" cycleInterval="T" loop="false" enabled="false"/>
<TimeSensor DEF="Dwell_AgentName_1" cycleInterval="2.0" loop="false" enabled="false"/>

<Script DEF="Arrival_AgentName" directOutput="true" mustEvaluate="true">
  <field name="startFromLoader" type="SFTime"  accessType="inputOnly"/>
  <field name="arrived"         type="SFBool"  accessType="inputOnly"/>
  <field name="advanceSeg"      type="SFInt32" accessType="inputOnly"/>
  <field name="resetSeg"        type="SFBool"  accessType="inputOnly"/>
  <field name="segmentArrived"  type="SFInt32" accessType="outputOnly"/>
  <![CDATA[ecmascript:
  var _seg=0, _wasActive=false;
  var _timerIds=['Timer_AgentName_1'];   // add more for multi-segment paths
  var _dwellIds=['Dwell_AgentName_1'];
  var _maxSeg=1;                          // = number of segments
  var _agentName='AgentName';
  function initialize(){ Browser.println('Arrival_'+_agentName+': initialized, maxSeg='+_maxSeg); }
  function resetSeg(val,time){ if(!val)return; _seg=0; _wasActive=false; }
  function startFromLoader(val,time){
    if(val<=0)return;
    try{ var t=Browser.currentScene.getNamedNode(_timerIds[0]);
      if(t){t.startTime=val;t.enabled=true;Browser.println('Arrival_'+_agentName+': Timer_1 at '+val);}
    }catch(e){}
  }
  function arrived(val,time){
    if(val){_wasActive=true;return;}
    if(!_wasActive)return;
    _wasActive=false; _seg++; segmentArrived=_seg;
    Browser.println('Arrival_'+_agentName+': arrived seg '+_seg);
  }
  function advanceSeg(completedSeg,time){
    var nextIdx=completedSeg;
    if(nextIdx>=_maxSeg){ Browser.println('Arrival_'+_agentName+': arc complete'); return; }
    var tNow=(time&&time>0)?time:Browser.currentTime;
    try{ var t=Browser.currentScene.getNamedNode(_timerIds[nextIdx]);
      if(t){t.startTime=tNow;t.enabled=true;}
    }catch(e){}
  }
  ]]>
</Script>

<!-- ROUTEs for AgentName — MUST be in ROUTEs section at end of scene -->
<ROUTE fromNode="Timer_AgentName_1" fromField="fraction_changed" toNode="Interp_AgentName_1" toField="set_fraction"/>
<ROUTE fromNode="Interp_AgentName_1" fromField="value_changed" toNode="Avatar_AgentName" toField="translation"/>
<ROUTE fromNode="Timer_AgentName_1" fromField="isActive" toNode="Arrival_AgentName" toField="arrived"/>
```

## Priority Queue for Next Session
1. **Fix reset/replay** — debug why `/arc/playback/start/all` hangs after reset
2. **All-complete Chorus** — verify Chorus TTS fires after allDone=true (was firing in last log)
3. **Zone voices** — verify Ollama zone command response plays via TTS
4. **Relational Dynamics Extension Session 1** — Attentional Filter

## Known Non-Issues (Do Not Fix)
- `VP_Overview not found` — viewpoint not in current scene, harmless
- `ambient/sync 500` — ambient API not implemented, harmless
- `lighting/scalars 404` — lighting API not implemented, harmless
- `Jin.png not allowed` — local file path in scene, harmless
- `Tracking Prevention blocked` — Edge CDN storage, X_ITE still loads fine
- MS audio 48khz reset — hardware/OS issue, not code

## File Versions
| File | Status |
|------|--------|
| garden_001.x3d | Day 18 — self-contained Arrival scripts |
| mccf_x3d_loader.html | Day 18 — speech lock, session routing, Chorus |
| mccf_playback.py | Day 17 — unchanged |
| mccf_api.py | Day 17 — unchanged |
