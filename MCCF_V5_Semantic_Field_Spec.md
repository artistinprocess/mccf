# MCCF V5 — Semantic Field Physics Specification

**Coupled Stochastic Hamiltonian Field Theory over Semantic Attractors**

> \\\*\\\*Origin:\\\*\\\* Santa Fe Institute conformity model (Kaleda Denton et al.) mapped to MCCF architecture by Kate (aiartistinprocess.blogspot.com), June 19 2026.  
> \\\*\\\*Status:\\\*\\\* Math complete through V5. Integration deferred to Day 51. Do not disrupt Day 50 plan.  
> \\\*\\\*Architecture class:\\\*\\\* Path-dependent coupled Hamiltonian field with emergent topological phase transitions in a learned semantic manifold.

\---

## 1\. The Core Insight from Santa Fe

Traditional conformity models assume agents drift toward the population mean. Real societies don't — they polarize, cluster, and maintain stable subgroups. The SFI work shows why: conformity is not averaging. It is falling into attractor basins formed by local density peaks in a non-convex landscape.

> \\\*\\\*Key shift:\\\*\\\* Society doesn't converge toward an average — it organizes into attractors in cultural space. Zones are not destinations. They are records of movement becoming structure.

MCCF's existing architecture — SemanticZones as attractor regions, MetaState vectors as agent positions, Hamiltonian energy governing transitions — is already the correct model class. The SFI math provides the formal physics that fills in what was implicit.

\---

## 2\. Vocabulary Mapping

|Santa Fe Model|MCCF Equivalent|Notes|
|-|-|-|
|Trait space|MetaState manifold (E,B,P,S)|n-dimensional phase space per agent|
|Conformity|Energy gradient descent|Fall into density-weighted Gaussian wells|
|Clusters|SemanticZones|Persistent low-energy attractors|
|Polarization|Multiple attractor basins|Zone splitting via entropy bifurcation|
|Anti-conformity|Entropy / repulsive field|Prevents collapse to single cluster|
|Social influence|Field coupling term J\_zz'|Elastic pressure between zone centers|
|Mean convergence|**NOT present**|Replaced by non-convex attractor dynamics|

\---

## 3\. Formal Specification

### 3.1 State Definitions

**Agent MetaState**

Each agent `i` carries a MetaState vector in the four-channel MCCF phase space:

```
x\\\_i = (E\\\_i, B\\\_i, P\\\_i, S\\\_i)   \\\[Emotional, Behavioral, Predictive, Social]
```

Agents also carry a memory buffer and compressed embedding:

```
memory\\\_i = {x\\\_i^(t-k), ..., x\\\_i^(t)}   (fading exponential trace, depth = memory\\\_dim)
M\\\_i = sum\\\_k \\\[ decay^k \\\* x\\\_i^(t-k) ]    (normalized exponential embedding)
```

**Zone State**

Each SemanticZone `z` carries:

* `mu\\\_z` — drifting center in MetaState space
* `Sigma\\\_z` — covariance / spread tensor
* `rho\\\_z` — density / gravitational depth (reinforced by occupancy)
* `flow\\\_z` — mean directional current (exponential trace of agent velocities)
* `flow\\\_cov\\\_z` — covariance of directional flow (dispersion of traversal directions)

\---

### 3.2 Field Energy Function

Total energy experienced by agent `i` in the field:

```
E(x\\\_i) = sum\\\_z \\\[ rho\\\_z \\\* phi(x\\\_i, mu\\\_z) ]   -   lambda \\\* H(x\\\_i)   +   gamma \\\* grad(rho)(x\\\_i)
          \\\\\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_/       \\\\\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_/       \\\\\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_\\\_/
                conformity / attraction           anti-conformity         density pressure
```

#### Attraction Term (Santa Fe conformity)

```
phi(x\\\_i, mu\\\_z) = (x\\\_i - mu\\\_z)^T  Sigma\\\_z^{-1}  (x\\\_i - mu\\\_z)
```

Zones act as Gaussian energy wells. Closer to a dense cluster = lower energy. Density reinforces depth.

#### Entropy Term (anti-conformity / novelty drive)

Soft assignment probability (softmax over zones):

```
P\\\_z(x) = \\\[ exp(-beta \\\* E\\\_z(x)) \\\* rho\\\_z ]  /  sum\\\_k \\\[ exp(-beta \\\* E\\\_k(x)) \\\* rho\\\_k ]

H(x) = - sum\\\_z  P\\\_z(x) \\\* log P\\\_z(x)
```

Analytic gradient (fully differentiable — no finite differences):

