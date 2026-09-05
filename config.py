import os
import re
from dotenv import load_dotenv

load_dotenv()

def _get_clean_env(*keys, default=""):
    """Fetch first matching environment variable, stripping quotes and whitespace."""
    for k in keys:
        v = os.getenv(k)
        if v is not None:
            val = str(v).strip()
            # Remove surrounding double or single quotes
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1].strip()
            if val:
                return val
    return default

def _get_clean_int(*keys, default=0):
    val_str = _get_clean_env(*keys, default=str(default))
    digits = re.sub(r"[^\d]", "", val_str)
    try:
        return int(digits) if digits else default
    except Exception:
        return default

class Config:
    API_ID: int = _get_clean_int("API_ID", "api_id", "TELEGRAM_API_ID", default=0)
    API_HASH: str = _get_clean_env("API_HASH", "api_hash", "TELEGRAM_API_HASH", default="")
    BOT_TOKEN: str = _get_clean_env("TOKEN", "BOT_TOKEN", "bot_token", "TG_BOT_TOKEN", default="")
    STRING3: str = _get_clean_env("STRING3", "STRING_SESSION", "SESSION_STRING", "string3", "string_session", default="")
    OWNER_ID: int = _get_clean_int("OWNER_ID", "owner_id", default=0)

    DOWNLOADS_DIR: str = _get_clean_env("DOWNLOADS_DIR", "downloads_dir", default="downloads")
    PROJECT_ROOT: str = os.path.dirname(os.path.abspath(__file__))

    BOT_NAME: str = "GᴀᴍᴇOᴠᴇʀ Mᴏᴠɪᴇ Hᴜʙ"
    BOT_USERNAME: str = ""

    @staticmethod
    def print_diagnostics():
        print("=" * 56)
        print("   GameOver Movie Hub — Credentials Check")
        print("=" * 56)
        api_id_str = str(Config.API_ID) if Config.API_ID else "NOT SET / 0"
        api_hash_masked = (Config.API_HASH[:4] + "..." + Config.API_HASH[-4:] + f" ({len(Config.API_HASH)} chars)") if Config.API_HASH else "NOT SET / EMPTY"
        bot_token_masked = (Config.BOT_TOKEN[:10] + "..." + Config.BOT_TOKEN[-4:] + f" ({len(Config.BOT_TOKEN)} chars)") if Config.BOT_TOKEN else "NOT SET / EMPTY"
        string3_masked = (Config.STRING3[:10] + "..." + Config.STRING3[-6:] + f" ({len(Config.STRING3)} chars)") if Config.STRING3 else "NOT SET / EMPTY"

        print(f"   API_ID:         {api_id_str}")
        print(f"   API_HASH:       {api_hash_masked}")
        print(f"   BOT_TOKEN:      {bot_token_masked}")
        print(f"   STRING_SESSION: {string3_masked}")
        print(f"   OWNER_ID:       {Config.OWNER_ID}")
        print("=" * 56)

    @staticmethod
    def validate():
        missing = []
        if not Config.API_ID:
            missing.append("API_ID (Telegram App ID)")
        if not Config.API_HASH:
            missing.append("API_HASH (Telegram App Hash)")
        if not Config.BOT_TOKEN:
            missing.append("TOKEN or BOT_TOKEN (Telegram Bot Token)")
        if not Config.STRING3:
            missing.append("STRING3 or STRING_SESSION (Assistant Session String)")

        if missing:
            err = (
                "\n" + "=" * 56 + "\n"
                "[FATAL CONFIG ERROR] Missing required credentials:\n" +
                "\n".join(f"  - {m}" for m in missing) + "\n\n"
                "If running on Hugging Face Spaces:\n"
                "1. Open your Space -> Settings -> Variables and secrets.\n"
                "2. Click 'New secret' and add each missing variable.\n"
                "3. Make sure names are exact uppercase (API_ID, API_HASH, TOKEN, STRING3).\n"
                "4. Do NOT wrap values in quotes or leave spaces.\n" +
                "=" * 56 + "\n"
            )
            raise ValueError(err)

