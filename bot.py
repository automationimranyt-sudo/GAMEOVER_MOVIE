"""
GameOver Movie Hub — Main Bot Entry Point
Dedicated movie/VOD bot — streams movies inside group voice chats.
Uses same API_ID, API_HASH, OWNER_ID as Music Bot.
Different: BOT_TOKEN (Gameovermovie_bot) + STRING3 (new assistant session).
"""

import sys
import io
import asyncio
import os
import inspect
import sqlite3

# Global SQLite patch to prevent "database is locked" errors in Pyrogram session & local DBs
_orig_sqlite_connect = sqlite3.connect
def _patched_sqlite_connect(*args, **kwargs):
    kwargs.setdefault("timeout", 30.0)
    conn = _orig_sqlite_connect(*args, **kwargs)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
    except Exception:
        pass
    return conn
sqlite3.connect = _patched_sqlite_connect

# Dynamic module wrappers to prevent pytgcalls import errors on standard/fork pyrogram versions
import pyrogram.errors
import pyrogram.raw.types

class RawTypesModuleWrapper:
    def __init__(self, original_module):
        self._original_module = original_module
    def __getattr__(self, name):
        try:
            return getattr(self._original_module, name)
        except AttributeError:
            class DummyClass:
                pass
            DummyClass.__name__ = name
            setattr(self._original_module, name, DummyClass)
            return DummyClass

if not isinstance(pyrogram.raw.types, RawTypesModuleWrapper):
    sys.modules["pyrogram.raw.types"] = RawTypesModuleWrapper(pyrogram.raw.types)

class ErrorsModuleWrapper:
    def __init__(self, original_module):
        self._original_module = original_module
    def __getattr__(self, name):
        try:
            return getattr(self._original_module, name)
        except AttributeError:
            # Case-insensitive mismatch fallback (e.g., GroupcallInvalid -> GroupCallInvalid)
            for key in dir(self._original_module):
                if key.lower() == name.lower():
                    val = getattr(self._original_module, key)
                    setattr(self._original_module, name, val)
                    return val
            class DummyError(Exception):
                pass
            DummyError.__name__ = name
            setattr(self._original_module, name, DummyError)
            return DummyError

if not isinstance(pyrogram.errors, ErrorsModuleWrapper):
    sys.modules["pyrogram.errors"] = ErrorsModuleWrapper(pyrogram.errors)

# Patch pyrogram JoinGroupCall and JoinGroupCallPresentation to drop unsupported arguments (like public_key)
import pyrogram.raw.functions.phone
for call_class_name in ("JoinGroupCall", "JoinGroupCallPresentation"):
    call_cls = getattr(pyrogram.raw.functions.phone, call_class_name, None)
    if call_cls and hasattr(call_cls, "__init__") and not getattr(call_cls, "__patched__", False):
        orig_init = call_cls.__init__
        def make_patched_init(old_init):
            def patched_init(self, *args, **kwargs):
                sig = inspect.signature(old_init)
                clean_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
                old_init(self, *args, **clean_kwargs)
            return patched_init
        call_cls.__init__ = make_patched_init(orig_init)
        call_cls.__patched__ = True

# Patch pyrogram.utils.get_peer_type to prevent ValueError crash in handle_updates on un-cached IDs
import pyrogram.utils
if not getattr(pyrogram.utils, "__patched__", False):
    _orig_get_peer_type = pyrogram.utils.get_peer_type
    def _patched_get_peer_type(peer_id: int) -> str:
        try:
            return _orig_get_peer_type(peer_id)
        except ValueError:
            # Safe fallback based on typical ID ranges:
            # -100xxxxxx is channel/supergroup, -xxxxxx is group chat, positive is user
            pid_str = str(peer_id)
            if pid_str.startswith("-100"):
                return "channel"
            elif pid_str.startswith("-"):
                return "chat"
            else:
                return "user"
    pyrogram.utils.get_peer_type = _patched_get_peer_type
    pyrogram.utils.__patched__ = True

from pyrogram import Client, idle, enums, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from config import Config
from core.player import stream_manager

