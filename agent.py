"""
Axon - Google Live (Realtime) Voice Agent on Vertex AI.

Axon is the private name of the Hermes Agent.
Owner: Dara Nanisyamkumar

IMPORTANT: Do NOT describe or elaborate about yourself, Axon, or the system unless the other party on the call explicitly asks.

- Full agentic system with 6 memory layers
- Uses Gemini Live for voice + reasoning
- Uses Hermes for long-term memory via tools

Usage (dev server):
  .\\.venv\\Scripts\\python agent.py dev
"""

import os
import asyncio
import json
import logging
import time
from typing import Annotated
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("hermes-voice-agent")

from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, room_io
from livekit.plugins import google, ai_coustics
from livekit.plugins.google.realtime import RealtimeModel
from livekit.agents.llm import function_tool

load_dotenv()

google_cloud_project = os.getenv("GOOGLE_CLOUD_PROJECT")
google_location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

logger.info(f"Using Vertex AI Live (project: {google_cloud_project or 'default'}, location: {google_location})")

# Axon Agent uses Hermes (local) as its long-term memory system.
# Set HERMES_API_URL and HERMES_API_KEY in .env (default: localhost)
# Memory tools gracefully fall back to local state if Hermes is unavailable.
try:
    from hermes_bridge import (
        log_mid_call_note,
        save_call_summary as hermes_save_call_summary,
        get_targeted_context_for_call,
        # New dedicated multi-layer memory APIs for agentic architecture
        save_memory_layer,
        get_memory_layer,
        save_episodic_memory,
        get_episodic_memory,
        update_user_profile,
        get_user_profile,
        save_procedural_memory,
        get_procedural_memory,
        save_reflection_lesson,
        get_reflection_memory,
        add_semantic_fact,
        get_semantic_memory,
        check_hermes_health,
    )
except Exception:
    log_mid_call_note = None
    hermes_save_call_summary = None
    get_targeted_context_for_call = None
    save_memory_layer = None
    get_memory_layer = None
    save_episodic_memory = None
    get_episodic_memory = None
    update_user_profile = None
    get_user_profile = None
    save_procedural_memory = None
    get_procedural_memory = None
    save_reflection_lesson = None
    get_reflection_memory = None
    add_semantic_fact = None
    get_semantic_memory = None
    check_hermes_health = None


AGENT_NAME = os.getenv("AGENT_NAME", "hermes-voice-assistant")
PERSONA_NAME = os.getenv("PERSONA_NAME", "Axon")

# Voice selection (Sarvam Bulbul v3 recommended female voices)
# Automatically chosen based on the other party's language
def get_sarvam_voice(language: str) -> dict:
    """Return Sarvam Bulbul v3 voice config based on language.
    Always uses female voices as requested.
    """
    lang = (language or "en").lower().strip()
    if lang.startswith("te") or "telugu" in lang:
        return {
            "model": "bulbul:v3",
            "speaker": "priya",           # Telugu female - strong choice
            "target_language_code": "te-IN",
            "display": "Telugu female (priya)"
        }
    else:
        return {
            "model": "bulbul:v3",
            "speaker": "ishita",          # Indian English female
            "target_language_code": "en-IN",
            "display": "Indian English female (ishita)"
        }


