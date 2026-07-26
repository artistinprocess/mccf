// MCCF Timeline XML loader — Day 74.
// Bridges MCCF_Step_Track_Timeline_Schema_v0_1.md's <Actor>/<Track>/<Step>/
// <Cue> XML into dispatcher.js's existing registerActor()/addStep() API.
// dispatcher.js itself has zero XML parsing (confirmed by reading it, not
// assumed) — it runs against stub Actors registered programmatically. This
// module is the missing piece: parse real scene XML, call the real
// dispatcher API, nothing invented in between.
//
// Same house style as dialogue-xml.js: hand-rolled parsing (schema is
// fully controlled, both ends are ours), zero dependencies, works under
// Node (tests) and as a plain browser <script>.
//
// Field maps: field-map.js's manifest is per actorType, not per Actor
// instance (Actor Doc §4: "every Actor type ships a manifest") — matches
// this loader's own <Actor type="..."> attribute directly. Field-map
// MetadataSet blocks are expected once per type, at scene top level
// (sibling to <Cue>, not nested inside individual <Actor> blocks — nesting
// one per instance would duplicate the same manifest across every Actor
// sharing a type). Each Actor's `type` attribute is the lookup key into
// that shared manifest set. Caller-supplied fieldMaps (keyed by actorType)
// are still accepted as an override/supplement for types not present in
// the scene XML itself.

