# MCCF V5 Server Reference

How to install, start, check and use the MCCF server. The server is a Flask application (`mccf_api.py`) that also serves the browser pages from `static/`. Every page needs it running.

## 1. Install

1. Install Python 3.10 or newer.
2. `pip install flask flask-cors`
3. Optional, only if you want a real language model: `pip install anthropic`, `openai` or `google-generativeai` (Ollama needs no pip package). Without a key the Stub adapter is used.
4. Put the files in one folder, called here `mccf_full`:
   - the `mccf_*.py` server modules beside `mccf_api.py`
   - the pages and `js/` under `static/`
   - `schemas/`, `scenes/`, `cultivars/`, `zones/` as shipped

## 2. Start and stop

```
cd mccf_full
python mccf_api.py
```

The server listens on `http://localhost:5000`. Open `http://localhost:5000/static/mccf_launcher.html` for the launcher. Stop it with Ctrl+C. The server runs with `debug=True`, so it reloads itself when a `.py` file changes; after copying new files in, restart it by hand anyway.

## 3. Check an install

`verify_install.sh` compares every installed file with the release set and prints OK, STALE or MISSING. It needs bash (on Windows use Git Bash, with paths like `/d/...`). Run it from `mccf_full`:

```
bash verify_install.sh
```

"All files match." means the install is the release.

## 4. Folder layout (files the author works with)

| Content | Server folder |
|---|---|
| Pages | `static/` |
| Scripts | `static/js/` |
| Avatars (X3D) | `static/avatars/` |
| MIDI files | `static/x3d/X3DAssets/media/music/` |
| Ambient recipes | `static/x3d/X3DAssets/media/music/recipes/` |
| Ambient mappings | `static/x3d/X3DAssets/media/music/mappings/` |
| Scores | `static/x3d/X3DAssets/media/music/scores/` |
| Arc files | `scenes/<scene>/arcs/<take>/arc_*.xml`, and `scenes/_unscoped_arcs/*.xml` |
| Practical Instruction lessons | `static/pi/lessons/` (backups in `_backup/`, last 10 kept) |
| Lesson media | `static/pi/media/` |
| Lesson session logs | `pi_logs/<lesson code>.jsonl` beside `mccf_pi.py` |
| Schemas | `schemas/` |

General rule: the author does not have to memorize this tree. Every open, load, import, save and export control in the pages lists the files already in the right folder.

## 5. Modules

| Module | Role |
|---|---|
| `mccf_api.py` | Main server; field, agents, scenes, arcs, cultivars, zones; registers all the others |
| `mccf_core.py` | Agent, CoherenceField, Librarian, Gardener |
| `mccf_ambient_api.py` | Ambient engine support: lighting, MIDI, recipes, file lists, arc state |
| `mccf_hanim_api.py` | Avatars and H-Anim: upload, wire joints, displacers, export |
| `mccf_pi.py` | Practical Instruction lessons, media, session log, report |
| `mccf_reports.py` | Report listing |
| `mccf_reaper.py` | Scene audio assets and the Reaper link |
| `mccf_x3dedit.py` | Configuration and launch of the X3D editor |
| `mccf_versions_api.py` | Scene versions and drafts |
| `mccf_playback.py` | Arc and waypoint playback |
| `mccf_chorus.py` | Chorus voices |
| `mccf_voice_api.py` | Voice and dialogue |
| `mccf_scene_wrapper.py` | Scene wrapping |
| `mccf_zone_attractor.py` | Zone attractors |
| `mccf_energy.py`, `mccf_neoriemannian.py`, `mccf_cultivar_lambda.py`, `mccf_cultivars.py`, `mccf_hotHouse.py`, `mccf_llm.py`, `mccf_effects_registry.py` | Supporting engines |

## 6. Routes added or changed in V5

Ambient (`mccf_ambient_api.py`)

| Route | Use |
|---|---|
| `GET /ambient/state`, `POST /ambient/sync` | Field state to and from the engine |
| `GET /lighting/state`, `/lighting/scalars`, `/lighting/x3d` | Lighting from field state |
| `POST /ambient/save_midi`, `POST /ambient/save_recipe` | Save a MIDI file or recipe; `?overwrite=1` to replace |
| `GET /ambient/media_midi` | MIDI files in the scene media folder |
| `GET /ambient/files?type=` | List files of one kind, newest first |
| `GET /ambient/file?type=&name=` | Read one file |
| `POST /ambient/save_file?type=&name=` | Save one file; refuses to replace unless `overwrite=1` |
| `GET, POST /ambient/arc/state` | Arc binding state |

Practical Instruction (`mccf_pi.py`)

| Route | Use |
|---|---|
| `GET /pi/lessons`, `GET /pi/lesson` | List lessons, read one |
| `POST /pi/lesson` | Save a lesson; the old file is backed up first |
| `GET, POST /pi/media` | List or upload lesson media |
| `GET, POST /pi/log` | Read or append session logs |
| `GET /pi/report` | Per-lesson summary of sessions |

Other

| Route | Use |
|---|---|
| `GET /reports`, `GET /reports/<id>` | Reports |
| `GET /scene/names`, `/scene/audio_assets`, `/scene/registry` | Scene lists |
| `GET, POST /reaper/config`, `POST /reaper/open` | Reaper path and launch |
| `GET, POST /x3dedit/config`, `POST /x3dedit/open` | X3D editor path and launch |
| `GET /avatar/list`, `POST /avatar/upload`, `POST /hanim/export` and others | Avatars and H-Anim |
| `GET /scene/versions`, `POST /scene/versions/save`, `/restore` | Scene versions |

## 7. Safety behaviour

- File saves are written atomically (temporary file, then rename), and a name that would leave the target folder is refused.
- Saving over an existing file asks first (the page) and requires `overwrite=1` (the server).
- Lesson saves keep dated backups.
- The Loader writes nothing to disk.
- Avatar export rewrites the avatar X3D; keep a copy of the original first.

## 8. Troubleshooting

| Symptom | Remedy |
|---|---|
| A page says the server is not reachable | Start `python mccf_api.py`; check the API URL is `http://localhost:5000` |
| A new button or file list is missing | The old file is still installed. Run `bash verify_install.sh` and replace anything STALE |
| A route returns 404 | The matching `mccf_*.py` is missing or old; restart after copying it in |
| PI report shows 0% finished | Correct if no session has finished; a session in progress has `"end": null` |
| Browser shows an old page | Hard refresh (Ctrl+F5) |
