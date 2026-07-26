// MCCF scene-level dispatcher — Day 72, build schedule item 3.
// Day 73: added the arc-complete trigger (priority queue item 3 — the
// Chorus redesign decided in the Day 72 seed doc §5.2). Fires through the
// same collision-policy branch as `declared` steps (interrupt/wait/overlap
// via _fireWithCollisionPolicy, extracted from what was previously
// _fireDeclared's inline body — no behavior change for declared/cue firing,
// just a shared helper so arc-complete doesn't duplicate that logic).
// Implements design doc §8 (scene-level coordination) end to end: the five
// verbs (§3), both trigger families (§3.1), the Welder default arbitration
// (§5.1, generalized to any track incl. camera cuts per §7), track-vs-affect
// arbitration from each Actor's field map (§5.2), declared-vs-running
// collision policy (§5.4), and declared multi-Actor cues (§8.1).
//
// Also implements the decision build-schedule item 4a flagged as open: two
// simultaneous affect-writers on the same field (§4.2's unresolved case,
// concretely the Ground Tremor fog conflict, §9). Decision made HERE, on
// record, not silently: priority order — a declared write holds an
// exclusive lock on the field for the duration of its step; continuous
// (non-declared) affect writes are refused while that lock is held, and
// resume being honored once the declared step's `arrived` fires and
// releases the lock. This was the build-schedule's recommended default
// (matches §5.4's interrupt/wait/overlap precedent: a scripted beat is more
// deliberate than an ambient coupling) — recorded here as the actual policy,
// not just a recommendation, since item 3 can't pass its own Ground Tremor
// test without it being decided.
//
// Also implements item 4b: the two named `blend` functions (walkPace,
// swingSpeed), both as a recorded-value × multiplier form, per their worked
// manifests in field-map/worked-manifests.js.
//
// No X3D emission here and no wiring to mccf_api.py — this is the
// architecture-level piece the build schedule called for; it runs against
// stub Actors (field map + track/step defs), not a real scene file, same as
// the Day 71 prototypes it eventually needs to plug into (item 5).

