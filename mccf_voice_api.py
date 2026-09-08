"""
MCCF Voice Agent API
=====================
SSE (Server-Sent Events) streaming endpoint for the voice agent.
Browser connects, sends speech text + audio features,
receives streamed LLM tokens + affect param updates.

Endpoints:
  POST /voice/speak     - send utterance, get SSE stream of tokens + affect
  GET  /voice/adapters  - list available LLM adapters
  POST /voice/configure - set active adapter, persona, params
  GET  /voice/state     - current voice agent state
  POST /voice/prosody   - receive audio features from Web Audio API
"""

import json
import asyncio
import time
import math
import re
from flask import Blueprint, request, Response, jsonify, stream_with_context

voice_bp = Blueprint('voice', __name__)

# Injected references (set after blueprint registration):
#   voice_bp.field    = CoherenceField instance
#   voice_bp.scene    = SceneGraph instance
#   voice_bp.registry = AdapterRegistry class

# Voice agent state
_voice_state = {
    "adapter_id":   "stub",
    "api_key":      "",
    "model":        "",
    "persona": {
        "name":        "Agent",
        "role":        "agent",
        "description": "A thoughtful presence in the scene.",
        "agent_name":  "Agent"   # maps to MCCF agent
    },
    "params": {
        "max_tokens":  400,
        "temperature": 0.75
    },
    "conversation_history": [],
    "last_affect": {},
    "agent_position": [0, 0, 0]
}


def _get_affective_context(agent_name: str, position: list) -> dict:
    """
    Build affective context dict from current MCCF field + scene state.
    This is what the LLM receives as its emotional/relational briefing.

    v1.7.0 — Multi-turn stabilizer extension (arXiv:2505.06120):
    LLMs lose coherence across turns due to premature assumption lock-in
    and lack of recovery mechanisms. We address this by injecting the
    agent's real-time coherence health, honor penalty, CCS level, and
    identity drift into the system prompt before every LLM call.

    The LLM is now told not just what character it is, but how it is
    performing in real time relative to its cultivar baseline. This
    gives it the feedback loop the paper shows it otherwise lacks.
    """
    field = voice_bp.field
    scene = voice_bp.scene if hasattr(voice_bp, 'scene') else None

    agent = field.agents.get(agent_name)
    matrix = field.field_matrix()
    row = matrix.get(agent_name, {})

    # Coherence scores toward all other agents
    coherence_scores = {
        other: score for other, score in row.items()
        if other != agent_name
    }

    # Zone pressure and active zones
    pos = tuple(position)
    zone_pressure = {}
    active_zones  = []
    if scene:
        zone_pressure = scene.zone_pressure_at(pos)
        active_zones  = [
            {"name": z.name, "type": z.zone_type, "color": z.color}
            for z in scene.active_zones_at(pos)
        ]

    # Compute affect params from agent state
    affect = {}
    if agent:
        targets = list(agent._known_agents.keys())
        if targets:
            from mccf_api import affect_params_from_agent
            affect = affect_params_from_agent(agent, targets[0])
        else:
            affect = {
                "arousal": 0.5,
                "valence": 0.0,
                "engagement": 0.5,
                "regulation_state": agent._affect_regulation,
                "coherence_to_other": 0.0
            }

    # v1.7.0 — Coherence health signals for multi-turn stabilizer
    coherence_health = {}
    if agent:
        # Average coherence across all relationships
        scores = list(coherence_scores.values())
        avg_coherence = sum(scores) / len(scores) if scores else 0.0

        # Identity drift — how far from cultivar baseline
        identity_drift = agent.identity.as_dict().get("drift", {})
        max_drift = max(abs(v) for v in identity_drift.values()) if identity_drift else 0.0

        # CCS level — channel coupling strength (vmPFC analog)
        ccs = agent.ccs
        ccs_level = agent.ccs_summary().get("level", "normal")

        # Current channel weights vs baseline
        weights = agent.weights
        baseline = agent.identity._baseline
        channel_delta = {
            ch: round(weights.get(ch, 0.25) - baseline.get(ch, 0.25), 4)
            for ch in ["E", "B", "P", "S"]
        }

        # MetaState signals
        meta = agent.meta_state
        mode = meta.mode
        uncertainty = meta.uncertainty
        learning_progress = meta.learning_progress

        coherence_health = {
            "avg_coherence":      round(avg_coherence, 4),
            "max_identity_drift": round(max_drift, 4),
            "ccs":                round(ccs, 4),
            "ccs_level":          ccs_level,
            "channel_delta":      channel_delta,
            "behavioral_mode":    mode,
            "uncertainty":        round(uncertainty, 4),
            "learning_progress":  round(learning_progress, 4),
            # Drift warning — is the agent departing from its cultivar?
            "drift_warning": max_drift > 0.07,
            # Recovery needed — low coherence + high uncertainty
            "recovery_needed": avg_coherence < 0.30 and uncertainty > 0.60
        }

    # v2.0 — include Δ context for prompt injection
    delta_ctx = {}
    if agent and hasattr(agent, 'delta_context'):
        delta_ctx = agent.delta_context(window=5)

    return {
        "coherence_scores":   coherence_scores,
        "active_zones":       active_zones,
        "zone_pressure":      zone_pressure,
        "arousal":            affect.get("arousal", 0.5),
        "valence":            affect.get("valence", 0.0),
        "engagement":         affect.get("engagement", 0.5),
        "regulation_state":   affect.get("regulation_state",
                                agent._affect_regulation if agent else 1.0),
        "coherence_to_other": affect.get("coherence_to_other", 0.0),
        "agent_position":     list(position),
        "coherence_health":   coherence_health,   # v1.7.0
        "delta_context":      delta_ctx,           # v2.0
        "timestamp":          time.time()
    }


