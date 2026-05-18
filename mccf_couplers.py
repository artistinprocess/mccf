"""
mccf_couplers.py — MCCF Coupler System
=======================================
Implements all seven coupler functions that drive expressive_cv (ϵ) drift.

Architecture invariants (never change):
  - This module owns ALL coupler math.  Never duplicated in mccf_api.py.
  - Couplers write to expressive_cv (ϵ) only — never to constitutional_cv (ϕ).
  - All coupler functions return a delta dict {E, B, P, S}.
  - Caller (field_tick in mccf_api.py) collects ALL deltas before applying ANY.
  - apply_coupler() is the only public entry point — callers never call coupler_*
    functions directly.

Coupler registry:
  R   — Resonance:   align and amplify shared dimensions (workhorse of sync)
  D   — Damping:     reduce intensity, absorb perturbations (stabiliser)
  I   — Inversion:   reflect across dimension (conflict, counterbalance)
  G   — Gated:       conditional activation (threshold-guarded inner coupler)
  T   — Threshold:   nonlinear amplification above trigger (phase transition)
  L   — Delay:       time-shifted response (resentment, lag, oscillation)
  Int — Integration: accumulate over time (bonding, trauma, habituation)

Spec reference: MCCF_Coupler_Implementation_Spec.md
Prepared: Day 15 — May 17 2026
"""

import math
import operator as _op

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHANNELS = ('E', 'B', 'P', 'S')

_ZERO_DELTA = {'E': 0.0, 'B': 0.0, 'P': 0.0, 'S': 0.0}


# ---------------------------------------------------------------------------
# Helper: filter parsing
# ---------------------------------------------------------------------------

def _parse_filter(filter_str: str) -> set:
    """
    Parse a comma-separated channel filter string into a set of valid channel names.
    e.g. 'E,S' → {'E', 'S'}, '' or 'E,B,P,S' → all four channels.
    """
    if not filter_str:
        return set(CHANNELS)
    return {c.strip() for c in filter_str.split(',') if c.strip() in CHANNELS}


# ---------------------------------------------------------------------------
# Helper: asymmetry measure (H_sym)
# ---------------------------------------------------------------------------

def _asymmetry(cv_a: dict, cv_b: dict, channels) -> float:
    """
    H_sym: normalised distance between two channel vectors over the given channel set.
    Returns 0.0 when vectors are identical, approaches 1.0 when maximally different.
    Used by Resonance for adaptive coupling strength.
    """
    diffs = [(cv_a[ch] - cv_b[ch]) ** 2 for ch in channels]
    if not diffs:
        return 0.0
    return math.sqrt(sum(diffs) / len(diffs))


# ---------------------------------------------------------------------------
# Helper: condition evaluator (used by Gated and Threshold)
# ---------------------------------------------------------------------------

_OPS = {
    '>=': _op.ge,
    '<=': _op.le,
    '>':  _op.gt,
    '<':  _op.lt,
    '==': _op.eq,
}


def _eval_condition(condition: str, cv: dict) -> bool:
    """
    Evaluate a simple 'CHANNEL op VALUE' condition against a CV dict.
    Supported operators: >, <, >=, <=, ==
    Examples: 'E>0.7', 'S<=0.5', 'B>=0.3'
    Returns False on malformed input.
    """
    condition = condition.strip()
    # Test longest operators first to avoid '>' matching '>='
    for sym in ('>=', '<=', '>', '<', '=='):
        if sym in condition:
            parts = condition.split(sym, 1)
            if len(parts) != 2:
                return False
            ch  = parts[0].strip()
            try:
                val = float(parts[1].strip())
            except ValueError:
                return False
            return _OPS[sym](cv.get(ch, 0.0), val)
    return False


# ---------------------------------------------------------------------------
# R — Resonance
# ---------------------------------------------------------------------------

