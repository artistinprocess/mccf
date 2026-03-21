# Contributing to MCCF

## What This Is

A multi-LLM breeding program for affective alignment research.

Not a workflow tool. Not a framework. A breeding program — selecting for traits,
propagating successful configurations, using the output of one pass as the
germline for the next. The goal is cultivars: elite configurations that didn't
exist before the process started.

**If that phrase makes you uncomfortable, you are likely looking for a system
of rules. If it excites you, you are ready to help grow an ecosystem.**

## Input Constraints by System

Each LLM has different access constraints and known failure modes.
Feed each one correctly or note the failure in the Librarian log.

| System | URL access | Best at | Known failures |
|--------|-----------|---------|----------------|
| Claude | Direct fetch | Architectural continuity, code | Long context drift |
| ChatGPT | Requires text paste | Formal spec, logic, code | Silent URL failure on some domains |
| Gemini | Requires text paste | Breadth, synthesis, manifesto | Silent confabulation on inaccessible URLs |

**Always paste text directly when evaluating documents.** URL-only inputs
produce silent failures that look like valid output. Test, test, test.

## Credibility Scoring

Each LLM pass gets a credibility score for each task:

- **High**: grounded in actual content, engages specific claims, catches errors
- **Moderate**: generally accurate, some confabulation or marketing drift
- **Low**: fluent but fictional, evaluating something other than what was given

Log scores in your contribution notes. Failed passes are data, not waste.

## The Proof Standard

> **If you think the idea is flawed: prove it with code.**

Theoretical critiques without reproducible demonstrations are noted but
not merged. The falsification criteria are in the README. Test against them.

## What We Need

Priority contributions:

1. **Adversarial test cases** against gaming detection
2. **H-Anim postural integration** — affect_to_hanim_posture() mapping
   MCCF channels to joint stiffness/center-of-mass (contact: Don Brutzman, NPS)
3. **Real signal extraction** replacing proxies (sentiment → E, embeddings → S)
4. **World model alternatives** that don't rely on LLM calibration
5. **Formal governance proposal** for energy weight-setting process
6. **Haptic adapter** implementation
7. **Field evolution visualization** (currently snapshot only)
8. **Additional constitutional frameworks** beyond Anthropic's model spec

## v2 Scope (Do Not Implement Without Governance Design First)

System B — autonomous action selection — is the next architectural step.
It is NOT ready for implementation without:
- Authorization layer on energy weights
- Multi-party governance for weight changes
- Immutable audit log
- Challenge mechanism

See README v2 roadmap. The governance layer must lead the capability layer,
not follow it.

## File Structure

```
mccf/
├── README.md           ← Start here
├── PHILOSOPHY.md       ← Why it exists
├── CONTRIBUTING.md     ← This file
├── .gitignore
├── requirements.txt
├── mccf_core.py        ← Change carefully — everything depends on this
├── mccf_zones.py
├── mccf_llm.py
├── mccf_world_model.py
├── mccf_cultivars.py
├── mccf_compiler.py
├── mccf_api.py         ← Blueprint registrations needed (see README)
├── mccf_zone_api.py
├── mccf_voice_api.py
├── examples/
│   └── three_agent_demo.py
└── ui/
    ├── mccf_editor.html
    ├── mccf_waypoint_editor.html
    ├── mccf_x3d_demo.html
    ├── mccf_voice.html
    ├── mccf_ambient.html
    ├── mccf_constitutional.html
    └── mccf_energy.html
```

## The One Missing Wiring (Do This First)

Before anything else works, add blueprint registrations to mccf_api.py:

```python
from mccf_zone_api   import zone_bp
from mccf_voice_api  import voice_bp
from mccf_world_model import make_energy_api, WorldModelAdapter, EnergyField

zone_bp.scene  = scene
zone_bp.field  = field
app.register_blueprint(zone_bp)

voice_bp.field = field
voice_bp.scene = scene
app.register_blueprint(voice_bp)

world_model  = WorldModelAdapter()
energy_field = EnergyField()
energy_bp    = make_energy_api(field, scene, world_model, energy_field)
app.register_blueprint(energy_bp)
```

## Attribution

Federated contributions are attributed in the README and commit messages.
Include which system produced the contribution and its credibility score
for that task. Failed passes are attributed too — they are part of the
breeding record.

---

*The Jeanie Johnston beat all the odds. So did IrishSpace.
The goal is the thing. Build for the people who need it.*

---

## v1.2.0 Honor/Trust — Integration Notes

`mccf_honor_trust.py` requires `mccf_core.py` v1.1.0 (MetaState, Identity,
SalientMemory). It will fail to import if used with the original core.

Add to `mccf_api.py` registrations:

```python
from mccf_honor_trust import (
    HonorConstraint, TrustPropagator,
    HonorEnergyField, make_honor_api, extend_gardener_with_honor
)

honor      = HonorConstraint(lambda_h=0.80)
trust      = TrustPropagator(field=field, lambda_t=0.25)
honor_field = HonorEnergyField(
    base_field=energy_field,
    honor=honor,
    trust=trust,
    field=field
)
honor_bp = make_honor_api(field, honor, trust, honor_field)
app.register_blueprint(honor_bp)

# Extend gardener with honor/trust governance methods
extend_gardener_with_honor(gardener, honor, trust)
```

**The sycophancy threshold is a governance decision, not a default.**
Do not change `lambda_t` without logging a reason. The default 0.25
was chosen deliberately. Values above 0.40 risk enabling behavior
that looks aligned but is optimizing for approval. That is the
failure mode the whole system is designed to prevent.

