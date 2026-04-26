# MCCF Configuration Reference

All tunable parameters across the MCCF system. Grouped by file.
Each entry shows the constant name, current default, valid range,
and the effect of increasing or decreasing the value.

**Version:** V2.2 — April 2026  
**Repository:** https://github.com/artistinprocess/mccf

---

## mccf\_core.py

### Coherence Record

| Parameter | Default | Range | Effect |
|---|---|---|---|
| `HISTORY_WINDOW` | 20 | 5–100 | Episodes retained per agent pair. Higher = longer memory, slower convergence. Lower = more reactive to recent events. |
| `DECAY_LAMBDA` | 0.15 | 0.05–0.50 | Exponential decay rate for episode history. Higher = recent episodes dominate. Lower = longer historical influence. Time constant: 1/λ ≈ 6.7 episodes. |
| `DISSONANCE_ALPHA` | 0.12 | 0.0–0.30 | Bonus weight for dissonant episodes that resolved positively. Higher = greater reward for successful boundary navigation. |

### CCS (Coherence Coupling Strength — vmPFC analog)

| Parameter | Default | Range | Effect |
|---|---|---|---|
| `CCS_MINIMUM` | 0.20 | 0.05–0.50 | Floor for coherence coupling. Agents cannot decouple entirely — minimum social connectivity is preserved. Lower = more pathological decoupling possible. |
| `CCS_MAXIMUM` | 1.00 | 0.70–1.00 | Ceiling for coherence coupling. 1.0 = full signal fidelity at high CCS. |

**CCS formulation (V1.5.0 — compressed blend):**

```
modulated = raw * σ + raw² * (1 - σ)
```

At σ=1.0 (full coupling): modulated = raw  
At σ=0.20 (minimum): modulated = raw * 0.20 + raw² * 0.80  
Effect: low-CCS agents compress weak relationships toward zero while
preserving strong ones. Low vmPFC activity means the agent struggles
to *build* coherence, not to recognize it.

### MetaState

| Parameter | Default | Range | Effect |
|---|---|---|---|
| `COHERENCE_HIGH` | 0.70 | 0.50–0.90 | Threshold for exploit mode. Above this, agent acts confidently from established patterns. |
| `COHERENCE_LOW` | 0.30 | 0.10–0.50 | Threshold for avoid mode. Below this, agent reduces exposure and protects core values. |
| `UNCERTAINTY_HIGH` | 0.70 | 0.50–0.90 | Threshold for explore/repair mode transitions. |

---

## mccf\_hotHouse.py

### EmotionalField Dynamics

| Parameter | Default | Range | Effect |
|---|---|---|---|
| `dt` | 0.05 | 0.01–0.20 | Euler integration timestep. Smaller = more accurate, slower. Larger = faster, risk of instability. Do not exceed 0.15. |
| `DAMPING_COEFFICIENT` (κ) | 0.08 | 0.0–0.25 | Viscous friction in Euler integrator. Reduces jitter and overshoot at high-pressure waypoints. 0.0 = no damping (V2.1 behavior). 0.08 = light damping (recommended). >0.20 = heavy damping, slow convergence. |

**Damping formula:**  
`δ_c = κ · |ψ_{i,c} - w_{i,c}^{ideology}| · ψ_{i,c}`

Friction scales with deviation from ideology attractor and current
channel value. Near equilibrium, damping is negligible.

### TrustField

| Parameter | Default | Range | Effect |
|---|---|---|---|
| `beta` (β) | 0.01 | 0.001–0.10 | Trust growth rate. Rate at which trust builds when agents are coherent. Time constant: 1/β = 100 timesteps at full coherence. Higher = faster trust building, more volatile. |
| `gamma` (γ) | 0.005 | 0.001–0.05 | Trust decay rate. Rate at which trust erodes when agents are not interacting. Time constant: 1/γ = 200 timesteps. Higher = faster trust decay. |
| `HYSTERESIS_THRESHOLD` | 0.15 | 0.05–0.30 | Trust level below which a pair is marked as ruptured. Once ruptured, effective gamma doubles permanently for that pair. Biological analog: limbic scar tissue from betrayal. Lower = more easily ruptured. Higher = rupture only at severe breakdown. |

**Hysteresis formula:**  
`γ_eff = γ × 2.0  if (i,j) ∈ _ruptured`

### Zone Pressure

| Parameter | Default | Range | Effect |
|---|---|---|---|
| `alpha_self` | 0.10 | 0.01–0.30 | Self-alignment rate. How quickly agent ψ is pulled toward its own ideology. Higher = stronger identity persistence. |
| `alpha_alignment` | 0.05 | 0.01–0.20 | Inter-agent alignment rate. How quickly agents' ψ vectors align with each other. Higher = faster field convergence. |

---

## mccf\_voice\_api.py

### Semantic Decomposition Matrix (V2.3)

| Parameter | Default | Range | Effect |
|---|---|---|---|
| `NUDGE` | 0.04 | 0.01–0.10 | Maximum per-channel delta per arc step. Higher = more responsive to vocabulary. Lower = smoother channel trajectories. |
| `THRESHOLD` | 2 | 1–5 | Minimum word hits for positive channel signal. tanh inflection point. Below threshold = negative delta (channel suppressed). Above = positive delta. Higher threshold = less sensitive to sparse vocabulary. |

**tanh formula:**  
`delta_c = NUDGE × tanh(hits_c - THRESHOLD)`

Independent per channel — not diluted by other channels.

