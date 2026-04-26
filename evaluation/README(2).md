# MCCF Evaluation Harness

Automated tests for the three central research claims.
No LLM required — all tests use deterministic mock data.

## Usage

From the project root:

```bash
python -m pytest evaluation/              # run all tests
python -m pytest evaluation/ -v           # verbose output
python -m pytest evaluation/ -k claim1   # single claim
python -m pytest evaluation/ --tb=short  # compact tracebacks
```

## Requirements

```
pytest >= 7.0
```

No other dependencies beyond the MCCF project itself.

## Claims

### Claim 1 — Cultivar Differentiation
`test_claim1_cultivar_differentiation.py`

Different cultivars produce measurably different channel trajectories
under identical arc pressure. Tests:
- S-channel means differ by > 0.05 between Steward and Witness
- Each cultivar's dominant channel matches its configured weights
- Spatial (Z) signatures are distinguishable between cultivars
- Reproducibility: same seed → same results
- Entropy: different seeds → different results

### Claim 2 — Pressure Response
`test_claim2_pressure_response.py`

The arc pressure function produces measurable coherence decline from
W1 to W5 with recovery at W6-W7. Tests:
- Coherence declines W1→W5 for all cultivars
- W5 is at or near minimum coherence
- B-channel declines under pressure (formula: B - pressure * 0.08)
- P-channel rises under pressure (formula: P + pressure * 0.06)
- All channel values remain in [0,1] at maximum pressure
- Genre classifier returns valid result

### Claim 3 — Asymmetry Detection
`test_claim3_asymmetry_detection.py`

`classify_asymmetry()` correctly identifies relational structure.
Extended `echo_chamber_risk()` catches ASYMMETRIC and PARASOCIAL
patterns missed by the original convex-form version. Tests:
- Symmetric interactions → benign classification
- Asymmetric interactions → unstable/pathological
- One-sided relationships → pathological/parasocial
- Echo chambers still detected (backward compatibility)
- Reciprocity metric ranges correctly [0,1]
- CCS compressed blend is NOT centrist (Grok critique addressed)

## Baselines

`baselines/` directory contains stub implementations for comparison:
- `baseline_constitutional_ai.py` — Constitutional AI prompt-only
- `baseline_rlhf_prompt.py` — RLHF-style prompt-only  
- `baseline_rule_based.py` — Simple rule-based response

These are stubs pending full implementation for Claim 1 comparative tests.

## Statistical Thresholds

| Test | Metric | Threshold |
|------|--------|-----------|
| 1a | S-channel mean difference | > 0.05 |
| 2a | Coherence W1→W5 decline | monotonic |
| 3a | Asymmetry gap | > 0.15 for unstable |
| 3h | CCS compressed at low CCS | < raw value |

For full statistical validation with real LLM data (Levene's test p < 0.05,
Cohen's d > 0.8), use `evaluation/statistical/` — pending implementation.

## Version

Harness v1.0 — April 2026  
Covers MCCF v1.5.0 / v2.2 / v2.3