# Force unbuffered UTF-8 stdout & stderr so logs stream live into Hugging Face / Docker terminals
os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True, write_through=True)
    except Exception:
        sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True, write_through=True)
    except Exception:
        sys.stderr.reconfigure(encoding="utf-8")

# Verify credentials before loading clients
Config.print_diagnostics()
Config.validate()

# Initialize bot client
bot = Client(
    name="GameOverMovieBot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
)

# Initialize assistant client
assistant = Client(
    name="GameOverMovieAssistant",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    session_string=Config.STRING3,
    in_memory=True,
)

# ─── Native Colored Button Support (Telegram Bot API 9.4) ────────────────────
# pyrogram/pyrofork doesn't serialize the 'style' field through MTProto.
# We patch InlineKeyboardButton to store style, then use the Bot HTTP API
# directly (via aiohttp) when sending/editing messages with styled keyboards.
import pyrogram.types

_orig_btn_init = pyrogram.types.InlineKeyboardButton.__init__
def _patched_btn_init(self, *args, **kwargs):
    style = kwargs.pop("style", None)
    _orig_btn_init(self, *args, **kwargs)
    self.style = style  # always store, even if None
pyrogram.types.InlineKeyboardButton.__init__ = _patched_btn_init

def _markup_to_bot_api_json(markup: InlineKeyboardMarkup) -> list:
    """Convert Pyrogram InlineKeyboardMarkup → Bot API JSON with style support."""
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

