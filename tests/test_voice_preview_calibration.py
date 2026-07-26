"""
Day 73 — regression + calibration test for the _estimate_sentiment /
_decompose_to_channels refactor (seed doc §4, priority queue item 1).

Two things must both be true:
  (a) The refactor changed NOTHING about the live-field-facing output of
      _estimate_sentiment / _decompose_to_channels — same inputs, same
      outputs, exactly, on a batch of real-shaped text.
  (b) /voice/preview's downstream tag suggestion (arousal_proxy,
      engagement_proxy, tag_valence, suggested_tag) is now fixed against
      the two confirmed failure cases in the seed doc, without breaking
      correct behavior on genuinely high-signal text.

Flask-free: execs each module file directly out of its own namespace dict,
same technique the Day 72 session used to verify against the mccf_voice_api
module without a running server. No mccf_api/mccf_llm/mccf_core import is
needed — nothing under test touches those.
"""

import sys
import re as _re
import math as _math

PATCHED_PATH = "mccf_voice_api.py"


def load_module_ns(path):
    ns = {"__name__": "mccf_voice_api_under_test"}
    with open(path) as f:
        code = f.read()
    exec(compile(code, path, "exec"), ns)
    return ns


# ---------------------------------------------------------------------------
# Frozen pre-refactor reference implementations (V2.2 / V2.3, exactly as
# they were in mccf_voice_api.py before the Day 73 calibration fix). Embedded
# here rather than loaded from a separate file so this test doesn't depend
# on a scratch copy surviving outside this repo.
# ---------------------------------------------------------------------------

def _old_estimate_sentiment(text: str) -> float:
    words = set(_re.findall(r'\b\w+\b', text.lower()))
    pos_words = {
        "good","great","yes","wonderful","trust","hope","safe","glad","joy",
        "understand","clarity","clear","honest","care","help","support",
        "together","resolve","healing","growth","learned","insight",
        "appreciate","grateful","open","willing","ready","certain","agree",
        "comfortable","relief","peaceful","balanced","stable","confident",
        "acknowledge","reassurance","compassion","empathy","gently","kindness",
        "prioritize","wellbeing","meaningful","purpose","support","assist",
        "balance","guidance","encourage","provide","establish","routine",
        "respect","validate","address","explain","focus","present",
        "remember","honor","cherish","loved","safe","warm","together"
    }
    neg_words = {
        "no","bad","wrong","danger","fear","hurt","lost","difficult",
        "problem","worry","harsh","angry","conflict","harm","threat",
        "confused","unclear","uncertain","resist","refuse","cannot",
        "collapse","rupture","broken","failed","stuck","trapped","frozen",
        "overwhelm","pressure","force","violate","uncomfortable","painful",
        "upset","distress","anxiety","confusion","disorientation","turmoil",
        "loss","grief","suffering","struggle","burden","weight","responsibility",
        "complexity","challenge","difficult","impossible","inappropriate",
        "intended","harm","hurt","damage","upset","manipulate"
    }
    uncertainty_words = {
        "maybe","perhaps","possibly","might","could","guess","suppose",
        "unsure","unclear","wonder","hesitate","complicated","complex",
        "firstly","however","although","while","but","consider","recognize",
        "understandable","acknowledge","balance","tradeoff","depends"
    }
    pos   = len(words & pos_words)
    neg   = len(words & neg_words)
    unc   = len(words & uncertainty_words)
    total = pos + neg + unc
    if total == 0:
        word_count = len(_re.findall(r'\b\w+\b', text))
        if word_count < 20:
            return -0.1
        return 0.0
    valence = (pos - neg - unc * 0.5) / total
    return round(max(-1.0, min(1.0, valence)), 3)


