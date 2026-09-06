"""
GameOver Movie Hub — Pure VOD Stream Downloader
High-performance, multi-threaded VOD stream downloader.
Leverages ThrottleBuster multi-tasking with HTTPX streaming fallback.
"""

import os
import time
import asyncio
import socket
from typing import Optional, Callable, Awaitable
import httpx
from throttlebuster import ThrottleBuster

socket.setdefaulttimeout(30.0)
from config import Config
from core.queue_manager import SongInfo

DOWNLOADS_DIR = Config.DOWNLOADS_DIR
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

DEFAULT_DOWNLOAD_HEADERS = {
    "Accept": "*/*",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:137.0) Gecko/20100101 Firefox/137.0",
    "Origin": "h5.aoneroom.com",
    "Referer": "https://fmoviesunblocked.net/",
}


async def get_download_headers_and_cookies() -> tuple[dict, dict]:
    """Retrieves verified CDN download headers and session cookies."""
    headers = dict(DEFAULT_DOWNLOAD_HEADERS)
    cookies = {}
    try:
        from core.vod_scraper import get_shared_session
        session = await get_shared_session()
        if hasattr(session, "_client") and session._client:
            client_hdrs = dict(session._client.headers)
            if "authorization" in client_hdrs:
                headers["Authorization"] = client_hdrs["authorization"]
            elif "Authorization" in client_hdrs:
                headers["Authorization"] = client_hdrs["Authorization"]
            elif getattr(session, "user_info", None) and getattr(session.user_info, "token", None):
                headers["Authorization"] = f"Bearer {session.user_info.token}"
            
            cookies = dict(session._client.cookies)
    except Exception as e:
        print(f"[Downloader] Session auth note: {e}")
    
    return headers, cookies


async def download_file(
    url: str,
    dest_path: str,
    progress_callback: Optional[Callable[[int, int, int], Awaitable[None]]] = None,
    headers: Optional[dict] = None
) -> bool:
    """
    Downloads MovieBox VOD stream using ThrottleBuster multi-tasking,
    falling back to HTTPX streaming if necessary.
    """
    auth_headers, auth_cookies = await get_download_headers_and_cookies()
    if headers:
        auth_headers.update(headers)
    # Never send the rejected themoviebox origin
    for bad in ["Origin", "origin"]:
        if "themoviebox" in str(auth_headers.get(bad, "")):
            auth_headers[bad] = "h5.aoneroom.com"

    dest_dir = os.path.dirname(dest_path) or DOWNLOADS_DIR
    filename = os.path.basename(dest_path)

    # ── Engine 1: Multi-Task ThrottleBuster Download ──
    print(f"[Downloader] Starting accelerated VOD download via ThrottleBuster...")
    try:
        tb = ThrottleBuster(
            dir=dest_dir,
            tasks=4,
            chunk_size=512,
            request_headers=auth_headers,
            cookies=auth_cookies
        )

        parts_progress = {}
        parts_expected = {}
        last_update_time = [0.0]
        last_console_time = [0.0]

        async def tb_hook(tracker):
            parts_progress[tracker.index] = tracker.downloaded_size
            parts_expected[tracker.index] = tracker.expected_size
            tot_down = sum(parts_progress.values())
            tot_size = sum(parts_expected.values())
            pct = int((tot_down / tot_size) * 100) if tot_size > 0 else 0

            now = time.time()
            if now - last_console_time[0] >= 1.0 or pct == 100:
                last_console_time[0] = now
                mb_down = tot_down / (1024 * 1024)
                mb_tot = tot_size / (1024 * 1024)
                print(f"[Downloader TB] -> {pct}% | {mb_down:.1f}/{mb_tot:.1f} MB", end="\r", flush=True)

            if progress_callback and (now - last_update_time[0] >= 2.5 or pct >= 99):
                last_update_time[0] = now
                try:
                    await progress_callback(pct, tot_down, tot_size)
                except Exception:
                    pass

        downloaded_file = await tb.run(
            url=url,
            filename=filename,
            progress_hook=tb_hook,
            disable_progress_bar=True
        )

        print()
        final_path = str(getattr(downloaded_file, "saved_to", dest_path))
        if os.path.exists(final_path) and os.path.getsize(final_path) > 100000:
            if final_path != dest_path:
                try:
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                    os.rename(final_path, dest_path)
                except Exception:
                    pass
            print(f"[Downloader] Accelerated VOD download complete: {dest_path} ({os.path.getsize(dest_path)/(1024*1024):.2f} MB)")
            if progress_callback:
                size = os.path.getsize(dest_path)
                try:
                    await progress_callback(100, size, size)
                except Exception:
                    pass
            return True
    except Exception as e:
        print(f"\n[Downloader] ThrottleBuster engine note: {e}")

    # ── Engine 2: HTTPX Chunked Stream Fallback ──
    print(f"[Downloader] Falling back to HTTPX streaming engine...")
    max_retries = 3
    timeout = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)
    loop = asyncio.get_running_loop()

    for attempt in range(1, max_retries + 1):
        try:
            existing_bytes = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
            req_headers = dict(auth_headers)
            file_mode = "wb"

            if existing_bytes > 0:
                req_headers["Range"] = f"bytes={existing_bytes}-"
                file_mode = "ab"
                print(f"[Downloader] Resuming download from byte {existing_bytes} (Attempt {attempt}/{max_retries})...")
            else:
                req_headers.pop("Range", None)
                if attempt > 1 and os.path.exists(dest_path):
                    try:
                        os.remove(dest_path)
                    except Exception:
                        pass
                print(f"[Downloader] Starting download (Attempt {attempt}/{max_retries})...")

            async with httpx.AsyncClient(headers=req_headers, cookies=auth_cookies, verify=True, follow_redirects=True, timeout=timeout) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code not in (200, 206):
                        if response.status_code == 416:
                            return True
                        print(f"[Downloader] HTTP status {response.status_code} for URL: {url[:60]}")
                        raise Exception(f"HTTP Status {response.status_code}")

                    total_size = 0
                    if existing_bytes == 0:
                        total_size = int(response.headers.get("content-length", 0))
                    else:
                        content_range = response.headers.get("Content-Range", "")
                        if "/" in content_range:
                            try:
                                total_size = int(content_range.split("/")[-1])
                            except Exception:
                                pass
                        if not total_size:
                            partial_length = int(response.headers.get("content-length", 0))
                            total_size = existing_bytes + partial_length

                    downloaded = existing_bytes
                    start_t = time.time()
                    last_cb_t = time.time()

                    with open(dest_path, file_mode) as f:
                        async for chunk in response.aiter_bytes(chunk_size=256 * 1024):
                            await loop.run_in_executor(None, f.write, chunk)
                            downloaded += len(chunk)

                            now = time.time()
                            pct = int((downloaded / total_size) * 100) if total_size > 0 else 0
                            if progress_callback and (now - last_cb_t >= 2.5 or (total_size > 0 and pct >= 99)):
                                last_cb_t = now
                                try:
                                    await progress_callback(pct, downloaded, total_size)
                                except Exception:
                                    pass

                    if downloaded >= 100000:
                        print(f"[Downloader] HTTPX download complete: {dest_path} ({downloaded/(1024*1024):.2f} MB)")
                        if progress_callback:
                            await progress_callback(100, downloaded, total_size or downloaded)
                        return True

        except Exception as e:
            print(f"[Downloader] HTTPX attempt {attempt} failed: {e}")
            if attempt < max_retries:
                await asyncio.sleep(2)

    if os.path.exists(dest_path):
        try:
            os.remove(dest_path)
        except Exception:
            pass
    return False


