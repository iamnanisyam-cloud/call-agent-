"""
Axon Agent - Outbound Call Tool (Gemini Live + 6-layer memory)

Axon is part of the Axon Agent system (owner: Dara Nanisyamkumar).
Launches an integrated agentic call.

Axon can:
- Observe using all memory layers
- Think, Plan, Act, Evaluate, Learn and Store via tools
- Handle calls intelligently with persistent memory

Usage examples:
  python make_call.py --to +918074835456 --person "Dara" ...

Axon will introduce itself as part of the Axon Agent.
"""

import argparse
import asyncio
import json
import os
import time
from dotenv import load_dotenv
from livekit import api

load_dotenv()

LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
TRUNK_ID = os.getenv("OUTBOUND_TRUNK_ID", "")
AGENT_NAME = os.getenv("AGENT_NAME", "hermes-voice-assistant")
PERSONA_NAME = os.getenv("PERSONA_NAME", "Axon")


def build_metadata(args) -> str:
    """Build rich, structured metadata that makes each call highly intelligent."""
    meta = {
        "phone_number": args.to,
        "purpose": args.purpose or "",
        "target_person": args.person or "",
        "desired_outcome": args.goal or "",
        "key_questions": [q.strip() for q in (args.questions or "").split("|") if q.strip()],
        "tone": args.tone or "professional, confident, and friendly",
        "additional_context": args.context or "",
        "language": args.language,
        "guardrails": args.guardrails or "",          # unique per call - Hermes handled
        "unique_context": args.unique_context or "",  # unique per call - Hermes handled
        # For agentic planner: hints for initial task plan
        "initial_plan_hint": args.plan or "",
        "tasks": [t.strip() for t in (args.tasks or "").split("|") if t.strip()],
    }
    # Remove empty fields
    meta = {k: v for k, v in meta.items() if v}
    return json.dumps(meta)


async def make_outbound_call(args):
    if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
        print("❌ Missing LiveKit credentials in .env")
        return

    if not TRUNK_ID:
        print("❌ OUTBOUND_TRUNK_ID not set. Run setup_trunk.py first.")
        return

    # Simple lock to prevent accidental multiple calls to same number
    lock_file = f".call_lock_{args.to.replace('+', '')}"
    if os.path.exists(lock_file):
        mtime = os.path.getmtime(lock_file)
        if time.time() - mtime < 300:  # 5 minutes
            print(f"❌ A recent call to {args.to} was already placed (lock file exists).")
            print("   Delete the lock file if you are sure no call is active, or wait a few minutes.")
            return
    with open(lock_file, "w") as f:
        f.write(str(time.time()))

    try:
        lk_api = api.LiveKitAPI(
            url=LIVEKIT_URL,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        )

        room_name = f"call-{args.to.replace('+', '')}-{int(asyncio.get_event_loop().time())}"

        metadata = build_metadata(args)

        print(f"\n🚀 Launching call with {PERSONA_NAME} (Hermes Agent)")
        print(f"   To: {args.to}")
        if args.person: print(f"   Person: {args.person}")
        if args.purpose: print(f"   Purpose: {args.purpose}")
        if args.goal: print(f"   Desired outcome: {args.goal}")
        print(f"   Room: {room_name}\n")

        # Dispatch with rich metadata so Gemini becomes hyper-targeted
        await lk_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=room_name,
                metadata=metadata,
            )
        )

        # Dial via Vobiz SIP
        participant = await lk_api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=TRUNK_ID,
                sip_call_to=args.to,
                room_name=room_name,
                participant_identity="callee",
                participant_name=args.person or "Contact",
            )
        )

        print("✅ Call initiated through Vobiz + LiveKit.")
        print(f"   {PERSONA_NAME} (private name of Hermes Agent) is active.")
        print("   Focus on the call topic. Do not volunteer identity unless asked.")
    finally:
        if os.path.exists(lock_file):
            os.remove(lock_file)


def main():
    parser = argparse.ArgumentParser(description="World-class agentic phone call launcher")
    parser.add_argument("--to", required=True, help="Phone number in E.164 format (+91...)")
    parser.add_argument("--person", help="Name of the person/company you're calling")
    parser.add_argument("--purpose", help="Clear purpose of the call")
    parser.add_argument("--goal", "--desired-outcome", dest="goal", help="What success looks like for this call")
    parser.add_argument("--questions", help='Key questions to ask, separated by | (pipe). Example: "Current stack?|Pain points?|Budget range?"')
    parser.add_argument("--tone", default="professional and friendly", help="Desired tone")
    parser.add_argument("--context", help="Any extra context or instructions for this specific call")
    parser.add_argument("--language", default="te", choices=["en", "te"], help="Language of the other party. The agent will automatically pick female voice: Telugu female (priya) or Indian English female (ishita) using Sarvam Bulbul v3 style.")
    parser.add_argument("--guardrails", "--limitations", dest="guardrails", help="UNIQUE guardrails and limitations for THIS call only (Hermes-handled).")
    parser.add_argument("--unique-context", dest="unique_context", help="Unique additional context specific to this call (Hermes-handled).")
    parser.add_argument("--plan", "--initial-plan", dest="plan", help="Hint for initial task plan (e.g. '1. Greet 2. Recall last sleep note 3. Remind 4. Confirm 5. Record+reflect')")
    parser.add_argument("--tasks", help="Pipe-separated high level tasks the agent should plan around, e.g. 'remind sleep|book follow up|ask preference'")

    args = parser.parse_args()
    asyncio.run(make_outbound_call(args))


if __name__ == "__main__":
    main()