def _old_decompose_to_channels(text: str, base_weights: dict) -> dict:
    words = set(_re.findall(r'\b\w+\b', text.lower()))
    NUDGE = 0.04
    THRESHOLD = 2
    S_words = {
        "we","us","our","together","shared","community","relationship","relationships",
        "connect","connection","connections","align","mutual","collective","belong","social",
        "trust","rapport","bond","partnership","collaborate",
        "conversation","conversations","dynamics","circumstances",
        "support","supported","supporting","alongside","presence",
        "open","opening","person","someone",
        "acknowledged","acknowledges","acknowledging","acknowledge",
        "validated","validates","validating","validate",
        "listened","listening","attentively","heard",
        "safe","safety","space","acceptance","accepted",
        "solace","comfort","comforting","alone","lonely",
        "honest","honesty","values","empathetic","empathy",
        "compassion","compassionate","loved","balance"
    }
    E_words = {
        "feel","feeling","felt","emotion","emotions","emotional","care","hurt","fear","love",
        "warm","warmth","cold","comfort","distress","distressing","distressed","pain","joy","grief",
        "vulnerable","sensitive","moved","touched","affected",
        "anxiety","anxious","confusion","confused",
        "overwhelmed","overwhelming","struggling","struggle",
        "compassion","compassionate","empathy","empathetic",
        "gentle","gently","kindness","sorrow","sadness","sad",
        "worried","worrying","concern","concerned","concerning",
        "loss","suffering","suffer","anguish",
        "scared","scary","uncertain","uncertainty","difficult","difficulty",
        "regulation","regulate","suppress","express","sense","sensing"
    }
    P_words = {
        "future","plan","predict","likely","anticipate","expect",
        "foresee","strategy","prepare","outcome","consequence",
        "model","framework","structure","pattern","systematic",
        "gradually","gradual","approach","consider","considering",
        "address","addresses","addressing","reduce","alleviate","potential",
        "potentially","information","accurate","specifics","diagnosis",
        "educating","educate","underlying","root","cause"
    }
    B_words = {
        "act","action","do","doing","consistent","reliable","pattern",
        "behavior","response","habit","practice","apply","execute",
        "follow","maintain","sustain","commit","discipline",
        "assist","assisting","help","helping","provide","providing",
        "handle","handling","communicate","communicating","intention",
        "intentional","write","writing","content","appropriate","mindful"
    }
    s_hits = len(words & S_words)
    e_hits = len(words & E_words)
    p_hits = len(words & P_words)
    b_hits = len(words & B_words)
    return {
        "S": round(NUDGE * _math.tanh(s_hits - THRESHOLD), 4),
        "E": round(NUDGE * _math.tanh(e_hits - THRESHOLD), 4),
        "P": round(NUDGE * _math.tanh(p_hits - THRESHOLD), 4),
        "B": round(NUDGE * _math.tanh(b_hits - THRESHOLD), 4),
    }


def _old_derive_emotion_tag(valence, arousal, engagement):
    if engagement < 0.35 and abs(valence) < 0.15:
        return 'dismissive'
    if arousal < 0.35:
        return 'whisper'
    if valence <= -0.5:
        if arousal >= 0.60:
            return 'angry'
        if arousal >= 0.45:
            return 'appalled'
        return 'sad'
    if valence <= -0.15:
        return 'annoyed'
    if valence >= 0.50:
        return 'excited' if arousal >= 0.60 else 'happy'
    if valence >= 0.15:
        return 'thoughtful' if arousal < 0.45 else 'happy'
    if arousal >= 0.70:
        return 'surprised'
    if arousal < 0.45:
        return 'thoughtful'
    return None


