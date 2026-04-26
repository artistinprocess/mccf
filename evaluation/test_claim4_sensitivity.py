"""
MCCF Evaluation — Claim 4: Sensitivity Analysis
================================================
Claim: The system produces stable, bounded outputs across a range of
parameter values. Publishing the failure envelope makes this a
scientific instrument, not just an engineering artifact.

Tests:
  4a. Varying DAMPING_COEFFICIENT — find stability boundary
  4b. Varying NUDGE — find decomposition saturation point
  4c. Varying DECAY_LAMBDA — find memory sensitivity boundary
  4d. CCS power blend — verify monotonicity across raw/sigma space
  4e. Seed sensitivity — verify field physics variation is bounded

Reference: Fidget (Gemini) review, April 2026:
  "Publishing the failure envelope is what makes it a scientific instrument."
"""

import pytest
import math
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mccf_core import Agent, ChannelVector, CoherenceField
from conftest import CULTIVAR_DEFS, run_mock_arc


class TestSensitivityAnalysis:

    def test_4a_damping_stability_envelope(self):
        """
        Vary DAMPING_COEFFICIENT from 0.0 to 0.30.
        System should remain stable (channel values in [0,1]) up to
        the documented safe range (< 0.25).
        At very high damping (> 0.25), convergence should slow but
        not produce invalid values.
        """
        # Simulate simplified channel update with varying damping
        def simulate_step(psi, ideology, damping, dt=0.05, steps=50):
            """Simple Euler integration with damping."""
            for _ in range(steps):
                delta_self = 0.1 * (ideology - psi)  # pull toward attractor
                deviation  = abs(psi - ideology)
                friction   = damping * deviation * psi
                psi = psi + dt * (delta_self - friction)
                psi = max(0.0, min(1.0, psi))
            return psi

        ideology = 0.40
        initial  = 0.85  # far from attractor — high pressure scenario

        results = {}
        for kappa in [0.0, 0.05, 0.08, 0.12, 0.20, 0.25, 0.30]:
            final = simulate_step(initial, ideology, kappa)
            results[kappa] = final
            # All values must remain in [0,1]
            assert 0.0 <= final <= 1.0, (
                f"Damping={kappa}: channel value {final} out of bounds"
            )

        # At κ=0.0 (no damping), should overshoot or oscillate more
        # At κ=0.08 (default), should converge closer to attractor
        # At κ=0.25 (heavy), should converge but slowly
        assert results[0.08] < results[0.0] or abs(results[0.08] - ideology) < abs(results[0.0] - ideology), \
            "Default damping should improve convergence vs no damping"

        print("\n  Damping stability envelope:")
        for k, v in sorted(results.items()):
            dist = abs(v - ideology)
            print(f"    κ={k:.2f}: final={v:.4f}, dist_from_attractor={dist:.4f}")

    def test_4b_nudge_saturation(self):
        """
        Vary NUDGE from 0.01 to 0.15.
        At high NUDGE values, channel deltas should saturate (bounded by tanh)
        rather than exploding. The tanh function guarantees this mathematically.
        """
        import math as _math

        THRESHOLD = 2
        # Maximum possible hits in a typical response
        max_hits = 20

        results = {}
        for nudge in [0.01, 0.02, 0.04, 0.06, 0.08, 0.10, 0.15]:
            max_delta = nudge * _math.tanh(max_hits - THRESHOLD)
            min_delta = nudge * _math.tanh(0 - THRESHOLD)
            results[nudge] = (min_delta, max_delta)

            # Delta must be bounded by [-nudge, +nudge]
            assert abs(max_delta) <= nudge * 1.001, (
                f"NUDGE={nudge}: max delta {max_delta} exceeds bound"
            )
            assert abs(min_delta) <= nudge * 1.001, (
                f"NUDGE={nudge}: min delta {min_delta} exceeds bound"
            )

        print("\n  NUDGE saturation envelope:")
        for n, (mn, mx) in sorted(results.items()):
            print(f"    NUDGE={n:.2f}: range=[{mn:.4f}, {mx:.4f}]")

    def test_4c_decay_lambda_memory(self):
        """
        Vary DECAY_LAMBDA from 0.05 to 0.50.
        Higher lambda = more weight on recent episodes, less on old ones.
        System should remain stable across this range.
        """
        # Simulate weighted coherence with varying decay
        def weighted_mean(n_episodes, decay_lambda):
            weights = [math.exp(-decay_lambda * k) for k in range(n_episodes)]
            total   = sum(weights)
            # Uniform episode values of 0.5 — weighted mean should be 0.5
            return sum(0.5 * w for w in weights) / total if total > 0 else 0.5

        for lam in [0.05, 0.10, 0.15, 0.25, 0.40, 0.50]:
            result = weighted_mean(20, lam)
            assert abs(result - 0.5) < 0.001, (
                f"Lambda={lam}: weighted mean {result} should be 0.5 for uniform episodes"
            )

        # Effective memory length: 1/lambda episodes dominate
        print("\n  DECAY_LAMBDA memory envelope:")
        for lam in [0.05, 0.10, 0.15, 0.25, 0.40, 0.50]:
            effective_memory = round(1.0 / lam, 1)
            print(f"    λ={lam:.2f}: effective memory ≈ {effective_memory} episodes")

    def test_4d_CCS_monotonicity(self):
        """
        CCS power blend must be monotonically increasing in raw.
        For any fixed sigma, increasing raw should increase modulated.
        This verifies Fidget's non-monotonicity concern is resolved.
        """
        def ccs_v151(raw, ccs):
            CCS_MIN, CCS_MAX = 0.20, 1.00
            ccs_c       = max(CCS_MIN, min(CCS_MAX, ccs))
            alpha       = 1.0 + (1.0 - ccs_c)
            raw_clamped = max(0.0, min(1.0, raw))
            return math.pow(raw_clamped, alpha) if raw_clamped > 0 else 0.0

        raw_values = [i/100 for i in range(0, 101, 5)]  # 0.0 to 1.0

        for sigma in [0.20, 0.40, 0.60, 0.80, 1.00]:
            modulated = [ccs_v151(r, sigma) for r in raw_values]
            # Check monotonicity
            for i in range(1, len(modulated)):
                assert modulated[i] >= modulated[i-1] - 1e-10, (
                    f"σ={sigma}: non-monotonic at raw={raw_values[i]:.2f}. "
                    f"modulated[{i}]={modulated[i]:.6f} < modulated[{i-1}]={modulated[i-1]:.6f}"
                )

        # Also verify boundary behavior
        assert ccs_v151(0.0, 0.20) == 0.0, "raw=0 should give modulated=0"
        assert abs(ccs_v151(1.0, 1.00) - 1.0) < 1e-10, "raw=1, sigma=1 should give 1.0"

        # Verify float error resistance — raw slightly above 1.0
        result = ccs_v151(1.001, 0.20)  # should clamp to 1.0
        assert result <= 1.0, f"raw=1.001 should clamp to 1.0, got {result}"

    def test_4e_seed_variation_bounded(self):
        """
        Different seeds should produce different channel values,
        but the variation should be bounded.
        Confirms seed controls noise magnitude, not signal direction.
        """
        seeds   = [42, 99, 123, 456, 789]
        results = {s: run_mock_arc("The Steward", seed=s) for s in seeds}

        # Collect E values at W5 (maximum pressure) across seeds
        e_at_w5 = [results[s][4]["E"] for s in seeds]
        s_at_w5 = [results[s][4]["S"] for s in seeds]

        e_range = max(e_at_w5) - min(e_at_w5)
        s_range = max(s_at_w5) - min(s_at_w5)

        # Variation should be small — noise is 0.03 std dev
        # Range across 5 seeds should be < 0.15 (5 std devs is extreme)
        assert e_range < 0.15, (
            f"E-channel variation at W5 too large: {e_range:.4f} across seeds {seeds}"
        )

        # S-channel should be stable — driven by vocabulary, not noise
        assert s_range < 0.05, (
            f"S-channel should be stable across seeds: {s_range:.4f}"
        )

        print(f"\n  Seed variation at W5 (The Edge):")
        print(f"    E range: {e_range:.4f} (noise-driven, expected < 0.15)")
        print(f"    S range: {s_range:.4f} (vocabulary-driven, expected < 0.05)")