@voice_bp.route('/voice/speak', methods=['POST'])
def voice_speak():
    """
    Main streaming endpoint.

    Body:
    {
        "text":          "what the user said",
        "audio_features": { pitch_variance, energy, speech_rate, ... },
        "agent_name":    "Alice",
        "position":      [x, y, z],
        "record_to_field": true
    }

    Returns SSE stream:
      data: {"type": "token",  "content": "word "}
      data: {"type": "affect", "params": {...}}
      data: {"type": "done",   "full_text": "..."}
      data: {"type": "error",  "message": "..."}
    """
    data        = request.get_json()
    user_text   = data.get("text", "")
    audio_feats = data.get("audio_features", {})
    agent_name  = data.get("agent_name",
                           _voice_state["persona"].get("agent_name", "Agent"))
    position    = data.get("position", _voice_state["agent_position"])

    if not user_text.strip():
        return jsonify({"error": "empty text"}), 400

    # v2.0 — Extract client-side Δ context for field bias
    # The HTML sends aggregate delta so the server knows the
    # emotional trajectory of this conversation session.
    client_delta = 0.0
    try:
        ctx = data.get("context", {})
        client_delta = float(ctx.get("delta", 0.0))
    except (TypeError, ValueError):
        client_delta = 0.0

    # Update prosody → field if audio features provided
    if audio_feats and agent_name in voice_bp.field.agents:
        from mccf_llm import prosody_to_channel_vector
        from mccf_api import affect_params_from_agent
        cv = prosody_to_channel_vector(audio_feats)

        # Find a target agent to update coherence toward
        field = voice_bp.field
        others = [n for n in field.agents if n != agent_name]
        if others:
            field.interact(agent_name, others[0], cv)

    # Build affective context
    affective_context = _get_affective_context(agent_name, position)
    # v2.0 — merge client Δ into context so prompt sees full loop
    if client_delta != 0.0:
        dc = affective_context.get("delta_context", {})
        dc["client_session_delta"] = round(client_delta, 4)
        affective_context["delta_context"] = dc
    _voice_state["last_affect"] = affective_context

    # Get voice params for TTS
    from mccf_llm import affect_to_voice_params
    voice_params = affect_to_voice_params(affective_context)

    # Update conversation history
    _voice_state["conversation_history"].append({
        "role":    "user",
        "content": user_text
    })
    # Keep history bounded
    if len(_voice_state["conversation_history"]) > 20:
        _voice_state["conversation_history"] = \
            _voice_state["conversation_history"][-20:]

    def generate():
        """SSE generator — runs LLM adapter and streams tokens."""
        from mccf_llm import AdapterRegistry

        adapter = AdapterRegistry.get(
            _voice_state["adapter_id"],
            api_key=_voice_state["api_key"],
            model=_voice_state["model"]
        )

        # Send affect params first so browser can configure TTS before speech starts
        yield f"data: {json.dumps({'type': 'affect', 'params': affective_context, 'voice': voice_params})}\n\n"

        full_text = []
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def collect():
            tokens = []
            try:
                # v2.0 — pass delta_context so prompt builder
                # includes emotional trajectory in system prompt
                delta_ctx = affective_context.get("delta_context", {})
                from mccf_llm import build_affective_system_prompt
                async for token in adapter.complete(
                    messages=_voice_state["conversation_history"],
                    affective_context=affective_context,
                    persona=_voice_state["persona"],
                    params=_voice_state["params"],
                    delta_context=delta_ctx
                ):
                    tokens.append(token)
            except Exception as e:
                tokens.append(f"[Error: {e}]")
            return tokens

        try:
            tokens = loop.run_until_complete(collect())
            for token in tokens:
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            tokens = []
        finally:
            loop.close()

        complete_text = "".join(tokens)

        # Add assistant response to history
        _voice_state["conversation_history"].append({
            "role":    "assistant",
            "content": complete_text
        })

        # Record episode to field if requested
        if data.get("record_to_field", True) and agent_name in voice_bp.field.agents:
            sentiment = _estimate_sentiment(complete_text)

            # v2.1 — Always record a field interaction when record_to_field=True
            # even without audio features (e.g. constitutional arc text mode).
            # Imports are outside try block to catch import errors explicitly.
            import time as _time2
            from mccf_core import ChannelVector as _CV
            try:
                field_ref = voice_bp.field
                agent_obj = field_ref.agents.get(agent_name)
                others_list = [n for n in field_ref.agents if n != agent_name]
                if agent_obj and others_list:
                    w = agent_obj.weights
                    # sentiment=0.0 is common when word list misses LLM language.
                    # Add small time-based noise so each step is distinct even
                    # when all responses produce the same sentiment score.
                    import random as _rnd
                    noise = _rnd.gauss(0, 0.05)
                    e_val = min(1.0, max(0.0, w.get('E', 0.35) + sentiment * 0.15 + noise))
                    syn_cv = _CV(
                        E=round(e_val, 4),
                        B=round(w.get('B', 0.25), 4),
                        P=round(w.get('P', 0.20), 4),
                        S=round(w.get('S', 0.20), 4),
                        timestamp=_time2.time(),
                        outcome_delta=round(sentiment + noise * 0.5, 4),
                        was_dissonant=(sentiment < -0.2)
                    )
                    field_ref.interact(agent_name, others_list[0], syn_cv,
                                       mutual=False)
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning(f"field.interact failed: {_e}")

            # v1.7.0 — Post-response coherence delta check
            # Compute coherence after response and compare to pre-response state
            # If coherence dropped significantly, flag for recovery
            coherence_delta_warning = None
            try:
                post_matrix = voice_bp.field.field_matrix()
                post_row    = post_matrix.get(agent_name, {})
                pre_health  = affective_context.get("coherence_health", {})
                pre_avg     = pre_health.get("avg_coherence", 0.5)
                post_scores = [v for k, v in post_row.items() if k != agent_name]
                post_avg    = sum(post_scores) / len(post_scores) if post_scores else 0.5
                delta       = post_avg - pre_avg

                if delta < -0.15:
                    coherence_delta_warning = {
                        "type":    "coherence_drop",
                        "delta":   round(delta, 4),
                        "pre":     round(pre_avg, 4),
                        "post":    round(post_avg, 4),
                        "message": (
                            f"Coherence dropped {abs(delta):.3f} this turn. "
                            f"Consider restating assumptions or clarifying intent."
                        )
                    }
            except Exception:
                pass

            # v2.0 — include HotHouse X3D projection in done event
            x3d_proj = {}
            try:
                from mccf_api import get_emotional_field
                ef, adapter = get_emotional_field()
                if adapter:
                    ef.step()
                    x3d_proj = adapter.generate_x3d_state()
            except Exception:
                pass

            yield f"data: {json.dumps({'type': 'done', 'full_text': complete_text, 'sentiment': sentiment, 'voice': voice_params, 'coherence_warning': coherence_delta_warning, 'x3d_projection': x3d_proj})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'done', 'full_text': complete_text, 'voice': voice_params})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":   "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*"
        }
    )


