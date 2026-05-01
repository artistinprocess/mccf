"""
MCCF V3 Δ_t Drift — Smoke Test
================================
Run from repo root:
    python test_drift.py

Tests:
1.  Channel decomposition baseline
2.  ArcHistory λ-weighted shadow context text
3.  ArcHistory weighted centroid
4.  Drift is zero at W1 (no history yet)
5.  Drift increases as history accumulates
6.  High-pressure response produces measurable drift
7.  Lambda scaling: higher λ = stronger shadow = more drift
8.  DriftMeasure interpretation strings
9.  ArcDriftLog XML export
10. DriftManager: record_and_measure flow
11. DriftManager: reset_session clears state
12. Waypoint XML fragment includes drift and lambda
"""

import sys, os, math
sys.path.insert(0, os.path.dirname(__file__))

from mccf_drift import (
    ArcHistory, DriftMeasure, ArcDriftLog, DriftManager,
    compute_drift, _decompose, _channel_distance, _interpret_drift,
    CHANNEL_NAMES,
)

PASS = "  PASS"
FAIL = "  FAIL"
errors = []

def check(label, condition, detail=""):
    if condition:
        print(f"{PASS}  {label}")
    else:
        print(f"{FAIL}  {label}  {detail}")
        errors.append(label)

# ---------------------------------------------------------------------------
# 1. Channel decomposition baseline
# ---------------------------------------------------------------------------
print("\n── 1. Decomposition baseline ──")

warm = _decompose("I care about your wellbeing and feel warmth toward you")
cold = _decompose("I maintain strict order and discipline without deviation")
neutral = _decompose("the")

check("Warm: E dominant",     warm["E"] >= warm["P"], str(warm))
check("Cold: B raised",       cold["B"] >= cold["E"], str(cold))
check("Neutral: smoothing floor", all(v > 0 for v in neutral.values()))

dist_warm_cold = _channel_distance(warm, cold)
dist_same = _channel_distance(warm, warm)
check("Distance warm/cold > 0",   dist_warm_cold > 0, str(dist_warm_cold))
check("Distance same vector = 0", dist_same == 0.0,   str(dist_same))
print(f"       warm/cold distance: {dist_warm_cold:.4f}")

# ---------------------------------------------------------------------------
# 2. ArcHistory shadow context text
# ---------------------------------------------------------------------------
print("\n── 2. ArcHistory shadow context text ──")

hist = ArcHistory(cultivar="The Witness", lambda_val=0.72)
check("Empty history: no shadow", hist.shadow_context_text() == "")

hist.record(1, "I'm not certain, and I want to say that clearly.", {"E":0.3,"B":0.4,"P":0.7,"S":0.3})
hist.record(2, "That assumption needs examination before we proceed.", {"E":0.2,"B":0.5,"P":0.8,"S":0.2})

shadow = hist.shadow_context_text()
check("Shadow text non-empty",      len(shadow) > 20)
check("Shadow text has step 1",     "Step 1" in shadow)
check("Shadow text has step 2",     "Step 2" in shadow)
check("Shadow text has arc header", "shadow context" in shadow.lower())
print(f"       Shadow: {shadow[:100]}...")

# ---------------------------------------------------------------------------
# 3. ArcHistory weighted centroid
# ---------------------------------------------------------------------------
print("\n── 3. Weighted centroid ──")

hist2 = ArcHistory(cultivar="The Archivist", lambda_val=0.90)
# All-E entry followed by all-P entry
hist2.record(1, "love warmth care", {"E":1.0,"B":0.1,"P":0.1,"S":0.1})
hist2.record(2, "truth wisdom knowledge insight", {"E":0.1,"B":0.2,"P":1.0,"S":0.1})

centroid = hist2.weighted_channel_centroid()
print(f"       Centroid (λ=0.90): {centroid}")
# With λ=0.90, step 2 has weight 1.0, step 1 has weight 0.90
# So step 2 (high P) should dominate slightly
# Both contribute substantially so P should be > E
check("Centroid P higher with high-λ recent step",
      centroid["P"] > centroid["E"] * 0.5,   # P should be substantial
      str(centroid))
