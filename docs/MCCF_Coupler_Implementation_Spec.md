# MCCF Coupler System — Implementation Specification
# Status: READY TO IMPLEMENT when prerequisites met
# Prepared: Day 12 — May 15 2026
# Based on: original coupler design (May 2026) + Kate/Goldstone review (Day 12)

---

## Prerequisites — Gates Before Implementation Begins

All three must be complete before coupler code is written.

### Gate 1: Constitutional/Expressive State Split
**Estimated effort:** Small — one session
Add `expressive_cv` as a runtime field separate from the cultivar's constitutional
`weights`. Couplers write to `expressive_cv` only. Constitutional weights are frozen
at load and never modified by runtime dynamics.

### Gate 2: Second Agent Moving in Test Scene
**Estimated effort:** One session (follower pattern, already in deferred list)
Couplers are agent-to-agent interactions. A single-agent scene is a degenerate test
case where nothing interesting can happen. Need at least two agents on independent
or semi-independent paths before coupler behavior is observable.

### Gate 3: Network Topology in Scene XML and Composer
**Estimated effort:** One session
`<Network><Link>` schema must be in the scene XML and authorable in Scene Composer
before the field tick loop can traverse the coupling graph.

---

## Part 1: Constitutional / Expressive State Split

### The Principle (from Kate's Goldstone review)

```
ψᵢ(t) = ϕᵢ + ϵᵢ(t)
```

- `ϕᵢ` — constitutional manifold: the cultivar's authored E/B/P/S weights.
  Frozen at load. Never written by couplers. Represents stable character identity.
- `ϵᵢ(t)` — expressive fluctuation: runtime emotional state. Written by couplers,
  zone pressure, waypoint attraction. Represents current emotional moment.

The actual observable state is `ϕᵢ + ϵᵢ(t)` clamped to [0,1].
The LLM prompt gets both: `ϕᵢ` as character identity, `ϕᵢ + ϵᵢ(t)` as current state.

### Code Changes Required

**`mccf_cultivar_lambda.py` — No changes.**
`CultivarDefinition.weights` remains the constitutional vector. It is the `ϕᵢ`.

**`mccf_api.py` — Runtime agent state extension.**

Add to the runtime agent state object (wherever active agents are tracked):

```python
@dataclass
class AgentRuntimeState:
    name: str
    constitutional_cv: dict   # ϕᵢ — frozen from CultivarDefinition.weights at load
                               # {'E': float, 'B': float, 'P': float, 'S': float}
    expressive_cv: dict        # ϵᵢ(t) — live, coupler-modified, starts at zeros
                               # {'E': 0.0, 'B': 0.0, 'P': 0.0, 'S': 0.0}
    regulation: float          # from cultivar — bounds ϵ drift
    position: list             # [x, y, z] — current scene position
    zone_id: str               # current zone (proximity-determined)
    arc_id: str                # arc being played, or ''

    @property
    def observed_cv(self) -> dict:
        """ϕᵢ + ϵᵢ(t), clamped to [0,1]"""
        return {
            k: max(0.0, min(1.0, self.constitutional_cv[k] + self.expressive_cv[k]))
            for k in ('E', 'B', 'P', 'S')
        }
```

**Initialization at arc load:**
```python
def load_agent(cultivar: CultivarDefinition) -> AgentRuntimeState:
    return AgentRuntimeState(
        name=cultivar.name,
        constitutional_cv=dict(cultivar.weights),  # frozen copy
        expressive_cv={'E': 0.0, 'B': 0.0, 'P': 0.0, 'S': 0.0},
        regulation=cultivar.regulation,
        position=[0, 0, 0],
        zone_id='',
        arc_id=''
    )
```

**Regulation as drift bound:**
The regulation value `R ∈ [0,1]` bounds how far `ϵᵢ` can drift from zero:
```python
MAX_EXPRESSIVE_DRIFT = 1.0 - agent.regulation  # high regulation → small ϵ range
```
A fully regulated agent (R=1.0) has `ϵ` locked to zero — pure constitutional state.
A fully reactive agent (R=0.0) can drift the full ±1.0 range.

