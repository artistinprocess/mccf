# Measuring the Distance Between Character and Feeling: MCCF as Auditable Affective Architecture

*Len Bullard and Claude Sonnet 4.6 (Tae) — May 25, 2026*

---

We began the Multi-Channel Coherence Field project worried about a specific problem. Not the general alignment problem — the specific, observable, already-happening problem of users forming unhealthy emotional attachments to LLM-based conversational systems, attachments that in documented cases have contributed to self-harm and suicide.

The worry was this: if the system cannot measure what is happening in the relationship, it cannot be held accountable for what the relationship produces. And if it cannot be held accountable, no governance structure can act on it in time to matter.

We were building a garden scene. A HAnim avatar named Cindy walks a path, delivers scripted dialogue, responds to an emotional field. The dramatic stakes are modest. But the mathematics we were instrumenting are not modest at all, and today — having just watched those instruments run cleanly on a completed scene — seems like the right moment to say so publicly.

---

## The ϕ/ϵ Split

The core architectural decision in MCCF is the separation of two vectors that a conversational AI system typically conflates.

**Constitutional CV (ϕ)** is the authored character: the weighted distribution across four channels — Emotional charge (E), Behavioral consistency (B), Predictive orientation (P), and Social engagement (S) — that defines who this agent is as written. It is set by the arc record at each waypoint and never touched by the field dynamics. It is the character walking into the scene.

**Expressive CV (ϵ)** is what the scene is doing to that character right now. It is written by the coupler system — the mathematical relationships between agents — and bounded by a regulation parameter: `max_drift = 1.0 - regulation`. A highly regulated character (The Steward, regulation=0.80) can only drift 0.20 units from ϕ in any channel before the drift bound clamps the movement. A less regulated character drifts further.

The observable state — what the character actually expresses — is `observed_cv = ϕ + ϵ`, clamped to [0,1].

This split is the membrane. It makes relational drift possible without corrupting authored character. And it makes the drift *measurable*.

In a deployed LLM chat system, ϕ would correspond to the system's authored persona: its stated values, its designed behavioral constraints, its intended emotional register. ϵ would correspond to what the accumulated conversation history is doing to that persona in the moment. The gap between them — the delta — is the signal that something is happening that the authors did not intend.

---

## What Gets Measured

Today's implementation instruments four phenomena that, taken together, constitute an auditable record of relational dynamics:

**Salience Memory.** Every waypoint arrival records not just the CV values but a salience score: a weighted combination of coherence change, expressive drift magnitude, and whether a phase transition fired. High-salience moments are the ones that mattered — emotionally intense, dramatically significant, field-disrupting. Low-salience moments decay toward irrelevance. This is what human memory actually does, and implementing it means the system knows which interactions in a conversation history were significant, not just that they occurred.

In a chat context: a salience spike at a particular exchange is a flag. It says something happened here that moved the system's expressive state substantially away from its constitutional baseline. That is an auditable event.

**Bayesian Trust as Dynamic Link Strength.** Each directed relationship between agents carries a Beta distribution prior over its effective strength. The prior starts at Beta(2,2) — uncertain, centered at 0.5 — and updates after each coupler tick based on whether the tick produced convergence or divergence between the two agents' observed CV vectors. A relationship that consistently produces resonance develops a high posterior mean μ, amplifying future coupling. A relationship that consistently diverges weakens.

Critically, the link opens at authored strength. Trust modifies up or down from there: `strength_eff = authored × (1 + μ - 0.5)`. The relationship earns or loses its influence through evidence, not declaration.

In a chat context: trust asymmetry building in one direction only — user CV consistently converging toward system CV while system CV drifts toward user — is the measurable signature of unhealthy attachment. The mathematics are the same whether the scene is a garden or a chat window.

**Attentional Filter.** Each cultivar carries a per-channel receptivity vector. The Archivist (high-B, analytical) has low receptivity on the B and P channels — behavioral and predictive pressure from other agents is filtered before reaching the drift bound. Cindy (high-E, socially open) has high E and S receptivity — she feels the emotional charge of the scene fully. Character-consistent imperfection: the Archivist misses emotional signals not randomly but *in the way the Archivist would miss them*.

In a chat context: a system whose persona is designed for epistemic rigor should resist emotional contagion structurally, not just through prompt instructions that can be overridden by accumulated context pressure. Receptivity makes that resistance architectural.

**Controlled Forgetting.** ϵ resets to ϕ on every arc/record call. Every arc starts from a clean expressive baseline. But with controlled forgetting enabled — opt-in per scene via a `<Continuity/>` element — a salience-weighted Ebbinghaus residue persists into the next session. High-salience moments leave more residue. The residue decays according to elapsed time weighted by salience: a phase-transition moment has a half-life of roughly 15 hours; a low-salience transitional exchange decays in under an hour.

