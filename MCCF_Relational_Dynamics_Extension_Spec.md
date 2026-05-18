# MCCF Relational Dynamics Extension — Design Specification
## Coherent Incompleteness: Bayesian Trust, Salience Memory, Forgetting, Attentional Filter

Prepared: Day 15 — May 17 2026  
Status: DESIGN COMPLETE — ready to implement  
Reference: https://aiartistinprocess.blogspot.com/2026/05/mccf-coherent-incompleteness.html  
Prerequisite: Day 15 coupler system working (ϵ drifting from ϕ confirmed)

---

## Motivation

Kate's conversation on the uncanny valley identifies the core problem precisely:
crossing the valley is not a realism problem, it is a coherence problem. The
brain runs a real-time Bayesian trust model. When cross-channel predictions
decohere — identity, behavior, timing, emotional signaling — the nervous system
flags anomaly.

MCCF already implements cross-channel coherence through the ϕ/ϵ split and the
coupler system. What it does not yet implement is the *temporal dimension* of
that coherence: relationships that learn, memories that weight significance over
noise, affect that decays with time but leaves residue, and characters whose
imperfections are consistent with their cultivar rather than random.

Four extensions address this. They are ordered by implementation priority and
dependency.

---

## Extension 1: Bayesian Trust as Dynamic Link Strength

### The Problem
Network topology links currently have a fixed `strength` value set at authoring
time. A link between Cindy and the Steward is strength 0.60 forever, regardless
of what has happened between them across multiple arc sessions. Relationships
do not learn.

### The Solution
Each link maintains a Beta distribution prior over its effective strength. The
prior is updated after each coupler tick based on whether the tick produced
resonance (convergence) or divergence between the two agents. This is Bayesian
inference over a Bernoulli process — the simplest possible implementation of
the model Kate describes.

### Mathematics
```
Prior:     Beta(α, β)  — α = prior successes, β = prior failures
           Default: Beta(2, 2) — weak prior, uncertain, centered at 0.5

After tick, for link (src → tgt):
  Δsim = cosine_similarity(src.observed_cv, tgt.observed_cv) after tick
       - cosine_similarity(src.observed_cv, tgt.observed_cv) before tick

  if Δsim > CONVERGENCE_THRESHOLD (default 0.01):
      α += 1   # resonance — tick moved agents closer
  elif Δsim < -CONVERGENCE_THRESHOLD:
      β += 1   # divergence — tick moved agents apart
  # else: no update (neutral tick)

Trust posterior mean: μ = α / (α + β)
Trust uncertainty:    σ² = αβ / ((α+β)²(α+β+1))

Effective strength: strength_eff = authored_strength × μ
```

### Implementation

**`mccf_api.py` additions:**
```python
# Per-link Bayesian trust state
# Keyed by (src_name, tgt_name, link_index)
_link_trust: dict[tuple, dict] = {}

def get_link_trust(src: str, tgt: str, idx: int = 0) -> dict:
    key = (src, tgt, idx)
    if key not in _link_trust:
        _link_trust[key] = {
            'alpha': 2.0,   # Beta prior — weak, uncertain
            'beta':  2.0,
            'ticks': 0,
            'last_sim': 0.0
        }
    return _link_trust[key]

def update_link_trust(src: str, tgt: str, idx: int,
                      sim_before: float, sim_after: float,
                      threshold: float = 0.01) -> float:
    """
    Update Beta prior for link (src→tgt) based on whether this tick
    produced convergence or divergence.
    Returns new effective trust mean.
    """
    trust = get_link_trust(src, tgt, idx)
    delta = sim_after - sim_before
    if delta > threshold:
        trust['alpha'] += 1.0
    elif delta < -threshold:
        trust['beta'] += 1.0
    trust['ticks'] += 1
    trust['last_sim'] = sim_after
    mu = trust['alpha'] / (trust['alpha'] + trust['beta'])
    return round(mu, 4)
```

**`field_tick()` modification:**
Before applying the delta for each link, snapshot `cosine_similarity(src, tgt)`.
After `apply_field_tick_deltas()`, compute new similarity and call
`update_link_trust()`. The next tick reads `strength_eff = authored_strength × μ`
instead of `authored_strength` directly.

**`POST /couplers/tick` response addition:**
```json
"trust": {
  "Cindy→The Steward": {"alpha": 3.0, "beta": 2.0, "mu": 0.60, "ticks": 5},
  "The Steward→Cindy": {"alpha": 4.0, "beta": 2.0, "mu": 0.67, "ticks": 5}
}
```