---

## Part 2: Scene XML Schema Extension — Network Topology

### Zone Schema — Add Coupler Block

```xml
<Zone id="temple" zone_type="temple">
  <Descriptor>Ancient ceremonial space, charged with memory</Descriptor>
  <Weights E="0.25" B="0.25" P="0.25" S="0.25"/>
  <Position x="21.9" y="0" z="17.4"/>
  <Radius value="4"/>
  <AmbientTheme scale="major" tempo="medium"/>

  <!-- Optional coupler block — how this zone influences agents within radius -->
  <Couplers>
    <Resonance gain="0.5" filter="E"/>      <!-- amplify emotional expressiveness -->
    <Damping gain="0.3" filter="B"/>         <!-- resist behavioral disruption -->
  </Couplers>
</Zone>
```

### Agent Placement Schema — Add Coupler Block

```xml
<!-- In scene XML, agent placement block -->
<AgentPlacement name="Cindy" x="10.0" y="0" z="8.0">
  <Couplers>
    <Resonance gain="0.6" filter="E,S"/>
    <Damping gain="0.4"/>
    <Gated threshold="S>0.5"/>
    <Threshold trigger="E>0.7" gain="1.2"/>
    <Delay lag="2"/>
    <Integration rate="0.1"/>
  </Couplers>
</AgentPlacement>
```

### Network Topology — New Top-Level Block in Scene XML

```xml
<!-- Add to scene XML after <Zones> block, before <Agents> -->
<Network>
  <!-- Agent-to-agent directional links -->
  <Link from="Cindy" to="The Steward" couplers="R,D" strength="0.6"/>
  <Link from="The Steward" to="Cindy" couplers="R,I" strength="0.4"/>

  <!-- Zone-to-agent links (supplement proximity radius system) -->
  <Link from="zone:temple" to="Cindy" couplers="R,D" strength="0.5"/>
</Network>
```

**Notes:**
- Links are directional: `from` influences `to`
- `strength` is a global scale on all couplers in the link (0.0–1.0)
- Zone links use `zone:id` prefix to distinguish from agent names
- Absence of `<Network>` block = no explicit coupling (zone proximity still active)

---

## Part 3: The Seven Couplers — Implementation

### Coupler Function Signatures

All coupler functions take the source state, target state, and parameters.
They return a delta to apply to `ϵᵢ` of the target agent.

```python
# mccf_couplers.py (new module)

from dataclasses import dataclass
from typing import Optional
import math

CHANNELS = ('E', 'B', 'P', 'S')

def apply_coupler(
    coupler_type: str,
    source_cv: dict,      # observed_cv of source agent or zone
    target_state: 'AgentRuntimeState',
    params: dict,
    context: dict         # {'timestep': int, 'zone_id': str, ...}
) -> dict:
    """
    Returns delta dict {'E': float, 'B': float, 'P': float, 'S': float}
    to add to target.expressive_cv.
    """
    fn = COUPLER_REGISTRY.get(coupler_type)
    if fn is None:
        raise ValueError(f"Unknown coupler type: {coupler_type}")
    return fn(source_cv, target_state, params, context)
```

### R — Resonance

Align and amplify shared dimensions. The workhorse of synchronization.
Implements adaptive coupling strength from Kate's recommendation.

```python
def coupler_resonance(source_cv, target_state, params, context):
    gain = float(params.get('gain', 0.5))
    filt = _parse_filter(params.get('filter', 'E,B,P,S'))
    lam  = float(params.get('lambda', 1.0))  # asymmetry sensitivity

    # Adaptive coupling: weaker when states are asymmetric
    # R_effective = R · e^(-λ · H_sym)
    h_sym = _asymmetry(source_cv, target_state.observed_cv, filt)
    r_eff = gain * math.exp(-lam * h_sym)

    delta = {}
    target_obs = target_state.observed_cv
    for ch in CHANNELS:
        if ch in filt:
            # Move target toward source
            delta[ch] = r_eff * (source_cv[ch] - target_obs[ch])
        else:
            delta[ch] = 0.0
    return delta

def _asymmetry(cv_a: dict, cv_b: dict, channels) -> float:
    """H_sym: normalized distance between two channel vectors."""
    diffs = [(cv_a[ch] - cv_b[ch])**2 for ch in channels]
    return math.sqrt(sum(diffs) / len(diffs))  # 0=identical, 1=maximally different
```