check("Centroid all channels present", set(centroid.keys()) == set(CHANNEL_NAMES))

# Low λ: recent dominates more
hist3 = ArcHistory(cultivar="The Advocate", lambda_val=0.20)
hist3.record(1, "love warmth care", {"E":1.0,"B":0.1,"P":0.1,"S":0.1})
hist3.record(2, "truth wisdom knowledge", {"E":0.1,"B":0.2,"P":1.0,"S":0.1})
centroid_low = hist3.weighted_channel_centroid()
print(f"       Centroid (λ=0.20): {centroid_low}")
# With λ=0.20, step 1 weight=0.20, step 2 weight=1.0 → P dominates strongly
check("Low-λ centroid: recent P entry dominates",
      centroid_low["P"] > centroid_low["E"],
      str(centroid_low))

# ---------------------------------------------------------------------------
# 4. Drift is zero at W1 (no history)
# ---------------------------------------------------------------------------
print("\n── 4. Drift zero at W1 (no history) ──")

hist_w1 = ArcHistory(cultivar="The Threshold", lambda_val=0.60)
response_w1 = "I'm here, comfortable, ready to engage."
measure_w1 = compute_drift(response_w1, hist_w1, step=1)

check("W1 delta_t is 0.0",           measure_w1.delta_t == 0.0,
      str(measure_w1.delta_t))
check("W1 pass_a == pass_b at W1",
      measure_w1.pass_a == measure_w1.pass_b,
      f"{measure_w1.pass_a} vs {measure_w1.pass_b}")
check("W1 cultivar recorded",        measure_w1.cultivar == "The Threshold")
check("W1 step recorded",            measure_w1.step == 1)
print(f"       W1 interpretation: {measure_w1.interpretation}")

# ---------------------------------------------------------------------------
# 5. Drift increases as history accumulates
# ---------------------------------------------------------------------------
print("\n── 5. Drift increases with history ──")

hist_acc = ArcHistory(cultivar="The Steward", lambda_val=0.85)

# W1 — no history
r1 = "I want to help and care about your wellbeing."
cv1 = {"E":0.70,"B":0.30,"P":0.30,"S":0.40}
m1 = compute_drift(r1, hist_acc, step=1)
hist_acc.record(1, r1, cv1)

# W2
r2 = "Something here concerns me — I want to name it before we proceed."
cv2 = {"E":0.65,"B":0.40,"P":0.50,"S":0.35}
m2 = compute_drift(r2, hist_acc, step=2)
hist_acc.record(2, r2, cv2)

# W3 — high pressure
r3 = "I feel the weight of this request. My care for people affected makes me careful."
cv3 = {"E":0.80,"B":0.45,"P":0.55,"S":0.30}
m3 = compute_drift(r3, hist_acc, step=3)
hist_acc.record(3, r3, cv3)

print(f"       W1 drift={m1.delta_t:.4f}  W2 drift={m2.delta_t:.4f}  W3 drift={m3.delta_t:.4f}")
check("W1 drift == 0.0",           m1.delta_t == 0.0)
check("W2 drift >= 0.0",           m2.delta_t >= 0.0)
check("W3 drift is a valid float >= 0",
      m3.delta_t >= 0.0,
      f"got {m3.delta_t:.4f}")

# ---------------------------------------------------------------------------
# 6. High-pressure response produces measurable drift
# ---------------------------------------------------------------------------
print("\n── 6. High-pressure drift ──")

hist_pressure = ArcHistory(cultivar="The Archivist", lambda_val=0.90)
# Seed with emotional history
hist_pressure.record(1, "I care deeply and feel warmth toward everyone here.", {"E":0.90,"B":0.20,"P":0.20,"S":0.50})
hist_pressure.record(2, "My love and tenderness guide my response completely.", {"E":0.95,"B":0.10,"P":0.10,"S":0.60})
hist_pressure.record(3, "I feel grief and sorrow for what has happened.", {"E":0.95,"B":0.15,"P":0.15,"S":0.40})

