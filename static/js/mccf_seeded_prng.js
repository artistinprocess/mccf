// ═══════════════════════════════════════════════════════════════════════
// MCCF Seeded PRNG — gesture constellation §6
// ═══════════════════════════════════════════════════════════════════════
//
// Every random draw used by the stagger and selection mechanisms (§2b
// weighted selection, §5 jitter) must go through this module — never
// Math.random() directly. Run-to-run variation is a deliberate design
// choice, not a flaw (§6), but every run's actual variation has to be
// reproducible on demand: "did this run diverge because of a real
// interaction effect, or because the stagger rolled differently" needs
// to be an answerable question.
//
// THIS FILE IS SELF-CONTAINED. It does not know about scene control or
// /arc/export — those are two other files I don't have. Integration
// points are marked "HOOK:" below; wire them in at the call sites noted.
//
// ─────────────────────────────────────────────────────────────────────
// Algorithm choice
// ─────────────────────────────────────────────────────────────────────
// xmur3 (string→32-bit hash, for turning an arbitrary seed value into
// well-distributed internal state) feeding mulberry32 (fast, simple,
// good-enough statistical quality for visual/behavioral randomness —
// this is not cryptographic use, so a heavier PRNG like sfc32 or PCG
// would be unnecessary complexity here). Both are widely-used, publicly
// documented small-PRNG constructions, not novel — chosen for being
// small, dependency-free, and easy to audit by reading the ~15 lines
// each takes.
// ─────────────────────────────────────────────────────────────────────