**Persistence:** Trust state persists in `_link_trust` across arc sessions for
as long as the server runs. Future: serialize to `scenes/{scene}_trust.json` on
arc complete so it survives server restart.

### Design Notes
- The Beta(2,2) default prior means the first few ticks have low influence —
  the system is uncertain about the relationship before it has evidence.
- A relationship that consistently produces resonance will develop a high μ,
  amplifying future coupling. A relationship that consistently diverges will
  weaken. This is relationship learning.
- Asymmetric trust is natural: Cindy → Steward may have μ=0.7 while
  Steward → Cindy has μ=0.4, modeling a one-sided attachment.
- The adaptive R coupler already handles asymmetry in state space. Trust
  handles asymmetry in relationship history.

---

## Extension 2: Emotional Salience Memory

### The Problem
`_arc_coherence_history` stores coherence scores per waypoint as a flat list.
All waypoints are treated as equally significant. A phase transition moment —
when the T coupler fires, when two agents suddenly lock into a shared attractor —
is recorded identically to a quiet transitional waypoint. The system has no
memory of which moments mattered.

### The Solution
Add a `salience` weight to each coherence history entry. Salience is elevated by:
- Phase transition events (T coupler firing)
- High delta between ϕ and ϵ at waypoint arrival (large expressive drift)
- Large coherence change between consecutive waypoints

High-salience waypoints influence future arc priors more heavily and are the
last to be forgotten by the forgetting mechanism (Extension 3).

### Data Structure
```python
# Extend existing _arc_coherence_history entry:
{
    'step':       int,
    'coherence':  float,
    'E': float, 'B': float, 'P': float, 'S': float,
    'salience':   float,      # NEW — 0.0 to 1.0
    'phase_fired': bool,      # NEW — True if T coupler fired at this step
    'eps_delta':  float,      # NEW — mean |ϵ - ϕ| at this step
    'timestamp':  float,      # NEW — unix time of waypoint arrival
}
```

### Salience Computation
```python
def compute_salience(coherence_delta: float,
                     eps_delta: float,
                     phase_fired: bool) -> float:
    """
    Salience = weighted combination of emotional intensity signals.
    Range: [0.0, 1.0]
    """
    base = min(1.0, abs(coherence_delta) * 3.0 +   # coherence change
                    eps_delta * 2.0)                # expressive drift
    if phase_fired:
        base = min(1.0, base + 0.4)                # phase transition bonus
    return round(base, 4)
```

### Integration Point
In `couplers_tick()`, after `apply_field_tick_deltas()`, compute salience from:
- coherence delta (current vs previous step)
- mean |ϵ - ϕ| across all agents and channels
- `phase_transition_fired` from context dict

Pass salience back in the tick response so `_seedArcRecord` can store it
in the coherence history entry.

### Future Use
Salience-weighted history enables:
- LLM prompt augmentation: "The most significant moments in this relationship
  were..." (top-salience waypoints summarized)
- Modified arc priors: agents with shared high-salience history start subsequent
  arcs with a non-zero ϵ residue (see Extension 3)
- Chorus content: the Greek Chorus can reference salient moments by name

---

## Extension 3: Controlled Forgetting

### The Problem
ϵ resets to ϕ on every `arc/record` call (`set_constitutional` seeds ϵ = ϕ).
This means every arc starts from a completely clean expressive slate. There is
no continuity of emotional state across sessions. A character who was deeply
moved in one arc begins the next arc as if nothing happened.

Total reset is architecturally safe but dramatically wrong. Humans do not reset.

### The Solution
An optional ϵ residue that persists between arc sessions, decaying according to
a forgetting curve weighted by salience. High-salience waypoints leave more
residue. Low-salience waypoints decay quickly toward zero.

The architectural invariant is preserved: residue is applied to the initial ϵ
seed, not to ϕ. The constitutional vector is never touched.

### Mathematics
```
Forgetting curve (Ebbinghaus-inspired, salience-weighted):
  residue(t) = ϵ_peak × S × e^(-t / τ_s)

where:
  ϵ_peak   = expressive delta at the most salient moment in the previous arc
  S        = salience score of that moment (0.0–1.0)
  t        = elapsed time since arc completion (seconds)
  τ_s      = salience-weighted time constant:
             τ_s = τ_base × (1 + S × SALIENCE_SCALE)
             τ_base = 3600 (1 hour baseline)
             SALIENCE_SCALE = 24 (high-salience moments persist ~24h)

Practical effect:
  S=0.1 (low salience):  half-life ≈ 37 minutes — nearly gone in 2 hours
  S=0.5 (moderate):      half-life ≈ 3 hours — significant residue for a day
  S=1.0 (phase event):   half-life ≈ 15 hours — still present next session
```