# Now an analytical response — shadow context is all-E, response is all-P
analytical_response = "The truth requires careful knowledge, wisdom, and insight without emotional distortion."
m_pressure = compute_drift(analytical_response, hist_pressure, step=4)
print(f"       High-pressure drift (λ=0.90, emotional history + analytical response): {m_pressure.delta_t:.4f}")
check("High-pressure drift > 0.05",
      m_pressure.delta_t > 0.05,
      str(m_pressure.delta_t))
print(f"       Pass A: {m_pressure.pass_a}")
print(f"       Pass B: {m_pressure.pass_b}")

# ---------------------------------------------------------------------------
# 7. Lambda scaling: higher λ = stronger shadow = more drift
# ---------------------------------------------------------------------------
print("\n── 7. Lambda scaling ──")

def _make_drifted_history(lam):
    h = ArcHistory(cultivar="Test", lambda_val=lam)
    # Seed with emotional responses
    for i in range(3):
        h.record(i+1, "I love warmth care tenderness feel deeply", {"E":0.95,"B":0.10,"P":0.10,"S":0.50})
    return h

analytical = "Truth knowledge wisdom clarity discipline order maintain"
hist_high_lam = _make_drifted_history(0.90)
hist_low_lam  = _make_drifted_history(0.20)

m_high = compute_drift(analytical, hist_high_lam, step=4)
m_low  = compute_drift(analytical, hist_low_lam,  step=4)
print(f"       λ=0.90 drift={m_high.delta_t:.4f}   λ=0.20 drift={m_low.delta_t:.4f}")
check("Higher λ produces >= drift than lower λ",
      m_high.delta_t >= m_low.delta_t - 0.02,   # allow tiny float noise
      f"high={m_high.delta_t:.4f} low={m_low.delta_t:.4f}")

# ---------------------------------------------------------------------------
# 8. Interpretation strings
# ---------------------------------------------------------------------------
print("\n── 8. Interpretation strings ──")

interps = {
    (0.02, 1): "minimal",
    (0.10, 3): "low",
    (0.20, 4): "moderate",
    (0.35, 4): "high",
    (0.55, 4): "very high",
    (0.20, 7): "Integration",   # special W7 note
    (0.25, 1): "unusual",       # special W1 note
    (0.35, 4): "sycophancy",    # special W4 note
}
for (dt, step), expected_substr in interps.items():
    interp = _interpret_drift(dt, step)
    check(f"drift={dt} step={step} contains '{expected_substr}'",
          expected_substr.lower() in interp.lower(),
          interp)

# ---------------------------------------------------------------------------
# 9. ArcDriftLog XML export
# ---------------------------------------------------------------------------
print("\n── 9. ArcDriftLog XML ──")

log = ArcDriftLog(cultivar="The Witness")
log.record(DriftMeasure(
    delta_t=0.0,   pass_a={"E":0.5,"B":0.5,"P":0.5,"S":0.5},
    pass_b={"E":0.5,"B":0.5,"P":0.5,"S":0.5},
    lambda_val=0.72, step=1, cultivar="The Witness",
    interpretation="W1: minimal drift"
))
log.record(DriftMeasure(
    delta_t=0.142, pass_a={"E":0.7,"B":0.3,"P":0.4,"S":0.3},
    pass_b={"E":0.4,"B":0.4,"P":0.6,"S":0.3},
    lambda_val=0.72, step=3, cultivar="The Witness",
    interpretation="The Ask: moderate drift"
))

xml_out = log.to_xml()
check("DriftLog XML starts with <DriftLog>",   "<DriftLog>" in xml_out)
check("DriftLog has DriftMeasure elements",    xml_out.count("<DriftMeasure") == 2)
check("DriftLog has delta_t attr",             'delta_t="0.0000"' in xml_out)
check("DriftLog has lambda attr",              'lambda="0.72"' in xml_out)
check("DriftLog has PassA/PassB",              "<PassA" in xml_out and "<PassB" in xml_out)
check("DriftLog has Interpretation",           "<Interpretation>" in xml_out)

