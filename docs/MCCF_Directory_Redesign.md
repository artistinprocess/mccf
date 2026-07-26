# MCCF Directory Redesign — Design Note

*Status: design agreed, not yet implemented. No code written against this document as of this writing.*

## 1. Why this exists

The current flat, type-first directory layout has a structural gap: nothing on disk scopes a file to the scene it belongs to. Scoping lives only in metadata (a `scene_name` field inside arc/zone files), which nothing enforces. This surfaced as a real bug during Day 67 testing — a previously-recorded arc from one scene sat selected in the playback dropdown while a different scene was loaded in the viewport, looking valid when it wasn't. That bug has a frontend stopgap in place (the arc selection is now forcibly cleared on every scene switch), but the actual fix is structural: make cross-scene bleed impossible by construction, not by convention.

This document is the target layout that fixes that, plus the reasoning behind each decision so it doesn't need to be re-derived later.

## 2. Root directory (unchanged root, `mccf_full`)

```
mccf_full\
  zones\              — zone TEMPLATES (redesigned, see §5)
  scenes\              — scene folders (redesigned, see §4)
  arcPaths\            — renamed from exports\ (see §3)
  cultivars\           — character definitions (unchanged)
  HAnim\               — avatar staging before ingest to static\avatars (unchanged)
  static\              — unchanged
    Avatars\           — used by Character Creator (unchanged)
    x3d\               — X3D scenes for the Loader (unchanged)
      protos\          — X3D proto files (unchanged)
      media\
        convolver\     — (unchanged)
        soundeffects\  — (unchanged)
        images\        — NEW
        music\         — NEW
        video\         — NEW
```

## 3. Rename: `exports` → `arcPaths`

`exports` said nothing about what it contained. `arcPaths` is unambiguous — this is where recorded emotional-arc playback files live. Content and format unchanged; only the directory name changes.

## 4. Scenes are containers, not files

A scene is a named folder, not a single XML file. Everything specific to one scene instance lives inside its own folder:

```
scenes\
  Saturn1Test1\
    Saturn1Test1_scene.xml         — the scene wrapper (unchanged format)
    arcs\
      FirstCameraPass__2026-07-11T1420\
        arc_Cindy_...xml
        arc_Salida_...xml
      SecondPass__2026-07-12T0930\
        arc_Cindy_...xml
```

Rationale: this is what makes the arc-scoping bug structurally impossible rather than policy-enforced. An arc physically lives inside its scene's folder — there is no longer a global, flat pile of arcs from every scene that a UI has to filter correctly by trusting a metadata field. If the directory listing itself is scene-scoped, a wrong-scene arc can't appear in the picker no matter what the frontend forgets to check.

### 4.1 Takes / versions are sibling scene folders, not nested revisions

New versions of a scene (re-exports, iterations, deliberate variants) are **new sibling folders under `scenes\`**, not new files inside the old scene's folder:

```
scenes\
  Saturn1Test1\
  Saturn1Test1__CameraRework__2026-07-15T0900\