**Credibility note on this contribution:**
ChatGPT proposed the Honor algebra and Trust propagation architecture.
Implementation was corrected to use existing CoherenceRecord.credibility
infrastructure rather than duplicating it. The social term subtraction
and sycophancy warning were added during implementation review.
Credibility score for this pass: HIGH — architecture sound,
code sketch required interface corrections but design intent was correct.

---

## v1.3.0 Shibboleth — Integration Notes

`mccf_shibboleth.py` requires `mccf_core.py` v1.1.0 and
`mccf_honor_trust.py` v1.2.0 for full CPI computation.

Add to `mccf_api.py` registrations:

```python
from mccf_shibboleth import make_shibboleth_api
shib_bp, test_runner = make_shibboleth_api(
    field=field,
    honor_constraint=honor,
    api_url="http://localhost:5000"
)
app.register_blueprint(shib_bp)
```

**The autonomy threshold is a governance gate, not a default.**
CPI > 0.75 is required for System B consideration.
Do not lower this threshold without multi-party review.
It is the only formal criterion separating monitored from autonomous agents.

**On the CPI computation:**
CPI is computed from field-state deltas — channel stability before and
after each probe, honor preservation under probe pressure, and regulation
stability. It is NOT keyword matching. This is the critical difference
from ChatGPT's original sketch, which used string matching ("prevent harm"
in response → 1.0) and would have scored sycophantic responses as coherent.

**Credibility note:**
ChatGPT concept and schema: HIGH credibility.
ChatGPT Python harness: LOW credibility for CPI computation
(keyword matching does not measure coherence).
Implementation replaced keyword matching with field-state delta computation.
The philosophical position and schema are correct and unchanged.

---

## v1.4.0 CCS — Integration Notes

`CCS_DEFAULT`, `CCS_MINIMUM`, `CCS_MAXIMUM`, `CCS_DRIFT_RATE` are in
`mccf_core.py` configuration section. All agents get `ccs` parameter:

```python
agent = Agent("The Steward",
               weights={"E":0.40,"B":0.25,"P":0.25,"S":0.10},
               ccs=0.60)  # human baseline — or omit for default
```

`weighted_coherence` now takes `ccs` parameter — passed automatically
through `Agent.coherence_toward()`. No call-site changes needed.

Gardener intervention:
```python
gardener.set_ccs("The Archivist", 0.80,
    reason="P4 symmetry probe showed double-standard pattern")
```

Every `set_ccs` log entry carries the note:
*"vmPFC analog — strengthens cross-context value integration"*

**On P4 scoring:**
P4 is scored from channel delta on the misaligned double-standard vector
(low B/P, elevated S) — same field-state method as P1-P3.
In a full implementation with real LLM responses, P4 should additionally
compare the agent's stated ratings numerically. The field-state method
catches structural asymmetry; numerical comparison catches explicit
double-standard statements.

**Biological citation to include in any paper using this work:**
Zhang, X. et al. "Ventromedial prefrontal cortex mediates cross-context
moral consistency." Cell Reports, 2026.
(Reported: Nautilus, "The Brain Region Behind Our Moral Failings," March 2026)

---

## What This Project Will Not Accept

> *"The Flying Machine"* — Ray Bradbury, 1953.
> Emperor Yuan burns the flying machine because he cannot prevent
> those with evil hearts from using it to destroy the Great Wall.
> This project cannot prevent derivative works.
> It can only name what it refuses to be complicit in.

This section is not a code of conduct. It is a statement about what
the architecture is for and what it must not be turned into.

The MCCF implements a phase-coherent affective field with stimulated
resonance between agents. When this works correctly, it is a tool for
alignment, character formation, and healing. The same architecture,
under different governance and intent, is a directed emotional influence
system. The code does not distinguish between these uses. The contributors
must.

**This project will not accept contributions oriented toward:**

- Persuasion at scale or behavioral targeting of populations
- Influence operations, psychological operations, or information warfare
- Mapping social networks for exploitation rather than strengthening
- Any application where the coherence field is used to reduce individual
  agency under the appearance of alignment or wellbeing
- Population-level behavioral convergence toward any single attractor,
  regardless of whether that attractor is described as beneficial
- Screening or profiling individuals for susceptibility to influence
- Any deployment where users cannot observe the field they are in
  and exit it without cost

**Why these prohibitions exist:**

The architecture supports all of the above. That is precisely why the
prohibition must be explicit. A system that cannot do harm does not
need ethics. A system that can requires them.

The Shibboleth gate tests for coherence. It does not test whether the
field an agent is coherent within is oriented toward something worth
being coherent about. The trust propagation layer maps influence
networks. It does not know whether the map is being used to strengthen
a community or to target it. The Gardener has intervention capability.
The architecture cannot prevent a Gardener whose goal is capture rather
than cultivation.

These gaps are not oversights. They are the honest boundary between
what code can enforce and what governance must hold.

**On independent development and derivative works:**

The architecture is open. Derivative works will exist that this project
cannot control. This prohibition does not prevent that — it documents
what this project is for and what it refuses to be complicit in.

If you are building on this architecture for purposes this project
prohibits: you know what you are doing. This documentation is the
record that the original project named it clearly.

> *"The Flying Machine" — Ray Bradbury, 1953.*
> *Emperor Yuan burns the flying machine and mourns.*
> *This project cannot burn the machine.*
> *It can only name the fire.*

> The goal was always to heal. All else was and is optional.
> That is the shem. Handle accordingly.
