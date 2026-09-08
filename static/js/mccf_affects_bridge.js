// ══════════════════════════════════════════════════════════════════════
// MCCF Affects Bridge — client-side poll/push loop
//
// NOT YET INTEGRATED. This is written to be dropped into whatever page
// hosts the live X3D scene's X_ITE player (the "X3D Loader" page this
// project's design notes refer to) — that file wasn't available this
// session, so this exists as a standalone, ready module rather than a
// confirmed-working integration. It follows the exact SAI convention
// already established in mccf_character_creator.html's hePoseSendSAI
// (postMessage to the X_ITE frame, a listener injected into that frame
// interprets {type, ...} and does the real browser.currentScene calls) —
// not a new mechanism invented for this.
//
// What this closes: MCCF_Bridge (see mccf_api.py's export_x3d) declares
// per-agent arousal_/valence_/engagement_/E_/B_/P_/S_ outputOnly fields
// and a pos_<agent> inputOnly field, but nothing anywhere polls the API
// to set those outputs, and nothing pushes live scene positions back in.
// Confirmed directly: X_ITE's own Script sandbox can't do fetch()/XHR
// (same reasoning already documented in the Route Graph editor's own
// _introspectScript comment) — so this loop has to live in the hosting
// page's plain JavaScript, not inside the Script node itself.
//
// Two directions, one interval:
//   1. GET /bridge/affect  -> push each agent's 7 values onto MCCF_Bridge's
//      matching outputOnly fields. Any ROUTE already authored from those
//      fields (e.g. arousal_Anna -> BasicPointLight.intensity, wired in
//      the Route Graph editor) fires exactly as it would from any other
//      eventOut change — this loop's only job is making that change happen
//      on a real cadence, not anything about what the ROUTE does with it.
//   2. Read each agent's live Transform.translation -> POST /bridge/position
//      -> lets field_tick's proximity math and flat_affect_for_agent's
//      arousal term use real, current distance instead of the None they've
//      been silently getting (see /bridge/position's own docstring in
//      mccf_api.py for the full story on that gap).
//
// Usage, once dropped into the real hosting page:
//   MCCFAffectsBridge.start({
//     apiUrl: 'http://localhost:5000',
//     xiteFrame: document.getElementById('the-real-xite-frame-id'),
//     agentNames: ['Anna', 'Cindy', 'Jack'],   // must match export_x3d's own agent list exactly
//     intervalMs: 200,
//   });
// ══════════════════════════════════════════════════════════════════════

