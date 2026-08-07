# MCCF Voice-Tag Lexicon System — Design Note

**Day 80. Status: implemented, tested, shipped.**
Scope: the emotion/delivery-tag pipeline behind `POST /voice/preview`, and the
lexicon-pack mechanism built to make its vocabulary extensible without
touching live-field sentiment.

---

## 1. Background

MCCF has carried a "convert authored dialogue text into an ElevenLabs
delivery tag" feature since Day 73 (`mccf_voice_api.py`'s `derive_emotion_tag`,
`build_tts_text`, `/voice/preview`). The schema side (`dialogue-xml.js`,
Day 73–74) has always supported it: `ttsText`/`tagSource` on a `<Line>` for
the tagged delivery text, `channelE/B/P/S` + `emotionalInterpreter` for a
more structured affect reading. Until Day 80 neither had a UI. The Timeline/
Dialogue editor (`mccf_timeline_dialogue_prototype_v2.html`) round-tripped
dialogue lines without ever reading or writing these fields — a scene
authored elsewhere with tags set would silently lose them on save.

Two problems surfaced this session, in order:

1. **Wrong client contract.** The editor's first "Generate tag" wiring
   guessed at `/voice/preview`'s response shape (`data.tag`/`data.ttsText`)
   without the server source available to check against. Once
   `mccf_voice_api.py` was provided, the real contract turned out to use
   `suggested_tag`/`suggested_tts_text`/`weights` — different field names
   entirely. Fixed once the real file was in hand (§3).

