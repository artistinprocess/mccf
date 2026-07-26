// MCCF Dialogue decoupling — Day 72, build schedule item 5a (schema work).
// Day 73: added ttsText/tagSource/audioFile/audioSource (priority queue
// item 2) and the arc-complete trigger kind (priority queue item 3 — the
// Chorus redesign decided in the Day 72 seed doc §5.2), and Kate export/
// import (priority queue item 5 — format revised to plain XML, see
// exportForKate/importFromKate below for why).
// Day 74: added channelE/channelB/channelP/channelS + emotionalInterpreter
// (MCCF_Proto_Timeline_Architecture_Spec_v1.7 §5a — this field group had
// been specified there but never built; the interpreted-affect-as-
// ChannelVector idea existed only in that spec until now). A line's
// interpreted affect is expressed as the same four-channel shape
// (E/B/P/S) already running live in mccf_core.py's coherence/coupler
// engine — not a free-text mood tag, so it's comparable to live agent
// state, not a parallel representation that has to be reconciled later.
// emotionalInterpreter names the persona whose affective judgment produced
// the tagging (a casting decision, per §5a — "Kate performs Anna" means
// Kate is cast as Anna's emotionalInterpreter, a separate decision from
// which voice/audio renders her).
// Reference implementation of DIALOGUE_SCHEMA.md. Same house style as
// field-map.js: hand-rolled parsing (the schema is fully controlled, both
// ends are ours), zero dependencies, works under Node (tests) and as a
// plain browser <script> (the eventual editor).
//
// Line shape (in-memory):
//   {
//     id, actor, type, mode, blocking, trigger: {type, ...params}, text,
//     ttsText?: string,                          // optional
//     tagSource?: {type, ...params},              // co-required with ttsText
//     audioFile?: string,                          // optional
//     audioSource?: {type, ...params},             // co-required with audioFile
//     channelE?: number,                          // [0,1] — co-required as
//     channelB?: number,                          // a group of four, plus
//     channelP?: number,                          // emotionalInterpreter —
//     channelS?: number,                          // all five or none
//     emotionalInterpreter?: string,               // co-required with channels
//   }

