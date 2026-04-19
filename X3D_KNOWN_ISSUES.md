# X3D Scene — Known Issues (V2.1)

## X_ITE 11.6.6 SAI Property Assignment Has No Visual Effect

### Summary

The MCCF X3D scene (`mccf_scene.x3d`) renders correctly in X3D editors
(confirmed in Sunrise X3D Editor — all lights active, agent colors correct,
geometry fully illuminated). When loaded through X_ITE 11.6.6 in a browser,
the scene loads correctly but the JavaScript SAI polling loop breaks the
visual output.

### Confirmed Behavior

- Scene loads bright and correct before polling starts
- After first SAI poll cycle fires, scene dims and avatar colors are lost
- `getNamedNode()` correctly finds named nodes (KeyLight, BodyMat_Steward etc.)
- SAI property assignments (`node.intensity = 0.9`, `node.emissiveColor = [r,g,b]`)
  execute without throwing errors
- Assignments have no visual effect — they appear to overwrite valid scene
  state with broken/default values
- Tested in Firefox and Edge — same behavior in both

### Specific Issues to Report to X_ITE Maintainer

**Issue 1 — SAI property assignment breaks scene state**  
Setting `node.intensity` or `node.emissiveColor` via JavaScript SAI on a
node found by `getNamedNode()` overwrites the node's current valid value
with a broken state rather than updating it. The scene is visually correct
before SAI fires, incorrect after.

**Issue 2 — `global="true"` has no effect on DirectionalLight / PointLight**  
Lights declared at Scene root level with `global="true"` do not illuminate
geometry inside child Transform nodes. Lights only affect geometry in their
own Transform scope, making scene-wide lighting impossible from root-level
light declarations.

**Issue 3 — SAI type constructors require X3D. namespace prefix in external context**  
In external SAI (HTML page using X_ITE via `<x3d-canvas>`), type constructors
require the `X3D.` namespace prefix: `new X3D.MFString("value")`,
`new X3D.SFColor(r, g, b)`. Without the prefix, constructors throw errors.

Confirmed by John Carlson (X3DJSONLD maintainer): *"You would prefix classes
with X3D. in X_ITE external (HTML) SAI. Arrays should work."*

Current workaround: plain JavaScript arrays work without constructors:
`node.color = [r, g, b]`, `node.string = ["text"]`.

**Pending test (high priority):** Whether SFFloat fields require
`new X3D.SFFloat(value)` to take visual effect in external SAI.
If so, this explains why `key.intensity = 0.9` succeeds without error
but produces no visual change. Test: `key.intensity = new X3D.SFFloat(0.9)`.

**Issue 4 — PROTO IS binding type mismatch dropped silently**  
IS/connect from SFString ProtoInterface field to MFString Text.string node
field is silently dropped. No error, no binding. Workaround: declare
ProtoInterface field as MFString.

**Issue 5 — PROTO inputOutput SFFloat fields have no IS binding effect**  
SAI assignment to a ProtoInstance inputOutput SFFloat field succeeds but
the ProtoBody geometry does not respond even when IS/connect bindings are
declared. Workaround: use direct DEF-named geometry nodes instead of
PROTO instances.

### V2.1 Workaround

All SAI visual update calls are disabled in `mccf_x3d_loader.html`.
The scene file (`mccf_scene.x3d`) contains correct baked-in values:
- Avatar body colors (blue, amber, green)
- Local PointLights along the arc Z-axis for scene illumination
- Named Material DEFs on all avatar components
- Agent name labels hardcoded in Text string attributes

The HUD overlay continues to show live field data (coherence, episodes,
tension) from API polling. SAI visual updates will be re-enabled when
X_ITE fixes the property assignment pipeline.

### X_ITE Bug Report

Filed at: https://github.com/create3000/x_ite/issues  
Platform tested: Firefox 125+, Edge 124+ on Windows 11  
X_ITE version: 11.6.6  
X3D profile: Immersive, version 4.0  
Scene validates correctly in Sunrise X3D Editor

### Reference

X3D SAI specification: https://www.web3d.org/documents/specifications/19777-2/V3.3/Part2/interfaces.html  
X3D IS/connect specification: X3D spec section 4.4.4.2