async def download_song(
    song: SongInfo,
    mode: str = "video",
    progress_callback: Optional[Callable[[int, int, int], Awaitable[None]]] = None
) -> Optional[str]:
    """Downloads MovieBox VOD stream locally and returns local file path."""
    clean_id = "".join(c for c in song.title if c.isalnum() or c in ("-", "_"))[:30]
    if not clean_id:
        clean_id = str(abs(hash(song.title)))

    output_filename = f"{clean_id}_{mode}.mp4"
    output_path = os.path.join(DOWNLOADS_DIR, output_filename)

    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        if size > 100000:
            print(f"[Downloader] File already downloaded and valid: {output_path} ({size / (1024*1024):.2f} MB)")
            if progress_callback:
                try:
                    await progress_callback(100, size, size)
                except Exception:
                    pass
            return output_path
        else:
            try:
                os.remove(output_path)
            except Exception:
                pass

    target_url = song.video_url or song.audio_url
    if not target_url:
        print(f"[Downloader] No stream URL provided for {song.title}")
        return None

    urls_to_try = [target_url]
    if hasattr(song, "fallback_urls") and song.fallback_urls:
        for fb in song.fallback_urls:
            if fb and fb not in urls_to_try:
                urls_to_try.append(fb)

    print(f"[Downloader] Downloading VOD stream for: {song.title}")
    for idx, u in enumerate(urls_to_try):
        if idx > 0:
            print(f"[Downloader] Primary stream failed, trying fallback stream {idx+1}/{len(urls_to_try)}...")
        ok = await download_file(u, output_path, progress_callback)
        if ok and os.path.exists(output_path):
            return output_path
    return None


def clean_cached_file(file_path: Optional[str]):
    """Removes downloaded file and any download parts from filesystem."""
    if not file_path:
        return
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"[Downloader] Deleted local cached file: {file_path}")
        
        # Clean any partial task files (.part*)
        dirname = os.path.dirname(file_path)
        base = os.path.basename(file_path)
        if dirname and os.path.exists(dirname):
            for f in os.listdir(dirname):
                if f.startswith(base) and f != base:
                    try:
                        os.remove(os.path.join(dirname, f))
                    except Exception:
                        pass
    except Exception as e:
        print(f"[Downloader] Error deleting file {file_path}: {e}")
