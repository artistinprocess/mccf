// Boots static/mccf_ambient.html in jsdom with mock canvas / Web MIDI / Worker so page logic can be driven from Node.
const path = require('path'), fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');
exports.boot = async function (htmlFile) {
  const errors = [], logs = [], sent = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => errors.push('jsdomError: ' + (e.detail && e.detail.message || e.message)));
  vc.on('error', e => errors.push('console.error: ' + e)); vc.on('log', e => logs.push(e)); vc.on('warn', e => logs.push('warn: ' + e));
  const dom = await JSDOM.fromFile(htmlFile || path.join(__dirname, '../static/mccf_ambient.html'), {
    runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) {
      const noop = () => {}, ctx = new Proxy({}, { get: (t, k) => k === 'canvas' ? {} : (k === 'measureText' ? () => ({ width: 0 }) : (k === 'createLinearGradient' || k === 'createRadialGradient' ? () => ({ addColorStop: noop }) : noop)), set: () => true });
      w.HTMLCanvasElement.prototype.getContext = () => ctx;
      w.Worker = function () { this.postMessage = noop; this.terminate = noop; this.onmessage = null; };
      w.URL.createObjectURL = () => 'blob:mock'; w.URL.revokeObjectURL = noop;
      const out = { id: 'mock', name: 'MOTU UltraLite mock', send: (m, t) => sent.push([Array.from(m), t]), clear: noop };
      w.navigator.requestMIDIAccess = () => Promise.resolve({ outputs: new Map([['mock', out]]), inputs: new Map(), onstatechange: null });
      w.AudioContext = w.webkitAudioContext = function () { const n = () => ({ connect: noop, disconnect: noop, gain: { value: 1, setValueAtTime: noop, linearRampToValueAtTime: noop, setTargetAtTime: noop, cancelScheduledValues: noop, exponentialRampToValueAtTime: noop }, frequency: { value: 0, setValueAtTime: noop, linearRampToValueAtTime: noop }, start: noop, stop: noop, type: '', buffer: null, Q: { value: 0 }, detune: { value: 0 } }); this.state = 'running'; this.currentTime = 0; this.destination = {}; this.sampleRate = 44100; this.resume = () => Promise.resolve(); ['createGain','createOscillator','createBiquadFilter','createBufferSource','createDynamicsCompressor','createConvolver','createDelay','createStereoPanner','createAnalyser','createWaveShaper'].forEach(k => this[k] = n); this.createBuffer = () => ({ getChannelData: () => new Float32Array(8) }); };
      w.fetch = () => Promise.reject(new Error('offline (test)'));
      w.matchMedia = () => ({ matches: false, addListener: noop, addEventListener: noop });
    }
  });
  await new Promise(r => { if (dom.window.document.readyState === 'complete') r(); else dom.window.addEventListener('load', r); });
  await new Promise(r => setTimeout(r, 50));
  return { dom, window: dom.window, document: dom.window.document, errors, logs, sent };
};
