// MCCF Path Recorder — core module. Day 78, V5 Tasklist Phase 2, tasks 3 & 4.
//
// Two things, both pure/testable, no DOM or X3D dependency:
//   1. RDP (Ramer-Douglas-Peucker) decimation of a captured position stream
//      (Tasklist §6 item 4: "RDP is the standard, proven algorithm for this
//      exact problem... one tolerance value, naturally denser where the path
//      actually curves, sparser where it's straight" — chosen explicitly over
//      a distance/angle streaming threshold).
//   2. The new independent recorded-path data structure (Tasklist §5's "Also
//      proposed, needs confirmation" item, now built) — NOT an extension of
//      Composer's existing `paths{}`. Today's `<Path agent="...">` bakes in
//      single-agent ownership (confirmed by reading `mccf_scene_composer.html`'s
//      own exportSceneXML — every `<Path>` element carries a required `agent`
//      attribute). A captured fly-mode path is explicitly meant to be reusable
//      across objects (Tasklist §5: "the same named path could plausibly drive
//      more than one object, or the same object along different paths at
//      different times") — reusing `<Path>`'s shape would misrepresent that as
//      ownership it doesn't have. This module's `<RecordedPath>` shape is
//      deliberately separate, not a variant of `<Path>`.
//
// What this module does NOT do: capture the live samples (that needs a real
// X3D browser instance — addFieldCallback on the bound Viewpoint's own
// position/orientation fields, Tasklist §6 item 2 — and lives inline in
// mccf_events_editor_prototype_2.html, same as this codebase's other
// X3D-instance-specific code). This module starts from whatever raw sample
// array that capture code hands it.
//
// XML shape is PROPOSED here, not an author-confirmed format (same caveat as
// actor-adapter.js's Camera field map) — flagged plainly, easy to revise.
//
// Same house style as the sibling modules: hand-rolled, zero dependencies,
// UMD-wrapped for Node (tests) and plain <script src> use.

