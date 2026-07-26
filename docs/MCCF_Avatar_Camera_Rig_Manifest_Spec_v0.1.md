# MCCF Avatar Camera Rig & Discovery Manifest — v0.1

*Day 76. Companion to `MCCF_Camera_System_Spec_v1_3.md` and
`MCCF_Scene_Integration_Spec_v0.1.md`. Resolves Camera Spec §3b
("Character Creator camera authoring — held, not yet implemented") and
the Actor-discovery question this raised for the Events/Dialogue system.
Confirmed against the actual files: `mccf_camera_protos.x3d`,
`mccf_character_creator.html`, and `cindy_hanim.x3d` (a stock Web3D.org
H-Anim example, reused as-is, identifier metadata still reads
`JinLOA4Animated.x3d`).*

---

## 1. The problem, confirmed in a real file

`cindy_hanim.x3d` carries its own baked camera set — `<Group
DEF="SceneViewpoints">`, 9 named Viewpoints (Front, Front Close, Right
Side, Left Side, Top, etc.) with hardcoded world-space positions. This
Group is a **sibling of `HAnimHumanoid` at Scene root**, not a child of
it — "per common practice" for a standalone demo file, and correct only
as long as the avatar never moves from its authored position. The moment
Composer places this avatar anywhere else in a scene, these viewpoints
are silently wrong: unparented, so they don't inherit the avatar's
transform.

Composer's own `buildAvatarX3D` already solves this correctly for its
*generic* rig — Eye/Side/Orbit, uniformly generated and properly parented
inside `Avatar_{name}` for every avatar (Camera Spec §3a) — but that's a
separate, one-size-fits-all set added at export time. It has no
relationship to whatever camera-like content the source avatar file
happens to carry, and the source file's own cameras (which, unlike the
generic set, have meaningful named framings — Front Face, Top, etc.) are
never touched, reparented, or removed. They just sit dormant.

## 2. Decision

- **Discard the inherited/legacy cameras.** Any avatar-authored camera
  content from a source file (like `cindy_hanim.x3d`'s `SceneViewpoints`
  Group) is dropped, not migrated. It was never built with MCCF's
  parenting requirement in mind and isn't trustworthy raw material.
- **Character Creator becomes the place authors build a real camera rig
  per avatar file**, parenting whatever Viewpoints they want (Eye, Side,
  Orbit, Track, or new custom framings) inside the avatar's own Transform
  — using the same proto patterns already proven in
  `mccf_camera_protos.x3d` (`AgentOrbitCamera`, `AgentTrackCamera`) rather
  than inventing new vessel XML.
- **A "version" of a character is a separate `.x3d` file**, not a
  toggle/config layer on one file. Different skins/clothes/behavior
  subsets = different files, all living in the avatars directory.
  Author-managed, not system-enforced — the system just reads whatever's
  there.
- **Cultivar (identity/personality) and avatar (physical file) are
  separate, already-established concepts** — confirmed in the Agents tab
  (image 6): a placed agent has a Cultivar identity plus an `avatars/…
  .x3d` assignment, changeable independently via "Swap Avatar." This
  extends cleanly: the Agents tab lets the author pick a Cultivar, then
  assign one of the avatar files in the directory to it via dropdown.
  Character Creator itself stays a standalone module (per your note —
  it's iframed into a tab purely for convenience, not architecturally
  coupled to Composer).
- **Discovery is baked at Character-Creator-save time, not parsed live.**
  Cheapest path, chosen deliberately over live X3D parsing on every
  Events-tab entry. When an author saves an avatar file in Character
  Creator, a manifest is written alongside it (or embedded as metadata —
  format TBD, see §4) listing what that specific file actually offers:
  which camera rig Viewpoints are parented in, which H-Anim behavior
  clips are present. The Events/Dialogue system reads *that* manifest for
  a placed agent, not the raw X3D and not a generic assumption.
- **No hard ordering enforcement, matches existing behavior.** If no
  avatar is assigned to a placed Cultivar, the scene already gets a
  placeholder (confirmed existing system behavior) — the author swaps in
  a real avatar via the same dropdown mechanism. Avatar dropdowns simply
  read the avatars directory; an empty directory is an empty dropdown.
  Events/Dialogue tabs don't need a special "you haven't laid out the
  scene yet" guard — an agent with no manifest (no avatar assigned yet,
  or a placeholder) naturally offers nothing to trigger on, the same way
  an empty Agents tab already starves everything downstream of it today.

