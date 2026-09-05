"""
GameOver Movie Hub — Pyrogram String Session Generator
Run this script to generate a new STRING3 for your Telegram assistant account.
"""

import sys
import os
import asyncio

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

load_dotenv()


def update_env_file(string_session: str):
    """Updates or inserts STRING3 in the .env file."""
    env_path = ".env"
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"STRING3={string_session}\n")
        return True

    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith("STRING3="):
            new_lines.append(f"STRING3={string_session}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"\nSTRING3={string_session}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    return True


async def main():
    print("=" * 60)
    print("   GᴀᴍᴇOᴠᴇʀ Mᴏᴠɪᴇ Hᴜʙ — Sᴛʀɪɴɢ Sᴇssɪᴏɴ Gᴇɴᴇʀᴀᴛᴏʀ")
    print("=" * 60)
    print()

    # Read API credentials
    api_id_env = os.getenv("API_ID", "").strip()
    api_hash_env = os.getenv("API_HASH", "").strip()

    if api_id_env and api_hash_env:
        try:
            api_id = int(api_id_env)
            api_hash = api_hash_env
            print(f"Loaded API_ID from .env: {api_id}")
        except ValueError:
            api_id = 0
            api_hash = ""
    else:
        api_id = 0
        api_hash = ""

    if not api_id:
        val = input("Enter your API_ID (from my.telegram.org): ").strip()
        api_id = int(val)
    if not api_hash:
        api_hash = input("Enter your API_HASH (from my.telegram.org): ").strip()

    print()
    print("Starting session generator...")
    print("Please enter your Phone Number with Country Code (e.g. +923001234567)")
    print("Telegram will send you a verification code.")
    print("-" * 60)

    from pyrogram import Client

    session_name = "generate_session_temp"
    async with Client(
        session_name,
        api_id=api_id,
        api_hash=api_hash,
        in_memory=True
    ) as app:
        string_session = await app.export_session_string()

    print()
    print("=" * 60)
    print("STRING3 Session Generated Successfully!")
    print("=" * 60)
    print()
    print("Aapki New Pyrogram String Session:")
    print("-" * 60)
    print(string_session)
    print("-" * 60)
    print()

    # Automatically offer to update .env
    save_choice = input("Kya aap is STRING3 ko automatically .env file me save karna chahte hain? (Y/n): ").strip().lower()
    if save_choice in ("", "y", "yes"):
        update_env_file(string_session)
        print("Updated .env file successfully with new STRING3!")
    else:
        print("Save skipped. Please copy the session string above and paste it into .env under STRING3.")

    print()
    print("Done! You can now start the bot using start.bat or 'python bot.py'.")
    print("=" * 60)

    # Clean up any leftover temporary files
    for fname in os.listdir("."):
        if fname.startswith("generate_session_temp"):
            try:
                os.remove(fname)
            except Exception:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSession generation cancelled by user.")
    except Exception as err:
        print(f"\nError: {err}")
