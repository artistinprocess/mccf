# Seed Note — TimeSensor `cycleComplete` (X_ITE 16.3+)

## Status: Deferred — future system upgrade, not this cycle

Not urgent, not free, but real: a genuine fix for a fragility already
living in the codebase, worth folding into a deliberate version-upgrade
pass rather than adopting piecemeal mid-scene-build.

## What it is

x3d-public mailing list, today (Don Brutzman → Holger Seelig thread):
Don proposed adding `cycleComplete` (SFTime, outputOnly) to `TimeSensor`
— a native event fired once at the end of every cycle, before the next
`cycleTime` fires at the start of the following one. Confirmed by Holger:
**a reference implementation already exists in X_ITE 16.3.**

The proposal's own framing of the problem it solves — three known
workarounds, all named as flawed:
- (a) watch `fraction_changed` for `== 1.0` — "a potential failure mode
  and not very portable"
- (b) compare `elapsedTime` to `cycles × cycleInterval`
- (c) `isActive` → `BooleanFilter` (screen for FALSE) → `TimeTrigger`
  (SFBool → SFTime) → route to the next TimeSensor's `startTime`

## Why this project specifically should care

Confirmed directly, not by analogy: `mccf_x3d_loader.html`'s
`_wirePathTimerBehavior` already does exactly workaround (a), including
the exact caveat that motivated Don's proposal:

```
//   Timer_N fraction_changed≥0.99 → DefaultTimer on (transit ends)
```

`0.99`, not `1.0` — softened specifically because the exact value isn't
reliably hit every cycle. This is the documented failure mode from the
proposal, already live in this codebase, already worked around by fuzzing
the threshold rather than fixing the underlying gap. `cycleComplete`
would replace that fuzzy poll with an exact, native event.

## The real blocker — not a small one

This project is pinned to **X_ITE 11.6.0** (`mccf_x3d_loader.html`,
CDN import). The reference implementation is in **16.3** — a large
version gap, and this same file has extensive, hard-won, version-specific
workarounds already tuned against 11.6 specifically:

- `getActiveViewpoint().position`/`.orientation` confirmed to hold only
  the Viewpoint's *authored* value, not live navigation (the
  `MCCF_PathRecorderProx` ProximitySensor workaround exists because of
  this)
- `canvas.browser.currentTime` returns 0 in "some X_ITE builds" — multiple
  fallback strategies already coded around this
- `startTime`/`stopTime` confirmed NOT to work for behavior-timer
  switching in this X_ITE build — `enabled=true/false` used instead
- Bulk `MFVec3f`/`MFRotation` constructors confirmed absent from this
  build's SAI

A jump from 11.6 to 16.3 is not "add one field" — it's a real
compatibility pass against all of the above, any of which could behave
differently (better, worse, or just differently) on a newer build.
Adopting `cycleComplete` casually, mid-scene-build, risks reopening
several already-solved problems to fix one real but non-blocking one.

## When to actually do this

Proposed timing, per the author's own call: **after the Qatar demo**,
likely folded into a broader system-upgrade pass once the post-demo code
review has surfaced whatever else the team wants to fold in at the same
time — batch the version bump with other accumulated asks rather than
a one-off mid-project upgrade for a single (real, but non-critical)
fragility fix.

## Concrete follow-up work, once that upgrade is scheduled

1. Confirm X_ITE 16.3 (or later) actually ships wherever this project's
   CDN pin points, and pin explicitly rather than trusting `@latest`-style
   drift.
2. Re-verify each of the four documented 11.6-specific quirks above
   against the new version before relying on any of them still holding.
3. Replace `_wirePathTimerBehavior`'s `fraction_changed>=0.99` check with
   a real `cycleComplete` listener — the direct, motivating fix.
4. Audit for other `isActive`/threshold-based "did this cycle finish"
   workarounds elsewhere in the loader that `cycleComplete` could also
   simplify, now that a real event exists to replace them with.