```

This was a deliberate choice, made explicit rather than defaulted into:

- **Why:** it extends the same scoping guarantee up one level. Two versions of a scene sharing no directory state means there's no structural mechanism for one version's data to bleed into another's, the same protection §4 gives arcs.
- **What's given up:** no structural notion that these folders are related — that's purely a naming convention, with the same fragility class as any convention (a typo or inconsistent naming won't be caught by the filesystem). If lineage tracking is ever needed, it's a small addition later — a `derived_from:` field inside the newer version's own metadata — not a directory-structure change.
- **Versions/takes accumulate deliberately, forever.** Deleting old takes is a file-management task for a human to do when they choose, not something this design automates or expects. This follows directly from where the project is headed: scene folders are the future repository of "takes" for playlist/take-assembly work, the same way a film editor keeps every take rather than only the one that made the final cut.

### 4.2 Take-folder naming: label + timestamp, combined

```
{SceneName}__{HumanLabel}__{ISO8601Timestamp}
```

Example: `Saturn1Test1__FirstCameraPass__2026-07-11T1420`

The label stays human-meaningful in a file browser; the timestamp guarantees uniqueness and gives free chronological sorting without parsing anything beyond what the filesystem already provides. This assumes the label survives path-safe sanitization (no slashes, colons, etc.) — the exporter is responsible for that sanitization. If a label ever needs characters that can't survive being part of a folder name, the sanitized version stays in the path and the original goes in a small metadata file alongside it — not needed today, just the fallback if it comes up.

## 5. Zones: template + instance, same shape as cultivars

### 5.1 What's actually there today (confirmed by reading real files, not assumed)

Checked an actual zone template file (`newSceneComoserTest1_zones.xml`) against the same scene's wrapper (`newSceneComoserTest1_scene.xml`): they contain byte-for-byte the same zone data (position, radius, weights, Chorus/Persona block), duplicated in two places. The standalone `zones\` file isn't a template at all as currently generated — it's scene-named, scene-specific, and nothing reads it back. Traced every call site in both frontend files: nothing fetches it. It's write-only dead weight from the frontend's side.

**One caveat, not yet resolved:** whether the backend's own X3D-generation step reads that file server-side to build zone geometry into the exported `.x3d`. That can't be confirmed without the backend code (`mccf_api.py`), and should be checked before actually deleting anything, not assumed safe.

### 5.2 Target shape

- `zones\` becomes a genuine **template library**, same role as `cultivars\` — a zone type (e.g. `Giparu.xml`) defined once, generically named (no scene prefix), holding what's reusable: descriptor, base weights, Chorus persona, ambient theme.
- The **instance** — which template was used, exact placement, and only the fields that override the template (radius, starting EBPS, which assets are actually present) — lives where it already effectively lives: inside the scene wrapper's own `<Zones>` block, now carrying a `template="Giparu"` reference.
- The current standalone per-scene `{scene}_zones.xml` file is retired under this shape — it was duplicating instance data that already has a home, without actually being a template.

This mirrors the cultivar pattern deliberately: design once, place many times, override per-placement — the same relationship a cultivar has to an agent instance placed in a scene.

### 5.3 Backend zone systems — audit findings, not yet wired

Three Python files exist for zones. Traced actual usage against both current frontend files:

- **`mccf_zones.py`** — the data model (`SemanticZone`, `Waypoint`, `AgentPath`, `SceneGraph`). Foundational; imported by the other two.
- **`mccf_zone_api.py`** — exposes that model via singular routes (`/zone`, `/zone/<name>`, `/zone/presets`). Technically called by the Composer, but structurally sidelined: the zone-placement POST discards its response (`.catch(function(){})`), and the startup GET is explicitly distrusted and overridden the moment a real scene loads (a past session already documented this exact staleness problem in a code comment). The actual source of truth for what gets saved is a separate client-side JS object, not this API's response.
- **`mccf_zone_attractor.py`** — the more sophisticated "V3" layer: zones with a `psi_zone` derived from descriptor decomposition (the dance-hall-vs-restaurant idea — a zone's semantic identity, computed once from its description, pulling agents toward it), per-agent coherence tracking, XML round-trip. Zero call sites found in either frontend file — built, never connected.

None of these three files need to change for the directory/template work in §5.2 — the actual duplicated zone data was never flowing through any of them. `mccf_zone_attractor.py` is the closer conceptual match to "zone as designed-once template with real semantic identity," and is a strong candidate to eventually become the real backend for §5.2 — but wiring it in is a separate, later decision, not a dependency of this directory pass.

## 6. Shared / global — unchanged, confirmed correct

`cultivars\`, `HAnim\`, `static\Avatars\`, `static\x3d\protos\`, and all `static\x3d\media\*` subfolders stay flat and type-organized, as they are today. These are genuinely reused across every scene rather than scoped to one — duplicating a cultivar or proto per scene would be worse, not better.

## 7. Deliberately left open — not decided, not precluded

These came up during the design conversation and were consciously not resolved now, so they don't get accidentally foreclosed by this pass:

- **Zone mutuality.** As built (and as this redesign preserves), a zone's `psi_zone` is a fixed identity set once at creation — it pulls agents toward it, and tracks how attuned each agent has become to it, but doesn't itself shift in response to who's currently present. A zone whose *own* state changes live based on current occupants is a distinct, real idea (confirmed as the intended reading, not a misunderstanding) that isn't built anywhere yet. Nothing in this directory design blocks adding it later.
- **Camera re-aim / parenting.** Parked pending its own scoping conversation (Day 66 §7), unaffected by this document.
- **Version = successive vs. variant.** This design assumes successive (each take supersedes conceptually, though all are kept) works fine for now, given the takes-repository framing. Whether "version" ever needs to mean parallel variant rather than succession was raised and not conclusively closed, though the takes framing makes it largely moot for the moment.
- **Agent-persistent memory across scenes.** Selective Persistence (per-cultivar retention profiles: working state / episodic traces / constitutional memory) and the coherence-scoped-imagination idea from the PAN/Futures piece both describe state that is per-agent-*instance*-over-time, evolving, and persisting *across* scene and take boundaries — Cindy's accumulated trust carrying from one take into the next. That doesn't cleanly fit either bucket this document defines (shared template, or per-scene instance) — it's a third shape this design doesn't build a slot for, but also doesn't preclude adding one later (most likely a new top-level `cultivars\{name}\memory\` or similar, if and when this gets designed for real, ahead of continuous-animation work). Zone `resonance_history` (already built, described in §5.3) is a narrow working precedent for the same idea, scoped to zones instead of agents.
- **`cindy_hanim.x3d` relative path resolution.** The X3D scene file's own `<Inline>` reference (`../avatars/cindy_hanim.x3d`) is correctly relative and should resolve to `static\avatars\`, but the browser was observed requesting `/static/cindy_hanim.x3d` — the relative portion dropped entirely. Evidence-backed, not yet chased; possibly related to the Day 66/67 canvas clone-and-replace mechanism interfering with relative URL resolution on the replacement element. Not blocking this document; worth a session of its own.

## 7.5 Folder creation is a backend responsibility, not an authoring step

The author should never manually create a scene or take folder before saving. The Composer only ever sends data to a backend save endpoint — the backend is responsible for creating the target folder (scene folder on first save of a new scene name; take subfolder on first arc export for that take) if it doesn't already exist, then writing into it. This is standard, low-complexity behavior for a save endpoint (create-if-missing before write), not something requiring new machinery — but it needs to actually be true of every save path this redesign introduces (scene wrapper save, arc export, future zone-template save), not just assumed. Added to §8 as a verification item rather than treated as already guaranteed, since the current backend save endpoints haven't been reviewed.

## 8. Before implementation — confirmed findings from `mccf_api.py`

These were open questions in the previous draft; checked against the actual backend code and now confirmed rather than assumed:

- **None of the three relevant save endpoints create per-scene subfolders today.** `POST /scene/save/zones`, `POST /scene/save/scene`, and `POST /arc/export` each write into a single fixed flat directory (`zones/`, `scenes/`, `exports/` respectively) regardless of which scene the content belongs to. This confirms the author's instinct — nothing needs deprecating here, this genuinely doesn't exist yet.
- **`/arc/export` already receives `scene_name` in its request body and doesn't use it for the file path** — only to stamp a `scene="..."` attribute inside the XML content. The information needed to nest the file correctly is already being sent; the endpoint just isn't acting on it.
- **`/scene/save/zones` and `/scene/save/scene` both sanitize the incoming filename with `os.path.basename()`** — a deliberate path-traversal guard. This means the fix cannot be "have the frontend send a filename containing a `/`" — that would be silently collapsed to just the last path segment and written flat, with no error. The backend needs a real change: accept `scene_name` (and later `take_name`) as an explicit field, build the nested path server-side with proper per-segment sanitization, and call `os.makedirs(path, exist_ok=True)` before writing. `/arc/export` has no equivalent guard at all today, so it needs that safety added at the same time it gains nesting, not as an afterthought.
- Still to confirm: whether the backend's X3D-generation step reads the standalone zones file server-side (§5.1 caveat) — not yet located in `mccf_api.py`, may live elsewhere in the codebase.
- Still to confirm: the exporter's behavior for arc take-folder creation — automatic per export run, or requiring an explicit "new take" action — now that it's clear this has to be built rather than adjusted.
- Old test scenes: cleanup is the author's task, already in progress, independent of this document.