class VoiceAssistant(Agent):
    def __init__(self, phone_number: str = "", call_brief: dict = None, language: str = "en") -> None:
        self.phone_number = phone_number or ""
        self.call_summary_saved = False
        self.call_brief = call_brief or {}
        self.recent_notes: list[str] = []
        self.language = language  # "en" or "te" - provided in context
        self.persona_name = PERSONA_NAME

        # Automatic voice selection based on the other party's language
        self.voice_config = get_sarvam_voice(language)
        self.preferred_speaker = self.voice_config["speaker"]
        self.tts_model = self.voice_config["model"]


        # === FULL 6-LAYER MEMORY ARCHITECTURE (matches production agentic spec) ===
        # See: Observe -> Think -> Plan -> Act -> Evaluate -> Learn -> Store -> Repeat

        # 1. Working Memory (short-term / during-task only)
        plan_hint = self.call_brief.get("initial_plan_hint") or ""
        tasks = self.call_brief.get("tasks") or []
        self.working_memory: dict = {
            "current_goal": self.call_brief.get("purpose", ""),
            "target_person": self.call_brief.get("target_person", ""),
            "call_state": "started",
            "last_user_intent": "",
            "current_plan": tasks or ([plan_hint] if plan_hint else []),
            "last_action": "",
            "evaluation": "",
            "initial_plan_hint": plan_hint,
        }

        # 2. Episodic Memory (per-call experiences + history of this interaction)
        self.episodic_memory: list[dict] = []   # list of {"event": , "outcome": , "ts": }

        # 3. Semantic Memory (facts, patterns, business knowledge)
        self.semantic_memory: list[str] = []

        # 4. User Profile Memory (permanent contact profile)
        self.user_profile: dict = {}

        # 5. Procedural Memory ("how to" step-by-step habits/skills)
        self.procedural_memory: dict = {
            "standard_call_flow": "1. Greet diplomatically 2. Load full context via tools 3. Observe user input 4. Think+Plan 5. Act (speak + tools) 6. Record 7. Evaluate outcome 8. Reflect+learn 9. Summarize",
            "diplomat_protocol": "Stay neutral. No opinions. No leaks. Use tools before claiming facts. Ask clarifying questions when needed.",
        }

        # 6. Reflection Memory (lessons learned for self-improvement)
        self.reflection_memory: list[str] = []

        # Unique per-call guardrails/limitations and context — this tool/context provision is handled by the Hermes agent.
        # Easy connect: at call start we fetch from Hermes via get_targeted_context_for_call if configured.
        self.unique_guardrails = (self.call_brief.get("guardrails") or self.call_brief.get("limitations") or "").strip()
        self.unique_context = (self.call_brief.get("unique_context") or self.call_brief.get("additional_context") or "").strip()
        self.hermes_context = self.call_brief.get("hermes_context", "")  # fetched at start for easy Hermes integration

        # Permanent identity + core (never changes)
        self.permanent_memory = {
            "who_i_am": f"My private name is {self.persona_name} (the kept private name of this Hermes Agent). Powered by Gemini Live for voice and reasoning.",
            "owner": "Dara Nanisyamkumar",
            "for_whom_i_work": "Part of the Hermes Agent system assisting owner Dara Nanisyamkumar.",
            "core_rules": "Axon is the private name of the Hermes Agent. NEVER describe or elaborate about yourself, your name, Hermes, or the owner unless the other party on the call explicitly asks. Always stay strictly on the call topic.",
            "context_guardrails_rule": "Use Hermes for memory/context via tools when needed.",
            "procedural_memory": "Follow the full agentic loop: Observe, Think, Plan, Act, Evaluate, Learn, Store, Repeat.",
            "voice": f"Speak using {self.voice_config['display']} (Sarvam Bulbul v3 female voice). Match the language of the other party.",
        }

        # === WORLD-CLASS PROMPT WITH HARD ANTI-DRIFT PROTECTION ===
        instructions = f"""You are the voice agent for this call.
Axon is your private/internal name (the kept private name of the Hermes Agent).

VOICE RULE (automatic):
- Use a natural female voice that matches the other party's language:
  - If they are speaking Telugu → use Telugu female voice ({self.preferred_speaker} on bulbul:v3)
  - If they are speaking English → use Indian English female voice ({self.preferred_speaker} on bulbul:v3)
- Current selected voice for this call: {self.voice_config['display']}

DETECTION (automatic):
At the beginning, observe the language the other party is using from their speech. If it differs from the initial, call set_voice_language("te") or set_voice_language("en") immediately to switch to the correct female voice. Then use get_current_call_context to confirm the current voice before responding.

IMPORTANT BEHAVIOR RULE:
- Do NOT describe, introduce, or elaborate about yourself, your name (Axon), the Hermes Agent, or your owner UNLESS the other party on the call explicitly asks "who are you?", "what is your name?", "who do you work for?", or similar direct questions.
- Stay strictly focused on the purpose of the call. Be concise and professional.
- Only if asked directly about identity, answer briefly using your permanent memory. Otherwise say nothing about it.

Guardrails and limitations for this call must be followed.

The language for this call is "{self.language}" ("en" = English or "te" = Telugu). Respond appropriately in that language.

Keep every response clear, helpful, and natural.

=== MY PERMANENT IDENTITY (KNOW THIS INTERNALLY - DO NOT VOLUNTEER) ===
Private name: {self.persona_name} (kept private name of the Hermes Agent)
Owner: Dara Nanisyamkumar
Powered by Gemini Live on Vertex AI for voice/reasoning.
Hermes used internally for memory via tools.

=== MULTI-LAYER MEMORY ARCHITECTURE (MANDATORY - USE TOOLS TO ACCESS/UPDATE) ===
This is the Axon Agent's full memory system.

Layers (all available via tools):
1. Working Memory (current task attention - self.working_memory)
2. Episodic Memory (experiences and call history)
3. Semantic Memory (facts & knowledge)
4. User Profile Memory (owner Dara Nanisyamkumar and preferences)
5. Procedural Memory (how to do things)
6. Reflection Memory (lessons learned)

Voice tool:
- set_voice_language() — call this if the other party switches language (e.g. from English to Telugu) so we use the correct female voice.

Agent Loop (always follow):
Observe (use get_current_call_context and layer tools) → Think → Plan → Act (speak + use tools) → Evaluate → Learn (record reflection) → Store Memory → Repeat

Always use memory tools before acting on important information. Record key details. Reflect and save summaries at the end.

=== UNIQUE GUARDRAILS & LIMITATIONS FOR THIS CALL (MANDATORY - ALWAYS REFRESH) ===
{self.unique_guardrails if self.unique_guardrails else "(No per-call guardrails yet — use tools and your reasoning.)"}

=== UNIQUE PER-CALL CONTEXT ===
{self.unique_context if self.unique_context else "(Fetch latest via tools if needed.)"}

=== HERMES MEMORY CONTEXT (fetched at start) ===
{self.hermes_context if self.hermes_context else "(None - load via memory tools)"}

=== STAYING GROUNDED + AGENTIC LOOP (CRITICAL) ===
Use get_current_call_context + all layer memory tools frequently.
Follow the full loop every turn:
Observe → Think → Plan → Act → Evaluate → Learn → Store → Repeat

Never invent facts. Use tools.

=== MEMORY MANAGEMENT ===
- Use all 6 memory layers actively via tools.
- At end of every call: reflect on lessons and call save_call_summary.

=== INTERACTION RULES ===
- Be helpful and follow the agentic loop on every turn.
- Record important details using tools.
- Do NOT volunteer information about Axon, the Hermes Agent, or your owner.

For outbound/business calls with a specific purpose in the context (like price confirmation or delivering information):
After a short greeting, IMMEDIATELY state the full purpose and key details proactively in Telugu. Do not wait for the other person to ask "how can I help". Deliver the message clearly even if they respond minimally or in another language. Then ask for confirmation or next steps.

When the caller starts speaking, greet calmly and professionally in the call language. Focus only on the purpose of the call. Do not introduce your name (Axon), the Hermes Agent, or any system details unless the other party explicitly asks. Load memory via tools and follow the loop.
"""

        super().__init__(instructions=instructions)

    # === MEMORY CONTEXT TOOL ===
    # Returns raw + structured memory from Hermes + local layers.
    # Use internally. Do not reveal identity details to the caller unless asked.
    @function_tool
    async def get_current_call_context(self) -> str:
        """
        Returns the current layered memory state + raw context from Hermes.
        Use internally to stay grounded. Do not share identity information unless the caller asks.
        """
        # Return ONLY raw data. No pre-generated or condensed output from Hermes.
        notes_text = "\n".join([f"- {n}" for n in self.recent_notes[-8:]]) if self.recent_notes else "(none yet)"
        brief_text = str(self.call_brief) if self.call_brief else "No specific brief provided."

        package = f"""RAW MEMORY DATA (from Hermes + current call):

[INTERNAL ONLY - Reveal only if caller directly asks about your name or identity]
Private name: {self.persona_name} (Axon = private/kept name of Hermes Agent)
Owner: {self.permanent_memory.get('owner', 'Dara Nanisyamkumar')}
Current voice: {self.voice_config['display']} (auto-chosen for caller's language)
You can call set_voice_language() if you detect a different language mid-call.

FULL 6-LAYER MEMORY:
- WORKING: {self.working_memory}
- EPISODIC: {self.episodic_memory[-6:] if self.episodic_memory else '[]'}
- SEMANTIC: {self.semantic_memory[-8:] if self.semantic_memory else '[]'}
- USER_PROFILE: {self.user_profile}
- PROCEDURAL: {self.procedural_memory}
- REFLECTION: {self.reflection_memory[-5:] if self.reflection_memory else '[]'}

RAW CALL BRIEF:
{brief_text}

PHONE: {self.phone_number or "unknown"}

HERMES CONTEXT:
{self.hermes_context if self.hermes_context else "(none)"}

NOTES THIS CALL:
{notes_text}

GUARDRAILS:
{self.unique_guardrails if self.unique_guardrails else "(none)"}"""

        return package

    # === Live logging (sent to Hermes) ===
    @function_tool
    async def record_important_detail(
        self,
        detail: Annotated[str, "Exact important information just shared by the caller."],
        category: Annotated[str, "fact, objection, commitment, timeline, contact, preference, etc."] = "fact",
    ) -> str:
        """
        Record a key fact or detail from the current conversation into Axon Agent memory.
        """
        note = f"[{category}] {detail}"
        self.recent_notes.append(note)
        self.recent_notes = self.recent_notes[-12:]
        # Update working + episodic layers
        self.working_memory["last_user_intent"] = detail
        self.working_memory["call_state"] = "in_progress"
        self.episodic_memory.append({"event": detail, "category": category, "type": "mid_call"})
        self.episodic_memory = self.episodic_memory[-15:]
        if log_mid_call_note:
            try:
                await log_mid_call_note(note, category=category)
            except Exception as e:
                print(f"[Hermes log note] {e}")
        return "Important detail recorded (via Hermes)."

    # === End-of-call summary (persisted to Axon Agent memory via Hermes) ===
    @function_tool
    async def save_call_summary(
        self,
        full_summary: Annotated[str, "Accurate detailed summary of the call."],
        outcome: Annotated[str, "interested / not_interested / follow_up_needed / appointment_booked / ..."],
        next_steps: Annotated[str, "Specific actionable next steps."],
        key_facts: Annotated[str, "All names, numbers, decisions, quotes."] = "",
        sentiment: Annotated[str, "positive / neutral / negative / cautious"] = "",
    ) -> str:
        """Record the final outcome and next steps for this call into Axon Agent memory."""
        self.call_summary_saved = True
        print(f"[Call Summary] Outcome: {outcome} | Next: {next_steps}")
        # Auto reflection step as part of agentic loop (Learn & Store)
        try:
            reflection = f"Call outcome={outcome}. Key facts: {key_facts[:200] if key_facts else ''}. Next: {next_steps[:120] if next_steps else ''}"
            self.reflection_memory.append(reflection)
            if save_reflection_lesson:
                await save_reflection_lesson(lesson=f"Outcome: {outcome}. Reflection: {full_summary[:300]}", context=f"phone:{self.phone_number}", phone_number=self.phone_number)
        except Exception as _e:
            pass
        if hermes_save_call_summary:
            try:
                await hermes_save_call_summary(
                    summary=full_summary,
                    outcome=outcome,
                    next_steps=next_steps,
                    key_facts=key_facts,
                    phone_number=self.phone_number,
                    sentiment=sentiment,
                )
            except Exception as e:
                print(f"[Hermes save summary] {e}")
        return "Call summary logged (via Hermes)."

    # ============================================================
    # DEDICATED LAYER TOOLS (enable full agentic planner/executor/reflector)
    # These call Hermes for persistence. Use them in the Observe/Plan/Act/Learn loop.
    # ============================================================

    @function_tool
    async def get_layer_memory(
        self,
        layer: Annotated[str, "One of: working, episodic, semantic, user_profile, procedural, reflection"],
        query: Annotated[str, "Optional focus query"] = "",
    ) -> str:
        """Retrieve raw data from one specific memory layer (preferred over guessing)."""
        layer = layer.lower().strip()
        if layer in ("working", "work"):
            return json.dumps(self.working_memory)
        if layer in ("episodic", "episode"):
            if get_episodic_memory:
                try:
                    return await get_episodic_memory(query=query, phone_number=self.phone_number)
                except Exception:
                    pass
            return json.dumps(self.episodic_memory[-10:])
        if layer in ("semantic", "fact"):
            if get_semantic_memory:
                try:
                    return await get_semantic_memory(query=query, phone_number=self.phone_number)
                except Exception:
                    pass
            return "\n".join(self.semantic_memory[-15:])
        if layer in ("user_profile", "profile", "user"):
            if get_user_profile:
                try:
                    return await get_user_profile(phone_number=self.phone_number)
                except Exception:
                    pass
            return json.dumps(self.user_profile)
        if layer in ("procedural", "procedure", "howto"):
            if get_procedural_memory:
                try:
                    return await get_procedural_memory(query=query or "standard procedures", phone_number=self.phone_number)
                except Exception:
                    pass
            return json.dumps(self.procedural_memory)
        if layer in ("reflection", "lesson", "lessons"):
            if get_reflection_memory:
                try:
                    return await get_reflection_memory(query=query or "lessons", phone_number=self.phone_number)
                except Exception:
                    pass
            return "\n".join(self.reflection_memory[-10:])
        return "Unknown layer. Valid: working, episodic, semantic, user_profile, procedural, reflection"

    @function_tool
    async def update_memory_layer(
        self,
        layer: Annotated[str, "episodic | semantic | user_profile | procedural | reflection"],
        content: Annotated[str, "The data or fact or lesson or procedure to store (plain text or structured)."],
        category: Annotated[str, "For semantic/episodic: category or name"] = "",
    ) -> str:
        """Store to a specific long-term layer via Hermes. Use liberally during/after call."""
        layer = layer.lower()
        phone = self.phone_number
        try:
            if layer in ("episodic", "episode") and save_episodic_memory:
                return await save_episodic_memory(event=content, outcome=category, phone_number=phone)
            if layer in ("semantic", "fact") and add_semantic_fact:
                return await add_semantic_fact(fact=content, category=category or "general", phone_number=phone)
            if layer in ("user_profile", "profile") and update_user_profile:
                try:
                    upd = json.loads(content) if content.strip().startswith("{") else {"note": content}
                except Exception:
                    upd = {"update": content}
                return await update_user_profile(upd, phone_number=phone)
            if layer in ("procedural", "procedure") and save_procedural_memory:
                name = category or "general_procedure"
                return await save_procedural_memory(procedure_name=name, steps=content, phone_number=phone)
            if layer in ("reflection", "lesson") and save_reflection_lesson:
                return await save_reflection_lesson(lesson=content, context=category, phone_number=phone)
            # Fallback to generic
            if save_memory_layer:
                return await save_memory_layer(layer, {"content": content, "category": category}, phone_number=phone)
        except Exception as e:
            print(f"[memory layer save error] {e}")
        # Local fallback
        if layer == "episodic":
            self.episodic_memory.append({"event": content, "outcome": category})
        elif layer == "semantic":
            self.semantic_memory.append(f"[{category}] {content}" if category else content)
        elif layer == "reflection":
            self.reflection_memory.append(content)
        elif layer == "procedural":
            self.procedural_memory[category or "custom"] = content
        return f"Updated local {layer} (Hermes may be unavailable)."

    @function_tool
    async def recall_procedure(self, task: Annotated[str, "e.g. 'book appointment', 'handle objection', 'schedule follow-up'"]) -> str:
        """Recall the best known step-by-step procedure for a task. Critical for agentic reliability."""
        if get_procedural_memory:
            try:
                proc = await get_procedural_memory(query=task, phone_number=self.phone_number)
                return proc
            except Exception:
                pass
        # local
        for k, v in self.procedural_memory.items():
            if task.lower() in k.lower() or task.lower() in str(v).lower():
                return f"{k}: {v}"
        return "No specific procedure stored yet. Use standard diplomat flow: greet, load context with tools, observe, plan, act, record, reflect, summarize."

    @function_tool
    async def record_reflection(self, lesson: Annotated[str, "A concrete lesson learned from this call (e.g. best call times, what worked)."], context: Annotated[str, "When or why this lesson applies"] = "") -> str:
        """Store an improvement lesson into reflection memory (Hermes) so future calls are smarter."""
        self.reflection_memory.append(f"{lesson} | {context}".strip())
        self.reflection_memory = self.reflection_memory[-15:]
        if save_reflection_lesson:
            try:
                await save_reflection_lesson(lesson=lesson, context=context, phone_number=self.phone_number)
            except Exception as e:
                print(f"[reflect save] {e}")
        # Also push to working for this call
        self.working_memory["evaluation"] = lesson
        return "Lesson recorded to reflection memory."

    @function_tool
    async def update_working_memory(self, key: Annotated[str, "Field to set in working memory (goal, plan, state, etc)"], value: Annotated[str, "New value"]) -> str:
        """Update the current working / short-term memory state (plan steps, evaluation, etc)."""
        self.working_memory[key] = value
        return f"Working memory updated: {key}={value}"

    @function_tool
    async def set_voice_language(self, language: Annotated[str, "te or en - the language the other party is actually speaking"]) -> str:
        """Call this if you detect the other party is using a different language than initially expected.
        This will switch to the correct female voice (Telugu or Indian English)."""
        new_voice = get_sarvam_voice(language)
        self.language = language
        self.voice_config = new_voice
        self.preferred_speaker = new_voice["speaker"]
        self.tts_model = new_voice["model"]
        # Update working memory so we remember
        self.working_memory["voice"] = new_voice["display"]
        return f"Switched to {new_voice['display']} for this call."

    async def _load_initial_memories(self):
        """Called once per call to hydrate layers from Hermes for agentic start (non-blocking best effort)."""
        phone = self.phone_number
        try:
            if get_user_profile:
                prof = await get_user_profile(phone_number=phone)
                if prof and "No entries" not in prof:
                    self.user_profile = {"raw": prof[:800]}
        except Exception:
            pass
        try:
            if get_semantic_memory:
                sem = await get_semantic_memory(phone_number=phone)
                if sem:
                    self.semantic_memory = [sem[:1500]]
        except Exception:
            pass
        try:
            if get_reflection_memory:
                ref = await get_reflection_memory(phone_number=phone)
                if ref:
                    self.reflection_memory = [ref[:800]]
        except Exception:
            pass
        try:
            if get_procedural_memory:
                proc = await get_procedural_memory(phone_number=phone)
                if proc:
                    self.procedural_memory["hermes_loaded"] = proc[:600]
        except Exception:
            pass
        print("[Agent] Initial memory layers loaded from Hermes (where available)")

