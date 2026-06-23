"""
Setup LiveKit SIP Outbound Trunk for Vobiz.

Run once:
  uv run python setup_trunk.py

It will create (or reuse) the outbound trunk using your Vobiz SIP credentials.
Prints the trunk ID - copy it into your .env as OUTBOUND_TRUNK_ID
"""

import asyncio
import os
from dotenv import load_dotenv
from livekit import api

load_dotenv()

LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

VOBIZ_DOMAIN = os.getenv("VOBIZ_SIP_DOMAIN")
VOBIZ_USER = os.getenv("VOBIZ_USERNAME")
VOBIZ_PASS = os.getenv("VOBIZ_PASSWORD")
PHONE = os.getenv("VOBIZ_PHONE_NUMBER")


async def main():
    if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
        print("LiveKit credentials missing")
        return

    if not all([VOBIZ_DOMAIN, VOBIZ_USER, VOBIZ_PASS]):
        print("Vobiz SIP credentials missing (VOBIZ_SIP_DOMAIN, USERNAME, PASSWORD)")
        return

    lk = api.LiveKitAPI(
        url=LIVEKIT_URL, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET
    )

    trunk_name = "Vobiz-Outbound"

    print("Creating / ensuring Vobiz outbound SIP trunk in LiveKit...")

    # Create the trunk (using new API to avoid deprecation)
    resp = await lk.sip.create_outbound_trunk(
        api.CreateOutboundTrunkRequest(
            trunk=api.SIPOutboundTrunkInfo(
                name=trunk_name,
                address=VOBIZ_DOMAIN,
                auth_username=VOBIZ_USER,
                auth_password=VOBIZ_PASS,
                numbers=[PHONE] if PHONE else [],
            )
        )
    )

    trunk_id = resp.sip_trunk_id
    print("\n✅ Success!")
    print(f"Trunk ID: {trunk_id}")
    print("Copy this value into your .env file as:")
    print(f"OUTBOUND_TRUNK_ID={trunk_id}")

    print("\nNext steps:")
    print("1. Add the trunk ID to .env (already done for you)")
    print("2. Add your GOOGLE_API_KEY to .env")
    print("3. Start Hermes with API server enabled, then:")
    print("   .\\.venv\\Scripts\\Activate.ps1")
    print("   python agent.py dev")
    print("4. Use make_call.py to place test outbound calls")


if __name__ == "__main__":
    asyncio.run(main())
