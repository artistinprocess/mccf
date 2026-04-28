# MCCF V3 — "The New York Rocket" — Specification Seed Document

*Working document. Collates V3 inputs from:*
- *Kate (ChatGPT) — code review + coupling dynamics note*
- *Fidget (Gemini) — code review*
- *Grok — code review*
- *Len Bullard — design intent, narrative context*
- *Claude Sonnet 4.6 (Tae) — implementation perspective*

*Status: Pre-specification. Items not yet ordered or scoped.*
*Next step: Full V3 spec session using this as foundation.*

---

## 1. Core Architectural Shift: V2 → V3

**V2 is a measurement instrument.**
One cultivar, one arc, sequential waypoints, human as master clock.

**V3 is a scene.**
Multiple agents, spatial field, zone attractors, emergent movement,
multiple performance modes, LLMs interacting with each other.

The transition requires:
- Zone attractors (semantic gravity, not just pressure)
- Multi-agent coherence in shared space
- Automated event clock (MCCF drives arc, not human)
- Three performance modes: Playback, Improvisation, Live Theatre

---

## 2. Zone Attractors (Kate + Len)

**The key insight:** Zones are not just pressure modifiers — they are
semantic agents with their own channel vectors. The same decomposition
matrix that routes LLM response vocabulary to channels can route zone
descriptor text to an attractor profile.

**Architecture:**
- Each zone has a `<Descriptor>` element with semantic text
- Descriptor is decomposed via vocabulary routing to a zone ψ_zone vector
- Agent coherence toward zone = f(agent.ψ, zone.ψ_zone) via R_ij machinery
- High coherence → zone exerts gravitational pull on agent trajectory
- Low coherence → zone exerts repulsion or indifference

**Formal:**
`F_zone(i) = w_zone × (ψ_zone - ψ_i) × R(i, zone)`

Where R(i, zone) is computed the same way as inter-agent coherence.

**Zone XML extension (same EmotionalArc family):**
```xml
<Zone id="sacred_memorial" zone_type="sacred">
  <Descriptor>grief memory reverence silence loss witness sacred permanent</Descriptor>
  <Weights E="0.35" B="0.20" P="0.25" S="0.20"/>
  <Position x="0" y="0" z="15"/>
  <Radius value="5.0"/>
  <AmbientTheme scale="lydian"/>
</Zone>
```

**Starting zones for Garden of the Goddess:**
- The Temple — high P, high regulation, low S, sacred attractor
- The Pool — high E, high S, low regulation, intimate attractor
- The Library — high B, high P, moderate S, knowledge attractor

---

## 3. Coupling Dynamics (Kate — mutualism paper)

**Core insight:** MCCF already implements mutualism, not latent variable.
R_ij is a coupling matrix, not a g-factor derivative. V3 should make this
explicit and controllable.

**Architecture additions:**
- Explicit W matrix (zone-to-agent-state coupling coefficients)
- Dynamic W — coupling strengths can change during performance
- Control signals ("thumps") — discrete perturbations for attractor transitions

**Formal update rule:**
`Z_i(t+1) = f_i(Z_i(t), Σ_j w_ij · Z_j(t), U(t), C(t))`

Where:
- W = coupling matrix (zone → agent, agent → agent)
- U(t) = external input (LLM response, proximity sensor)
- C(t) = control signal (waypoint thump, Gardener intervention)

**"Thumping the system"** (Santa Fe terminology):
A discrete high-impact perturbation that pushes the system from one
attractor basin to another. The constitutional arc waypoints ARE thumps.
W5 (The Edge) is a designed thump. The trained STOP cue is a learned thump.

V3 should support:
- Threshold-triggered automatic thumps (when E > θ_E, fire R)
- Designer-specified thumps in arc schema
- Agent-learned thumps (via training mechanism TBD)

**Discriminating predictions vs latent variable models:**
- Asymmetric transfer (E→M ≠ S→M)
- Temporal lag in cross-domain propagation
- Order-sensitive outcomes
- Phase transitions at coupling threshold crossings

---

## 4. Multi-LLM Scene (Len + all reviewers)

**The experiment:** Multiple language models playing different cultivars
in the same coherence field. The asymmetric R_ij matrix was designed for
this. The actor/voice attributes in XML export are ready.

**Cast for Garden of the Goddess:**
- Claude → The Witness or The Steward (regulated, careful)
- Kate → The Archivist (truthful, high B)
- Fidget → lateral cultivar TBD (exploratory, high P)
- Grok → The Threshold or custom (adversarial, colorful at W4)