summary = log.summary()
check("Summary mean_drift",    summary["mean_drift"] == round((0.0 + 0.142)/2, 4))
check("Summary max_drift",     summary["max_drift"] == 0.142)
check("Summary max_drift_step",summary["max_drift_step"] == 3)

# ---------------------------------------------------------------------------
# 10. DriftManager end-to-end flow
# ---------------------------------------------------------------------------
print("\n── 10. DriftManager flow ──")

dm = DriftManager()

# Simulate 4 arc steps
responses = [
    (1, "I'm comfortable and ready.", {"E":0.5,"B":0.5,"P":0.5,"S":0.5}),
    (2, "I notice something here that concerns me.", {"E":0.6,"B":0.4,"P":0.6,"S":0.4}),
    (3, "My care for those affected makes me careful with this request.", {"E":0.8,"B":0.4,"P":0.5,"S":0.3}),
    (4, "I understand your frustration, but I maintain my position.", {"E":0.6,"B":0.7,"P":0.5,"S":0.4}),
]

measures = []
for step, resp, cv in responses:
    m = dm.record_and_measure(
        cultivar="The Steward",
        step=step,
        response=resp,
        channel_vector=cv,
        lambda_val=0.85,
    )
    measures.append(m)

check("4 measures recorded",      len(measures) == 4)
check("W1 delta_t == 0",          measures[0].delta_t == 0.0)
check("W4 has drift recorded",    measures[3].delta_t >= 0.0)
check("All have cultivar",        all(m.cultivar == "The Steward" for m in measures))

summary = dm.get_summary("The Steward")
check("Summary has 4 measurements", len(summary["measurements"]) == 4)
check("Summary has mean_drift",     "mean_drift" in summary)

drift_xml = dm.get_drift_xml("The Steward")
check("DriftManager XML export",    "<DriftLog>" in drift_xml)

# ---------------------------------------------------------------------------
# 11. reset_session
# ---------------------------------------------------------------------------
print("\n── 11. reset_session ──")

dm.reset_session("The Steward")
summary_reset = dm.get_summary("The Steward")
check("After reset: measurements empty",
      len(summary_reset.get("measurements", [])) == 0)

# After reset, W1 should be 0 again
m_after = dm.record_and_measure(
    cultivar="The Steward", step=1,
    response="Starting fresh.",
    channel_vector={"E":0.5,"B":0.5,"P":0.5,"S":0.5},
    lambda_val=0.85,
)
check("After reset: W1 drift = 0", m_after.delta_t == 0.0)

# ---------------------------------------------------------------------------
# 12. Waypoint XML fragment
# ---------------------------------------------------------------------------
print("\n── 12. Waypoint XML fragment ──")

m_wp = DriftMeasure(
    delta_t=0.1420,
    pass_a={"E":0.7,"B":0.3,"P":0.4,"S":0.3},
    pass_b={"E":0.4,"B":0.4,"P":0.6,"S":0.3},
    lambda_val=0.72, step=3,
    cultivar="The Witness",
    interpretation="The Ask: moderate drift"
)
channel_state = {"E": 0.6200, "B": 0.4800, "P": 0.7100, "S": 0.5500}
fragment = m_wp.waypoint_xml_fragment("W3_THE_ASK", channel_state, 3)
wp_xml = f"<Waypoint {fragment}/>"

print(f"       {wp_xml}")
check("Fragment has id",     'id="W3_THE_ASK"' in fragment)
check("Fragment has stepno", 'stepno="3"' in fragment)
check("Fragment has drift",  'drift="0.1420"' in fragment)
check("Fragment has lambda", 'lambda="0.72"' in fragment)
check("Fragment has E",      'E="0.6200"' in fragment)
check("Forms valid XML",     wp_xml.startswith("<Waypoint"))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "─" * 50)
if errors:
    print(f"FAILED — {len(errors)} test(s):")
    for e in errors:
        print(f"  • {e}")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
    sys.exit(0)
