# MCCF Day 80 Build — Guided Test Procedure

Covers everything changed this cycle: the X3D export fixes in
`mccf_scene_composer.html`, the Timeline/Dialogue editor rebuild
(`mccf_timeline_dialogue_prototype_v2.html`), and the voice/lexicon layer
(`mccf_voice_api.py` + `lexicon_packs/default_narrative.json`). Not testing
the Observation Model architecture — nothing from that note is built yet.

Work through sections in order; later sections assume earlier ones passed.
Record pass/fail and notes inline as you go — this doc doubles as your test
log if you fill it in.

---

## A. Setup

- [ ] Server running with the updated `mccf_api.py`, `mccf_voice_api.py`,
      `mccf_couplers.py` in place.
- [ ] `lexicon_packs/default_narrative.json` present **as a sibling
      directory to `mccf_voice_api.py`**, not under `static/`. Quick check:
      `GET /voice/lexicon` should return `pos_count: 19, neg_count: 18` — if
      it returns different counts or a 404, the pack isn't where the loader
      expects it.
- [ ] Updated `mccf_scene_composer.html` and
      `mccf_timeline_dialogue_prototype_v2.html` deployed to wherever
      Composer serves its static files from.
- [ ] Test scene ready: something with **at least one zone/waypoint name
      containing an apostrophe** (e.g. "Enhedhuanna's Garden"), **at least
      one avatar assignment**, and **at least one waypoint with authored
      Question/Response/Statement dialogue** already on it. If your Garden
      scene from earlier sessions still has these, reuse it — it's exactly
      the shape this needs.

---

NOTE:  Asset assignments for zones only enable rotation in Y Axis.  Need rotation in
X and Y axis.

## B. Composer — X3D export fixes

These three bugs were the reason this cycle started. Confirm all three are
actually gone before testing anything downstream.

**B1 — Apostrophe in a name no longer breaks the export**
1. Open the test scene in Composer, confirm the apostrophe-bearing zone
   name is present (Scene tab or Place tab).
2. Export the scene XML.
3. Open the exported file in the Events tab's embedded viewport, **and**
   separately in standalone X_ITE.
- [ ] **Pass:** both load the scene normally. **Fail:** "Couldn't parse
      X3D" / "Failed loading world" in either — if this happens, the fix
      didn't ship or got reverted; stop here, this blocks everything else.


Pass.  Apostophe accepted.


**B2 — Avatar path**
1. In the exported XML, find the `<Inline DEF="HAnim_...">` line for your
   assigned avatar.
- [ ] **Pass:** URL is `../avatars/<filename>.x3d` (avatars/ folder
      present). **Fail:** URL is missing the `avatars/` segment (e.g. just
      `../cindy_hanim.x3d`).

Pass.  Both avatars present in scene.



**B3 — No more "cue request timed out" toast**
1. In Actors tab, assign or re-assign an avatar to any agent.
2. Watch for the save toast.
- [ ] **Pass:** "Avatar assignment saved for [name]" with no error.
      **Fail:** "Save aborted: cue request timed out..." — if this
      appears, the fix to `saveHanimSrc()`/`exportSceneXML()` didn't ship.
3. Repeat using the main Export button (not just avatar save) to confirm
   the same fix applies there too.

Pass.  Avatar reassignment correct.  We need to look at positions of zone cameras.  They do not observe zone.

## C. Timeline/Dialogue editor — legacy waypoint merge

**C1 — Legacy dialogue appears, read-only, correctly labeled**
1. Open the Timeline/Dialogue tab against the test scene.
2. Scroll below the per-Actor dialogue editor.
- [ ] **Pass:** a "Waypoint Dialogue · legacy · read-only" panel appears,
      grouped by waypoint name, each line showing a colored
      Question/Response/Statement badge matching what you authored in
      Composer's waypoint panel, plus speaker name and line text.
      **Fail:** panel missing, empty, or badges don't match what's
      actually on the waypoints in Composer.
3. Try to click into/edit a legacy line's text.
- [ ] **Pass:** nothing is editable — it's plain text and badges only, no
      inputs. **Fail:** anything in this panel accepts input.

**C2 — No legacy dialogue, no panel**
1. Open the Timeline/Dialogue tab against a scene (or a copy) with **no**
   waypoint dialogue authored at all.
- [ ] **Pass:** the legacy panel section doesn't render at all (no empty
      box, no header with zero content). **Fail:** an empty/awkward
      section still shows.

---

## D. Dialogue line type (Question/Response/Statement)

**D1 — New line defaults correctly**
1. Select an Actor with a dialogue track, click "Add line."
- [ ] **Pass:** new line's badge reads "Statement." **Fail:** anything
      else, or no badge at all.

**D2 — Type dropdown works**
1. Open the new line's editor, change Type to "Question."
- [ ] **Pass:** the badge on the card header updates immediately to
      "Question" (amber). Switch to "Response" — badge updates to teal.
      **Fail:** badge doesn't update, or updates to the wrong color.

**D3 — Type survives a save/reload round trip** *(this was the original
bug — type used to silently flatten to Statement)*
1. Set a line's type to "Question," give it real content, save/export the
   scene.
2. Reload the scene fresh into the Timeline/Dialogue tab (close and
   reopen, or hard refresh).