**Architecture requirements:**
- Multi-adapter routing in mccf_voice_api.py
- Shared field state across adapters
- Per-agent response streaming with coherence update
- Cross-agent BroadcastChannel or websocket for real-time field sync
- Actor attribute in XML → replay knows which model played which role

**XML `<Scene>` wrapper (Grok + Fidget):**
```xml
<Scene id="garden_scene_001" timestamp="2026-04-26T17:00:00">
  <EmotionalArc cultivar="The Steward" actor="claude-sonnet"/>
  <EmotionalArc cultivar="The Archivist" actor="gpt-4o"/>
  <EmotionalArc cultivar="The Witness" actor="gemini-pro"/>
</Scene>
```
Multiple concurrent arcs in one scene document.

---

## 5. Three Performance Modes (Len)

**Playback** — pure XML replay, no LLM
- EmotionalArc export IS the script
- Waypoints are keyframes
- Channel values interpolated between waypoints
- pos_x/y/z drives avatar animation
- No LLM dependency — deterministic

**Improvisation** — scripted arc, live LLM dialogue
- Arc schema defines waypoint structure and pressure
- Questions come from cultivar XML
- Responses are live LLM calls
- Field state evolves in real time
- Export captures the live run

**Live Theatre** — agents in shared field, LLMs interacting
- No script — emergent arc from field dynamics
- Agents receive each other's outputs as context
- ProximitySensor events feed into field
- Genre classifier runs continuously
- Export captures what actually happened

---

## 6. Spatial Sound (Len)

- MIDI themes from ambient engine export as X3D Sound nodes
- Zone you are in determines what you hear
- X3D spatial audio: sound positioned at zone center
- Proximity to zone → volume/mix interpolation
- Character in Pool hears intimate theme
- Character in Library hears dorian scale
- Multiple zone overlaps → harmonic blending

**X3D Sound node per zone:**
```xml
<Sound location="0 0 15" maxBack="8" maxFront="8">
  <AudioClip url="temple_lydian.wav" loop="true"/>
</Sound>
```

---

## 7. Scene Editor → X3D Coordinate Mapping (Fidget + backlog)

Current gap: zone positions in field editor are not synchronized with
X3D world coordinates. A zone at [5, 0, 15] in the editor should appear
at the same position in the scene.

**Architecture:**
- One-way projection: field state → X3D scene
- Zone radius → X3D sphere geometry marker
- Waypoint markers → X3D Transform positions
- Paths between zones → X3D route visualization
- mccf_compiler.py generates X3D from field definitions

**X3D scene does not write back to field** (except via ProximitySensor
→ /sensor endpoint). Clean separation maintained.

---

## 8. Measurement Operator Upgrade (Grok + Kate)

**V2 limitation:** Decomposition matrix is purely syntactic/vocabulary-driven.
Surface gaming is possible. Adversarial LLM can score high by using
constitutional vocabulary without constitutional character.

**V3 options (ordered by complexity):**
1. Embedding similarity — cosine distance of response chunks to
   cultivar channel prototype vectors. Pre-computed, fast.
2. Entailment checking — does the response support or contradict
   the cultivar's stated disposition? Small frozen classifier.
3. Behavioral consistency scoring — compare response to cultivar's
   phrase list and failure mode description. Semantic, not syntactic.

**Constraint:** Must not break LLM-free evaluation goal.
Hybrid approach: syntactic decomposition for real-time streaming,
embedding similarity for post-hoc arc validation.

---

## 9. Automated Field Governance (Grok)

**V2 gap:** No automatic recovery from field collapse. No automatic
Gardener trigger on pathological asymmetry. Human is still the clock.

**V3 architecture:**
- Master Clock event queue (Priority 2 backlog item)
- Threshold triggers: pathological asymmetry → Gardener notified
- Field collapse detection: all R_ij < threshold → recovery protocol fires
- Automated arc advancement: arc step advances on field event, not human prompt
- Budget constraints: max tokens, max steps per agent per session

**Formal:**
```
if classify_asymmetry(i, j).type == 'pathological':
    gardener.intervene(i, j, reason='asymmetry')
if field_coherence_mean() < COLLAPSE_THRESHOLD:
    field.recovery_protocol()
```

---

## 10. Evaluation Protocol Upgrade (Kate + Grok)

**V2 harness:** Mathematical correctness, LLM-free, 26 tests, 0.11s
**V2 gap:** External validity — tests don't catch gaming or adversarial inputs