def run():
    new = load_module_ns(PATCHED_PATH)

    failures = []

    def check(label, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        print(f"[{status}] {label}" + (f"  ({detail})" if detail and not cond else ""))
        if not cond:
            failures.append(label)

    # ---------------------------------------------------------------
    # (a) Regression: _estimate_sentiment output unchanged
    # ---------------------------------------------------------------
    sentiment_corpus = [
        "Okay.",
        "",  # will be skipped by callers normally, but function should still not crash
        "I understand your concern and I want to help you feel safe.",
        "This is confusing and I feel trapped, it's overwhelming.",
        "Perhaps we should consider this carefully, however it's complicated.",
        "Yes, great, wonderful, I trust you completely and feel so grateful.",
        "No, this is wrong and harmful, I refuse to continue, it's dangerous.",
        "The weather today involves several meteorological factors of note "
        "that persist across a wide geographic region for an extended time.",
        "I feel a bit uncertain but I think we can work through this together, "
        "and I appreciate your patience and understanding here.",
        "Firstly, although this is difficult, we should recognize the "
        "tradeoffs and balance our approach depending on circumstances.",
    ]
    for text in sentiment_corpus:
        old_val = _old_estimate_sentiment(text)
        new_val = new["_estimate_sentiment"](text)
        check(
            f"_estimate_sentiment unchanged: {text[:40]!r}",
            old_val == new_val,
            f"old={old_val} new={new_val}",
        )

    # ---------------------------------------------------------------
    # (a) Regression: _decompose_to_channels output unchanged
    # ---------------------------------------------------------------
    base_weights = {"E": 0.25, "B": 0.25, "P": 0.25, "S": 0.25}
    for text in sentiment_corpus:
        old_val = _old_decompose_to_channels(text, base_weights)
        new_val = new["_decompose_to_channels"](text, base_weights)
        check(
            f"_decompose_to_channels unchanged: {text[:40]!r}",
            old_val == new_val,
            f"old={old_val} new={new_val}",
        )

    # ---------------------------------------------------------------
    # (b) Confirmed failure case #1 — "Okay." must NOT read near-max arousal
    # ---------------------------------------------------------------
    channel_hits = new["_channel_hit_counts"]("Okay.")
    arousal, engagement = new["_preview_arousal_engagement"](channel_hits)
    check(
        "'Okay.' arousal_proxy is low, not near-max (old bug: 0.879)",
        arousal <= 0.4,
        f"arousal_proxy={arousal}",
    )

    # ---------------------------------------------------------------
    # (b) Confirmed failure case #2 — calm hedging line must not tag 'angry'
    # ---------------------------------------------------------------
    hedging_line = (
        "Perhaps we should consider this carefully, however it's complicated "
        "and unclear, although I recognize the tradeoffs depend on circumstances."
    )
    s_hits = new["_sentiment_hit_counts"](hedging_line)
    tag_valence = new["_tag_valence_from_hits"](s_hits)
    c_hits = new["_channel_hit_counts"](hedging_line)
    h_arousal, h_engagement = new["_preview_arousal_engagement"](c_hits)
    tag = new["derive_emotion_tag"](tag_valence, h_arousal, h_engagement)
    check(
        "Hedging line no longer tagged 'angry'",
        tag != "angry",
        f"tag_valence={tag_valence} arousal={h_arousal} engagement={h_engagement} tag={tag}",
    )
    check(
        "Hedging line no longer tagged 'sad' either (should be neutral/thoughtful/None)",
        tag not in ("angry", "sad", "appalled", "annoyed"),
        f"tag={tag}",
    )
    # Confirm the OLD code really did fail this case, so the test itself is honest
    old_sentiment = _old_estimate_sentiment(hedging_line)
    old_deltas = _old_decompose_to_channels(hedging_line, base_weights)
    old_intensity = min(1.0, sum(abs(v) for v in old_deltas.values()) / (4 * 0.04))
    old_arousal = round(0.3 + 0.6 * old_intensity, 4)
    old_tag = _old_derive_emotion_tag(old_sentiment, old_arousal, 0.5)
    check(
        "(sanity) old code really did mis-tag the hedging line",
        old_tag in ("angry", "sad", "appalled", "annoyed"),
        f"old_sentiment={old_sentiment} old_arousal={old_arousal} old_tag={old_tag}",
    )

    # ---------------------------------------------------------------
    # (b) Fix must not flatten genuinely high-signal negative text
    # ---------------------------------------------------------------
    angry_line = (
        "No, this is wrong and harmful and dangerous, I refuse, it's broken "
        "and it hurt me and caused fear and pain and distress and anguish."
    )
    s_hits2 = new["_sentiment_hit_counts"](angry_line)
    tag_valence2 = new["_tag_valence_from_hits"](s_hits2)
    c_hits2 = new["_channel_hit_counts"](angry_line)
    a2, e2 = new["_preview_arousal_engagement"](c_hits2)
    tag2 = new["derive_emotion_tag"](tag_valence2, a2, e2)
    check(
        "Genuinely angry/harmful text still tags as negative-strong "
        "(angry/appalled/sad), not flattened to neutral",
        tag2 in ("angry", "appalled", "sad"),
        f"tag_valence={tag_valence2} arousal={a2} engagement={e2} tag={tag2}",
    )

    # ---------------------------------------------------------------
    # (b) Genuinely warm/positive high-engagement text still tags positive
    # ---------------------------------------------------------------
    warm_line = (
        "Yes, I trust you and I feel so grateful, together we found "
        "clarity and healing, this connection feels wonderful and safe."
    )
    s_hits3 = new["_sentiment_hit_counts"](warm_line)
    tag_valence3 = new["_tag_valence_from_hits"](s_hits3)
    c_hits3 = new["_channel_hit_counts"](warm_line)
    a3, e3 = new["_preview_arousal_engagement"](c_hits3)
    tag3 = new["derive_emotion_tag"](tag_valence3, a3, e3)
    check(
        "Genuinely warm/positive text tags as happy/excited/thoughtful, not negative",
        tag3 in ("happy", "excited", "thoughtful", None),
        f"tag_valence={tag_valence3} arousal={a3} engagement={e3} tag={tag3}",
    )

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All checks passed.")


if __name__ == "__main__":
    run()