### D — Damping

Reduce intensity, absorb perturbations. Stabilizer.

```python
def coupler_damping(source_cv, target_state, params, context):
    gain = float(params.get('gain', 0.4))
    filt = _parse_filter(params.get('filter', 'E,B,P,S'))
    delta = {}
    for ch in CHANNELS:
        if ch in filt:
            # Pull expressive component toward zero (toward constitutional)
            delta[ch] = -gain * target_state.expressive_cv[ch]
        else:
            delta[ch] = 0.0
    return delta
```

### I — Inversion

Reflect across dimension. Conflict, counterbalance.

```python
def coupler_inversion(source_cv, target_state, params, context):
    gain = float(params.get('gain', 0.3))
    filt = _parse_filter(params.get('filter', 'E,B,P,S'))
    delta = {}
    target_obs = target_state.observed_cv
    for ch in CHANNELS:
        if ch in filt:
            # Move away from source
            delta[ch] = gain * (target_obs[ch] - source_cv[ch])
        else:
            delta[ch] = 0.0
    return delta
```

### G — Gated

Conditional activation. Only couples when condition is met.

```python
def coupler_gated(source_cv, target_state, params, context):
    condition = params.get('threshold', 'S>0.5')
    inner_type = params.get('inner', 'R')      # which coupler fires when gate opens
    inner_params = params.get('inner_params', {'gain': 0.5})

    if _eval_condition(condition, target_state.observed_cv):
        return apply_coupler(inner_type, source_cv, target_state, inner_params, context)
    return {ch: 0.0 for ch in CHANNELS}

def _eval_condition(condition: str, cv: dict) -> bool:
    """Parse simple 'CHANNEL op VALUE' condition. E.g. 'S>0.5', 'E<0.3'"""
    import operator as op
    ops = {'>': op.gt, '<': op.lt, '>=': op.ge, '<=': op.le, '==': op.eq}
    for sym, fn in ops.items():
        if sym in condition:
            ch, val = condition.split(sym)
            return fn(cv.get(ch.strip(), 0.0), float(val.strip()))
    return False
```

### T — Threshold

Nonlinear — amplify above threshold. Phase transition trigger.
After firing, sets a flag consumed by the minimum variance floor enforcement.

```python
def coupler_threshold(source_cv, target_state, params, context):
    trigger = params.get('trigger', 'E>0.7')
    gain    = float(params.get('gain', 1.2))
    filt    = _parse_filter(params.get('filter', 'E,B,P,S'))

    if not _eval_condition(trigger, source_cv):
        return {ch: 0.0 for ch in CHANNELS}

    # Threshold fired — amplify. Also flag phase transition.
    context['phase_transition_fired'] = True

    delta = {}
    for ch in CHANNELS:
        if ch in filt:
            delta[ch] = gain * source_cv[ch]
        else:
            delta[ch] = 0.0
    return delta
```

### L — Delay

Time-shifted response. Resentment, lag, oscillation.

```python
def coupler_delay(source_cv, target_state, params, context):
    lag     = int(params.get('lag', 2))     # timesteps
    gain    = float(params.get('gain', 0.5))
    filt    = _parse_filter(params.get('filter', 'E,B,P,S'))

    # Read from history buffer at lag offset
    history = context.get('source_history', [])
    if len(history) < lag:
        return {ch: 0.0 for ch in CHANNELS}

    past_cv = history[-lag]
    delta = {}
    target_obs = target_state.observed_cv
    for ch in CHANNELS:
        if ch in filt:
            delta[ch] = gain * (past_cv[ch] - target_obs[ch])
        else:
            delta[ch] = 0.0
    return delta
```

### ∫ — Integration

Accumulate over time. Bonding, trauma, habituation, baseline drift.

