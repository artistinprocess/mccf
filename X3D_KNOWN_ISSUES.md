# X3D Scene — Known Issues (V2.1 → V2.1.9)

## ✓ RESOLVED V2.1.9 — Root Cause Identified and Fixed (April 2026)

**All SAI visual failures traced to a single root cause:**

> X\_ITE 11.6.6 external SAI requires typed `X3D.` namespace constructors
> for all non-string field assignments. Plain JavaScript values (numbers,
> arrays) are silently accepted but do not trigger visual updates.

**Confirmed working patterns:**

```javascript
// Scalar fields
node.intensity    = new X3D.SFFloat(0.9);    // ✓
node.transparency = new X3D.SFFloat(0.3);    // ✓

// Vector fields
node.translation  = new X3D.SFVec3f(x,y,z); // ✓

// Color fields
node.emissiveColor = new X3D.SFColor(r,g,b); // ✓

// String fields — plain array works without constructor
node.string = \["text"];                       // ✓

// Arrays for MFColor/MFVec3f — plain array works
node.color = \[r, g, b];                       // ✓ (MFColor)
```

**Confirmed by John Carlson (X3DJSONLD):** "You would prefix classes with
X3D. in X\_ITE external (HTML) SAI."

**Status as of V2.1.9:**

* Avatar emissiveColor → `X3D.SFColor` ✓ colors live
* Avatar transparency → `X3D.SFFloat` ✓
* Avatar Transform translation → `X3D.SFVec3f` ✓ movement confirmed
* HotHouse polling → 3/3 agents, 12 nodes updated per cycle ✓
* Scene loads at correct brightness ✓
* Load time normal after pollLighting sync fix ✓

\---

## Issue 1 — Light Node SAI (Partially Resolved)

**Status:** Light color arrays work. Light intensity SAI degrades scene.

Any `node.intensity = value` write to DirectionalLight or PointLight nodes
darkens the scene even with `X3D.SFFloat`. Light color array writes `\[r,g,b]`
are accepted without degradation.

**Current approach:** All light intensity SAI disabled. Scene uses baked-in
intensity values. Color temperature is tracked in HUD (informational only).

**V2.2 fix:** Light Master Script Node inside `mccf\_scene.x3d` receives
field state as a string via SAI, distributes to local lights using internal
X3D scripting. Bypasses external SAI for lights entirely.

\---

## Issue 2 — global="true" Has No Effect on Root-Level Lights

**Status:** Open. Lights declared at Scene root with `global="true"` do not
illuminate geometry in child Transform nodes. Workaround: local PointLights
inside Transform wrappers (partially implemented via baked-in scene values).

\---

## Issue 3 — SAI Type Constructors Require X3D. Prefix (RESOLVED)

**Status:** RESOLVED V2.1.9.

Confirmed by testing and John Carlson: all type constructors require `X3D.`
prefix in external SAI context. `new X3D.SFFloat()`, `new X3D.SFColor()`,
`new X3D.SFVec3f()` all work. Plain values silently ignored for typed fields.

\---

## Issue 4 — PROTO IS Binding Type Mismatch Dropped Silently

**Status:** Open. IS/connect bindings from ProtoInterface SFString fields
to ProtoBody MFString fields are silently dropped at runtime. Confirmed
workaround: use MFString type for all Text node connections in PROTO fields.
All current PROTO IS bindings in `mccf\_scene.x3d` use correct types.

\---

## Issue 5 — SFString to MFString IS Connect Silently Dropped (RESOLVED)

**Status:** RESOLVED V2.1. All Text node `string=` attributes confirmed
correct MFString XML encoding. PROTO IS connect uses MFString type throughout.
No changes needed.

\---

## Issue 6 — Light Intensity SAI Degrades Visual State

**Status:** Open. See Issue 1. `X3D.SFFloat` constructor does not resolve
intensity writes on light nodes — scene still darkens. Color writes work.
Root cause unknown — may be X\_ITE internal lighting pipeline behavior.

\---

## Issue 7 — diffuseColor SAI Breaks Material Visual State (RESOLVED)

**Status:** RESOLVED V2.1.9 by root cause identification.

`bodyMat.diffuseColor = \[r,g,b]` (plain array) was silently ignored.
`bodyMat.emissiveColor = new X3D.SFColor(r,g,b)` works correctly and
is now used for all avatar field-state color updates. Identity colors
preserved in baked-in diffuseColor (untouched by SAI).

\---

## Issue 8 — pollLighting Hammering /ambient/sync

**Status:** RESOLVED V2.1.9.

`pollLighting()` was calling `/ambient/sync` POST on every 2-second cycle,
causing server load and slow browser response. Fixed: pollLighting now reads
cached `/lighting/scalars` only. Single sync POST fires once at startup.

\---

## Summary — What Works in V2.1.9

|Feature|Status|Method|
|-|-|-|
|Avatar emissiveColor|✓ Working|`X3D.SFColor`|
|Avatar transparency|✓ Working|`X3D.SFFloat`|
|Avatar translation|✓ Working|`X3D.SFVec3f`|
|Text node string|✓ Working|plain array|
|Light color|✓ Working|plain array|
|Light intensity|✗ Breaks scene|pending Script Node|
|diffuseColor|✗ Use emissive instead|plain array ignored|
|ProximitySensor|Untested|in scene, fires on position|

## What Is Next

**V2.2 Light Master Script Node** — internal X3D Script node receives
JSON string from JavaScript, distributes color+intensity to local lights.
Bypasses all external SAI for lighting.

**V2.2 Avatar motion** — `X3D.SFVec3f` translation confirmed working.
HotHouse ψ vectors can drive avatar position. Proximity sensors will fire
on position changes. Real-time simulation layer is viable.

**Reported to:** Holger Selig (X\_ITE maintainer), John Carlson (X3DJSONLD),
W3D Consortium public list, AI Working Group.

\---

*Last updated: April 2026 — V2.1.9
Len Bullard / Claude Sonnet 4.6*

