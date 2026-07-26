# MCCF Dialogue / Chorus — LLM Character Voice Spec v0.1

*Day 76. Companion to `MCCF_Scene_Integration_Spec_v0.1.md`. Settles one
open question from that spec's Actor/dialogue work: how and when the LLM
is allowed to speak as a character, and how that relates to the Chorus
system (`mccf_chorus.py`, Day 13, `voice_actor` extension Day 73). This
does not redesign Chorus's firing mechanics — those are confirmed working
and unchanged. It settles the prompt-construction question that Chorus's
Day 73 `voice_actor` extension opened but didn't finish, and extends the
same answer to ordinary in-scene dialogue.*

---

## 1. The decision

There is one mechanism for "the LLM speaks as a character," used at two
different trigger points:

- **Regular QRS dialogue, `mode="llm"` Step** — the LLM answers *as* the
  character assigned to that specific dialogue line, at that Step's own
  normal trigger (declared/sensed). It inherits that character's
  qualities *at that point in the dialogue*.
- **Chorus** — the LLM is also assigned a character, but the assignment
  is scene-scoped, not zone-scoped, and can differ from scene to scene.
  It fires once, at scene/arc-complete, and comments on the whole
  scene's dialogue rather than answering one line.

**Explicitly rejected:** LLM-fires-on-blank-Response (the old composer
waypoint QA behavior — `hasAuthoredResponse` check in
`mccf_scene_composer.html`). Blank-means-LLM is an implicit, silent
trigger with no audit trail — a reviewed scene can't tell whether an
empty Response was intentional or a mistake. Every LLM-authored line must
be the result of an explicit author choice, recorded as such.

**Explicitly out of scope, flagged for later:** inter-scene selective
persistence — a character "knowing more" because of what happened in an
earlier scene. Real future requirement, not designed, not touched here.
Both mechanisms below build their prompt from single-scene context only.

---

## 2. Shared mechanism: character-voice prompt building

Both call sites build a system prompt from the **same source**: the
target actor's real Cultivar record (Character Creator — Disposition,
Description, Weights E/B/P/S, FailureMode, Characteristic Phrases; see
the `<Cultivar>` XML shape already visible in Character Creator's live
preview). Neither call site invents its own persona text independently.

```
character_voice_prompt(actor_id, scene_context) →
    pulls actor_id's Cultivar record (Disposition/Description/Weights/
    FailureMode/Phrases)
  + injects scene_context (live E/B/P/S field snapshot at fire time)
  → system prompt
```

This is a genuine change to `mccf_chorus.py`: `_build_system_prompt`
today only reads `config.persona` (a plain string on `<Chorus>`) or falls
back to a generic `_TONE_PROMPTS` tone lookup — it never touches a
Cultivar record at all. That has to change for Chorus's `voice_actor`
case to actually mean what §3 below says it means.

---

## 3. Chorus — what changes, what doesn't

**Unchanged (confirmed working, not touched):**
- Fires at arc-complete only, zone-scoped config, async, never blocks
  TTS/playback.
- `llm`/`stub`/`ollama:<model>`/`openai:<model>` dispatch.
- `captured_lines()` / per-take capture / never-auto-merged-into-canon
  contract — this promotion boundary is correct as-is and should not
  change. A captured Line is a candidate, not canon, until an author
  explicitly promotes it.
- The no-`voice_actor` case: uncredited omniscient commentary, prompt
  built from `persona`/`tone` as today. This stays as the fallback for
  scenes that want a voiceless observer.

**Changes:**
- When `voice_actor` is set, `_build_system_prompt` (or a new sibling
  function used only for the voice_actor path) must call
  `character_voice_prompt(config.voice_actor, live_cv)` instead of using
  `config.persona`/`tone`. The character's actual Cultivar sheet drives
  the commentary, not a separate zone-authored persona string.
- `config.persona`/`config.tone` remain valid **only** for the mute/
  uncredited-observer case — they stop being used at all once a
  `voice_actor` is assigned. (Open question, not blocking: does an
  author ever want *both* — a `voice_actor` whose base persona is
  intentionally overridden by zone-level `persona` text? Default answer
  here is no; Cultivar wins whenever `voice_actor` is set. Flag if this
  needs to be overridable later.)