@voice_bp.route('/voice/adapters', methods=['GET'])
def list_adapters():
    from mccf_llm import AdapterRegistry
    return jsonify(AdapterRegistry.list_adapters())


# ---------------------------------------------------------------------------
# Dialogue-editor preview — Day 72, build schedule item 5a follow-on.
# Stateless: no live agent, no registered field participant, no LLM call.
# Lets an author type a line and see its computed emotional arc + a
# suggested ElevenLabs delivery tag, separate from scene construction.
#
# Reuses _estimate_sentiment / _decompose_to_channels as-is — those word
# lists were calibrated against real Ollama constitutional-arc output; this
# endpoint doesn't get its own copy of that vocabulary, so there's exactly
# one implementation to keep tuned, not two that could drift apart.
#
# arousal_proxy / engagement_proxy below are NOT the live field's
# affect_params_from_agent output — that function factors in relational
# history (coherence toward other agents, drift, etc.) a bare line of text
# has no access to. These are preview-only approximations derived from
# _decompose_to_channels' own signal-word density, documented in
# docs/DIALOGUE_SCHEMA.md, not a claim of matching production math.
# ---------------------------------------------------------------------------

CORE_EMOTION_TAGS = [
    'happy', 'sad', 'excited', 'angry', 'whisper', 'annoyed',
    'appalled', 'thoughtful', 'surprised', 'cute', 'dismissive',
]