```
grad H(x) = - sum\\\_z  (grad P\\\_z) \\\* (log P\\\_z + 1)

grad P\\\_z  = P\\\_z \\\* beta \\\* ( sum\\\_k \\\[P\\\_k \\\* grad E\\\_k]  -  grad E\\\_z )
```

#### Zone Coupling Kernel (field interaction)

```
J(z, z') = exp( -||mu\\\_z - mu\\\_z'||^2 / sigma^2 )
```

Coupled zone effective energy (elastic pressure between zone centers):

```
E\\\_z^{eff} = E\\\_z + alpha \\\* sum\\\_{z' != z} \\\[ J(z,z') \\\* (mu\\\_z - mu\\\_z') ]
```

This turns the zone set from independent attractors into a deformable elastic manifold. Boundaries become soft deformation fields, not hard partitions.

#### Flow Bias Term (anisotropic current field — V5)

```
E\\\_z(x) = (x - mu\\\_z)^T Sigma\\\_z^{-1} (x - mu\\\_z)   -   kappa\\\_flow \\\* dot(flow\\\_z, x - mu\\\_z)
```

Zones traversed in a consistent direction create a directional groove. New agents feel a current biasing them along the historical path of motion through that zone.

#### Memory-Modulated Effective State (V3)

Agent perception of zones is warped by trajectory history:

```
x\\\_eff = x\\\_i + kappa \\\* M\\\_i
```

All zone energy evaluations use `x\\\_eff`. Two agents at the same MetaState position perceive zones differently if their histories differ.

\---

### 3.3 Analytic Agent Gradient (no finite differences)

**Attraction gradient:**

```
grad E\\\_att = 2 \\\* sum\\\_z \\\[ rho\\\_z \\\* Sigma\\\_z^{-1} \\\* (x - mu\\\_z) ]
```

**Full gradient:**

```
grad E = grad E\\\_att   -   lambda \\\* grad H(x)
```

**Agent dynamics (stochastic Hamiltonian flow):**

```
x\\\_i^{t+1} = x\\\_i^t   -   eta \\\* grad E(x\\\_i^t)   +   xi\\\_t

xi\\\_t \\\~ N(0, T)   \\\[exploration noise / temperature]
```

\---

### 3.4 Zone Update Rules

**Mean drift (conformity-driven):**

```
mu\\\_z^{t+1} = mu\\\_z^t + alpha \\\* (1/N\\\_z) \\\* sum\\\_{i in z} (x\\\_i - mu\\\_z)
```

**Density reinforcement (attention creates gravity):**

```
rho\\\_z^{t+1} = rho\\\_z^t + beta \\\* sum\\\_{i in z} exp( -||x\\\_i - mu\\\_z||^2 )
```

**Covariance update:**

```
Sigma\\\_z = Cov( {x\\\_i : i assigned to z} ) + epsilon \\\* I
```

**Flow memory update (V5 — the missing symmetry):**

```
v\\\_i = x\\\_i^t - x\\\_i^{t-1}                              \\\[agent traversal velocity]

flow\\\_z^{t+1}     = decay \\\* flow\\\_z^t     + (1-decay) \\\* mean({ v\\\_i : i in z })
flow\\\_cov\\\_z^{t+1} = decay \\\* flow\\\_cov\\\_z^t + (1-decay) \\\* Cov({ v\\\_i : i in z })
```

\---

### 3.5 Zone Splitting (emergent polarization)

**Scale-free entropy measure:**

```
S\\\_z          = (1/d) \\\* log det(Sigma\\\_z)   \\\[normalized by dimensionality d]
S\\\_population = mean({ S\\\_z : all zones })
```

**Directional tension:**

```
D\\\_z = lambda\\\_max( flow\\\_cov\\\_z )   \\\[max eigenvalue of flow covariance]
```

**Split condition (no magic numbers):**

```
Split if:  S\\\_z > S\\\_population + kappa   OR   D\\\_z > kappa
```

Zones split when spatially too spread OR when traversed in conflicting directions. Opposite flows through the same semantic region force bifurcation.

**Split mechanism:**

```
axis  = principal eigenvector of Sigma\\\_z
delta = axis \\\* sqrt( lambda\\\_max(Sigma\\\_z) ) \\\* 0.5

z1 = Zone(mu\\\_z + delta, Sigma\\\_z, rho\\\_z / 2)
z2 = Zone(mu\\\_z - delta, Sigma\\\_z, rho\\\_z / 2)
```

\---

### 3.6 Zone-Specific Habituation