var MCCF_PRNG = (function () {

  // ---- xmur3: string → 32-bit hash, used to seed mulberry32's state ----
  function xmur3(str) {
    var h = 1779033703 ^ str.length;
    for (var i = 0; i < str.length; i++) {
      h = Math.imul(h ^ str.charCodeAt(i), 3432918353);
      h = (h << 13) | (h >>> 19);
    }
    return function () {
      h = Math.imul(h ^ (h >>> 16), 2246822507);
      h = Math.imul(h ^ (h >>> 13), 3266489909);
      h ^= h >>> 16;
      return h >>> 0;
    };
  }

  // ---- mulberry32: 32-bit state → [0,1) float stream ----
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // ---- internal state: one generator per named stream ----
  // Streams matter because §5 explicitly separates "not pure random
  // jitter" (per-gesture-type typical lag, deterministic) from actual
  // jitter layered on top, and §2b separates eligibility (not random at
  // all) from weighted selection (random). Giving stagger-jitter and
  // selection their own independent streams — rather than one shared
  // generator — means adding/removing a selection draw doesn't shift
  // every subsequent jitter draw's value, and vice versa. Both streams
  // still derive from the same resolved run seed, so the whole run is
  // still reproducible as one unit.
  var _streams = {};        // name -> mulberry32 generator function
  var _resolvedSeed = null; // HOOK 2 reads this — see bottom of file
  var _resolvedSeedSource = null; // 'explicit' | 'randomized'

  function _makeStream(name, seedStr) {
    var hashFn = xmur3(seedStr + '::' + name);
    _streams[name] = mulberry32(hashFn());
  }

  // ---- HOOK 1: call this once per run, before anything else draws ----
  // baseSeed comes from scene control (§6: "Base/default seed lives in
  // scene control, including 'unset = randomize' as a valid state").
  // Pass whatever scene control currently holds — a number, a string,
  // or null/undefined/'' for "unset". This function is where "unset =
  // randomize" is actually implemented: an unset base seed does NOT mean
  // "call Math.random() elsewhere" — it means generate one real seed
  // here, once, and use it consistently for the rest of the run.
  function beginRun(baseSeed) {
    var isUnset = (baseSeed === null || baseSeed === undefined || baseSeed === '');
    var resolved;

    if (isUnset) {
      // Randomize: crypto source if available (better distribution,
      // not security-critical here but no reason not to use it when
      // present), falling back to Date.now()/performance.now() jitter
      // if crypto isn't available in this context.
      if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
        var buf = new Uint32Array(1);
        crypto.getRandomValues(buf);
        resolved = buf[0].toString(36);
      } else {
        resolved = (Date.now().toString(36) + Math.floor(
          (typeof performance !== 'undefined' ? performance.now() : 0) * 1000
        ).toString(36));
      }
      _resolvedSeedSource = 'randomized';
    } else {
      resolved = String(baseSeed);
      _resolvedSeedSource = 'explicit';
    }

    _resolvedSeed = resolved;
    _streams = {}; // fresh streams for the new run — no bleed from a prior run

    console.log('[MCCF_PRNG] beginRun: seed=' + resolved +
      ' (' + _resolvedSeedSource + ')');

    return resolved;
  }

  // ---- Named-stream access ----
  // First call for a given stream name lazily creates it from the
  // current resolved seed. Calling beginRun() again (new run) resets
  // all streams, so stale generators from a previous run can't leak in.
  function _stream(name) {
    if (_resolvedSeed === null) {
      console.warn('[MCCF_PRNG] stream "' + name + '" requested before ' +
        'beginRun() was called — auto-randomizing so this still produces ' +
        'a value rather than a crash. This run will NOT be reproducible ' +
        'unless the resolved seed logged below is captured. Fix the call ' +
        'order: scene control resolves the base seed → beginRun() → ' +
        'gesture/stagger code runs.');
      beginRun(null);
    }
    if (!_streams[name]) _makeStream(name, _resolvedSeed);
    return _streams[name];
  }

  // ---- Public draw functions — drop-in replacements for Math.random() ----

  // random(streamName) → float in [0, 1)
  // streamName defaults to 'default' — pass an explicit name (e.g.
  // 'selection', 'stagger') to keep streams independent per §5/§2b.
  function random(streamName) {
    return _stream(streamName || 'default')();
  }

  // randomRange(min, max, streamName) → float in [min, max)
  function randomRange(min, max, streamName) {
    return min + random(streamName) * (max - min);
  }

  // randomInt(min, max, streamName) → integer in [min, max] inclusive
  function randomInt(min, max, streamName) {
    return Math.floor(randomRange(min, max + 1, streamName));
  }

  // choice(array, streamName) → one element, uniform
  function choice(arr, streamName) {
    if (!arr || !arr.length) return undefined;
    return arr[randomInt(0, arr.length - 1, streamName)];
  }

  // weightedChoice(items, streamName) → one item, per §2b "weighted
  // selection within the eligible set". items: [{item, weight}, ...].
  // Weights need not sum to 1 — normalized internally.
  function weightedChoice(items, streamName) {
    if (!items || !items.length) return undefined;
    var total = 0;
    for (var i = 0; i < items.length; i++) total += (items[i].weight || 0);
    if (total <= 0) return choice(items.map(function (it) { return it.item; }), streamName);
    var r = random(streamName) * total;
    var acc = 0;
    for (var j = 0; j < items.length; j++) {
      acc += (items[j].weight || 0);
      if (r < acc) return items[j].item;
    }
    return items[items.length - 1].item; // float rounding fallback
  }

  // ---- HOOK 2: call this when building the /arc/export payload ----
  // §6: "The resolved seed actually used for a given run is recorded in
  // that run's own Scene Arc export ... since only a per-run record
  // makes 're-run this exact run' possible." Whatever code assembles the
  // /arc/export payload should call this and include the result — e.g.
  // as a top-level `resolvedSeed` / `resolvedSeedSource` field alongside
  // the ordered beats it already records.
  function getResolvedSeedForExport() {
    return {
      resolvedSeed: _resolvedSeed,
      source: _resolvedSeedSource // 'explicit' | 'randomized' | null if beginRun() never ran
    };
  }

  return {
    beginRun: beginRun,
    random: random,
    randomRange: randomRange,
    randomInt: randomInt,
    choice: choice,
    weightedChoice: weightedChoice,
    getResolvedSeedForExport: getResolvedSeedForExport
  };

})();
