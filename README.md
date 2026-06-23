# Axon — Hermes Agent Voice (Gemini Live + Hermes Memory)

**Axon** is the private name of the Hermes Agent.
Owner: Dara Nanisyamkumar

On calls: Do not describe or elaborate about yourself or the system unless the other party explicitly asks. Stay focused on the task.

**Core stack (no compromises):**
- **Gemini Live** = Main brain (best-in-class realtime voice + reasoning)
- **Hermes** = Perfect long-term memory + structured call logging (read + write)
- **Vobiz + LiveKit** = Reliable global telephony

**What makes it world-class:**
- Deep, targeted context retrieval before and during every call
- Strict "no hallucination" grounding rules
- Immediate mid-call memory logging
- Goal-oriented behavior when you provide a clear brief
- Automatic high-quality structured summaries saved to Hermes
- Robust end-of-call enforcement so nothing is ever lost
- Natural yet highly effective conversation control

The more specific the brief you give when launching a call, the more intelligent and reliable the agent becomes.

## Architecture

```
Phone (Vobiz)
    ↔ LiveKit SIP
        ↔ LiveKit Room
            ↔ LiveKit Agent
                ├── Gemini RealtimeModel (MAIN LLM)
                │     ├── Reads core context at start
                │     ├── Uses context tools during call
                │     └── Writes structured summary at end
                └── Tools:
                      • get_relevant_context / recall_specific_memory
                      • save_call_summary   ← writes back to Hermes
                        ↔ Hermes (memory + call log store)
```

**Key principle**:
- **Axon** = private name of the Hermes Agent voice component (Gemini Live)
- **Hermes** = long-term memory system
- **Important**: On calls, do not volunteer name or system details unless asked.

### Automatic Voice Selection (Female only)
The agent now automatically chooses the voice based on the other party's language:

- Telugu speaker → Telugu female (`priya` on Sarvam Bulbul v3)
- English speaker → Indian English female (`ishita` on Sarvam Bulbul v3)

Pass `language: "te"` or `language: "en"` in the call brief (make_call.py or dispatch metadata).
The agent can also call `set_voice_language()` mid-call if it detects a switch.

## Full Agentic Framework Architecture (6 Memory Layers + Loop)

This goes far beyond a simple scripted call flow. The implementation matches this production-grade design:

```
                    ┌─────────────────┐
                    │     USER        │
                    └────────┬────────┘
                             │
                             ▼
                ┌──────────────────────┐
                │ INTENT UNDERSTANDING │
                └────────┬─────────────┘
                         │
                         ▼
              ┌────────────────────────┐
              │      TASK PLANNER       │
              └────────┬───────────────┘
                       │
      ┌────────────────┼────────────────┐
      ▼                ▼                ▼
┌────────────┐ ┌─────────────┐ ┌─────────────┐
│ CALL TOOL  │ │ SEARCH TOOL │ │ CRM / APIs  │   (memory tools here)
└─────┬──────┘ └──────┬──────┘ └──────┬──────┘
      │               │               │
      └───────────────┼───────────────┘
                      ▼
           ┌────────────────────┐
           │ EXECUTION AGENT    │
           └─────────┬──────────┘
                     │
                     ▼
           ┌────────────────────┐
           │ REFLECTION AGENT   │
           └─────────┬──────────┘
                     │
                     ▼
           ┌────────────────────┐
           │ MEMORY SYSTEM      │
           └─────────┬──────────┘
                     │
                     ▼
           ┌────────────────────┐
           │ USER REPORTING     │
           └────────────────────┘
```

### Memory Architecture (6 layers)

1. **Working Memory** (short-term attention): current goal, plan, state. In-process dict. Reset per call.
2. **Episodic Memory**: call experiences, transcripts notes, successes/failures. Stored via Hermes.
3. **Semantic Memory**: facts, learned patterns, business knowledge (not tied to single event).
4. **User Profile Memory**: permanent contact prefs, contact info, style. Loaded every call.
5. **Procedural Memory**: "how to" step-by-step (e.g. "how to book haircut" or "standard call + reflect flow"). Prevents re-learning.
6. **Reflection Memory**: lessons (e.g. "Restaurant chains answer faster 10-11am"). This is how the agent improves autonomously.