(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.MCCFPathRecorder = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {

  // ── geometry helpers ────────────────────────────────────────────────
  function sub(a, b) { return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]; }
  function dot(a, b) { return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]; }
  function cross(a, b) {
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
  }
  function mag(a) { return Math.sqrt(dot(a, a)); }

  // Perpendicular distance from point `p` to the line through `a`-`b` (3D).
  // Falls back to point-to-point distance when `a` and `b` coincide (a
  // degenerate "segment" — RDP's recursive calls can produce this at the
  // edges of a near-stationary capture, e.g. an author hovering in place).
  function perpendicularDistance(p, a, b) {
    var ab = sub(b, a);
    var abLen = mag(ab);
    if (abLen < 1e-9) return mag(sub(p, a));
    var ap = sub(p, a);
    return mag(cross(ap, ab)) / abLen;
  }

  // ── RDP decimation ──────────────────────────────────────────────────
  // points: array of plain [x,y,z] positions (already time-ordered).
  // Returns the surviving INDICES into the original array (not copies) —
  // callers that need to carry other per-sample data (orientation, t) along
  // just index back into their own array with these, rather than this
  // function needing to know about anything beyond position.
  function rdpIndices(points, epsilon) {
    if (!Array.isArray(points) || points.length < 3) {
      // Nothing to simplify — every point survives, including the
      // 0/1/2-point degenerate cases.
      return points ? points.map(function(_, i) { return i; }) : [];
    }
    var keep = new Array(points.length).fill(false);
    keep[0] = true;
    keep[points.length - 1] = true;

    // Iterative stack instead of recursive slicing (Tasklist's own worked
    // description is recursive, but slicing arrays at every level is
    // wasteful for a live-flown capture that could run to thousands of
    // samples before decimation — this produces the identical result,
    // index-based, without the repeated array copies).
    var stack = [[0, points.length - 1]];
    while (stack.length) {
      var range = stack.pop();
      var startIdx = range[0], endIdx = range[1];
      if (endIdx - startIdx < 2) continue;
      var a = points[startIdx], b = points[endIdx];
      var dmax = -1, idx = -1;
      for (var i = startIdx + 1; i < endIdx; i++) {
        var d = perpendicularDistance(points[i], a, b);
        if (d > dmax) { dmax = d; idx = i; }
      }
      if (dmax > epsilon) {
        keep[idx] = true;
        stack.push([startIdx, idx]);
        stack.push([idx, endIdx]);
      }
    }

    var result = [];
    for (var j = 0; j < keep.length; j++) if (keep[j]) result.push(j);
    return result;
  }

  // ── recorded-path data structure ────────────────────────────────────
  // rawSamples: [{ t, position:[x,y,z], orientation:[x,y,z,angle] }, ...]
  //   t          — seconds since capture start (monotonic, not wall-clock)
  //   position   — SFVec3f as a plain array
  //   orientation— SFRotation (axis-angle) as a plain 4-array
  // opts.tolerance — RDP epsilon in the position field's native units
  //   (scene meters). No universal default — worth tuning per capture; the
  //   UI should let the author see before/after sample counts (see
  //   `buildRecordedPath`'s returned `stats`) and re-run with a different
  //   tolerance rather than this module guessing one silently.
  //
  // Per Tasklist §6 item 4: "run RDP on position to decide which samples
  // survive, carry each surviving sample's already-captured orientation
  // along with it" — orientation is never independently decimated, only
  // carried. Known, accepted gap (not designed around pre-emptively): a
  // pure hover-and-pan capture (position barely moving, orientation
  // changing a lot) would lose those orientation changes, since RDP would
  // see a near-stationary position trace and keep almost nothing.
  function buildRecordedPath(rawSamples, opts) {
    opts = opts || {};
    if (!Array.isArray(rawSamples) || rawSamples.length === 0) {
      throw new Error('buildRecordedPath: rawSamples must be a non-empty array');
    }
    var tolerance = opts.tolerance !== undefined ? opts.tolerance : 0.15;
    var positions = rawSamples.map(function(s) { return s.position; });
    var survivingIdx = rdpIndices(positions, tolerance);

    var keys = survivingIdx.map(function(i) {
      var s = rawSamples[i];
      return {
        t: s.t,
        position: s.position.slice(),
        orientation: (s.orientation || [0, 1, 0, 0]).slice(),
      };
    });

    return {
      id: opts.id || null, // caller assigns — this module doesn't invent ids
      createdAt: opts.createdAt || new Date().toISOString(),
      tolerance: tolerance,
      keys: keys,
      stats: {
        rawSampleCount: rawSamples.length,
        decimatedKeyCount: keys.length,
        reductionPct: rawSamples.length > 0
          ? Math.round((1 - keys.length / rawSamples.length) * 100)
          : 0,
      },
    };
  }

  function validateRecordedPath(path) {
    var errors = [];
    if (!path || typeof path !== 'object') return { valid: false, errors: ['path is missing or not an object'] };
    if (!path.id || typeof path.id !== 'string') errors.push('id is required');
    if (!Array.isArray(path.keys) || path.keys.length < 2) errors.push('keys must be an array with at least 2 entries — a single point is not a path');
    (path.keys || []).forEach(function(k, i) {
      if (typeof k.t !== 'number') errors.push('keys['+i+']: t must be a number');
      if (!Array.isArray(k.position) || k.position.length !== 3) errors.push('keys['+i+']: position must be a 3-array');
      if (!Array.isArray(k.orientation) || k.orientation.length !== 4) errors.push('keys['+i+']: orientation must be a 4-array (axis-angle)');
    });
    // t must be non-decreasing — SplinePositionInterpolator/SquadOrientation-
    // Interpolator (the eventual consumer, task 5) both require strictly
    // ordered keys, same as any X3D Interpolator's `key` field.
    for (var j = 1; j < (path.keys || []).length; j++) {
      if (path.keys[j].t <= path.keys[j-1].t) {
        errors.push('keys['+j+']: t ('+path.keys[j].t+') must be strictly greater than keys['+(j-1)+']\'s t ('+path.keys[j-1].t+')');
      }
    }
    return { valid: errors.length === 0, errors: errors };
  }

  // ── XML serialization (PROPOSED format — see file header) ──────────
  function xmlEscape(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function serializeRecordedPath(path) {
    var v = validateRecordedPath(path);
    if (!v.valid) throw new Error('serializeRecordedPath: refusing to serialize an invalid path:\n' + v.errors.join('\n'));
    var lines = [];
    lines.push('<RecordedPath id="'+xmlEscape(path.id)+'" createdAt="'+xmlEscape(path.createdAt||'')+'" tolerance="'+(path.tolerance!==undefined?path.tolerance:'')+'">');
    path.keys.forEach(function(k) {
      lines.push('  <Key t="'+k.t.toFixed(3)+'" x="'+k.position[0].toFixed(4)+'" y="'+k.position[1].toFixed(4)+'" z="'+k.position[2].toFixed(4)+
        '" ax="'+k.orientation[0].toFixed(4)+'" ay="'+k.orientation[1].toFixed(4)+'" az="'+k.orientation[2].toFixed(4)+'" angle="'+k.orientation[3].toFixed(4)+'"/>');
    });
    lines.push('</RecordedPath>');
    return lines.join('\n');
  }

  function extractAttr(tag, name) {
    var m = tag.match(new RegExp(name + '="([^"]*)"'));
    return m ? m[1] : null;
  }

  function parseRecordedPath(xml) {
    if (typeof xml !== 'string') throw new Error('parseRecordedPath: expected an XML string');
    var outerMatch = xml.match(/<RecordedPath\s+([^>]*)>([\s\S]*?)<\/RecordedPath>/);
    if (!outerMatch) throw new Error('parseRecordedPath: no <RecordedPath> element found');
    var outerAttrs = outerMatch[1], body = outerMatch[2];
    var id = extractAttr(outerAttrs, 'id');
    var createdAt = extractAttr(outerAttrs, 'createdAt');
    var toleranceStr = extractAttr(outerAttrs, 'tolerance');

    var keys = [];
    var keyRe = /<Key\s+([^>]*)\/>/g;
    var m;
    while ((m = keyRe.exec(body)) !== null) {
      var a = m[1];
      keys.push({
        t: parseFloat(extractAttr(a, 't')),
        position: [parseFloat(extractAttr(a, 'x')), parseFloat(extractAttr(a, 'y')), parseFloat(extractAttr(a, 'z'))],
        orientation: [parseFloat(extractAttr(a, 'ax')), parseFloat(extractAttr(a, 'ay')), parseFloat(extractAttr(a, 'az')), parseFloat(extractAttr(a, 'angle'))],
      });
    }

    var path = {
      id: id,
      createdAt: createdAt,
      tolerance: toleranceStr !== null && toleranceStr !== '' ? parseFloat(toleranceStr) : undefined,
      keys: keys,
    };
    var v = validateRecordedPath(path);
    if (!v.valid) throw new Error('parseRecordedPath: parsed path failed validation:\n' + v.errors.join('\n'));
    return path;
  }

  return {
    rdpIndices,
    buildRecordedPath,
    validateRecordedPath,
    serializeRecordedPath,
    parseRecordedPath,
  };
});
