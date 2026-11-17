# Change log: repo (HEAD 4baa6a8, 2026-10-10) to V5 (v5.0.0, 2026-11-16)

New files (not in the repo)
- server: mccf_pi.py, mccf_reports.py, mccf_reaper.py, mccf_x3dedit.py, mccf_effects_registry.py
- static/js/mccf_serial.js
- schemas/mccf_pi.xsd
- pi/MCCF-P-10-01-00-00A-520A-D.xml (sample lesson) and reference images
- verify_install.sh

Changed (differs from the repo copy)
- server: mccf_api.py, mccf_ambient_api.py, mccf_hanim_api.py, mccf_chorus.py, mccf_playback.py, mccf_scene_wrapper.py, mccf_versions_api.py, mccf_voice_api.py, mccf_zone_attractor.py, mccf_energy.py, mccf_neoriemannian.py, mccf_cultivar_lambda.py, mccf_cultivars.py, mccf_hotHouse.py, mccf_llm.py
- pages: ambient, character creator, dashboard, dialogue editor, events editor, launcher, PI, route graph, scene composer, X3D loader

Unchanged: mccf_core.py

Notes
- The repo's other pages (constitutional, energy, lighting, voice, waypoint editor and so on) are not in the release set; they stay as they are.
- Highlights since the repo: serial mode, file lists, PI log fix, H-Anim duplicate-declaration fix, install check script.

Since the release set above (2026-11-07 to 2026-11-09)
- Composer: placeholder cameras (Front, Side, Back at 3.5 m); actor name label lowered; trackball and rotation helpers; folder pickers; placeholder avatar can be restored; lights can follow an actor (position only, or turning with it); zone option to drive the Ambient Composer.
- Loader: Ambient drawer (hidden engine frame, zone scale on enter and exit); voice falls back to a local voice when an online voice fails; zone-command speech fixed; stale zone commands dropped when the arc ends; default zone release is silent.
- Ambient Composer: accepts start, stop, scale, root and volume commands from a parent page.
- Voice API: optional max_sentences and max_tokens for short waypoint answers.
- Schema: AmbientTheme drive; Light follow and followTurns.
- Licence files added: LICENSE (Apache-2.0), NOTICE, LICENSE-DOCS.md (CC BY 4.0), CONTRIBUTING.md, README opening, docs/ECOSYSTEM_PRINCIPLES.md.

Since 2026-11-09 (to 2026-11-13)
- Ambient: transport bar with Pause; Video view tempo map and "bars to Grid / Notation"; empty-bar Notation staff; mccf_midi.js and mccf_notation.js patched for it.
- Loader: idle timers for all avatars; mccfPerf(); face caps.
- New: mccf_videosync.js, mccf_progression.js, tests.

Since 2026-11-13 (to 2026-11-16)
- Help Composer: Getting Started modules 1 and 2, ICN-named pictures with a graphics register, video, live callouts (on/off, numbers on/off, groups per frame), tabs for several pictures, Enlarge, read-aloud with spoken replies, Refresh picture list, captions in the picture list.
- Ambient Composer: Repeat transform; Save block at the top; renamed from Ambient Engine.
- Launcher: cards for Ambient Composer and Help Composer; collapsible descriptions.
- Guide: User's Guide and Systems Implementation Guide published under docs/guide/.
- Repository: example scene ConeAndCamera, Anna avatar, schemas for the lessons (mccf_pi.xsd); test files and session notes removed; obsolete demo page removed.