var MCCFAffectsBridge = (function () {
  var _cfg = null;
  var _timer = null;

  // Same postMessage convention as hePoseSendSAI — not a new one.
  function _sendSAI(msg) {
    if (_cfg.xiteFrame && _cfg.xiteFrame.contentWindow) {
      _cfg.xiteFrame.contentWindow.postMessage(msg, '*');
    }
  }

  // Pushes one agent's affect values onto MCCF_Bridge's matching fields.
  // Field names must match export_x3d's own naming exactly:
  // arousal_<safe>, valence_<safe>, engagement_<safe>, E_<safe>, B_<safe>,
  // P_<safe>, S_<safe> — 'safe' being the agent name with spaces replaced
  // by underscores, same transform export_x3d applies before naming fields.
  function _pushAffect(agentName, vals) {
    var safe = agentName.replace(/ /g, '_');
    ['arousal', 'valence', 'engagement', 'E', 'B', 'P', 'S'].forEach(function (ch) {
      if (vals[ch] === undefined) return;
      _sendSAI({
        type: 'setBridgeField',
        scriptDEF: 'MCCF_Bridge',
        field: ch + '_' + safe,
        value: vals[ch],
      });
    });
  }

  // Reads one agent's live position out of the scene and reports it back
  // to the API. Needs the SAI listener (see the injected-listener note at
  // the bottom of this file) to answer a 'getTranslation' request the
  // same way the Character Creator's own preview already answers
  // 'getJointRotation'/'getCoordPositions' — request/response over
  // postMessage, not a direct return value (there isn't one, across an
  // iframe boundary).
  function _pollPosition(agentName) {
    var reqId = 'pos_' + agentName + '_' + Date.now();
    _sendSAI({ type: 'getTranslation', nodeDEF: agentName, requestId: reqId });
    // The response arrives via the message listener below, matched on
    // requestId — see _onMessage.
    _pendingPositionRequests[reqId] = agentName;
  }

  var _pendingPositionRequests = {};

  function _onMessage(evt) {
    var msg = evt.data;
    if (!msg || msg.type !== 'translationResult') return;
    var agentName = _pendingPositionRequests[msg.requestId];
    if (!agentName) return;
    delete _pendingPositionRequests[msg.requestId];
    fetch(_cfg.apiUrl + '/bridge/position', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent: agentName, position: msg.translation }),
    }).catch(function (e) {
      console.warn('[MCCFAffectsBridge] position push failed for ' + agentName + ': ' + e.message);
    });
  }

  function _tick() {
    // Direction 1: pull affect, push into the scene.
    fetch(_cfg.apiUrl + '/bridge/affect')
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (data) {
        var agents = data.agents || {};
        Object.keys(agents).forEach(function (name) {
          if (_cfg.agentNames.indexOf(name) === -1) return; // not in this scene's exported set
          _pushAffect(name, agents[name]);
        });
      })
      .catch(function (e) {
        console.warn('[MCCFAffectsBridge] /bridge/affect poll failed: ' + e.message);
      });

    // Direction 2: pull live position, push to the API.
    _cfg.agentNames.forEach(_pollPosition);
  }

  return {
    start: function (cfg) {
      if (_timer) this.stop();
      _cfg = cfg;
      window.addEventListener('message', _onMessage);
      _timer = setInterval(_tick, cfg.intervalMs || 200);
      console.log('[MCCFAffectsBridge] started, polling every ' + (cfg.intervalMs || 200) + 'ms for: ' + cfg.agentNames.join(', '));
    },
    stop: function () {
      if (_timer) { clearInterval(_timer); _timer = null; }
      window.removeEventListener('message', _onMessage);
    },
  };
})();

// ══════════════════════════════════════════════════════════════════════
// Preview-side SAI listener — the OTHER half, which has to be injected
// into whatever HTML actually contains the X_ITE <x3d-canvas> for the
// live scene (NOT this file — this file lives in the hosting page, this
// listener lives inside the X_ITE frame itself, same split
// mccf_character_creator.html already uses for its own preview). Handles
// the two message types this bridge sends: 'setBridgeField' and
// 'getTranslation'. Written here so both halves exist somewhere, but not
// wired into any real preview HTML this session, since that file wasn't
// available either.
// ══════════════════════════════════════════════════════════════════════
/*
window.addEventListener('message', function (evt) {
  var msg = evt.data;
  if (!msg || !msg.type) return;
  var browser = document.getElementById('x3d-canvas'); // real id depends on the hosting page's own X_ITE embed
  if (!browser || !browser.currentScene) return;

  if (msg.type === 'setBridgeField') {
    try {
      var script = browser.currentScene.getNamedNode(msg.scriptDEF);
      script[msg.field] = msg.value;
    } catch (e) {
      console.warn('[MCCF SAI listener] setBridgeField failed for ' + msg.scriptDEF + '.' + msg.field + ': ' + e.message);
    }
  }

  if (msg.type === 'getTranslation') {
    try {
      var node = browser.currentScene.getNamedNode(msg.nodeDEF);
      var t = node.translation;
      window.parent.postMessage({
        type: 'translationResult',
        requestId: msg.requestId,
        translation: [t.x, t.y, t.z],
      }, '*');
    } catch (e) {
      console.warn('[MCCF SAI listener] getTranslation failed for ' + msg.nodeDEF + ': ' + e.message);
    }
  }
});
*/
