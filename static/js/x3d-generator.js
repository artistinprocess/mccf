// MCCF X3D Generator \u2014 Day 79, V5 Tasklist Phase 4 task 8.
//
// Track/Step/Cue authored data (Timeline/Dialogue editor's state.actors/
// state.zones, same shape the Composer<->Timeline bridge already moves) ->
// a real, playable X3D fragment: one scene-level dispatcher Script node,
// a master-clock TimeSensor, and the ROUTEs/sensors that feed it. Per the
// Tasklist's own Phase 4 architecture note: compiles to native X3D (path
// (a) of the two forks identified there), using dispatcher.js as the
// verified spec \u2014 literally embedded, not re-derived by hand.
//
// Why the dispatcher core is embedded verbatim, not reimplemented: dispatcher.js
// is ES6 (class syntax, const, arrow functions, Set). X3D ECMAScript SAI
// environments are typically the browser's own real JS engine (X_ITE 11.6.0
// confirmed using setInterval in the existing SoundFader Script precedent,
// so modern syntax may well already work) \u2014 but rather than assume that,
// this embeds a Babel-transpiled ES5 build of the real dispatcher.js, with
// exactly one behavior-preserving edit (Set -> plain object map,
// dispatcher.js's only true ES6-runtime dependency beyond syntax;
// Object.assign/Array.find/Object.values are safe on any realistic target).
// Verified byte-for-byte behaviorally identical to the original via a real
// equivalence test (every verb, both trigger families, Welder displacement,
// all three collision policies, field locks, blend arbitration) before being
// trusted here. If dispatcher.js changes, regenerate DISPATCHER_CORE_ES5 the
// same way (Babel + the one Set edit + rerun the equivalence test) rather
// than hand-editing the embedded string.
//
// What this generator actually does, honestly scoped:
// REAL, wired, tested: scene-start / declared (via TimeSensor tick) / sensed
// triggers; Welder displacement, interrupt/wait/overlap collision policies,
// field-lock priority, blend arbitration (all inherited from the embedded
// core); camera-cut execution for a named authored Viewpoint and a placed
// FreeCamera (mccf_x3d_loader.html's _bindNamedViewpoint/_bindFreeCamera
// pattern, reused not reinvented); GESTURE execution via a real, proven-
// elsewhere mechanism (mccf_x3d_loader.html's pbActivateX3DTimers:
// getImportedNode("<TimerBase>_<agentName>") then .enabled = true) —
// flagged, not fully confirmed: that pattern has only ever been proven
// callable from the outer page's own browser API, never from inside a
// Script node's own Browser.currentScene, so this is real reuse of a
// proven mechanism with one genuinely unverified assumption, not a fully
// proven path (wrapped in try/catch with a diagnostic saying exactly
// that if it fails); also needs step._clipTimerDEF, which nothing in the
// Timeline authoring UI sets yet either (same gap as path, below);
// ZONE triggers (Day 79 addition — real
// position polling of each Actor's own Transform against real zone
// geometry, edge-triggered, see actorDefName/ZONE_CHECK_JS below — X3D's
// own ProximitySensor only ever reports the bound viewpoint, never an
// arbitrary Actor, so this was a real gap, not just missing wiring).
// STUBBED on purpose (a clear Browser.println diagnostic, never a crash):
// TOUCH triggers — unlike zones, "touching" implies a specific target
// object, and no object-target data model (props, interactive items)
// exists anywhere in this codebase yet for a touch trigger to reference.
// Not a smaller version of the zone gap; a different, still-open one.
// path field-write execution beyond the dispatcher's own abstract
// fieldValues bookkeeping (path-recorder.js's buildRecordedPathX3D can now
// generate real playback nodes for a RecordedPath, Day 79 addition, but
// nothing here calls it yet — no authoring UI exists for "which
// RecordedPath does this actor play", so a path-track step has nothing to
// reference); dialogue execution entirely (no audio/TTS playback
// infrastructure exists anywhere in this codebase to hook into — a
// separate, larger project, not a quick splice); camera cameraType
// orbit/pov/dolly/track; the camera release/stop
// verb gap flagged in MCCF_Actor_Architecture_Design_v0.2.md §7/§12 and
// the Tasklist's own Phase 4 note — a cut still just displaces whatever
// was bound before it.