- [ ] **Pass:** the line still shows "Question." **Fail:** it's reverted
      to "Statement" — this is the exact regression this fix targeted.

---

## E. Voice tag panel

**E1 — Manual authoring + auto-promote to "authored"**
1. On any dialogue line, type free text into the Voice tag textarea (e.g.
   `[warmly] Welcome home.`).
- [ ] **Pass:** badge next to "Voice tag" reads "authored." **Fail:**
      badge stays "not tagged" or shows something else.

**E2 — Quick-tag buttons insert at cursor**
1. Click into the middle of existing ttsText, click a quick-tag button
   (e.g. `[excited]`).
- [ ] **Pass:** tag is inserted exactly at the cursor position, not
      appended to the end or prepended to the start. **Fail:** wrong
      insertion point.
2. Confirm the button set matches: `whisper, dismissive, annoyed, sad,
   appalled, angry, thoughtful, happy, excited, surprised, cute` — this is
   the real `derive_emotion_tag` vocabulary, not a generic placeholder set.

**E3 — Generate tag: empty content**
1. On a line with no dialogue text yet, click "Generate tag (sentiment)."
- [ ] **Pass:** inline message "No line text to analyze yet." **Fail:**
      button does nothing visible, or throws an error to console with no
      user-facing message.

**E4 — Generate tag: the actual bug-fix regression test**
1. Use a line with real dramatic content — good candidates from the
   Garden scene: *"I am so excited to finally be home in the Garden
   again!"* or *"I am terrified, something feels wrong here."*
2. Click "Generate tag (sentiment)."
- [ ] **Pass:** tag is something plausible for the content (`happy`/
      `excited` for the first, `sad`/`angry`/`appalled` for the second).
      **Fail — this is the core bug:** tag comes back `dismissive`
      regardless of content. If this fails, check `GET /voice/lexicon`
      first (§A) before assuming the fix regressed — a missing/misplaced
      pack file will silently reproduce the original bug.
3. Confirm the tagSource badge now reads "algorithmic."

**E5 — Manual edit demotes/promotes correctly**
1. After E4, manually edit the generated ttsText.
- [ ] **Pass:** badge flips from "algorithmic" to "authored" the instant
      you type. **Fail:** badge stays "algorithmic" after a human edit.

**E6 — Clear tag**
1. Click "Clear tag."
- [ ] **Pass:** both the ttsText field and the badge reset to "not
      tagged" together. **Fail:** one clears without the other (a
      dangling tagSource with no text, or vice versa, is invalid per
      schema).

---

## F. Affect channels panel

**F1 — Enable/default values**
1. Check "Affect channels" on any line.
- [ ] **Pass:** four fields (E/B/P/S) appear, each defaulting to `0.25`,
      plus an empty interpreter name field. **Fail:** fields missing,
      wrong defaults, or interpreter field absent.

**F2 — Clamping**
1. Type a value `>1` or `<0` into any channel field, tab out.
- [ ] **Pass:** value clamps to `1` or `0`. **Fail:** out-of-range value
      is accepted and saved.

**F3 — Disable clears the whole group**
1. Uncheck "Affect channels."
- [ ] **Pass:** all four channel values and the interpreter name disappear
      together. **Fail:** any of the five fields survives independently
      (schema requires all-or-nothing).

**F4 — Generate tag also fills channels, only when already enabled**
1. On a line **with** Affect channels already checked, click "Generate tag
   (sentiment)."
- [ ] **Pass:** the four channel values update from the server response,
      interpreter defaults to "sentiment (auto)" if it was empty.
2. On a **different** line with Affect channels **unchecked**, click
   "Generate tag (sentiment)."
- [ ] **Pass:** Affect channels panel stays off — Generate tag must not
      silently turn it on for you. **Fail:** the checkbox gets enabled
      automatically.

---

## G. Full round-trip — the original data-loss bug

This is the fix that made everything in E and F actually matter — confirm
none of it evaporates on save.

1. On one line: set type = Question, author a voice tag, enable affect
   channels with non-default values and a real interpreter name.
2. Save/export the scene.
3. Close the Timeline/Dialogue tab entirely and reopen it against the same
   scene (not just re-render — a genuine reload).
- [ ] **Pass:** type, ttsText, tagSource, and all four channel values +
      interpreter are exactly as you left them. **Fail:** any field is
      blank, reset to a default, or the tagSource/type has changed —
      this was the original silent-data-loss bug and is the most
      important single test in this whole procedure.

---

## H. Lexicon API (optional — only if you plan to extend vocabulary)

1. `GET /voice/lexicon` — confirm it returns the pack with correct
   pos/neg counts and word lists.
2. `POST /voice/lexicon` with `{"add_neg": ["dank"]}`.
3. Generate a tag on a line containing "dank" that previously had no
   lexicon-word hits.
- [ ] **Pass:** the new word is detected immediately (no server restart
      needed) and influences the tag. **Fail:** no effect, or requires a
      restart.
4. Check the pack file on disk — confirm "dank" was persisted, not just
   held in memory.

---

## What this procedure does *not* cover

No part of the Observation Model / Evidence Object / PersistenceField
architecture from the Day 81 note — none of it is built. Nothing here
tests `/couplers/tick`, `/arc/record`, trust dynamics, or receptivity
directly; those are confirmed live via the loader source, not via this
editor, and aren't part of what changed this cycle.
