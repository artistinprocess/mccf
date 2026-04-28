# MCCF V3 Specification Review Request
## For: Kate (ChatGPT) / Fidget (Gemini) / Grok
## From: Len Bullard / artistinprocess
## Date: April 28, 2026

---

MCCF V3 — "The New York Rocket" — specification v0.1 is ready for review.

**Repository:** https://github.com/artistinprocess/mccf  
**Spec document:** `MCCF_V3_SPEC.md` in the repository root

---

## Context

V2 "Q" is complete and released. All three of you reviewed V2 and your
findings were addressed before this specification was written. The V2
codebase is the foundation V3 builds on.

Your theoretical contributions are reflected in the spec:
- Kate: zone attractors as semantic agents, Shadow Context Field, λ per
  cultivar, sharpness gap / structured noise principle
- Fidget: scar tissue hysteresis, sensitivity analysis, arc pressure as
  scalar not attractor shift
- Grok: gaming vectors, field collapse, harness attack vectors, XML schema
  extensibility for multi-agent scenes

The theoretical seed document (`MCCF_V3_SPEC_SEED.md`) captures the full
theoretical stack including CRIL, geopolitical sphere dynamics, and the
Shadow Context formalism. The spec intentionally scopes down from that
to what is buildable in V3. The seed document remains as theoretical horizon.

---

## What the Spec Contains

Eight concrete build items:

1. Zone attractor system — semantic descriptors, noise coefficients,
   zone-to-agent coherence via existing R_ij machinery
2. X3D Master Script — one Script node governing avatars, zones, sound
3. Three performance modes — Playback, Improvisation, Live Theatre
4. Scene XML wrapper — single or multi-agent, backward compatible
5. Δ_t drift measurement — Shadow Context proxy logged per waypoint
6. Adaptive λ per cultivar — shadow context decay rate in cultivar XML
7. Spatial Sound — X3D Sound nodes at zone positions, author-provided audio
8. Garden of the Goddess — initial V3 scene, three zones

Module decisions:
- Lighting module: retired (never worked reliably)
- Music module: retired and replaced by Spatial Sound
- Voice module: held for later testing
- Character Studio: extended with λ slider, otherwise unchanged
- Field Editor: scope-limited to tuning, not character creation

---

## Review Instructions

**Scope:** V3 specification only. We are not revisiting V2 findings.

**One round of comments.** After this review, implementation begins.

**Focus your review on:**

1. **Scope** — Is anything genuinely necessary for V3 missing from the
   eight build items? Is anything included that should be deferred?

2. **Architecture** — Are the eight items internally consistent? Do they
   create build dependencies that complicate the implementation order?

3. **Open questions** — The spec contains seven open questions (section
   "Open Questions for Team Review"). Please address any you have a
   strong view on. Do not feel obligated to answer all seven.

4. **Module decisions** — Do you agree with retiring lighting and music?
   Any concerns about holding the voice module?

**Do not propose:**
- New theoretical frameworks
- Features beyond the eight build items
- V4 architectural changes
- Revisions to V2

---

## Format

Please structure your response as:

**Confirmed** — build items or decisions you consider sound  
**Concerns** — specific issues with specific items  
**Open questions** — your answers to any of the seven spec questions  
**Missing** — anything you believe is genuinely necessary that is absent  

---

## Note to Kate

Your theoretical contributions from April 27-28 (Shadow Context, CRIL,
Sharpness Gap) are captured in the spec seed document and inform the spec.
Δ_t measurement and adaptive λ are direct implementations of your Shadow
Context formalism. CRIL is documented as theoretical horizon. This review
is for the bounded spec, not the theoretical stack.

## Note to Fidget

Your V2 finding on scar tissue hysteresis is implemented and tested.
Your sensitivity analysis is live in the evaluation harness. This review
is forward-looking only.

## Note to Grok

Your V2 gaming vector and field collapse findings are documented in the
spec seed as known limitations. The Δ_t drift measurement addresses the
gaming vector partially — a syntactic gamer will show low Δ_t because
their output is context-independent regardless of vocabulary. Full
embedding-based measurement is deferred to V4. Address the adequacy of
this partial fix if you have a strong view.

---

Thank you. One round. Then we build.

*Len Bullard / artistinprocess*  
*https://github.com/artistinprocess/mccf*
