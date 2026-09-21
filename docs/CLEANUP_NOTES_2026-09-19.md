# H-Anim Editor + export cleanup — Task 1 (2026-09-19)

**Status:** code done and tested offline against your real `Anna.x3d`. **Not yet run live** — that is your acceptance test below.
Files: `mccf_hanim_api.py` (server), `mccf_character_creator.html` (client), `hanim_test.zip` (harness + exact diffs).

## What was wrong (all reproduced offline on the real endpoint before fixing)
Your first-click scenario on the ORIGINAL code: `Timer6` deleted, 51 dangling ROUTEs, cultivar Bow→`Timer8` (scene imports `BowTimer`), Wait→`Timer13` (has no EXPORT — unreachable). Plus two things the resume didn't have:
- **S5 (new):** authored keyframes are keyed by joint *name* but ROUTEs need the *DEF*. In Anna 38 of 96 joints differ (`L-Thigh` vs `L_Thigh`), so any authored clip emitted dangling ROUTEs. Would have hit Cindy.
- **Backup (new):** `_hanim_backup` kept one `.bak`, overwritten every export — two exports in a row destroyed the only good copy.

## Changes (each is separate; tests in the zip name them)
| # | Where | Change |
|---|---|---|
| P1 | server `_write_clip_nodes` (S1/S2) | Rewritten. A timer with ROUTEs is never stripped/rewritten. "Authored" = a keyframe actually holds joints. Only this writer's own earlier output can be replaced. Keyframes on a real clip are ignored **with a warning**. |
| P2 | server (S4) | Clip's own `timerDEF` (DEF **or EXPORT alias**, e.g. `BowTimer`) is kept as sent. Label fallback only picks timers that have an EXPORT. Cultivar merge keeps keys it doesn't own. |
| P3 | server | Joint name→DEF mapping; interpolator DEFs `<timer>_Interp_<joint>`, sanitised (old naming never matched its own cleanup → duplicates). |
| P4 | server | **Integrity gate:** compares the file before/after; refuses (HTTP 409, writes nothing) if the export would add a dangling ROUTE, undefined EXPORT, duplicate/whitespace DEF. Anna's 5 existing whitespace stubs don't block. |
| P5 | server | Timestamped backups in `backups/` beside each file (newest 5) in addition to `.bak`. |
| P6 | server (S3) | `/hanim/joints` clips now carry `routes`, `hollow`, `exported_as`; `loop` default fixed (X3D default is **false**; Bow/Idle/Wait were shown as looping). |
| P7 | server | `cameraRig` absent/null = leave CAM_* nodes alone (explicit `{}` still replaces — old contract). |
| C1 | client | `hePoseClipPropChanged` never reassigns `timerDEF`; records `_loopEdited` only when *you* change Loop. E_max=0 no longer coerced to 1. |
| C2 | client | Clip dropdown rendered right after cultivar load (and on Pose-tab open). |
| C3 | client | Unedited clips send `keyframes: []`; hollow timers hidden from playback panel/seeding; server refusal (409) text now shown; server notes shown; `cameraRig` sent as `null` until the rig state has loaded/been edited. |

Loop semantics: ticking Loop writes `loop=` to that clip's real timer in the file **only if you changed it** (`loop_edited`); untouched clips are never modified. Unticking later writes an explicit `loop="false"` where the attribute used to be absent — same meaning in X3D.

## Evidence
- Server: 36/36 scenario checks patched vs **9/33 on the original** (tests can fail).
- Client (real HTML in jsdom): 20/20 patched vs 10/20 original.
- Client × server matrix for "load Anna → tick Loop on Bow → Export": original×original **damaged**; patched client + original server **still damaged** (server fixes are essential); original client + patched server healthy; patched×patched healthy, only change = `Timer8.loop`.
- No-op export of Anna is structurally identical to the input (nodes, attributes, ROUTE set).
- Not covered: real `mccf_cultivar_lambda.py` (stand-in used; cultivar reconstructed from the resume), a real browser, X_ITE playback.

## Your live acceptance test (one step at a time)
0. Dated backup of `Anna.x3d` + `cultivars/cultivar_anna.xml`; commit. Install both files, restart the server.
1. `python3 audit_x3d.py static/avatars/Anna.x3d` → 144 TimeSensors, 106 EXPORTs, 1,526 ROUTEs, 0 dangling.
2. Open Anna in the editor → Pose tab. **Pass:** clip dropdown already filled; playback panel ~14 buttons, not ~96.
3. Tick Loop on Bow. **Pass:** Network tab → export payload later shows Bow `timerDEF` unchanged.
4. Export. **Pass:** status says `loop set: Timer8 loop=true`; audit → same counts, 0 dangling; only `Timer8` differs (`diff_x3d.py`).
5. Untick, Export again → back to original meaning. Scene ▶▶ All → Bow fires once.
Restore path if anything looks off: `static/avatars/backups/Anna.x3d.<timestamp>.bak`.

## Found, deliberately NOT changed (your call)
1. `_update_displacer_weights` strips the wrong namespace string, so it has **never updated a displacer** (returns 0). Fixing it would start baking AU slider weights into the file — behaviour change, so left alone.
2. Renaming a clip in the editor adds a second cultivar entry; the old one stays. Parked.
3. `+ new clip` then Save Character stores a `timerDEF` that doesn't exist in the file until keyframes are authored.
4. Camera rig: if `Anna.manifest.xml` were missing (404) while CAM_* nodes exist in the file, export would remove them. Worth confirming the manifest exists.
5. Anna.x3d still contains ~82 hollow timers and 5 whitespace-DEF stubs. Harmless now, but no cleanup tool exists yet.

## Decision for you
Do you want a small "clean file" action (drop hollow/duplicate stubs, with the same integrity gate + backup) before Cindy, or leave Anna's clutter and start Cindy clean?