**Agent Loop** (executed internally by Gemini + tools on every turn):
```
Observe → Think → Plan → Act → Evaluate → Learn → Store Memory → Repeat
```

**Recommended Memory Stack** (realized via Hermes + local):
- Working: local
- Episodic / Semantic / Reflection / Procedural / Profile: Hermes (via dedicated tools)

See `agent.py` (VoiceAssistant + tools: get_layer_memory, update_memory_layer, record_reflection, recall_procedure, get_current_call_context...) and `hermes_bridge.py` for the concrete implementation.

**Ideal Call Agent Framework** (what the code follows):
```
User
 │
 ▼
Intent Detection (from brief + memory)
 │
 ▼
Planner (Gemini reasons a plan into working_memory)
 │
 ├── Retrieve Memories (all 6 layers via tools)
 │
 ├── Build Task Plan
 │
 ├── Execute Call (voice + tool calls)
 │
 ├── Monitor Conversation
 │
 ├── Update Working Memory
 │
 ├── Handle Exceptions (guardrails)
 │
 ├── Reflect On Outcome
 │
 └── Save Long-Term Learnings (reflection + summary)
 │
 ▼
Final Report (saved to Hermes)
```

**Production Readiness & Easy Local Hermes Connection (Same VPS)**

### VPS / Linux Production Deployment (Recommended)

**Run Hermes + Axon on the same VPS machine** for easiest/lowest-latency connection (localhost).

1. Install on VPS (Ubuntu/Debian example):
   ```bash
   sudo apt update && sudo apt install -y python3-venv python3-pip git
   git clone <your-repo> /opt/hermes-voice-assistant
   cd /opt/hermes-voice-assistant
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Configure `.env` (use localhost for Hermes):
   ```
   HERMES_API_URL=http://127.0.0.1:8642/v1
   HERMES_API_KEY=your-key
   # ... other keys
   ```

3. Create systemd service for auto-start + auto-restart on crash:

   `/etc/systemd/system/axon-agent.service`:
   ```ini
   [Unit]
   Description=Axon Voice Agent (Hermes + Gemini Live)
   After=network.target

   [Service]
   Type=simple
   User=youruser
   WorkingDirectory=/opt/hermes-voice-assistant
   Environment=PATH=/opt/hermes-voice-assistant/.venv/bin
   EnvironmentFile=/opt/hermes-voice-assistant/.env
   ExecStart=/opt/hermes-voice-assistant/.venv/bin/python agent.py dev
   Restart=always
   RestartSec=5
   StandardOutput=journal
   StandardError=journal

   [Install]
   WantedBy=multi-user.target
   ```

   Enable:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now axon-agent
   sudo journalctl -u axon-agent -f   # live logs
   ```

   The agent now has built-in auto-restart wrapper + graceful degradation (local memory fallbacks when Hermes is temporarily down).

**Easy Hermes Connection**
- Default in code: `http://localhost:8642/v1`
- Run Hermes and this agent on the **same VPS** (no firewall, lowest latency).
- At startup the agent does a health check and auto-falls back to local memory if Hermes is unreachable.
- All tools (`get_*`, `save_*`, `set_voice_language`) auto-retry with exponential backoff.

### Verifying Conversation + Agentic Behavior (place call and check)

1. On VPS:
   ```bash
   sudo systemctl status axon-agent
   # or for dev
   source .venv/bin/activate
   python agent.py dev
   ```

2. From your machine or another terminal, use make_call.py (or call your Vobiz number for inbound).

3. In the agent logs, search for:
   - `[Agent] Initial memory layers loaded`
   - `[Voice] Auto-selected`
   - `start reading stream` + `callee`
   - `conversation_item_added`
   - Tool calls + final summary

**Production ready** (auto handles issues):
- Realtime audio via Gemini Live (robust low-latency)
- Hermes tools with retries, auto session reconnect, health checks + graceful fallback to local memory
- Per-call unique guardrails (changeable, no leaks)
- Diplomatic/neutral persona (configurable)
- Proper session lifecycle, summary enforcement on any disconnect/error
- Lock in make_call to prevent duplicate calls
- Built-in auto-restart on crash (systemd + code wrapper)
- Auto-recovery from network/Hermes/Gemini transient failures

