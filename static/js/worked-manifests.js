// The three worked manifests from MCCF_Actor_Architecture_Design_v0.2.md §4.2,
// moved from prose table to serializable artifact per build-schedule item 2.

const AVATAR = {
  actorType: 'Avatar',
  fields: [
    {
      name: 'idleGestureBias',
      reach: 'affect-writable',
      channel: 'arousal',
      curve: 'direct',
      range: 'calm(0.0) – wary(1.0)',
      arbitration: 'track-wins', // only meaningful while idle; a running gesture track owns the skeleton outright
    },
    {
      name: 'walkPace',
      reach: 'affect-writable',
      channel: 'arousal',
      curve: 'direct',
      range: '0.9 – 1.6 (m/s)',
      arbitration: 'blend', // affect nudges the recorded pace, doesn't replace it
    },
    {
      name: 'poemLine / dialogueText',
      reach: 'track-only', // owned by the dialogue track; not affect-writable
    },
    {
      name: 'translation',
      reach: 'telemetry',
    },
  ],
};

const SCENE_FOG = {
  actorType: 'SceneFog',
  fields: [
    {
      name: 'visibility',
      reach: 'affect-writable',
      channel: 'tension',
      curve: 'inverse', // higher tension -> lower visibility
      range: '2000 – 80',
      arbitration: 'replace', // no competing track; nothing else claims it
    },
    {
      name: 'color',
      reach: 'affect-writable',
      channel: 'valence',
      curve: 'custom', // warm ochre -> cold blue-grey, not a scalar lerp
      arbitration: 'replace',
    },
    {
      name: 'cycleInterval',
      reach: 'track-only', // day/night cycle; not narrative-reachable
    },
  ],
};

const DOOR = {
  actorType: 'Door',
  fields: [
    {
      name: 'hingeAngle',
      reach: 'track-only',
    },
    {
      name: 'swingSpeed',
      reach: 'affect-writable',
      channel: 'tension',
      curve: 'direct',
      range: '0.6x – 1.3x nominal',
      arbitration: 'blend',
    },
  ],
};

// Day 74 — browser export path added, same fix and same reasoning as
// dispatcher.js: a bare module.exports throws ReferenceError in a browser
// with no CommonJS shim. Node behavior unchanged.
const _manifestExports = { AVATAR, SCENE_FOG, DOOR };
if (typeof module !== 'undefined' && module.exports) {
  module.exports = _manifestExports;
} else {
  (typeof self !== 'undefined' ? self : this).MCCFWorkedManifests = _manifestExports;
}
