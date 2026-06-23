"""
Quick test for Hermes context retrieval (new architecture).

Gemini is the main LLM.
Hermes is queried only for context / memories.

Usage:
  1. Make sure `hermes gateway` is running + API_SERVER_ENABLED=true
  2. Set HERMES_API_URL and HERMES_API_KEY in .env
  3. uv run python test_hermes.py
"""

import asyncio
from hermes_bridge import (
    get_core_user_context,
    get_context_from_hermes,
    call_hermes,
    save_call_summary,
    get_targeted_context_for_call,
    log_mid_call_note,
    get_condensed_context_package,
)

async def main():
    print("=== Test 1: Get core user context (used at start of every call) ===")
    core = await get_core_user_context()
    print(core[:600] if core else "No core context")
    print("\n" + "="*50 + "\n")

    print("=== Test 2: Retrieve context for a specific topic ===")
    topic = "my current or recent projects"
    ctx = await get_context_from_hermes(topic)
    print(f"Topic: {topic}\n{ctx}\n")

    print("=== Test 3: Low-level call (for debugging) ===")
    raw = await call_hermes([
        {"role": "user", "content": "What are the most important things you know about me?"}
    ])
    print(raw[:500])

    print("\n=== Test 4: Targeted context for a specific call ===")
    ctx = await get_targeted_context_for_call(
        phone_number="+919876543210",
        purpose="Sales introduction for AI voice platform",
        target_person="Rahul at TechCorp"
    )
    print(ctx[:400] if ctx else "No targeted context")

    print("\n=== Test 5: Log a mid-call note (simulates live call) ===")
    note_result = await log_mid_call_note(
        "They said they are currently using a very expensive legacy system and hate the latency.",
        category="objection"
    )
    print("Mid-call log:", note_result)

    print("\n=== Test 6: Save a high-quality sample summary ===")
    result = await save_call_summary(
        summary="Spoke with Rahul. They are frustrated with their current high-latency legacy calling system. Showed strong interest when I described our low-latency Gemini-powered solution. Asked detailed questions about pricing and integration time.",
        outcome="interested",
        next_steps="Email the one-pager + pricing to rahul@techcorp.com today. Book a 20-min technical demo for Thursday or Friday this week.",
        key_facts="Current pain: expensive legacy system + high latency. Team size mentioned: ~40. Contact: Rahul Sharma.",
        phone_number="+919876543210",
        sentiment="positive",
        call_type="sales_qualification"
    )
    print("Summary save:", result[:250])

    print("\n=== Test 7: Generate live grounding package (anti-drift tool) ===")
    package = await get_condensed_context_package(
        phone_number="+919876543210",
        call_brief={
            "purpose": "Follow up and book pilot",
            "target_person": "Rahul at TechCorp",
            "desired_outcome": "Secure pilot commitment"
        },
        recent_notes=[
            "Rahul mentioned frustration with legacy system latency",
            "Team of ~40 people",
            "Interested in pricing for enterprise"
        ]
    )
    print(package[:600])

if __name__ == "__main__":
    asyncio.run(main())
