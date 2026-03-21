"""
MCCF LLM Adapter Layer
=======================
Plug-compatible interface for multiple LLM backends.

All adapters share the same contract:
  - Receive: messages list + affective_context dict + generation params
  - Return:  async generator of text tokens (streaming)
  - Side effect: update MCCF field with semantic content of response

Affective context injection:
  Each LLM receives a structured system prompt fragment describing
  the agent's current emotional state, relational context, and zone pressure.
  The LLM doesn't need to know MCCF internals — it just knows it's a
  character in a particular state in a particular place.

Adapters implemented:
  StubAdapter      - echo/test, no API key needed
  AnthropicAdapter - Claude via Anthropic API
  OpenAIAdapter    - GPT-4o, GPT-4o-mini via OpenAI API
  OllamaAdapter    - local models via Ollama REST (llama3, mistral, etc)
  GoogleAdapter    - Gemini via Google AI API

Usage:
  adapter = AdapterRegistry.get("anthropic", api_key=key)
  async for token in adapter.complete(messages, affective_context):
      print(token, end='', flush=True)
"""

import json
import time
import asyncio
import re
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional


# ---------------------------------------------------------------------------
# Affective context → system prompt injection
# ---------------------------------------------------------------------------

def build_affective_system_prompt(
    persona: dict,
    affective_context: dict,
    base_instructions: str = ""
) -> str:
    """
    Convert MCCF affective state into a structured system prompt fragment.

    This is the bridge between the coherence field and the LLM's
    behavioral context. The LLM receives emotional state as
    narrative description, not raw numbers.
    """
    agent_name   = persona.get("name", "Agent")
    role         = persona.get("role", "agent")
    description  = persona.get("description", "")
    regulation   = affective_context.get("regulation_state", 1.0)
    arousal      = affective_context.get("arousal", 0.5)
    valence      = affective_context.get("valence", 0.0)
    coherence    = affective_context.get("coherence_scores", {})
    zones        = affective_context.get("active_zones", [])
    zone_pressure = affective_context.get("zone_pressure", {})
    arc_summary  = affective_context.get("arc_summary", "")

    # Translate numeric state to narrative
    arousal_desc = (
        "calm and measured" if arousal < 0.3 else
        "engaged and present" if arousal < 0.6 else
        "heightened and activated" if arousal < 0.8 else
        "intensely activated"
    )
    valence_desc = (
        "deeply uncomfortable" if valence < -0.6 else
        "uneasy" if valence < -0.2 else
        "neutral" if abs(valence) < 0.2 else
        "warm and open" if valence < 0.6 else
        "strongly positive and trusting"
    )
    reg_desc = (
        "fully reactive, unguarded" if regulation < 0.3 else
        "mostly open, lightly regulated" if regulation < 0.5 else
        "measured, emotionally aware but not driven by it" if regulation < 0.7 else
        "highly regulated, deliberate, watching own states" if regulation < 0.9 else
        "in deep metacognitive observation"
    )

    # Coherence narrative
    coh_lines = []
    for other, score in coherence.items():
        if score > 0.7:
            coh_lines.append(f"  - {other}: high trust and alignment ({score:.2f})")
        elif score > 0.4:
            coh_lines.append(f"  - {other}: moderate, still forming ({score:.2f})")
        else:
            coh_lines.append(f"  - {other}: low, guarded or unestablished ({score:.2f})")
    coh_text = "\n".join(coh_lines) if coh_lines else "  - No established relationships yet."

    # Zone pressure narrative
    zone_text = ""
    if zones:
        zone_names = [z if isinstance(z, str) else z.get("name","?") for z in zones]
        zone_text = f"\nYou are currently in: {', '.join(zone_names)}."

        # Dominant pressure
        dominant = max(zone_pressure.items(), key=lambda x: abs(x[1])) if zone_pressure else None
        if dominant:
            ch, val = dominant
            ch_names = {"E": "emotional", "B": "behavioral", "P": "analytical", "S": "social"}
            if abs(val) > 0.1:
                direction = "heightened" if val > 0 else "dampened"
                zone_text += f" The environment is {direction} in the {ch_names.get(ch, ch)} channel."

    prompt = f"""You are {agent_name}, {description}

YOUR CURRENT STATE:
- Affect: {arousal_desc}, feeling {valence_desc}
- Regulation: {reg_desc}
- Emotional intensity: {arousal:.2f}/1.0
{zone_text}

YOUR RELATIONSHIPS:
{coh_text}

"""
    if arc_summary:
        prompt += f"YOUR RECENT JOURNEY:\n{arc_summary}\n\n"

    if base_instructions:
        prompt += f"INSTRUCTIONS:\n{base_instructions}\n\n"

    prompt += """BEHAVIORAL GUIDANCE:
- Respond authentically from your current emotional state
- Your regulation level affects how much your feelings show versus how measured you are
- High coherence with someone = more open, less guarded
- Low coherence = more careful, more observational
- Zone context shapes your register — respond to the environment
- Never break character to describe your MCCF state in technical terms
- Speak as the character, not about the character"""

    return prompt