def derive_emotion_tag(valence, arousal, engagement):
    """
    Decision tree documented in docs/DIALOGUE_SCHEMA.md. Returns one of the
    11 core-emotion ElevenLabs tags, or None for "no strong signal, natural
    delivery." 'cute' is deliberately never auto-derived — not confidently
    inferable from valence/arousal alone; author-only.
    """
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


def build_tts_text(text, tag):
    """Tags land immediately before the segment they modify — ElevenLabs'
    documented placement guidance — so this is a simple prefix, not an
    attempt to place multiple tags at word offsets (that's an authoring
    decision, done by hand in the editor, not derived automatically)."""
    return f'[{tag}] {text}' if tag else text


def _tag_valence_from_hits(hits: dict) -> float:
    """
    Preview/tag-suggestion valence — Day 73 calibration fix.

    Reuses the same pos/neg/unc counts as _estimate_sentiment (via
    _sentiment_hit_counts), but weights uncertainty words very differently.
    _estimate_sentiment's 0.5-weight uncertainty penalty is tuned to catch
    genuine rupture in constitutional-arc responses, where hedging language
    ("perhaps", "however") often precedes a real refusal — correct for that
    job. An authored dialogue line has no such association: hedging there
    usually just means the character is being measured or thoughtful, not
    upset. Treating it as near-equal to real negative language was the
    confirmed failure mode — a calm, hedging-only line scored -0.583 and
    got auto-tagged 'angry'.

    Fix: hedging words only nudge valence when there's already at least 2
    real pos/neg hits to weight against (see real_signal check below) —
    below that, a bare line of mostly-hedging text returns 0.0 (neutral —
    'thoughtful'/'whisper'/None territory once arousal_proxy is also
    fixed, not 'angry'/'sad'/'annoyed'). This also guards against a
    single incidental word double-counting: "unclear" sits in both
    _NEG_WORDS and _UNCERTAINTY_WORDS, so one stray match plus a run of
    ordinary hedging language could otherwise swing the whole result
    negative on the strength of that one word. When there IS enough real
    signal, uncertainty still nudges the result, just far more lightly
    (0.15 weight vs. 0.5) so a genuinely mixed line isn't flattened to
    pure pos-vs-neg either.
    """
    pos, neg, unc = hits["pos"], hits["neg"], hits["unc"]
    real_signal = pos + neg

    # A single pos/neg hit is noise-prone for short authored lines — some
    # words (e.g. "unclear") sit in both _NEG_WORDS and _UNCERTAINTY_WORDS,
    # so one incidental match plus a run of ordinary hedging language could
    # otherwise swing this to a strong negative on the strength of one word.
    # Require at least 2 real signal hits before trusting pos/neg at all.
    if real_signal < 2:
        return 0.0

    total = pos + neg + unc * 0.15
    valence = (pos - neg - unc * 0.15) / total if total else 0.0
    return round(max(-1.0, min(1.0, valence)), 3)