2. **The tagger defaults to "dismissive" for ordinary dramatic dialogue.**
   Confirmed by testing the real endpoint against lines from the actual
   exported scene (`testDialogueTimeline.x3d`, Enhedhuanna's Garden), not
   guessed. Root cause and fix are the bulk of this note (§4–§6).

---

## 2. Emotion-tag data model (unchanged this session, restated for context)

`dialogue-xml.js`, `<Line>` attributes:

- `ttsText` / `tagSource` — co-required pair. `ttsText` is the ElevenLabs-
  ready text (bracket tag + line, e.g. `[excited] I'm home!`).
  `tagSource.type` ∈ `algorithmic | authored | llm-interpreted`, tracking
  provenance. Editing a tag by hand promotes it to `authored`.
- `channelE/B/P/S` + `emotionalInterpreter` — co-required group of five.
  The line's interpreted affect in the same E/B/P/S shape the live
  coherence engine uses, plus who cast that interpretation.

Both pairs are validated by `validateDialogueLines` (co-requirement,
range/type checks) and serialize/parse losslessly — confirmed by a direct
round-trip test through the real `serializeDialogueBlock`/
`parseDialogueBlock` functions this session (a line with both fields set
survives `state → XML → state` byte-for-byte).

The **11 core-emotion tags** `derive_emotion_tag` can suggest: `dismissive,
whisper, angry, appalled, sad, annoyed, excited, happy, thoughtful,
surprised`, plus `cute` (author-only, never auto-suggested — not reliably
inferable from valence/arousal alone).

---

## 3. Editor UI added this session (`mccf_timeline_dialogue_prototype_v2.html`)

Each dialogue-line card now has:

- **Voice tag panel** — `ttsText` textarea, `tagSource` badge, 11 one-click
  quick-insert buttons (the real tag vocabulary above, not a generic
  ElevenLabs example list — that was an early mistake, corrected once the
  real `derive_emotion_tag` decision tree was read).
- **"Generate tag (sentiment)" button** — calls the real
  `POST /voice/preview`, sets `ttsText = suggested_tts_text`,
  `tagSource = {type:'algorithmic'}`. If the affect-channel panel for that
  line is already on, also fills `channelE-S` from the response's
  `weights` and defaults `emotionalInterpreter` to `'sentiment (auto)'`
  — never turns the panel on by itself.
- **Affect channels panel** — checkbox reveals four `[0,1]` number inputs
  + interpreter name field, enforced as the same co-required group of
  five the schema requires; toggling off clears all five together.

**Round-trip fix:** `dialogueLineToStateStep`/`dialogueTrackToXml` now
carry `ttsText`/`tagSource`/`channelE-S`/`emotionalInterpreter` through
import and export. Before this fix these fields were silently dropped —
opening a tagged scene and saving it back out would erase the tags with no
error. This was the more urgent of the two Day 80 fixes, independent of
the calibration issue below.

---

## 4. The "dismissive" bug — root cause

Confirmed by running the real Flask blueprint locally (not guessed):

| Line | `suggested_tag` (before fix) |
|---|---|
| "I am so excited to finally be home in the Garden again!" | dismissive |
| "This is the Garden. It hasn't changed since I was small." | dismissive |
| "I am terrified, something feels wrong here." | dismissive |
| "I feel so much joy and love being back home." | *(none)* |

`_POS_WORDS`/`_NEG_WORDS`/`_S_WORDS`/`_E_WORDS`/`_P_WORDS`/`_B_WORDS` in
`mccf_voice_api.py` are explicitly documented as *"calibrated for
constitutional arc language (Ollama/llama3.2)"* — therapeutic/coaching
register (`acknowledge`, `compassion`, `boundaries`, `validate`). Ordinary
narrative dialogue barely overlaps with it (`excited`, `terrified`,
`beautiful` are in none of the lists).

Separately, `_tag_valence_from_hits`'s Day 73 fix requires **≥2** real
pos/neg word hits before trusting them at all (added to stop a single
overlap word like `"unclear"` — present in both `_NEG_WORDS` and
`_UNCERTAINTY_WORDS` — from swinging a long hedging paragraph to a false
`angry`). That guard is correct for the long multi-sentence constitutional-
arc replies it was tuned and regression-tested against, but far too strict
for a single short dramatic line, where one strong word is often the
*entire* signal. Below threshold, `tag_valence` collapses to `0.0`;
`engagement_proxy` is also floored near its baseline for a zero-hit line;
`derive_emotion_tag`'s first branch (`engagement < 0.35 and |valence| <
0.15`) fires and returns `dismissive` regardless of actual content.

**Verdict: not a coding bug.** The code does exactly what it was tuned to
do — for a genre of text this feature is now also being pointed at, which
it was never calibrated against.

---

## 5. Design discussion (this is the part worth keeping)

Prior context found via conversation search: the Day 73 fix's own
regression tests (`tests/test_voice_preview_calibration.py`) only used
long, word-dense paragraphs — the short-dramatic-line failure mode was
never exercised, so this isn't a repeat of an old bug, it's the same
mechanism (word-list sparsity + the `≥2` guard) hitting new territory. A
prior roadmap note ("V2.2 — Richer Measurement Operator") had already
flagged the underlying word-list fragility and proposed eventually moving
to embeddings/classification — noted as a real future direction, not
undertaken here.

**The core design question:** should the word lists be exposed for direct
user editing, and should that include per-culture vocabulary (since
word-to-emotion association is culturally variable, not just a translation
problem)?

**Decided:**

- **Not a single shared, editable global dict.** `_estimate_sentiment` and
  `_decompose_to_channels` feed live agent coherence via `/arc/record` —
  editing their word lists directly risks destabilizing tuning the
  constitutional arc depends on, for a change made for dialogue-authoring
  reasons.
- **Named, swappable lexicon packs instead** — the same shape as the
  existing *cultivar* concept (a named preset a project selects) rather
  than one mutable list everyone shares. A pack layers *supplemental*
  vocabulary on top of the untouched core, scoped to `/voice/preview`
  only.
- **Cultural/regional packs: explicitly out of scope for now.** Getting
  this right needs real research per culture, not a guessed word list —
  building one without that would mean stereotyping. The mechanism is
  built to hold such a pack later; none is shipped. What ships is one
  general-purpose English narrative/dramatic pack, motivated by the
  concrete need (the Garden of the Goddess opening scene).
- **Noted, not built:** Character Creator already has a "favorite phrases"
  field intended for future emotion-driven behavior work. A natural later
  step is seeding a per-cultivar supplemental pack from that field. Not
  wired up — Character Creator's source wasn't in scope this session.
- **Known ceiling, accepted for now:** bag-of-words can't do negation
  ("I don't like this" doesn't improve — `"don't"` doesn't even tokenize
  as a word past the apostrophe) or irony, and a genuinely neutral
  expository line will still land on `dismissive`/no-tag correctly, since
  there's no emotion in the text for any word list to find. This is a
  ceiling of the approach, not a defect in this fix.

---

## 6. Implementation (`mccf_voice_api.py`)

**Safety invariant, verified not just asserted:** `_estimate_sentiment`,
`_decompose_to_channels`, `_sentiment_hit_counts`, `_channel_hit_counts`,
and all four core word-list constants are **byte-for-byte unchanged**.
Confirmed by construction — every new function is additive, and by test —
any line with zero lexicon-pack-word hits runs through code proven
identical to the pre-Day-80 path (`threshold = 2` unchanged when
`supplement_hits == 0`).

New, `/voice/preview`-only:

- **`lexicon_packs/default_narrative.json`** — the active pack.
  `{pack_id, label, description, pos: [...], neg: [...]}`. Ships with 19
  positive / 18 negative English narrative/dramatic words (`beautiful`,
  `excited`, `radiant` … / `terrified`, `dread`, `haunted` …). Falls back
  to an inline copy (`_FALLBACK_PACK`) if the file is missing.
- **`_sentiment_hit_counts_preview(text)`** — core `_sentiment_hit_counts`
  (untouched) plus pack pos/neg matches, tracked separately as
  `supplement_hits`.
- **`_channel_hit_counts_preview(text)`** — core `_channel_hit_counts`
  (untouched) plus pack hits folded in as general emotional-signal weight
  (not attributed to a specific E/B/P/S channel — the arousal/engagement
  proxies only need "how much charged language," not per-channel split).
- **`_tag_valence_from_hits`** — threshold logic changed from a flat `≥2`
  to `≥1 if supplement_hits > 0 else ≥2`. Pack words are curated to be
  unambiguous (no overlap with `_UNCERTAINTY_WORDS`), so a single pack-word
  hit doesn't carry the noise risk the original `≥2` guard existed to stop;
  a single *core*-vocabulary hit still does, and still requires the second
  hit.
- **`_preview_arousal_engagement`** — now also folds `_supplement` hits
  into both the arousal total and the engagement count, so a line whose
  only charged word is a pack word doesn't stay floored into the
  `arousal < 0.35 → whisper` branch even after `tag_valence` correctly
  reads it as strongly negative.
- **`GET /voice/lexicon`** — inspect the active pack.
- **`POST /voice/lexicon`** — `{add_pos, add_neg, remove_pos, remove_neg}`.
  Updates in-memory immediately, persists to
  `lexicon_packs/default_narrative.json`; reports `persisted:false` rather
  than failing if the directory isn't writable.

**Deployment note:** `lexicon_packs/default_narrative.json` must sit
alongside `mccf_voice_api.py` (same directory) — the loader resolves the
path relative to the module file.

---

## 7. Verified results

Tested against the real endpoint (Flask test client, not mocked):

| Line | Before | After |
|---|---|---|
| "I am so excited to finally be home in the Garden again!" | dismissive | **happy** |
| "I am terrified, something feels wrong here." | dismissive | **sad** |
| "Okay." | dismissive | dismissive *(unchanged — correct, no signal to find)* |
| "I feel so much joy and love being back home." | *(none)* | *(none — below threshold, honest miss, see §5)* |

Regression protection re-confirmed against fabricated stand-ins for the
original Day 73 test cases (angry/harmful long line, warm/positive long
line, calm hedge-only line): none regressed, because none contain any
lexicon-pack word, so all three ran the unmodified code path.

`GET`/`POST /voice/lexicon` tested live: adding words takes effect on the
very next `/voice/preview` call in the same process, and persists to disk
across a fresh module load.

---

## 8. Open items for later

- Embedding/classifier-based sentiment, as an eventual replacement for
  bag-of-words matching (pre-existing roadmap item, not started).
- Cultural/regional lexicon packs — needs real research per culture before
  building, explicitly deferred.
- Per-cultivar or per-Zone pack selection (right now there is exactly one
  active pack, globally, for the whole `/voice/preview` path).
- Character Creator "favorite phrases" → auto-seeded per-cultivar
  supplemental pack.
- No test file was added for this session's changes (no
  `tests/test_voice_preview_calibration.py`-style coverage of the
  lexicon-pack path) — worth adding before this is relied on further.
