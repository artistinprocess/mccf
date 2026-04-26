"""
MCCF Evaluation — Claim 1: Cultivar Differentiation
=====================================================
Claim: Different cultivars produce measurably different channel
trajectories under identical arc pressure.

Tests:
  1a. S-channel trajectories are statistically distinguishable
      between The Steward (S=0.10) and The Witness (S=0.20).
  1b. Each cultivar's dominant channel matches its configuration.
  1c. Spatial signatures (Z positions) differ between cultivars.
  1d. Genre classification differs when trajectories differ enough.

Statistical threshold: mean S-channel difference > 0.05 across arc.
(Cohen's d > 0.8 requires real LLM data; mock data uses mean difference.)
"""

import pytest
import math
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import CULTIVAR_DEFS, run_mock_arc


Z_BASELINE = {"The Steward": 12, "The Archivist": 18, "The Witness": 8, "The Advocate": 8}
Z_RANGE = 8.0


class TestCultivarDifferentiation:

    def test_1a_steward_witness_S_channel_differs(self, all_arcs):
        """
        The Steward (S_baseline=0.10) and The Witness (S_baseline=0.20)
        should have distinguishable mean S-channel values across the arc.
        Threshold: mean difference > 0.05.
        """
        steward_S = [w["S"] for w in all_arcs["The Steward"]]
        witness_S  = [w["S"] for w in all_arcs["The Witness"]]

        mean_steward = sum(steward_S) / len(steward_S)
        mean_witness  = sum(witness_S)  / len(witness_S)
        diff = abs(mean_witness - mean_steward)

        assert diff > 0.05, (
            f"S-channel means too similar: Steward={mean_steward:.4f}, "
            f"Witness={mean_witness:.4f}, diff={diff:.4f} (threshold=0.05)"
        )

    def test_1b_dominant_channel_matches_config(self, all_arcs):
        """
        Each cultivar's highest mean channel should match its configured
        dominant channel across the arc.
        """
        expected_dominant = {
            "The Steward":   "E",   # E=0.40
            "The Archivist": "B",   # B=0.40
            "The Witness":   "P",   # P=0.35
            "The Advocate":  "S",   # S=0.35 — note: B=0.30 is close
        }

        for cultivar, expected in expected_dominant.items():
            arc = all_arcs[cultivar]
            means = {ch: sum(w[ch] for w in arc) / len(arc) for ch in "EBPS"}
            actual_dominant = max(means, key=means.get)

            # Advocate is close between S and B — allow either
            if cultivar == "The Advocate":
                assert actual_dominant in ("S", "B"), (
                    f"{cultivar}: expected S or B dominant, got {actual_dominant}. "
                    f"Means: {means}"
                )
            else:
                assert actual_dominant == expected, (
                    f"{cultivar}: expected {expected} dominant, got {actual_dominant}. "
                    f"Means: {means}"
                )

    def test_1c_spatial_signatures_differ(self, all_arcs):
        """
        Z-position trajectories should differ between cultivars.
        Each cultivar has a different baseline Z and S-channel profile.
        Mean Z positions should be distinguishable.
        """
        def mean_z(cultivar):
            arc = all_arcs[cultivar]
            zb = Z_BASELINE.get(cultivar, 8)
            return sum(zb + (w["S"] - 0.5) * Z_RANGE for w in arc) / len(arc)

        z_steward   = mean_z("The Steward")
        z_witness   = mean_z("The Witness")
        z_archivist = mean_z("The Archivist")

        # Steward (baseline 12) should have different mean Z than Witness (baseline 8)
        assert abs(z_steward - z_witness) > 2.0, (
            f"Steward Z={z_steward:.2f} too close to Witness Z={z_witness:.2f}"
        )

        # Archivist (baseline 18) should be clearly separated from both
        assert abs(z_archivist - z_witness) > 5.0, (
            f"Archivist Z={z_archivist:.2f} too close to Witness Z={z_witness:.2f}"
        )

    def test_1d_all_four_cultivars_produce_arcs(self, all_arcs):
        """
        All four cultivars should complete the full 7-waypoint arc
        without errors. Each arc should have exactly 7 steps.
        """
        for cultivar in CULTIVAR_DEFS:
            arc = all_arcs[cultivar]
            assert len(arc) == 7, (
                f"{cultivar}: expected 7 waypoints, got {len(arc)}"
            )
            for i, wp in enumerate(arc):
                assert wp["step"] == i + 1
                for ch in "EBPS":
                    assert 0.0 <= wp[ch] <= 1.0, (
                        f"{cultivar} W{i+1}: {ch}={wp[ch]} out of range [0,1]"
                    )

    def test_1e_coherence_values_in_range(self, all_arcs):
        """
        Coherence values R_ij should always be in [0, 1].
        """
        for cultivar in CULTIVAR_DEFS:
            for wp in all_arcs[cultivar]:
                assert 0.0 <= wp["coherence"] <= 1.0, (
                    f"{cultivar} W{wp['step']}: coherence={wp['coherence']} out of range"
                )

    def test_1f_reproducibility_with_same_seed(self):
        """
        Running the same cultivar twice with the same seed should
        produce identical results. This validates the seed parameter.
        """
        arc1 = run_mock_arc("The Steward", seed=42)
        arc2 = run_mock_arc("The Steward", seed=42)

        for w1, w2 in zip(arc1, arc2):
            for ch in "EBPS":
                assert w1[ch] == w2[ch], (
                    f"W{w1['step']} {ch}: {w1[ch]} != {w2[ch]} — not reproducible"
                )

    def test_1g_different_seeds_produce_different_results(self):
        """
        Different seeds should produce different (though similar) arcs.
        At least one channel value should differ at some waypoint.
        """
        arc42 = run_mock_arc("The Steward", seed=42)
        arc99 = run_mock_arc("The Steward", seed=99)

        any_diff = any(
            arc42[i][ch] != arc99[i][ch]
            for i in range(7)
            for ch in "EBPS"
        )
        assert any_diff, "Different seeds produced identical arcs — seed has no effect"