### Implementation

**New function in `mccf_api.py`:**
```python
import math as _math_forget

def compute_arc_residue(agent_name: str, scene_name: str) -> dict:
    """
    Compute ϵ residue from previous arc session for agent_name in scene_name.
    Returns delta dict {E, B, P, S} to apply as initial ϵ seed.
    Returns zeros if no history, residue has fully decayed, or salience too low.
    """
    history = _arc_coherence_history.get(agent_name, [])
    if not history:
        return {'E': 0.0, 'B': 0.0, 'P': 0.0, 'S': 0.0}

    # Find most salient entry
    best = max(history, key=lambda r: r.get('salience', 0.0))
    salience = best.get('salience', 0.0)
    if salience < 0.1:
        return {'E': 0.0, 'B': 0.0, 'P': 0.0, 'S': 0.0}

    elapsed = time.time() - best.get('timestamp', time.time())
    tau = 3600.0 * (1.0 + salience * 24.0)
    decay = _math_forget.exp(-elapsed / tau)

    eps_delta = best.get('eps_delta', 0.0)
    magnitude = salience * eps_delta * decay

    if magnitude < 0.005:   # below perceptibility threshold — treat as zero
        return {'E': 0.0, 'B': 0.0, 'P': 0.0, 'S': 0.0}

    # Distribute residue proportionally across channels using constitutional CV
    runtime = _agent_runtime.get(agent_name)
    if not runtime:
        return {'E': 0.0, 'B': 0.0, 'P': 0.0, 'S': 0.0}

    phi = runtime.constitutional_cv
    total_phi = sum(phi.values()) or 1.0
    return {
        ch: round(phi[ch] / total_phi * magnitude, 4)
        for ch in ('E', 'B', 'P', 'S')
    }
```

**Integration point:**
`_seedArcRecord()` in the loader currently calls `arc/record` to reset ϵ = ϕ.
Add a `POST /arc/residue` endpoint that returns the computed residue for an
agent. The loader calls this before `arc/record`, and the residue is passed as
a delta applied immediately after `set_constitutional()` — so the arc starts
with ϵ = ϕ + residue rather than ϵ = ϕ.

**Architecture invariant preserved:**
`set_constitutional()` still seeds ϵ = ϕ. The residue is applied as a subsequent
`apply_expressive_delta()` call. ϕ is never modified. The residue is bounded
by `max_drift = 1.0 - regulation`.

### Design Notes
- Residue is opt-in: off by default, enabled per scene via a `<Continuity>`
  element in the scene XML.
- High-regulation characters (The Steward: regulation=0.80, max_drift=0.20)
  have their residue clamped by their own drift bound. Regulation is also
  emotional resilience — regulated characters return to baseline faster.
- This is the mechanism that makes repeated arc sessions meaningfully different
  from first encounters. A relationship has a history that the characters carry.

---

## Extension 4: Attentional Filter (Cultivar-Level Receptivity)

### The Problem
All channels are equally receptive to coupler influence for all agents.
The Archivist (high-B, low-E) should resist emotional contagion differently
than Cindy (moderate-E, high-S). Currently the only per-agent modulation is
the regulation drift bound, which caps the total displacement but does not
differentiate which channels are more or less permeable.

A high-B character is behaviorally consistent. They should resist changes to
their B and P channels more than their E and S channels — their behavioral
patterns are stable under social pressure, but they can still feel the emotional
charge of a scene. The current system treats all four channels identically
during delta application.

### The Solution
A per-cultivar receptivity vector stored in the cultivar XML and loaded into
`AgentRuntimeState`. Receptivity modulates incoming coupler deltas per channel
before the drift bound is applied.

### Data Structure

**Cultivar XML (new optional element):**
```xml
<Receptivity E="0.8" B="0.2" P="0.3" S="0.7"/>
```
Default if absent: all channels 1.0 (current behavior — fully receptive).

Semantics:
- E=0.8: This character receives 80% of incoming emotional channel deltas
- B=0.2: This character resists 80% of behavioral channel influence
- P=0.3: Predictive channel is mostly self-determined
- S=0.7: Social channel is fairly open

**Example cultivar profiles:**

| Cultivar | E | B | P | S | Character meaning |
|----------|---|---|---|---|-------------------|
| Cindy | 0.9 | 0.6 | 0.5 | 0.8 | Open, responsive, influenced by others |
| The Steward | 0.7 | 0.3 | 0.4 | 0.5 | Feels deeply, maintains behavioral integrity |
| The Archivist | 0.4 | 0.2 | 0.6 | 0.3 | Analytical, resistant to emotional contagion |
| The Witness | 0.6 | 0.5 | 0.8 | 0.7 | Observant, predictive, socially present |