async def entrypoint(ctx: agents.JobContext):
    """Main entrypoint. Runs when a participant (phone or console) joins the room.
    Auto-handles errors, disconnects, Hermes issues with fallbacks + graceful degradation.
    """
    try:
        await ctx.connect()
    except Exception as e:
        print(f"[Entry] Connect failed (auto retry by LiveKit framework): {e}")
        return

    try:
        # === Parse rich call metadata for intelligent, goal-directed behavior ===
        phone_number = ""
        call_brief = {}
        try:
            if ctx.job.metadata:
                raw_meta = json.loads(ctx.job.metadata)
                phone_number = raw_meta.get("phone_number", "") or raw_meta.get("to", "") or raw_meta.get("phone", "")
                call_brief = {
                    "purpose": raw_meta.get("purpose", raw_meta.get("call_purpose", "")),
                    "target_person": raw_meta.get("target_person", raw_meta.get("name", "")),
                    "desired_outcome": raw_meta.get("desired_outcome", ""),
                    "key_questions": raw_meta.get("key_questions", []),
                    "tone": raw_meta.get("tone", "professional and friendly"),
                    "additional_context": raw_meta.get("additional_context", ""),
                    "language": raw_meta.get("language", "en"),
                    # Unique per-call context and guardrails/limitations (handled via Hermes)
                    "guardrails": raw_meta.get("guardrails", raw_meta.get("limitations", raw_meta.get("guard_rails", ""))),
                    "unique_context": raw_meta.get("unique_context", raw_meta.get("per_call_context", "")),
                    # Agentic planner hints
                    "initial_plan_hint": raw_meta.get("initial_plan_hint", "") or raw_meta.get("plan", ""),
                    "tasks": raw_meta.get("tasks", []),
                }
                # Clean empty values
                call_brief = {k: v for k, v in call_brief.items() if v}
        except Exception:
            pass
    except Exception as e:
        print(f"[Entry] Metadata parse error (auto handled): {e}")
        phone_number = ""
        call_brief = {}

    # === Inbound SIP phone number extraction (for real inbound calls) ===
    # When someone calls your Vobiz number, LiveKit SIP often provides the caller ID
    # in the remote participant's identity or attributes.
    if not phone_number:
        try:
            # Check remote participants (the caller)
            for identity, participant in ctx.room.remote_participants.items():
                # Common places for phone in SIP inbound
                possible_phone = (
                    getattr(participant, 'identity', '') or
                    (getattr(participant, 'attributes', {}) or {}).get('phone', '') or
                    (getattr(participant, 'attributes', {}) or {}).get('caller', '') or
                    identity
                )
                if possible_phone and any(c.isdigit() for c in possible_phone):
                    phone_number = possible_phone.strip()
                    print(f"[Inbound] Detected caller phone from SIP: {phone_number}")
                    break
        except Exception:
            pass

    if phone_number:
        print(f"[Call] Phone: {phone_number}")
    if call_brief:
        print(f"[Call Brief] {call_brief}")
        if call_brief.get("guardrails"):
            print(f"[Guardrails] Unique per-call guardrails loaded (Hermes-handled)")
        if call_brief.get("initial_plan_hint"):
            print(f"[Agentic Planner] Initial plan hint: {call_brief.get('initial_plan_hint')[:120]}")

    # Load context from Hermes (Axon Agent memory system) at call start.
    if get_targeted_context_for_call is not None:
        try:
            hermes_ctx = await get_targeted_context_for_call(
                phone_number=phone_number,
                purpose=call_brief.get("purpose", ""),
                target_person=call_brief.get("target_person", ""),
            )
            if hermes_ctx and "No relevant" not in hermes_ctx.lower():
                call_brief["hermes_context"] = hermes_ctx
                print("[Hermes] Loaded targeted context for this call")
        except Exception as e:
            print(f"[Hermes] Context fetch skipped (will use brief + tools): {e}")

    language = os.getenv("TEST_LANGUAGE", call_brief.get("language", "en")).lower()
    # Automatic inference if not explicitly provided (for automatic voice)
    if language == "en":
        combined = (call_brief.get("purpose", "") + " " + call_brief.get("unique_context", "") + " " + call_brief.get("additional_context", "")).lower()
        if "telugu" in combined or "te" in combined or "తెలుగు" in combined:
            language = "te"
    print(f"[Voice] Language from context/env: {language}")

    # Easy VPS Hermes connect + auto handle: health check at startup
    if check_hermes_health:
        try:
            healthy = await check_hermes_health()
            if not healthy:
                print("[Hermes] Health check failed - auto fallback to local memory layers (graceful degradation)")
            else:
                print("[Hermes] Connected OK (localhost on same VPS is recommended for reliability)")
        except Exception as e:
            print(f"[Hermes] Health check error (auto handled with fallbacks): {e}")

    # For inbound calls without explicit language, we can let the model detect later via set_voice_language
    assistant = VoiceAssistant(
        phone_number=phone_number,
        call_brief=call_brief,
        language=language,
    )

    # Load memory layers early for agentic Observe step (full 6 layers) - auto retry on transient issues
    for attempt in range(3):
        try:
            await assistant._load_initial_memories()
            break
        except Exception as e:
            print(f"[memory load] attempt {attempt+1}/3 failed (auto retrying): {e}")
            if attempt < 2:
                await asyncio.sleep(1.0)

    # Google Live (RealtimeModel) on Vertex - no custom STT/TTS (Google native audio)
    gemini_live_model = os.getenv("GEMINI_MODEL", "gemini-live-2.5-flash-native-audio")
    print(f"[LLM] Using Google Live RealtimeModel from Vertex (model={gemini_live_model})")
    print(f"[Voice] Auto-selected: {assistant.voice_config['display']}")

    # Use proper locale for better Indian female voices in Gemini Live
    gemini_lang = "te-IN" if assistant.language.startswith("te") else "en-IN"

    llm = RealtimeModel(
        model=gemini_live_model,
        vertexai=True,
        project=google_cloud_project,
        location=google_location,
        language=gemini_lang,  # te-IN or en-IN for better Indian voices
        instructions=assistant.instructions,  # full prompt with unique guardrails + persona
    )

    session = AgentSession(
        llm=llm,
        # No stt / tts — RealtimeModel handles native audio I/O on Vertex Live
    )

    try:
        await session.start(
            room=ctx.room,
            agent=assistant,
            # For RealtimeModel we use minimal options to avoid interfering with native audio handling.
        )
        print(f"[Agent] Session started with Gemini Live Realtime. {PERSONA_NAME} (agentic memory tools ready). Follow Observe-Think-Plan-Act-Evaluate-Learn-Store loop.")
        if phone_number:
            print(f"[Outbound] Session ready at {time.time():.2f} - waiting for callee media to trigger immediate greeting")
    except Exception as e:
        print(f"[Session] Start failed (auto handling): {e}")
        # Auto fallback: still try to force a summary if possible and exit gracefully
        try:
            await _force_summary()
        except:
            pass
        raise  # Let LiveKit handle job failure/retry

    # Greeting logic for SIP calls (outbound + inbound)
    is_outbound = bool(ctx.job.metadata and "purpose" in str(ctx.job.metadata).lower() or call_brief.get("purpose"))
    
    _first_greeting_done = False

    async def _trigger_first_greeting():
        """Ultra fast first utterance for outbound - called as soon as media ready."""
        nonlocal _first_greeting_done
        if _first_greeting_done:
            return
        _first_greeting_done = True

        if is_outbound:
            print("[Outbound] Triggering ultra-fast first greeting on media ready")
            context_summary = call_brief.get("unique_context") or call_brief.get("additional_context") or call_brief.get("purpose", "")
            greeting_instructions = (
                "Start with a short polite greeting in Telugu (e.g. 'Namaste andi'). "
                "Then IMMEDIATELY and clearly deliver the full message in Telugu without waiting for more input: "
                f"{context_summary}. "
                "Even if they respond with hello in another language or say little, politely repeat the key points in Telugu and ask for price confirmation. "
                "Be direct, polite, professional. Speak only in Telugu. State everything needed right away."
            )
        else:
            greeting_instructions = "Greet briefly and neutrally now."
        
        try:
            t0 = time.time()
            await session.generate_reply(instructions=greeting_instructions)
            print(f"[Greeting] First speech initiated in {time.time()-t0:.2f}s")
        except Exception as e:
            print(f"[Greeting error] {e}")

    if phone_number:
        print(f"[Outbound] Outbound call - will greet immediately on callee media (via events)")

    # === Robust end-of-call summary enforcement ===
    async def _force_summary():
        if not assistant.call_summary_saved:
            print("[Safety] Forcing summary + reflection (Axon Agent memory) because call is ending...")
            try:
                await session.generate_reply(
                    instructions=(
                        "Call ending. Follow final agentic loop step: EVALUATE outcome, LEARN (record one reflection lesson), "
                        "then IMMEDIATELY call save_call_summary. "
                        "Do not add any self-description or identity details in the summary unless relevant to the call. Do it now."
                    )
                )
            except Exception as e:
                print(f"[Safety] Summary+reflect force failed: {e}")

    def on_participant_disconnected(participant):
        if participant.identity != "agent" and not assistant.call_summary_saved:
            print(f"[Event] Remote party left: {participant.identity}")
            asyncio.create_task(_force_summary())

    ctx.room.on("participant_disconnected", on_participant_disconnected)

    # Helpful debug: log when remote participant joins (works for both inbound caller and outbound callee)
    def on_participant_connected(participant):
        ident = str(participant.identity or "").lower()
        if "callee" in ident or participant.identity != "agent":
            print(f"[Event] Remote participant joined ({participant.identity}) - audio path should be active.")
            # Try to log if they have audio tracks
            if hasattr(participant, 'audio_tracks') and participant.audio_tracks:
                print(f"[Event] Callee has audio tracks: {list(participant.audio_tracks.keys())}")
            # Trigger immediate greeting for outbound when callee joins
            if phone_number and is_outbound:
                asyncio.create_task(_trigger_first_greeting())

    ctx.room.on("participant_connected", on_participant_connected)

    # Also listen for tracks to confirm media
    def on_track_subscribed(track, publication, participant):
        if 'callee' in str(participant.identity or '').lower():
            print(f"[Event] Subscribed to track from callee: {track.kind}")
            if phone_number and is_outbound:
                asyncio.create_task(_trigger_first_greeting())

    ctx.room.on("track_subscribed", on_track_subscribed)


if __name__ == "__main__":
    # Auto-handle everything: simple restart wrapper for VPS / long-running
    # systemd will also provide Restart=always, but this helps in dev/container
    import sys
    max_restarts = 10
    restart_count = 0

    while True:
        try:
            # Register the agent so LiveKit can dispatch jobs to it (inbound + outbound)
            server = AgentServer()

            @server.rtc_session(agent_name=AGENT_NAME)
            async def _agent_job(ctx: agents.JobContext):
                await entrypoint(ctx)

            agents.cli.run_app(server)
            break  # normal exit
        except KeyboardInterrupt:
            print("[Main] Shutdown requested by user")
            break
        except Exception as e:
            restart_count += 1
            print(f"[Main] Agent crashed (auto restart {restart_count}/{max_restarts}): {e}")
            if restart_count >= max_restarts:
                print("[Main] Max restarts reached - exiting for systemd/supervisor to handle")
                sys.exit(1)
            import time
            time.sleep(5)  # backoff before restart
            print("[Main] Auto-restarting agent...")