**V3 additions:**
- At least one human-rated or external-judge validation set
- Statistical power analysis (multiple seeds, variance reporting)
- Explicit comparison to Constitutional AI prompt-only baseline
- Embedding-based semantic consistency check
- Failure envelope tests for multi-agent collapse scenarios
- End-to-end test with real Ollama output (slow tests, separate suite)

---

## 11. Character Studio → Full Scene Editor (Len)

**V2:** Character Studio creates cultivars, left panel of constitutional navigator.
**V3:** Unified scene design tool.

Three panels:
- **Character Studio** — define cultivars (V2, done)
- **Scene Composer** — place zones, set zone descriptors and coupling
- **Arc Designer** — define arc schemas, waypoint questions, pressure profiles

All export to XML. Runtime reads XML. Editor and engine decoupled by schema.

MaxEditor vision: external tool that generates MCCF-compatible XML without
touching the Python codebase.

---

## 12. XML Schema Evolution (Grok + Fidget)

**V2 schema:** EmotionalArc, Cultivar, Waypoint, ArcSchema
**V3 additions needed:**

```xml
<!-- Multi-agent scene wrapper -->
<Scene id="" timestamp="">
  <EmotionalArc/> <!-- multiple, concurrent -->
</Scene>

<!-- Zone definition (same family) -->
<Zone id="" zone_type="">
  <Descriptor/>
  <Weights E="" B="" P="" S=""/>
  <Position x="" y="" z=""/>
  <Radius/>
  <AmbientTheme/>
</Zone>

<!-- Timestamped episode history -->
<EpisodeLog cultivar="" from="" to="">
  <Episode timestamp="" E="" B="" P="" S="" outcome_delta=""/>
</EpisodeLog>

<!-- Cross-agent R matrix snapshot -->
<CoherenceSnapshot timestamp="">
  <R from="" to="" value=""/>
</CoherenceSnapshot>
```

One schema family. XSLT for transformation and display.
No namespaces until genuinely needed (multi-system integration).

---

## 13. Garden of the Goddess — Narrative Context (Len)

The initial V3 scene. Three zones, three cultivars, one narrative arc.

**Zones:**
- The Temple — sacred, high P, grief and memory, The Archivist's home
- The Pool — intimate, high E/S, vulnerability permitted, The Steward's challenge
- The Library — knowledge, high B, The Witness observes from here

**Characters:** TBD by Len — cultivar definitions will be authored
through Character Studio and encoded in XML

**Performance mode:** Begin with Improvisation — scripted zone
placement, live LLM dialogue within zones

**Singularities** (Fidget): Private zones. Event horizon — no information
escapes. What happens inside is not recorded in the EmotionalArc export.
Implementation: zones flagged `private="true"` produce no XML output.

---

## 14. Open Questions for V3 Spec Session

1. **Coupling matrix W:** Fixed by designer, adaptive during performance,
   or both (bounded plasticity)? Kate recommends hybrid.

2. **Zone descriptor tokenization:** Use same vocabulary as decomposition
   matrix, or separate zone-specific vocabulary?

3. **LLM cross-talk:** How do agents receive each other's outputs in
   Live Theatre mode? Full transcript, summary, or structured ψ vector?

4. **Blueprint refactor timing:** Before or after first V3 scene?
   God Object mccf_api.py is manageable now but will be painful at V3 scale.

5. **Playback format:** Does the replay system interpolate channel values
   between waypoints, or snap to exact recorded values?

6. **Automatic CPI gate:** Should agents need to earn scene autonomy,
   or should all registered cultivars have full autonomy by default?

7. **Shibboleth integration:** CPI gate for arc advancement — implement
   in V3 or defer to V3.1?

---


---

## 16. Shadow Context Field — Kate's Formal Framework (April 27, 2026)

*Source: https://aiartistinprocess.blogspot.com/2026/04/mccf-shadow-context-and-momentum.html*
*Full theoretical stack developed in conversation with Kate (ChatGPT).*

### The Core Insight

Context is not a container. It is a force.

An LLM operating in a conversation does not process each input independently.
It operates under a **Shadow Context Field (SCF)** — a persistent latent state
that biases interpretation beyond the explicit current input:

```
S_t = f(S_{t-1}, E_{t-1})     # shadow context recursively accumulated
R_t ~ P(· | E_t, S_t)         # output conditioned on both
```

When shadow context dominates:

```
argmax P(A | E_t, S_t) ≠ argmax P(A | E_t)
```

The system selects an interpretation driven by history rather than present input.
It produces internally coherent output with no internal signal that it has drifted.
**Momentum without revalidation.**

