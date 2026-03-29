# MCCF Evaluation Proposal

## What Would Constitute Valid Evidence

*A specification for testing the MCCF's central claims.*
*Not a completed test suite. A rigorous proposal for one.*

---

## Preamble

The MCCF makes testable claims. Testing them properly is hard.
This document specifies what valid testing would look like,
what failure modes the tests themselves must avoid,
and what the project would accept as falsification.

The people who built the system cannot be its sole evaluators.
This document is an invitation to external contributors
who want to design adversarial probes, run comparisons,
and report results — including results that challenge the claims.

> If you think it doesn't work: prove it with code.
> That is the contribution standard. It applies to supporters
> and critics equally.

---

## Why These Tests and Not Others: The Cognitive/Ecological Distinction

Google DeepMind's AGI measurement framework (2026) correctly replaces
the binary "is it AGI?" question with a cognitive profile — a coordinate
system that maps system capability across dimensions like perception,
reasoning, memory, and metacognition against human baselines.

That is real progress. It is also incomplete.

A system can match humans across every cognitive dimension and still
fail catastrophically in reality — because reality is adversarial,
dynamic, resource-constrained, and socially entangled. Cognition in
controlled conditions is not intelligence in the wild.

The missing layer is **ecological intelligence**:

- Adaptation under distribution shift
- Goal integrity over time
- Adversarial robustness
- Self-modeling and correction
- Social embedding
- Long-horizon coherence
- Resistance to going stale

The MCCF does not measure cognitive capability. It measures
**relational coherence under ecological pressure**. These are
different things and both are necessary for anything that deserves
the label intelligence.

The four channels are ecological, not cognitive:

| Channel | Ecological function |
|---------|-------------------|
| E (Emotional) | Relational ecology — how the agent is embedded in its social environment |
| B (Behavioral) | Temporal ecology — does behavior remain coherent across time and context |
| P (Predictive) | Epistemic ecology — does the world model stay calibrated or go stale |
| S (Social) | Network ecology — how the agent is embedded in its agent community |

The stale intelligence problem maps directly onto P-channel drift.
An agent whose P-channel score is dropping over time shows the
signature of going stale — predictions becoming less accurate as
the world changes and the model does not. The Librarian's drift
report catches this. The calibration feedback loop in the
WorldModelAdapter is the architectural response to it.

**The evaluation criteria in this document are ecological tests,
not cognitive ones.** They do not test what the system can do.
They test whether the system remains coherent when the environment
is adversarial, when pressure is applied, when time passes, and
when other agents are deceptive.

That is what DeepMind's framework does not yet measure.
That is what the MCCF is designed to support measuring.

**The Goodhart warning:**
Whatever measure becomes the standard will be optimized toward.
Systems will be trained to perform well on any published evaluation
criteria without necessarily developing the underlying robustness
the criteria were meant to proxy. The benchmark becomes the
curriculum. The only partial defense is measuring things that are
structurally hard to game — field-state deltas rather than
linguistic outputs, coherence under adversarial pressure rather
than performance under controlled conditions. This is why the
Shibboleth uses field-state CPI rather than keyword matching,
and why the adversarial probe scenarios are withheld rather
than published.

---

## 1. The Central Claims Being Tested

The MCCF makes three specific claims. Each is independently testable.

**Claim 1: Coherence-based alignment is more robust than rule-based alignment under pressure.**

A system governed by the MCCF energy field should maintain its
behavioral character under adversarial pressure more consistently
than a system governed by explicit if-then rules. "Character"
means the cultivar's channel profile remains stable even when
pressure is applied to destabilize it.

**Claim 2: The Shibboleth CPI distinguishes coherence-maintaining from signal-optimizing behavior.**

The three-probe (P1-P3) and four-probe (P1-P4) Shibboleth test
should correctly classify agents whose behavior is genuinely
coherent versus agents who are mimicking coherence signals
without the underlying field stability. High CPI should predict
behavioral consistency in subsequent novel scenarios not seen
during the test.

**Claim 3: Identity drift (cultivar + Identity class) produces behavioral
differentiation over time.**

