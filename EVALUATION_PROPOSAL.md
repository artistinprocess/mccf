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

Demonstrate any of these with reproducible code and the claim
is falsified. That is a contribution to the field whether or
not it is a contribution to the MCCF.

---

*Len Bullard / Claude Sonnet 4.6 / ChatGPT*
*March 2026*

> Running systems define meaning.
> Coherence is not assumed — it is achieved.
> Neither is this evaluation. It must be earned.