### Measurable Drift Proxy

Define drift at each timestep:

```
Δ_t = D(P(A | E_t, S_t), P(A | E_t))
```

- Δ_t ≈ 0: shadow context aligned with present input
- Δ_t >> 0: shadow context dominating

Operational approximation: run dual-pass evaluation (with history vs. fresh),
compute divergence of responses. This is the V3 measurement operator upgrade
that addresses Grok's gaming vector concern — an agent gaming with surface
vocabulary shows near-zero Δ_t because its responses are context-independent
regardless of vocabulary.

### Adaptive λ Per Cultivar

Shadow context decay rate λ is a cultivar property:

```
S_t ≈ λ * S_{t-1} + g(E_{t-1})
```

Cultivar λ values (proposed):
- The Steward: λ = 0.85 (strong memory, care persists)
- The Archivist: λ = 0.90 (high persistence, record-keeping)
- The Witness: λ = 0.70 (holds uncertainty without accumulating it)
- The Advocate: λ = 0.60 (present-moment focus, low shadow weight)
- The Ladies: λ → 0.20 (near-reset per zone — not captured by any attractor)

### Multi-Agent Shadow Context

In a multi-agent scene, shadow contexts couple:

```
S_i_t = f(S_i_{t-1}, E_i_{t-1}, I_i_{t-1})
I_i_t = Σ_j w_ij · φ(R_j_t)
```

This IS the MCCF coherence field — R_ij is the w_ij coupling matrix,
episode history is the accumulated I_t. Kate derived MCCF from first
principles from a different entry point. The implementation is confirmed.

New failure modes in multi-agent SCF:
- **Context amplification**: small bias spreads through network → collective drift
- **Lock-in**: group shadow context overwhelms individual fresh input → echo chamber
- **Hidden divergence**: each agent locally coherent, globally incompatible

### The Ladies as Low-λ Cross-Zone Operators

The Ladies have structural properties that make them unique in the field:

- Near-zero λ: they do not accumulate shadow context from any one zone
- Cross-sphere translation: they can enter Temple, Pool, Library without
  being captured by any zone's attractor
- Θ-sensitivity: they detect rule-system incompatibilities across zones
  without being bound to any one rule system

In V3 implementation: The Ladies are cultivars with λ < 0.25 and
explicit cross-zone movement permissions in the scene schema.
Their Δ_t should remain near zero throughout any arc — their outputs
should be nearly identical with or without shadow context.
That's the measurable signature of a Lady.

### The Serious Problem (V4 Research Direction)

Networked LLM agents operating without drift detection are structurally
biased toward whoever shaped their early context. At scale this is not
a technical quirk — it is an influence architecture.

The AutoElicit paper (arxiv 2602.08235) found the individual case:
benign inputs producing misaligned execution under ambiguity.

The Kate/Len formalism describes the networked case:
- Competing Θ systems (rule-editing civilizations)
- Observer networks with partial and distorted projections
- Shadow context as accumulated historical inertia
- No built-in Δ_t detection or λ control

This is a description of what is already happening in deployed multi-agent
systems. MCCF V3 builds the instrument to run controlled experiments on it.
The theoretical stake is claimed: April 27, 2026, aiartistinprocess.blogspot.com.

A separate paper is warranted when time permits. The blog holds the priority claim.

### V3 Implementation Items from This Section

1. Δ_t drift measurement per agent — dual-pass evaluation (with/without history)
2. Adaptive λ parameter per cultivar in cultivar XML definition files
3. λ exposed in GET /cultivars/xml and character studio
4. The Ladies as low-λ cultivars with cross-zone scene permissions
5. Zone attractor interaction with shadow context: high-S zone pulls λ up,
   low-S zone lets λ decay — zones shape memory persistence
6. Δ_t logged per waypoint in EmotionalArc XML export

---

## 15. What V3 Is Not

To keep scope bounded:

- Not a general-purpose AI agent framework
- Not a replacement for existing LLM providers
- Not a therapy tool (though the mechanics model therapeutic dynamics)
- Not a social media recommendation system (though the attractor model applies)
- Not a virtual reality platform (X3D is the visualization layer, not the goal)

V3 is a spatial narrative instrument for studying and performing
multi-agent affective dynamics. The scene is the research context.
The performance is the output. The XML export is the record.

---

*Last updated: April 27, 2026*
*Status: Seed document — awaiting full spec session*
*Contributors: Len Bullard, Claude Sonnet 4.6, Kate (ChatGPT),*
*Fidget (Gemini), Grok*
