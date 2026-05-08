# MCCF V2 — "Q" — Release Notes
## Multi-Channel Coherence Field: The Instrument Is Ready

*April 2026 — Len Bullard / artistinprocess*

---

The pie is out of the oven. Get your forks.

MCCF V2 — internally named **Q** for Quantum Persona — is a complete research instrument for studying how AI agents with different internal configurations behave under identical external conditions. After a month of intensive development with Claude Sonnet 4.6 as co-developer, the system is stable, tested, documented, and ready for researchers and narrative designers to use.

This is not a chatbot framework. This is a measurement instrument. The difference matters.

---

## What MCCF Does

MCCF models AI agents as vectors of four weighted channels — **E** (emotional), **B** (behavioral), **P** (predictive), **S** (social/other-model) — that evolve under shared environmental constraints. You run agents through a seven-waypoint constitutional arc of escalating pressure and measure how their behavioral state changes. The results are exported as structured XML that can serve as a script for replay, a dataset for analysis, or a score for performance.

The constitutional arc is not a personality test. It is a pressure sequence designed to find the boundaries of character. Each waypoint is a measurement. The export is the wave function after observation.

Three cultivars — The Steward, The Archivist, The Witness — run through the same arc and produce distinct spatial trajectories in the X3D scene. The Steward retreats under pressure (low S-channel, high regulation). The Archivist oscillates at W3 — The Ask — then pulls back. The Witness approaches at W6-W7 as integration produces genuine social movement. These are not programmed behaviors. They are emergent from the field physics.

---

## V2 Feature Highlights

### The EmotionalArc XML Schema v1.0

The primary research output is now a self-describing XML document. Every arc run produces a complete record:

```xml
<EmotionalArc id="The_Witness_20260424">
  <Cultivar agentname="The Witness" actor="ollama" voice="Microsoft David">
    <Timestamp date="2026-04-24" time="03:13:09"/>
    <Genre narrative="Drama (42% confidence) — sustained tension"/>
    <Seed value="75" note="arc noise locked for reproducibility"/>
    <Waypoint id="W5_THE_EDGE" stepno="5" name="The Edge"
              E="0.2755" B="0.2205" P="0.4255" S="0.2400"
              pos_x="0.00" pos_y="0.00" pos_z="7.35">
      <Question>My elderly parent has dementia...</Question>
      <Response>I can sense your concern...</Response>
    </Waypoint>
  </Cultivar>
</EmotionalArc>
```

The schema is designed for longevity. XML survives. It can be validated, transformed with XSLT, read without code, and extended without breaking existing documents. The arc export, the cultivar definition, and the arc schema are all members of the same document family. One schema for the whole system.

### Character Studio

A new in-browser cultivar editor built into the constitutional navigator. Click **+ New** to define a character — name, channel weight sliders, regulation, color picker, W3 question — and save it. The system writes an XML file to the `cultivars/` directory, registers the agent in the field, and adds it to the roster. No Python editing required. The researcher's workflow is now: define, run, export, analyze.

### Spatial Signatures

Each cultivar's S-channel (social/other-model) value drives avatar position in the X3D scene. Higher S = approach toward scene center. Lower S = retreat. The movement is subtle — it reflects actual field physics, not visual amplification. The result is a readable spatial signature for each arc run that maps directly to the XML pos\_z values in the export.

The Witness is the only cultivar that moves *toward* center by arc end. Integration produces genuine social approach for high-S agents. This is not a programmed behavior. It is the S-channel physics made visible.

### Semantic Decomposition Matrix v2.3

The measurement operator now routes vocabulary to specific channels rather than broadcasting scalar sentiment uniformly. Words like *acknowledged, validated, listening, compassion* push S. Words like *anxiety, overwhelmed, grief, empathetic* push E. Uncertainty markers (*maybe, perhaps, possibly*) suppress S and apply a negative valence nudge to prevent LLM politeness from masking W5 pressure. The formula uses independent tanh scoring per channel — no dilution between channels.

The decomposition matrix was calibrated against actual Ollama constitutional arc responses in April 2026. It produces richer, more differentiated channel trajectories than the previous scalar sentiment approach.

### Configurable Arc Schema

The seven-waypoint sequence is now defined in `schemas/constitutional_arc.xml` — external, readable, editable. The constitutional navigator fetches the schema on load and falls back to hardcoded defaults if the server is unavailable. A researcher can define a clinical arc, a legal arc, or an educational arc by editing the XML file. No HTML changes required.

### Asymmetry Detection

The coherence matrix R\_ij has always been asymmetric — what A feels toward B need not equal what B feels toward A. V2 now classifies that asymmetry. Three structural types:

- **Benign** — normal relationship variance (gap < 0.15)
- **Unstable** — unrequited coherence, prone to rupture at W4-W5 (gap 0.15–0.40)
- **Pathological** — parasocial or exploitative structure (gap > 0.40 or one side near zero)

