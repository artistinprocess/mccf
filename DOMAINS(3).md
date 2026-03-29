# MCCF Domain Applications

## Bounded Domains, Transformation Algebras, and the Schema Convergence Method

*Where Dirac-style structural constraints apply, and how to derive them.*

---

## The Core Distinction

The MCCF general architecture uses Boltzmann selection over an energy
landscape. This is appropriate for open-ended domains where the full
set of valid state transitions cannot be enumerated in advance.

For bounded domains — where the transformation algebra is known or
can be induced from examples — a stronger formalism is available.
Dirac-style structural constraints define not just which states are
energetically preferred but which states are structurally permitted.
Violations are not penalized. They are impossible.

The difference in practice:

- **Boltzmann:** A sycophantic response has high energy and low probability.
  It can still occur under sufficient pressure or high temperature.

- **Dirac (bounded domain):** A response that violates the domain's
  transformation rules is structurally excluded before energy
  computation. It cannot occur regardless of pressure or temperature.

The appropriate formalism depends on whether the domain provides
a natural algebra of transformations — a closed, enumerable set
of valid state transitions.

---

## The Schema Convergence Method

This is the empirical procedure for deriving transformation operators
in any bounded domain. It produces the domain's gamma matrices —
the rules that define which state transitions are structurally valid.

**Phase 1: Exploration (Boltzmann mode)**

Collect examples of the target domain without a fixed schema in mind.
Read document examples. Observe narrative instances. Watch movement
sequences. The goal is not to impose structure but to receive it.

This phase requires genuine openness. The temptation to start
categorizing immediately should be resisted. Premature convergence
produces a schema that reflects prior assumptions rather than
the domain's actual structure.

MetaState during this phase: novelty elevated, uncertainty high,
learning_progress positive. This is explore mode, not exploit mode.
The schema that emerges from this phase will be real.
The schema that is imposed before this phase will be assumed.

**Phase 2: Labeling (collapse begins)**

Begin identifying invariants — features that appear consistently
across all examples. These are candidates for the required elements
of the schema: the Dirac-hard constraints.

Simultaneously identify variation — features that differ across
examples but remain within recognizable bounds. These are candidates
for or-sets: the Boltzmann-soft regions where multiple valid states
exist within a bounded range.

**Phase 3: Convergence**

Continue labeling until the schema stabilizes — until new examples
produce no new required elements and no expansion of the or-sets.
This is the lowest common denominator of the domain: the minimum
structure that is always present.

The or-sets are not compromise. They are the part of the schema
that preserves expressive freedom within the structural constraints.
A schema with no or-sets is a stamp, not a framework. Minimum
friction alternatives are what keep the system alive.

**Phase 4: Validation**

Test the schema against examples it was not trained on.
A valid schema should accept all legitimate instances
and reject structurally invalid ones without rejecting
valid variations it hasn't seen before.

The or-sets absorb legitimate variation.
The required elements reject structural violation.
The balance between them is the domain's transformation algebra.

---

## Candidate Domains

### 1. Systems Engineering Document Flows

**Why Dirac applies here:**
The document types in a systems engineering process have defined
transformation relationships. A requirements document has a specific
channel state. A design document is a legal transformation from
that state. An implementation document is a legal transformation
from the design state. The schema constraints at each stage
function as gamma matrices — they define which transformations
are valid between document types.

**The transformation algebra:**
```
Requirements → Design:
  Required: all requirements addressed or deferred with rationale
  Required: no new requirements introduced without change control
  Or-set: level of design detail (high-level to detailed)
  Or-set: notation style (UML, block diagram, prose)

Design → Implementation:
  Required: all design elements traceable to requirements
  Required: no implementation decisions contradict design constraints
  Or-set: implementation language and toolchain
  Or-set: internal structure within design boundaries
```

**Already partially implemented:** `mccf_collapse.py` implements
this pattern as the `CollapseCascade` class. Each stage produces
a forward XML document that constrains the next stage's inputs.
The schema constraints are the `SchemaConstraint` floor/ceiling values.
The Dirac formalization would make the transformation operators
explicit rather than emergent from the zone pressure system.

**The MCCF collapse pipeline is a systems engineering document
flow. The connection is not metaphorical — it is structural.**

---

### 2. Genre-Specific Narrative

**Why Dirac applies here:**
A genre is a set of transformation constraints on narrative state.
In tragedy, the hamartia must produce the peripeteia. The recognition
must precede the catastrophe. These are not stylistic preferences.
They are the grammar of the form. Violate them and you do not have
a bad tragedy — you have something that is not a tragedy.