Anti-conformity entropy is zone-specific, modulated by visit count:

```
memory\\\_strength(agent, zone) = base\\\_strength / (1 + visit\\\_count(agent, zone))
```

First exposure: high plasticity. Repeated exposure: habituation and flattening. Character history shapes perception of place.

\---

## 4\. Full System Hamiltonian

```
H(x, Z) = sum\\\_i E(x\\\_i ; Z)   +   sum\\\_z V(mu\\\_z, rho\\\_z)
```

Where `V(mu\\\_z, rho\\\_z)` captures zone self-energy (depth and spread). System dynamics:

* Agents descend the energy landscape
* Zones reshape the landscape as agents move
* Density reinforces zone depth
* Flow memory creates directional currents
* Entropy prevents collapse to a single basin
* Coupling creates elastic zone-to-zone pressure

> \\\*\\\*No global equilibrium exists.\\\*\\\* The system is always in flux. Only metastable basins exist. This is correct — MCCF models culture, which does not converge.

\---

## 5\. Module Structure

### `mccf\\\_hothouse\\\_hamiltonian\\\_v2.py`

Core field engine.

* `Agent` — MetaState vector + temperature
* `Zone` — mu, Sigma, rho, inv\_cov
* `HotHouseHamiltonian` — analytic gradients, softmax entropy, zone coupling kernel
* `update\\\_agents()` — stochastic Hamiltonian descent
* `update\\\_zones()` — drift, density, covariance, coupling deformation, entropy-split
* `step()` — single simulation tick

### `mccf\\\_memory\\\_hothouse\\\_v3.py` (extension)

Non-Markovian agent memory. Plugs into v2.

* `Agent.memory` — fading trajectory buffer
* `Agent.memory\\\_embedding` — compressed exponential trace M\_i
* `update\\\_memory()` — exponential decay accumulation
* `effective\\\_state()` — memory-modulated x\_eff
* `zone\\\_habituation()` — zone-specific plasticity decay
* Modified `E\\\_z()`, `P()`, `grad()` — all use x\_eff and zone visit counts

### `mccf\\\_zones\\\_v5\\\_bridge.py` (V5 extension)

Zone trajectory memory — the missing symmetry.

* `Zone.flow` — mean directional current vector
* `Zone.flow\\\_cov` — directional dispersion tensor
* `Agent.prev\\\_x` — previous position for velocity computation
* `update\\\_zone\\\_flow()` — accumulates agent velocities into zone flow memory
* Modified `E\\\_z()` — anisotropic attraction with flow bias term
* `should\\\_split()` — entropy + directional tension bifurcation condition

### `mccf\\\_api.py` additions (Day 51)

* `POST /field/step` — advance V5 kernel one tick, return per-zone JSON
* `GET /field/zones` — current zone state (mu, rho, flow, flow\_tension)
* `POST /field/init` — initialize zones from X3D scene zone IDs

\---

## 6\. Key Code Patterns

```python
# Analytic attraction gradient
def grad\\\_attraction(self, x):
    g = np.zeros\\\_like(x)
    for z in self.zones:
        g += 2.0 \\\* z.rho \\\* z.inv\\\_cov @ (x - z.mu)
    return g

# Softmax zone assignment (memory-modulated)
def P(self, x, memory=None):
    x\\\_eff = x + kappa \\\* memory if memory is not None else x
    energies = np.array(\\\[np.exp(-self.beta \\\* self.E\\\_z(x\\\_eff, z)) \\\* z.rho
                         for z in self.zones])
    return energies / (np.sum(energies) + 1e-9)

# Zone coupling force
def zone\\\_coupling\\\_force(self):
    forces = \\\[np.zeros\\\_like(z.mu) for z in self.zones]
    for i, zi in enumerate(self.zones):
        for j, zj in enumerate(self.zones):
            if i != j:
                forces\\\[i] += self.alpha \\\* self.J(zi, zj) \\\* (zi.mu - zj.mu)
    return forces

# Flow memory update
def update\\\_zone\\\_flow(zones, agents, assignments):
    for i, z in enumerate(zones):
        flows = \\\[a.x - a.prev\\\_x for a, k in zip(agents, assignments)
                 if k == i and hasattr(a, 'prev\\\_x')]
        if flows:
            z.flow     = z.flow\\\_decay \\\* z.flow     + (1 - z.flow\\\_decay) \\\* np.mean(flows, axis=0)
            z.flow\\\_cov = z.flow\\\_decay \\\* z.flow\\\_cov + (1 - z.flow\\\_decay) \\\* np.cov(np.array(flows).T)

# Entropy-relative split condition
def should\\\_split(z, global\\\_entropy, kappa=0.3):
    d             = len(z.mu)
    local\\\_entropy = np.log(np.linalg.det(z.cov) + 1e-9) / d
    flow\\\_tension  = np.max(np.linalg.eigvals(z.flow\\\_cov).real)
    return local\\\_entropy > global\\\_entropy + kappa or flow\\\_tension > kappa

# Memory-warped agent state
def effective\\\_state(agent, kappa=0.5):
    return agent.x + kappa \\\* agent.memory\\\_embedding

# Zone-specific habituation
def zone\\\_habituation(agent, zone, base=0.3):
    visits = getattr(agent, 'zone\\\_visits', {})
    return base / (1.0 + visits.get(id(zone), 0))
```

