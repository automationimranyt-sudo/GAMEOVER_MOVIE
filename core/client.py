"""
GameOver Movie Hub — Central Client Reference
Provides global access to the active running bot & assistant instances,
and a bulletproof send_styled helper.
"""
import sys
from pyrogram import Client, enums
from pyrogram.types import InlineKeyboardMarkup
import pyrogram.errors

# Global active client references
bot: Client = None
assistant: Client = None


def get_bot() -> Client:
    """Always resolves to the active running bot instance."""
    global bot
    if bot is not None and getattr(bot, "is_connected", False):
        return bot
    # Fallback to sys.modules
    main_mod = sys.modules.get("bot") or sys.modules.get("__main__")
    if main_mod and hasattr(main_mod, "bot"):
        candidate = getattr(main_mod, "bot")
        if candidate is not None and (getattr(candidate, "is_connected", False) or bot is None):
            bot = candidate
    return bot


async def send_styled(
    chat_id: int,
    text: str,
    markup: InlineKeyboardMarkup = None,
    parse_mode: str = "HTML",
    message_id: int = None
) -> dict:
    """
    Send or edit a message using the active running Pyrogram client.
    Guarantees that the running, connected client instance is used.
    """
    active_bot = get_bot()
    if not active_bot:
        print(f"[send_styled ERROR] Active bot client instance not found!", flush=True)
        return {}

    p_mode = enums.ParseMode.HTML if str(parse_mode).upper() == "HTML" else None
    try:
        if message_id:
            msg = await active_bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=markup,
                parse_mode=p_mode,
                disable_web_page_preview=True
            )
            return {"ok": True, "result": {"message_id": msg.id if msg else message_id}}
        else:
            msg = await active_bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=markup,
                parse_mode=p_mode,
                disable_web_page_preview=True
            )
            return {"ok": True, "result": {"message_id": msg.id}}
    except pyrogram.errors.MessageNotModified:
        return {"ok": True, "result": {"message_id": message_id}}
    except Exception as e:
        print(f"[send_styled] Pyrogram send error to {chat_id}: {e}", flush=True)
        return {}