Use `agent.py dev` for testing; for full prod consider `lk agents` or Docker + systemd.

## Easy Hermes Integration

1. Enable API in Hermes (`API_SERVER_ENABLED=true`, `API_SERVER_KEY=...`)
2. In this project's `.env`:
   ```
   HERMES_API_URL=http://your-hermes:8642/v1
   HERMES_API_KEY=...
   ```
3. In `make_call.py` or dispatch metadata, pass:
   - `guardrails` / `limitations` (unique per call)
   - `unique_context` (per-call data)
   - `purpose`, `target_person`, etc.
4. At call start, agent fetches extra from Hermes (via `get_targeted_context_for_call`).
5. Tools (`get_current_call_context`, `record_important_detail`, `save_call_summary`) call Hermes automatically.
6. Hermes only needs to return raw context/notes — Gemini generates the final context + guardrails using its reasoning.

See `hermes_bridge.py` for the helpers and `agent.py` VoiceAssistant for usage.

## Call Summaries & Agentic Usage (Main Feature)

Because you want to use this to talk to people **instead of wasting your time**, the agent is heavily optimized for call logging:

- Gemini is instructed to **save a summary at the end of every call**.
- It uses the `save_call_summary` tool.
- Summaries include: full summary, outcome, next_steps, key_facts.
- The summary is written to Hermes using a memory-logging prompt so it becomes future context.

### What a good saved summary looks like (in Hermes)

```
COMPLETED PHONE CALL LOG
Phone: +91...
OUTCOME: follow_up_needed
NEXT STEPS: Send the pricing PDF to john@company.com and schedule a demo for next Tuesday.
SUMMARY: ...
KEY FACTS: ...
```

### How to use for agentic calling

1. Make outbound calls using `make_call.py --to +91...`
2. The agent will:
   - Pull your current context from Hermes at the start
   - Conduct the conversation using Gemini Live
   - **Automatically save a detailed summary** when the call ends
3. Later ask Hermes (via chat, Telegram, etc.):
   - "What happened in the call with +91..."
   - "Any follow ups from recent calls?"
   - "Summarize all conversations with Acme Corp"

You can also explicitly tell it during a call:
> "Please summarize everything and save it."

### Customizing summary behavior

Edit the instructions inside `agent.py` (in `VoiceAssistant.__init__`) to change:
- What fields are required
- Tone of summaries
- Whether it speaks the "I've saved it" message or stays silent

## Production Readiness & Hermes Connection

This setup is designed to be **production-ready** out of the box:

- Uses Gemini Live RealtimeModel (low-latency native audio on Vertex)
- Per-call unique, changeable guardrails (injected via metadata, enforced in prompt)
- Hermes tools have retries + automatic fallback if Hermes is down
- Lock in `make_call.py` prevents accidental duplicate calls
- Robust session handling, summary enforcement on disconnect
- Axon persona (part of Axon Agent, owner Dara Nanisyamkumar) - set PERSONA_NAME in .env

### Easy Hermes Agent Connection (recommended flow)

1. In Hermes: `API_SERVER_ENABLED=true`, set `API_SERVER_KEY`
2. In this `.env`:
   ```
   HERMES_API_URL=http://your-hermes-host:8642/v1
   HERMES_API_KEY=...
   PERSONA_NAME=Axon
   ```
3. When launching calls (via `make_call.py` or your dispatch code), include in metadata:
   - `guardrails` or `limitations` (unique rules for *this* call)
   - `unique_context` (per-call facts)
   - Standard fields: purpose, target_person, etc.
4. Agent automatically:
   - Fetches extra context from Hermes at call start (`get_targeted_context_for_call`)
   - Exposes tools that call Hermes (`get_current_call_context`, record, save)
   - Gemini uses raw Hermes data + brief to generate final context/guardrails

Hermes does **not** need to be the LLM — it is the memory/context source. Gemini Live does voice + reasoning.