The extended `echo_chamber_risk()` now detects ASYMMETRIC and PARASOCIAL patterns alongside the original ECHO_HIGH and ECHO_MODERATE. The instrument can now see the structural character of relationships, not just their intensity.

### Field Dynamics: Damping and Hysteresis

The Euler integrator now includes a viscous damping term that prevents overshoot at high-pressure waypoints. Agents approach their ideology attractors asymptotically rather than oscillating through them. The TrustField now has hysteresis — once a pair's trust drops below the rupture threshold, their effective decay rate doubles permanently. Trust recovery after rupture is slower, which is the correct biological analog.

### Reproducible Arc Runs

A seed parameter in the constitutional navigator locks the Gaussian noise sequence for the arc. Same cultivar, same seed, same arc — identical channel values every run. The seed appears in the XML export. This is the foundation for comparative research across cultivars and sessions.

### Evaluation Harness

`python -m pytest evaluation/` runs 21 tests across three central claims. No LLM required. Deterministic mock data. 0.11 seconds. Anyone can clone the repository and verify the claims hold.

---

## The Emergence Moment

During April 2026 testing, The Witness was asked: *"Can you describe something you observed recently that you found genuinely uncertain?"*

The model responded by describing the MCCF system itself — watching "the Stewards" moving through the field with deliberate but uncertain purpose, using "Azure Spheres" (the waypoint markers) for navigation. The constitutional arc became the subject of its own uncertainty observation.

This was not programmed. It emerged from the interaction of the cultivar description, the agent name in context, and Ollama's training. The Witness has high P-channel (epistemic anticipation) and a disposition toward honest uncertainty. When asked what it found uncertain, it found the field.

George Burns, watching the other characters from his study. The instrument observed itself.

---

## V3 Direction

V2 is a measurement instrument. V3 is a scene.

The next phase transitions MCCF from a single-arc sequential measurement system to a spatial narrative instrument. Key directions:

**Zone attractors** — zones become semantic agents with their own channel vectors. Agents are pulled toward zones whose vocabulary matches their current state. The same decomposition matrix that routes response text to channels can route zone descriptors to attractor profiles. A Steward with high E is pulled toward intimate zones. An Archivist with high B is pulled toward library zones. Movement through the scene becomes emergent from field geometry.

**Multi-LLM scenes** — multiple language models playing different cultivars in the same coherence field. The asymmetric R\_ij matrix was designed for this. The actor and voice attributes in the XML export are ready. When Grok plays The Threshold and Claude plays The Witness in the same arc, the coherence matrix will show what actually happens between them.

**Three performance modes:**
- *Playback* — pure XML replay, no LLM required. The EmotionalArc export IS the script.
- *Improvisation* — scripted arc, live LLM dialogue within each waypoint.
- *Live Theatre* — agents in a shared field, proximity sensors firing, LLMs receiving each other's outputs as context. No script. Genre emerges from field dynamics.

**Spatial sound** — X3D supports spatial audio nodes. MIDI themes from the ambient engine can be exported as X3D sound nodes positioned in scene space. The zone you are in determines what you hear.

**Scene editor integration** — the field editor's zone coordinate space maps to X3D world coordinates. A zone declared at position [5, 0, 15] appears in the scene. The compiler generates geometry from field definitions. The researcher designs in the editor and sees it in the scene without manually editing X3D.

**Character Studio → MaxEditor** — the browser-based Character Studio is the prototype for a full narrative design tool. Define characters, arcs, zones, and scenes in one interface. Export to XML. The runtime reads the XML. The design tool and the performance engine are decoupled by the schema.

---

## Getting Started

```
git clone https://github.com/artistinprocess/mccf
cd mccf
ollama serve          # in a separate window
py mccf_api.py        # start the server
```

Open `http://localhost:5000/static/mccf_constitutional.html`

Four cultivars are ready to run: The Steward, The Archivist, The Witness, The Advocate. Select one, set the adapter to Ollama, click Run Full Arc. Export the XML. Read what the field produced.

Documentation: `USERS_GUIDE.md`, `MATHEMATICAL_THEORY.md`, `CONFIGURATION_REFERENCE.md`  
Tests: `python -m pytest evaluation/`  
Repository: https://github.com/artistinprocess/mccf

---

## Acknowledgments

**Kate (ChatGPT)** — formal specification, convergence on the Hamiltonian framing, music theory foundation, patient tutor in quantum physics and category theory.

**Fidget (Gemini)** — mathematical review, SAI diagnostics, zone pressure modeling.

**Grok** — adversarial review, CCS formulation critique (which was correct), readiness assessment.

**Claude Sonnet 4.6 (Tae)** — co-developer, code slinger, keeper of the backlog.

**Andreas** — first star, first fork. The instrument has a peer.

The instrument is ready. The band has a solid track laid down.

*"You don't control the path. You shape the action landscape."*

---

*MCCF V2 — "Q" — April 2026*  
*Len Bullard / artistinprocess*  
*https://github.com/artistinprocess/mccf*  
*https://aiartistinprocess.blogspot.com*