def coupler_resonance(source_cv: dict, target_state, params: dict, context: dict) -> dict:
    """
    Align target toward source on filtered channels.
    Adaptive strength: R_effective = gain · e^(-λ · H_sym)
    Weaker when states are asymmetric — asymmetric bonds are unstable.

    params:
      gain   (float, default 0.5)  — base coupling gain
      filter (str,   default all)  — comma-separated channels to affect
      lambda (float, default 1.0)  — asymmetry sensitivity
    """
    gain  = float(params.get('gain', 0.5))
    filt  = _parse_filter(params.get('filter', 'E,B,P,S'))
    lam   = float(params.get('lambda', 1.0))

    h_sym  = _asymmetry(source_cv, target_state.observed_cv, filt)
    r_eff  = gain * math.exp(-lam * h_sym)

    delta      = {}
    target_obs = target_state.observed_cv
    for ch in CHANNELS:
        if ch in filt:
            delta[ch] = r_eff * (source_cv[ch] - target_obs[ch])
        else:
            delta[ch] = 0.0
    return delta


# ---------------------------------------------------------------------------
# D — Damping
# ---------------------------------------------------------------------------

def coupler_damping(source_cv: dict, target_state, params: dict, context: dict) -> dict:
    """
    Pull expressive component toward zero (toward constitutional baseline).
    Reduces intensity; absorbs perturbations.  Stabiliser coupler.

    params:
      gain   (float, default 0.4) — damping strength
      filter (str,   default all) — channels to damp
    """
    gain = float(params.get('gain', 0.4))
    filt = _parse_filter(params.get('filter', 'E,B,P,S'))
    delta = {}
    for ch in CHANNELS:
        if ch in filt:
            # Pull ϵ back toward zero (toward ϕ baseline)
            delta[ch] = -gain * target_state.expressive_cv[ch]
        else:
            delta[ch] = 0.0
    return delta


# ---------------------------------------------------------------------------
# I — Inversion
# ---------------------------------------------------------------------------

def coupler_inversion(source_cv: dict, target_state, params: dict, context: dict) -> dict:
    """
    Move target away from source on filtered channels.
    Implements conflict, counterbalance, complementary opposition.

    params:
      gain   (float, default 0.3) — inversion strength
      filter (str,   default all) — channels to invert
    """
    gain  = float(params.get('gain', 0.3))
    filt  = _parse_filter(params.get('filter', 'E,B,P,S'))
    delta = {}
    target_obs = target_state.observed_cv
    for ch in CHANNELS:
        if ch in filt:
            # Move away from source — amplify the existing difference
            delta[ch] = gain * (target_obs[ch] - source_cv[ch])
        else:
            delta[ch] = 0.0
    return delta


# ---------------------------------------------------------------------------
# G — Gated
# ---------------------------------------------------------------------------

def coupler_gated(source_cv: dict, target_state, params: dict, context: dict) -> dict:
    """
    Conditional coupler: fires inner coupler only when condition on target CV is met.
    If gate is closed, returns zero delta.

    params:
      threshold    (str,  default 'S>0.5') — condition on target.observed_cv
      inner        (str,  default 'R')     — coupler type to fire when gate opens
      inner_params (dict, default {gain:0.5}) — params forwarded to inner coupler
    """
    condition    = params.get('threshold', 'S>0.5')
    inner_type   = params.get('inner', 'R')
    inner_params = params.get('inner_params', {'gain': 0.5})

    if _eval_condition(condition, target_state.observed_cv):
        return apply_coupler(inner_type, source_cv, target_state, inner_params, context)
    return dict(_ZERO_DELTA)


# ---------------------------------------------------------------------------
# T — Threshold
# ---------------------------------------------------------------------------