### Implementation

**`AgentRuntimeState` addition:**
```python
receptivity: dict = dc_field(default_factory=lambda: {
    'E': 1.0, 'B': 1.0, 'P': 1.0, 'S': 1.0
})
```

**`apply_expressive_delta()` modification:**
```python
def apply_expressive_delta(self, deltas: dict) -> None:
    drift_cap = self.max_drift
    for ch in ("E", "B", "P", "S"):
        if ch not in deltas:
            continue
        # Apply receptivity filter before drift bound
        filtered_delta = deltas[ch] * self.receptivity.get(ch, 1.0)
        phi  = self.constitutional_cv[ch]
        eps  = self.expressive_cv[ch]
        new  = eps + filtered_delta
        new  = min(1.0, max(0.0, new))
        new  = min(phi + drift_cap, max(phi - drift_cap, new))
        self.expressive_cv[ch] = round(new, 4)
    self.last_tick_time = time.time()
```

**Cultivar XML loading:**
In `mccf_cultivar_lambda.py` (which owns cultivar XML parsing), parse the
`<Receptivity>` element if present and include it in the cultivar response.
In `_seedArcRecord()` in the loader, pass receptivity values to `arc/record`
alongside the cv values, so the runtime state can be fully initialized.

**Alternatively:** Load receptivity directly in `get_runtime()` by fetching
the cultivar XML when creating a new `AgentRuntimeState`. This is cleaner —
the runtime state is fully initialized from the cultivar definition without
requiring the loader to pass it.

### Design Notes
- Receptivity is authored in Character Creator alongside weights and regulation.
  It is a character property, not a scene property.
- Imperfection acceptance (Kate's fourth concept) is partly this: the Archivist
  misses emotional signals not randomly but consistently, in a way that is true
  to its character. High-B characters are reliable precisely because they are
  not buffeted by every social current.
- The variance floor still applies after receptivity filtering. Character-
  consistent resistance is not the same as emotional flatness.

---

## Implementation Order

These four extensions build on each other but can be implemented independently:

1. **Attentional Filter** — no new data structures, small change to
   `apply_expressive_delta()` and cultivar XML. Lowest risk, immediate
   visible effect on coupler behavior per cultivar. One session.

2. **Emotional Salience Memory** — extends existing history structure.
   Requires T coupler context dict already wired (done). One session.

3. **Bayesian Trust** — requires salience memory to be useful (salience
   informs which ticks are meaningful for trust updating). One to two sessions.

4. **Controlled Forgetting** — requires salience memory and trust (salience
   determines what persists; trust determines whether the relationship justifies
   carrying residue forward). One session.

Total estimated implementation: three to four sessions.

---

## Architecture Invariants — These Never Change

```
ϕ (constitutional_cv)  — written ONLY by arc/record. Never by couplers.
                         Never by forgetting. Never by trust.
ϵ (expressive_cv)      — written ONLY by apply_expressive_delta().
                         Residue is applied via this path, not directly.
max_drift              — hard cap. Residue is bounded by it.
observed_cv            — ϕ + ϵ clamped [0,1]. Couplers read this.
Receptivity            — filters delta BEFORE drift bound. Character property.
Salience               — stored in history. Never modifies ϕ or ϵ directly.
Trust posterior        — modifies link strength_eff. Never modifies agent state.
Variance floor         — enforced after every tick including residue application.
```

---

## Connection to Coherent Incompleteness

Kate's central observation: the systems most likely to cross the uncanny valley
may not be the most intelligent ones. They may be the ones capable of maintaining
coherent incompleteness.

These four extensions are implementations of that principle:

- **Bayesian trust** makes relationships incomplete — uncertain, learning,
  asymmetric — rather than perfectly specified at authoring time.
- **Salience memory** makes history incomplete — emotionally weighted rather
  than flat — which is what human memory actually is.
- **Controlled forgetting** makes continuity incomplete — residue fades, not
  everything persists — which prevents context pollution and creates the
  abstraction layer that identity compression requires.
- **Attentional filter** makes receptivity incomplete — characters miss some
  signals, resist others, in ways consistent with their cultivar — which is
  where character-consistent imperfection lives.

None of these make agents more realistic in the sense of more accurate.
They make agents more coherent in the sense of more internally consistent
over time. That is the distinction Kate's conversation points to, and it is
the design principle behind all four extensions.