See `hermes_bridge.py` (the helpers) and the tools in `VoiceAssistant` for implementation.

### Production Deployment

- **Testing**: `python agent.py dev` (one terminal) + `make_call.py` (another)
- **Prod**: 
  - Deploy the agent worker to LiveKit (use `lk agent` CLI or containerize the app).
  - Set all secrets via env (never commit .env).
  - Use a stable Hermes instance (not localhost).
  - Monitor via LiveKit dashboard + your logs.
  - For outbound: ensure trunk is production-grade.
- Scale: LiveKit + Gemini handle concurrency; multiple workers for high volume.
- Security: Guardrails per call, no personal info in prompts, use HTTPS for Hermes.

Update `GEMINI_MODEL` only if needed. Default `gemini-live-2.5-flash-native-audio` is current for Vertex Live.


## Step 1: Prepare Hermes for external calls

On the machine running Hermes:

```bash
# Edit ~/.hermes/.env
API_SERVER_ENABLED=true
API_SERVER_KEY=some-strong-secret-key-here
```

Then start the gateway:

```bash
hermes gateway
```

You should see:
```
[API Server] API server listening on http://127.0.0.1:8642
```

**For phone access later**, make Hermes reachable:
- Same machine (easiest for testing)
- Or run on a VPS and use the private IP / tailscale / ngrok / Cloudflare tunnel
- Update `HERMES_API_URL` in this project's `.env`

Test it quickly:

```bash
curl http://localhost:8642/v1/chat/completions \
  -H "Authorization: Bearer some-strong-secret-key-here" \
  -H "Content-Type: application/json" \
  -d '{"model":"hermes-agent","messages":[{"role":"user","content":"hello"}]}'
```

## Step 2: Deploy the Script on the VPS

See the VPS section above for the recommended way (same machine as Hermes, localhost connection, systemd service).

Basic VPS setup commands are in the "Production Readiness & Easy Local Hermes Connection" section.

**Requirements:**
- Vertex AI API enabled in your GCP project
- Billing account linked (Vertex usually requires it)
- Your Google account (or service account) must have access to the project

The agent will print "[Google] Using Vertex AI ..." when it starts.

## Step 3: Vobiz + LiveKit SIP setup (phone numbers)

Follow the official Vobiz LiveKit guide:
https://docs.vobiz.ai/integrations/livekit

### Quick outbound trunk

1. In this folder run:
   ```powershell
   uv run python setup_trunk.py
   ```

2. Copy the printed `OUTBOUND_TRUNK_ID` into `.env`

### Inbound calls (real incoming calls to your Vobiz number)

**This is the #1 reason people get stuck** — inbound setup is completely separate from the outbound trunk.

Your symptom ("calls not going through from multiple phones") almost always means the call is not being routed from Vobiz to LiveKit, or LiveKit has no Dispatch Rule.

### Quick Diagnostic First

1. Start the agent (must be running):
   ```powershell
   cd $env:USERPROFILE\projects\hermes-voice-assistant
   .\.venv\Scripts\python agent.py dev
   ```

2. While the agent is running, call **+918065481208** from any other phone.

3. Immediately tell me:
   - What happens on the calling phone? (rings forever, busy, voicemail, connects with silence?)
   - Any new lines in the `agent.py dev` terminal when you dial?

### Most Likely Fix (do these in order)

**A. Set inbound_destination in Vobiz (very common missing step)**

1. Log into Vobiz console.
2. Go to your SIP trunk settings.
3. Find the field called `inbound_destination` or "SIP Inbound URI".
4. Set it to exactly this (no `sip:`):
   ```
   vobiz-2s614xio.sip.livekit.cloud
   ```
5. Save and wait 30-60 seconds.

**B. Create Inbound Trunk + Dispatch Rule in LiveKit (this is what actually sends the call to Axon)**

Go to your LiveKit dashboard → **SIP** section:

1. **Create Inbound Trunk**
   - Name: Vobiz Inbound
   - Save. Copy the Trunk ID if shown.