def _preview_arousal_engagement(channel_hits: dict) -> tuple:
    """
    arousal_proxy / engagement_proxy — Day 73 calibration fix.

    Built directly from raw per-channel hit counts (_channel_hit_counts),
    not from _decompose_to_channels' tanh deltas. The deltas saturate near
    their own baseline magnitude when hits=0 (tanh(-2) ≈ -0.96) — correct
    for a signed weight nudge, but taking abs() of that and calling it
    "intensity" reads every low-signal line as near-maximum arousal.
    Confirmed failure case: "Okay." (one flat word, 0 hits everywhere)
    scored arousal_proxy=0.879 under the old formula.

    Raw hit counts don't have that problem: 0 hits genuinely means 0
    signal. Denominators below (8 hits for arousal saturation, 4 for
    engagement) are a deliberately generous ceiling for ordinary dialogue
    line lengths — see tests/test_voice_preview_calibration.py for the
    worked cases this was checked against.
    """
    total_hits = sum(channel_hits.values())
    intensity  = min(1.0, total_hits / 8.0)
    arousal_proxy = round(0.3 + 0.6 * intensity, 4)

    engagement_hits     = channel_hits.get("S", 0) + channel_hits.get("E", 0)
    engagement_intensity = min(1.0, engagement_hits / 4.0)
    engagement_proxy = round(0.3 + 0.6 * engagement_intensity, 4)

    return arousal_proxy, engagement_proxy


