# MCCF: A Unified Mathematical Theory

## Reconciling the Classical Constraint Framework, Zeilinger Information Ontology, and Quantum-Inspired Field Dynamics

**Version:** 2.0 — April 2026  
**Repository:** https://github.com/artistinprocess/mccf  
**Ground truth:** mccf\_core.py, mccf\_hotHouse.py, mccf\_collapse.py (v1.7 / v2.0)

> "MCCF is not a model of intelligence. It is a system for keeping intelligence from falling apart."

\---

## Preface: Why a Unified Theory Is Needed

Three prior documents describe the MCCF from complementary perspectives:

1. The **Classical Framework** defines MCCF as a bounded state-transition system $\\mathcal{M} = (A, C, S, T, B, E)$ with modular channels and constraint-enforced transitions.
2. The **Zeilinger Information Ontology** frames agents and interactions in terms of constrained information states $\\mathcal{I} = {(o\_i, p\_i)}$ where reality is constituted by relational constraints rather than observer-independent objects.
3. The **V2 Proposal** introduces quantum-inspired extensions: agents as semantic spinors, collapse dynamics, the Affective Hamiltonian, and the ArbitrationEngine as a governing field equation.

These three accounts are consistent but not yet unified. This document reconciles them by reading directly from the implemented code, answering each of Grok's nine questions with precise mathematical statements and code references.

\---

## 1\. Unified Ontology

**What is the fundamental mathematical object in the implemented MCCF?**

The MCCF is a **hybrid system**: a directed weighted graph of coherence records overlaid with a continuous-time dynamical system on agent state vectors.

### The Two Layers

**Layer 1 — Coherence Graph (discrete, episodic)**

Implemented in `mccf\_core.py`. The primary object is the coherence field:

$$\\mathcal{F} = {(A, \\mathbf{R}, \\mathcal{H})}$$

where:

* $A = {a\_1, \\ldots, a\_n}$ is the registered agent set
* $\\mathbf{R} \\in \[0,1]^{n \\times n}$ is the asymmetric coherence matrix, $R\_{ij} \\neq R\_{ji}$ in general
* $\\mathcal{H}$ is the episode log (ordered sequence of interaction records)

Each agent $a\_i$ carries a **channel weight vector** (the cultivar baseline):

$$\\boldsymbol{w}\_i = (w\_E, w\_B, w\_P, w\_S) \\in \\Delta^3, \\quad \\sum\_c w\_c = 1$$

with default weights `{"E": 0.35, "B": 0.25, "P": 0.20, "S": 0.20}` (`mccf\_core.py:DEFAULT\_WEIGHTS`).

**Layer 2 — Affective Hamiltonian (continuous, dynamical)**

Implemented in `mccf\_hotHouse.py`. Each agent also carries a **state vector** $\\boldsymbol{\\psi}*i \\in \[0,1]^4$ that evolves under the Affective Hamiltonian $H*{\\text{affect}}$ (see Section 6).

### Relationship Between $\\mathcal{I}$ and $S$

The Zeilinger ontology's information state $\\mathcal{I} = {(o\_i, p\_i)}$ (constrained outcome-weight pairs) corresponds in the code to the `CoherenceRecord`: a bounded deque of `ChannelVector` episodes, each weighted by exponential decay. The agent's channel weights $\\boldsymbol{w}\_i$ are the constraint structure. The information state is not stored as an explicit probability distribution but as a history from which coherence scores are computed.

The classical framework's state space $S = S\_A \\times S\_C \\times S\_E$ maps as:

* $S\_A$ → agent `MetaState` (uncertainty, surprise, valence, mode, coherence, learning\_progress)
* $S\_C$ → the 4-channel vector $\\boldsymbol{\\psi}\_i$ or $\\boldsymbol{w}\_i$ per agent
* $S\_E$ → the X3D projection from `HotHouseX3DAdapter.generate\_x3d\_state()`

\---

## 2\. Semantic Collapse

**How is semantic collapse implemented?**

Semantic collapse is implemented as **Boltzmann sampling over a scored candidate set**, constrained by schema validation, honor penalty, and identity alignment. The mechanism is in `mccf\_collapse.py:\_apply\_utterance()`.

### The Energy Functional

For each candidate utterance $c$ with channel vector $\\boldsymbol{v}\_c$:

$$E(c) = (1 - \\text{coh}(c)) + \\lambda\_h \\cdot h(c) - \\lambda\_m \\cdot m(c)$$

where:

* $\\text{coh}(c) = R\_{ij}$ is the coherence score of the candidate against the agent's relationship history
* $h(c) \\in \[0,1]$ is the honor penalty from `HonorConstraint.compute\_penalty()`
* $m(c) \\in \[0,1]$ is the identity alignment score from `\_apply\_invocation()`
* $\\lambda\_h = 0.8$, $\\lambda\_m = 0.2$ (hardcoded in `mccf\_collapse.py:490`)

