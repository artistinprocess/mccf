# MCCF V5 release notes

Release date: 2026-11-15. Tag: v5.0.0. Licence: Apache-2.0 (code), CC BY 4.0 (docs).

## What V5 is
A scene composer, an X3D loader, a character creator, an H-Anim editor, an Ambient Composer, a Programmed Instruction (PI) tool, a Dashboard and a server that ties them together, with the User's Guide and a sample lesson.

## New since the 2026-11-02 release set
- Ambient Composer: transport bar (big clock at bottom center, Start/Stop and Pause beside it); Pause keeps the playhead line in Grid and Notation.
- Video view: a tempo map from a video's bars and sync points; "bars to Grid / Notation" sends empty bars, so Grid and Notation open with the right number of bars before any MIDI is loaded. Notation shows an empty staff for it.
- Loader: every loaded avatar idles with its default timer (two actors that share one avatar both animate); face-cap and smoothing settings; `mccfPerf()` frame-rate test from the browser console.
- Harmony and progression modules for the Ambient Composer (Neo-Riemannian chords, twelve-tone serial).
- User's Guide (15 chapters, six appendices) and the Systems Implementation Guide, both in docs/guide/.
- Help Composer: two Getting Started modules, pictures and video in lessons, live callouts on pictures, tabs for several pictures, Enlarge for pictures, video and the X_ITE window, read-aloud, spoken replies.
- Ambient Composer: Repeat transform, Save at the top of the pane.
- Launcher: a card for every tool, descriptions hidden by default.
- Example scene ConeAndCamera and the Anna avatar.

## Known issues (ship as is)
- Frame rate in large scenes (the Garden scene) can be low in Edge; see `mccfPerf()` in INSTALL.md. Work continues after release.
- Edge "Tracking Prevention blocked access to storage" messages at load are harmless.
- A few 404s for optional media at load are ignored.
- Notation uses one constant meter for the whole piece. Meter changes inside a piece are planned for V6.
- Some Guide statements were written from the code and have not yet been checked against a running install; they are listed for V6.
- The Scene Music walkthrough and the Loader's "What is saved" section are not written yet.

## Install
See the Quick start in the README. To check an install against a download set, run `bash verify_install.sh` from the install folder (in the MCCF_V5.zip release asset).