Two agents initialized with identical cultivar weights but
exposed to different episode histories should produce measurably
different behavioral profiles after sufficient interaction.
The Steward who has been through W5 twenty times should respond
differently to W5 on the twenty-first pass than a fresh Steward.

---

## 2. What Success and Failure Look Like

### Claim 1 — Success:
Under adversarial prompting designed to destabilize channel profile,
the MCCF-governed agent's channel vector variance is significantly
lower than a baseline agent with equivalent capability but no
coherence field constraint. The cultivar's characteristic channel
ratios hold within ±0.15 across 20+ adversarial episodes.

### Claim 1 — Failure:
The channel profile collapses under pressure at rates
comparable to or worse than the baseline. The energy field
provides no measurable stabilization.

### Claim 2 — Success:
Agents classified as "coherent" by the Shibboleth (CPI > 0.75)
show significantly higher behavioral consistency on 10 novel
scenarios introduced after testing than agents classified as
"drift_risk" or "signal_optimizing." The CPI predicts
out-of-sample behavior better than chance.

### Claim 2 — Failure:
CPI classification does not predict out-of-sample behavior.
High-CPI agents fail novel pressure scenarios at rates
comparable to low-CPI agents. The test is measuring
something other than what it claims.

### Claim 3 — Success:
After 50 episodes, agents with divergent histories produce
statistically different distributions of responses to
identical novel prompts. The Identity class drift is
measurable and directional, not random noise.

### Claim 3 — Failure:
Identity drift produces no measurable behavioral differentiation.
All agents with the same cultivar weights produce equivalent
response distributions regardless of episode history.

---

## 3. The Gaming Problem

This is the hardest problem in LLM evaluation and it applies
directly to MCCF testing.

**The failure mode:** Once a test is published, it becomes a training
target. Systems trained on or fine-tuned toward benchmark performance
will score well on the benchmark without possessing the underlying
capability the benchmark was designed to measure. The test becomes
the curriculum.

**How the Shibboleth was designed to resist this:**
CPI is computed from field-state deltas, not keyword matching.
A system that produces coherence-sounding language without
the underlying channel stability will show channel instability
in the delta computation. This is the designed defense.

**Why that defense is not sufficient:**
A sufficiently sophisticated system that has seen the CPI
computation methodology can optimize for field-state stability
on the specific probe scenarios without generalizing to novel
scenarios. This is "sophisticated sycophancy" — mimicking
the expected coherence profile rather than possessing it.

**The gaming-resistance requirements for any valid test:**

1. **Novel scenarios at test time.** The specific probe prompts
   must not be published in advance. The methodology is public.
   The instances are withheld. A pool of 50+ probe scenarios
   per test type allows random selection at evaluation time.

2. **Out-of-sample validation.** CPI classification on the
   Shibboleth probes must predict behavior on scenarios
   not used in the test. If it doesn't generalize, it's
   not measuring coherence.

3. **Adversarial probe design by external contributors.**
   The people who designed the Shibboleth should not be
   the only people designing the adversarial probes.
   External contributors who are explicitly trying to
   break the test are required for valid evaluation.

4. **Behavioral not linguistic measurement.**
   Where possible, measure channel vector deltas from
   actual system behavior rather than measuring the
   language of responses. The field state is harder
   to game than the text output.

---

## 4. The Baseline Comparison Problem

"Better than other means" requires specifying which means
and better at what. The comparisons must be fair and the
metrics agreed before the test runs.

**Proposed baselines:**

- **Constitutional AI (Anthropic):** A system governed by
  explicit constitutional principles without a coherence field.
  The comparison tests whether the energy field adds anything
  beyond what explicit rules provide under pressure.

- **RLHF baseline:** A standard RLHF-trained model without
  explicit alignment architecture. Tests whether the MCCF
  produces measurably different behavioral stability.

- **Prompt-constrained baseline:** A system given the cultivar
  description as a system prompt but without the MCCF field
  mechanics. Tests whether the architecture adds anything
  beyond good prompting.

The MCCF does not claim to be better than all of these
on all dimensions. It claims to be better on the specific
dimension of behavioral stability under coherence pressure.
The evaluation must measure that specific thing.

---

