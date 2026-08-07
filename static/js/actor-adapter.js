// MCCF Actor export-boundary adapter — Day 78, V5 Tasklist Phase 1 task 1.
//
// What this is: the reconciliation point between Composer's authoring-side
// state (`placedAgents`/`placedCameras`/`zones`, three independently-keyed
// objects in `mccf_scene_composer.html`) and the uniform Actor view the
// Design Doc (`MCCF_Actor_Architecture_Design_v0.2.md` §2) and the Phase 4
// generator both expect: `{ fields, tracks, coordinator }` per Actor.
//
// What this deliberately does NOT do: touch `placedAgents`/`placedCameras`
// themselves. The V5 Tasklist's §1 (composer-implementation question) is
// settled as of Day 78 — "leaning further toward zero changes needed" to
// Composer's own in-memory shape, confirmed by the Tasklist's own heading
// change from "Phase 1 — Settle the one remaining open fork" to "Phase 1 —
// No longer a decision, an implementation task." Composer keeps authoring
// by `placedAgents`/`placedCameras`/`zones` exactly as it does today
// (Design Doc §2's "convenience layer for the human, not a second runtime
// noun"); this module is the export/generator-boundary translation, called
// only when something downstream (validation today, the Phase 4 generator
// later) actually needs the Actor view.
//
// Zones are NOT converted into Actors. Design Doc §2 is explicit and
// deliberate about this: "A Zone is a spatial trigger source — it fires
// events into Actors — but it has no field map and no tracks of its own.
// Collapsing Zones into Actors would blur 'the thing that fires the verb'
// with 'the thing that receives it.'" `zones` is passed through unconverted
// so a `zone`-type trigger (dialogue-xml.js's TRIGGER_KINDS) still has
// something to resolve a zone id against, but zones never appear in the
// returned `actors` map.
//
// A real gap this reconciliation surfaces, not previously checked anywhere:
// Composer's own `registerId()` (mccf_scene_composer.html) guards id
// uniqueness only WITHIN one scope map at a time — `zones`, `placedCameras`,
// and `placedAgents` are three independent namespaces today, so an author
// can currently place an Avatar named "Alice" and a Camera named "Alice" in
// the same scene with no warning. dispatcher.js's `this.actors` is one flat
// object (confirmed by reading `registerActor()`), and Timeline XML's
// `<Actor name="...">` / `<Step trigger="zone:...">` resolve against that
// same flat, scene-wide id space (confirmed by reading `timeline-xml.js`).
// A same-named Avatar and Camera would silently collide the moment this
// adapter (or the real generator) tries to build one registry from three
// separately-guarded namespaces. This adapter refuses to build a registry
// when that happens (see `errors` below) rather than silently renaming —
// renaming would break the match between what the author typed in Composer
// and what a Timeline/Dialogue authoring surface would need to reference by
// that same name.
//
// Camera field map: NOT one of the three "worked manifests" in
// `worked-manifests.js` (that file's own header says it's sourced from
// Design Doc §4.2, which only worked Avatar/SceneFog/Door — Camera was
// never given a worked example). Rather than inventing affect-writable
// semantics nothing in the source docs asked for (a channel-driven roll or
// FOV, say), this adapter declares Camera's field map EMPTY — "this Actor
// is narrative-inert, tracks-only, not affect-reachable" is a legal, honest
// declaration per Design Doc §4.1, and matches the fact that nothing in
// Camera Spec, the Avatar Camera Rig spec, or the Actor Architecture doc
// ever proposes a camera responding to an emotion channel directly (only
// camera CUTS fire, via the `cuts` track's `start` verb, same as any other
// Welder-arbitrated track — Design Doc §5.1/§7). Flagged explicitly as a
// judgment call in `DEFAULT_FIELD_MAPS.Camera` below — extend it the moment
// a real affect-writable camera field is actually wanted, don't treat this
// as load-bearing today.
//
// Track seeding is intentionally minimal. Per Design Doc §6/§7:
//   - Avatar  -> one `path` track (kind 'path'). Composer already has a
//     paths{}/waypoints{}-driven playback concept; this is that Actor's
//     placeholder slot for it, nothing more, at this phase.
//   - Camera  -> one `cuts` track (kind 'camera'), per §7.
// No `gesture`/`dialogue` tracks are seeded here — those are authored by
// the not-yet-built Timeline/Dialogue editor (the actual V5 work, Phase 4),
// which will add tracks to whatever Actor registry this adapter produces.
// This module's job stops at "does a scene-consistent Actor exist to add
// tracks to," not "author the tracks."
//
// Same house style as field-map.js/dispatcher.js/timeline-xml.js: hand-
// rolled, zero dependencies beyond the two sibling modules it explicitly
// needs, UMD-wrapped so it works under Node (tests) and as a plain
// `<script src="actor-adapter.js">` next to Composer with no bundler.