\---

## 7\. Rendering Output Channels (Day 51+)

Three channels connect the V5 field to the X3D stage via SAI:

|Field Value|X3D Target|SAI Call Pattern|
|-|-|-|
|`z.flow` vector|Viewpoint Transform|`setField('translation', flow \\\* scale)`|
|`max\\\_eigenvalue(z.flow\\\_cov)`|PointLight intensity/color|`setField('intensity', tension\\\_to\\\_intensity(eig))`|
|`flow\\\_tension > kappa`|AudioClip dwell trigger|`startTime = tNow + 0.05` (existing pattern)|
|`z.rho` density|SoundFader gain|`ramp(0 -> rho\\\_to\\\_gain(z.rho), FADE\\\_MS)`|
|zone split event|Zone SAI rediscovery|`spDiscoverZones()` re-call|

### Channel 1 — Camera Drift (z.flow → Viewpoint)

Zone flow vector biases camera lead direction. A zone traversed left-to-right nudges the Viewpoint Transform to lead that motion.

```python
camera\\\_nudge = z.flow \\\* camera\\\_sensitivity
viewpoint\\\_transform.setField('translation', base\\\_pos + camera\\\_nudge)
```

### Channel 2 — Lighting Bias (flow\_tension → PointLight)

Max eigenvalue of `flow\\\_cov` maps to light intensity and color temperature. High tension (conflicting flows) = cooler, harder light. Coherent flow = warmer light.

```python
tension   = np.max(np.linalg.eigvals(z.flow\\\_cov).real)
intensity = lerp(warm\\\_intensity, cool\\\_intensity, normalize(tension))
light.setField('intensity', intensity)
```

### Channel 3 — Sound Triggers (tension → dwell / ambient crossfade)

Connects to the Day 49 sound engine. Tension above threshold fires dwell stinger. Flow direction reversal triggers ambient crossfade.

```python
if tension > dwell\\\_threshold:
    Clip\\\_zone\\\_Dwell.startTime = tNow + 0.05          # existing SAI pattern

if np.dot(z.flow, z.prev\\\_flow) < -reversal\\\_threshold:
    SoundFader\\\_zone.ramp(cur\\\_gain, 0)                # fade out
    SoundFader\\\_next\\\_zone.ramp(0, ambient\\\_gain)       # fade in
```

\---

## 8\. Integration Map

V5 is additive — it lives below the X3D layer and does not touch scene XML, loader logic, or the Day 49 sound engine. The integration seam is a thin JSON API.

|V5 Output|Existing Loader Hook|Status|
|-|-|-|
|`z.rho` density|SoundFader gain ramp|✅ Ready — wire to `rho\\\_to\\\_gain()`|
|`z.flow` tension|Dwell trigger threshold|✅ Ready — replace fixed timer with tension gate|
|Agent zone assignment|`\\\_agentSegZoneMap`|✅ Ready — add `/field/step` call on waypoint arrival|
|Zone split event|`spDiscoverZones()`|🔧 Needs new handler|
|`z.flow` vector|Viewpoint SAI (dope sheet)|📅 Day 51+ — cinematics layer|
|`flow\\\_cov` eigenvalue|PointLight SAI|📅 Day 51+ — cinematics layer|

### API Seam (Day 51)

```
POST /field/step
Body:    { "agent\\\_positions": \\\[{"id": "Cindy", "x": \\\[E, B, P, S]}, ...] }
Returns: { "zones": \\\[{"id": "Zone1", "mu": \\\[...], "rho": 1.4,
                      "flow": \\\[...], "flow\\\_tension": 0.7, "split": false}, ...] }
```

The loader calls `/field/step` on each waypoint arrival, consumes the JSON, and translates zone values to SAI calls. The X3D side knows nothing about Hamiltonians.