async def send_styled(chat_id: int, text: str, markup: InlineKeyboardMarkup = None, parse_mode: str = "HTML", message_id: int = None) -> dict:
    """
    Send or edit a message using Pyrogram client over native MTProto.
    Ultra-fast, native, and 100% reliable without external HTTP dependency.
    """
    p_mode = enums.ParseMode.HTML if str(parse_mode).upper() == "HTML" else None
    try:
        if message_id:
            msg = await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=markup,
                parse_mode=p_mode,
                disable_web_page_preview=True
            )
            return {"ok": True, "result": {"message_id": msg.id if msg else message_id}}
        else:
            msg = await bot.send_message(
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


# ── Global Real-Time Telegram Event Logger for Hugging Face Terminal ─────────
@bot.on_message(group=-1)
async def _live_message_logger(client: Client, message: Message):
    user = message.from_user
    u_info = f"@{user.username}" if user and user.username else (user.first_name if user else "Unknown")
    chat_type = "Private" if message.chat.type == enums.ChatType.PRIVATE else (message.chat.title or "Group")
    text_snippet = message.text or message.caption or (f"[{message.media.value}]" if message.media else "[Event]")
    print(f"[Telegram Log] [{chat_type}] {u_info} ({message.chat.id}): {text_snippet[:100]}", flush=True)

@bot.on_callback_query(group=-1)
async def _live_callback_logger(client: Client, query):
    user = query.from_user
    u_info = f"@{user.username}" if user and user.username else (user.first_name if user else "Unknown")
    print(f"[Telegram Button] {u_info}: Clicked button '{query.data}'", flush=True)


# ── /start handler for Private Chats ───────────────────────────────────────
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user = message.from_user
    user_id = user.id if user else 0
    username = user.username if user and user.username else ""
    first_name = user.first_name if user and user.first_name else ""
    
    # Track user and alert owner
    try:
        from core.db import add_started_user
        is_new = add_started_user(user_id, username, first_name)
        
        owner_id = Config.OWNER_ID or 6805412676
        tag = "<b>NEW USER STARTED BOT!</b>" if is_new else "<b>USER STARTED BOT!</b>"
        user_link = f"<a href=\"tg://user?id={user_id}\">{first_name}</a>"
        alert_text = (
            f"<b>GᴀᴍᴇOᴠᴇʀ Mᴏᴠɪᴇ Hᴜʙ</b>\n\n"
            f"{tag}\n\n"
            f"‣ <b>Nᴀᴍᴇ :</b> {user_link}\n"
            f"‣ <b>Usᴇʀ ID :</b> <code>{user_id}</code>\n"
            f"‣ <b>Usᴇʀɴᴀᴍᴇ :</b> @{username or 'N/A'}"
        )
        try:
            await send_styled(chat_id=owner_id, text=alert_text)
        except Exception as alert_err:
            print(f"[Start Alert] Failed to alert owner: {alert_err}")
    except Exception as db_err:
        print(f"[Start Alert] DB error: {db_err}")

    from core.db import get_setting
    start_video_file_id = get_setting("start_video_file_id")

    owner_id = Config.OWNER_ID or 6805412676
    owner_link = f"tg://user?id={owner_id}"
    try:
        owner_user = await client.get_users(owner_id)
        if owner_user and owner_user.username:
            owner_link = f"https://t.me/{owner_user.username}"
    except Exception:
        pass

    caption_text = (
        "<b>GᴀᴍᴇOᴠᴇʀ Mᴏᴠɪᴇ Hᴜʙ</b>\n\n"
        "I Aᴍ Tʜᴇ Fᴀsᴛ Aɴᴅ PᴏᴡᴇʀFᴜʟ Mᴏᴠɪᴇ Pʟᴀʏᴇʀ Bᴏᴛ Wɪᴛʜ Sᴏᴍᴇ Aᴡᴇsᴏᴍᴇ Fᴇᴀᴛᴜʀᴇs.\n\n"
        "Cʟɪᴄᴋ Oɴ Tʜᴇ Hᴇʟᴘ Bᴜᴛᴛᴏɴ Tᴏ Gᴇᴛ Iɴғᴏʀᴍᴀᴛɪᴏɴ Aʙᴏᴜᴛ Mʏ Mᴏᴅᴜʟᴇs Aɴᴅ Cᴏᴍᴍᴀɴᴅs."
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Aᴅᴅ Mᴇ Iɴ Yᴏᴜʀ Gʀᴏᴜᴘ", url=f"https://t.me/{Config.BOT_USERNAME}?startgroup=true", style="primary")],
        [InlineKeyboardButton("Hᴇʟᴘ Aɴᴅ Cᴏᴍᴍᴀɴᴅs", callback_data="help_all", style="primary")],
        [InlineKeyboardButton("Oᴡɴᴇʀ", url=owner_link, style="primary")]
    ])

    if start_video_file_id:
        try:
            await client.send_video(
                chat_id=message.chat.id,
                video=start_video_file_id,
                caption=caption_text,
                parse_mode=enums.ParseMode.HTML,
                reply_markup=markup,
                supports_streaming=True
            )
            return
        except Exception as e:
            print(f"[Start] Cached video failed: {e}")

    # Fallback: check disk for start.mp4 / Welcome.mp4
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for fname in ["start.mp4", "Start.mp4", "welcome.mp4", "Welcome.mp4"]:
        video_path = os.path.join(base_dir, fname)
        if os.path.exists(video_path):
            try:
                sent = await client.send_video(
                    chat_id=message.chat.id,
                    video=video_path,
                    caption=caption_text,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=markup,
                    supports_streaming=True
                )
                if sent and sent.video:
                    from core.db import set_setting
                    set_setting("start_video_file_id", sent.video.file_id)
                return
            except Exception as e:
                print(f"[Start] Local video send failed: {e}")
            break

    # Final fallback: text only
    await message.reply_text(caption_text, parse_mode=enums.ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True)


# ── /start handler for Groups ──────────────────────────────────────────────
@bot.on_message(filters.command("start") & filters.group)
async def start_group_handler(client: Client, message: Message):
    user = message.from_user
    u_name = user.first_name if user else "Friend"
    owner_id = Config.OWNER_ID or 6805412676
    text = (
        "<b>GᴀᴍᴇOᴠᴇʀ Mᴏᴠɪᴇ Hᴜʙ</b>\n\n"
        f"Hᴇʏ {u_name}! I Aᴍ Tʜᴇ Fᴀsᴛ Aɴᴅ PᴏᴡᴇʀFᴜʟ Mᴏᴠɪᴇ Pʟᴀʏᴇʀ Bᴏᴛ.\n\n"
        "‣ <b>Tᴏ Sᴛʀᴇᴀᴍ A Mᴏᴠɪᴇ Oʀ Sᴇʀɪᴇs:</b>\n"
        "<code>/movie [movie name]</code>\n\n"
        "‣ <b>Exᴀᴍᴘʟᴇ:</b>\n"
        "<code>/movie Avengers Endgame</code>\n\n"
        "Cʟɪᴄᴋ Tʜᴇ Bᴜᴛᴛᴏɴ Bᴇʟᴏᴡ Fᴏʀ Mᴏʀᴇ Iɴғᴏ:"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Hᴇʟᴘ Aɴᴅ Cᴏᴍᴍᴀɴᴅs", url=f"https://t.me/{Config.BOT_USERNAME}?start=help")],
        [InlineKeyboardButton("Tʀᴇɴᴅɪɴɢ Mᴏᴠɪᴇs", callback_data=f"VOD|trend_movies|{user.id if user else 0}")]
    ])
    await send_styled(chat_id=message.chat.id, text=text, markup=markup)


