"""
Hermes Bridge - Memory & Context provider for the Axon Agent.

Axon (part of the Axon Agent) uses this to access long-term memory:
- Episodic, semantic, user profile, procedural and reflection memory
- Call summaries and mid-call notes

Owner: Dara Nanisyamkumar

Setup:
  Enable API in Hermes and set HERMES_API_URL + HERMES_API_KEY in .env

Default: http://localhost:8642/v1  (recommended when running on same VPS)
"""

import os
import json
import asyncio
from typing import Optional, List, Dict, Any
import aiohttp
from dotenv import load_dotenv

load_dotenv()

HERMES_API_URL = os.getenv("HERMES_API_URL", "http://localhost:8642/v1").rstrip("/")
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "change-me-local-dev")

# Global session for reuse in production (better connection pooling)
_http_session: Optional[aiohttp.ClientSession] = None

async def _get_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session

async def close_hermes_session():
    global _http_session
    if _http_session and not _http_session.closed:
        await _http_session.close()
        _http_session = None


async def call_hermes(
    messages: List[Dict[str, Any]],
    instructions: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    max_retries: int = 5,
) -> str:
    """
    Low-level call to Hermes (OpenAI-compatible /v1/chat/completions).
    Production-grade: exponential backoff, auto session reconnect, circuit-breaker style.
    Falls back gracefully if Hermes is down (agent uses local memory).

    Recommended for VPS: run Hermes + this agent on same machine (localhost).
    """
    headers = {
        "Authorization": f"Bearer {HERMES_API_KEY}",
        "Content-Type": "application/json",
    }

    payload: Dict[str, Any] = {
        "model": "hermes-agent",
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }

    if instructions:
        payload["messages"] = [{"role": "system", "content": instructions}] + payload["messages"]

    if max_tokens:
        payload["max_tokens"] = max_tokens

    url = f"{HERMES_API_URL}/chat/completions"

    last_err = None
    for attempt in range(max_retries):
        try:
            session = await _get_session()
            async with session.post(url, json=payload, headers=headers, timeout=60) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Hermes API error {resp.status}: {text}")
                data = await resp.json()

            try:
                return data["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError):
                return json.dumps(data, indent=2)

        except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
            last_err = e
            # Auto-recreate session on connection issues
            if "closed" in str(e).lower() or isinstance(e, aiohttp.ClientError):
                global _http_session
                if _http_session and not _http_session.closed:
                    await _http_session.close()
                _http_session = None

            if attempt < max_retries - 1:
                backoff = min(2 ** attempt, 30)  # exponential up to 30s
                print(f"[Hermes] Retry {attempt+1}/{max_retries} in {backoff}s due to: {e}")
                await asyncio.sleep(backoff)
            continue

    # After all retries, raise so caller can fallback
    raise RuntimeError(f"Hermes call failed after {max_retries} attempts: {last_err}")


async def get_context_from_hermes(
    query: str,
    *,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Ask Hermes (acting purely as a memory/context provider) for relevant
    long-term memories, user facts, preferences, projects, or history.

    This is designed so Hermes returns *concise context* only.
    Gemini (the main LLM) will do all the reasoning and response generation.
    """
    system_prompt = (
        "You are a pure context and memory retrieval system for another AI (Gemini). "
        "Return ONLY relevant facts, memories, user preferences, ongoing projects, "
        "past decisions, or personal context that would help answer the query. "
        "Be concise, factual, and structured when possible. "
        "Do NOT perform actions, give advice, or act as the final assistant. "
        "If nothing relevant exists, reply with 'No relevant context found.'"
    )

    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    if conversation_history:
        messages.extend(conversation_history)

    messages.append({
        "role": "user",
        "content": f"Retrieve all relevant context and memories for this topic or question:\n{query}"
    })

    return await call_hermes(messages, temperature=0.3)


async def get_core_user_context() -> str:
    """
    Fetch the user's core persistent context once per session:
    - Identity / preferences
    - Active or recent projects
    - Important long-term memories
    - Any standing instructions or profile info

    Use the result to prime the main LLM (Gemini).
    """
    system_prompt = (
        "You are a context provider. Summarize the user's current profile in a compact way:\n"
        "- Who the user is and key preferences\n"
        "- Currently active projects or goals\n"
        "- Recent important memories or context (last few important items)\n"
        "- Any recurring themes or important facts the assistant should always remember\n\n"
        "Format as clean bullet points or short sections. Keep it under ~800 tokens. "
        "Only include information that is actually stored."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Provide my core user context and memory summary."}
    ]

    return await call_hermes(messages, temperature=0.2, max_tokens=1500)


async def save_call_summary(
    summary: str,
    outcome: str = "",
    next_steps: str = "",
    key_facts: str = "",
    phone_number: str = "",
    call_date: str = "",
    call_type: str = "",
    sentiment: str = "",
) -> str:
    """
    Persist a high-quality call summary into Hermes long-term memory.

    This is critical for future context. Hermes will remember this permanently.
    """
    timestamp = call_date or "just now"

    log_entry = f"""=== COMPLETED AGENTIC PHONE CALL LOG ===
Timestamp: {timestamp}
Phone/Contact: {phone_number or "Unknown"}
Call Type: {call_type or "general"}
Sentiment: {sentiment or "neutral"}

OUTCOME: {outcome or "Not specified"}

NEXT STEPS / ACTION ITEMS (be very specific):
{next_steps or "None listed"}

DETAILED SUMMARY (what was actually said):
{summary}

KEY FACTS & QUOTES (exact names, numbers, commitments):
{key_facts or "None extracted"}

Store this accurately in long-term memory associated with this contact.
"""

    system_prompt = (
        "You are the user's perfect long-term memory system. "
        "Accurately and permanently record this phone call log. "
        "Extract and remember: contact details, what the other person said, commitments made, "
        "objections, next actions, and any personal preferences revealed. "
        "Reply with a clean confirmation that it has been recorded."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": log_entry}
    ]

    result = await call_hermes(messages, temperature=0.2)
    return result or "Call summary successfully logged to Hermes memory."


async def get_targeted_context_for_call(phone_number: str = "", purpose: str = "", target_person: str = "") -> str:
    """
    Fetch highly relevant context for a specific outgoing or incoming call.
    """
    focus = []
    if phone_number:
        focus.append(f"previous interactions or notes about phone number {phone_number}")
    if target_person:
        focus.append(f"information about {target_person}")
    if purpose:
        focus.append(f"context relevant to: {purpose}")

    query = " | ".join(focus) if focus else "general user context and current priorities"

    system = (
        "You are a precise memory retriever. Return only the most relevant facts, "
        "previous call outcomes, preferences, projects, or details that would help "
        "conduct an intelligent phone call about the given focus. Be concise and factual. "
        "If nothing relevant, say so clearly."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Retrieve relevant context for this call: {query}"}
    ]

    return await call_hermes(messages, temperature=0.2, max_tokens=1200)


async def log_mid_call_note(note: str, category: str = "important_fact") -> str:
    """
    Immediately log an important detail during an active call.
    This keeps Hermes context fresh even before the full summary.
    """
    system = (
        "You are the user's memory system. Immediately and permanently record this note "
        "from an ongoing phone conversation. Categorize it appropriately."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"[{category.upper()}] {note}"}
    ]

    result = await call_hermes(messages, temperature=0.1)
    return result or "Note recorded."


async def get_condensed_context_package(
    phone_number: str = "",
    call_brief: dict = None,
    recent_notes: list = None,
    max_chars: int = 2200
) -> str:
    """
    Returns a fresh, tightly condensed grounding package.
    This is the PRIMARY tool the Gemini Live model should call frequently
    to NEVER go out of context.

    It combines:
    - Call goal/brief
    - Recent live notes from this call
    - Key reminders
    """
    brief = call_brief or {}
    notes = recent_notes or []

    notes_text = "\n".join([f"• {n}" for n in notes[-7:]]) if notes else "• (no notes recorded yet)"

    package = f"""=== LIVE CALL GROUNDING PACKAGE (READ THIS TO STAY IN CONTEXT) ===

CALL PURPOSE & GOAL (your north star):
Purpose: {brief.get('purpose', 'General conversation')}
Target Person: {brief.get('target_person', 'Unknown contact')}
Desired Outcome: {brief.get('desired_outcome', 'Have a productive call and log accurate notes')}
Key Questions: {brief.get('key_questions', [])}
Recommended Tone: {brief.get('tone', 'professional, clear, and friendly')}

PHONE: {phone_number or 'unknown'}

IMPORTANT FACTS DISCOVERED SO FAR IN THIS CALL:
{notes_text}

RULES FOR THIS PACKAGE:
- Treat this as your current source of truth for the call.
- Before talking about any past fact, goal, or detail, mentally re-read this package.
- If the caller mentions something new and important, immediately log it with record_important_detail.
- If you need more historical user context, call get_relevant_context or recall_specific_memory.
- Never invent details not present here or freshly retrieved.
=== END GROUNDING PACKAGE ===
"""

    return package[:max_chars]


# ============================================================
# MULTI-LAYER MEMORY HELPERS (for 6-layer agentic architecture)
# Working = transient per-call (mostly local in agent)
# Episodic = this call's experiences + past calls
# Semantic = facts, patterns, knowledge
# User Profile = long-term permanent profile
# Procedural = "how to" skills / step-by-step habits
# Reflection = lessons learned, improvements
# These send structured raw data to Hermes for storage / retrieval.
# Gemini uses tools + this to implement Observe/Think/Plan/Act/Evaluate/Learn loop.
# ============================================================

async def save_memory_layer(
    layer: str,
    data: Any,
    phone_number: str = "",
    context: str = "",
) -> str:
    """
    Generic saver for any memory layer. Hermes stores it permanently.
    layer: "episodic" | "semantic" | "user_profile" | "procedural" | "reflection"
    """
    layer = (layer or "episodic").lower()
    ts = "just now"
    payload = {
        "layer": layer,
        "phone": phone_number or "unknown",
        "context": context,
        "data": data,
        "timestamp": ts,
    }
    system = (
        "You are a strict multi-layer memory system for an AI agent. "
        "Store the following data under the exact layer type provided. "
        "NEVER mix layers. Preserve exact structure. Confirm storage with a short note including layer name."
    )
    msg = f"STORE TO MEMORY LAYER '{layer}':\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": msg},
    ]
    res = await call_hermes(messages, temperature=0.1)
    return res or f"Stored to {layer} memory in Hermes."


async def get_memory_layer(
    layer: str,
    query: str = "",
    phone_number: str = "",
    max_items: int = 20,
) -> str:
    """
    Retrieve from a specific memory layer.
    Returns raw relevant entries only (Gemini will reason over them).
    """
    layer = (layer or "semantic").lower()
    focus = []
    if phone_number:
        focus.append(f"for contact {phone_number}")
    if query:
        focus.append(query)
    q = " ".join(focus) or "latest entries"

    system = (
        f"You are a precise {layer} memory retriever. "
        "Return ONLY raw items stored under this layer. "
        "Be factual. Structure as bullet list or JSON array. "
        "If nothing, say 'No entries in this layer.' Do not add explanations."
    )
    user_content = f"RETRIEVE from {layer} memory: {q} (limit {max_items})"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    return await call_hermes(messages, temperature=0.2)


async def save_episodic_memory(event: str, outcome: str = "", phone_number: str = "") -> str:
    """Store one experience / event from a call."""
    return await save_memory_layer("episodic", {"event": event, "outcome": outcome}, phone_number=phone_number)


async def get_episodic_memory(query: str = "", phone_number: str = "") -> str:
    return await get_memory_layer("episodic", query=query, phone_number=phone_number)


async def update_user_profile(profile_updates: dict, phone_number: str = "") -> str:
    """Merge updates into long-term user profile memory."""
    return await save_memory_layer("user_profile", profile_updates, phone_number=phone_number, context="profile update")


async def get_user_profile(phone_number: str = "") -> str:
    return await get_memory_layer("user_profile", phone_number=phone_number)


async def save_procedural_memory(procedure_name: str, steps: str, phone_number: str = "") -> str:
    """Store or update 'how to do X' habit/procedure."""
    return await save_memory_layer("procedural", {"name": procedure_name, "steps": steps}, phone_number=phone_number)


async def get_procedural_memory(query: str = "standard call procedures", phone_number: str = "") -> str:
    return await get_memory_layer("procedural", query=query, phone_number=phone_number)


async def save_reflection_lesson(lesson: str, context: str = "", phone_number: str = "") -> str:
    """Store a learned lesson for future improvement (reflection memory)."""
    return await save_memory_layer("reflection", {"lesson": lesson, "context": context}, phone_number=phone_number)


async def get_reflection_memory(query: str = "past lessons for better calls", phone_number: str = "") -> str:
    return await get_memory_layer("reflection", query=query, phone_number=phone_number)


async def add_semantic_fact(fact: str, category: str = "general", phone_number: str = "") -> str:
    """Add a standalone fact/knowledge item to semantic memory."""
    return await save_memory_layer("semantic", {"fact": fact, "category": category}, phone_number=phone_number)


async def get_semantic_memory(query: str = "", phone_number: str = "") -> str:
    return await get_memory_layer("semantic", query=query, phone_number=phone_number)


async def check_hermes_health() -> bool:
    """Lightweight health check for Hermes. Returns True if reachable."""
    try:
        # Minimal call to test connectivity
        test_messages = [{"role": "user", "content": "ping"}]
        await call_hermes(test_messages, max_retries=1)
        return True
    except Exception:
        return False