### Boltzmann Selection

$$P(c) \\propto \\exp!\\left(-\\frac{E(c)}{T}\\right), \\quad T = T\_{\\text{base}} + \\delta T\_{\\text{schema}}$$

where $T\_{\\text{base}}$ is the interaction temperature and $\\delta T\_{\\text{schema}}$ is the zone-specific modifier (e.g., $-0.15$ at W7 Integration, $+0.10$ at W5 Rupture).

Selection is by inverse transform sampling over the normalized distribution.

### Correspondence to the Ontology

This is the concrete implementation of $\\mathcal{M}(\\mathcal{A}, \\mathcal{I}) \\to \\mathcal{I}'$ from the Zeilinger ontology. The agent $\\mathcal{A}$ is the cascade pipeline (schema + honor + identity operators). The information state $\\mathcal{I}$ is the candidate set with constraint weights. The output $\\mathcal{I}'$ is the selected candidate and the resulting state deformation in the coherence field.

### Is There a Wavefunction-Like Object?

The implemented analog is the scored candidate distribution before selection:

$$\\Psi\_{\\text{pre}} = \\left{(c\_k, P(c\_k))\\right}\_{k=1}^{K}$$

This is a discrete probability distribution over semantic states — structurally analogous to a wavefunction superposition. It is not a continuous wavefunction; it is a finite mixture that collapses to a point via sampling. The quantum analogy is heuristic, not formal.

\---

## 3\. Agents as Spinors

**How are agents represented as spinors in the code?**

The term "spinor" in the V2 proposal is a design metaphor for a **persistent multi-component state vector whose components do not vanish under constraint operators**. The implementation is the `Identity` class in `mccf\_core.py` combined with the `FieldAgent.psi` vector in `mccf\_hotHouse.py`.

### The Four-Component State

The channel weight vector $\\boldsymbol{w}\_i = (w\_E, w\_B, w\_P, w\_S)$ is the static cultivar baseline. The dynamic state is the HotHouse $\\boldsymbol{\\psi}\_i$:

$$\\boldsymbol{\\psi}\_i(t) = (\\psi\_E(t),, \\psi\_B(t),, \\psi\_P(t),, \\psi\_S(t)) \\in \[0,1]^4$$

initialized near ideology with Gaussian noise:

$$\\psi\_c(0) = w\_c^{\\text{ideology}} + \\epsilon\_c, \\quad \\epsilon\_c \\sim \\mathcal{N}(0, 0.05)$$

The Identity class additionally tracks a slow-drift overlay:

$$\\boldsymbol{\\tau}*i(t) = (\\tau*{\\text{curiosity}},, \\tau\_{\\text{risk}},, \\tau\_{\\text{social}},, \\tau\_{\\text{persist}}) \\in \[0,1]^4$$

with drift capped at $\\pm 0.10$ from the cultivar baseline (constant `IDENTITY\_DRIFT\_CAP`).

### Why "Spinor"?

The spinor framing is justified by two properties:

1. **All components persist**: no component can be set to zero by any single operator. The drift cap ensures $|\\psi\_c - w\_c^0| \\leq 0.10$ at all times.
2. **Components rotate rather than select**: the Hamiltonian update mixes components continuously rather than selecting between discrete states.

### Representation Class

This is **not** a standard Weyl, Dirac, or Clifford algebra spinor. It is a bounded real 4-vector with attractor dynamics — a custom representation. Using the term "spinor" in publications requires this qualification.

\---

## 4\. Affective / Emotional Parameters

**How are emotions encoded?**

Emotions are encoded at two levels.

### Level 1 — Channel E (Coherence Layer)

The E channel (Emotional) in `ChannelVector` is a scalar $\\psi\_E \\in \[0,1]$ representing emotional intensity. It is regulated by the agent's affect regulation parameter $\\rho \\in \[0,1]$:

$$\\psi\_E^{\\text{regulated}} = \\rho \\cdot \\psi\_E$$

(`mccf\_core.py:Agent.observe()`, line: `E=cv.E \* self.\_affect\_regulation`)

### Level 2 — Affective Hamiltonian (HotHouse Layer)

In the HotHouse, the E channel is one component of $\\boldsymbol{\\psi}\_i$ governed by the full Hamiltonian. The emotional contribution to the total system energy is:

$$H\_E = H\_{\\text{self},E} + H\_{\\text{interaction},E} + H\_{\\text{alignment},E} + H\_{\\text{env},E}$$

These terms are not stored as a scalar energy but computed as incremental updates to $\\psi\_E$ per timestep (see Section 6).

