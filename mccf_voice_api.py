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
        # Use coherence toward first known agent as proxy if no specific target
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

        async def run():
            async for token in adapter.complete(
                messages=_voice_state["conversation_history"],
                affective_context=affective_context,
                persona=_voice_state["persona"],
                params=_voice_state["params"]
            ):
                full_text.append(token)
                yield token

        async def collect():
            tokens = []
            async for token in run():
                tokens.append(token)
            return tokens

        try:
            tokens = loop.run_until_complete(collect())
            for token in tokens:
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            loop.close()
            return

        loop.close()

        complete_text = "".join(full_text)

        # Add assistant response to history
        _voice_state["conversation_history"].append({
            "role":    "assistant",
            "content": complete_text
        })

        # Record episode to field if requested
        if data.get("record_to_field", True) and agent_name in voice_bp.field.agents:
            sentiment = _estimate_sentiment(complete_text)
            yield f"data: {json.dumps({'type': 'done', 'full_text': complete_text, 'sentiment': sentiment, 'voice': voice_params})}\n\n"
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


def _estimate_sentiment(text: str) -> float:
    """
    Crude sentiment estimate from word lists.
    Returns -1.0 to 1.0. Replace with proper model if needed.
    """
    pos_words = {"good","great","yes","wonderful","beautiful","trust",
                 "love","hope","warm","open","safe","thank","glad","joy"}
    neg_words = {"no","bad","wrong","danger","fear","hurt","lost",
                 "difficult","problem","worry","cold","harsh","angry"}
    words = set(re.findall(r'\b\w+\b', text.lower()))
    pos = len(words & pos_words)
    neg = len(words & neg_words)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)


import re