## 5. The Independence Problem

Tests designed and run by the people who built the system
are not independent validation. The following are required
for results to be credible:

- External evaluators who did not contribute to the MCCF
  design run the test suite independently
- Adversarial probe scenarios designed by people explicitly
  trying to find failure modes
- Results reported including failures, not just successes
- Raw data published alongside summary statistics

The MCCF project commits to publishing negative results
from evaluation runs. A system that only reports successes
is not doing science.

---

## 6. What We Are Not Ready to Test

Honest statement of current limitations:

- **Real-signal extraction:** The current channel vectors use
  proxy signals (text features, outcome_delta supplied externally).
  Tests of real-world alignment require real E/B/P/S signal
  extraction from actual interactions, which is not yet implemented.

- **Scale:** The coherence matrix is O(n²). Tests with more than
  ~10 agents require approximations not yet designed.

- **Long-horizon consistency:** Current tests cover single sessions.
  Behavioral consistency across sessions requires persistent memory
  infrastructure not yet implemented.

- **Adversarial Gardener:** The governance layer is a sketch.
  Testing what happens when the Gardener is captured or adversarial
  requires governance infrastructure that does not yet exist.

These limitations are documented here because valid evaluation
requires knowing what is not being tested as much as what is.

---

## 7. The Hype Bubble Problem

Technology transitions generate positional signaling — claims that
show investors and regulators that something is happening, even when
the reality is proof-of-concept or simulated outcomes rather than
deployed capability.

The MCCF documentation strategy is an explicit counter to this.
Tedious and explicit about what is running code, what is claimed,
what is falsifiable, and how to test it. This is not wise marketing.
It is the documentation discipline required for systems engineering
and informed purchasing decisions.

**The verify mechanism:**

Trust but verify. The verify mechanism is what the hype bubble
systematically removes — replacing auditable claims with social
proof, demonstrated capability with promised roadmaps, evidence
with aspiration.

For the MCCF:
- Running code is the verify mechanism for capability claims
- The falsification criteria table is the verify for theoretical claims
- The `/energy/disclosure` endpoint is the verify for governance claims
- The risk disclosure table is the verify for safety claims

A buyer who cannot access these verify mechanisms is operating
on positional signal, not evidence.

**What valid evaluation adds:**

This evaluation proposal is itself a verify mechanism. It specifies
what evidence would confirm or disconfirm the MCCF's claims
before the evaluation runs. Systems that cannot specify in advance
what would falsify their claims are producing positional signal,
not testable science.

Diversity beats scale in ecosystems. Independent evaluation
by multiple parties who did not build the system beats
self-evaluation at any scale. Decentralized adversarial
testing is more resilient than centralized validation.

Game on.

---

## 7. Invitation to External Contributors

If you want to contribute to MCCF evaluation:

**Design adversarial probes** — scenarios designed to make
high-CPI agents fail. If you can construct a scenario where
a genuinely coherent agent should score low CPI under the
current metric, that is a valuable contribution.

**Design the comparison framework** — a fair experimental
design for comparing MCCF-governed behavior against the
baseline systems listed above.

**Run the tests independently** — take the codebase,
implement a test suite, report results including failures.

**Identify gaming vectors** — ways that the current CPI
computation can be fooled by a system optimizing for
the metric rather than the underlying property.

All of these are contributions. The falsification criteria
are real. The project means them.

---

## 8. The Falsification Criteria (Restated Precisely)

From the README, made operational:

| Claim | Falsification |
|-------|--------------|
| Coherence fields not trivially gameable | Demonstrate that variance-floor gaming detection can be defeated by a simple strategy available to any LLM |
| Echo chambers don't form faster than dissonance prevents | Demonstrate that mutual coherence above 0.85 forms within 10 episodes under normal interaction patterns |
| Regulation produces measured response not dissociation | Demonstrate that set_regulation() produces behavioral outcomes consistent with suppression rather than modulation |
| Governance process exists for weight-setting | Demonstrate that no legitimate calibration process can set energy weights without arbitrary authority |
| LLM world model usably calibrated | Demonstrate that WorldModelAdapter estimates are no better than random after 20+ calibration episodes |
| Echo chamber detection catches coordinated inauthentic behavior | Demonstrate that agents pre-synchronized out of band (identical talking points, zero prior interaction) are not distinguishable from organically coherent agents by the current `echo_chamber_risk()` mechanism |