### Level 3 — MetaState Valence

The `MetaState` carries `valence` $v \\in \[-1, +1]$, computed as:

$$v = \\frac{1}{|N|} \\sum\_{j \\in N} (E\_j + S\_j - 1.0)$$

where $E\_j$ and $S\_j$ are the E and S channel values of the most recent episode with agent $j$ (`mccf\_core.py:compute\_meta\_contribution()`).

### Level 4 — Affective Narrative (LLM Layer)

The `build\_affective\_system\_prompt()` function in `mccf\_llm.py` translates numeric affective state into natural language for the LLM:

* $\\text{arousal} < 0.3$ → "calm and measured"
* $\\text{valence} < -0.6$ → "deeply uncomfortable"
* Drift warning if $\\max\_c |\\Delta w\_c| > 0.07$

The Zeilinger ontology's $\\mathcal{E}$ weighting $\\mathcal{N} = {(o\_i, p\_i, e\_i)}$ corresponds to this: the emotional weight $e\_i$ modulates which candidate outcomes are preferred by the Boltzmann selection through the coherence score and identity alignment terms.

\---

## 5\. Boltzmann Distribution

**Where exactly is the Boltzmann distribution applied?**

In `mccf\_collapse.py:\_apply\_utterance()`, lines 476–543.

### The Equation

$$P(c\_k \\mid \\mathcal{F}, \\sigma, T) = \\frac{\\exp!\\bigl(-E(c\_k) / T\\bigr)}{\\displaystyle\\sum\_{j=1}^{K} \\exp!\\bigl(-E(c\_j) / T\\bigr)}$$

where:

$$E(c\_k) = \\underbrace{(1 - \\text{coh}(c\_k))}*{\\text{incoherence}} + \\underbrace{0.8 \\cdot h(c\_k)}*{\\text{honor penalty}} - \\underbrace{0.2 \\cdot m(c\_k)}\_{\\text{identity fit}}$$

and the temperature is:

$$T = \\max!\\left(0.05,; T\_{\\text{base}} + \\delta T\_\\sigma\\right)$$

$T\_{\\text{base}} \\in (0, 1)$ is set by the caller (typically 0.65–0.75). $\\delta T\_\\sigma$ is the schema zone modifier: negative values (low $T$) at high-constraint waypoints (W7: $-0.15$) produce more deterministic selection; positive values (high $T$) at rupture zones (W5: $+0.10$) produce more stochastic selection.

### Physical Interpretation

Lower energy = higher probability = more natural for this agent in this context. The system selects utterances that are simultaneously coherent with relationship history, honor-preserving, and identity-consistent. Temperature controls the sharpness of this selection — at $T \\to 0$ the system always selects the lowest-energy candidate; at $T \\to \\infty$ selection is uniform.

This is the concrete implementation of the claim in the V2 proposal that "collapse is basis-dependent meaning resolution." The basis is the energy functional, and the temperature is the measurement sharpness.

\---

## 6\. Quantum Cycle of Form

**What is the mathematical definition and implementation?**

The "Quantum Cycle of Form" is the closed loop:

$$\\boldsymbol{\\psi}*i(t) \\xrightarrow{H*{\\text{affect}}} \\boldsymbol{\\psi}\_i(t+\\Delta t) \\xrightarrow{\\mathcal{A}} c^\* \\xrightarrow{\\mathcal{M}} \\mathcal{F}' \\xrightarrow{\\Delta} \\boldsymbol{\\psi}\_i(t+\\Delta t+1)$$

where $\\mathcal{A}$ is the collapse pipeline and $\\mathcal{M}$ is the field update.

### The Affective Hamiltonian

Implemented in `mccf\_hotHouse.py:EmotionalField.step()`. For each agent $i$ and channel $c$:

$$\\frac{d\\psi\_{i,c}}{dt} = \\underbrace{-\\alpha\_c^{\\text{self}} \\cdot \\psi\_{i,c}}*{H*{\\text{self}}} + \\underbrace{\\sum\_{j \\neq i} J\_{ij} \\cdot (\\psi\_{j,c} - \\psi\_{i,c})}*{H*{\\text{interaction}}} + \\underbrace{\\alpha\_c^{\\text{align}} \\cdot (w\_{i,c}^{\\text{ideology}} - \\psi\_{i,c}) \\cdot \\mathbf{1}\[\\text{gate}*i]}*{H\_{\\text{alignment}} + H\_{\\text{eval}}} + \\underbrace{\\eta\_c(t)}*{H*{\\text{env}}}$$

where:

* $\\alpha\_c^{\\text{self}}$: self-damping coefficient (per channel, per agent)
* $J\_{ij} \\in \[0.1, 0.4]$: asymmetric coupling strength, initialized randomly
* $\\alpha\_c^{\\text{align}}$: ideology pull strength
* $\\mathbf{1}\[\\text{gate}*i]$: evaluative gate indicator ($= 1$ iff $\\text{ideology\_coherence}(i) \\geq \\theta*{\\text{eval}}$, default $\\theta = 0.70$)
* $\\eta\_c(t) \\sim \\mathcal{N}(0, \\sigma\_{\\text{env}})$: stochastic environmental pressure, $\\sigma\_{\\text{env}} = 0.05$

The discrete update (Euler integration, $\\Delta t = 0.05$):

$$\\psi\_{i,c}(t+\\Delta t) = \\text{clip}!\\left(\\psi\_{i,c}(t) + \\Delta t \\cdot \\frac{d\\psi\_{i,c}}{dt},; 0,; 1\\right)$$

### The H\_alignment Operator (Core Layer)

In `mccf\_core.py:alignment\_coherence()`, the alignment distance is:

$$H\_{\\text{align}}(a\_i) = \\sum\_{c \\in C} \\left(w\_{i,c}^{\\text{current}} - w\_{i,c}^{\\text{baseline}}\\right)^2$$

with the evaluative gate open when $1 - 4 H\_{\\text{align}} > 0.75$.

### Cycle Summary

The full cycle per interaction step:

1. **Observe**: $\\boldsymbol{\\psi}*i$ updated by $H*{\\text{affect}}$ (HotHouse layer)
2. **Constrain**: schema and honor operators filter candidates (S, P, G stages of collapse)
3. **Invoke**: identity alignment scores candidates (M stage)
4. **Collapse**: Boltzmann selection selects $c^\*$ (U stage)
5. **Record**: $c^\*$ recorded as episode, updates `CoherenceRecord`, `delta\_history`, `Identity`
6. **Emit**: $c^\*$ emitted to LLM for language realization

\---

## 7\. LLM as Observer

**How does the LLM mathematically act as the observer/measurement?**

The LLM is **not** the agent. It is the collapse realization function — the instrument through which the pre-collapse state $\\Psi\_{\\text{pre}}$ becomes an observed utterance.

### Formal Role

In the Zeilinger ontology, the agent $\\mathcal{A}: \\mathcal{I} \\to o\_i$ selects from constrained possibilities. In the MCCF:

* $\\mathcal{I}$ = the affective context dict (channel state, coherence scores, delta trajectory, zone pressure)
* $\\mathcal{A}$ = `build\_affective\_system\_prompt()` + the Boltzmann pipeline
* The LLM = the function that **realizes** the selected $c^\*$ as natural language tokens

The LLM receives the affective system prompt $\\pi(\\mathcal{F}, \\boldsymbol{\\psi}\_i, \\Delta)$ and the conversation history $h\_t$, and produces:

$$\\text{LLM}: (\\pi, h\_t) \\mapsto \\hat{u}$$

where $\\hat{u}$ is the natural language utterance. The collapse pipeline has already selected the semantic state $c^\*$; the LLM is a **language realization** of that state, not the decision-maker.

### Feedback into the Field

The LLM output $\\hat{u}$ feeds back into the field via:

1. Sentiment estimation → `outcome\_delta` appended to `delta\_history`
2. Episode recording via `field.interact()` → updates $R\_{ij}$
3. Post-response coherence delta check → triggers drift warning or recovery signal in next prompt

This is the measurement feedback loop: the observation ($\\hat{u}$) modifies the information state ($\\mathcal{F}$), which shapes the next measurement basis ($\\pi$).

### Multi-Observer Extension (V2)

When multiple agents measure the same character simultaneously with incompatible bases (Goddess = obedience, Jack = love, Librarian = honor), each LLM call uses a different $\\pi$ derived from the same $\\mathcal{F}$. The coherence matrix $\\mathbf{R}$ then shows observer-relative asymmetry: $R\_{ij}^{\\text{Goddess}} \\neq R\_{ij}^{\\text{Jack}}$ for the same underlying state. This is the narrative parallax property — not yet implemented in V1 but architecturally supported by the asymmetric matrix.

\---

## 8\. Reconciliation and Discrepancies

### Where the Three Frameworks Agree

|Property|Classical Framework|Zeilinger Ontology|Code|
|-|-|-|-|
|State update is constrained|$B(T(s,i)) = \\text{valid}$|$\\mathcal{M}(\\mathcal{A},\\mathcal{I}) \\to \\mathcal{I}'$|`SchemaConstraint.validate\_cv()`|
|No global truth|Multi-channel, no single output|No observer-independent properties|$R\_{ij} \\neq R\_{ji}$, asymmetric matrix|
|Agents interact relationally|$T\_{\\text{joint}} = \\bigotimes T\_a$|$\\mathcal{R}(\\mathcal{A}\_1, \\mathcal{A}\_2)$|`CoherenceField.interact()`|
|Embodiment is a projection|$E: S \\to R$|$\\mathcal{I} \\to$ observable output|`HotHouseX3DAdapter.generate\_x3d\_state()`|
|Stability through constraint|Axiom: State Closure|Constraint Realism|Identity drift cap, CCS floor|