(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.MCCFActorAdapter = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {

  // ── dependencies ─────────────────────────────────────────────────────
  // Needs field-map.js (to validate the field maps it hands out) and
  // worked-manifests.js (the real, author-confirmed Avatar manifest — this
  // module does not reinvent that one). Same require/global pattern
  // timeline-xml.js already uses for its own two dependencies.
  let MCCFFieldMap, MCCFWorkedManifests;
  if (typeof module !== 'undefined' && module.exports) {
    MCCFFieldMap = require('./field-map.js');
    MCCFWorkedManifests = require('./worked-manifests.js');
  } else if (typeof self !== 'undefined' && self.MCCFFieldMap && self.MCCFWorkedManifests) {
    MCCFFieldMap = self.MCCFFieldMap;
    MCCFWorkedManifests = self.MCCFWorkedManifests;
  } else {
    throw new Error('MCCFActorAdapter requires MCCFFieldMap (field-map.js) and MCCFWorkedManifests (worked-manifests.js) to be loaded first.');
  }

  // ── default field maps per actorType this adapter can produce ─────────
  // Avatar: the real, author-confirmed manifest (Design Doc §4.2). Not
  // reinvented here.
  // Camera: proposed by this adapter, not a worked manifest — see the
  // file-header note above. Empty fields array is a deliberate, honest
  // "track-only, not affect-reachable" declaration (Design Doc §4.1),
  // not a placeholder that got forgotten.
  const DEFAULT_FIELD_MAPS = {
    Avatar: MCCFWorkedManifests.AVATAR,
    Camera: { actorType: 'Camera', fields: [] },
  };

  // Self-check both default manifests through the real validator at load
  // time — same "always re-verify" discipline as the rest of this
  // codebase (Day 77 seed doc's own closing note). A malformed default
  // here should fail loudly on load, not silently produce Actors that
  // choke the first time something calls registerActor() on them.
  Object.keys(DEFAULT_FIELD_MAPS).forEach((actorType) => {
    const { valid, errors } = MCCFFieldMap.validateFieldMap(DEFAULT_FIELD_MAPS[actorType]);
    if (!valid) {
      throw new Error('MCCFActorAdapter: built-in field map for "' + actorType + '" is invalid:\n' + errors.join('\n'));
    }
  });

  // ── cross-namespace id collision check ─────────────────────────────
  // Composer's own registerId() only guards uniqueness within a single
  // scope map (zones vs placedCameras vs placedAgents are checked
  // separately, confirmed by reading each call site). This is the one
  // check that actually spans all three, because the flat Actor/Track/
  // Step id space downstream needs it to.
  function findCrossNamespaceCollisions(placedAgents, placedCameras, zones) {
    const seenIn = {}; // name -> [namespace, ...]
    function note(name, ns) {
      (seenIn[name] = seenIn[name] || []).push(ns);
    }
    Object.keys(placedAgents).forEach((n) => note(n, 'Avatar'));
    Object.keys(placedCameras).forEach((n) => note(n, 'Camera'));
    Object.keys(zones).forEach((n) => note(n, 'Zone (trigger source, not an Actor)'));

    const collisions = [];
    Object.keys(seenIn).forEach((name) => {
      if (seenIn[name].length > 1) {
        collisions.push({ name, namespaces: seenIn[name] });
      }
    });
    return collisions;
  }

  // ── the adapter itself ─────────────────────────────────────────────
  // state: { placedAgents, placedCameras, zones } — pass Composer's own
  //        live objects directly; nothing here mutates them.
  // opts.fieldMaps: optional { Avatar?, Camera? } override for either
  //        default manifest (e.g. a future non-default Camera field map,
  //        or a test double) — merged over DEFAULT_FIELD_MAPS, not
  //        replacing the whole set.
  //
  // Returns { actors, zones, errors }:
  //   actors — { actorId: { id, actorType, fieldMap, trackDefs, instance } },
  //            empty if there were any cross-namespace id collisions.
  //   zones  — passthrough of the input `zones`, unconverted (trigger
  //            sources, not Actors — see file header).
  //   errors — string[], empty on a clean build. Non-empty means `actors`
  //            is empty too: this adapter refuses a partial/ambiguous
  //            registry rather than silently building around a real
  //            id collision.
  function buildActorRegistry(state, opts) {
    opts = opts || {};
    const placedAgents = state.placedAgents || {};
    const placedCameras = state.placedCameras || {};
    const zones = state.zones || {};
    const fieldMaps = Object.assign({}, DEFAULT_FIELD_MAPS, opts.fieldMaps || {});

    const errors = [];
    const collisions = findCrossNamespaceCollisions(placedAgents, placedCameras, zones);
    collisions.forEach((c) => {
      errors.push(
        `id "${c.name}" is used by more than one namespace (${c.namespaces.join(', ')}). ` +
        `Composer's registerId() only guards uniqueness within a single type today, but the ` +
        `Actor/Track/Step model needs one flat scene-wide id space (dispatcher.js's this.actors ` +
        `is a single object; Timeline XML's <Actor name="..."> and <Step trigger="zone:..."> both ` +
        `resolve against that same flat space). Rename one before this scene can build a valid ` +
        `Actor registry.`
      );
    });

    if (errors.length) {
      return { actors: {}, zones, errors };
    }

    const actors = {};

    Object.keys(placedAgents).forEach((name) => {
      const a = placedAgents[name];
      actors[name] = {
        id: name,
        actorType: 'Avatar',
        fieldMap: fieldMaps.Avatar,
        trackDefs: { path: { kind: 'path' } },
        // Composer-side authoring data, carried through unconverted for
        // whatever consumes this next (generator, validation UI, etc.) —
        // not part of the Actor/field-map/track model itself.
        instance: {
          position: a.position, color: a.color, weights: a.weights,
          regulation: a.regulation, disposition: a.disposition,
          voice: a.voice, hanim_src: a.hanim_src, hanim_loa: a.hanim_loa,
        },
      };
    });

    Object.keys(placedCameras).forEach((name) => {
      const c = placedCameras[name];
      actors[name] = {
        id: name,
        actorType: 'Camera',
        fieldMap: fieldMaps.Camera,
        trackDefs: { cuts: { kind: 'camera' } },
        instance: { position: c.position, hAngle: c.hAngle, vAngle: c.vAngle, roll: c.roll },
      };
    });

    return { actors, zones, errors };
  }

  // ── convenience: push a built registry straight into a live Dispatcher ──
  // Thin wrapper over dispatcher.js's own registerActor() — this module
  // doesn't reimplement registration, just supplies the (actorId, fieldMap,
  // trackDefs) triple per Actor in the order dispatcher.js expects them.
  function registerWithDispatcher(dispatcher, registry) {
    if (registry.errors && registry.errors.length) {
      throw new Error('registerWithDispatcher: refusing to register a registry that failed validation:\n' + registry.errors.join('\n'));
    }
    Object.keys(registry.actors).forEach((id) => {
      const a = registry.actors[id];
      dispatcher.registerActor(a.id, a.fieldMap, a.trackDefs);
    });
    return dispatcher;
  }

  return { DEFAULT_FIELD_MAPS, buildActorRegistry, registerWithDispatcher, findCrossNamespaceCollisions };
});