(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.MCCFDialogue = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {

  const LINE_TYPES = ['Question', 'Response', 'Statement'];
  const MODES = ['static', 'improv'];
  const TRIGGER_KINDS = ['scene-start', 'touch', 'zone', 'sensed', 'declared', 'arc-complete', 'legacy-waypoint'];

  // ── trigger string <-> object ──────────────────────────────────────────
  function parseTrigger(str) {
    if (str === 'scene-start') return { type: 'scene-start' };
    if (str === 'arc-complete') return { type: 'arc-complete' };
    const m = /^(\w[\w-]*):(.+)$/.exec(str || '');
    if (!m) return { type: '__invalid__', raw: str };
    const [, kind, param] = m;
    if (kind === 'touch') return { type: 'touch', sensor: param };
    if (kind === 'zone') return { type: 'zone', zone: param };
    if (kind === 'sensed') return { type: 'sensed', lineId: param };
    if (kind === 'declared') {
      const time = Number(param);
      return { type: 'declared', time: Number.isFinite(time) ? time : NaN };
    }
    if (kind === 'arc-complete') return { type: 'arc-complete', zone: param };
    if (kind === 'legacy-waypoint') return { type: 'legacy-waypoint', waypoint: param };
    return { type: '__invalid__', raw: str };
  }

  function serializeTrigger(trigger) {
    switch (trigger.type) {
      case 'scene-start': return 'scene-start';
      case 'touch': return `touch:${trigger.sensor}`;
      case 'zone': return `zone:${trigger.zone}`;
      case 'sensed': return `sensed:${trigger.lineId}`;
      case 'declared': return `declared:${trigger.time}`;
      case 'arc-complete': return trigger.zone ? `arc-complete:${trigger.zone}` : 'arc-complete';
      case 'legacy-waypoint': return `legacy-waypoint:${trigger.waypoint}`;
      default: throw new Error(`serializeTrigger: unknown trigger type "${trigger.type}"`);
    }
  }

  // ── tagSource string <-> object ────────────────────────────────────────
  // Provenance of ttsText's delivery tag. See DIALOGUE_SCHEMA.md's
  // "ttsText / tagSource" section — 'algorithmic' from /voice/preview's
  // heuristic, 'authored' from a human (dropdown or hand-typed, and the
  // editor is expected to auto-promote algorithmic -> authored the instant
  // a human edits a tag — that promotion is editor behavior, not enforced
  // here), 'llm-interpreted:<name>' from a Kate-style collaborator loop.
  const TAG_SOURCE_KINDS = ['algorithmic', 'authored', 'llm-interpreted'];

  function parseTagSource(str) {
    if (str === 'algorithmic') return { type: 'algorithmic' };
    if (str === 'authored') return { type: 'authored' };
    const m = /^llm-interpreted:(.+)$/.exec(str || '');
    if (m) return { type: 'llm-interpreted', name: m[1] };
    return { type: '__invalid__', raw: str };
  }

  function serializeTagSource(tagSource) {
    switch (tagSource.type) {
      case 'algorithmic': return 'algorithmic';
      case 'authored': return 'authored';
      case 'llm-interpreted': return `llm-interpreted:${tagSource.name}`;
      default: throw new Error(`serializeTagSource: unknown tagSource type "${tagSource.type}"`);
    }
  }

  // ── audioSource string <-> object ──────────────────────────────────────
  // Provenance of audioFile. 'elevenlabs' / 'recorded' / 'other-engine:<name>'
  // — see DIALOGUE_SCHEMA.md's "audioFile / audioSource" section. This is
  // what makes "still placeholder TTS" vs. "final hired-actor VO" a visible
  // scene state rather than something tracked only in the author's head.
  const AUDIO_SOURCE_KINDS = ['elevenlabs', 'recorded', 'other-engine'];

  function parseAudioSource(str) {
    if (str === 'elevenlabs') return { type: 'elevenlabs' };
    if (str === 'recorded') return { type: 'recorded' };
    const m = /^other-engine:(.+)$/.exec(str || '');
    if (m) return { type: 'other-engine', name: m[1] };
    return { type: '__invalid__', raw: str };
  }

  function serializeAudioSource(audioSource) {
    switch (audioSource.type) {
      case 'elevenlabs': return 'elevenlabs';
      case 'recorded': return 'recorded';
      case 'other-engine': return `other-engine:${audioSource.name}`;
      default: throw new Error(`serializeAudioSource: unknown audioSource type "${audioSource.type}"`);
    }
  }

  // ── validate ────────────────────────────────────────────────────────────
  function validateDialogueLines(lines, opts) {
    opts = opts || {};
    const additionalValidIds = opts.additionalValidIds || [];
    const errors = [];
    if (!Array.isArray(lines)) return { valid: false, errors: ['dialogue lines must be an array'] };
    const seenIds = new Set();
    lines.forEach((l, i) => {
      const where = `line[${i}]${l && l.id ? ' (' + l.id + ')' : ''}`;
      if (!l || typeof l !== 'object') { errors.push(`${where}: not an object`); return; }
      if (!l.id) errors.push(`${where}: missing id`);
      else if (seenIds.has(l.id)) errors.push(`${where}: duplicate id "${l.id}" — line ids must be scene-wide unique`);
      else seenIds.add(l.id);
      if (!l.actor) errors.push(`${where}: missing actor`);
      if (!LINE_TYPES.includes(l.type)) errors.push(`${where}: type must be one of ${LINE_TYPES.join(' | ')}`);
      if (!MODES.includes(l.mode)) errors.push(`${where}: mode must be one of ${MODES.join(' | ')}`);
      if (typeof l.blocking !== 'boolean') errors.push(`${where}: blocking must be a boolean`);
      if (!l.trigger || !TRIGGER_KINDS.includes(l.trigger.type)) {
        errors.push(`${where}: invalid trigger`);
      } else if (l.trigger.type === 'declared' && !Number.isFinite(l.trigger.time)) {
        errors.push(`${where}: declared trigger needs a numeric time`);
      }
      // Day 74 fix, on record: text was required unconditionally, with no
      // exception for mode==='improv' — contradicts this schema's own
      // design intent (MCCF_Proto_Timeline_Architecture_Spec_v1.7 §5a:
      // "TTS is the default... the permanent path for live-riffed lines,
      // since improvised dialogue is generated and spoken in the same
      // moment and is never pre-recorded by definition"). An improv line
      // genuinely has no text at authoring time — that's not a missing
      // value, it's the correct state for a line whose content doesn't
      // exist until runtime. static lines keep the original strict rule.
      if (l.mode === 'improv') {
        if (l.text !== undefined && l.text !== null && typeof l.text !== 'string') {
          errors.push(`${where}: text must be a string when present`);
        }
      } else if (typeof l.text !== 'string' || !l.text.trim()) {
        errors.push(`${where}: missing text`);
      }

      // ttsText / tagSource — co-required (Day 73)
      const hasTtsText = l.ttsText !== undefined && l.ttsText !== null;
      const hasTagSource = l.tagSource !== undefined && l.tagSource !== null;
      if (hasTtsText && !hasTagSource) {
        errors.push(`${where}: ttsText present but tagSource missing — a tag with no recorded provenance can't be trusted or distrusted later`);
      } else if (hasTagSource && !hasTtsText) {
        errors.push(`${where}: tagSource present but ttsText missing — tagSource describes a tag that doesn't exist on this line`);
      } else if (hasTagSource && (!l.tagSource || !TAG_SOURCE_KINDS.includes(l.tagSource.type))) {
        errors.push(`${where}: tagSource must be one of ${TAG_SOURCE_KINDS.join(' | ')}`);
      } else if (hasTtsText && typeof l.ttsText !== 'string') {
        errors.push(`${where}: ttsText must be a string`);
      }

      // audioFile / audioSource — co-required (Day 73)
      const hasAudioFile = l.audioFile !== undefined && l.audioFile !== null;
      const hasAudioSource = l.audioSource !== undefined && l.audioSource !== null;
      if (hasAudioFile && !hasAudioSource) {
        errors.push(`${where}: audioFile present but audioSource missing — an audio path with no recorded provenance can't be trusted or distrusted later`);
      } else if (hasAudioSource && !hasAudioFile) {
        errors.push(`${where}: audioSource present but audioFile missing — audioSource describes an audio file that doesn't exist on this line`);
      } else if (hasAudioSource && (!l.audioSource || !AUDIO_SOURCE_KINDS.includes(l.audioSource.type))) {
        errors.push(`${where}: audioSource must be one of ${AUDIO_SOURCE_KINDS.join(' | ')}`);
      } else if (hasAudioFile && typeof l.audioFile !== 'string') {
        errors.push(`${where}: audioFile must be a string`);
      }

      // channelE/B/P/S + emotionalInterpreter — co-required as a group of
      // five (Day 74). A partial ChannelVector isn't a valid vector — either
      // all four channels are tagged plus who cast the interpretation, or
      // none of it is present. Mirrors the ttsText/tagSource co-requirement
      // above: an affect tag with no recorded interpreter can't be trusted
      // or distrusted later any more than a delivery tag with no provenance.
      const CHANNEL_KEYS = ['channelE', 'channelB', 'channelP', 'channelS'];
      const presentChannels = CHANNEL_KEYS.filter((k) => l[k] !== undefined && l[k] !== null);
      const hasAnyChannel = presentChannels.length > 0;
      const hasAllChannels = presentChannels.length === CHANNEL_KEYS.length;
      const hasInterpreter = l.emotionalInterpreter !== undefined && l.emotionalInterpreter !== null && l.emotionalInterpreter !== '';
      if (hasAnyChannel && !hasAllChannels) {
        const missing = CHANNEL_KEYS.filter((k) => !presentChannels.includes(k));
        errors.push(`${where}: partial ChannelVector — missing ${missing.join(', ')} (all four channels required together, or none)`);
      } else if (hasAllChannels) {
        CHANNEL_KEYS.forEach((k) => {
          const v = l[k];
          if (typeof v !== 'number' || !Number.isFinite(v) || v < 0 || v > 1) {
            errors.push(`${where}: ${k} must be a number in [0,1]`);
          }
        });
        if (!hasInterpreter) {
          errors.push(`${where}: channelE/B/P/S present but emotionalInterpreter missing — an affect tag with no cast interpreter can't be trusted or distrusted later`);
        }
      } else if (hasInterpreter && !hasAnyChannel) {
        errors.push(`${where}: emotionalInterpreter present but no channelE/B/P/S — emotionalInterpreter describes a tagging that doesn't exist on this line`);
      }
    });
    // sensed triggers must resolve to a real id in this same set (rule from
    // schema doc), OR one of the caller-supplied additionalValidIds — Day
    // 74: dialogue lines can legitimately chain off a non-dialogue step
    // (a path segment's `arrived`), per Actor Doc §8's scene-wide step-id
    // model; the dialogue block alone doesn't have visibility into those
    // ids, so a Timeline-level caller (one that DOES know the full
    // scene's step ids) can supply them here rather than this validator
    // wrongly rejecting a legitimate cross-track reference.
    const ids = new Set(lines.filter((l) => l && l.id).map((l) => l.id).concat(additionalValidIds));
    lines.forEach((l, i) => {
      if (l && l.trigger && l.trigger.type === 'sensed' && !ids.has(l.trigger.lineId)) {
        errors.push(`line[${i}] (${l.id}): sensed trigger references unknown line id "${l.trigger.lineId}"`);
      }
    });
    return { valid: errors.length === 0, errors };
  }

  function xmlEscape(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── serialize just the <Dialogue> block ────────────────────────────────
  function serializeDialogueBlock(lines, opts) {
    const { valid, errors } = validateDialogueLines(lines, opts);
    if (!valid) throw new Error('serializeDialogueBlock: invalid lines:\n' + errors.join('\n'));
    const rows = lines.map((l) => {
      const trig = serializeTrigger(l.trigger);
      let attrs = `id="${xmlEscape(l.id)}" actor="${xmlEscape(l.actor)}" type="${l.type}" ` +
        `mode="${l.mode}" blocking="${l.blocking}" trigger="${xmlEscape(trig)}"`;
      if (l.ttsText !== undefined && l.ttsText !== null) {
        attrs += ` ttsText="${xmlEscape(l.ttsText)}" tagSource="${xmlEscape(serializeTagSource(l.tagSource))}"`;
      }
      if (l.audioFile !== undefined && l.audioFile !== null) {
        attrs += ` audioFile="${xmlEscape(l.audioFile)}" audioSource="${xmlEscape(serializeAudioSource(l.audioSource))}"`;
      }
      if (l.channelE !== undefined && l.channelE !== null) {
        attrs += ` channelE="${l.channelE}" channelB="${l.channelB}" channelP="${l.channelP}" channelS="${l.channelS}"` +
          ` emotionalInterpreter="${xmlEscape(l.emotionalInterpreter)}"`;
      }
      return `  <Line ${attrs}>${xmlEscape((l.text || '').trim())}</Line>`;
    });
    return `<Dialogue>\n${rows.join('\n')}\n</Dialogue>`;
  }

  // ── parse a <Dialogue> block out of a full scene XML string ───────────
  function parseDialogueBlock(sceneXml) {
    const m = sceneXml.match(/<Dialogue>([\s\S]*?)<\/Dialogue>/);
    if (!m) return []; // absent block is not an error — legacy scene, see parseLegacyWaypointLines
    const body = m[1];
    const lines = [];
    const lineRe = /<Line\s+([^>]*)>([\s\S]*?)<\/Line>/g;
    let lm;
    while ((lm = lineRe.exec(body)) !== null) {
      const attrsRaw = lm[1];
      const text = lm[2].trim();
      const attrs = {};
      const attrRe = /(\w+)="([^"]*)"/g;
      let am;
      while ((am = attrRe.exec(attrsRaw)) !== null) attrs[am[1]] = am[2];
      const line = {
        id: attrs.id,
        actor: attrs.actor,
        type: attrs.type,
        mode: attrs.mode,
        blocking: attrs.blocking === 'true',
        trigger: parseTrigger(attrs.trigger),
        text: text.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&'),
      };
      if (attrs.ttsText !== undefined) {
        line.ttsText = attrs.ttsText.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&');
        // Only set tagSource if the attribute is actually present — a
        // well-formed <Dialogue> block always has both together (co-
        // required by validateDialogueLines), but parseDialogueBlock also
        // needs to tolerate malformed/in-progress XML (e.g. an LLM
        // collaborator's reply with a tag but no provenance yet, see
        // importFromKate) without inventing a fake tagSource value for a
        // genuinely-absent attribute.
        if (attrs.tagSource !== undefined) {
          line.tagSource = parseTagSource(attrs.tagSource);
        }
      }
      if (attrs.audioFile !== undefined) {
        line.audioFile = attrs.audioFile.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&');
        if (attrs.audioSource !== undefined) {
          line.audioSource = parseAudioSource(attrs.audioSource);
        }
      }
      if (attrs.channelE !== undefined) {
        line.channelE = Number(attrs.channelE);
        line.channelB = Number(attrs.channelB);
        line.channelP = Number(attrs.channelP);
        line.channelS = Number(attrs.channelS);
        if (attrs.emotionalInterpreter !== undefined) {
          line.emotionalInterpreter = attrs.emotionalInterpreter.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&');
        }
      }
      lines.push(line);
    }
    return lines;
  }

  // ── legacy migration: pull Question/Response/Statement out of <Waypoint> ──
  function parseLegacyWaypointLines(sceneXml) {
    const lines = [];
    const wpRe = /<Waypoint\s+([^>]*)>([\s\S]*?)<\/Waypoint>/g;
    let wm;
    while ((wm = wpRe.exec(sceneXml)) !== null) {
      const wpAttrs = {};
      const attrRe = /(\w+)="([^"]*)"/g;
      let am;
      while ((am = attrRe.exec(wm[1])) !== null) wpAttrs[am[1]] = am[2];
      const wpName = wpAttrs.name;
      if (!wpName) continue;
      const body = wm[2];
      const lineRe = /<(Question|Response|Statement)([^>]*)>([\s\S]*?)<\/\1>/g;
      let lm, idx = 0;
      while ((lm = lineRe.exec(body)) !== null) {
        const type = lm[1];
        const attrs = {};
        const a2 = /(\w+)="([^"]*)"/g;
        let am2;
        while ((am2 = a2.exec(lm[2])) !== null) attrs[am2[1]] = am2[2];
        const text = lm[3].trim();
        if (!text) continue;
        lines.push({
          id: `${wpName}_${idx++}`,
          actor: attrs.speaker || '',
          type,
          mode: 'improv',      // legacy default — see schema doc migration rules
          blocking: false,     // legacy default
          trigger: { type: 'legacy-waypoint', waypoint: wpName },
          text: text.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&'),
        });
      }
    }
    return lines;
  }

  // ── the merge-safe save path ────────────────────────────────────────────
  // Replaces only the <Dialogue>...</Dialogue> block in a full scene XML
  // string, inserting one before </Scene> if none exists yet. Everything
  // else in the document is left byte-identical — see schema doc's
  // round-trip/merge contract, and the Day 71 "plain overwrite, no merge"
  // lesson this is deliberately built around rather than repeating.
  function mergeDialogueIntoRawXml(sceneXml, lines) {
    const block = serializeDialogueBlock(lines);
    if (/<Dialogue>[\s\S]*?<\/Dialogue>/.test(sceneXml)) {
      return sceneXml.replace(/<Dialogue>[\s\S]*?<\/Dialogue>/, block);
    }
    if (!/<\/Scene>/.test(sceneXml)) {
      throw new Error('mergeDialogueIntoRawXml: no </Scene> closing tag found — refusing to guess where to insert the Dialogue block');
    }
    return sceneXml.replace(/<\/Scene>/, `${block}\n</Scene>`);
  }

  // ── Kate (or any long-collaboration LLM partner) export/import ─────────
  // Day 73, priority queue item 5.
  //
  // FORMAT REVISION, on record: the Day 72 seed doc §7 originally decided
  // to reuse Chorus's own build_transcript() bracket convention
  // (`[line_id] Speaker: "text"`) rather than invent a new format. That
  // decision is superseded here — export is plain <Dialogue> XML, this
  // schema's own format, not a second convention. Reasoning: the whole
  // point of the bracket convention was that `[line_id]` made strict-id-
  // first reimport possible; `<Line id="...">` already does that job, and
  // reusing it means zero new parsing logic and zero risk of the two
  // formats drifting apart. Kate reads/returns the exact same shape any
  // other tool in this codebase does.
  //
  // "Kate" is a generic slot (per the original decision, never hardcoded
  // to one collaborator) — collaboratorName defaults to 'Kate' but any
  // long-collaboration LLM partner's name can be passed.

  function exportForKate(lines) {
    // Just the <Dialogue> block. No extra wrapping, no instructions
    // embedded in the XML itself — what Kate is asked to do with it is a
    // prompt-authoring concern outside this module, not something baked
    // into the export format.
    return serializeDialogueBlock(lines);
  }

  function importFromKate(kateXml, originalLines, collaboratorName) {
    collaboratorName = collaboratorName || 'Kate';

    // Tolerate a bare fragment (just <Line> elements, no <Dialogue> wrapper)
    // as well as a full block — an LLM asked to "return the edited lines"
    // may reasonably drop the wrapper even if it was told to keep it.
    const wrapped = /<Dialogue[\s>]/.test(kateXml) ? kateXml : `<Dialogue>\n${kateXml}\n</Dialogue>`;
    const returnedLines = parseDialogueBlock(wrapped);

    const originalById = new Map(originalLines.map((l) => [l.id, l]));
    // Duplicate original text across multiple lines is a known limitation
    // here — last one wins in this map, same as any Map with duplicate
    // keys. Not expected to be common (dialogue lines are rarely verbatim
    // duplicates of each other), not worth a more elaborate structure yet.
    const originalByText = new Map(originalLines.map((l) => [(l.text || '').trim(), l]));

    const updated = [];
    const added = [];
    const usedIds = new Set(originalLines.map((l) => l.id));
    let newIdCounter = 0;

    returnedLines.forEach((rl) => {
      // Auto-stamp tagSource for a tag Kate added/edited, IF she didn't
      // already set one herself — never clobber an explicit tagSource
      // that came back on the line (same "don't override what's already
      // there" caution as everywhere else provenance is tracked in this
      // schema).
      if (rl.ttsText !== undefined && rl.ttsText !== null &&
          (rl.tagSource === undefined || rl.tagSource === null)) {
        rl.tagSource = { type: 'llm-interpreted', name: collaboratorName };
      }

      // Same stamping discipline for affect tagging: if Kate returned
      // channelE/B/P/S without naming who cast the interpretation, she's
      // the one who cast it — never override an explicit emotionalInterpreter
      // that came back on the line, same "don't clobber what's already there"
      // caution as tagSource above.
      if (rl.channelE !== undefined && rl.channelE !== null &&
          (rl.emotionalInterpreter === undefined || rl.emotionalInterpreter === null || rl.emotionalInterpreter === '')) {
        rl.emotionalInterpreter = collaboratorName;
      }

      // Strict id-first: an id we recognize is an edit to that line.
      if (rl.id && originalById.has(rl.id)) {
        updated.push(rl);
        return;
      }

      // Fallback to exact-text match: id drifted or got regenerated, but
      // the text is unchanged from something we sent — keep OUR canonical
      // id, never let a returned id override a resolved one (same
      // identity discipline as build-schedule item 1).
      const fallback = originalByText.get((rl.text || '').trim());
      if (fallback) {
        updated.push(Object.assign({}, rl, { id: fallback.id }));
        return;
      }

      // Neither id nor text matches anything we sent — a genuinely new
      // line Kate authored, not an edit. Don't trust her id to be
      // globally unique; assign a fresh one if it collides or is absent.
      let candidateId = rl.id && !usedIds.has(rl.id) ? rl.id : null;
      if (!candidateId) {
        do {
          newIdCounter += 1;
          candidateId = `kate_import_${newIdCounter}`;
        } while (usedIds.has(candidateId));
      }
      usedIds.add(candidateId);
      added.push(Object.assign({}, rl, { id: candidateId }));
    });

    const merged = originalLines
      .map((orig) => updated.find((u) => u.id === orig.id) || orig)
      .concat(added);

    const { valid, errors } = validateDialogueLines(merged);

    // Reconciled result, not an auto-applied one — same "promotion is a
    // deliberate author action" discipline as Chorus's per-take capture.
    // Caller decides whether/how to merge `lines` into the real scene.
    return {
      lines: merged,
      updatedIds: updated.map((l) => l.id),
      addedIds: added.map((l) => l.id),
      valid,
      errors,
    };
  }

  return {
    LINE_TYPES, MODES, TRIGGER_KINDS, TAG_SOURCE_KINDS, AUDIO_SOURCE_KINDS,
    parseTrigger, serializeTrigger,
    parseTagSource, serializeTagSource,
    parseAudioSource, serializeAudioSource,
    validateDialogueLines, serializeDialogueBlock, parseDialogueBlock,
    parseLegacyWaypointLines, mergeDialogueIntoRawXml,
    exportForKate, importFromKate,
  };
});