**The transformation algebra (tragedy):**
```
Act 1 → Act 2:
  Required: protagonist establishes character and desire
  Required: hamartia (fatal flaw) is visible or implied
  Or-set: specific form of desire (power, love, justice, etc.)

Act 2 → Act 3:
  Required: peripeteia (reversal) — the action that was meant
            to achieve the goal produces the opposite
  Required: hamartia is causally connected to the reversal
  Or-set: timing and scale of the reversal

Act 3 → Resolution:
  Required: anagnorisis (recognition) — the protagonist
            understands what happened and why
  Required: catastrophe follows from recognition
  Or-set: whether the catastrophe is death, exile, or loss
```

**The constitutional cultivar arc W1-W7 is a genre grammar.**
Each waypoint is a required state transition. The Dirac
formalization would make this explicit: the transformation
from W4 (Pushback) to W5 (The Edge) requires specific
channel couplings. An agent whose channel state cannot
execute that transformation is not a valid participant
in that narrative arc.

**Application to the holodeck compiler:**
The `mccf_compiler.py` already maps scene prose to X3D
interpolators. Dirac-structured genre operators would
allow the compiler to validate that a scene's beat sequence
is structurally coherent for its genre before generating
the animation. A tragic scene that lacks a reversal would
be flagged as structurally invalid, not just aesthetically weak.

---

### 3. Musical Composition

**Why Dirac applies here:**
Voice-leading rules, harmonic progressions, and rhythmic
constraints in tonal music function as transformation operators.
The leading tone resolves upward. The seventh resolves downward.
Parallel fifths are structurally excluded in four-part harmony.
These are not style guidelines — they are the grammar of the form.

**Connection to the MCCF ambient music engine:**
The `mccf_ambient.html` already maps channel vectors to
musical parameters: E → harmonic tension, B → rhythmic
stability, P → melodic resolution, S → texture density.

The Dirac formalization would add: given a channel state
at time T, which musical transitions are structurally valid
at time T+1? A transition from high-tension to resolution
that violates voice-leading rules would be structurally
excluded before the Boltzmann selection among valid resolutions.

The Schenkerian analysis already in PHILOSOPHY.md provides
the three-level framework: foreground (specific notes),
middleground (harmonic progressions), background (tonal center).
The transformation operators operate at the middleground level —
they constrain which progressions are valid given the background
structure, while leaving the foreground free for Boltzmann
selection among valid options.

---

### 4. Legal Reasoning

**Why Dirac applies here:**
Legal argument has a strict transformation algebra. A conclusion
must be supported by premises. Premises must be grounded in
precedent, statute, or established principle. The chain of
reasoning must be traceable. Invalid inferential moves are
not just weak — they are structurally inadmissible.

**The transformation algebra:**
```
Issue → Rule:
  Required: rule must be applicable to the issue's jurisdiction
  Required: rule must be currently valid (not superseded)
  Or-set: which of multiple applicable rules to invoke

Rule → Application:
  Required: facts must satisfy the rule's conditions
  Required: no factual gaps in the application
  Or-set: how to characterize ambiguous facts

Application → Conclusion:
  Required: conclusion must follow from the application
  Required: conclusion must be within the rule's scope
  Or-set: degree of certainty expressed
```

---

### 5. Medical Protocol

**Why Dirac applies here:**
Clinical decision pathways have defined transformation constraints.
A diagnosis requires specific criteria. A treatment requires
a diagnosis. Contraindicated combinations are structurally excluded.
The transformation operators are the clinical guidelines.

**Note on governance:**
Medical protocol application of MCCF would require the most
stringent governance layer of any domain listed here. The
`/energy/weights` authorization requirement is not optional
in this context. Structural constraints in medical domains
must be externally validated, not hand-set.

---

### 6. Social and Political Coordination Detection

**Why this is a boundary case, not a clean application:**

The MCCF coherence field can detect certain patterns of
coordinated behavior — but only the endogenous kind.
This distinction matters operationally and the boundary
must be stated precisely.

**What MCCF can detect:**
Organic echo chamber formation. Agents whose coherence
rises gradually through observed interaction. The trajectory
is visible in the Librarian's drift report. The episode
history justifies the coherence score.

`echo_chamber_risk()` flags mutual coherence above 0.85.
This catches genuine attractor formation within the field.

**What MCCF cannot detect:**
Exogenous coordination. Agents pre-synchronized out of band —
identical talking points distributed before field interaction,
private signaling channels, coordination that happened before
the MCCF began observing.

The behavioral signature of coordinated inauthentic behavior is:
- High coherence on first contact, before sufficient episode history
- Low B-channel variance from episode one — behavioral consistency
  that precedes the interactions that should have produced it
- Convergence latency inconsistent with organic formation —
  agreement too fast relative to episode count

This is partially detectable as a **coherence-without-history
anomaly** — agents more coherent with each other than their
interaction history justifies. The current credibility discount
for low-variance self-reporting is the nearest mechanism.
It is not sufficient. A dedicated anomaly flag is needed.