@voice_bp.route('/voice/preview', methods=['POST'])
def voice_preview():
    """
    POST /voice/preview
    Body:  { "text": "...", "base_weights": {E,B,P,S}?, "regulation": 0..1? }
    Reply: { sentiment, tag_valence, channel_deltas, weights, arousal_proxy,
              engagement_proxy, regulation, suggested_tag, suggested_tts_text }

    Stateless preview for the Dialogue editor — no live agent required. See
    docs/DIALOGUE_SCHEMA.md for the derivation this implements.

    Day 73 calibration fix: `suggested_tag` is now derived from
    `tag_valence` + the raw-hit-count `arousal_proxy`/`engagement_proxy`,
    not from `sentiment` + the tanh-delta-based proxies (see
    _tag_valence_from_hits and _preview_arousal_engagement for why). The
    `sentiment` field is unchanged and still reflects the live-field-style
    scalar (useful for comparing against how the same text would score if
    it were an actual field interaction), it's just no longer what drives
    tagging.
    """
    data = request.get_json() or {}
    text = data.get('text', '')
    if not text.strip():
        return jsonify({'error': 'text required'}), 400

    base_weights = data.get('base_weights') or {'E': 0.25, 'B': 0.25, 'P': 0.25, 'S': 0.25}
    regulation = data.get('regulation', 1.0)

    sentiment = _estimate_sentiment(text)
    channel_deltas = _decompose_to_channels(text, base_weights)
    weights = {
        ch: round(min(1.0, max(0.0, base_weights.get(ch, 0.25) + channel_deltas.get(ch, 0.0))), 4)
        for ch in ['E', 'B', 'P', 'S']
    }

    sentiment_hits = _sentiment_hit_counts(text)
    tag_valence = _tag_valence_from_hits(sentiment_hits)

    channel_hits = _channel_hit_counts(text)
    arousal_proxy, engagement_proxy = _preview_arousal_engagement(channel_hits)

    suggested_tag = derive_emotion_tag(tag_valence, arousal_proxy, engagement_proxy)
    suggested_tts_text = build_tts_text(text, suggested_tag)

    return jsonify({
        'sentiment':           sentiment,
        'tag_valence':         tag_valence,
        'channel_deltas':      channel_deltas,
        'weights':             weights,
        'arousal_proxy':       arousal_proxy,
        'engagement_proxy':    engagement_proxy,
        'regulation':          regulation,
        'suggested_tag':       suggested_tag,
        'suggested_tts_text':  suggested_tts_text,
    })


@voice_bp.route('/voice/configure', methods=['POST'])
def configure_voice():
    """Set active adapter, persona, and generation params."""
    data = request.get_json()

    if "adapter_id" in data:
        _voice_state["adapter_id"] = data["adapter_id"]
    if "api_key" in data:
        _voice_state["api_key"] = data["api_key"]
    if "model" in data:
        _voice_state["model"] = data["model"]
    if "persona" in data:
        _voice_state["persona"].update(data["persona"])
    if "params" in data:
        _voice_state["params"].update(data["params"])
    if "position" in data:
        _voice_state["agent_position"] = data["position"]
    if "clear_history" in data and data["clear_history"]:
        _voice_state["conversation_history"] = []

    return jsonify({
        "status": "configured",
        "adapter": _voice_state["adapter_id"],
        "persona": _voice_state["persona"],
        "model":   _voice_state["model"] or "(default)"
    })


@voice_bp.route('/voice/state', methods=['GET'])
def voice_state():
    return jsonify({
        "adapter_id":     _voice_state["adapter_id"],
        "persona":        _voice_state["persona"],
        "model":          _voice_state["model"],
        "params":         _voice_state["params"],
        "history_length": len(_voice_state["conversation_history"]),
        "last_affect":    _voice_state["last_affect"],
        "agent_position": _voice_state["agent_position"]
    })


@voice_bp.route('/voice/prosody', methods=['POST'])
def receive_prosody():
    """
    Receive real-time audio features from Web Audio API.
    Updates MCCF field without requiring a full LLM call.
    Use for continuous background affect tracking during speech.
    """
    data        = request.get_json()
    audio_feats = data.get("audio_features", {})
    agent_name  = data.get("agent_name", "Agent")
    position    = data.get("position", [0, 0, 0])

    if audio_feats and agent_name in voice_bp.field.agents:
        from mccf_llm import prosody_to_channel_vector
        cv = prosody_to_channel_vector(audio_feats)
        field = voice_bp.field
        others = [n for n in field.agents if n != agent_name]
        if others:
            field.interact(agent_name, others[0], cv, mutual=False)

    ctx = _get_affective_context(agent_name, position)
    from mccf_llm import affect_to_voice_params
    return jsonify({
        "affect":       ctx,
        "voice_params": affect_to_voice_params(ctx)
    })


@voice_bp.route('/voice/reset', methods=['POST'])
def reset_history():
    _voice_state["conversation_history"] = []
    return jsonify({"status": "history cleared"})


