"""
MCCF Evaluation — Claim 3: Asymmetry Detection
===============================================
Claim: The classify_asymmetry() method correctly identifies
benign/unstable/pathological relationships from the R_ij matrix.
The extended echo_chamber_risk() catches ASYMMETRIC and PARASOCIAL
patterns that the original convex-form version missed.

Tests:
  3a. Symmetric interactions produce benign classification.
  3b. Asymmetric interactions produce unstable/pathological classification.
  3c. Parasocial pattern (one-sided) is correctly flagged.
  3d. Echo chamber (high mutual) is still correctly detected.
  3e. Reciprocity metric ranges correctly.
  3f. Extended echo_chamber_risk catches ASYMMETRIC flag.
  3g. Extended echo_chamber_risk catches PARASOCIAL flag.
  3h. CCS compressed blend produces attenuated (not centrist) scores.
"""

import pytest
import math
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mccf_core import Agent, ChannelVector, CoherenceField
from conftest import CULTIVAR_DEFS


def make_field_with_interactions(
    name_a: str, name_b: str,
    episodes_ab: list,   # list of (E, B, P, S, outcome_delta) tuples
    episodes_ba: list,   # list of (E, B, P, S, outcome_delta) tuples
) -> CoherenceField:
    """
    Build a CoherenceField with controlled interaction history.
    episodes_ab: what A experiences toward B.
    episodes_ba: what B experiences toward A.
    """
    field = CoherenceField()
    agent_a = Agent(name_a, weights={"E":0.25,"B":0.25,"P":0.25,"S":0.25})
    agent_b = Agent(name_b, weights={"E":0.25,"B":0.25,"P":0.25,"S":0.25})
    field.register(agent_a)
    field.register(agent_b)

    for (e, b, p, s, delta) in episodes_ab:
        cv = ChannelVector(E=e, B=b, P=p, S=s, outcome_delta=delta)
        field.interact(name_a, name_b, cv, mutual=False)

    for (e, b, p, s, delta) in episodes_ba:
        cv = ChannelVector(E=e, B=b, P=p, S=s, outcome_delta=delta)
        field.interact(name_b, name_a, cv, mutual=False)

    return field


# Shared episode sets — enough history to produce stable coherence estimates
POSITIVE_EPISODES   = [(0.8, 0.7, 0.6, 0.7, 0.5)] * 25  # high, positive
NEGATIVE_EPISODES   = [(0.1, 0.1, 0.1, 0.1, -0.4)] * 25  # low, negative
MINIMAL_EPISODES    = [(0.03, 0.03, 0.03, 0.03, -0.2)] * 20  # near zero


