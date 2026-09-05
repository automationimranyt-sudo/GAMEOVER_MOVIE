"""
GameOver Movie Hub — Typography & Style Helper
Centralized Unicode Small Capitals font converter and zero-emoji UI standards.
"""

SMALL_CAPS_MAP = {
    'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ',
    'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ',
    'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ', 's': 's', 't': 'ᴛ', 'u': 'ᴜ',
    'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ'
}

def to_small_caps(text: str) -> str:
    """Converts a standard text string into stylish Small Caps typography."""
    if not text:
        return ""
    return "".join(SMALL_CAPS_MAP.get(c, c) for c in text)

# Global Zero-Emoji Clean Header
HEADER = "<b>GᴀᴍᴇOᴠᴇʀ Mᴏᴠɪᴇ Hᴜʙ</b>\n\n"
ADMIN_HEADER = "<b>GᴀᴍᴇOᴠᴇʀ Aᴅᴍɪɴ Pᴀɴᴇʟ</b>\n\n"

# Standard Bullet
BULLET = "‣ "

# Clean Player Control Symbols (Matching Image 2 Reference)
PLAY_SYM = "▷"
PAUSE_SYM = "II"
REPLAY_SYM = "↺"
SKIP_SYM = "--I"
STOP_SYM = "▢"
CLOSE_SYM = "CLOSE"

# Safe global patch for pyrogram InlineKeyboardButton style attribute
try:
    import pyrogram.types
    if not hasattr(pyrogram.types.InlineKeyboardButton, "_style_patched"):
        _orig_btn_init = pyrogram.types.InlineKeyboardButton.__init__
        def _patched_btn_init(self, *args, **kwargs):
            style = kwargs.pop("style", None)
            _orig_btn_init(self, *args, **kwargs)
            self.style = style
        pyrogram.types.InlineKeyboardButton.__init__ = _patched_btn_init
        pyrogram.types.InlineKeyboardButton._style_patched = True
except Exception:
    pass
