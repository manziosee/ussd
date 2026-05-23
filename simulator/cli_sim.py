"""
SmartAssist USSD CLI Simulator
================================
Simulates a real USSD session in your terminal.

Usage:
    python simulator/cli_sim.py
    python simulator/cli_sim.py --phone +250788000001
    python simulator/cli_sim.py --url http://localhost:8000

Requirements:
    pip install httpx   (already in requirements.txt)
"""
import argparse
import sys
import uuid

import httpx


def parse_args():
    p = argparse.ArgumentParser(description="SmartAssist USSD terminal simulator")
    p.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    p.add_argument("--phone", default="+250788123456", help="Phone number to simulate")
    return p.parse_args()


def print_banner():
    print("\n" + "═" * 50)
    print("   SmartAssist USSD Simulator")
    print("═" * 50)
    print("  Phone :", args.phone)
    print("  Server:", args.url)
    print("  Type   input then press Enter.")
    print("  Ctrl+C to quit.\n")


def send_ussd(session_id: str, text: str) -> str:
    """POST to /simulate and return the CON/END response string."""
    resp = httpx.post(
        f"{args.url}/simulate",
        json={
            "session_id": session_id,
            "phone_number": args.phone,
            "text": text,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.text


def run_session():
    session_id = f"sim-{uuid.uuid4().hex[:12]}"
    accumulated = ""  # text grows with each input, joined by *

    print_banner()

    while True:
        # Send current accumulated text
        try:
            response = send_ussd(session_id, accumulated)
        except httpx.ConnectError:
            print(f"\n✗  Cannot connect to {args.url}")
            print("   Make sure the server is running:  uvicorn app.main:app --reload")
            sys.exit(1)
        except httpx.HTTPStatusError as e:
            print(f"\n✗  HTTP {e.response.status_code}: {e.response.text}")
            sys.exit(1)

        # Display the response in a phone-like frame
        is_end = response.startswith("END ")
        body = response[4:]  # strip "CON " or "END "

        print("\n┌" + "─" * 38 + "┐")
        for line in body.splitlines():
            print(f"│  {line:<36}│")
        print("└" + "─" * 38 + "┘")

        if is_end:
            print("\n  [Session ended]\n")
            again = input("  Start new session? (y/n): ").strip().lower()
            if again == "y":
                run_session()
            return

        # Get user input
        try:
            user_input = input("\n  Your input: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  [Interrupted]\n")
            return

        # Accumulate: "1", then "1*2", then "1*2*question"
        accumulated = f"{accumulated}*{user_input}" if accumulated else user_input


if __name__ == "__main__":
    args = parse_args()
    run_session()