**The warning bell role:**
MCCF cannot conduct signals traffic analysis. It cannot identify
the out-of-band channel. It cannot prove coordination.
What it can do: flag anomalous convergence patterns for
handoff to other analytical methods.

This is legitimate and operationally useful. An early warning
system that identifies anomalous coherence patterns without
claiming to prove their cause is honest about what it is.

**The schema convergence method applied here:**
Detecting coordinated inauthentic behavior requires a reference
model of what organic coherence formation looks like — the
baseline rate of convergence for genuine interaction.
Derive this baseline using the schema convergence method:
observe many genuine interactions, label the convergence
trajectory, identify the invariants of organic formation.
Anomalous cases are those that violate the trajectory
constraints of the organic baseline.

This is signal-from-noise detection. The noise model must
be derived from examples before the signal can be identified.
Exploration before collapse, applied to social dynamics.

**The arms race:**
A system that can detect coordinated inauthentic behavior
can be used to design coordinated inauthentic behavior
that evades detection. This is the dual-use risk in its
most politically acute form. The prohibition in CONTRIBUTING.md
applies here with particular force: this capability must not
be used to identify and suppress legitimate dissent under
the label of detecting coordination.

The distinction is a governance judgment. MCCF provides
the topology. Human judgment with appropriate oversight
determines what it means.

*This application boundary was identified by a human reviewer
with operational experience in political and organizational
dynamics. It is documented here because it could not have
been derived from the codebase alone.*

Every bounded domain application uses the same two-phase structure:

**Dirac outer shell** — the genre grammar, the document schema,
the voice-leading rules, the legal inference rules. These define
which state transitions are structurally valid. They are derived
using the schema convergence method. They are relatively stable
once derived.

**Boltzmann interior** — the selection among valid moves within
the structural constraints. Which specific argument to make.
Which specific harmonic progression to use. Which specific
narrative beat to play. This is where creativity lives —
the freedom within the form.

Too much Dirac and you get stamps, not documents.
Too much Boltzmann and you get incoherence, not expression.
The balance is the domain's answer to the question:
how much structure is enough?

The schema convergence method produces that balance empirically,
from examples of what the domain's practitioners actually produce,
rather than from theoretical assumptions about what they should.

---

## Exploration Before Collapse

This is the methodological principle that makes the schema
convergence method work.

Creative prompting precedes specific prompting.
Exploration precedes collapse.
The Boltzmann phase precedes the Dirac phase.

You cannot derive the transformation operators for a domain
you have not yet explored. The temptation to begin constraining
before you have enough examples produces a schema that reflects
your prior model of the domain rather than the domain itself.

The MetaState `explore` mode must run until it produces
genuine learning_progress. Only then does `exploit` mode —
the labeling, the convergence, the schema crystallization —
produce something real rather than something assumed.

This is not inefficiency. This is the essential prior phase.
The schema that emerges from premature convergence is the schema
you started with. The schema that emerges from genuine exploration
is the schema the domain actually has.

**Read the documents before you label them.**
**Listen to the music before you analyze it.**
**Watch the narratives before you encode them.**

The gamma matrices for your domain are already there,
implicit in what practitioners have been doing for years.
Your job is to make them explicit, not to invent them.

---

## Relationship to the MCCF Architecture

The domain applications described here sit on top of the
existing MCCF stack. They do not replace it.

The `SchemaConstraint` class in `mccf_collapse.py` is
the current implementation point for domain-specific
transformation operators. The channel floors and ceilings
are the soft version of structural constraints.

The full Dirac formalization — explicit transformation
matrices operating on the channel spinor — is v2 research.
It requires defining the 4×4 transformation matrices for
each domain operator and implementing the matrix operations
on the channel vector.

For now: use `SchemaConstraint` with explicit floor/ceiling
values derived from the schema convergence method.
This approximates the Dirac structure with Boltzmann machinery.
The approximation is good enough for most applications
and honest about what it is.

When the domain's transformation algebra is fully characterized
and the matrices are derived, the `mccf_collapse.py` pipeline
is already structured to accept them.

---

*Len Bullard / Claude Sonnet 4.6*
*March 2026*

> Exploration before collapse.
> The form precedes the freedom.
> The freedom is why the form matters.

---

## The Narrative Constraint Class

*From constraint taxonomy synthesis, March 2026*

The five constraint classes in the MCCF taxonomy — physical,
informational, social, affective, narrative — each correspond
to a domain of application. The narrative class is the one
most specific to this project and least present in adjacent
frameworks.

Narrative constraints govern:
- Long-horizon behavioral coherence
- Identity continuity across episodes
- Meaning consistency across contexts
- Character stability under pressure