2. **Create Dispatch Rule** (the most important part)
   - Name: Axon Inbound
   - Rule Type: **SIP**
   - Select the Inbound Trunk you just created (or choose "Match by phone number" and put `+918065481208`)
   - **Agent Name**: `hermes-voice-assistant`   ← must match your .env exactly
   - Save.

**C. Test again**

- Keep `agent.py dev` running.
- Call the number again.
- Watch the agent terminal closely.

You should see lines like:
- `received job request`
- `[Inbound] Detected caller phone from SIP: ...`
- `[Voice] Auto-selected: ...`
- Session starting

### Extra things that sometimes block inbound

- The Vobiz number must be assigned to the trunk that has inbound enabled.
- Sometimes you need to wait 1-2 minutes after creating trunks/rules.
- Make sure `AGENT_NAME=hermes-voice-assistant` is still in your .env (it was last time).

Reply with:
1. What exactly happens when you call now.
2. Any output from the agent terminal when you dial.
3. Whether you completed steps A and B above.

We'll get it routing. This is almost always a one-time config thing.

## Real phone call test (Vobiz outbound)

You **must** run the agent worker first:

```powershell
# Terminal 1 (keep running)
cd $env:USERPROFILE\projects\hermes-voice-assistant
.\.venv\Scripts\python agent.py dev
```

Then in another terminal:

```powershell
# Terminal 2
.\.venv\Scripts\python make_call.py `
  --to +918074835456 `
  --language te `
  --person "Dara Nanisyamkumar" `
  --purpose "Sleep reminder and friendly check-in" `
  --goal "Deliver a calm sleep reminder, confirm understanding or preference, record key facts, reflect, and save full summary" `
  --plan "1. Greet neutral. 2. Load full context+memories via tools. 3. Deliver reminder. 4. Ask simple confirmation. 5. Record details + reflect lesson. 6. Save authoritative summary." `
  --guardrails "You are a neutral diplomat ONLY. Never show interest/sales/enthusiasm. No owner info leaks. Use EVERY memory layer tool (get_layer_memory, update_memory_layer, record_reflection, get_current_call_context, save_call_summary). Follow Observe-Think-Plan-Act-Evaluate-Learn-Store loop. Stay in Telugu. Keep responses short and factual." `
  --unique-context "Friendly sleep reminder for Dara. You are helping with consistent good sleep. Record everything important. Reflect on conversation effectiveness at end." `
  --tone "neutral, calm and professional diplomat"
```

Watch Terminal 1 for:
- Job pickup
- Realtime session start
- Any Vertex or audio errors

The call should have audio both ways once the worker attaches.


**VPS/Linux start helper** (optional):
Create `start-axon.sh`:
```bash
#!/bin/bash
cd /opt/hermes-voice-assistant
source .venv/bin/activate
exec python agent.py dev
```
`chmod +x start-axon.sh`

Then use it in the systemd ExecStart.

**Important on Windows:** The plain `python` command often points to a broken Microsoft Store stub. **Always use the venv Python explicitly** like this:

```powershell
cd $env:USERPROFILE\projects\hermes-voice-assistant

# Telugu console test (Sarvam voices)
$env:TEST_LANGUAGE = "te"
.\.venv\Scripts\python agent.py console

# English console test
# $env:TEST_LANGUAGE = "en"
# .\ .venv\Scripts\python agent.py console
```

To make a real call (run agent in one window, make_call in another):

```powershell
# Window 1 - start the worker
.\.venv\Scripts\python agent.py dev

# Window 2 - make the call
.\.venv\Scripts\python make_call.py --to +918074835456 --language te --purpose "Test Telugu with Sarvam"
```

Speak into your microphone. The language from `TEST_LANGUAGE` (console) or `--language` / metadata (real calls) chooses Sarvam (te) or Google (en).

### Validating Sarvam key directly (PowerShell example)
```powershell
Invoke-WebRequest -Uri "https://api.sarvam.ai/text-to-speech" `
  -Method POST `
  -Headers @{"api-subscription-key" = "sk_..."; "Content-Type" = "application/json"} `
  -Body '{"inputs":["Namaste, main Telugu mein bol raha hoon."],"target_language_code":"te-IN","speaker":"anushka","model":"bulbul:v2"}'
```
Speakers for bulbul:v2: anushka (default), abhilash, manisha, vidya, arya, karun, hitesh. Must match model.