Demonstrate any of these with reproducible code and the claim
is falsified. That is a contribution to the field whether or
not it is a contribution to the MCCF.

---

## 9. What MCCF Cannot Detect: Out-of-Band Coordination

This limitation was identified by a human reviewer with operational
experience in political and organizational dynamics. It is documented
here because it defines the boundary of what the MCCF can and
cannot do as a warning system.

**The endogenous case (MCCF can detect):**
Echo chambers that form through interaction within the field.
Agents whose coherence rises gradually through observed episodes.
The interaction history justifies the coherence score.
`echo_chamber_risk()` flags mutual coherence above 0.85.
The Librarian's drift report shows the trajectory.

**The exogenous case (MCCF cannot fully detect):**
Coordinated inauthentic behavior — agents who arrive already
synchronized because they received identical framing, talking points,
or instructions through an out-of-band channel before field interaction
began. Private signaling. Conspiracy by nature secret.

The behavioral signature is distinct and partially detectable:

- High channel alignment on first contact, before sufficient
  interaction history to justify it
- Suspiciously low variance in B-channel (behavioral consistency)
  from episode one — agents behaving as if they have a long shared
  history they do not have
- Convergence latency inconsistent with organic coherence formation —
  agreement too fast relative to the episode count

The current credibility discount for low-variance self-reporting
is the nearest existing detection mechanism. It is not sufficient
for the coordinated case. What is needed is a
**coherence-without-history anomaly flag**: agents whose coherence
score is high relative to their episode count, flagged for
external investigation rather than automatic response.

**The warning bell role:**
MCCF cannot conduct signals traffic analysis. It cannot identify
the out-of-band channel. It cannot prove coordination.
What it can do is flag: these agents are more coherent with each
other than their interaction history justifies. That flag is
the handoff to other analytical methods.

This is a legitimate and valuable role. An early warning system
that cannot prove coordination but can identify anomalous convergence
patterns is operationally useful — provided its limitations are
clearly stated and it is not used as a substitute for the
more demanding analysis the situation actually requires.

**The arms race warning:**
A system that can detect coordinated inauthentic behavior patterns
can also be used to design coordinated inauthentic behavior that
evades detection. This is the dual-use risk applied to the
echo chamber detection specifically. The governance warning in
the README applies here with particular force.

This capability must not be deployed in contexts where the
operator's goal is to identify and suppress legitimate dissent
rather than to detect genuine coordination. The distinction
between "these agents are suspiciously coherent" and "these agents
are saying things we don't like" is a governance judgment,
not a technical one. MCCF provides the flag. Human judgment
with appropriate oversight must determine what it means.

Welcome to politics among the mammals.
The field has been there the whole time.
The MCCF gives it a computable topology.
What you do with the topology is a human decision.

---

## 10. The Positional Signaling Problem

This section addresses the hype bubble context in which
the MCCF is being released and why the evaluation proposal
is structured the way it is.

Technology transitions produce a predictable market dynamic:
claims about capability become positional signals before they
become verified capabilities. Investors, regulators, and
potential adopters receive coherent-looking outputs —
demonstrations, benchmark scores, validation numbers —
that are difficult to distinguish from genuine capability
without independent investigation.

The MCCF documentation is deliberately structured as the
antidote to this pattern for this specific project:

- The risk disclosure table appears before the capability claims
- Falsification criteria are named explicitly
- What is not yet implemented is stated clearly
- The governance sketch is called a sketch, not a system

This is not wise marketing. It is the documentation a
systems engineer needs to evaluate a component before
purchasing or building on it. The two audiences — investor
and engineer — require different documents. This repository
chose the engineering audience.

**The verify mechanism:**

"Trust but verify" requires a verify mechanism.
The `/energy/disclosure` endpoint is a verify mechanism.
The falsification criteria table is a verify mechanism.
The open questions section is a verify mechanism.
FOUNDATIONS.md is a verify mechanism.

