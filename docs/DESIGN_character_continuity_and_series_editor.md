# Character Continuity & the Series Editor — Design Notes

Status markers used throughout: **BUILT** (real, in the code today),
**DEFERRED** (deliberately not built yet — single-scene runs only until
the demo is solid), **FUTURE** (the series editor itself — not designed
in detail, this document is the seed of that design, not the design).

---

## 1. BUILT today — cultivar/character isolation

A cultivar is a template: stateless, re-testable, no history by
definition. A character is the opposite: nothing but accumulated
history. Until this pass, both lived in the same runtime slot
(`_agent_runtime[name]`), keyed by bare name — meaning testing a
cultivar called "Anna" against the Constitutional waypoint arc and
playing a scene with a character named "Anna" wrote into the same
state. A test run could leave residue a live scene would silently
inherit; a scene's real history could contaminate what should have
been an isolated template test.

Fixed by giving `_agent_runtime` a composite key: `scope::name`.
`scope` defaults to `'character'` everywhere — every existing caller
(scenes, dialogue, zone commands, couplers) needs no changes and keeps
its current behavior exactly. Only `mccf_constitutional.html` opts
into `scope: 'cultivar_test'` explicitly on its `/arc/record` calls.
`/couplers/tick` filters to `'character'` scope only, unconditionally
— coupler network-topology math has no business touching an isolated
test, and now can't by construction, not by convention. `/field` and
`/field/runtime` show `'character'` scope by default too, so a
cultivar-test run never bleeds into the live scene panel Composer's
Field State reads from.

This is infrastructure, not the series editor — it's the ground the
series editor needs to stand on, since "test the template separately
from playing the character" was the whole premise of the conversation
that led here.

## 2. BUILT today, already relevant — `/arc/residue`

Worth knowing this already exists, because it's real prior art for
what the series editor needs to formalize: `/arc/residue` (opt-in per
scene via `<Continuity/>` in scene XML) lets a scene start with
`ϵ = 0 + salience-weighted residue` from a previous arc session,
instead of a clean `ϵ = 0`. It's narrow — one flat residue blended in
at scene start, not a general "which prior state does this scene
follow" mechanism — but it's the same underlying idea as the
checkpoint graph below, already partially working, already
`'character'`-scoped.

## 3. Also fixed this pass — the ϵ initialization bug

Unrelated to scope, but touches the same code: `AgentRuntimeState.
set_constitutional()` was initializing `expressive_cv` (ϵ) equal to
`constitutional_cv` (ϕ) instead of to zero. Since `observed_cv = ϕ + ϵ`,
this made every character's observed state start at roughly double its
constitutional baseline (clamped to 1.0) immediately after every
`/arc/record` call — for every regulation level, including a fully
regulated character (regulation=1.0), whose entire defined guarantee
is "ϵ locked to zero, pure constitutional state." Confirmed against
the original Day 12 spec (`expressive_cv` should start at zeros) and
against `mccf_couplers.py`'s own Damping coupler docstring ("pull
expressive component toward zero, toward constitutional baseline" —
which only makes sense if ϵ's rest state is zero). Fixed to match spec.

Worth flagging precisely what this doesn't affect: the original
Constitutional-tool validation ("Llama returns to baseline") never
read `observed_cv` at all — it reads `/arc/record`'s own returned `cv`
directly. That historical result stands independent of this bug.

---

## 4. FUTURE — the series editor's real problem, and the shape that solves it

**Run order and story order are two different orderings.** Everything
built so far (including `/arc/residue`) implicitly assumes "the state
a scene starts from = whatever was persisted most recently" — a
run-order assumption. That breaks under flashbacks, because a
flashback's correct starting state isn't "whatever ran last," it's
"whatever this character's state was at *this point in the story*" —
a different question entirely once run order and story order diverge.

**Proposed primitive: a checkpoint graph, not a linear persist/load.**
Each scene's ending state, per character, is a named checkpoint node.
Each scene's *starting* state is an explicit edge the author draws in
the Series Editor, pointing at whichever checkpoint it causally
follows — not inferred from execution order.

- **Ordered** scenes: edges chained scene-to-scene in story sequence.
  The common case.
- **Flashback**: an edge pointing *backward* to an earlier checkpoint
  (or to the cultivar template itself, if this is the character's
  earliest story appearance) — regardless of when it was actually
  rendered. The flashback scene never touches "present-day" state.
- **Unordered**: no defined causal relationship between two scenes.
  Proposal: these should not auto-chain to each other — both branch
  from the same last-definite-ordered checkpoint, rather than one
  silently feeding the other.

Branching sub-timelines fall out of this for free: a divergent
timeline is just a second edge off the same checkpoint node.

**Explicitly the author's responsibility, per this session's
discussion**: persistence conditions are authored in the Series
Editor, not inferred. If a scene carries the wrong history, that's an
authoring mistake in the composer, not a system failure to guard
against automatically.

**Not designed yet, deliberately**: the actual Series Editor UI, the
checkpoint storage format, how `/arc/residue`'s existing mechanism
generalizes from "one flat residue blend" to "read from an arbitrary
graph node." This section is the seed of that design, not the design.