# Group message auto-registration
@bot.on_message(filters.group, group=-1)
async def global_group_message_handler(client: Client, message: Message):
    chat_id = message.chat.id
    title = message.chat.title or "Unknown Group"
    if chat_id and title:
        from core.db import update_group_info
        update_group_info(chat_id, title)


async def main():
    # Initialize working domain detection for VOD/MOVIES engine
    try:
        from core.domain_manager import detect_working_domain
        await detect_working_domain()
    except Exception as e:
        print(f"[DomainManager] Failed to detect working domain: {e}")

    print("\n" + "="*52)
    print("   GameOver Movie Hub Bot")
    print("   Starting clients & Web Server...")
    print("="*52)

    # Start 24/7 web server & keep-alive dashboard (Hugging Face Spaces Port 7860)
    try:
        from core.web_server import start_web_server
        await start_web_server()
    except Exception as ws_err:
        print(f"[WebServer] Note: {ws_err}")

    # Fixed 25-second cloud delay so previous Hugging Face container disconnects completely
    start_delay = int(os.getenv("START_DELAY", "25") or "25")
    if start_delay > 0:
        print("\n" + "="*56, flush=True)
        print(f"   [Cloud Startup Delay] Waiting {start_delay} seconds for previous", flush=True)
        print("   container and Telegram session to disconnect completely...", flush=True)
        print("="*56 + "\n", flush=True)
        await asyncio.sleep(start_delay)

    # Start Bot client
    try:
        await bot.start()
    except pyrogram.errors.FloodWait as fw:
        wait_time = int(fw.value)
        print("\n" + "=" * 56, flush=True)
        print(f"[TELEGRAM FLOOD WAIT: {wait_time} SECONDS]", flush=True)
        print("Telegram rate-limited authorizations due to multiple container restarts.", flush=True)
        print(f"Required wait time: {wait_time}s (~{wait_time // 60} min).", flush=True)
        print("\nINSTANT BYPASS (Bina intezaar kiye foran chalane ke liye):", flush=True)
        print("1. Telegram mein @BotFather open karein.", flush=True)
        print("2. /mybots -> Apna bot select karein -> API Token -> Revoke current token.", flush=True)
        print("3. Naya token copy karke Hugging Face Space Settings -> Secrets mein 'TOKEN' update karein.", flush=True)
        print("4. New token se FloodWait foran khatam ho jayega!", flush=True)
        print("=" * 56 + "\n", flush=True)
        print(f"[FloodWait] Waiting {wait_time} seconds before retrying...", flush=True)
        await asyncio.sleep(wait_time)
        await bot.start()
    except pyrogram.errors.ApiIdInvalid:
        print("\n" + "=" * 56)
        print("[CRITICAL ERROR: 400 API_ID_INVALID]")
        print("Telegram rejected the API_ID and API_HASH combination!")
        print(f"Loaded API_ID:   {Config.API_ID}")
        print(f"Loaded API_HASH: {Config.API_HASH[:4]}...{Config.API_HASH[-4:]} ({len(Config.API_HASH)} chars)")
        print("\nPOSSIBLE REASONS:")
        print("1. In Hugging Face Space Settings -> Secrets, API_ID or API_HASH is mistyped.")
        print("2. The API_HASH has trailing spaces or quotes.")
        print("3. API_ID and API_HASH were swapped in Settings.")
        print("4. This API_ID / API_HASH was revoked or deleted on my.telegram.org.")
        print("=" * 56 + "\n")
        raise
    except (pyrogram.errors.AccessTokenExpired, pyrogram.errors.AccessTokenInvalid) as tok_err:
        print("\n" + "=" * 56)
        print(f"[CRITICAL ERROR: BOT TOKEN INVALID / EXPIRED ({tok_err})]")
        print(f"Loaded Bot Token prefix: {Config.BOT_TOKEN[:10]}... ({len(Config.BOT_TOKEN)} chars)")
        print("\nHOW TO FIX:")
        print("1. Open Telegram -> Go to @BotFather")
        print("2. Type /mybots -> Select your bot -> API Token")
        print("3. Revoke or copy the new Bot Token")
        print("4. Update TOKEN in Hugging Face Space Settings -> Secrets")
        print("=" * 56 + "\n")
        raise

    bot_me = await bot.get_me()
    Config.BOT_USERNAME = bot_me.username or ""
    print(f"[Bot]       Started as: @{bot_me.username}")

    # Safe assistant startup with auto-retry if old session connection is still closing
    for attempt in range(1, 4):
        try:
            await assistant.start()
            break
        except pyrogram.errors.AuthKeyDuplicated as auth_err:
            if attempt < 3:
                print(f"[Assistant] Session still active in previous container ({auth_err}). Waiting 15s (Attempt {attempt}/3)...")
                await asyncio.sleep(15)
            else:
                print("\n" + "=" * 56)
                print("[CRITICAL ERROR: AUTH_KEY_DUPLICATED]")
                print("STRING3 session is currently being used simultaneously elsewhere.")
                print("Please stop duplicate containers or generate a fresh STRING3 session.")
                print("=" * 56 + "\n")
                raise auth_err
        except pyrogram.errors.SessionRevoked as rev_err:
            print("\n" + "=" * 56)
            print("[CRITICAL ERROR: SESSION_REVOKED]")
            print("The STRING3 session was terminated or logged out from Telegram!")
            print("Please generate a new Pyrogram string session.")
            print("=" * 56 + "\n")
            raise rev_err
        except Exception as conn_err:
            err_msg = str(conn_err).lower()
            if ("auth_key_duplicated" in err_msg or "connection" in err_msg) and attempt < 3:
                print(f"[Assistant] Previous session connection still closing ({conn_err}). Waiting 15s (Attempt {attempt}/3)...")
                await asyncio.sleep(15)
            else:
                raise conn_err

    me = await assistant.get_me()
    print(f"[Assistant] Logged in as: {me.first_name} (@{me.username or 'no username'})")

    # Set Telegram native menu button commands
    try:
        await bot.set_bot_commands([
            BotCommand("start", "Bot start karein"),
            BotCommand("movie", "Movie ya series stream karein"),
            BotCommand("vod", "Movie ya series stream karein"),
            BotCommand("trending", "Trending Movies & Series list dekhein"),
            BotCommand("latest", "Latest Movies & Series list dekhein"),
            BotCommand("random", "Random Hindi movie stream karein (Surprise Me)"),
            BotCommand("history", "Recent watch history aur saved progress dekhein"),
            BotCommand("request", "Request any missing movie/series to admin"),
        ])
        print("[Bot] Native menu commands set successfully!")
    except Exception as e:
        print(f"[Bot] Failed to set native menu commands: {e}")

    # Register plugins
    from plugins import movies, welcome, admin, controls
    movies.register(bot)
    welcome.register(bot)
    admin.register(bot)
    controls.register(bot)

    # Initialize PyTgCalls streamer
    await stream_manager.init(assistant, bot)

    print("\n" + "="*52)
    print("   Movie Hub Bot is running LIVE!")
    print("="*52 + "\n")

    try:
        await idle()
    except BaseException:
        pass
    finally:
        print("\nShutting down...")
        try:
            await asyncio.wait_for(assistant.stop(), timeout=1.5)
        except BaseException:
            pass
        try:
            await asyncio.wait_for(bot.stop(), timeout=1.5)
        except BaseException:
            pass
        print("[Bot] Hard exiting now... Goodbye!")
        os.kill(os.getpid(), 9)


if __name__ == "__main__":
    bot.run(main())
