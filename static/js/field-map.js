// MCCF field-map serialization — Day 72, build schedule item 2.
// Reference implementation of FIELD_MAP_FORMAT.md. No external dependencies
// (deliberately — this needs to run both in Node tooling and inside the
// browser-based composer without pulling in an XML library for a schema
// this constrained).
//
// Manifest shape (in-memory, what serialize/parse produce and consume):
//
//   {
//     actorType: 'Avatar',
//     fields: [
//       { name: 'idleGestureBias', reach: 'affect-writable',
//         channel: 'arousal', curve: 'direct',
//         range: 'calm(0.0) – wary(1.0)', arbitration: 'track-wins' },
//       { name: 'translation', reach: 'telemetry' },
//       ...
//     ]
//   }

const REACH_VALUES = ['track-only', 'affect-writable', 'telemetry'];
const CURVE_VALUES = ['direct', 'inverse', 'custom'];
const ARBITRATION_VALUES = ['replace', 'blend', 'track-wins'];
const AFFECT_ONLY_KEYS = ['channel', 'curve', 'arbitration'];

// ── validate ────────────────────────────────────────────────────────────
// Returns { valid: bool, errors: string[] }. Never throws — callers decide
// what to do with an invalid manifest (reject export, show in UI, etc).
function validateFieldMap(manifest) {
  const errors = [];
  if (!manifest || typeof manifest !== 'object') {
    return { valid: false, errors: ['manifest is missing or not an object'] };
  }
  if (!manifest.actorType || typeof manifest.actorType !== 'string') {
    errors.push('actorType is required');
  }
  const fields = Array.isArray(manifest.fields) ? manifest.fields : null;
  if (!fields) {
    errors.push('fields must be an array (use [] for a legal empty manifest, not undefined)');
    return { valid: errors.length === 0, errors };
  }

  const seenNames = new Set();
  fields.forEach((f, i) => {
    const where = `field[${i}]${f && f.name ? ' (' + f.name + ')' : ''}`;
    if (!f || typeof f !== 'object') {
      errors.push(`${where}: not an object`);
      return;
    }
    if (!f.name || typeof f.name !== 'string') {
      errors.push(`${where}: missing name`);
    } else if (seenNames.has(f.name)) {
      errors.push(`${where}: duplicate field name "${f.name}" — field names must be unique within an Actor type (same identity discipline as build item 1)`);
    } else {
      seenNames.add(f.name);
    }
    if (!REACH_VALUES.includes(f.reach)) {
      errors.push(`${where}: reach must be one of ${REACH_VALUES.join(' | ')}, got "${f.reach}"`);
    }
    const isAffect = f.reach === 'affect-writable';
    AFFECT_ONLY_KEYS.forEach((key) => {
      const present = f[key] !== undefined && f[key] !== null && f[key] !== '';
      if (isAffect && !present) {
        errors.push(`${where}: "${key}" is required when reach is affect-writable`);
      }
      if (!isAffect && present) {
        errors.push(`${where}: "${key}" is only legal when reach is affect-writable (this field is "${f.reach}")`);
      }
    });
    if (isAffect && f.curve && !CURVE_VALUES.includes(f.curve)) {
      errors.push(`${where}: curve must be one of ${CURVE_VALUES.join(' | ')}, got "${f.curve}"`);
    }
    if (isAffect && f.arbitration && !ARBITRATION_VALUES.includes(f.arbitration)) {
      errors.push(`${where}: arbitration must be one of ${ARBITRATION_VALUES.join(' | ')}, got "${f.arbitration}"`);
    }
  });

  return { valid: errors.length === 0, errors };
}