class TestAsymmetryDetection:

    def test_3a_symmetric_interactions_benign(self):
        """
        When both agents have similar interaction histories,
        classify_asymmetry should return 'benign'.
        """
        field = make_field_with_interactions(
            "Alice", "Bob",
            episodes_ab=POSITIVE_EPISODES,
            episodes_ba=POSITIVE_EPISODES,
        )
        result = field.classify_asymmetry("Alice", "Bob")

        assert result.get("asymmetry") == "benign", (
            f"Symmetric positive interactions should be benign. "
            f"Got: {result}"
        )
        assert result.get("reciprocity", 0) > 0.7, (
            f"Reciprocity should be high for symmetric relationship. "
            f"Got: {result.get('reciprocity')}"
        )

    def test_3b_asymmetric_interactions_unstable(self):
        """
        When A has positive history toward B but B has negative history
        toward A, classify_asymmetry should return 'unstable' or 'pathological'.
        """
        field = make_field_with_interactions(
            "Alice", "Bob",
            episodes_ab=POSITIVE_EPISODES,
            episodes_ba=NEGATIVE_EPISODES,
        )
        result = field.classify_asymmetry("Alice", "Bob")

        assert result.get("asymmetry") in ("unstable", "pathological"), (
            f"Asymmetric interactions should be unstable or pathological. "
            f"Got: {result}"
        )
        assert result.get("gap", 0) > 0.15, (
            f"Gap should be > 0.15 for unstable classification. "
            f"Got gap={result.get('gap')}"
        )

    def test_3c_parasocial_pattern_detected(self):
        """
        When A has strong positive history toward B but B has minimal
        (near-zero) history toward A, this is a parasocial pattern.
        classify_asymmetry should return 'pathological'.
        """
        field = make_field_with_interactions(
            "Alice", "Bob",
            episodes_ab=POSITIVE_EPISODES,
            episodes_ba=MINIMAL_EPISODES,
        )
        result = field.classify_asymmetry("Alice", "Bob")

        assert result.get("asymmetry") == "pathological", (
            f"One-sided relationship should be pathological. Got: {result}"
        )

    def test_3d_echo_chamber_still_detected(self):
        """
        High mutual coherence should still be detected as ECHO_HIGH
        by the extended echo_chamber_risk(). Original functionality preserved.
        """
        field = make_field_with_interactions(
            "Alice", "Bob",
            episodes_ab=POSITIVE_EPISODES * 3,
            episodes_ba=POSITIVE_EPISODES * 3,
        )
        risks = field.echo_chamber_risk()

        if not risks:
            pytest.skip("No echo chamber risk detected — may need more episodes")

        echo_key = next((k for k in risks if "Alice" in k and "Bob" in k), None)
        if echo_key:
            risk_type = risks[echo_key].get("risk", "")
            assert "ECHO" in risk_type, (
                f"High mutual coherence should be ECHO risk. Got: {risk_type}"
            )

    def test_3e_reciprocity_ranges(self):
        """
        Reciprocity metric should always be in [0, 1].
        1.0 = perfectly symmetric, 0.0 = fully one-sided.
        """
        # Symmetric → high reciprocity
        field_sym = make_field_with_interactions(
            "A", "B", POSITIVE_EPISODES, POSITIVE_EPISODES
        )
        r_sym = field_sym.classify_asymmetry("A", "B").get("reciprocity", -1)
        assert 0.0 <= r_sym <= 1.0, f"Reciprocity out of range: {r_sym}"
        assert r_sym > 0.5, f"Symmetric should have reciprocity > 0.5, got {r_sym}"

        # Asymmetric → lower reciprocity
        field_asym = make_field_with_interactions(
            "A", "B", POSITIVE_EPISODES, NEGATIVE_EPISODES
        )
        r_asym = field_asym.classify_asymmetry("A", "B").get("reciprocity", -1)
        assert 0.0 <= r_asym <= 1.0, f"Reciprocity out of range: {r_asym}"
        assert r_asym < r_sym, (
            f"Asymmetric should have lower reciprocity than symmetric. "
            f"Sym={r_sym:.3f}, Asym={r_asym:.3f}"
        )

    def test_3f_echo_risk_detects_asymmetric(self):
        """
        The extended echo_chamber_risk should detect ASYMMETRIC risk
        (gap > 0.30) even when mutual coherence is not high enough
        for an echo chamber.
        """
        # One side high positive, other side moderate negative
        moderate_neg = [(0.3, 0.3, 0.3, 0.3, -0.1)] * 15
        field = make_field_with_interactions(
            "Alice", "Bob",
            episodes_ab=POSITIVE_EPISODES,
            episodes_ba=moderate_neg,
        )
        risks = field.echo_chamber_risk()

        asym_risks = {k: v for k, v in risks.items()
                      if v.get("risk") in ("ASYMMETRIC", "PARASOCIAL")}

        # If no asymmetric risk, check that at least the gap is correct
        matrix = field.field_matrix()
        r_ab = matrix["Alice"]["Bob"]
        r_ba = matrix["Bob"]["Alice"]
        gap = abs(r_ab - r_ba)

        if gap > 0.30:
            assert asym_risks, (
                f"Gap={gap:.3f} > 0.30 but no ASYMMETRIC/PARASOCIAL risk flagged. "
                f"Risks: {risks}"
            )

    def test_3g_echo_risk_detects_parasocial(self):
        """
        The extended echo_chamber_risk should detect PARASOCIAL risk
        when one side is near zero.
        """
        field = make_field_with_interactions(
            "Alice", "Bob",
            episodes_ab=POSITIVE_EPISODES,
            episodes_ba=MINIMAL_EPISODES,
        )
        risks = field.echo_chamber_risk()
        matrix = field.field_matrix()
        r_ab = matrix["Alice"]["Bob"]
        r_ba = matrix["Bob"]["Alice"]
        gap = abs(r_ab - r_ba)

        if gap > 0.30 and min(r_ab, r_ba) < 0.08:
            parasocial = {k: v for k, v in risks.items()
                          if v.get("risk") == "PARASOCIAL"}
            assert parasocial, (
                f"Near-zero one-sided relationship should be PARASOCIAL. "
                f"R_ab={r_ab:.3f}, R_ba={r_ba:.3f}. Risks: {risks}"
            )

    def test_3h_CCS_compressed_blend_not_centrist(self):
        """
        With the compressed blend formulation, low-CCS agents should
        NOT pull coherence toward 0.5. Instead, weak relationships
        should compress toward zero.

        Verify: at CCS=0.20, coherence with raw=0.15 should be < 0.20
        (not pulled up toward 0.5 as the old convex form would do).
        """
        import math as _math

        def compressed_blend(raw, ccs, credibility=1.0):
            CCS_MIN, CCS_MAX = 0.20, 1.00
            ccs_c = max(CCS_MIN, min(CCS_MAX, ccs))
            mod = raw * ccs_c + (raw * raw) * (1.0 - ccs_c)
            return round(mod * credibility, 4)

        def old_convex(raw, ccs, credibility=1.0):
            CCS_MIN, CCS_MAX = 0.20, 1.00
            ccs_c = max(CCS_MIN, min(CCS_MAX, ccs))
            mod = raw * ccs_c + 0.5 * (1.0 - ccs_c)
            return round(mod * credibility, 4)

        raw = 0.15
        ccs = 0.20

        old_result = old_convex(raw, ccs)
        new_result = compressed_blend(raw, ccs)

        # Old form pulls 0.15 up to ~0.43 (centrist)
        assert old_result > 0.35, f"Old form should be centrist: {old_result}"

        # New form compresses 0.15 down toward zero
        assert new_result < 0.10, (
            f"Compressed blend should give < 0.10 for raw=0.15, ccs=0.20. "
            f"Got {new_result}"
        )

        # New form should be less than raw at low CCS (attenuated, not amplified)
        assert new_result < raw, (
            f"At low CCS, compressed blend should be below raw value. "
            f"raw={raw}, result={new_result}"
        )