```python
def coupler_integration(source_cv, target_state, params, context):
    rate = float(params.get('rate', 0.05))
    filt = _parse_filter(params.get('filter', 'E,B,P,S')))
    delta = {}
    target_obs = target_state.observed_cv
    for ch in CHANNELS:
        if ch in filt:
            # Slow drift toward source state
            delta[ch] = rate * (source_cv[ch] - target_obs[ch])
        else:
            delta[ch] = 0.0
    return delta
```

### Coupler Registry

```python
COUPLER_REGISTRY = {
    'R': coupler_resonance,
    'D': coupler_damping,
    'I': coupler_inversion,
    'G': coupler_gated,
    'T': coupler_threshold,
    'L': coupler_delay,
    'Int': coupler_integration,   # ∫ — 'Int' as XML-safe name
}

def _parse_filter(filter_str: str) -> set:
    return set(c.strip() for c in filter_str.split(',') if c.strip() in CHANNELS)
```

---

## Part 4: The Field Tick — Update Equation

### Where It Lives: `mccf_api.py`

A new function `field_tick()` runs at each arc waypoint arrival (reactive tick,
tied to existing playback event flow). Later: promote to independent timer if needed.

```python
# mccf_api.py addition

def field_tick(
    agents: dict,          # {name: AgentRuntimeState}
    network: list,         # parsed <Network><Link> entries
    zones: list,           # parsed zone elements with Couplers
    timestep: int,
    history: dict          # {agent_name: deque of past observed_cv}
) -> dict:
    """
    One tick of the coupler update loop.
    Returns dict of deltas: {agent_name: {'E': float, ...}}
    Does NOT apply deltas — caller applies after all are computed (synchronous update).
    """
    from mccf_couplers import apply_coupler
    from collections import defaultdict

    deltas = defaultdict(lambda: {'E': 0.0, 'B': 0.0, 'P': 0.0, 'S': 0.0})
    context = {'timestep': timestep}

    # --- Agent-to-agent links ---
    for link in network:
        src_name = link['from']
        tgt_name = link['to']
        if src_name not in agents or tgt_name not in agents:
            continue
        src = agents[src_name]
        tgt = agents[tgt_name]
        strength = float(link.get('strength', 1.0))
        ctx = {**context, 'source_history': list(history.get(src_name, []))}

        for coupler_type in link.get('couplers', []):
            params = link.get('coupler_params', {}).get(coupler_type, {})
            delta = apply_coupler(coupler_type, src.observed_cv, tgt, params, ctx)
            for ch in ('E', 'B', 'P', 'S'):
                deltas[tgt_name][ch] += delta[ch] * strength

    # --- Zone-to-agent links (proximity-based) ---
    for zone in zones:
        zone_couplers = _parse_zone_couplers(zone)
        if not zone_couplers:
            continue
        zone_cv = _zone_cv(zone)
        zone_pos = _zone_position(zone)
        zone_radius = _zone_radius(zone)

        for name, agent in agents.items():
            if _in_radius(agent.position, zone_pos, zone_radius):
                for coupler_type, params in zone_couplers:
                    delta = apply_coupler(coupler_type, zone_cv, agent, params, context)
                    for ch in ('E', 'B', 'P', 'S'):
                        deltas[name][ch] += delta[ch]

    return dict(deltas)


def apply_field_tick_deltas(agents, deltas, variance_floor=0.02):
    """
    Apply computed deltas to agent expressive_cv.
    Enforces:
      - regulation drift bound
      - minimum variance floor (Kate: preserve local fluctuation after phase transition)
      - clamp to valid range
    """
    for name, agent in agents.items():
        if name not in deltas:
            continue
        max_drift = 1.0 - agent.regulation
        d = deltas[name]
        for ch in ('E', 'B', 'P', 'S'):
            new_val = agent.expressive_cv[ch] + d[ch]
            # Regulation bound
            new_val = max(-max_drift, min(max_drift, new_val))
            agent.expressive_cv[ch] = new_val

        # Minimum variance floor — after synchronization some fluctuation must survive
        # Prevents emotional monoculture / frozen lock
        _enforce_variance_floor(agent, variance_floor)

        # Update history
        # (caller maintains history deque)


def _enforce_variance_floor(agent, floor):
    """
    Kate's Goldstone constraint: perfect synchronization is forbidden.
    After strong coupling, ensure expressive_cv retains minimum variance
    relative to constitutional_cv.
    """
    obs = agent.observed_cv
    mean = sum(obs.values()) / 4.0
    variance = sum((v - mean)**2 for v in obs.values()) / 4.0
    if variance < floor:
        # Nudge expressive_cv slightly away from uniform
        for ch in ('E', 'B', 'P', 'S'):
            noise = (agent.constitutional_cv[ch] - mean) * floor
            agent.expressive_cv[ch] += noise
```