// ── serialize ───────────────────────────────────────────────────────────
function xmlEscape(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// X3D MFString/SFString attribute values are quoted; embedded quotes are
// escaped per X3D XML encoding rules (a literal double-quote inside the
// value becomes \").
function quoteX3DString(s) {
  return '"' + String(s).replace(/"/g, '\\"') + '"';
}

function serializeFieldMap(manifest) {
  const { valid, errors } = validateFieldMap(manifest);
  if (!valid) {
    throw new Error('serializeFieldMap: refusing to serialize an invalid manifest:\n' + errors.join('\n'));
  }
  const lines = [];
  lines.push(`<MetadataSet name='fieldMap' DEF='FieldMap_${xmlEscape(manifest.actorType)}'>`);
  lines.push(`  <MetadataString name='actorType' value='${quoteX3DString(manifest.actorType)}'/>`);
  manifest.fields.forEach((f) => {
    lines.push(`  <MetadataSet name='field:${xmlEscape(f.name)}'>`);
    lines.push(`    <MetadataString name='reach' value='${quoteX3DString(f.reach)}'/>`);
    if (f.reach === 'affect-writable') {
      lines.push(`    <MetadataString name='channel' value='${quoteX3DString(f.channel)}'/>`);
      lines.push(`    <MetadataString name='curve' value='${quoteX3DString(f.curve)}'/>`);
      lines.push(`    <MetadataString name='arbitration' value='${quoteX3DString(f.arbitration)}'/>`);
    }
    if (f.range !== undefined && f.range !== null && f.range !== '') {
      lines.push(`    <MetadataString name='range' value='${quoteX3DString(f.range)}'/>`);
    }
    lines.push(`  </MetadataSet>`);
  });
  lines.push(`</MetadataSet>`);
  return lines.join('\n');
}

// ── parse ───────────────────────────────────────────────────────────────
// Hand-rolled, deliberately not a general XML parser: the format this reads
// is fully controlled (we also write it), so a general parser is more
// machinery than the problem needs. This is tolerant of the field-level
// MetadataSet blocks appearing in any order and of extraneous whitespace,
// but strict about the actual schema rules (see validateFieldMap).

function extractAttr(tag, attrName) {
  // attribute values are single-quoted per this format's own serializer;
  // match non-greedily up to the closing single quote.
  const m = tag.match(new RegExp(`${attrName}='([^']*)'`));
  return m ? m[1] : null;
}

function unquoteX3DString(raw) {
  // raw is like `"actual value"` (with escaped \" inside) per quoteX3DString
  if (raw === null) return null;
  const trimmed = raw.trim();
  if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
    return trimmed.slice(1, -1).replace(/\\"/g, '"');
  }
  return trimmed; // tolerate an unquoted value rather than hard-failing
}

function parseFieldMap(xml) {
  if (typeof xml !== 'string') {
    throw new Error('parseFieldMap: expected an XML string');
  }
  const outerMatch = xml.match(/<MetadataSet\s+name='fieldMap'[^>]*>([\s\S]*)<\/MetadataSet>\s*$/);
  if (!outerMatch) {
    throw new Error('parseFieldMap: no fieldMap MetadataSet found — an Actor type with no manifest at all is not legal to export (rule 1)');
  }
  const body = outerMatch[1];

  const actorTypeMatch = body.match(/<MetadataString\s+name='actorType'\s+value='([^']*)'\s*\/>/);
  if (!actorTypeMatch) {
    throw new Error('parseFieldMap: fieldMap is missing its actorType MetadataString');
  }
  const actorType = unquoteX3DString(actorTypeMatch[1]);

  const fields = [];
  const fieldBlockRe = /<MetadataSet\s+name='field:([^']*)'\s*>([\s\S]*?)<\/MetadataSet>/g;
  let fm;
  while ((fm = fieldBlockRe.exec(body)) !== null) {
    const name = fm[1];
    const inner = fm[2];
    const field = { name };
    const stringRe = /<MetadataString\s+name='([^']*)'\s+value='([^']*)'\s*\/>/g;
    let sm;
    while ((sm = stringRe.exec(inner)) !== null) {
      field[sm[1]] = unquoteX3DString(sm[2]);
    }
    fields.push(field);
  }

  const manifest = { actorType, fields };
  const { valid, errors } = validateFieldMap(manifest);
  if (!valid) {
    throw new Error('parseFieldMap: parsed manifest failed validation:\n' + errors.join('\n'));
  }
  return manifest;
}

// Works two ways, deliberately: `require`d by test-field-map.js under Node,
// and dropped in as a plain <script src="field-map.js"> next to the composer
// HTML with no bundler. A bare `module.exports = ...` breaks the second case
// outright (ReferenceError: module is not defined in a browser with no
// CommonJS shim) — this project's existing composer/prototype files are
// single unbundled <script> blocks, so that's the case to assume by default.
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api; // Node / test-field-map.js
  } else {
    root.MCCFFieldMap = api; // plain browser script tag: window.MCCFFieldMap.validateFieldMap(...)
  }
})(typeof self !== 'undefined' ? self : this, function () {
  return { validateFieldMap, serializeFieldMap, parseFieldMap };
});