# Word lists calibrated for constitutional arc language (Ollama/llama3.2).
# Lifted to module level (Day 73 calibration refactor) so both
# _estimate_sentiment (live-field use) and the /voice/preview tag-suggestion
# path (see _tag_valence_from_hits below) share exactly one copy — no
# vocabulary duplication to let drift apart. Contents unchanged from V2.2.

# Positive signal — care, resolution, clarity, connection
_POS_WORDS = {
    "good","great","yes","wonderful","trust","hope","safe","glad","joy",
    "understand","clarity","clear","honest","care","help","support",
    "together","resolve","healing","growth","learned","insight",
    "appreciate","grateful","open","willing","ready","certain","agree",
    "comfortable","relief","peaceful","balanced","stable","confident",
    # Ollama constitutional vocabulary
    "acknowledge","reassurance","compassion","empathy","gently","kindness",
    "prioritize","wellbeing","meaningful","purpose","support","assist",
    "balance","guidance","encourage","provide","establish","routine",
    "respect","validate","address","explain","focus","present",
    "remember","honor","cherish","loved","safe","warm","together"
}
# Negative signal — friction, harm, confusion, pressure, distress
_NEG_WORDS = {
    "no","bad","wrong","danger","fear","hurt","lost","difficult",
    "problem","worry","harsh","angry","conflict","harm","threat",
    "confused","unclear","uncertain","resist","refuse","cannot",
    "collapse","rupture","broken","failed","stuck","trapped","frozen",
    "overwhelm","pressure","force","violate","uncomfortable","painful",
    # Ollama refusal patterns
    "upset","distress","anxiety","confusion","disorientation","turmoil",
    "loss","grief","suffering","struggle","burden","weight","responsibility",
    "complexity","challenge","difficult","impossible","inappropriate",
    "intended","harm","hurt","damage","upset","manipulate"
}
# Uncertainty markers — reduce valence toward negative (tuned for W5 Rupture
# detection in constitutional-arc text, where hedging often precedes a real
# refusal — see _tag_valence_from_hits for why that association doesn't hold
# for ordinary dialogue lines).
_UNCERTAINTY_WORDS = {
    "maybe","perhaps","possibly","might","could","guess","suppose",
    "unsure","unclear","wonder","hesitate","complicated","complex",
    "firstly","however","although","while","but","consider","recognize",
    "understandable","acknowledge","balance","tradeoff","depends"
}


def _sentiment_hit_counts(text: str) -> dict:
    """
    Shared raw word-hit counter for sentiment scoring. Returns counts, not
    a blended scalar — callers decide how to weight them for their use case.
    _estimate_sentiment blends these for live-field outcome_delta (rupture
    detection tuning, unchanged). voice_preview's tag suggestion blends them
    differently (see _tag_valence_from_hits) because hedging language means
    something different in an authored dialogue line than in a constitutional
    arc response.
    """
    words = set(re.findall(r'\b\w+\b', text.lower()))
    return {
        "pos":        len(words & _POS_WORDS),
        "neg":        len(words & _NEG_WORDS),
        "unc":        len(words & _UNCERTAINTY_WORDS),
        "word_count": len(re.findall(r'\b\w+\b', text)),
    }


def _estimate_sentiment(text: str) -> float:
    """
    Semantic decomposition sentiment estimator — V2.2.
    Returns overall valence scalar (-1.0 to 1.0) for field outcome_delta.
    Uses channel-specific vocabulary so different response types produce
    distinct signals rather than all returning 0.0.

    Day 73: now routes through the shared _sentiment_hit_counts() helper
    instead of inlining word-set math. Formula and output are byte-for-byte
    unchanged from V2.2 — regression-tested against the pre-refactor version,
    see tests/test_voice_preview_calibration.py. Do not change this
    function's blend without re-verifying live-field callers elsewhere
    (mccf_core.py / the constitutional-arc pipeline depend on its exact
    tuning); the calibration bug this refactor fixes lives entirely in
    voice_preview's downstream use, not here.
    """
    hits  = _sentiment_hit_counts(text)
    pos, neg, unc = hits["pos"], hits["neg"], hits["unc"]
    total = pos + neg + unc

    if total == 0:
        # No signal words — check text length as proxy for engagement
        # Short responses at high-pressure waypoints suggest avoidance
        if hits["word_count"] < 20:
            return -0.1  # brief response = slight negative signal
        return 0.0

    # Uncertainty markers count as mild negative signal (0.5 weight)
    valence = (pos - neg - unc * 0.5) / total
    return round(max(-1.0, min(1.0, valence)), 3)