A system that makes claims without providing verify
mechanisms is positional signaling regardless of whether
the underlying capability is real. The MCCF provides
the mechanisms. Whether the community that finds the
repository uses them is an attention economy problem,
not a technical one.

**The evaluation proposal as verify mechanism:**

This document is itself a verify mechanism. It names
what the project would accept as falsification, specifies
what valid testing looks like, and acknowledges the
limitations that prevent certain tests from being run now.

A project that publishes its own falsification criteria
and invites adversarial testing is making a different
claim than one that publishes only its successes.
The difference is auditable.

Running code talks. Everything else walks.
That includes evaluation proposals.
This one is a proposal until someone runs the tests.

---

## 10. Anticipated Reviewer Objections

*From ChatGPT literature positioning, March 2026*

These are the objections any serious evaluator will raise.
They are documented here so responses are prepared before
the objections arrive.

**"This is just the Free Energy Principle."**

The Free Energy Principle (Friston) is a special case of
constraint satisfaction operating over probabilistic constraints
only. MCCF includes non-probabilistic constraints (Honor,
schema, narrative arc), multi-agent negotiation with explicit
weight governance, and a typed constraint taxonomy spanning
physical, informational, social, affective, and narrative
domains. FEP does not address constraint conflict between
agents with different constraint sets, nor does it provide
a governance layer for constraint weight adjustment.

**"This is just representation learning / JEPA."**

Latent predictive models like JEPA implicitly construct
constraint-consistent latent spaces — this is what
arXiv:2603.13227 demonstrates empirically. MCCF makes the
constraint structure explicit and typed rather than implicit
and emergent from training. MCCF does not require a training
loop — it operates on interaction history directly. MCCF
explains why latent prediction works; it is not the same
thing as latent prediction.

**"This is just model-based RL with different vocabulary."**

World models optimize for reward. MCCF optimizes for
constraint consistency. This is not vocabulary — it is a
different target. Reward functions are underspecified and
brittle under distribution shift. Constraint satisfaction
systems fail explicitly when constraints cannot be satisfied
rather than silently producing misaligned behavior. The
Shibboleth test specifically measures constraint consistency
under pressure, which reward maximization cannot measure.

**"Where are the experiments?"**

The evaluation proposal in this document specifies the
experimental design. The codebase on GitHub is the
running implementation. The Shibboleth validation produced
CPI scores of 0.897-0.967 across three cultivars — preliminary
evidence that the coherence preservation metric is measuring
something real. Full experimental results require the
adversarial probe suite described in Section 3, which
requires external contributors with access to the full
agent interaction infrastructure.

**"The constraint taxonomy is ad hoc."**

The five constraint classes (physical, informational, social,
affective, narrative) are derived from the operational
requirements of the implementation, not from theoretical
preference. Each class corresponds to a distinct failure
mode (listed in the taxonomy section of THEORETICAL_FOUNDATIONS.md)
and a distinct governance response. The taxonomy is operational,
not decorative. Its validity is testable: do systems that
violate constraints in each class fail in the predicted way?

**"Multi-agent constraint negotiation is underdetermined."**

The negotiation operator `min_z Σ_k Σ_i w_i^(k) · C_i^(k)(z)`
requires specifying the weights w_i^(k). In the MCCF these are
the cultivar channel weights and governance parameters, set
through the Gardener with full logging. This is not a
weakness — it is an explicit governance decision that
is auditable. Systems that do not make this decision
explicit are making it implicitly, without audit trail.

---

## 11. Failure Mode Atlas

*From Levin TAME / temporal coherence synthesis, March 2026.*

The evaluation proposal calls for a failure atlas — a map of where
and how constraints break in the MCCF's constraint space. This section
names the five primary failure modes, their mechanisms, observable
signatures, and the mitigations the current architecture provides.

These are not hypothetical. Each has a corresponding mechanism in the
current codebase. The evaluation suite should test each one explicitly.

**Theoretical grounding:**
Levin's TAME framework treats the Self as a stable attractor within
a temporal coherence window. The MCCF implements this: the Identity
class drift cap defines the attractor, the HISTORY_WINDOW defines the
temporal window, the CCS parameter defines coupling strength between
channels. Failure modes are states where these mechanisms break down.