(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.MCCFTimeline = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {

  // Reuse dialogue-xml.js's trigger parser and field-map.js's manifest
  // parser — both real, tested modules; nothing about triggers or field
  // maps is reimplemented here.
  let MCCFDialogue, MCCFFieldMap;
  if (typeof module !== 'undefined' && module.exports) {
    MCCFDialogue = require('./dialogue-xml.js');
    MCCFFieldMap = require('./field-map.js');
  } else if (typeof self !== 'undefined' && self.MCCFDialogue && self.MCCFFieldMap) {
    MCCFDialogue = self.MCCFDialogue;
    MCCFFieldMap = self.MCCFFieldMap;
  } else {
    throw new Error('MCCFTimeline requires MCCFDialogue (dialogue-xml.js) and MCCFFieldMap (field-map.js) to be loaded first — trigger and field-map parsing are shared, not duplicated.');
  }

  // ── trigger adapter ───────────────────────────────────────────────────
  // dialogue-xml.js's parseTrigger() is dialogue's own domain — a sensed
  // trigger there references a *lineId*. dispatcher.js's Step shape
  // references a *stepId* for the same underlying `sensed:<id>` string.
  // Same encoding, different property name on the parsed object — this is
  // the one real seam between the two modules, confirmed by reading both,
  // not assumed compatible. Everything else (scene-start/touch/zone/
  // declared) passes through unchanged.
  function parseStepTrigger(str) {
    const t = MCCFDialogue.parseTrigger(str);
    if (t.type === 'sensed') {
      return { type: 'sensed', stepId: t.lineId };
    }
    return t;
  }

  // ── extract each top-level fieldMap MetadataSet block, then hand the
  //    isolated substring to field-map.js's own parseFieldMap ───────────
  // Can't use a single non-greedy regex here: field-map.js's serialized
  // format nests field-level <MetadataSet name='field:...'> blocks inside
  // the outer <MetadataSet name='fieldMap'>, so opening/closing tags of
  // the same element name are nested. A simple balanced-tag scan handles
  // that correctly; field-map.js's own parseFieldMap (which expects an
  // isolated, self-contained block) does the actual parsing/validation —
  // this function's only job is finding where each block starts and ends.
  function extractFieldMapBlocks(sceneXml) {
    const blocks = [];
    const startRe = /<MetadataSet\s+name='fieldMap'/g;
    let sm;
    while ((sm = startRe.exec(sceneXml)) !== null) {
      const start = sm.index;
      const tagRe = /<MetadataSet\b|<\/MetadataSet>/g;
      tagRe.lastIndex = start;
      let depth = 0;
      let end = -1;
      let tm;
      while ((tm = tagRe.exec(sceneXml)) !== null) {
        if (tm[0] === '</MetadataSet>') {
          depth -= 1;
          if (depth === 0) { end = tm.index + tm[0].length; break; }
        } else {
          depth += 1;
        }
      }
      if (end === -1) {
        throw new Error('parseTimelineXml: unbalanced <MetadataSet name=\'fieldMap\'> block — no matching close tag found');
      }
      blocks.push(sceneXml.slice(start, end));
      startRe.lastIndex = end;
    }
    return blocks;
  }

  // Parse every fieldMap block in the scene, keyed by actorType.
  function parseFieldMapsFromScene(sceneXml) {
    const maps = {};
    extractFieldMapBlocks(sceneXml).forEach((block) => {
      const manifest = MCCFFieldMap.parseFieldMap(block);
      maps[manifest.actorType] = manifest;
    });
    return maps;
  }

  // ── XML attribute helper ────────────────────────────────────────────
  function getAttrs(tagStr) {
    const attrs = {};
    const re = /(\w+)="([^"]*)"/g;
    let m;
    while ((m = re.exec(tagStr)) !== null) attrs[m[1]] = m[2];
    return attrs;
  }

  // ── parse <Cue> registry (top-level, scene-scoped) ────────────────────
  function parseCues(sceneXml) {
    const cues = [];
    const re = /<Cue\s+([^>]*?)\/?>/g;
    let m;
    while ((m = re.exec(sceneXml)) !== null) {
      const attrs = getAttrs(m[1]);
      if (!attrs.id) continue;
      cues.push({ id: attrs.id, at: Number(attrs.at) });
    }
    return cues;
  }

  // ── parse one <Step> tag's attributes into dispatcher.js's step shape ──
  function stepFromAttrs(attrs, actorId, trackId) {
    if (!attrs.id) throw new Error('parseTimelineXml: <Step> missing id');
    if (!attrs.verb) throw new Error(`parseTimelineXml: step "${attrs.id}" missing verb`);
    if (!attrs.trigger) throw new Error(`parseTimelineXml: step "${attrs.id}" missing trigger`);

    const step = {
      id: attrs.id,
      actorId,
      trackId: trackId || undefined,
      trigger: parseStepTrigger(attrs.trigger),
    };

    // durationKind XML attribute -> dispatcher.js's duration:{certainty} object.
    // Not required for verb="set" (dispatcher.js's addStep only requires it
    // in general — a bare set() call has no duration concept of its own,
    // but addStep() still validates it unconditionally today, so a set
    // step needs SOME durationKind; "fixed" is the correct default since a
    // direct value write completes instantaneously, not over an estimated
    // span).
    step.duration = { certainty: attrs.durationKind || 'fixed' };

    if (attrs.onCollision) step.onCollision = attrs.onCollision;
    if (attrs.cue) step.cueName = attrs.cue;

    if (attrs.verb === 'set') {
      if (!attrs.field) throw new Error(`parseTimelineXml: set step "${attrs.id}" missing field`);
      let value = attrs.value;
      // Numeric coercion: field values are numbers far more often than
      // strings in this schema (visibility, walkPace, etc.) — attempt
      // numeric parse, fall back to the raw string for fields that are
      // genuinely string-valued (e.g. a mode/state field).
      const numeric = Number(value);
      if (value !== undefined && value !== '' && !Number.isNaN(numeric)) value = numeric;
      step.fieldWrite = {
        field: attrs.field,
        value,
        priority: attrs.priority || 'continuous',
      };
    }

    // camera-kind-specific, passed through as-is for the caller/renderer —
    // dispatcher.js doesn't interpret these itself (no camera-specific
    // logic in the dispatch engine per the Actor doc's "no new mechanism"
    // claim for cameras), they just ride along on the step object.
    if (attrs.cameraType) step.cameraType = attrs.cameraType;
    if (attrs.target) step.target = attrs.target;
    if (attrs.viewpoint) step.viewpoint = attrs.viewpoint;

    return step;
  }

  // ── parse <Actor>/<Track>/<Step> and register everything with a live
  //    Dispatcher instance ────────────────────────────────────────────
  // fieldMaps: caller-supplied { actorType -> manifest }, merged with
  // (and overriding) whatever fieldMap MetadataSet blocks are embedded in
  // the scene XML itself — useful for tests or partial scenes that don't
  // carry their own manifests yet.
  function loadTimelineIntoDispatcher(dispatcher, sceneXml, fieldMaps) {
    const sceneFieldMaps = parseFieldMapsFromScene(sceneXml);
    const effectiveFieldMaps = Object.assign({}, sceneFieldMaps, fieldMaps || {});
    const cues = parseCues(sceneXml);

    const actorRe = /<Actor\s+([^>]*?)>([\s\S]*?)<\/Actor>/g;
    let am;
    const allSteps = [];
    while ((am = actorRe.exec(sceneXml)) !== null) {
      const actorAttrs = getAttrs(am[1]);
      const actorBody = am[2];
      const actorId = actorAttrs.name;
      if (!actorId) throw new Error('parseTimelineXml: <Actor> missing name');

      // Look up this Actor's field map by its `type` attribute — a manifest
      // is per actorType (Actor Doc §4), shared across every instance of
      // that type, not authored per-instance. Absent manifest -> legal
      // empty field map (§4.1: "an Actor with no manifest at all is not
      // legal to export" is an *export-time* rule for the real pipeline;
      // this loader tolerates it so partial/test scenes still load,
      // rather than hard-failing here).
      const fieldMap = effectiveFieldMaps[actorAttrs.type] || { fields: [] };
      const trackDefs = {};

      const trackRe = /<Track\s+([^>]*?)>([\s\S]*?)<\/Track>/g;
      let tm;
      const trackSteps = [];
      while ((tm = trackRe.exec(actorBody)) !== null) {
        const trackAttrs = getAttrs(tm[1]);
        const trackBody = tm[2];
        if (!trackAttrs.id) throw new Error(`parseTimelineXml: <Track> on Actor "${actorId}" missing id`);
        trackDefs[trackAttrs.id] = { kind: trackAttrs.kind };

        const stepRe = /<Step\s+([^>]*?)\/?>/g;
        let sm;
        while ((sm = stepRe.exec(trackBody)) !== null) {
          const stepAttrs = getAttrs(sm[1]);
          trackSteps.push(stepFromAttrs(stepAttrs, actorId, trackAttrs.id));
        }
      }

      dispatcher.registerActor(actorId, fieldMap, trackDefs);
      trackSteps.forEach((s) => allSteps.push(s));

      // Dialogue lines aren't generic <Step> XML (schema §6 — they're the
      // Actor's existing <Dialogue> block), but per Actor Doc's own model
      // dialogue is "just its own track... using the same five verbs" —
      // a line has to actually be registered as a dispatcher step, or a
      // `sensed` trigger on a dialogue line can never fire (nothing would
      // ever call addStep for it, so arrived() on the step it references
      // would have nothing to chain into). One synthetic 'dialogue' track
      // per Actor, Welder-style displacement included, same as any other
      // track kind — a second line starting while one is still running
      // displaces it exactly like a gesture or camera cut would.
      const dialogueLines = MCCFDialogue.parseDialogueBlock(actorBody);
      if (dialogueLines.length) {
        dispatcher.actors[actorId].tracks.dialogue = { kind: 'dialogue', activeStepId: null };
        dialogueLines.forEach((line) => {
          const trigger = parseStepTrigger(MCCFDialogue.serializeTrigger(line.trigger));
          allSteps.push({
            id: line.id,
            actorId,
            trackId: 'dialogue',
            verb: 'start',
            trigger,
            duration: { certainty: line.mode === 'improv' ? 'estimate' : 'fixed' },
          });
        });
      }
    }

    allSteps.forEach((s) => dispatcher.addStep(s));

    return { cues, stepCount: allSteps.length, actorCount: Object.keys(dispatcher.actors).length };
  }

  return { parseStepTrigger, parseCues, stepFromAttrs, extractFieldMapBlocks, parseFieldMapsFromScene, loadTimelineIntoDispatcher };
});
