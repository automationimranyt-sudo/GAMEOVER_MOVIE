---
title: GAMEOVER MOVIE HUB
emoji: 🎬
colorFrom: red
colorTo: gray
sdk: docker
pinned: false
short_description: GameOver Movie Hub VOD Streaming Telegram Bot
---

# GameOver Movie Hub

A high-performance Video-On-Demand (VOD) Telegram streaming bot powered by PyTgCalls and MovieBox API. Stream movies and TV series directly in Telegram group voice chats with clean typography, dynamic progress bar, and zero-emoji modern UI.

## Features
- Direct high-speed MovieBox VOD streaming (1080p / 720p / 480p).
- Zero-Emoji Clean Small Caps Typography.
- Interactive playback controls (`▷`, `II`, `↺`, `--I`, `▢`) with live seek bar button.
- Resume playback from saved position.
- Multi-Group isolation with vote-skip and admin management.
- Built-in `START_DELAY` for cloud container restarts on Hugging Face Spaces.

## Environment Variables (.env)
- `API_ID`: Telegram API ID from my.telegram.org
- `API_HASH`: Telegram API Hash from my.telegram.org
- `TOKEN`: Bot Token from @BotFather
- `STRING3`: Pyrogram String Session for assistant user account
- `OWNER_ID`: Telegram User ID of owner
- `START_DELAY`: Startup delay in seconds (set 15 or 20 on Hugging Face Spaces)