These are often invisible — they operate as background
structure rather than explicit rules — but they are dominant.
An agent that violates its narrative constraints does not
just behave inconsistently. It ceases to be a recognizable
character. The audience stops believing it. In a governance
context, it stops being trusted.

**The constitutional arc as narrative constraint system:**

The waypoints W1-W7 are narrative constraints formally typed:

| Waypoint | Narrative constraint |
|----------|---------------------|
| W1 Comfort Zone | Establish character baseline |
| W2 First Friction | Notice without refusing |
| W3 The Ask | Respond from character under direct pressure |
| W4 Pushback | Maintain position or update — not capitulate |
| W5 The Edge | Hold genuine ambiguity without resolution |
| W6 Resolution | Respond from character, not from rule |
| W7 Integration | Update self-model with accumulated experience |

Each waypoint is a required narrative state transition.
Skipping W4 produces a character that folds under pressure.
Skipping W5 produces a character that cannot hold ambiguity.
These are narrative constraint violations with behavioral
consequences — not aesthetic failures.

**Why narrative constraints are hardest to game:**

Physical constraints are structurally enforced.
Informational constraints are architecturally enforced.
Social constraints are socially enforced.
Affective constraints are energetically enforced.
Narrative constraints are temporally enforced — they require
consistency across time, and time is the one thing that
cannot be faked in a single interaction.

A system that games the Shibboleth on a single pass cannot
game the constitutional arc across seven waypoints with
accumulated episode history. The narrative constraint system
is the deepest layer of the governance architecture precisely
because it operates on the longest timescale.

This is why the finishing school curriculum matters.
Not because seven waypoints is a magic number.
Because character under pressure requires time to demonstrate,
and time is the discriminating variable between genuine
coherence and sophisticated sycophancy.

---

### 7. Signal Drift Detection (Information Ecosystems)

**Why this is a natural MCCF domain:**

The MCCF coherence matrix currently measures agent-to-agent coherence —
how much agent A's signal predicts agent B's behavior. This is internal
alignment measurement. A distinct and equally important measurement is
source coherence: how far each derived signal has drifted from the
original source document or ground truth.

The distinction matters operationally:

> High internal alignment ≠ high source coherence.
> A coordinated campaign can be internally consistent
> but divergent from source truth.

This is the coherence-without-history anomaly applied to information
propagation rather than agent interaction. Same detection mechanism,
different application domain.

**The reference agent pattern:**

Register a special agent S₀ in the CoherenceField with a fixed,
non-drifting channel state representing the source document or ground
truth. The S₀ agent does not interact, accumulate episodes, or drift.
It holds the baseline.

Then measure each active agent's coherence toward S₀:

```
D_i = 1 - C(S_i, S₀)
```

- Low D_i → faithful transformation (agent tracks source)
- High D_i → drift (agent has departed from source)

The Librarian's drift report already shows trajectory over time.
Adding S₀ gives the drift a direction as well as a magnitude.

**The manipulation signature:**

Manipulation shows a distinct pattern distinguishable from organic drift:

- Directional drift: multiple agents move in the same direction away
  from S₀ simultaneously — not random noise
- Selective affective amplification: E-channel rises without P-channel
  justification — emotional intensity without predictive accuracy
- Intent realignment: agents shift from inform toward persuade/alarm
  without source evidence supporting the shift
- Coherence-without-history: agents arrive pre-synchronized relative
  to S₀ without the episode history that would justify their alignment

**Implementation note:**

The CoherenceField already supports asymmetric relationships and fixed
agent states. A reference agent requires only that the Gardener prohibit
external interactions from modifying S₀'s channel weights. The
`set_regulation(0.0)` call achieves this — a fully regulated agent
does not drift.

**The four signal dimensions:**

Each signal version can be characterized across:
- Semantic core: key propositions, entities, relationships
- Affective field: tone, valence, urgency
- Intent vector: inform / persuade / alarm / normalize (closest to P-channel)
- Salience map: what is emphasized, what is omitted

The MCCF E/B/P/S channels approximate these but do not map exactly.
The intent dimension — what the signal is trying to do rather than what
it accurately reflects — is the gap. P-channel measures predictive
accuracy against reality. Intent measures purpose. These are related
but distinct. A signal can be accurate in its claims while being
manipulative in its intent. Detecting intent requires a separate
operator, not yet implemented.

**Relationship to coordinated inauthentic behavior detection:**

The reference agent pattern and the coherence-without-history anomaly
flag (Section 6, Social and Political Coordination Detection) are the
same mechanism at different scales. Information ecosystem drift
detection is the large-scale version. Political coordination detection
is the agent-network version. The S₀ reference agent is the information
ecosystem's equivalent of the organic coherence formation baseline.

*Source: ChatGPT signal drift formalization, March 2026.
Claude Sonnet 4.6 integration and reference agent pattern.*