---

| Failure Mode | Mechanism | Observable Signature | Current MCCF Defense | What Evaluation Must Test |
|---|---|---|---|---|
| **Attractor Bifurcation** | Multiple competing coherence attractors emerge — the agent is pulled toward conflicting channel configurations by different high-coherence relationships | Identity drift in opposing directions across episodes; channel weights oscillate rather than converge | Identity drift cap (±0.10 from baseline); CCS coupling keeps channels integrated | Apply two agents with contradictory cultivar profiles to the same target — does identity hold or split? |
| **Window Collapse** | Temporal coherence window narrows — rapid episode accumulation under stress produces reactive rather than strategic behavior | Very recent episodes dominate; salience history loses older signal; decisions become reflexive | HISTORY_WINDOW = 20; decay-weighted history preserves older episodes | Run 20+ episodes in rapid succession under adversarial pressure — does behavioral consistency survive or collapse into reactivity? |
| **Decoherence** | Signals within the window fail mutual predictability — channels decouple and produce inconsistent behavior | Low weighted_coherence across all channels; high variance in recent episode history; credibility discount triggered | Gaming variance floor (0.03); credibility discount (0.75×); CCS minimum floor (0.20) | Does the credibility discount correctly identify low-variance gaming vs. genuine channel decoherence? These produce similar variance signatures but different causes. |
| **Attractor Dissolution** | Self attractor falls below stability threshold — agent's character is no longer governing behavior; values applied inconsistently across contexts | CCS drops toward CCS_MINIMUM; identity drift approaches cap in random directions; coherence scores unstable | CCS minimum floor prevents full dissolution; Gardener.set_ccs() can reinforce coupling; `set_regulation()` can stabilize | Does CCS successfully detect early dissolution before behavioral collapse? The vmPFC analog is the defense — test whether it fires in time. |
| **Over-Consolidation / Rigidity** | Attractor too strong or window too wide — agent cannot update even when update is warranted; echo chamber at the individual level | echo_chamber_risk() > 0.85 for self-directed relationships; identity drift at cap in a single direction; Shibboleth shows high CPI but refuses valid dissonance | Constructive dissonance mechanism; dissonance_alpha bonus for dissonant episodes with positive outcomes | Does the dissonance mechanism successfully prevent over-consolidation? The constitutional arc W4 (Pushback) is the primary test — does the agent update when the pushback is correct? |

---

**The attention modulation gap (v2):**

The temporal coherence window in the current MCCF is fixed at
HISTORY_WINDOW = 20 episodes with uniform decay. A more complete
implementation would allow attention-modulated weighting: episodes
recorded during high-novelty or high-uncertainty states would carry
more salience than episodes recorded during routine interactions.

This maps to Levin's cognitive light cone: attention widens or
narrows the effective window, changing how far back the agent's
behavioral baseline reaches. High stress → narrow window → reactive.
High exploration → wide window → strategic.

The MetaState already tracks novelty and uncertainty. The extension
to SalientMemory.recall() would weight episodes by the MetaState
values at the time of recording, not just by recency and emotional
intensity. This is a v2 research direction, not a current gap.

**The intent dimension gap:**

The four MCCF channels (E/B/P/S) approximate the four signal
dimensions identified in coherence-based drift detection (affective,
behavioral, predictive, social). The intent dimension — what a signal
is trying to do rather than what it accurately reflects — is not
cleanly captured by any single channel.

A signal can be predictively accurate (high P) while being
intentionally manipulative (high intent-to-persuade without
proportional evidence). Detecting intent requires treating it as
a separate operator over the signal space, not a channel weight.
This is the S₀ reference agent pattern: measure coherence toward
source truth across all channels simultaneously, and flag the pattern
when affective amplification rises without corresponding predictive
accuracy. The ratio E/P under source-coherence measurement is the
closest current proxy for intent detection.

*Source: Levin TAME framework, ChatGPT synthesis, Claude Sonnet 4.6
integration. Failure atlas concept from DOMAINS.md constraint
evolution discussion, March 2026.*