Good things to test:
- "What was I working on last week?"
- "Remind me what my preferences are for side projects"
- "Tell me about the Acme thing we discussed"
- Normal conversation
- At the end: just end the conversation naturally — the agent should automatically call `save_call_summary`.

You can also say: "Summarize the call and save it to Hermes."

Gemini uses context tools when needed and is instructed to always save a structured summary when a call ends.


## Step 5: Make World-Class Intelligent Outbound Calls

Start the agent worker:

```powershell
uv run python agent.py dev
```

### Simple call
```powershell
uv run python make_call.py --to +919876543210
```

### World-class agentic call (recommended)
Give the agent a clear brief so it becomes hyper-intelligent and goal-oriented:

```powershell
uv run python make_call.py --to +919876543210 `
  --person "Rahul at TechCorp" `
  --purpose "Qualify interest in our new low-latency AI voice platform" `
  --goal "Book a 20-minute technical demo this week" `
  --questions "What is their current calling solution?|Biggest pain points with latency or cost?|Who else is involved in the decision?"
```

The agent will:
- Pull highly targeted context from Hermes using the phone + purpose
- Start with a clear, professional purpose statement
- Ask the right questions
- Log important details live
- Save an extremely high-quality structured summary automatically

This is what makes it "as intelligent as the world's best". The richer the brief, the better it performs.

### Inbound

Call your Vobiz number. LiveKit will dispatch the agent into the room and Gemini + Hermes will answer.

## How Hermes is Used (Read + Write)

### Pre-call intelligence
- Loads your **core context**
- Loads **targeted context** using the phone number + purpose/person from your call brief

### During the call (anti-drift)
**Main protection against Gemini Live going out of context:**

- `get_current_call_context()` — **PRIMARY anti-drift tool**. 
  The system prompt forces Gemini to call this tool very frequently (every few turns, before referencing any fact, and when the topic changes). 
  It returns a fresh, condensed package with the call goal + live notes from this call.

- The model is explicitly told: "Treat the result of get_current_call_context() as your live source of truth."

- Additional tools: `get_relevant_context`, `recall_specific_memory`, `record_important_detail` (which keeps the package fresh).

This combination (strong instructions + easy-to-call fresh grounding package) is specifically designed to stop the realtime Gemini Live model from drifting.

### After the call
- Mandatory `save_call_summary` with rich structure
- The summary becomes permanent context for all future calls

This closed loop (context → intelligent conversation → perfect logging) is what allows the agent to perform at a world-class level without making critical mistakes.

See `agent.py` (instructions + tools) and `hermes_bridge.py`.


## Recommended Next-Level Improvements

Tell me which ones you want and I'll implement them:

- Pass live conversation turns into Hermes context queries for perfect continuity
- Stronger voicemail detection + specialized voicemail leaving logic
- Structured JSON summaries + auto-export to Notion/Sheets/CRM
- Post-call review command ("review and improve the last summary")
- Calendar booking tool integration (directly create events via Hermes)
- Campaign mode (multiple coordinated calls with shared state)
- Different expert personas per call type (sales closer, researcher, support agent, etc.)

## Important notes (Windows)

- Local console mode works great on Windows for testing.
- For production phone agents, most people run the worker on Linux (cheaper + more reliable audio/SIP).
- You can run Hermes + this agent on the same Windows machine for development.
- Use WSL2 or a cheap VPS when you want stable inbound numbers.

## Resources

- Vobiz LiveKit integration: https://docs.vobiz.ai/integrations/livekit
- LiveKit Gemini docs: https://docs.livekit.io/agents/integrations/google/
- Hermes Agent docs: https://hermes-agent.nousresearch.com/
- Gemini Live API: https://ai.google.dev/gemini-api/docs/live-api

---

Every call is now grounded in rich Hermes context, follows strict anti-hallucination rules, logs live, and produces excellent summaries.

This is the foundation of a truly world-class agentic calling system.

Let me know what to build next to push it even further.