def coupler_threshold(source_cv: dict, target_state, params: dict, context: dict) -> dict:
    """
    Nonlinear amplification: fires only when source CV meets trigger condition.
    When fired, amplifies filtered source channels into target delta.
    Sets context['phase_transition_fired'] = True — consumed by variance floor.

    params:
      trigger (str,   default 'E>0.7') — condition on source_cv
      gain    (float, default 1.2)     — amplification when triggered
      filter  (str,   default all)     — channels to amplify into
    """
    trigger = params.get('trigger', 'E>0.7')
    gain    = float(params.get('gain', 1.2))
    filt    = _parse_filter(params.get('filter', 'E,B,P,S'))

    if not _eval_condition(trigger, source_cv):
        return dict(_ZERO_DELTA)

    # Threshold fired — flag phase transition for variance floor enforcement
    context['phase_transition_fired'] = True

    delta = {}
    for ch in CHANNELS:
        if ch in filt:
            delta[ch] = gain * source_cv[ch]
        else:
            delta[ch] = 0.0
    return delta


# ---------------------------------------------------------------------------
# L — Delay
# ---------------------------------------------------------------------------

def coupler_delay(source_cv: dict, target_state, params: dict, context: dict) -> dict:
    """
    Time-shifted response: target responds to source state from `lag` ticks ago.
    Models resentment, emotional lag, oscillation.
    Returns zero delta if history buffer is shorter than lag.

    params:
      lag    (int,   default 2)   — timestep offset into source history
      gain   (float, default 0.5) — response strength
      filter (str,   default all) — channels affected

    context keys consumed:
      source_history: list of past observed_cv dicts, oldest first
    """
    lag    = int(params.get('lag', 2))
    gain   = float(params.get('gain', 0.5))
    filt   = _parse_filter(params.get('filter', 'E,B,P,S'))

    history = context.get('source_history', [])
    if len(history) < lag:
        return dict(_ZERO_DELTA)

    # history[-lag] is the CV from `lag` ticks ago
    past_cv    = history[-lag]
    target_obs = target_state.observed_cv
    delta      = {}
    for ch in CHANNELS:
        if ch in filt:
            delta[ch] = gain * (past_cv[ch] - target_obs[ch])
        else:
            delta[ch] = 0.0
    return delta


# ---------------------------------------------------------------------------
# ∫ — Integration  (XML-safe name: 'Int')
# ---------------------------------------------------------------------------

def coupler_integration(source_cv: dict, target_state, params: dict, context: dict) -> dict:
    """
    Slow accumulative drift toward source state.
    Models bonding, trauma, habituation, baseline drift over many waypoints.

    params:
      rate   (float, default 0.05) — drift rate per tick
      filter (str,   default all)  — channels affected
    """
    rate = float(params.get('rate', 0.05))
    filt = _parse_filter(params.get('filter', 'E,B,P,S'))
    delta      = {}
    target_obs = target_state.observed_cv
    for ch in CHANNELS:
        if ch in filt:
            delta[ch] = rate * (source_cv[ch] - target_obs[ch])
        else:
            delta[ch] = 0.0
    return delta


# ---------------------------------------------------------------------------
# Coupler registry
# ---------------------------------------------------------------------------

COUPLER_REGISTRY = {
    'R':   coupler_resonance,
    'D':   coupler_damping,
    'I':   coupler_inversion,
    'G':   coupler_gated,
    'T':   coupler_threshold,
    'L':   coupler_delay,
    'Int': coupler_integration,   # ∫ — 'Int' as XML-safe name
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def apply_coupler(
    coupler_type: str,
    source_cv: dict,
    target_state,
    params: dict,
    context: dict
) -> dict:
    """
    Dispatch to the named coupler function.
    Returns delta dict {'E': float, 'B': float, 'P': float, 'S': float}.
    Raises ValueError for unknown coupler_type.

    This is the ONLY function callers (field_tick) should invoke.
    Never call coupler_* functions directly.
    """
    fn = COUPLER_REGISTRY.get(coupler_type)
    if fn is None:
        raise ValueError(f"Unknown coupler type: {coupler_type!r}. "
                         f"Known types: {list(COUPLER_REGISTRY)}")
    return fn(source_cv, target_state, params, context)
