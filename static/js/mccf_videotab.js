// MCCF Ambient Composer: the Video view. Plays an mp4 (or webm) from X3DAssets/media/video beside the music, with a bar-and-beat ruler.
// The video runs on its own clock and is the master for "where are we": a tempo map (js/mccf_videosync.js) turns video seconds into bars and beats.
// The music runs on its own clock (the theme player). "Play together" starts both; the offset says how many ms after the video the music starts.
// Needs js/mccf_videosync.js. No dependency on the rest of the Ambient page: the page passes in hooks (see init).
(function (root) {
  'use strict';
  var VS = root.MccfVideoSync || (typeof require !== 'undefined' ? require('./mccf_videosync.js') : null);
  var CSS = '' +
    '.vt{display:flex;flex-direction:column;gap:8px;padding:10px 12px;height:100%;box-sizing:border-box;overflow:auto;color:var(--text,#ddd);font-family:var(--mono,monospace);font-size:12px}' +
    '.vt .vt-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px}' +
    '.vt label{display:inline-flex;align-items:center;gap:4px;color:var(--dim,#99a)}' +
    '.vt select,.vt input[type=number]{background:var(--s2,#151a24);color:var(--text,#ddd);border:1px solid var(--border,#334);border-radius:3px;font-family:inherit;font-size:12px;padding:2px 4px}' +
    '.vt input[type=number]{width:64px}' +
    '.vt button{background:var(--s2,#151a24);color:var(--text,#ddd);border:1px solid var(--border,#334);border-radius:3px;font-family:inherit;font-size:12px;padding:3px 10px;cursor:pointer}' +
    '.vt button.primary{background:var(--purple,#7c5cff);border-color:var(--purple,#7c5cff);color:#fff}' +
    '.vt video{width:100%;max-height:46vh;background:#000;border-radius:4px}' +
    '.vt canvas{width:100%;height:72px;background:var(--s2,#151a24);border:1px solid var(--border,#334);border-radius:4px;cursor:pointer}' +
    '.vt .vt-read{font-size:15px;color:var(--text,#ddd)}' +
    '.vt .vt-msg{color:var(--dim,#99a);min-height:16px}' +
    '.vt .vt-pts{display:flex;flex-wrap:wrap;gap:6px}' +
    '.vt .vt-pt{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border,#334);border-radius:3px;padding:1px 4px 1px 8px}' +
    '.vt .vt-pt button{padding:0 6px;border:none;background:none}';

  var EXTS = ['mp4', 'webm', 'ogv'];

  // opts: { container: element, api: 'http://localhost:5000',
  //         music: { start(): promise|void, stop(), isPlaying(): bool, tempoScale(): number (optional), bpm(): number (optional, the loaded theme's tempo) } }
  function init(opts) {
    if (!VS) throw new Error('js/mccf_videosync.js is not loaded');
    var host = opts.container, api = (opts.api || '').replace(/\/$/, ''), music = opts.music || {};
    if (!document.getElementById('vt-css')) { var st = document.createElement('style'); st.id = 'vt-css'; st.textContent = CSS; document.head.appendChild(st); }
    host.innerHTML = '' +
      '<div class="vt">' +
      '<div class="vt-row"><label>video <select id="vt-file"><option value="">(none)</option></select></label>' +
      '<button id="vt-refresh" title="read the folder again">refresh</button>' +
      '<label>or a file <input type="file" id="vt-local" accept="video/mp4,video/webm,video/ogg"></label>' +
      '<span class="vt-msg" id="vt-status"></span></div>' +
      '<video id="vt-video" muted loop playsinline controls></video>' +
      '<div class="vt-row"><label><input type="checkbox" id="vt-mute" checked> mute video</label>' +
      '<label><input type="checkbox" id="vt-loop" checked> loop video</label>' +
      '<label>tempo <input type="number" id="vt-bpm" min="20" max="300" step="1" value="90"></label>' +
      '<button id="vt-bars" title="make an empty score with these bars and tempo changes, and open it in Grid and Notation">bars to Grid / Notation</button>' +
      '<button id="vt-usetheme" title="take the tempo of the loaded MIDI theme">use theme tempo</button>' +
      '<label>meter <select id="vt-num"></select> / <select id="vt-den"><option>4</option><option>8</option><option>2</option></select></label>' +
      '<label title="positive: the music starts this many ms after the video. negative: the video starts later.">music starts <input type="number" id="vt-off" step="10" value="0"> ms after video</label></div>' +
      '<div class="vt-row"><button class="primary" id="vt-both">&#9654; Play together</button><button id="vt-vonly">&#9654; Video only</button><button id="vt-stop">&#9209; Stop both</button>' +
      '<span class="vt-read" id="vt-read">-</span></div>' +
      '<canvas id="vt-ruler"></canvas>' +
      '<div class="vt-row"><span>sync point:</span><label>bar <input type="number" id="vt-sbar" min="1" step="1" value="1"></label><button id="vt-sadd" title="bar N starts at the video\'s current time">bar N = here</button>' +
      '<span class="vt-msg" id="vt-smsg"></span></div>' +
      '<div class="vt-pts" id="vt-pts"></div>' +
      '</div>';
    var $ = function (id) { return host.querySelector('#' + id); };
    var video = $('vt-video'), canvas = $('vt-ruler'), map = VS.create({}), curKey = '', timers = [], raf = 0;
    [2, 3, 4, 5, 6, 7, 9, 12].forEach(function (n) { var o = document.createElement('option'); o.textContent = n; if (n === 4) o.selected = true; $('vt-num').appendChild(o); });

    // ---- settings: remembered per video (browser storage may be unavailable) ----
    function save() { try { if (curKey) localStorage.setItem('mccf_vt:' + curKey, JSON.stringify({ map: VS.toJSON(map), mute: $('vt-mute').checked, loop: $('vt-loop').checked, moff: +$('vt-off').value || 0 })); } catch (e) { /* no storage */ } }
    function load(key) {
      var d = null; try { d = JSON.parse(localStorage.getItem('mccf_vt:' + key) || 'null'); } catch (e) { d = null; }
      map = VS.create(d && d.map ? d.map : {});
      $('vt-bpm').value = map.bpm; $('vt-num').value = map.num; $('vt-den').value = map.den; $('vt-off').value = d && isFinite(+d.moff) ? +d.moff : 0;
      $('vt-mute').checked = d ? d.mute !== false : true; $('vt-loop').checked = d ? d.loop !== false : true;
      video.muted = $('vt-mute').checked; video.loop = $('vt-loop').checked;
    }
    function rebuild() {                                   // the controls are the truth for bpm, meter; the points are kept
      var pts = map.points.slice();
      map = VS.create({ bpm: $('vt-bpm').value, num: $('vt-num').value, den: $('vt-den').value, offset: 0, points: pts });
      $('vt-bpm').value = map.bpm; save(); draw();
    }
    function scale() { var s = typeof music.tempoScale === 'function' ? +music.tempoScale() : 1; return isFinite(s) && s > 0 ? s : 1; }

    // ---- the file list ----
    function setSrc(url, key) {
      curKey = key || ''; video.pause(); video.src = url || ''; load(curKey); renderPts(); draw();
      if (url) video.load();
    }
    async function listFiles() {
      var all = [];
      for (var i = 0; i < EXTS.length; i++) {
        try { var r = await fetch(api + '/media/list?subdir=video&ext=' + EXTS[i]); var d = await r.json(); (d.files || []).forEach(function (f) { all.push(f); }); } catch (e) { $('vt-status').textContent = 'Could not reach the server.'; return; }
      }
      all.sort();
      var sel = $('vt-file'), keep = sel.value; sel.innerHTML = '<option value="">(none)</option>';
      all.forEach(function (f) { var o = document.createElement('option'); o.value = f; o.textContent = f.replace(/^video\//, ''); sel.appendChild(o); });
      if (keep && all.indexOf(keep) >= 0) sel.value = keep;
      $('vt-status').textContent = all.length ? '' : 'No video files in X3DAssets/media/video.';
    }
    $('vt-file').addEventListener('change', function () { var f = this.value; setSrc(f ? api + '/static/x3d/X3DAssets/media/' + f : '', f); });
    $('vt-refresh').addEventListener('click', listFiles);
    $('vt-local').addEventListener('change', function () { var f = this.files && this.files[0]; if (!f) return; $('vt-file').value = ''; setSrc(URL.createObjectURL(f), 'local:' + f.name); });

    // ---- controls ----
    $('vt-mute').addEventListener('change', function () { video.muted = this.checked; save(); });
    $('vt-loop').addEventListener('change', function () { video.loop = this.checked; save(); });
    ['vt-bpm', 'vt-num', 'vt-den'].forEach(function (id) { $(id).addEventListener('change', rebuild); });
    $('vt-off').addEventListener('change', save);          // the music's start offset is its own setting; bar 1 is always the start of the video
    $('vt-usetheme').addEventListener('click', function () {
      var b = typeof music.bpm === 'function' ? +music.bpm() : NaN;
      if (isFinite(b) && b > 0) { $('vt-bpm').value = Math.round(b); rebuild(); $('vt-smsg').textContent = 'Tempo set from the theme.'; }
      else $('vt-smsg').textContent = 'No theme is loaded.';
    });
    // Send the bars to Grid and Notation. auto=true: after a video loads or the map changes; the page skips it when a real MIDI theme
    // is loaded or the music is playing, so it never overwrites your work.
    var pushTimer = null;
    function pushBars(auto) {
      var dur = video.duration;
      if (!isFinite(dur) || dur <= 0) { if (!auto) $('vt-status').textContent = 'Choose a video first, so the length is known.'; return; }
      if (typeof music.loadBars !== 'function') { if (!auto) $('vt-status').textContent = 'This page cannot load a score.'; return; }
      var w = VS.toSMF(map, dur, 480);
      var ok = music.loadBars(w.bytes.buffer, 'Video bars (' + (curKey || 'video').replace(/^.*\//, '') + ').mid', !!auto);
      if (ok === false) { if (!auto) $('vt-status').textContent = 'Not sent: a MIDI theme is loaded or the music is playing.'; return; }
      $('vt-status').textContent = w.bars + ' empty bars are in Grid and Notation.';
    }
    function pushSoon() { clearTimeout(pushTimer); pushTimer = setTimeout(function () { pushBars(true); }, 300); }
    $('vt-bars').addEventListener('click', function () { pushBars(false); });
    video.addEventListener('loadedmetadata', pushSoon);
    ['vt-bpm', 'vt-num', 'vt-den'].forEach(function (id) { $(id).addEventListener('change', pushSoon); });
    function clearTimers() { timers.forEach(clearTimeout); timers = []; }
    function playVideo() { try { var p = video.play(); if (p && p.catch) p.catch(function (e) { $('vt-status').textContent = 'The browser would not play the video: ' + (e && e.message ? e.message : e); }); } catch (e) { /* ignore */ } }
    function startMusic() { try { var r = music.start && music.start(); if (r && r.catch) r.catch(function () { }); } catch (e) { /* ignore */ } }
    $('vt-both').addEventListener('click', function () {
      if (!video.src) { $('vt-status').textContent = 'Choose a video first.'; return; }
      clearTimers(); if (music.isPlaying && music.isPlaying() && music.stop) music.stop();
      video.currentTime = 0;
      var off = +$('vt-off').value || 0;
      if (off >= 0) { playVideo(); timers.push(setTimeout(startMusic, off)); } else { startMusic(); timers.push(setTimeout(playVideo, -off)); }
      loop();
    });
    $('vt-vonly').addEventListener('click', function () { if (!video.src) { $('vt-status').textContent = 'Choose a video first.'; return; } playVideo(); loop(); });
    $('vt-stop').addEventListener('click', function () { clearTimers(); video.pause(); video.currentTime = 0; if (music.isPlaying && music.isPlaying() && music.stop) music.stop(); draw(); });

    // ---- sync points ----
    function renderPts() {
      var h = $('vt-pts'); h.innerHTML = '';
      map.points.forEach(function (p) {
        var s = document.createElement('span'); s.className = 'vt-pt'; s.textContent = 'bar ' + p.bar + ' = ' + p.t.toFixed(2) + ' s';
        var b = document.createElement('button'); b.textContent = '✕'; b.title = 'remove this sync point';
        b.addEventListener('click', function () { VS.removePoint(map, p.bar); save(); renderPts(); draw(); pushSoon(); });
        s.appendChild(b); h.appendChild(s);
      });
    }
    $('vt-sadd').addEventListener('click', function () {
      var t = video.currentTime, bar = Math.round(+$('vt-sbar').value), r = VS.addPoint(map, bar, t);
      $('vt-smsg').textContent = r.ok ? 'Bar ' + bar + ' now starts at ' + t.toFixed(2) + ' s.' : r.error;
      if (r.ok) { save(); renderPts(); draw(); pushSoon(); }
    });
    function suggestBar() { var p = VS.locate(map, video.currentTime); $('vt-sbar').value = Math.max(1, Math.round(p.pos)); }
    video.addEventListener('pause', suggestBar); video.addEventListener('seeked', suggestBar);

    // ---- ruler ----
    function sizeCanvas() { var r = canvas.getBoundingClientRect(), d = root.devicePixelRatio || 1; canvas.width = Math.max(1, Math.round(r.width * d)); canvas.height = Math.max(1, Math.round(r.height * d)); return d; }
    function draw() {
      var d = sizeCanvas(), W = canvas.width, H = canvas.height, g = canvas.getContext('2d'), dur = video.duration;
      var cs = getComputedStyle(host), dim = (cs.getPropertyValue('--dim') || '#99a').trim() || '#99a', txt = (cs.getPropertyValue('--text') || '#ddd').trim() || '#ddd', acc = (cs.getPropertyValue('--purple') || '#7c5cff').trim() || '#7c5cff';
      g.clearRect(0, 0, W, H);
      map.scale = scale();
      var t = video.currentTime || 0, p = VS.locate(map, t);
      $('vt-read').textContent = VS.fmtPos(p) + '  ·  ' + Math.round(p.bpm) + ' bpm  ·  ' + t.toFixed(1) + ' s' + (isFinite(dur) ? ' / ' + dur.toFixed(1) + ' s' : '');
      if (!isFinite(dur) || dur <= 0) { g.fillStyle = dim; g.font = (11 * d) + 'px monospace'; g.fillText('Choose a video to see the bars.', 8 * d, H / 2); return; }
      var X = function (s) { return (s / dur) * W; }, lines = VS.barLines(map, dur), every = 1, k;
      var minGap = 34 * d; while (lines.length > 1 && (X(lines[1].t) - X(lines[0].t)) * every < minGap && every < 64) every *= 2;
      g.font = (10 * d) + 'px monospace'; g.textBaseline = 'top';
      for (k = 0; k < lines.length; k++) {
        var x = X(lines[k].t), major = (lines[k].bar - 1) % every === 0;
        g.strokeStyle = major ? dim : 'rgba(150,150,170,.35)'; g.lineWidth = 1 * d;
        g.beginPath(); g.moveTo(x, major ? 4 * d : 14 * d); g.lineTo(x, H - 4 * d); g.stroke();
        if (major) { g.fillStyle = txt; g.fillText(String(lines[k].bar), x + 3 * d, 4 * d); }
      }
      map.points.forEach(function (pt) {               // sync points: a flag at the foot of the bar line
        var x = X(pt.t); g.fillStyle = acc; g.fillRect(x - 1 * d, 0, 2 * d, H);
        g.beginPath(); g.moveTo(x, H - 4 * d); g.lineTo(x + 10 * d, H - 12 * d); g.lineTo(x, H - 20 * d); g.closePath(); g.fill();
      });
      g.fillStyle = '#ff5a5f'; g.fillRect(X(t) - 1 * d, 0, 2 * d, H);
    }
    function loop() { cancelAnimationFrame(raf); if (video.paused && !timers.length) { draw(); return; } draw(); raf = requestAnimationFrame(loop); }
    canvas.addEventListener('click', function (e) { var r = canvas.getBoundingClientRect(), dur = video.duration; if (!isFinite(dur) || dur <= 0) return; video.currentTime = Math.max(0, Math.min(dur, (e.clientX - r.left) / r.width * dur)); draw(); });
    ['loadedmetadata', 'seeked', 'timeupdate', 'pause', 'play', 'durationchange'].forEach(function (ev) { video.addEventListener(ev, function () { if (ev === 'play') loop(); else draw(); }); });
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(function () { draw(); }).observe(canvas);

    listFiles(); renderPts(); draw();
    return { getMap: function () { return map; }, video: video, refresh: listFiles, draw: draw, setSource: setSrc, stopAll: function () { $('vt-stop').click(); }, _clear: clearTimers };
  }

  var api = { init: init };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.MccfVideoTab = api;
})(typeof window !== 'undefined' ? window : this);