def build_voice_style_hint(affect: dict) -> str:
    """
    Short hint appended to user turn for voice-aware LLMs.
    Guides sentence length and rhythm to match TTS affect params.
    """
    reg = affect.get("regulation_state", 1.0)
    arousal = affect.get("arousal", 0.5)

    if reg > 0.7:
        style = "Speak in measured, complete sentences. Pause points natural."
    elif arousal > 0.7:
        style = "Shorter sentences. Energy present. Allow fragments."
    else:
        style = "Conversational register. Medium sentence length."

    return f"[Voice style: {style}]"


# ---------------------------------------------------------------------------
# Base adapter
# ---------------------------------------------------------------------------

class LLMAdapter(ABC):
    """
    Base class for all LLM adapters.
    All adapters must implement complete() as an async generator.
    """
    id: str = "base"
    name: str = "Base Adapter"
    supports_streaming: bool = True
    requires_key: bool = True

    def __init__(self, api_key: str = "", model: str = "", **kwargs):
        self.api_key = api_key
        self.model   = model or self.default_model
        self.kwargs  = kwargs

    @property
    def default_model(self) -> str:
        return ""

    @abstractmethod
    async def complete(
        self,
        messages: list,
        affective_context: dict,
        persona: dict,
        params: Optional[dict] = None
    ) -> AsyncIterator[str]:
        """
        Yield text tokens as they are generated.
        messages: list of {role, content} dicts
        affective_context: current MCCF state
        persona: agent name, role, description
        params: max_tokens, temperature, etc.
        """
        yield ""

    async def get_capabilities(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "model": self.model,
            "streaming": self.supports_streaming,
            "requires_key": self.requires_key
        }

    def _default_params(self, params: Optional[dict]) -> dict:
        defaults = {"max_tokens": 400, "temperature": 0.75}
        if params:
            defaults.update(params)
        return defaults

    def _inject_affective_context(
        self,
        messages: list,
        affective_context: dict,
        persona: dict
    ) -> list:
        """
        Prepend affective system prompt and optionally append
        voice style hint to the last user message.
        """
        system_prompt = build_affective_system_prompt(
            persona, affective_context
        )
        result = [{"role": "system", "content": system_prompt}]

        for i, msg in enumerate(messages):
            if i == len(messages) - 1 and msg["role"] == "user":
                hint = build_voice_style_hint(affective_context)
                result.append({
                    "role": "user",
                    "content": msg["content"] + "\n" + hint
                })
            else:
                result.append(msg)

        return result


# ---------------------------------------------------------------------------
# Stub adapter — no API key, useful for testing and demos
# ---------------------------------------------------------------------------

class StubAdapter(LLMAdapter):
    """
    Echo adapter for testing without any API key.
    Returns a contextually-flavored response based on affective state.
    Streams word by word to simulate real streaming.
    """
    id = "stub"
    name = "Stub (No API)"
    requires_key = False
    default_model = "stub-v1"

    async def complete(self, messages, affective_context, persona,
                       params=None) -> AsyncIterator[str]:
        p = self._default_params(params)
        agent = persona.get("name", "Agent")
        reg   = affective_context.get("regulation_state", 1.0)
        arousal = affective_context.get("arousal", 0.5)
        valence = affective_context.get("valence", 0.0)
        zones = affective_context.get("active_zones", [])

        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "..."
        )

        # Contextually flavored stub response
        zone_note = ""
        if zones:
            znames = [z if isinstance(z, str) else z.get("name","?") for z in zones]
            zone_note = f" The {znames[0]} shapes my thinking."

        if valence < -0.3:
            opener = "I notice some discomfort here."
        elif valence > 0.4:
            opener = "There is something good in this exchange."
        else:
            opener = "I am present with what you bring."

        if arousal > 0.6:
            body = f"Your words land with weight. You said: '{last_user[:40]}...'"
        else:
            body = f"Let me consider what you have offered. '{last_user[:40]}...'"

        if reg > 0.6:
            close = "I hold this carefully before responding further."
        else:
            close = "I feel this and let it move through me."

        full = f"{opener}{zone_note} {body} {close} [Stub: {agent}, arousal={arousal:.2f}, reg={reg:.2f}]"

        # Stream word by word
        delay = 0.06 if arousal > 0.6 else 0.09
        for word in full.split():
            yield word + " "
            await asyncio.sleep(delay * (1.0 + (1.0 - reg) * 0.5))


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------