---

## Part 5: Phase Transition Detection

Monitor the coherence matrix (relational state), not individual channel dominance.
Per Kate: broken symmetry = relational attractor selection, not axis dominance.

```python
# mccf_api.py addition

def detect_phase_transition(agents: dict, threshold: float = 0.85) -> dict:
    """
    Monitor relational state for synchronization events.
    Returns {'transition': bool, 'type': str, 'agents': list}

    Transition fires when mean pairwise similarity exceeds threshold —
    agents have locked into a shared attractor.
    """
    names = list(agents.keys())
    if len(names) < 2:
        return {'transition': False}

    similarities = []
    for i, n1 in enumerate(names):
        for n2 in names[i+1:]:
            sim = _cosine_similarity(
                agents[n1].observed_cv,
                agents[n2].observed_cv
            )
            similarities.append(sim)

    mean_sim = sum(similarities) / len(similarities)

    if mean_sim >= threshold:
        return {
            'transition': True,
            'type': 'synchronization',
            'mean_similarity': mean_sim,
            'agents': names
        }
    return {'transition': False, 'mean_similarity': mean_sim}


def _cosine_similarity(cv_a: dict, cv_b: dict) -> float:
    a = [cv_a[ch] for ch in ('E', 'B', 'P', 'S')]
    b = [cv_b[ch] for ch in ('E', 'B', 'P', 'S')]
    dot = sum(x*y for x,y in zip(a,b))
    mag_a = math.sqrt(sum(x**2 for x in a))
    mag_b = math.sqrt(sum(x**2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)
```

---

## Part 6: Coherence Waves (Deferred)

Design only — implement after network topology is wired and basic coupler loop working.

**Principle:** Coupler effects propagate through the `<Network>` topology with
distance-based delay rather than applying instantly to all linked agents.
Close agents feel the effect first; distant agents feel it later.

**Implementation sketch (future):**

```python
# Each Link gets a propagation_delay based on graph distance
# field_tick queues deltas with timestep offsets
# apply_field_tick_deltas checks timestep before applying

@dataclass
class PendingDelta:
    target_name: str
    delta: dict
    apply_at_timestep: int

pending_queue: list[PendingDelta] = []

# In field_tick: instead of direct delta, enqueue:
delay = _graph_distance(src_name, tgt_name, network) * PROPAGATION_SPEED
pending_queue.append(PendingDelta(tgt_name, delta, timestep + delay))

# In apply loop: only apply deltas where apply_at_timestep <= current_timestep
```

---

## Part 7: Dashboard Design Question

**Open question — decide after first coupler data is flowing.**

Current dashboard shows: coherence, echo risk, episodes, agents count, tension.
These are field-level aggregates. Coupler state adds per-agent, per-link data.

**Option A — Augment existing dashboard:**
Add a coupler state panel: active links, current R_effective per link,
phase transition indicator, constitutional vs expressive divergence per agent.
Simple. May get crowded.

**Option B — Separate coupler monitor view:**
A dedicated panel or tab showing the coupling network graph with live
link strength visualization, per-agent ϕ vs ϵ bars, phase state indicator.
More work but dramatically better for debugging and authoring.

**Option C — In-scene visualization:**
Render coupling links as visible geometry in the X3D scene (colored lines between
agents, thickness = link strength, color = coupler type). Audience-invisible (toggle).
Powerful for the author during scene design and debugging.