// Day 75: wrapped in a UMD-style IIFE, same pattern field-map.js and
// timeline-xml.js already use. Day 74's browser-export fix only patched
// the bare `module.exports` line below (the ReferenceError-in-browser
// problem) but left VERBS/TRIGGER_TYPES/COLLISION_POLICIES/BLEND_FUNCTIONS/
// DispatchError/Dispatcher all declared at the file's top level. Loaded via
// <script src="dispatcher.js"> that way, `const VERBS` becomes a global
// lexical binding — and the Timeline prototype's own inline script
// separately declares its own top-level `const VERBS` (a UI badge-styling
// object, unrelated shape) for its own purposes. Two top-level `const
// VERBS` declarations on one page is a SyntaxError at parse time, which
// silently kills the *entire* inline script block — no render, no button
// wiring, nothing runs. Found by an actual jsdom load-and-click of the
// real file (Day 75 browser-equivalent test), not by code review; the
// Day 74 Node `vm` check didn't catch it because it extracted and ran the
// inline script in isolation rather than alongside the real script-src
// files the way a real page load does. Fixed by containing everything
// this file declares inside one function scope; only MCCFDispatcher
// reaches the outer (window/global) scope, exactly like field-map.js.
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.MCCFDispatcher = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {

const VERBS = ['start', 'stop', 'arrived', 'blocked', 'set'];
const TRIGGER_TYPES = ['scene-start', 'touch', 'zone', 'sensed', 'declared', 'arc-complete'];
const COLLISION_POLICIES = ['interrupt', 'wait', 'overlap'];

// Field-type-specific blend functions (item 4b). Deliberately not a general
// mechanism — only these two fields have a concrete shape decided anywhere
// in the source docs (both multiplier form, per their worked manifests).
const BLEND_FUNCTIONS = {
  walkPace: (recorded, affectMultiplier) => recorded * affectMultiplier,
  swingSpeed: (recorded, affectMultiplier) => recorded * affectMultiplier,
};

class DispatchError extends Error {}

class Dispatcher {
  constructor() {
    this.actors = {};        // actorId -> Actor
    this.steps = {};         // stepId -> step def (as registered)
    this.clock = 0;
    this._firedDeclared = new Set();
    this._waitQueues = {};   // "actorId:trackId" -> [stepId,...] pending 'wait'-policy declared steps
    this.eventLog = [];      // {t, verb, actorId, trackId, stepId, detail}
  }

  _log(entry) {
    this.eventLog.push(Object.assign({ t: this.clock }, entry));
  }

  // ── registration ─────────────────────────────────────────────────────
  // Same identity discipline as build-schedule item 1: reject a duplicate
  // id outright rather than silently overwrite. Actor ids, track ids
  // (scoped to their Actor), and step ids (scoped to the whole scene, since
  // `sensed` triggers reference step ids scene-wide per design doc §8) all
  // go through this.

  registerActor(actorId, fieldMap, trackDefs) {
    if (this.actors[actorId]) {
      throw new DispatchError(`registerActor: "${actorId}" already registered`);
    }
    if (!fieldMap || !Array.isArray(fieldMap.fields)) {
      throw new DispatchError(`registerActor: "${actorId}" needs a field map (even an empty one — §4.1)`);
    }
    const tracks = {};
    Object.keys(trackDefs || {}).forEach((trackId) => {
      tracks[trackId] = {
        kind: trackDefs[trackId].kind,
        activeStepId: null,
      };
    });
    this.actors[actorId] = {
      id: actorId,
      fieldMap,
      tracks,
      fieldValues: {},
      fieldLock: {}, // fieldName -> { priority: 'declared', holderStepId } while a declared write holds it
    };
    return this.actors[actorId];
  }

  addStep(step) {
    // step: { id, actorId, trackId, trigger: {type, ...}, duration: {certainty, seconds?},
    //         onCollision?, fieldWrite?: {field, value, priority}, cueName? }
    if (this.steps[step.id]) {
      throw new DispatchError(`addStep: step id "${step.id}" already exists — step ids are scene-wide unique (design doc §8)`);
    }
    if (!this.actors[step.actorId]) {
      throw new DispatchError(`addStep: unknown actor "${step.actorId}" for step "${step.id}"`);
    }
    const actor = this.actors[step.actorId];
    if (step.trackId && !actor.tracks[step.trackId]) {
      throw new DispatchError(`addStep: actor "${step.actorId}" has no track "${step.trackId}" for step "${step.id}"`);
    }
    if (!step.trigger || !TRIGGER_TYPES.includes(step.trigger.type)) {
      throw new DispatchError(`addStep: step "${step.id}" has an invalid trigger type`);
    }
    if (step.trigger.type === 'declared' && typeof step.trigger.time !== 'number') {
      throw new DispatchError(`addStep: declared trigger on "${step.id}" needs a numeric time`);
    }
    if (step.trigger.type === 'sensed' && !step.trigger.stepId) {
      throw new DispatchError(`addStep: sensed trigger on "${step.id}" needs a stepId to chain off`);
    }
    if (step.trigger.type === 'arc-complete' && step.trigger.zone !== undefined && typeof step.trigger.zone !== 'string') {
      throw new DispatchError(`addStep: arc-complete trigger on "${step.id}" has a non-string zone — omit it entirely for the scene-wide (bare) form`);
    }
    if (!step.duration || !['fixed', 'estimate'].includes(step.duration.certainty)) {
      throw new DispatchError(`addStep: step "${step.id}" needs duration.certainty (fixed|estimate) — §3.2`);
    }
    if (step.onCollision && !COLLISION_POLICIES.includes(step.onCollision)) {
      throw new DispatchError(`addStep: step "${step.id}" has an invalid onCollision policy`);
    }
    this.steps[step.id] = step;
    return step;
  }

  // ── the five verbs ──────────────────────────────────────────────────

  // start(): the generic entry point for actually beginning a step. Applies
  // the Welder default (§5.1) — starting a new step on a track displaces
  // whatever's currently active on that track, generalized from gestures to
  // every track kind, camera cuts included (§7), with no special-casing.
  start(stepId) {
    const step = this.steps[stepId];
    if (!step) throw new DispatchError(`start: unknown step "${stepId}"`);
    const actor = this.actors[step.actorId];
    if (step.trackId) {
      const track = actor.tracks[step.trackId];
      if (track.activeStepId && track.activeStepId !== stepId) {
        this.stop(track.activeStepId); // Welder displacement — not an 'arrived', it didn't finish on its own
      }
      track.activeStepId = stepId;
    }
    this._log({ verb: 'start', actorId: step.actorId, trackId: step.trackId, stepId });
    if (step.fieldWrite) {
      this.set(step.actorId, step.fieldWrite.field, step.fieldWrite.value, {
        priority: step.fieldWrite.priority || 'continuous',
        holderStepId: stepId,
      });
    }
    return true;
  }

  stop(stepId) {
    const step = this.steps[stepId];
    if (!step) throw new DispatchError(`stop: unknown step "${stepId}"`);
    const actor = this.actors[step.actorId];
    if (step.trackId && actor.tracks[step.trackId].activeStepId === stepId) {
      actor.tracks[step.trackId].activeStepId = null;
    }
    this._releaseFieldLock(step.actorId, stepId);
    this._log({ verb: 'stop', actorId: step.actorId, trackId: step.trackId, stepId });
  }

  // arrived(): pushed BY an Actor when a step completes on its own. Chains
  // any `sensed` steps waiting on this step id (§5.3 — push, not pull), and
  // releases whatever this step held (track slot, field lock) before
  // checking the wait queue for anything queued behind it (§5.4).
  arrived(stepId) {
    const step = this.steps[stepId];
    if (!step) throw new DispatchError(`arrived: unknown step "${stepId}"`);
    const actor = this.actors[step.actorId];
    if (step.trackId && actor.tracks[step.trackId].activeStepId === stepId) {
      actor.tracks[step.trackId].activeStepId = null;
    }
    this._releaseFieldLock(step.actorId, stepId);
    this._log({ verb: 'arrived', actorId: step.actorId, trackId: step.trackId, stepId });

    // sensed chaining — scene-wide, per §8
    Object.values(this.steps).forEach((s) => {
      if (s.trigger.type === 'sensed' && s.trigger.stepId === stepId) {
        this.start(s.id);
      }
    });

    // anything queued behind this step under a 'wait' collision policy
    if (step.trackId) this._drainWaitQueue(step.actorId, step.trackId);
  }

  blocked(stepId, reason) {
    const step = this.steps[stepId];
    if (!step) throw new DispatchError(`blocked: unknown step "${stepId}"`);
    const actor = this.actors[step.actorId];
    if (step.trackId && actor.tracks[step.trackId].activeStepId === stepId) {
      actor.tracks[step.trackId].activeStepId = null;
    }
    this._releaseFieldLock(step.actorId, stepId);
    // §3: blocked is new precisely so a failure is visible instead of silent —
    // logged with its reason rather than just dropped.
    this._log({ verb: 'blocked', actorId: step.actorId, trackId: step.trackId, stepId, detail: reason || null });
  }

  // set(): direct field write, subject to the field map's arbitration rule
  // (§5.2) and, when two affect-writers contend (§4.2/item 4a), the
  // priority-order policy decided at the top of this file.
  //   opts: { priority: 'declared' | 'continuous', holderStepId? }
  set(actorId, fieldName, value, opts) {
    opts = opts || {};
    const actor = this.actors[actorId];
    if (!actor) throw new DispatchError(`set: unknown actor "${actorId}"`);
    const fieldDef = actor.fieldMap.fields.find((f) => f.name === fieldName);
    if (!fieldDef) {
      this._log({ verb: 'set', actorId, detail: `refused — "${fieldName}" is not in this Actor's field map` });
      return false;
    }
    if (fieldDef.reach !== 'affect-writable') {
      this._log({ verb: 'set', actorId, detail: `refused — "${fieldName}" is ${fieldDef.reach}, not affect-writable` });
      return false;
    }

    const priority = opts.priority || 'continuous';
    const existingLock = actor.fieldLock[fieldName];

    // item 4a: a declared write in progress holds the field; a lower-priority
    // (continuous) write attempted while that lock is held is refused, not
    // queued — it simply resumes being honored once the lock releases.
    if (existingLock && existingLock.priority === 'declared' && priority !== 'declared') {
      this._log({ verb: 'set', actorId, detail: `refused — "${fieldName}" is locked by declared step "${existingLock.holderStepId}" (item 4a priority order)` });
      return false;
    }

    if (priority === 'declared') {
      actor.fieldLock[fieldName] = { priority: 'declared', holderStepId: opts.holderStepId || null };
    }

    // track-vs-affect arbitration (§5.2). `replace`/`track-wins` need to know
    // whether a track currently claims the field; this dispatcher doesn't
    // track per-field track ownership separately from track-only reach (a
    // track-only field can never reach set() at all, per the reach check
    // above), so `track-wins` only matters for fields also driven by an idle-
    // vs-active track state passed in via opts.trackActive.
    let resolved = value;
    if (fieldDef.arbitration === 'track-wins' && opts.trackActive) {
      this._log({ verb: 'set', actorId, detail: `refused — "${fieldName}" arbitration is track-wins and its track is active` });
      return false;
    }
    if (fieldDef.arbitration === 'blend' && BLEND_FUNCTIONS[fieldName]) {
      const recorded = opts.recordedValue !== undefined ? opts.recordedValue : (actor.fieldValues[fieldName] !== undefined ? actor.fieldValues[fieldName] : 1);
      resolved = BLEND_FUNCTIONS[fieldName](recorded, value);
    }
    // arbitration === 'replace' (or blend with no named function yet): value applies as given.

    actor.fieldValues[fieldName] = resolved;
    this._log({ verb: 'set', actorId, detail: `${fieldName} = ${resolved} (priority=${priority})` });
    return true;
  }

  _releaseFieldLock(actorId, stepId) {
    const actor = this.actors[actorId];
    Object.keys(actor.fieldLock).forEach((fieldName) => {
      if (actor.fieldLock[fieldName].holderStepId === stepId) {
        delete actor.fieldLock[fieldName];
      }
    });
  }

  // ── trigger evaluation ──────────────────────────────────────────────

  sceneStart() {
    Object.values(this.steps).forEach((step) => {
      if (step.trigger.type === 'scene-start') this.start(step.id);
    });
  }

  fireZone(actorId, zoneName) {
    Object.values(this.steps).forEach((step) => {
      if (step.trigger.type === 'zone' && step.actorId === actorId && step.trigger.zone === zoneName) {
        this.start(step.id);
      }
    });
  }

  fireTouch(actorId, sensorName) {
    Object.values(this.steps).forEach((step) => {
      if (step.trigger.type === 'touch' && step.actorId === actorId && step.trigger.sensor === sensorName) {
        this.start(step.id);
      }
    });
  }

  // tick(): advances the master clock and fires any `declared` triggers
  // whose time has arrived. Pushed, not polled by each Actor (§5.3) — the
  // clock is the single source that decides when, everything else reacts.
  tick(time) {
    this.clock = time;
    Object.values(this.steps)
      .filter((s) => s.trigger.type === 'declared' && s.trigger.time <= time && !this._firedDeclared.has(s.id))
      .sort((a, b) => a.trigger.time - b.trigger.time)
      .forEach((step) => {
        this._firedDeclared.add(step.id);
        this._fireDeclared(step);
      });
  }

  // fireCue(): explicit fan-out for a named declared multi-Actor cue (§8.1) —
  // fires every step sharing a cueName in one action, each honoring its own
  // per-step onCollision policy (§5.4). tick() also reaches these
  // individually once their shared time arrives; fireCue() is for triggering
  // the whole group by name directly (e.g. from a UI "fire this cue now").
  fireCue(cueName) {
    Object.values(this.steps)
      .filter((s) => s.cueName === cueName && s.trigger.type === 'declared')
      .forEach((step) => {
        this._firedDeclared.add(step.id);
        this._fireDeclared(step);
      });
  }

  // fireArcComplete(): fires steps whose trigger is `arc-complete` (bare —
  // scene-wide, any arc) or `arc-complete:<zoneId>` (only that zone's arc).
  // Pushed by whatever completes an arc (the not-yet-wired Chorus/arc-
  // recording integration — see Day 72 seed doc §5.2), same "pushed, not
  // polled" discipline as tick()/fireZone()/fireTouch(). Unlike tick(),
  // this does NOT do the _firedDeclared one-shot bookkeeping — a `declared`
  // beat fires once at a fixed scene-clock time by definition, but an arc
  // completing is an external event that can legitimately happen more than
  // once across a session (a zone's arc completing again on a later visit,
  // per-take Chorus capture). Whether a caller wants "only ever once"
  // semantics is that caller's decision, not this dispatcher's to assume.
  fireArcComplete(zoneId) {
    Object.values(this.steps)
      .filter((s) => s.trigger.type === 'arc-complete' && (!s.trigger.zone || s.trigger.zone === zoneId))
      .forEach((step) => this._fireWithCollisionPolicy(step));
  }

  _fireDeclared(step) {
    this._fireWithCollisionPolicy(step);
  }

  // _fireWithCollisionPolicy(): the actual interrupt/wait/overlap branching
  // (§5.4), shared by declared-trigger firing (tick()/fireCue(), via
  // _fireDeclared) and arc-complete firing (fireArcComplete). Extracted
  // Day 73 so arc-complete doesn't duplicate this logic — behavior for
  // declared/cue firing is unchanged, this is a pure refactor for that path.
  _fireWithCollisionPolicy(step) {
    const actor = this.actors[step.actorId];
    const track = step.trackId ? actor.tracks[step.trackId] : null;
    const collision = track && track.activeStepId && track.activeStepId !== step.id;
    if (!collision) {
      this.start(step.id);
      return;
    }
    const policy = step.onCollision || 'interrupt';
    if (policy === 'interrupt') {
      this.start(step.id); // start() already displaces via Welder
    } else if (policy === 'overlap') {
      // Deliberately does NOT go through the track-slot displacement in
      // start(): overlap is only valid where the two don't contend on the
      // same track/field (§5.4), so this leaves the running step's track
      // ownership alone and just runs this step's own field-write, if any,
      // without claiming the track slot.
      this._log({ verb: 'start', actorId: step.actorId, trackId: step.trackId, stepId: step.id, detail: 'overlap — no track displacement' });
      if (step.fieldWrite) {
        this.set(step.actorId, step.fieldWrite.field, step.fieldWrite.value, {
          priority: step.fieldWrite.priority || 'continuous',
          holderStepId: step.id,
        });
      }
    } else if (policy === 'wait') {
      const key = `${step.actorId}:${step.trackId}`;
      this._waitQueues[key] = this._waitQueues[key] || [];
      this._waitQueues[key].push(step.id);
      this._log({ verb: 'start', actorId: step.actorId, trackId: step.trackId, stepId: step.id, detail: 'wait — queued behind current step' });
    }
  }

  _drainWaitQueue(actorId, trackId) {
    const key = `${actorId}:${trackId}`;
    const queue = this._waitQueues[key];
    if (queue && queue.length) {
      const nextId = queue.shift();
      this.start(nextId);
    }
  }
}

// Day 74 note (still accurate): a bare `module.exports` throws
// "ReferenceError: module is not defined" the instant it's loaded via
// <script src="dispatcher.js"> in a real browser with no CommonJS shim.
// That problem is now handled one level up, by the UMD wrapper opened at
// the top of this file (Day 75) — this just returns the same export
// surface from inside the factory function instead of assigning it
// directly, so VERBS/TRIGGER_TYPES/COLLISION_POLICIES/BLEND_FUNCTIONS/
// DispatchError/Dispatcher stay contained in this closure and only
// MCCFDispatcher (Node: module.exports, browser: window.MCCFDispatcher)
// reaches outer scope.
return { Dispatcher, DispatchError, VERBS, TRIGGER_TYPES, COLLISION_POLICIES, BLEND_FUNCTIONS };

}); // end UMD factory (opened Day 75, top of file)