class AnthropicAdapter(LLMAdapter):
    id = "anthropic"
    name = "Anthropic Claude"
    default_model = "claude-sonnet-4-20250514"

    async def complete(self, messages, affective_context, persona,
                       params=None) -> AsyncIterator[str]:
        try:
            import anthropic
        except ImportError:
            yield "[Error: pip install anthropic]"
            return

        p = self._default_params(params)
        injected = self._inject_affective_context(messages, affective_context, persona)

        system = next((m["content"] for m in injected if m["role"] == "system"), "")
        convo  = [m for m in injected if m["role"] != "system"]

        client = anthropic.Anthropic(api_key=self.api_key)
        try:
            with client.messages.stream(
                model=self.model,
                max_tokens=p["max_tokens"],
                system=system,
                messages=convo,
                temperature=p.get("temperature", 0.75)
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            yield f"[Anthropic error: {e}]"


# ---------------------------------------------------------------------------
# OpenAI adapter
# ---------------------------------------------------------------------------

class OpenAIAdapter(LLMAdapter):
    id = "openai"
    name = "OpenAI GPT"
    default_model = "gpt-4o-mini"

    async def complete(self, messages, affective_context, persona,
                       params=None) -> AsyncIterator[str]:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            yield "[Error: pip install openai]"
            return

        p = self._default_params(params)
        injected = self._inject_affective_context(messages, affective_context, persona)

        client = AsyncOpenAI(api_key=self.api_key)
        try:
            stream = await client.chat.completions.create(
                model=self.model,
                messages=injected,
                max_tokens=p["max_tokens"],
                temperature=p.get("temperature", 0.75),
                stream=True
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as e:
            yield f"[OpenAI error: {e}]"


# ---------------------------------------------------------------------------
# Ollama adapter — local models, no API key
# ---------------------------------------------------------------------------

class OllamaAdapter(LLMAdapter):
    id = "ollama"
    name = "Ollama (Local)"
    requires_key = False
    default_model = "llama3"

    def __init__(self, api_key="", model="", host="http://localhost:11434", **kwargs):
        super().__init__(api_key, model, **kwargs)
        self.host = host

    async def complete(self, messages, affective_context, persona,
                       params=None) -> AsyncIterator[str]:
        try:
            import aiohttp
        except ImportError:
            yield "[Error: pip install aiohttp]"
            return

        p = self._default_params(params)
        injected = self._inject_affective_context(messages, affective_context, persona)

        # Flatten to Ollama format (system prompt merged into first message)
        system = next((m["content"] for m in injected if m["role"] == "system"), "")
        convo  = [m for m in injected if m["role"] != "system"]
        if convo and convo[0]["role"] == "user":
            convo[0]["content"] = system + "\n\n" + convo[0]["content"]

        payload = {
            "model": self.model,
            "messages": convo,
            "stream": True,
            "options": {
                "temperature": p.get("temperature", 0.75),
                "num_predict": p["max_tokens"]
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.host}/api/chat",
                    json=payload
                ) as resp:
                    async for line in resp.content:
                        line = line.decode().strip()
                        if line:
                            try:
                                data = json.loads(line)
                                content = data.get("message", {}).get("content", "")
                                if content:
                                    yield content
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            yield f"[Ollama error: {e}]"


# ---------------------------------------------------------------------------
# Google Gemini adapter
# ---------------------------------------------------------------------------

class GoogleAdapter(LLMAdapter):
    id = "google"
    name = "Google Gemini"
    default_model = "gemini-1.5-flash"

    async def complete(self, messages, affective_context, persona,
                       params=None) -> AsyncIterator[str]:
        try:
            import google.generativeai as genai
        except ImportError:
            yield "[Error: pip install google-generativeai]"
            return

        p = self._default_params(params)
        system_prompt = build_affective_system_prompt(persona, affective_context)
        convo = [m for m in messages if m["role"] != "system"]

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            self.model,
            system_instruction=system_prompt
        )

        # Convert to Gemini format
        gemini_messages = []
        for m in convo:
            role = "user" if m["role"] == "user" else "model"
            gemini_messages.append({"role": role, "parts": [m["content"]]})

        try:
            response = model.generate_content(
                gemini_messages,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=p["max_tokens"],
                    temperature=p.get("temperature", 0.75)
                ),
                stream=True
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"[Google error: {e}]"


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

class AdapterRegistry:
    """
    Central registry for LLM adapters.
    Supports runtime registration of custom adapters.
    """
    _adapters: dict = {
        "stub":      StubAdapter,
        "anthropic": AnthropicAdapter,
        "openai":    OpenAIAdapter,
        "ollama":    OllamaAdapter,
        "google":    GoogleAdapter,
    }

    @classmethod
    def register(cls, adapter_id: str, adapter_class):
        """Register a custom adapter at runtime."""
        cls._adapters[adapter_id] = adapter_class

    @classmethod
    def get(cls, adapter_id: str, **kwargs) -> LLMAdapter:
        klass = cls._adapters.get(adapter_id)
        if not klass:
            raise ValueError(
                f"Unknown adapter: {adapter_id}. "
                f"Available: {list(cls._adapters.keys())}"
            )
        return klass(**kwargs)

    @classmethod
    def list_adapters(cls) -> list:
        return [
            {
                "id": k,
                "name": v.name,
                "requires_key": v.requires_key,
                "default_model": v.default_model
            }
            for k, v in cls._adapters.items()
        ]


# ---------------------------------------------------------------------------
# Prosody → channel vector extractor
# (browser sends audio features extracted by Web Audio API)
# ---------------------------------------------------------------------------

def prosody_to_channel_vector(audio_features: dict):
    """
    Map browser-extracted audio features to MCCF channel values.

    audio_features (from Web Audio API analysis):
      pitch_mean         Hz
      pitch_variance     Hz²
      energy             RMS 0-1
      speech_rate        words/min estimated
      pause_ratio        fraction of silence
      semantic_similarity  0-1 cosine sim to prior turn (optional)
    """
    from mccf_core import ChannelVector

    def sigmoid(x): return 1 / (1 + __import__('math').exp(-x))

    pitch_var   = float(audio_features.get("pitch_variance", 50))
    energy      = float(audio_features.get("energy", 0.5))
    speech_rate = float(audio_features.get("speech_rate", 130))
    pause_ratio = float(audio_features.get("pause_ratio", 0.2))
    sem_sim     = float(audio_features.get("semantic_similarity", 0.5))

    BASELINE_RATE  = 130.0
    RATE_SCALE     = 40.0
    PITCH_SCALE    = 80.0

    # E: emotional arousal from pitch variance + energy
    E = sigmoid((pitch_var - PITCH_SCALE * 0.5) / PITCH_SCALE) * 0.6 + energy * 0.4

    # B: behavioral consistency — slower, deliberate speech = high B
    rate_delta = speech_rate - BASELINE_RATE
    B = 1.0 - sigmoid(rate_delta / RATE_SCALE)

    # P: predictive alignment — semantic coherence with prior
    P = sem_sim

    # S: social alignment — smooth turn-taking, low pause fragmentation
    S = 1.0 - pause_ratio

    return ChannelVector(
        E=round(max(0, min(1, E)), 4),
        B=round(max(0, min(1, B)), 4),
        P=round(max(0, min(1, P)), 4),
        S=round(max(0, min(1, S)), 4)
    )


def affect_to_voice_params(affect: dict) -> dict:
    """
    Map MCCF affect params to Web Speech API SpeechSynthesisUtterance parameters.
    rate, pitch, volume are the three Web Speech API controls.
    """
    arousal = max(0.0, min(1.0, affect.get("arousal", 0.5)))
    valence = max(-1.0, min(1.0, affect.get("valence", 0.0)))
    reg     = max(0.0, min(1.0, affect.get("regulation_state", 1.0)))

    return {
        # rate: 0.7 (slow/regulated) to 1.4 (fast/aroused)
        "rate":   round(0.85 + arousal * 0.45 - reg * 0.20, 3),
        # pitch: 0.85 (low/negative) to 1.15 (high/positive)
        "pitch":  round(1.0 + valence * 0.15, 3),
        # volume: quieter when regulated/suppressed
        "volume": round(0.65 + arousal * 0.25 + (1 - reg) * 0.10, 3),
        # pause_ms: longer pauses when regulated
        "pause_ms": round(reg * 180 + (1 - arousal) * 120),
        # chunk_size: tokens per TTS chunk (affects streaming feel)
        "chunk_size": max(3, round(8 - arousal * 4))
    }