**Zone ID namespace:** Initialize V5 with `Zone1`, `Zone2`, `Zone3` from `testScene3`. Same IDs in Python and X3D.

\---

## 9\. Implementation Sequencing

### Day 50 (today — do not change)

* \[ ] Sound isolation tests — dwell, convolver, 300ms fade, bed guard
* \[ ] Fix `zone` attr on waypoints in `testScene3\\\_scene.xml`
* \[ ] Dope sheet architecture decision (Option A vs B)
* \[ ] GitHub commit — Days 48 + 49

> V5 math is done. Let it sit. Do not integrate today.

### Day 51

* \[ ] Ask Kate: define `/field/step` JSON contract
* \[ ] Ask Kate: analytic rendering functions for 3 channels
* \[ ] Initialize V5 kernel with Zone1/Zone2/Zone3
* \[ ] Wire `/field/step` call to waypoint arrival in loader

### Day 52+

* \[ ] Camera drift as first dope sheet track
* \[ ] Lighting bias as second track
* \[ ] Sound trigger integration (builds on Day 49 dwell pipeline)
* \[ ] Unified V5 kernel collapse (`mccf\\\_v5\\\_unified.py`)
* \[ ] GitHub commit — V5 integration

### What to Ask Kate on Day 51

1. Replace the magic `kappa` threshold with a principled derivation for d=4 MetaState space
2. Define the three rendering functions as explicit Python callables: `(z.flow, z.flow\\\_cov, z.rho) -> SAI-compatible scalar/vector`
3. Add inter-agent memory coupling: `M\\\_i <- M\\\_i + sum\\\_{j in zone} gamma \\\* M\\\_j` so culture becomes a transmissible memory field

\---

## 10\. What MCCF Becomes

|Before V5|After V5|
|-|-|
|Adaptive clustering field|Coupled stochastic Hamiltonian field theory|
|Agent-based simulation|Path-dependent dynamical system with memory|
|Zones as static attractors|Zones as historical currents — geology of behavior|
|Markovian agents|Non-Markovian agents (trajectory shapes perception)|
|Emergent behavior|Spontaneous symmetry breaking as polarization mechanism|
|Culture as backdrop|Culture as co-evolving agents and attractor basins|

> \\\*\\\*The deep result:\\\*\\\* Story is no longer a sequence. It is a deforming field history.  
> Character identity = memory-weighted field distortion.  
> Plot = evolution of interacting memory fields.  
> Emotion = gradient asymmetry induced by past exposure.

\---

*MCCF V5 Semantic Field Specification — originated June 19 2026 — Kate + Claude — do not implement before Day 51*



*https://aiartistinprocess.blogspot.com/2026/06/santa-fe-conformity-model.html*



*The spec credits Kate but doesn't link to the source. That post has the full derivation chain in Kate's own voice. Worth having for when you brief someone new on where V5 came from.*



*The "geology" framing*



*Kate's line: "a zone is not a place — it is a record of movement becoming structure." The spec has it but buried. It's the single best one-line explanation of what V5 actually does and worth keeping prominent when you explain this to anyone — musicians, collaborators, grant readers.*



*The Reaper implication*



*Nobody said it explicitly but it's sitting right there: V5's flow tension is a continuous scalar that maps directly to CC11 (expression). The Reaper Vision in your seed doc says "Tension → CC11 modulates live instrument." V5 gives you a principled, physics-derived tension value to drive that. That connection should go in the Day 51 prompt to Kate and in the next seed doc. It closes the loop between the semantic field and the DAW bridge in a way that wasn't possible before.

The camera drift formula at top right — C = α \* F̂\_j + β \* ∇ρ\_j — is cleaner than anything we wrote in the spec. Camera leads the flow vector and the density gradient. That's more complete than what we had. Get that formula into the MD file and into the Day 51 prompt.*

*The "9. The Principle" box in the bottom right is the thing to put on the wall:*



*All audiovisual output is a function of the same field derivatives. Meaning flows. The world responds. The story emerges.*



*And the two runtime modes — Deterministic (full gradients, reproducible, authorial control) vs Performance (approximate gradients, sampled updates, real-time interaction) — that's an architectural distinction we never made explicit. It matters a lot for how you wire the API. Worth a section in the spec.*



*She also named the Stage Adapter Layer explicitly as its own architectural tier with smoothing and temporal coherence. That's the piece between the raw field output and the SAI calls — we implied it but didn't name it. Good to have a name for it.*



*Lucky fellow indeed. Go start Day 50. You've got good work waiting.*