- The `voice_actor` assignment is confirmed scene-scoped, not
  zone-scoped, matching the Day 76 discussion directly — this may
  already match how `<Chorus voice_actor="...">` is structured today
  (one Chorus per scene, per the module's own Option-A/Option-B note)
  and likely needs no schema change, only a rename/clarification of
  intent in the doc comments if the attribute currently reads as
  zone-level.

---

## 4. Regular dialogue — `mode="improv"` Line

**Correction, Day 76 — `dialogue-xml.js` and `dispatcher.js` are now
actually in hand and read in full.** This already exists, under
different names than §4 originally proposed. No new attribute is needed:

- `dialogue-xml.js`'s `Line.mode` is already `'static' | 'improv'` —
  `static` requires authored text at authoring time (strict, unchanged);
  `improv` explicitly allows *no* text at authoring time, with a Day 74
  fix-comment on record for exactly this reasoning: *"an improv line
  genuinely has no text at authoring time — that's not a missing value,
  it's the correct state for a line whose content doesn't exist until
  runtime."* This is the settled "author must be explicit" rule from
  earlier in this thread, already built, before this conversation
  happened.
- An `improv` Line still declares `actor` the normal way — that actor id
  is what `character_voice_prompt()` (§2) resolves against.
- Fires at the Line's own trigger (declared/sensed/etc. — whatever
  `TRIGGER_KINDS` already supports) — not a new trigger kind. `arc-complete`
  stays Chorus's own trigger; it is not being generalized into regular
  dialogue.
- **What's confirmed missing, by absence, not by design gap:** neither
  `dialogue-xml.js` nor `dispatcher.js` contains any LLM dispatch or
  prompt-building logic at all. `dispatcher.js`'s five verbs
  (`start/stop/arrived/blocked/set`) move data and fire triggers; nothing
  calls Ollama/OpenAI. That logic exists today only in `mccf_chorus.py`
  (`_call_ollama`, `_call_openai`, `_build_system_prompt`). So
  `character_voice_prompt()` (§2) has to live in Python alongside
  Chorus's existing dispatch code, invoked when an `improv` Line's step
  fires — the JS layer's job is only to mark the Line and let the
  dispatcher fire it at the right moment; the actual generation is a
  Python-side hook that doesn't exist yet.
- Open, not yet settled: how much prior-dialogue-in-this-scene context an
  `improv` Line's prompt should include (just the immediately preceding
  line? the full scene transcript so far, like Chorus gets the full
  completed transcript?). Worth deciding before implementation, not
  blocking this spec.

## 4a. Confirmed gap: Chorus and `arc-complete` are not wired together

`dispatcher.js` already has a fully implemented `fireArcComplete(zoneId)`
— bare form (scene-wide, any arc) or `:zoneId` form — and deliberately
skips the one-shot bookkeeping `tick()` uses for `declared` triggers,
because, in the code's own words, an arc completing "can legitimately
happen more than once across a session... per-take Chorus capture." That
sentence describes Chorus's real behavior precisely. But the function's
own comment says outright: *"Pushed by whatever completes an arc (the
not-yet-wired Chorus/arc-recording integration)."* `mccf_chorus.py`'s
`ChorusManager.fire_chorus()` and `dispatcher.js`'s `fireArcComplete()`
are two halves of the same idea, built independently, never connected.
This is real, scoped work — not a design question — and should be on the
list alongside the manifest/camera work already settled.

---

## 5. What this settles vs. what's still open

**Settled:**
- One shared character-voice mechanism for both call sites.
- Blank-Response-triggers-LLM is dead; `mode="llm"` is explicit.
- Chorus's trigger/firing mechanics unchanged; only its prompt source
  changes when `voice_actor` is set.
- Inter-scene persistence is out of scope, on record as future work.

**Still open, not blocking, worth flagging for whoever builds this:**
- Does zone `persona` ever coexist with/override a `voice_actor`'s
  Cultivar-driven prompt, or is Cultivar always authoritative once
  `voice_actor` is set? (§3)
- How much prior-transcript context a `mode="llm"` Step gets. (§4)
- The actual current state of `dialogue-xml.js`/`dispatcher.js` — this
  spec describes the *shape* of `mode="llm"`, but hasn't been checked
  against the real trigger/verb code yet, since those files haven't been
  read this session.