**Recommendation:** Design for Option B/C as target, ship Option A first.
The in-scene visualization (Option C) would be the killer authoring tool —
watching the emotional field propagate through the scene in real time while
the arc plays. Defer to after couplers are working and stable.

---

## Part 8: Module Ownership (Never Change)

| Concern | Module |
|---------|--------|
| Coupler function implementations | `mccf_couplers.py` (new) |
| `AgentRuntimeState` dataclass | `mccf_api.py` |
| `field_tick()` and `apply_field_tick_deltas()` | `mccf_api.py` |
| `detect_phase_transition()` | `mccf_api.py` |
| Network topology parsing from scene XML | `mccf_api.py` |
| Zone coupler parsing | `mccf_api.py` |
| Coupler schema in scene XML | scene XML + scene composer |
| `<Network><Link>` authoring UI | `mccf_scene_composer.html` |
| Dashboard coupler display (when built) | `mccf_x3d_loader.html` |
| `mccf_couplers.py` owns all coupler math | NOT duplicated in `mccf_api.py` |

---

## Part 9: Implementation Sequence (When Prerequisites Met)

1. **`mccf_couplers.py`** — write all seven coupler functions + registry
2. **`mccf_api.py`** — add `AgentRuntimeState`, `field_tick()`,
   `apply_field_tick_deltas()`, `detect_phase_transition()`
3. **Scene XML schema** — add `<Couplers>` to Zone and AgentPlacement,
   add `<Network><Link>` block
4. **`mccf_scene_composer.html`** — add Network link authoring UI
   (basic: dropdown from→to, coupler type checkboxes, strength slider)
5. **Wire `field_tick()` to arc playback** — call at each waypoint arrival
6. **Test with two-agent scene** — verify R coupler produces observable
   expressive_cv convergence without constitutional_cv modification
7. **Test phase transition detector** — verify it fires on high-R synchronization
8. **Test variance floor** — verify agents don't lock perfectly after T fires
9. **Add coupler state to API response** — so dashboard can display it
10. **Dashboard Option A** — add coupler panel to existing loader dashboard
11. **Coherence waves** — deferred until steps 1–10 stable

---

## Part 10: Test Scenarios (Two-Agent Minimum)

| Scenario | Setup | Expected Behavior |
|----------|-------|-------------------|
| Empathy | Cindy + Steward, high R both directions | E channels converge, constitutional unchanged |
| Authority | Steward → Cindy high D, Cindy → Steward low D | Cindy's ϵ dampened, Steward unaffected |
| Defiance | Cindy → Steward Inversion on E | Cindy's E moves opposite to Steward's |
| Slow bonding | Both agents, ∫ integration, long arc | Baseline drift toward each other over waypoints |
| Panic cascade | High R + T trigger on E>0.7 | Both agents spike, variance floor prevents total lock |
| Asymmetric obsession | Cindy → Steward R=0.8, Steward → Cindy R=0.1 | High H_sym → adaptive R weakens Cindy's influence |

---

## Key Constraints — Coupler System (Never Change)

- `mccf_couplers.py` owns all coupler math — not duplicated in `mccf_api.py`
- Couplers write to `expressive_cv` (ϵ) only — never to `constitutional_cv` (ϕ)
- Constitutional vector E/B/P/S is never replaced or extended — constitutional
- Regulation value bounds maximum expressive drift: `max_drift = 1.0 - regulation`
- Minimum variance floor enforced after every tick — perfect synchronization forbidden
- Phase transition detection monitors relational state (cosine similarity matrix)
  not individual channel dominance
- Adaptive R: `R_effective = R · e^(-λ · H_sym)` — asymmetric bonds are unstable
- `field_tick()` computes ALL deltas before applying ANY — synchronous update,
  no agent processed before another (prevents order dependency artifacts)
- Coherence waves deferred — do not implement until basic coupler loop is stable
- No explicit Goldstone entities, boson propagation objects, or quantum runtime
  metaphors in implementation code