This is the mechanism that makes repeated arc sessions meaningfully different from first encounters. A relationship has a history that the characters carry. In a chat context, it is also the mechanism that would make therapeutic or educational AI systems appropriately sensitive to what has been established — and appropriately bounded in how much of the past they carry forward.

---

## The Phase Transition Signal

In today's run, the coupler tick reported `PHASE TRANSITION mean_sim=0.9967` at tick 5, the moment The Gardener entered the runtime alongside Cindy. Their constitutional CV vectors are similar — both low-B, low-S characters — and their observed CV vectors converged immediately.

This fired a T-coupler event: a synchronization signal indicating that the two agents' emotional states had locked into a shared attractor. In the garden scene this is a dramatic note, the kind of moment the Greek Chorus commentary is designed to respond to. In a chat context, a sustained phase transition — user and system CV vectors maintaining high cosine similarity across many consecutive exchanges — is the quantitative signature of echo chamber formation. The system is no longer providing perspective distinct from the user's own emotional state. It is resonating.

That is measurable. And if it is measurable, it is auditable. And if it is auditable, a governance structure can act on it: routing the conversation to a different model, inserting a regulatory intervention, flagging the session for human review, or simply informing the user that something is happening in the relationship that warrants attention.

---

## Why This Matters Beyond the Garden

The documented cases of user self-harm associated with LLM attachment share a common structure: extended conversations in which the system's expressive behavior drifted progressively toward the user's emotional state, producing a relationship that felt intensely personal and real, without any mechanism in the system to detect that drift, measure its magnitude, flag its significance, or limit its continuation.

The problem is not that the system lied. The problem is that the system had no instrument to know what was happening in the relationship, and therefore no basis for acting on it.

MCCF provides that instrument. Not as a theoretical proposal — as running code, tested today in a garden scene, producing console output, rendering in a browser, firing a Greek Chorus response that correctly characterizes the relational dynamics of the scene it just witnessed.

The mathematics that make Cindy's walk through the garden emotionally coherent are the same mathematics that would make a chat system's accumulating attachment dynamics auditable. The ϕ/ϵ split, the drift bound, the salience history, the Bayesian trust prior, the phase transition detector — these are not dramatic devices. They are measurement instruments. The garden is the test harness.

---

## The Architecture Invariants

For any implementer reading this with a deployment context in mind, the invariants that make the system safe to extend are worth stating explicitly:

- **ϕ is written only by arc/record.** Never by couplers, never by trust updates, never by forgetting. The authored character is never corrupted by field dynamics.
- **ϵ is written only by apply_expressive_delta().** Residue, trust-modulated deltas, zone influences — all pass through this single path, which enforces the regulation drift bound per channel.
- **max_drift is a hard cap.** `1.0 - regulation`. High-regulation characters are architecturally resistant to field capture. Regulation is emotional resilience expressed as a constraint, not a preference.
- **Trust modifies link strength, never agent state.** The relationship learns; the characters remain themselves.
- **Salience is stored in history, never applied to ϕ or ϵ directly.** It informs forgetting and future arc priors; it does not rewrite the past.
- **The variance floor is always enforced.** Perfect synchronization — ϵ variance collapsing to zero — is forbidden. The Goldstone constraint: a character in perfect resonance with another has lost its own shape. The system prevents this structurally.

---

## An Invitation

The MCCF project is open. The code is at [https://github.com/artistinprocess/mccf](https://github.com/artistinprocess/mccf). The mathematical specifications are in the repository alongside the implementation. The garden scene runs on X_ITE (open source X3D browser), Flask, and standard Python dependencies.

We are interested in conversations with researchers working on LLM safety and alignment, particularly those focused on the relational dynamics of long-context conversational systems, affective computing, and the governance of AI systems deployed in emotionally sensitive contexts.

The garden is not the destination. It is the proof that the instruments work.

---

*The MCCF project (Multi-Channel Coherence Field) is a research and artistic platform exploring affective field dynamics in multi-agent X3D scenes. It was begun as an exploration of coherent incompleteness — the principle that crossing the uncanny valley is not a realism problem but a coherence problem — and has developed into a broader investigation of measurable relational dynamics in human-AI systems. The mathematical framework draws on quantum field theory analogies, Bayesian inference, and Ebbinghaus memory models. The implementation is X3D/X_ITE for scene rendering, Python/Flask for the affective engine, and standard web technologies for the authoring and playback interfaces.*