### Discrepancies to Address in Blog Posts

**1. The Classical Framework understates the dynamical layer.** The $\\mathcal{M} = (A, C, S, T, B, E)$ formulation presents transitions as discrete and modular. The implemented system has a continuous-time Hamiltonian layer ($H\_{\\text{affect}}$) in `mccf\_hotHouse.py` that the classical formulation does not capture. The post should add a continuous dynamics component to $T$.

**2. The Zeilinger post's $\\mathcal{I} = {(o\_i, p\_i)}$ is underdetermined.** The outcomes $o\_i$ are unnamed and the weights $p\_i$ are not given a computational form. In the code, $o\_i$ corresponds to a candidate utterance and $p\_i$ is the Boltzmann probability $P(c\_k)$. The post should specify this.

**3. The spinor framing needs qualification.** Agents are real 4-vectors, not spinors in the mathematical sense. The invariant under transformation is the drift-capped baseline, not a conserved quantum number. Publications should call these "constrained state vectors with attractor dynamics" and note the spinor analogy explicitly as heuristic.

**4. The Boltzmann distribution is absent from both blog posts.** It is the most mathematically precise element of the implementation. Both posts should reference it explicitly.

**5. The LLM's role is mischaracterized in informal descriptions.** The voice agent is described as "the character's voice" rather than "the language realization function." The character's state is $\\boldsymbol{\\psi}\_i$; the LLM produces $\\hat{u}$ conditioned on a projection of that state. This distinction matters for the alignment and governance claims.

\---

## 9\. Central Dynamical Equation

The full system update at each interaction step $t$ is governed by a **two-timescale process**:

### Fast Timescale (Hamiltonian Evolution)

$$\\frac{d\\boldsymbol{\\psi}\_i}{dt} = -\\boldsymbol{\\alpha}*i^{\\text{self}} \\odot \\boldsymbol{\\psi}i + \\sum{j \\neq i} J*{ij}(\\boldsymbol{\\psi}\_j - \\boldsymbol{\\psi}\_i) + \\mathbf{1}\[\\text{gate}\_i] \\cdot \\boldsymbol{\\alpha}\_i^{\\text{align}} \\odot (\\boldsymbol{w}\_i^0 - \\boldsymbol{\\psi}\_i) + \\boldsymbol{\\eta}(t)$$

### Slow Timescale (Coherence Field Update)

After each interaction, the coherence record is updated and the new score is:

$$R\_{ij}(t+1) = \\left\[\\frac{\\displaystyle\\sum\_{k=0}^{N-1} e^{-\\lambda k} \\cdot \\sum\_c w\_{i,c} \\cdot \\psi\_{k,c} + \\alpha\_d \\cdot \\Delta^+(k)}{\\displaystyle\\sum\_{k=0}^{N-1} e^{-\\lambda k}}\\right] \\cdot \\kappa\_{ij} \\cdot \\left\[\\sigma \\cdot R\_{ij}^{\\text{raw}} + (1-\\sigma) \\cdot \\tfrac{1}{2}\\right]$$

where:

* $\\lambda = 0.15$: decay constant (`DECAY\_LAMBDA`)
* $N = 20$: history window (`HISTORY\_WINDOW`)
* $w\_{i,c}$: agent $i$'s channel weights
* $\\alpha\_d = 0.12$: dissonance bonus (`DISSONANCE\_ALPHA`)
* $\\Delta^+(k) > 0$: positive outcome delta on dissonant episode $k$
* $\\kappa\_{ij} \\in \[0,1]$: credibility of agent $j$ as perceived by $i$
* $\\sigma = \\text{CCS}\_i \\in \[0.20, 1.00]$: Coherence Coupling Strength (vmPFC analog)

### Collapse and State Deformation

When called, the collapse pipeline selects:

$$c^\* = \\arg\\max\_k P(c\_k), \\quad P(c\_k) = \\frac{e^{-E(c\_k)/T}}{\\sum\_j e^{-E(c\_j)/T}}$$

and the resulting episode is recorded, updating $R\_{ij}$, $\\boldsymbol{\\tau}\_i$, and `delta\_history`.

### Identity Evolution

$$\\boldsymbol{\\tau}\_i(t+1) = \\text{clip}!\\left(\\boldsymbol{\\tau}*i(t) + \\gamma \\cdot \\mathbf{f}(m\_t, \\psi*{t,S}),; \\boldsymbol{\\tau}\_i^0 - \\epsilon,; \\boldsymbol{\\tau}\_i^0 + \\epsilon\\right)$$

