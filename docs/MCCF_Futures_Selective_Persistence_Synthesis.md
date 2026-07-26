# MCCF Futures & Selective Persistence — Design Synthesis

*Status: capture only. No scheduling commitment beyond "before continuous animation work." Nothing in this document is approved for implementation.*

## 1. Why this document exists

Two design proposals were reviewed together — *Selective Persistence: A Coherence-Based Architecture for Episodic Memory* and *MCCF Futures: Integrating PAN World Models into the Multi-Channel Coherence Framework*. Read separately, each is a distinct proposal. Read together, they resolve each other's most important open question. This document exists to record that resolution now, while it's fresh, without committing to build any of it yet.

Continuity note: the Futures/PAN piece was already reviewed once before, during Day 66, under a similar or earlier draft. That review's verdict stands and is restated here rather than superseded: most of the piece's heavier claims (multi-hypothesis future simulation, a "semantic energy landscape" with no actual energy function defined, the full World Model Components wishlist) are aspirational — named, not specified. No data model, no cost model, no falsifiable claim as written. The one component flagged then as worth real attention was the feedback loop — *coherence should shape what gets imagined next, not just score it afterward*. What's new since that review is that Selective Persistence gives that feedback loop an actual mechanism, which is most of what this document is about.

## 2. The two sources, briefly

**Selective Persistence** proposes that MCCF memory should work by compression, not accumulation — retaining trust deltas, unresolved goals, and symbolic residue rather than growing transcripts. Each Constitutional Cultivar gets its own persistence profile (a Witness retains causal anomalies and lets emotional intensity decay fast; a Steward retains obligations and discards sensory detail), governed by a scalar persistence intensity. It proposes three memory layers per agent — a working state always supplied to the next prompt, sparse episodic traces retained only when significant, and slow-changing constitutional memory (identity, values, tendencies). The appendix sketches this mathematically as an attention-like operator: persistence = attention weight × a cultivar-specific governance function, with multi-channel relevance derived from EBPS coherence rather than assigned by hand.

**MCCF Futures / PAN** proposes giving each agent an explicit internal World Model — belief graph, causal model, counterfactual simulator, emotional forecaster, social model, narrative state, uncertainty field — as inspectable objects rather than hidden model activations. Agents would imagine multiple candidate futures simultaneously and select among them by coherence, identity preservation, and trust rather than by reward. Its most important idea, and the one the Day 66 review already isolated as worth keeping: coherence shouldn't just score imagined futures after they're generated, it should shape which futures get imagined in the first place — a loop running Constitution → World Model → Imagined Futures → Coherence Field → back into an updated World Model.

## 3. The synthesis

The Futures piece leaves "what narrows the imagination space" abstract — coherence, generically, feeds back into imagination. It doesn't say *how*. Selective Persistence, read as the missing half, answers that directly: **what a cultivar chose to retain is the scoping mechanism.** An agent doesn't imagine every possible future and then filter by coherence after the fact — it can't imagine ex nihilo. It imagines *from* what persisted: the trust deltas, the unresolved goals, the symbolic residue its own persistence profile kept. Selective Persistence isn't just a memory-compression scheme sitting next to the World Model — it's the thing that makes the World Model's imagination *tractable* and *coherent by construction*, rather than needing a separate evaluation pass to reject incoherent futures after generating them.

Restated as the working thesis for future design sessions: **futures are scoped by desire, and desire is what selective persistence made durable.** A cultivar with a high-fidelity trust memory imagines futures where that trust matters; a cultivar that let a slight fade doesn't reimagine it into relevance. Emotional continuity is not a filter applied to imagination — it's the substrate imagination draws from.

This is a genuine synthesis, not something either source states outright — worth remembering as such when this gets written up formally later, since neither post makes this specific connection on its own.

## 4. Where this already touches existing, working code

Two points of contact were found during the Day 67 zone-system audit, worth carrying forward as precedent rather than starting from a blank page:

- **`SemanticZone.resonance_history`** (in `mccf_zones.py`) already implements a narrow, working instance of the same underlying idea — episodes occurring in a zone accumulate and decay over time, amplifying or dampening the zone's future pressure. This is Selective Persistence's core mechanism (weighted, decaying retention shaping future behavior) already built and shipped, just scoped to zones rather than agents, and without a cultivar-specific persistence profile governing what's kept.
- **`ZoneAttractor.psi_zone`** (in `mccf_zone_attractor.py`) is a *fixed* identity, set once at creation from a descriptor decomposition, not itself an evolving memory — a useful negative example. It confirms the codebase already distinguishes "an entity's persistent identity" from "an entity's accumulating history," which is exactly the working-state / episodic-trace split Selective Persistence proposes for agents. The pattern exists; it just hasn't been generalized past zones.

## 5. What this doesn't yet have a home for

Flagged already in the directory redesign document (§7) and repeated here because it's the direct architectural consequence of this synthesis: agent-persistent memory that evolves *and* persists across scene and take boundaries doesn't fit either bucket that document defines — not a shared static template (like a cultivar definition), not a per-scene instance (like a placed zone or a recorded arc). It's a third shape: per-agent-*instance*-over-time, evolving, scene-transcending. Likely eventual home is something like a `cultivars\{name}\memory\` layer, distinct from the cultivar's own static definition — but that's a guess to be tested at actual design time, not a decision made here.

## 6. Explicitly not decided by this document

- **No mathematical formalization is adopted.** The appendix's attention-operator model (persistence = attention weight × governance function) is presented in its own source as a research hypothesis, not a finalized algorithm, and this document treats it the same way — a plausible starting shape, not a spec.
- **No commitment to the full World Model Components list.** Per the Day 66 review, most of that list (Counterfactual Simulator, Uncertainty Field, full multi-hypothesis simulation) remains aspirational and unspecified. Only the feedback-loop idea, now sharpened by §3's synthesis, is being carried forward as worth real design attention.
- **No timeline.** The only scheduling commitment made is relative: this work comes before continuous animation implementation, not before anything else, and not on any particular session.
- **Zone mutuality** (a zone's own state shifting live in response to current occupants, discussed separately) is related but distinct from everything in this document — that's about a zone reacting to the present, this is about an agent's imagination being scoped by its past. Worth keeping the two ideas from being conflated when design work actually starts.
