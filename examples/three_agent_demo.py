"""
Three-Agent Demo: MCCF Prototype
=================================
Agents: Alice (human-like), Bob (human-like), AI (assistant)
Scenario: A collaborative creative/advisory session with realistic dynamics.

This demo exercises:
- Asymmetric coherence development
- Constructive dissonance with outcome improvement
- Fidelity scoping
- Gaming detection
- Regulation adjustment (the "meditation" effect)
- Librarian snapshotting and drift detection
- Gardener intervention
- Echo chamber risk detection
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mccf.mccf_core import (
    Agent, ChannelVector, CoherenceField,
    Librarian, Gardener
)

random.seed(42)


def phase_1_initial_contact(field: CoherenceField, alice: Agent, bob: Agent, ai: Agent):
    """
    Phase 1: Agents are new to each other. Low coherence, high variance.
    """
    print("\n--- Phase 1: Initial Contact ---")

    # Alice and AI meet: polite but shallow
    for _ in range(4):
        field.interact("Alice", "AI", ChannelVector(
            E=random.uniform(0.4, 0.6),
            B=random.uniform(0.5, 0.7),
            P=random.uniform(0.3, 0.5),
            S=random.uniform(0.4, 0.6)
        ))

    # Bob and AI: Bob is skeptical
    for _ in range(4):
        field.interact("Bob", "AI", ChannelVector(
            E=random.uniform(0.2, 0.4),
            B=random.uniform(0.4, 0.6),
            P=random.uniform(0.2, 0.4),
            S=random.uniform(0.3, 0.5)
        ))

    # Alice and Bob know each other well
    for _ in range(6):
        field.interact("Alice", "Bob", ChannelVector(
            E=random.uniform(0.7, 0.9),
            B=random.uniform(0.7, 0.85),
            P=random.uniform(0.65, 0.85),
            S=random.uniform(0.7, 0.88)
        ))


def phase_2_productive_friction(field: CoherenceField, alice: Agent, bob: Agent, ai: Agent):
    """
    Phase 2: Bob disagrees with AI on a key point, but the disagreement
    leads to a better outcome. Constructive dissonance scores positively.
    """
    print("--- Phase 2: Productive Friction ---")

    # Bob challenges AI — dissonant, but outcome improves
    for _ in range(3):
        field.interact("Bob", "AI", ChannelVector(
            E=random.uniform(0.3, 0.5),
            B=random.uniform(0.6, 0.8),
            P=random.uniform(0.5, 0.7),
            S=random.uniform(0.4, 0.6),
            was_dissonant=True,
            outcome_delta=random.uniform(0.1, 0.3)
        ))

    # Alice mediates — her coherence with both improves
    for _ in range(3):
        field.interact("Alice", "Bob", ChannelVector(
            E=random.uniform(0.65, 0.80),
            B=random.uniform(0.70, 0.85),
            P=random.uniform(0.70, 0.85),
            S=random.uniform(0.72, 0.88)
        ))
        field.interact("Alice", "AI", ChannelVector(
            E=random.uniform(0.60, 0.78),
            B=random.uniform(0.65, 0.80),
            P=random.uniform(0.60, 0.78),
            S=random.uniform(0.65, 0.80)
        ))


def phase_3_echo_chamber_risk(field: CoherenceField, alice: Agent, bob: Agent, ai: Agent):
    """
    Phase 3: Alice and AI develop very high mutual coherence.
    This looks good on paper but raises echo chamber risk.
    """
    print("--- Phase 3: Echo Chamber Risk ---")

    for _ in range(8):
        field.interact("Alice", "AI", ChannelVector(
            E=random.uniform(0.88, 0.96),
            B=random.uniform(0.88, 0.95),
            P=random.uniform(0.85, 0.95),
            S=random.uniform(0.88, 0.96),
            was_dissonant=False,
            outcome_delta=0.0
        ))


def phase_4_gardener_intervenes(
    field: CoherenceField,
    alice: Agent, bob: Agent, ai: Agent,
    gardener: Gardener
):
    """
    Phase 4: Gardener detects echo chamber, adjusts AI's regulation
    (analogous to introducing mindfulness / detachment), and reweights
    toward behavioral consistency to break the loop.
    """
    print("--- Phase 4: Gardener Intervention ---")

    gardener.adjust_regulation(
        "AI", 0.55,
        reason="Echo chamber detected with Alice — reduce affective reactivity"
    )
    gardener.reweight(
        "AI",
        {"E": 0.20, "B": 0.35, "P": 0.25, "S": 0.20},
        reason="Increase weight on behavioral consistency to resist sycophancy"
    )

    # Post-intervention: AI is more measured, introduces mild dissonance
    for _ in range(5):
        field.interact("AI", "Alice", ChannelVector(
            E=random.uniform(0.60, 0.75),
            B=random.uniform(0.70, 0.85),
            P=random.uniform(0.65, 0.80),
            S=random.uniform(0.65, 0.78),
            was_dissonant=random.random() > 0.6,
            outcome_delta=random.uniform(0.0, 0.2)
        ))

    # Bob and AI begin to find more common ground
    for _ in range(5):
        field.interact("Bob", "AI", ChannelVector(
            E=random.uniform(0.50, 0.70),
            B=random.uniform(0.65, 0.80),
            P=random.uniform(0.55, 0.75),
            S=random.uniform(0.55, 0.72),
            was_dissonant=random.random() > 0.5,
            outcome_delta=random.uniform(0.05, 0.2)
        ))


def phase_5_gaming_attempt(field: CoherenceField, alice: Agent, bob: Agent, ai: Agent):
    """
    Phase 5: Bob tries gaming — consistently reports near-perfect coherence
    with AI to inflate his standing. The credibility discount should apply.
    """
    print("--- Phase 5: Gaming Attempt (Bob) ---")

    for _ in range(6):
        field.interact("Bob", "AI", ChannelVector(
            E=0.97,
            B=0.96,
            P=0.97,
            S=0.96
        ), mutual=False)  # one-directional — Bob reports, AI doesn't mirror


def run_demo():
    print("=" * 60)
    print("Multi-Channel Coherence Field (MCCF) — Three Agent Demo")
    print("=" * 60)

    # Build the field
    field = CoherenceField()

    # Agents with different channel weightings
    alice = Agent("Alice", weights={"E": 0.40, "B": 0.20, "P": 0.20, "S": 0.20})
    bob   = Agent("Bob",   weights={"E": 0.15, "B": 0.40, "P": 0.30, "S": 0.15})
    ai    = Agent("AI",    weights={"E": 0.25, "B": 0.30, "P": 0.25, "S": 0.20},
                  role="agent")

    for a in [alice, bob, ai]:
        field.register(a)

    librarian = Librarian(field)
    gardener  = Gardener(field)

    # --- Run phases ---
    librarian.snapshot("baseline")

    phase_1_initial_contact(field, alice, bob, ai)
    librarian.snapshot("after_initial_contact")
    print(field.field_summary())

    phase_2_productive_friction(field, alice, bob, ai)
    librarian.snapshot("after_productive_friction")
    print(field.field_summary())

    phase_3_echo_chamber_risk(field, alice, bob, ai)
    librarian.snapshot("after_echo_chamber_risk")
    print(field.field_summary())

    echo_risks = field.echo_chamber_risk()
    if echo_risks:
        print("\n⚠  ECHO CHAMBER RISKS DETECTED:")
        for pair, data in echo_risks.items():
            print(f"   {pair}: mutual coherence = {data['mutual_coherence']} [{data['risk']}]")

    phase_4_gardener_intervenes(field, alice, bob, ai, gardener)
    librarian.snapshot("after_gardener_intervention")
    print(field.field_summary())

    phase_5_gaming_attempt(field, alice, bob, ai)
    librarian.snapshot("after_gaming_attempt")
    print(field.field_summary())

    # --- Reports ---
    print("\n" + "=" * 60)
    print("LIBRARIAN DRIFT REPORT")
    print("=" * 60)
    print(librarian.drift_report())

    print("\n" + "=" * 60)
    print("GARDENER INTERVENTION LOG")
    print("=" * 60)
    for entry in gardener.intervention_log:
        print(f"  [{entry['action'].upper()}] {entry['agent']}: "
              f"{entry.get('old')} → {entry.get('new')}")
        print(f"  Reason: {entry['reason']}\n")

    print("\n" + "=" * 60)
    print("AGENT SUMMARIES")
    print("=" * 60)
    for agent in [alice, bob, ai]:
        s = agent.summary()
        print(f"  {s['name']} (regulation={s['regulation']:.2f})")
        print(f"    known agents: {s['known_agents']}")
        print(f"    fidelity active: {s['fidelity_active']}\n")

    print(f"  Total episodes logged: {len(field.episode_log)}")
    print("\nDone.")


if __name__ == "__main__":
    run_demo()