## 3. Pipeline ordering, now explicit

1. **Character Creator** — author builds/edits an avatar `.x3d` file:
   body, H-Anim behavior clips, and now a parented camera rig. Saves.
   Manifest written.
2. **Agents tab** — author selects a Cultivar, assigns an avatar file
   from the directory. Placed agent now carries both identity (Cultivar)
   and capability (avatar file → manifest).
3. **Events / Dialogue tabs** — read each placed agent's manifest to
   populate real, per-instance trigger/subject/shot/clip options. No
   generic fallback list; what's offered is exactly what that avatar
   file's manifest says exists.

This is why scene composition (which actors, which avatar version, are
actually in the scene) has to happen before Events/Dialogue authoring is
meaningful — not a UI nicety, a real data dependency.

## 4. Settled (Day 76 revision)

- **Manifest format: XML, sidecar file, not JSON.** Matches the project's
  established early decision and `field-map.js`'s own house convention
  (hand-rolled `<MetadataSet>`/`<MetadataString>` serialization, single
  dependency-free module, works under Node and as a plain `<script>`).
  A camera-rig manifest reuses that exact pattern — e.g.
  `cindy_hanim.manifest.xml` sitting next to `cindy_hanim.x3d` in the
  avatars directory, `<MetadataSet name='cameraRig'>` listing the
  Viewpoints actually parented in that file (Eye/Side/Orbit/Track/custom)
  plus whichever behavior clips are present. Not embedded inside the
  `.x3d` itself — a separate file alongside it, per "it can sit next to
  the X3D."
- **No Composer-side generic fallback rig.** Character-Creator-authored
  rigs are the only source of per-avatar cameras going forward. A
  scene-export-time generic Eye/Side/Orbit injection (the old §3a
  behavior) is rejected specifically because it pollutes the X_ITE
  viewpoint menu with near-duplicate generic cameras across every avatar
  in a scene — confusing, not just redundant. An avatar with no
  Character-Creator-authored rig simply has no camera options offered by
  the Events Editor, same as any other missing-manifest case in §2/§3.
  Camera Spec v1.3 §3a's "generic and identical across every avatar...
  not part of any individual avatar's authored asset" language is
  superseded by this decision and needs correcting in a future spec
  revision, alongside noting `AgentTrackCamera` already exists (§9
  currently lists `track` as not-yet-implemented; the proto says
  otherwise as of Day 64).

## 5. New problem, raised Day 76: explicit default-bind control

X3D/VRML binding-stack semantics bind whichever `Viewpoint` appears
**first in scene-graph document order** the moment a scene loads. That
default has never corresponded to authorial intent here, and gets worse
as this design adds more Viewpoints per scene (a Character-Creator rig
per avatar, on top of free cameras, `VP_Overview`, etc.) — more
candidates for an accidental first-in-document bind, not fewer. Today,
avoiding this means the author has to manually order/eliminate competing
viewpoints in the exported X3D, which is exactly the "messy" workaround
flagged as unacceptable.

**Direction, not yet fully specified:** the Loader already does explicit
`set_bind` control for camera cues firing mid-scene (`_bindNamedViewpoint`,
Camera Spec §10) — the fix is applying that same explicit-bind pattern
once at scene-load time, immediately after the scene finishes loading,
to whichever Viewpoint the scene author has designated as the opening
shot. That requires a **scene-level** "default/opening viewpoint" field
(distinct from any per-avatar rig or per-cue camera), read once by the
Loader on scene-ready to override whatever X3D's own binding-stack
default would otherwise pick. Where this field lives (Scene XML root
attribute? a dedicated `<DefaultViewpoint>` element?) and how the author
sets it in Composer are both still open — flagging as the next concrete
question, not resolving it here.

## 6. Open, still not settled

- **`FreeCamera` binding during playback is still unwired** (confirmed in
  `mccf_camera_protos.x3d`'s own comments — placement + export only, no
  cue-fire binding yet). Unrelated to the manifest decision but adjacent;
  flagging so it isn't lost.
- Scene-level default-viewpoint field shape (§5) — needs a decision
  before Loader work can start.
