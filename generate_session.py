#!/usr/bin/env python3
"""
NeX 4GB Rename Bot - Standalone String Session Generator
Generates a Pyrogram/Pyrotgfork String Session for Telegram Premium 4GB Uploads.

Powered by @Nex_bots
"""

import os
import re
import sys
import asyncio

try:
    from pyrogram import Client
except ImportError:
    print("❌ Pyrogram / Pyrotgfork is not installed!")
    print("👉 Please run: pip install pyrotgfork")
    sys.exit(1)

# Default credentials from config or environment if available
try:
    from config import Config
    DEFAULT_API_ID = getattr(Config, "API_ID", 0) or int(os.environ.get("API_ID", "0") or 0)
    DEFAULT_API_HASH = getattr(Config, "API_HASH", "") or os.environ.get("API_HASH", "")
except Exception:
    DEFAULT_API_ID = int(os.environ.get("API_ID", "0") or 0)
    DEFAULT_API_HASH = os.environ.get("API_HASH", "")


def save_session_to_env(session_str: str) -> bool:
    """
    Saves or updates STRING_SESSION in the root .env file.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(base_dir, ".env")
    example_path = os.path.join(base_dir, ".env.example")

    try:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()
        elif os.path.exists(example_path):
            with open(example_path, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            content = ""

        if re.search(r"^STRING_SESSION=.*$", content, flags=re.MULTILINE):
            new_content = re.sub(
                r"^STRING_SESSION=.*$",
                f"STRING_SESSION={session_str}",
                content,
                flags=re.MULTILINE
            )
        else:
            new_content = content.rstrip() + f"\nSTRING_SESSION={session_str}\n"

        with open(env_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    except Exception as e:
        print(f"⚠️ Error updating .env file: {e}")
        return False


async def generate_session():
    print("=" * 60)
    print("    ⚡ NeX 4GB Rename Bot - Premium Session Generator ⚡")
    print("                   Powered by @Nex_bots")
    print("=" * 60)
    print()
    print("ℹ️  This script generates a Pyrogram String Session.")
    print("⭐ Use an account with Telegram Premium for 4GB uploads!")
    print()

    # Get API_ID
    while True:
        api_id_raw = input(f"Enter API_ID [Press Enter for default: {DEFAULT_API_ID}]: ").strip()
        if not api_id_raw:
            api_id = int(DEFAULT_API_ID)
            break
        try:
            api_id = int(api_id_raw)
            break
        except ValueError:
            print("❌ Invalid API_ID! Must be an integer.")

    # Get API_HASH
    api_hash_raw = input(f"Enter API_HASH [Press Enter for default: {DEFAULT_API_HASH}]: ").strip()
    api_hash = api_hash_raw if api_hash_raw else str(DEFAULT_API_HASH)

    print()
    print("🚀 Initializing Pyrotgfork in-memory client...")
    print("⚠️  REMINDER: When prompted, enter ONLY your Telegram Phone Number (e.g. +91XXXXXXXXXX)!")
    print("⛔  DO NOT enter a Bot Token! This requires a real Telegram account for 4GB Premium uploads.")
    print("📲 You will receive an official login OTP inside your Telegram app.")
    print("-" * 60)

    app = Client(
        name="nex_session_gen",
        api_id=api_id,
        api_hash=api_hash,
        in_memory=True
    )

    try:
        await app.start()
    except Exception as e:
        print(f"❌ Failed to authenticate: {e}")
        return

    try:
        me = await app.get_me()
        session_str = await app.export_session_string()
        is_premium = getattr(me, "is_premium", False)

        print("-" * 60)
        print("✅ Logged in successfully!")
        print(f"👤 Account Name: {me.first_name} {me.last_name or ''}".strip())
        print(f"🏷️ Username    : @{me.username or 'No Username'}")
        print(f"🆔 User ID     : {me.id}")
        if is_premium:
            print("⭐ Telegram Premium: YES ✅ (Full 4GB upload capability active)")
        else:
            print("ℹ️ Telegram Premium: NO ❌ (Standard 2GB limit unless Premium is active)")
        print("-" * 60)

        # Send backup copy to Saved Messages
        saved_msg = (
            "⚡ <b><u>NeX 4GB Rename Bot - Pyrogram String Session</u></b> ⚡\n\n"
            f"👤 <b>Account Name:</b> {me.first_name}\n"
            f"🆔 <b>User ID:</b> <code>{me.id}</code>\n"
            f"⭐ <b>Telegram Premium:</b> {'YES ✅' if is_premium else 'NO ❌'}\n\n"
            "🔑 <b>Your STRING_SESSION (Tap to Copy):</b>\n"
            f"<code>{session_str}</code>\n\n"
            "⚠️ <b>Security Notice:</b> Never share this string session with anyone!\n"
            "📢 <b>Powered by:</b> @Nex_bots"
        )
        try:
            await app.send_message("me", saved_msg)
            print("📬 A backup copy has been sent to your Telegram 'Saved Messages'!")
        except Exception as e:
            print(f"⚠️ Could not send backup to Saved Messages: {e}")

        print()
        print("🔑 YOUR GENERATED STRING SESSION:")
        print("=" * 60)
        print(session_str)
        print("=" * 60)
        print()

        # Prompt to auto-save to .env
        save_choice = input("Would you like to automatically save this STRING_SESSION into your .env file? (y/n): ").strip().lower()
        if save_choice in ["y", "yes"]:
            if save_session_to_env(session_str):
                print("✅ STRING_SESSION was automatically saved into your .env file!")
                print("🚀 You can now start the bot using: python bot.py")
            else:
                print("⚠️ Could not write to .env. Please copy and paste the string manually.")
        else:
            print("ℹ️ Skipped saving to .env. Remember to paste the string into your .env or server environment variables!")

    finally:
        try:
            await app.stop()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(generate_session())
    except KeyboardInterrupt:
        print("\n\n❌ Process cancelled by user. Exiting...")
        sys.exit(0)