(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.MCCFX3DGenerator = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {

  let MCCFActorAdapter;
  if (typeof module !== 'undefined' && module.exports) {
    MCCFActorAdapter = require('./actor-adapter.js');
  } else if (typeof self !== 'undefined' && self.MCCFActorAdapter) {
    MCCFActorAdapter = self.MCCFActorAdapter;
  } else {
    throw new Error('MCCFX3DGenerator requires MCCFActorAdapter (actor-adapter.js) to be loaded first.');
  }

  // Verified ES5 build of dispatcher.js \u2014 see file header.
  const DISPATCHER_CORE_ES5 = "function _typeof(o) { \"@babel/helpers - typeof\"; return _typeof = \"function\" == typeof Symbol && \"symbol\" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && \"function\" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? \"symbol\" : typeof o; }, _typeof(o); }\nfunction _classCallCheck(a, n) { if (!(a instanceof n)) throw new TypeError(\"Cannot call a class as a function\"); }\nfunction _defineProperties(e, r) { for (var t = 0; t < r.length; t++) { var o = r[t]; o.enumerable = o.enumerable || !1, o.configurable = !0, \"value\" in o && (o.writable = !0), Object.defineProperty(e, _toPropertyKey(o.key), o); } }\nfunction _createClass(e, r, t) { return r && _defineProperties(e.prototype, r), t && _defineProperties(e, t), Object.defineProperty(e, \"prototype\", { writable: !1 }), e; }\nfunction _toPropertyKey(t) { var i = _toPrimitive(t, \"string\"); return \"symbol\" == _typeof(i) ? i : i + \"\"; }\nfunction _toPrimitive(t, r) { if (\"object\" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || \"default\"); if (\"object\" != _typeof(i)) return i; throw new TypeError(\"@@toPrimitive must return a primitive value.\"); } return (\"string\" === r ? String : Number)(t); }\n// MCCF scene-level dispatcher \u2014 Day 72, build schedule item 3.\n// Day 73: added the arc-complete trigger (priority queue item 3 \u2014 the\n// Chorus redesign decided in the Day 72 seed doc \u00a75.2). Fires through the\n// same collision-policy branch as `declared` steps (interrupt/wait/overlap\n// via _fireWithCollisionPolicy, extracted from what was previously\n// _fireDeclared's inline body \u2014 no behavior change for declared/cue firing,\n// just a shared helper so arc-complete doesn't duplicate that logic).\n// Implements design doc \u00a78 (scene-level coordination) end to end: the five\n// verbs (\u00a73), both trigger families (\u00a73.1), the Welder default arbitration\n// (\u00a75.1, generalized to any track incl. camera cuts per \u00a77), track-vs-affect\n// arbitration from each Actor's field map (\u00a75.2), declared-vs-running\n// collision policy (\u00a75.4), and declared multi-Actor cues (\u00a78.1).\n//\n// Also implements the decision build-schedule item 4a flagged as open: two\n// simultaneous affect-writers on the same field (\u00a74.2's unresolved case,\n// concretely the Ground Tremor fog conflict, \u00a79). Decision made HERE, on\n// record, not silently: priority order \u2014 a declared write holds an\n// exclusive lock on the field for the duration of its step; continuous\n// (non-declared) affect writes are refused while that lock is held, and\n// resume being honored once the declared step's `arrived` fires and\n// releases the lock. This was the build-schedule's recommended default\n// (matches \u00a75.4's interrupt/wait/overlap precedent: a scripted beat is more\n// deliberate than an ambient coupling) \u2014 recorded here as the actual policy,\n// not just a recommendation, since item 3 can't pass its own Ground Tremor\n// test without it being decided.\n//\n// Also implements item 4b: the two named `blend` functions (walkPace,\n// swingSpeed), both as a recorded-value \u00d7 multiplier form, per their worked\n// manifests in field-map/worked-manifests.js.\n//\n// No X3D emission here and no wiring to mccf_api.py \u2014 this is the\n// architecture-level piece the build schedule called for; it runs against\n// stub Actors (field map + track/step defs), not a real scene file, same as\n// the Day 71 prototypes it eventually needs to plug into (item 5).\n\n// Day 75: wrapped in a UMD-style IIFE, same pattern field-map.js and\n// timeline-xml.js already use. Day 74's browser-export fix only patched\n// the bare `module.exports` line below (the ReferenceError-in-browser\n// problem) but left VERBS/TRIGGER_TYPES/COLLISION_POLICIES/BLEND_FUNCTIONS/\n// DispatchError/Dispatcher all declared at the file's top level. Loaded via\n// <script src=\"dispatcher.js\"> that way, `const VERBS` becomes a global\n// lexical binding \u2014 and the Timeline prototype's own inline script\n// separately declares its own top-level `const VERBS` (a UI badge-styling\n// object, unrelated shape) for its own purposes. Two top-level `const\n// VERBS` declarations on one page is a SyntaxError at parse time, which\n// silently kills the *entire* inline script block \u2014 no render, no button\n// wiring, nothing runs. Found by an actual jsdom load-and-click of the\n// real file (Day 75 browser-equivalent test), not by code review; the\n// Day 74 Node `vm` check didn't catch it because it extracted and ran the\n// inline script in isolation rather than alongside the real script-src\n// files the way a real page load does. Fixed by containing everything\n// this file declares inside one function scope; only MCCFDispatcher\n// reaches the outer (window/global) scope, exactly like field-map.js.\n(function (root, factory) {\n  var api = factory();\n  if (typeof module !== 'undefined' && module.exports) {\n    module.exports = api;\n  } else {\n    root.MCCFDispatcher = api;\n  }\n})(typeof self !== 'undefined' ? self : this, function () {\n  var VERBS = ['start', 'stop', 'arrived', 'blocked', 'set'];\n  var TRIGGER_TYPES = ['scene-start', 'touch', 'zone', 'sensed', 'declared', 'arc-complete'];\n  var COLLISION_POLICIES = ['interrupt', 'wait', 'overlap'];\n\n  // Field-type-specific blend functions (item 4b). Deliberately not a general\n  // mechanism \u2014 only these two fields have a concrete shape decided anywhere\n  // in the source docs (both multiplier form, per their worked manifests).\n  var BLEND_FUNCTIONS = {\n    walkPace: function walkPace(recorded, affectMultiplier) {\n      return recorded * affectMultiplier;\n    },\n    swingSpeed: function swingSpeed(recorded, affectMultiplier) {\n      return recorded * affectMultiplier;\n    }\n  };\n  function DispatchError(message) {\n    var err = Error.call(this, message);\n    this.name = 'DispatchError';\n    this.message = err.message;\n    this.stack = err.stack;\n  }\n  DispatchError.prototype = Object.create(Error.prototype);\n  DispatchError.prototype.constructor = DispatchError;\n  var Dispatcher = /*#__PURE__*/function () {\n    function Dispatcher() {\n      _classCallCheck(this, Dispatcher);\n      this.actors = {}; // actorId -> Actor\n      this.steps = {}; // stepId -> step def (as registered)\n      this.clock = 0;\n      this._firedDeclared = {}; // Day 79 generator note: plain object map, not Set\n      this._waitQueues = {}; // \"actorId:trackId\" -> [stepId,...] pending 'wait'-policy declared steps\n      this.eventLog = []; // {t, verb, actorId, trackId, stepId, detail}\n    }\n    return _createClass(Dispatcher, [{\n      key: \"_log\",\n      value: function _log(entry) {\n        this.eventLog.push(Object.assign({\n          t: this.clock\n        }, entry));\n      }\n\n      // \u2500\u2500 registration \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n      // Same identity discipline as build-schedule item 1: reject a duplicate\n      // id outright rather than silently overwrite. Actor ids, track ids\n      // (scoped to their Actor), and step ids (scoped to the whole scene, since\n      // `sensed` triggers reference step ids scene-wide per design doc \u00a78) all\n      // go through this.\n    }, {\n      key: \"registerActor\",\n      value: function registerActor(actorId, fieldMap, trackDefs) {\n        if (this.actors[actorId]) {\n          throw new DispatchError(\"registerActor: \\\"\".concat(actorId, \"\\\" already registered\"));\n        }\n        if (!fieldMap || !Array.isArray(fieldMap.fields)) {\n          throw new DispatchError(\"registerActor: \\\"\".concat(actorId, \"\\\" needs a field map (even an empty one \\u2014 \\xA74.1)\"));\n        }\n        var tracks = {};\n        Object.keys(trackDefs || {}).forEach(function (trackId) {\n          tracks[trackId] = {\n            kind: trackDefs[trackId].kind,\n            activeStepId: null\n          };\n        });\n        this.actors[actorId] = {\n          id: actorId,\n          fieldMap: fieldMap,\n          tracks: tracks,\n          fieldValues: {},\n          fieldLock: {} // fieldName -> { priority: 'declared', holderStepId } while a declared write holds it\n        };\n        return this.actors[actorId];\n      }\n    }, {\n      key: \"addStep\",\n      value: function addStep(step) {\n        // step: { id, actorId, trackId, trigger: {type, ...}, duration: {certainty, seconds?},\n        //         onCollision?, fieldWrite?: {field, value, priority}, cueName? }\n        if (this.steps[step.id]) {\n          throw new DispatchError(\"addStep: step id \\\"\".concat(step.id, \"\\\" already exists \\u2014 step ids are scene-wide unique (design doc \\xA78)\"));\n        }\n        if (!this.actors[step.actorId]) {\n          throw new DispatchError(\"addStep: unknown actor \\\"\".concat(step.actorId, \"\\\" for step \\\"\").concat(step.id, \"\\\"\"));\n        }\n        var actor = this.actors[step.actorId];\n        if (step.trackId && !actor.tracks[step.trackId]) {\n          throw new DispatchError(\"addStep: actor \\\"\".concat(step.actorId, \"\\\" has no track \\\"\").concat(step.trackId, \"\\\" for step \\\"\").concat(step.id, \"\\\"\"));\n        }\n        if (!step.trigger || !TRIGGER_TYPES.includes(step.trigger.type)) {\n          throw new DispatchError(\"addStep: step \\\"\".concat(step.id, \"\\\" has an invalid trigger type\"));\n        }\n        if (step.trigger.type === 'declared' && typeof step.trigger.time !== 'number') {\n          throw new DispatchError(\"addStep: declared trigger on \\\"\".concat(step.id, \"\\\" needs a numeric time\"));\n        }\n        if (step.trigger.type === 'sensed' && !step.trigger.stepId) {\n          throw new DispatchError(\"addStep: sensed trigger on \\\"\".concat(step.id, \"\\\" needs a stepId to chain off\"));\n        }\n        if (step.trigger.type === 'arc-complete' && step.trigger.zone !== undefined && typeof step.trigger.zone !== 'string') {\n          throw new DispatchError(\"addStep: arc-complete trigger on \\\"\".concat(step.id, \"\\\" has a non-string zone \\u2014 omit it entirely for the scene-wide (bare) form\"));\n        }\n        if (!step.duration || !['fixed', 'estimate'].includes(step.duration.certainty)) {\n          throw new DispatchError(\"addStep: step \\\"\".concat(step.id, \"\\\" needs duration.certainty (fixed|estimate) \\u2014 \\xA73.2\"));\n        }\n        if (step.onCollision && !COLLISION_POLICIES.includes(step.onCollision)) {\n          throw new DispatchError(\"addStep: step \\\"\".concat(step.id, \"\\\" has an invalid onCollision policy\"));\n        }\n        this.steps[step.id] = step;\n        return step;\n      }\n\n      // \u2500\u2500 the five verbs \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n      // start(): the generic entry point for actually beginning a step. Applies\n      // the Welder default (\u00a75.1) \u2014 starting a new step on a track displaces\n      // whatever's currently active on that track, generalized from gestures to\n      // every track kind, camera cuts included (\u00a77), with no special-casing.\n    }, {\n      key: \"start\",\n      value: function start(stepId) {\n        var step = this.steps[stepId];\n        if (!step) throw new DispatchError(\"start: unknown step \\\"\".concat(stepId, \"\\\"\"));\n        var actor = this.actors[step.actorId];\n        if (step.trackId) {\n          var track = actor.tracks[step.trackId];\n          if (track.activeStepId && track.activeStepId !== stepId) {\n            this.stop(track.activeStepId); // Welder displacement \u2014 not an 'arrived', it didn't finish on its own\n          }\n          track.activeStepId = stepId;\n        }\n        this._log({\n          verb: 'start',\n          actorId: step.actorId,\n          trackId: step.trackId,\n          stepId: stepId\n        });\n        if (step.fieldWrite) {\n          this.set(step.actorId, step.fieldWrite.field, step.fieldWrite.value, {\n            priority: step.fieldWrite.priority || 'continuous',\n            holderStepId: stepId\n          });\n        }\n        return true;\n      }\n    }, {\n      key: \"stop\",\n      value: function stop(stepId) {\n        var step = this.steps[stepId];\n        if (!step) throw new DispatchError(\"stop: unknown step \\\"\".concat(stepId, \"\\\"\"));\n        var actor = this.actors[step.actorId];\n        if (step.trackId && actor.tracks[step.trackId].activeStepId === stepId) {\n          actor.tracks[step.trackId].activeStepId = null;\n        }\n        this._releaseFieldLock(step.actorId, stepId);\n        this._log({\n          verb: 'stop',\n          actorId: step.actorId,\n          trackId: step.trackId,\n          stepId: stepId\n        });\n      }\n\n      // arrived(): pushed BY an Actor when a step completes on its own. Chains\n      // any `sensed` steps waiting on this step id (\u00a75.3 \u2014 push, not pull), and\n      // releases whatever this step held (track slot, field lock) before\n      // checking the wait queue for anything queued behind it (\u00a75.4).\n    }, {\n      key: \"arrived\",\n      value: function arrived(stepId) {\n        var _this = this;\n        var step = this.steps[stepId];\n        if (!step) throw new DispatchError(\"arrived: unknown step \\\"\".concat(stepId, \"\\\"\"));\n        var actor = this.actors[step.actorId];\n        if (step.trackId && actor.tracks[step.trackId].activeStepId === stepId) {\n          actor.tracks[step.trackId].activeStepId = null;\n        }\n        this._releaseFieldLock(step.actorId, stepId);\n        this._log({\n          verb: 'arrived',\n          actorId: step.actorId,\n          trackId: step.trackId,\n          stepId: stepId\n        });\n\n        // sensed chaining \u2014 scene-wide, per \u00a78\n        Object.values(this.steps).forEach(function (s) {\n          if (s.trigger.type === 'sensed' && s.trigger.stepId === stepId) {\n            _this.start(s.id);\n          }\n        });\n\n        // anything queued behind this step under a 'wait' collision policy\n        if (step.trackId) this._drainWaitQueue(step.actorId, step.trackId);\n      }\n    }, {\n      key: \"blocked\",\n      value: function blocked(stepId, reason) {\n        var step = this.steps[stepId];\n        if (!step) throw new DispatchError(\"blocked: unknown step \\\"\".concat(stepId, \"\\\"\"));\n        var actor = this.actors[step.actorId];\n        if (step.trackId && actor.tracks[step.trackId].activeStepId === stepId) {\n          actor.tracks[step.trackId].activeStepId = null;\n        }\n        this._releaseFieldLock(step.actorId, stepId);\n        // \u00a73: blocked is new precisely so a failure is visible instead of silent \u2014\n        // logged with its reason rather than just dropped.\n        this._log({\n          verb: 'blocked',\n          actorId: step.actorId,\n          trackId: step.trackId,\n          stepId: stepId,\n          detail: reason || null\n        });\n      }\n\n      // set(): direct field write, subject to the field map's arbitration rule\n      // (\u00a75.2) and, when two affect-writers contend (\u00a74.2/item 4a), the\n      // priority-order policy decided at the top of this file.\n      //   opts: { priority: 'declared' | 'continuous', holderStepId? }\n    }, {\n      key: \"set\",\n      value: function set(actorId, fieldName, value, opts) {\n        opts = opts || {};\n        var actor = this.actors[actorId];\n        if (!actor) throw new DispatchError(\"set: unknown actor \\\"\".concat(actorId, \"\\\"\"));\n        var fieldDef = actor.fieldMap.fields.find(function (f) {\n          return f.name === fieldName;\n        });\n        if (!fieldDef) {\n          this._log({\n            verb: 'set',\n            actorId: actorId,\n            detail: \"refused \\u2014 \\\"\".concat(fieldName, \"\\\" is not in this Actor's field map\")\n          });\n          return false;\n        }\n        if (fieldDef.reach !== 'affect-writable') {\n          this._log({\n            verb: 'set',\n            actorId: actorId,\n            detail: \"refused \\u2014 \\\"\".concat(fieldName, \"\\\" is \").concat(fieldDef.reach, \", not affect-writable\")\n          });\n          return false;\n        }\n        var priority = opts.priority || 'continuous';\n        var existingLock = actor.fieldLock[fieldName];\n\n        // item 4a: a declared write in progress holds the field; a lower-priority\n        // (continuous) write attempted while that lock is held is refused, not\n        // queued \u2014 it simply resumes being honored once the lock releases.\n        if (existingLock && existingLock.priority === 'declared' && priority !== 'declared') {\n          this._log({\n            verb: 'set',\n            actorId: actorId,\n            detail: \"refused \\u2014 \\\"\".concat(fieldName, \"\\\" is locked by declared step \\\"\").concat(existingLock.holderStepId, \"\\\" (item 4a priority order)\")\n          });\n          return false;\n        }\n        if (priority === 'declared') {\n          actor.fieldLock[fieldName] = {\n            priority: 'declared',\n            holderStepId: opts.holderStepId || null\n          };\n        }\n\n        // track-vs-affect arbitration (\u00a75.2). `replace`/`track-wins` need to know\n        // whether a track currently claims the field; this dispatcher doesn't\n        // track per-field track ownership separately from track-only reach (a\n        // track-only field can never reach set() at all, per the reach check\n        // above), so `track-wins` only matters for fields also driven by an idle-\n        // vs-active track state passed in via opts.trackActive.\n        var resolved = value;\n        if (fieldDef.arbitration === 'track-wins' && opts.trackActive) {\n          this._log({\n            verb: 'set',\n            actorId: actorId,\n            detail: \"refused \\u2014 \\\"\".concat(fieldName, \"\\\" arbitration is track-wins and its track is active\")\n          });\n          return false;\n        }\n        if (fieldDef.arbitration === 'blend' && BLEND_FUNCTIONS[fieldName]) {\n          var recorded = opts.recordedValue !== undefined ? opts.recordedValue : actor.fieldValues[fieldName] !== undefined ? actor.fieldValues[fieldName] : 1;\n          resolved = BLEND_FUNCTIONS[fieldName](recorded, value);\n        }\n        // arbitration === 'replace' (or blend with no named function yet): value applies as given.\n\n        actor.fieldValues[fieldName] = resolved;\n        this._log({\n          verb: 'set',\n          actorId: actorId,\n          detail: \"\".concat(fieldName, \" = \").concat(resolved, \" (priority=\").concat(priority, \")\")\n        });\n        return true;\n      }\n    }, {\n      key: \"_releaseFieldLock\",\n      value: function _releaseFieldLock(actorId, stepId) {\n        var actor = this.actors[actorId];\n        Object.keys(actor.fieldLock).forEach(function (fieldName) {\n          if (actor.fieldLock[fieldName].holderStepId === stepId) {\n            delete actor.fieldLock[fieldName];\n          }\n        });\n      }\n\n      // \u2500\u2500 trigger evaluation \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    }, {\n      key: \"sceneStart\",\n      value: function sceneStart() {\n        var _this2 = this;\n        Object.values(this.steps).forEach(function (step) {\n          if (step.trigger.type === 'scene-start') _this2.start(step.id);\n        });\n      }\n    }, {\n      key: \"fireZone\",\n      value: function fireZone(actorId, zoneName) {\n        var _this3 = this;\n        Object.values(this.steps).forEach(function (step) {\n          if (step.trigger.type === 'zone' && step.actorId === actorId && step.trigger.zone === zoneName) {\n            _this3.start(step.id);\n          }\n        });\n      }\n    }, {\n      key: \"fireTouch\",\n      value: function fireTouch(actorId, sensorName) {\n        var _this4 = this;\n        Object.values(this.steps).forEach(function (step) {\n          if (step.trigger.type === 'touch' && step.actorId === actorId && step.trigger.sensor === sensorName) {\n            _this4.start(step.id);\n          }\n        });\n      }\n\n      // tick(): advances the master clock and fires any `declared` triggers\n      // whose time has arrived. Pushed, not polled by each Actor (\u00a75.3) \u2014 the\n      // clock is the single source that decides when, everything else reacts.\n    }, {\n      key: \"tick\",\n      value: function tick(time) {\n        var _this5 = this;\n        this.clock = time;\n        Object.values(this.steps).filter(function (s) {\n          return s.trigger.type === 'declared' && s.trigger.time <= time && !_this5._firedDeclared[s.id];\n        }).sort(function (a, b) {\n          return a.trigger.time - b.trigger.time;\n        }).forEach(function (step) {\n          _this5._firedDeclared[step.id] = true;\n          _this5._fireDeclared(step);\n        });\n      }\n\n      // fireCue(): explicit fan-out for a named declared multi-Actor cue (\u00a78.1) \u2014\n      // fires every step sharing a cueName in one action, each honoring its own\n      // per-step onCollision policy (\u00a75.4). tick() also reaches these\n      // individually once their shared time arrives; fireCue() is for triggering\n      // the whole group by name directly (e.g. from a UI \"fire this cue now\").\n    }, {\n      key: \"fireCue\",\n      value: function fireCue(cueName) {\n        var _this6 = this;\n        Object.values(this.steps).filter(function (s) {\n          return s.cueName === cueName && s.trigger.type === 'declared';\n        }).forEach(function (step) {\n          _this6._firedDeclared[step.id] = true;\n          _this6._fireDeclared(step);\n        });\n      }\n\n      // fireArcComplete(): fires steps whose trigger is `arc-complete` (bare \u2014\n      // scene-wide, any arc) or `arc-complete:<zoneId>` (only that zone's arc).\n      // Pushed by whatever completes an arc (the not-yet-wired Chorus/arc-\n      // recording integration \u2014 see Day 72 seed doc \u00a75.2), same \"pushed, not\n      // polled\" discipline as tick()/fireZone()/fireTouch(). Unlike tick(),\n      // this does NOT do the _firedDeclared one-shot bookkeeping \u2014 a `declared`\n      // beat fires once at a fixed scene-clock time by definition, but an arc\n      // completing is an external event that can legitimately happen more than\n      // once across a session (a zone's arc completing again on a later visit,\n      // per-take Chorus capture). Whether a caller wants \"only ever once\"\n      // semantics is that caller's decision, not this dispatcher's to assume.\n    }, {\n      key: \"fireArcComplete\",\n      value: function fireArcComplete(zoneId) {\n        var _this7 = this;\n        Object.values(this.steps).filter(function (s) {\n          return s.trigger.type === 'arc-complete' && (!s.trigger.zone || s.trigger.zone === zoneId);\n        }).forEach(function (step) {\n          return _this7._fireWithCollisionPolicy(step);\n        });\n      }\n    }, {\n      key: \"_fireDeclared\",\n      value: function _fireDeclared(step) {\n        this._fireWithCollisionPolicy(step);\n      }\n\n      // _fireWithCollisionPolicy(): the actual interrupt/wait/overlap branching\n      // (\u00a75.4), shared by declared-trigger firing (tick()/fireCue(), via\n      // _fireDeclared) and arc-complete firing (fireArcComplete). Extracted\n      // Day 73 so arc-complete doesn't duplicate this logic \u2014 behavior for\n      // declared/cue firing is unchanged, this is a pure refactor for that path.\n    }, {\n      key: \"_fireWithCollisionPolicy\",\n      value: function _fireWithCollisionPolicy(step) {\n        var actor = this.actors[step.actorId];\n        var track = step.trackId ? actor.tracks[step.trackId] : null;\n        var collision = track && track.activeStepId && track.activeStepId !== step.id;\n        if (!collision) {\n          this.start(step.id);\n          return;\n        }\n        var policy = step.onCollision || 'interrupt';\n        if (policy === 'interrupt') {\n          this.start(step.id); // start() already displaces via Welder\n        } else if (policy === 'overlap') {\n          // Deliberately does NOT go through the track-slot displacement in\n          // start(): overlap is only valid where the two don't contend on the\n          // same track/field (\u00a75.4), so this leaves the running step's track\n          // ownership alone and just runs this step's own field-write, if any,\n          // without claiming the track slot.\n          this._log({\n            verb: 'start',\n            actorId: step.actorId,\n            trackId: step.trackId,\n            stepId: step.id,\n            detail: 'overlap \u2014 no track displacement'\n          });\n          if (step.fieldWrite) {\n            this.set(step.actorId, step.fieldWrite.field, step.fieldWrite.value, {\n              priority: step.fieldWrite.priority || 'continuous',\n              holderStepId: step.id\n            });\n          }\n        } else if (policy === 'wait') {\n          var key = \"\".concat(step.actorId, \":\").concat(step.trackId);\n          this._waitQueues[key] = this._waitQueues[key] || [];\n          this._waitQueues[key].push(step.id);\n          this._log({\n            verb: 'start',\n            actorId: step.actorId,\n            trackId: step.trackId,\n            stepId: step.id,\n            detail: 'wait \u2014 queued behind current step'\n          });\n        }\n      }\n    }, {\n      key: \"_drainWaitQueue\",\n      value: function _drainWaitQueue(actorId, trackId) {\n        var key = \"\".concat(actorId, \":\").concat(trackId);\n        var queue = this._waitQueues[key];\n        if (queue && queue.length) {\n          var nextId = queue.shift();\n          this.start(nextId);\n        }\n      }\n    }]);\n  }(); // Day 74 note (still accurate): a bare `module.exports` throws\n  // \"ReferenceError: module is not defined\" the instant it's loaded via\n  // <script src=\"dispatcher.js\"> in a real browser with no CommonJS shim.\n  // That problem is now handled one level up, by the UMD wrapper opened at\n  // the top of this file (Day 75) \u2014 this just returns the same export\n  // surface from inside the factory function instead of assigning it\n  // directly, so VERBS/TRIGGER_TYPES/COLLISION_POLICIES/BLEND_FUNCTIONS/\n  // DispatchError/Dispatcher stay contained in this closure and only\n  // MCCFDispatcher (Node: module.exports, browser: window.MCCFDispatcher)\n  // reaches outer scope.\n  return {\n    Dispatcher: Dispatcher,\n    DispatchError: DispatchError,\n    VERBS: VERBS,\n    TRIGGER_TYPES: TRIGGER_TYPES,\n    COLLISION_POLICIES: COLLISION_POLICIES,\n    BLEND_FUNCTIONS: BLEND_FUNCTIONS\n  };\n}); // end UMD factory (opened Day 75, top of file)\n";

  function safeId(s) { return String(s || '').replace(/[^a-zA-Z0-9_]/g, '_'); }
  function xmlEscape(s) {
    // Also escapes apostrophes (&apos;) — see the matching fix and comment
    // on xe() in mccf_scene_composer.html. Same bug class: any attribute
    // built with single-quote delimiters breaks on an unescaped apostrophe
    // in the value, and &apos; is safe inside double-quoted attributes too,
    // so escaping it unconditionally here costs nothing.
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;');
  }

  // Timeline authoring shape -> dispatcher.js's addStep shape. Timeline's
  // authored trigger objects use 'at'/'ref' (UI-facing names);
  // dispatcher.js's own addStep validation expects 'time'/'stepId' for the
  // same two trigger types (dialogue-xml.js's parseStepTrigger already does
  // this exact kind of adaptation for dialogue lines). touch has no
  // sensor-name field anywhere in the current authoring UI \u2014 defaults to
  // a per-actor sensor named after the actor id, a documented convention,
  // not a discovered one.
  function toDispatcherTrigger(t, actorId) {
    if (!t) return t;
    if (t.type === 'declared') return { type: 'declared', time: t.at };
    if (t.type === 'sensed') return { type: 'sensed', stepId: t.ref };
    if (t.type === 'touch' && !t.sensor) return { type: 'touch', sensor: actorId };
    if (t.type === 'arc-complete') return { type: 'arc-complete', zone: t.zone };
    return t;
  }

  function toDispatcherStep(s, actorId, trackId) {
    const step = {
      id: s.id,
      actorId: actorId,
      trackId: trackId,
      trigger: toDispatcherTrigger(s.trigger, actorId),
      duration: { certainty: s.durationKind || 'fixed' },
    };
    if (s.onCollision) step.onCollision = s.onCollision;
    if (s.trigger && s.trigger.cue) step.cueName = s.trigger.cue;
    if (s.verb === 'set' && s.field !== undefined) {
      step.fieldWrite = { field: s.field, value: s.value, priority: s.priority || 'continuous' };
    }
    step._t0 = s.t0; step._t1 = s.t1;
    step._cameraType = s.cameraType; step._targetActor = s.targetActor; step._viewpointRef = s.viewpointRef;
    step._clipTimerDEF = s.clipTimerDEF;
    step._recordedPathId = s.recordedPathId;
    step._trackKind = null;
    return step;
  }

  function buildRegistrationGlue(actors, warnings) {
    const lines = [];
    actors.forEach(function (a) {
      const fieldMap = MCCFActorAdapter.DEFAULT_FIELD_MAPS[a.type];
      if (!fieldMap) {
        warnings.push('Actor "' + a.id + '" has type "' + a.type + '" with no known field map (only Avatar/Camera are defined) - registered with an empty one.');
      }
      const trackDefs = {};
      (a.tracks || []).forEach(function (t) { trackDefs[t.id] = { kind: t.kind }; });
      lines.push('__D.registerActor(' + JSON.stringify(a.id) + ',' + JSON.stringify(fieldMap || { actorType: a.type, fields: [] }) + ',' + JSON.stringify(trackDefs) + ');');
      (a.tracks || []).forEach(function (t) {
        (t.steps || []).forEach(function (s) {
          const dstep = toDispatcherStep(s, a.id, t.id);
          dstep._trackKind = t.kind;
          lines.push('__D.addStep(' + JSON.stringify(dstep) + ');');
        });
      });
    });
    return lines.join('\n  ');
  }

  const EFFECT_EXECUTOR_JS = "function __afterStart(step) {\n    if (step._trackKind === \"camera\") { __execCameraStep(step); }\n    else if (step._trackKind === \"gesture\") { __execGestureStep(step); }\n    else if (step._trackKind) { Browser.println(\"[MCCF] \" + step._trackKind + \" track step \" + step.id + \" started, no execution layer wired yet (path/dialogue effect execution is a follow-up pass, not this generator).\"); }\n    if (step.duration && step.duration.certainty === \"fixed\" && typeof step._t0 === \"number\" && typeof step._t1 === \"number\") {\n      var dur = Math.max(0, step._t1 - step._t0);\n      setTimeout(function () { __D.arrived(step.id); }, dur * 1000);\n    }\n  }\n  \n  function __execCameraStep(step) {\n    try {\n      if (step._cameraType === \"fixed\" && step._viewpointRef) {\n        var vp = Browser.currentScene.getNamedNode(step._viewpointRef);\n        if (vp) { vp.set_bind = true; Browser.println(\"[MCCF] camera: bound named viewpoint \" + step._viewpointRef); }\n        else { Browser.println(\"[MCCF] camera: named viewpoint not found: \" + step._viewpointRef); }\n        return;\n      }\n      if (step._cameraType === \"orbit\" && step._targetActor) {\n        var orb = Browser.currentScene.getNamedNode(\"CAM_OrbitProto_\" + step._targetActor.replace(/[^A-Za-z0-9_]/g, \"_\"));\n        if (orb) { orb.set_bind = true; Browser.println(\"[MCCF] camera: bound orbit around \" + step._targetActor); }\n        else { Browser.println(\"[MCCF] camera: orbit proto not found for \" + step._targetActor + \" (that avatar\\u0027s camera rig manifest may not include agent_orbit)\"); }\n        return;\n      }\n      if (step._cameraType === \"track\" && step._targetActor) {\n        var trk = Browser.currentScene.getNamedNode(\"CAM_TrackProto_\" + step._targetActor.replace(/[^A-Za-z0-9_]/g, \"_\"));\n        if (trk) { trk.set_bind = true; Browser.println(\"[MCCF] camera: bound track following \" + step._targetActor); }\n        else { Browser.println(\"[MCCF] camera: track proto not found for \" + step._targetActor + \" (that avatar\\u0027s camera rig manifest may not include agent_track)\"); }\n        return;\n      }\n      if (step._cameraType === \"pov\" && step._targetActor) {\n        var pov = Browser.currentScene.getNamedNode(\"VP_\" + step._targetActor.replace(/[^A-Za-z0-9_]/g, \"_\") + \"_Eye\");\n        if (pov) { pov.set_bind = true; Browser.println(\"[MCCF] camera: bound POV (eye viewpoint) of \" + step._targetActor); }\n        else { Browser.println(\"[MCCF] camera: eye viewpoint not found for \" + step._targetActor + \" (that avatar\\u0027s camera rig manifest may not include agent_eye)\"); }\n        return;\n      }\n      Browser.println(\"[MCCF] camera step \" + step.id + \" has cameraType \" + step._cameraType + \", not implemented this pass (dolly has no defined mechanism yet, or a required target/viewpoint was missing).\");\n    } catch (e) { Browser.println(\"[MCCF] camera step \" + step.id + \" execution failed: \" + e.message); }\n  }\n  \n  function __execGestureStep(step) {\n    if (!step._clipTimerDEF) {\n      Browser.println(\"[MCCF] gesture step \" + step.id + \" has no clipTimerDEF set, no authoring UI for this yet, nothing to trigger.\");\n      return;\n    }\n    try {\n      var importedName = step._clipTimerDEF + \"_\" + step.actorId.replace(/[^A-Za-z0-9_]/g, \"_\");\n      var timer = Browser.currentScene.getImportedNode(importedName);\n      if (timer) {\n        timer.enabled = true;\n        Browser.println(\"[MCCF] gesture: started \" + importedName);\n      } else {\n        Browser.println(\"[MCCF] gesture: imported timer not found: \" + importedName);\n      }\n    } catch (e) {\n      Browser.println(\"[MCCF] gesture step \" + step.id + \" execution failed, getImportedNode may not be callable from inside a Script node, unverified: \" + e.message);\n    }\n  }";

  // Day 79: which top-level DEF holds an actor's real live position, per
  // exportX3D/buildX3DString's own naming (confirmed by reading both):
  // Avatar -> "Avatar_<safeId>" (buildAX3D's own top-level Transform DEF,
  // NOT nested inside the avatar's Inline scope, so getNamedNode resolves
  // it); Camera -> "CAM_Free_<safeId>" (buildFreeCamerasX3D). Used for
  // zone-entry detection below - the actual DEF an actor's placement lives
  // under, not the actor's own authoring-time id.
  function actorDefName(a) {
    return (a.type === 'Camera' ? 'CAM_Free_' : 'Avatar_') + safeId(a.id);
  }

  // Zone-entry detection (Day 79) - the real gap flagged when this
  // generator first shipped: X3D's own ProximitySensor only ever reports
  // the bound VIEWPOINT's position (confirmed empirically, Day 78 seed
  // doc), never an arbitrary Actor's. There's no built-in X3D mechanism
  // for "did Cindy walk into the Garden zone" the way there is for "did
  // the author's own camera." This polls each Actor's real Transform
  // position against each zone's center/radius on the same master-clock
  // tick that already drives declared triggers - simple distance math, no
  // new sensor needed, and it reuses dispatcher.js's own real fireZone()
  // rather than inventing a parallel mechanism. Fires only on the
  // outside->inside edge (not every tick while inside), matching how a
  // real zone-enter sensor would behave. Touch triggers are NOT solved by
  // this - "touching" implies a specific target object, and no object-
  // target data model exists anywhere in this codebase yet (props,
  // interactive items) for a touch trigger to reference. That's a
  // separate, still-open gap, not a smaller version of this one.
  const ZONE_CHECK_JS = "var __zoneState = {};\n  function __checkZones() {\n    ZONES.forEach(function (z) {\n      ACTOR_DEFS.forEach(function (a) {\n        var key = a.id + \"|\" + z.id;\n        var node = Browser.currentScene.getNamedNode(a.def);\n        if (!node) return;\n        var p = node.translation;\n        if (!p) return;\n        var dx = p.x - z.location[0], dz = p.z - z.location[2];\n        var inside = Math.sqrt(dx * dx + dz * dz) <= z.radius;\n        var wasInside = !!__zoneState[key];\n        if (inside && !wasInside) { __D.fireZone(a.id, z.id); }\n        __zoneState[key] = inside;\n      });\n    });\n  }";

  function buildDispatcherScriptXML(actors, zones, warnings) {
    const regGlue = buildRegistrationGlue(actors, warnings);
    const actorDefs = actors.map(function (a) { return { id: a.id, def: actorDefName(a) }; });
    const lines = [];
    lines.push('<Script DEF="MCCFDispatcherRuntime" directOutput="true" mustEvaluate="true">');
    lines.push('  <field name="set_time" type="SFTime" accessType="inputOnly"/>');
    lines.push('  <![CDATA[ecmascript:');
    lines.push(DISPATCHER_CORE_ES5);
    lines.push('  var __D = new MCCFDispatcher.Dispatcher();');
    lines.push('  var __realStart = __D.start.bind(__D);');
    lines.push('  __D.start = function (stepId) {');
    lines.push('    var r = __realStart(stepId);');
    lines.push('    var step = __D.steps[stepId];');
    lines.push('    if (step) __afterStart(step);');
    lines.push('    return r;');
    lines.push('  };');
    lines.push('  ' + EFFECT_EXECUTOR_JS);
    lines.push('  var ZONES = ' + JSON.stringify(zones) + ';');
    lines.push('  var ACTOR_DEFS = ' + JSON.stringify(actorDefs) + ';');
    lines.push('  ' + ZONE_CHECK_JS);
    lines.push('  ' + regGlue);
    lines.push('  function initialize() { __D.sceneStart(); }');
    lines.push('  function set_time(value, timestamp) { __D.tick(value); __checkZones(); }');
    lines.push('  ]]' + '>');
    lines.push('</' + 'Script>');
    return lines.join('\n');
  }

  function buildClockXML() {
    const lines = [];
    lines.push('<TimeSensor DEF="MCCFMasterClock" cycleInterval="86400" loop="true" enabled="true"/>');
    lines.push('<ROUTE fromNode="MCCFMasterClock" fromField="elapsedTime" toNode="MCCFDispatcherRuntime" toField="set_time"/>');
    return lines.join('\n');
  }

  function generateSceneScript(sceneData) {
    const warnings = [];
    const actors = (sceneData && sceneData.actors) || [];
    const zones = (sceneData && sceneData.zones) || [];
    if (!actors.length) warnings.push('No actors in scene data - generated a dispatcher with nothing registered.');
    const scriptXML = buildDispatcherScriptXML(actors, zones, warnings);
    const clockXML = buildClockXML();
    return {
      xml: '<!-- MCCF Dispatcher Runtime (generated, Day 79 Phase 4 task 8) -->\n' + scriptXML + '\n' + clockXML,
      warnings: warnings,
    };
  }

  return { generateSceneScript, toDispatcherTrigger, toDispatcherStep, safeId, xmlEscape };
});