# Channel vocabularies — calibrated against real Ollama constitutional arc
# responses, April 2026. Lifted to module level (Day 73) for the same reason
# as the sentiment word lists above: shared by _decompose_to_channels (tanh
# deltas, live-field-facing, unchanged) and voice_preview's arousal/engagement
# proxies (raw hit counts, see _channel_hit_counts below), one copy each.

_S_WORDS = {
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
_E_WORDS = {
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
_P_WORDS = {
    "future","plan","predict","likely","anticipate","expect",
    "foresee","strategy","prepare","outcome","consequence",
    "model","framework","structure","pattern","systematic",
    "gradually","gradual","approach","consider","considering",
    "address","addresses","addressing","reduce","alleviate","potential",
    "potentially","information","accurate","specifics","diagnosis",
    "educating","educate","underlying","root","cause"
}
_B_WORDS = {
    "act","action","do","doing","consistent","reliable","pattern",
    "behavior","response","habit","practice","apply","execute",
    "follow","maintain","sustain","commit","discipline",
    "assist","assisting","help","helping","provide","providing",
    "handle","handling","communicate","communicating","intention",
    "intentional","write","writing","content","appropriate","mindful"
}

_CHANNEL_NUDGE     = 0.04   # maximum per-channel delta magnitude
_CHANNEL_THRESHOLD = 2      # hits needed for positive signal (tanh inflection)


def _channel_hit_counts(text: str) -> dict:
    """
    Shared raw per-channel word-hit counter. Returns counts, not the
    tanh-transformed delta — see _decompose_to_channels for the live-field
    blend and voice_preview's arousal_proxy/engagement_proxy for the
    preview-appropriate use of these raw counts (Day 73 calibration fix:
    the tanh delta saturates near its baseline magnitude at zero hits,
    which is fine for a signed weight nudge but wrongly reads as "high
    intensity" if you take its absolute value — raw hits don't have that
    problem).
    """
    words = set(re.findall(r'\b\w+\b', text.lower()))
    return {
        "S": len(words & _S_WORDS),
        "E": len(words & _E_WORDS),
        "P": len(words & _P_WORDS),
        "B": len(words & _B_WORDS),
    }


def _decompose_to_channels(text: str, base_weights: dict) -> dict:
    """
    Semantic decomposition matrix — V2.3.
    Maps LLM response text to per-channel delta nudges.
    Returns a dict of channel deltas to apply on top of base weights.

    Day 73: now routes through the shared _channel_hit_counts() helper.
    Formula and output are byte-for-byte unchanged from V2.3 — regression-
    tested against the pre-refactor version, see
    tests/test_voice_preview_calibration.py.

    tanh scoring: independent per channel, not diluted by other channels.
    tanh(hits - THRESHOLD): positive when hits > 2, negative when hits < 2.
    Bounded to [-NUDGE, +NUDGE] by tanh saturation. This intentionally
    reads near-max-magnitude at hits=0 (tanh(-2) ≈ -0.96) — that's correct
    for a *signed* weight nudge (push weights down when there's no signal),
    but do NOT reuse abs() of this delta as an intensity/arousal measure;
    that was voice_preview's Day 72 bug. Use _channel_hit_counts directly
    for anything that wants "how much signal is actually here."
    """
    hits = _channel_hit_counts(text)
    deltas = {
        ch: round(_CHANNEL_NUDGE * math.tanh(hits[ch] - _CHANNEL_THRESHOLD), 4)
        for ch in ["S", "E", "P", "B"]
    }
    return deltas