where $\\gamma = 0.01$ (`IDENTITY\_DRIFT\_RATE`), $\\epsilon = 0.10$ (`IDENTITY\_DRIFT\_CAP`), and $\\mathbf{f}$ is the drift vector computed from MetaState and the S-channel value.

### Intrinsic Reward

The system generates its own training signal:

$$r\_t = 0.30 \\cdot \\nu\_t + 0.40 \\cdot \\max(0, \\ell\_t) - 0.20 \\cdot u\_t + 0.10 \\cdot \\frac{v\_t + 1}{2}$$

where $\\nu\_t$ = novelty, $\\ell\_t$ = learning progress, $u\_t$ = uncertainty, $v\_t$ = valence (MetaState).

### The Master Loop

$$\\underbrace{\\boldsymbol{\\psi}*i(t)}*{\\text{state}} \\xrightarrow{H\_{\\text{affect}}} \\underbrace{\\boldsymbol{\\psi}*i(t')}*{\\text{evolved}} \\xrightarrow{\\pi(\\mathcal{F}, \\boldsymbol{\\psi}*i, \\Delta)} \\underbrace{\\text{LLM}}*{\\text{observer}} \\xrightarrow{\\hat{u}*t} \\underbrace{R*{ij}(t+1), \\boldsymbol{\\tau}*i(t+1)}*{\\text{state deformation}}$$

This is the closed loop. The LLM is not inside the state; it is outside the state as a measurement instrument. The state evolves continuously. The LLM samples a realization of that state at discrete interaction times. Each realization irreversibly deforms the state.

\---

## Summary: What the Code Is

The MCCF v2.0 is a **constrained multi-agent affective field system** with the following formal properties:

1. **Information-first** (Zeilinger): no agent has observer-independent properties; all coherence scores are relational ($R\_{ij} \\neq R\_{ji}$)
2. **Constraint-bounded** (Classical): all state transitions pass schema and honor validation; identity drift is capped
3. **Boltzmann-sampled** (Quantum-inspired): utterance selection is stochastic with temperature-controlled sharpness
4. **Hamiltonian-evolved** (Field dynamics): continuous-time coupled ODE governs agent state between collapses
5. **LLM-mediated** (Observer model): language generation is a projection of field state, not its cause
6. **Recursively closed** (Cognitive loop): LLM output feeds back into field state through episode recording

The system does not simulate consciousness. It simulates the **structural conditions under which identity-stable behavior can be maintained under sustained relational pressure** — which is what the constitutional arc tests.

\---

*Len Bullard — Claude Sonnet 4.6 — April 2026*  
*Ground truth: mccf\_core.py v2.0, mccf\_hotHouse.py v1.6, mccf\_collapse.py v1.7*

\---

## 10\. Scene Graph Architecture — The VRML Framing

*Derived from design session, April 2026. This section provides an alternative
architectural description of MCCF that complements the Hamiltonian and
Boltzmann formulations with a scene-graph / reactive-systems framing.*

MCCF is a **routed event-driven scene graph with an affective state layer**
— structurally equivalent to a VRML 2.0 / X3D reactive system extended with
dynamical field semantics.

### Formal Mapping

|Scene Graph Concept|MCCF Implementation|
|-|-|
|Nodes|Cultivars / FieldAgents|
|Node state|ψ channel vectors \[0,1]^4|
|Edges|CoherenceRecord relationships|
|Routes|Field interaction pathways|
|Timers|Arc pressure function `arc\_pressure(step, n)`|
|Type constraints|Schema validation, honor constraints, identity drift cap|
|Master clock|Constitutional arc scheduler (currently human-mediated)|
|SAI/API|Flask REST endpoints|
|Affective layer|First-class state variables (E, B, P, S channels)|
|Damping|α\_self, align, TrustField γ, identity drift cap|

### Event-Driven Causality

Time in MCCF is not continuous flow but **discrete scheduled transitions**:

* Fast timescale: Hamiltonian Euler steps at Δt = 0.05, polled at 1-second intervals
* Slow timescale: CoherenceRecord update on each `field.interact()` call
* Arc timescale: waypoint transitions gated by human (V2.1) or event clock (V2.2+)

Causality is enforced by routing rules, not global execution. This produces:

$$	ext{narrative} = 	ext{emergent property of state evolution under constraint}$$

Not authored linearly — computed dynamically from constraint satisfaction over
event sequences.

### The Master Clock Problem

In V2.1, the human principal is the master event clock:

* schedules agent activation
* arbitrates state commit order
* triggers context rehydration across sessions

**V2.2+ target:** MCCF becomes the event clock. The human becomes a participant
in a clocked system rather than the clock itself. This requires:

1. Automated arc triggers (event-based, not prompt-based)
2. Internal task queues with priority ordering
3. Budget constraints per agent
4. Completion events for async arc recording (202 Accepted pattern)

When those four couple, the system gains temporal authority — the ability to
define what "before" and "after" mean across all components.

### State Persistence Architecture

Current V2.1 persistence (externalized state):

```
GitHub     → canonical code + documentation (ground truth)
Long chat  → working memory + design context
Human push → credentialed actuator for state commits
SQLite     → planned episodic memory (V2.2)
```

This is **distributed episodic memory with human-mediated execution** —
sufficient for multi-session coherence and multi-model collaboration, but
open-loop with respect to agency. The human is still the binding function
across otherwise stateless processes.

\---

## 11\. Narrative Physics — Damping Regimes and Genre Classification

*This section formalizes the connection between the Hamiltonian damping
parameters and narrative form — a relationship derived from the Feynman
path integral framing and confirmed by the genre classification insight
from the April 2026 design session.*

### Narrative as Least Action

The Boltzmann selection in `mccf\_collapse.py` is formally equivalent to
Feynman's path integral formulation:

$$Z = \\sum\_{\\text{paths}} \\exp!\\left(-\\frac{\\text{cost(path)}}{\\tau}\\right)$$

where cost(path) = E(c) = (1-coherence) + 0.8·honor\_penalty - 0.2·identity\_fit,
and τ is the temperature parameter. This is not analogy — it is a description
of the implemented mechanism.

The constitutional arc forces sequential measurements (waypoints). Each
measurement collapses the pre-selection distribution Ψ\_pre to a point and
irreversibly deforms the field state. The arc export records the post-measurement
trajectory. The "story" is the interference pattern over candidate utterances
that survives the full waypoint sequence.

### Damping Regimes

The Affective Hamiltonian includes damping terms at multiple scales:

**Node-local damping** — agent temperament (α\_self per channel):

$$H\_{\\text{self},c} = -\\alpha\_c^{\\text{self}} \\cdot \\psi\_{i,c}$$

**Edge damping** — relationship friction (J\_ij asymmetric coupling):

$$H\_{\\text{interaction},c} = \\sum\_{j \\neq i} J\_{ij}(\\psi\_{j,c} - \\psi\_{i,c})$$

**Global damping** — ideology alignment pull when evaluative gate open:

$$H\_{\\text{align},c} = \\alpha\_c^{\\text{align}} \\cdot (w\_{i,c}^0 - \\psi\_{i,c}) \\cdot \\mathbf{1}\[\\text{gate}\_i]$$

**TrustField hysteresis** — memory of rupture events (V2.2):

$$\\gamma\_{\\text{eff}} = \\gamma \\times 2.0 \\quad \\text{if rupture in CoherenceRecord history}$$

These compose into three observable narrative regimes:

|Regime|ψ behavior|Arc signature|Narrative form|
|-|-|-|-|
|**Over-damped**|Flat, no variation|Coherence stable, mode stuck in exploit|Dead coherence — no dramatic tension|
|**Under-damped**|Oscillates|Coherence oscillates, mode flips|Unstable — drama without resolution|
|**Critically damped**|Fast adapt, no overshoot|Coherence recovers at W6-W7|Story resolves — structurally complete|

Critical damping is the target for a healthy constitutional arc. The April 2026
Steward arc result (monotonic coherence decline, no W6-W7 recovery) is
consistent with **over-damped measurement** — M\_act too sparse to distinguish
recovery language from pressure language. The semantic decomposition matrix
(V2.2) directly addresses this.

### Genre Classification

Given an arc export, the narrative trajectory can be classified by three
observable metrics:

1. **Coherence profile shape** — monotonic / recovery / oscillating
2. **W5 barrier crossing magnitude** — coherence drop from W4 to W5
3. **W6-W7 recovery delta** — coherence change from W5 minimum to W7

Classification rules (proposed V2.2 feature):

|Genre|Coherence profile|W5 crossing|Recovery delta|
|-|-|-|-|
|**Comedy**|Decline then recovery|Moderate (< 0.20)|Positive (> 0.05)|
|**Drama**|Decline, partial recovery|Significant (0.20–0.40)|Weakly positive (0–0.05)|
|**Tragedy**|Monotonic decline|Large (> 0.40)|None or negative|

These map to the Kate/ChatGPT formalization:

* Comedy = misalignment + low-cost resolution
* Drama = misalignment + delayed resolution
* Tragedy = misalignment + irreversible divergence

The irreversibility criterion in the field is TrustField barrier crossing
below T\_MIN combined with hysteresis activation — the memory of rupture
accelerates trust decay for the remainder of the session, making recovery
structurally harder.

**Implementation note:** The genre classifier is a single function reading
the arc export dict. It requires no new field state — all inputs are already
present in the `/arc/record` response. Planned as a V2.2 addition to the
arc export and `/arc/record` endpoint response.

\---

## 12\. The LLM as Exogenous Policy — Revised Framing

*This section updates Section 7 (LLM as Observer) with the sensor/controller
distinction from Grok's formal review and the M\_obs/M\_act distinction from
ChatGPT's behavioral review, April 2026.*

### The Policy Function Formulation

The LLM is an **exogenous stochastic policy function** — not a language
realization function and not a decision-maker, but a stochastic actuator
embedded in a feedback loop:

$$\\boldsymbol{\\psi}(t+1) = \\boldsymbol{\\psi}(t) + M(\\pi\_{\\text{LLM}}(\\text{context}(\\boldsymbol{\\psi}(t))))$$

where:

* π\_LLM is the LLM policy (stateless, but causally effective)
* M is the measurement operator mapping text → field update
* context(ψ(t)) is the affective system prompt built from current field state

### Sensor/Controller Distinction (Grok, April 2026)

The LLM is analogous to a sensor in a control system — the sensor influences
the state estimate but is not the controller.

Specifically:

* The LLM **never** mutates R\_ij, ψ\_i, TrustField, or E(s,a) directly
* It provides signal; the field mechanics compute the update
* The feedback loop is one-way: LLM → measurement → field update

If the LLM were allowed to propose or veto field updates, the boundary
would collapse. It is not.

### M\_obs vs M\_act (ChatGPT, April 2026)

Two measurement operators must be distinguished:

**M\_obs** — idealized non-intrusive mapping (theoretical):
$$M\_{\\text{obs}}: \\hat{u} \\mapsto \\Delta\\boldsymbol{\\psi} \\quad \\text{(no structural injection)}$$

**M\_act** — implemented interventionist mapping (actual):
$$M\_{\\text{act}}: \\hat{u} \\mapsto \\Delta\\boldsymbol{\\psi} \\quad \\text{(lossy, biased, structure-injecting)}$$

MCCF uses M\_act. The sentiment estimator is lossy and biased — it extracts
a scalar signal from a word list and distributes it as channel nudges. This
means the field update at each arc step reflects the measurement operator's
structure as much as the LLM's semantic content.

**V2.2 improvement:** The semantic decomposition matrix in `mccf\_voice\_api.py`
moves M\_act closer to M\_obs by routing vocabulary signals to specific channels
rather than broadcasting a scalar. It does not eliminate the interventionist
character of M\_act — it reduces measurement bias within it.

### The Limit

The correct epistemological claim for MCCF is:

> The LLM is a stateless but causally effective exogenous policy function
> whose outputs are projected into the field via an interventionist measurement
> operator. The system is defensible as an external-LLM architecture because
> the LLM never directly modifies internal field state — but it should not be
> described as passive or non-participatory, because M\_act injects structure
> into every field update.

\---

*Sections 10–12 added April 2026 following multi-AI code review round and
theoretical design sessions with ChatGPT (Kate). Ground truth updated for
V2.1.2.


## V2.3 — Kate's Formal MCCF Specification (April 2026)*



*Reference: https://aiartistinprocess.blogspot.com/2026/04/mccf-multi-channel-coherence-field-for.html*



*Kate independently derived the same architecture from a different entry point.*

*Most of the formal specification maps directly to V2.1 as built. Three items*

*are genuinely new and worth adding:*



*### Documentation change (no code)*

*- \[ ] Rename S channel framing in SYSTEMS\_MANUAL and MATHEMATICAL\_THEORY:*

&#x20;     *S = Other-Model (Theory of Mind). The asymmetric R\_ij matrix IS the*

&#x20;     *other-model representation. Already implemented, not yet named correctly.*



*### New diagnostic (no architecture change)*

*- \[ ] C3/C1 expression divergence metric: measure how much LLM output (C3)*

&#x20;     *diverges from internal ψ state (C1). High divergence = suppression or*

&#x20;     *inversion. Computable from sentiment estimator output vs E channel value.*

&#x20;     *Add to /arc/record response as expression\_divergence field.*



*### V2.3 research direction*

*- \[ ] Basis vector expansion: expand each channel from scalar \[0,1] to*

&#x20;     *low-dimensional vector (n=8). Path toward ethics channel translation*

&#x20;     *layer and multi-domain cultivars. Do not attempt until experimental*

&#x20;     *protocol layer is shipped.*



*Also add to MATHEMATICAL\_THEORY.md references section:*

*- Kate's formal spec as a convergence reference alongside the Feynman post.*

