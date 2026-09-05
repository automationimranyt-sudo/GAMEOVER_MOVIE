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


def _markup_to_bot_api_json(markup: InlineKeyboardMarkup) -> list:
    """Convert Pyrogram InlineKeyboardMarkup -> Bot API JSON with style support (Telegram Bot API 9.4+)."""
    rows = []
    for row in markup.inline_keyboard:
        btn_row = []
        for btn in row:
            obj = {"text": btn.text}
            if btn.callback_data is not None:
                obj["callback_data"] = btn.callback_data
            elif btn.url is not None:
                obj["url"] = btn.url
            if getattr(btn, "style", None):
                obj["style"] = btn.style
            btn_row.append(obj)
        rows.append(btn_row)
    return rows


async def send_styled(
    chat_id: int,
    text: str,
    markup: InlineKeyboardMarkup = None,
    parse_mode: str = "HTML",
    message_id: int = None
) -> dict:
    """
    Send or edit a message.
    1. First attempts Telegram Bot API 9.4 HTTP to preserve button colors (primary/success/danger).
    2. Gracefully falls back to Pyrogram MTProto for 100% reliable local/cloud delivery.
    """
    from config import Config
    import aiohttp
    import json

    token = Config.BOT_TOKEN
    # Attempt HTTP Bot API for native colored buttons if markup is present
    if token and markup and any(getattr(btn, "style", None) for row in markup.inline_keyboard for btn in row):
        try:
            endpoint = f"https://api.telegram.org/bot{token}/"
            method = "editMessageText" if message_id else "sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
                "reply_markup": json.dumps({"inline_keyboard": _markup_to_bot_api_json(markup)})
            }
            if message_id:
                payload["message_id"] = message_id

            timeout = aiohttp.ClientTimeout(total=2.5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint + method, json=payload) as resp:
                    if resp.status == 200:
                        res = await resp.json()
                        if res.get("ok"):
                            return res
        except Exception:
            # Fall back directly to native MTProto
            pass

    # Native Pyrogram MTProto fallback
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