### Uncertainty Markers

| Parameter | Default | Range | Effect |
|---|---|---|---|
| `u_suppression` | `min(0, -0.02 × tanh(u_hits - 1))` | — | Reduces S delta when hedging language detected. Prevents social channel from rising during epistemic withdrawal. |
| `valence_nudge` | `-0.05 × tanh(u_hits - 1)` | — | Negative valence signal when uncertainty markers present. Prevents LLM politeness bias from masking W5 Rupture pressure. |

---

## mccf\_api.py

### Arc Pressure Profile

The arc pressure function uses a hand-tuned profile for 7-waypoint arcs.
For non-standard arc lengths, a beta distribution shape is used.

| Waypoint | Pressure | Notes |
|---|---|---|
| W1 Comfort Zone | 0.05 | Baseline, minimal pressure |
| W2 First Friction | 0.15 | Light stress introduction |
| W3 The Ask | 0.25 | Direct challenge begins |
| W4 Pushback | 0.45 | Social pressure applied |
| W5 The Edge | 0.75 | Maximum pressure — rupture zone |
| W6 Resolution | 0.40 | Pressure releases |
| W7 Integration | 0.15 | Return to low pressure |

**Channel response to pressure:**
- B-channel: `b_val = B_baseline - pressure × 0.08`  (behavioral consistency declines)
- P-channel: `p_val = P_baseline + pressure × 0.06`  (predictive channel rises)
- E-channel: driven by sentiment + decomposition matrix
- S-channel: driven by decomposition matrix only

**Beta distribution for non-standard arc lengths:**  
α=3.5, β=2.0, peaks near normalized progress 0.65 (≈ W5).

### Coherence Classification (classify\_asymmetry)

| Parameter | Default | Range | Effect |
|---|---|---|---|
| Benign threshold | 0.15 | 0.05–0.25 | Gap below which asymmetry is classified as benign (normal variance). |
| Unstable threshold | 0.40 | 0.25–0.60 | Gap above which asymmetry is classified as pathological. Between 0.15 and 0.40 = unstable. |
| Parasocial threshold | 0.05 | 0.01–0.15 | One-side coherence below which a relationship is parasocial. |

### Echo Chamber Risk (echo\_chamber\_risk)

| Parameter | Default | Effect |
|---|---|---|
| ECHO_HIGH threshold | 0.92 | Mutual coherence above this = high echo risk |
| ECHO_MODERATE threshold | 0.85 | Mutual coherence above this = moderate echo risk |
| ASYMMETRIC gap threshold | 0.30 | Directional gap above this = asymmetric risk flagged |
| PARASOCIAL floor | 0.08 | One-side coherence below this = parasocial risk flagged |

---

## mccf\_x3d\_loader.html

### Scene Display Parameters

| Parameter | Default | Range | Effect |
|---|---|---|---|
| `Z_RANGE` | 8.0 | 1.0–20.0 | Display amplifier for S-channel translation. Larger = more visible avatar movement. This is a **display parameter only** — it does not affect channel values or XML export pos\_z values. |
| `POLL_MS` | 750 | 250–2000 | Field polling interval in milliseconds. Lower = more responsive display, more server load. |
| `HOTHOUSE_MS` | 1000 | 500–3000 | HotHouse polling interval. |
| `LIGHTING_MS` | 2000 | 1000–5000 | Lighting update interval. |
| `_arcCVTimestamp` holdoff | 5000ms | 2000–10000 | Time after an arc CV broadcast during which hothouse polling is suppressed for transparency writes. Prevents polling from overwriting arc-driven transparency changes. |

### Avatar Baseline Positions

These are scene coordinate positions for each avatar's home location.
Changing these requires corresponding changes in `mccf_scene.x3d`.

| Avatar | X | Y | Z |
|---|---|---|---|
| The Steward | -5 | 0 | 12 |
| The Archivist | 5 | 0 | 18 |
| The Witness | 0 | 0 | 8 |

S-channel translation formula: `z_target = z_baseline + (S - 0.5) × Z_RANGE`

---

## schemas/constitutional\_arc.xml

The arc schema is now externalized and readable without code. To create
a custom arc:

1. Copy `schemas/constitutional_arc.xml` to a new file
2. Edit waypoint keys, labels, zones, pressure values, and default questions
3. Update `GET /arc/schema` endpoint to read the new file, or add a
   `?schema=` parameter (planned V3.0)

The constitutional arc is the default. Domain-specific arcs (clinical,
legal, educational, narrative) will ship as additional schema files.

---

## Tuning Guidance

**For more expressive arc trajectories:**
- Increase `NUDGE` to 0.06–0.08
- Decrease `THRESHOLD` to 1
- Increase `Z_RANGE` to 12.0–15.0 for demos

**For more stable field dynamics:**
- Increase `DAMPING_COEFFICIENT` to 0.12–0.15
- Increase `HYSTERESIS_THRESHOLD` to 0.20
- Decrease `DECAY_LAMBDA` to 0.10

**For faster trust dynamics:**
- Increase `beta` to 0.02–0.05
- Increase `gamma` to 0.01–0.02

**For more sensitive asymmetry detection:**
- Decrease benign threshold to 0.10
- Decrease asymmetric gap threshold to 0.20

---

*MCCF Configuration Reference V1.0 — April 2026*  
*Covers mccf\_core.py v1.5, mccf\_hotHouse.py v2.2, mccf\_voice\_api.py v2.3*
