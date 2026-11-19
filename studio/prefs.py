"""Settings that are changed in the dashboard (Settings, Clips & YouTube) and hold for the whole server.

They are kept in prefs.json in the data folder. What is saved here wins over .env, as with the AI settings:
.env gives the starting value, the dashboard changes it.

  cam_x, cam_y     where the streamer's webcam goes in the gameplay layout (pixels of the 1080x1920 clip)
  yt_transcript    use YouTube's own transcript to find clips faster
and the YouTube cookies file (see config.YT_COOKIES), which the dashboard can upload and remove.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from . import config

FILE_NAME = "prefs.json"
CLIP_W, CLIP_H = 1080, 1920
MAX_COOKIES_BYTES = 1_000_000
_lock = threading.Lock()
_cache: dict = {"mtime": None, "data": {}}


def _path() -> Path:
    return Path(config.DATA_DIR) / FILE_NAME


def _load() -> dict:
    p = _path()
    try:
        m = p.stat().st_mtime
    except OSError:
        return {}
    if _cache["mtime"] != m:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        _cache.update(mtime=m, data=data if isinstance(data, dict) else {})
    return dict(_cache["data"])


def _save(data: dict):
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    _cache["mtime"] = None


# ---------------------------------------------------------------- the webcam's place

def cam() -> tuple[int, int]:
    """(x, y) of the webcam's top-left corner in the clip: what the dashboard saved, or else .env."""
    d = _load()
    try:
        return int(d.get("cam_x", config.CAM_X)), int(d.get("cam_y", config.CAM_Y))
    except (TypeError, ValueError):
        return int(config.CAM_X), int(config.CAM_Y)


def yt_transcript() -> bool:
    d = _load()
    return bool(d["yt_transcript"]) if "yt_transcript" in d else bool(config.YT_TRANSCRIPT)


def save(body: dict) -> dict:
    """Saves what the dashboard sent. Unknown keys are ignored; numbers are kept inside the clip."""
    with _lock:
        d = _load()
        if body.get("reset_cam"):
            d.pop("cam_x", None)
            d.pop("cam_y", None)
        for k, top in (("cam_x", CLIP_W), ("cam_y", CLIP_H)):
            if k in body and body[k] not in ("", None):
                try:
                    d[k] = max(0, min(top, int(float(body[k]))))
                except (TypeError, ValueError):
                    raise ValueError("The webcam's place must be a number of pixels.") from None
        if "yt_transcript" in body:
            d["yt_transcript"] = bool(body["yt_transcript"])
        _save(d)
    return public()


# ---------------------------------------------------------------- YouTube cookies

def _cookies_from_env() -> bool:
    return bool(os.environ.get("PEAKCUT_YT_COOKIES"))


def cookies_info() -> dict:
    """What the dashboard may know about the cookies file. Never the cookies themselves."""
    p = Path(config.YT_COOKIES)
    info = {"present": False, "from_env": _cookies_from_env(), "path": str(p) if _cookies_from_env() else "",
            "count": 0, "youtube": False, "signed_in": False, "updated": None}
    try:
        st = p.stat()
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return info
    rows = [r.split("\t") for r in text.splitlines()
            if r.strip() and (not r.startswith("#") or r.startswith("#HttpOnly_"))]
    rows = [r for r in rows if len(r) >= 7]
    names = {r[5] for r in rows if "youtube.com" in r[0] or "google.com" in r[0]}
    info.update(present=st.st_size > 0, count=len(rows), updated=st.st_mtime,
                youtube=any("youtube.com" in r[0] for r in rows),
                signed_in=bool(names & {"SID", "__Secure-1PSID", "__Secure-3PSID", "LOGIN_INFO", "SAPISID"}))
    return info


def save_cookies(data: bytes) -> dict:
    """Checks that this is a cookies.txt file with YouTube cookies in it, then keeps it in the data folder."""
    if _cookies_from_env():
        raise ValueError("The cookies file is set with PEAKCUT_YT_COOKIES in the .env file. Change it there, or "
                         "remove that line to manage it here.")
    if not data or len(data) > MAX_COOKIES_BYTES:
        raise ValueError("That file is empty or too big to be a cookies file.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("That isn't a cookies.txt file (it should be plain text).") from None
    rows = [r.split("\t") for r in text.splitlines()
            if r.strip() and (not r.startswith("#") or r.startswith("#HttpOnly_"))]
    if not rows or any(len(r) < 7 for r in rows):
        raise ValueError("That isn't a cookies.txt file. Export the cookies in the Netscape cookies.txt format "
                         "(the \"Get cookies.txt LOCALLY\" extension does it).")
    if not any("youtube.com" in r[0] for r in rows):
        raise ValueError("There are no YouTube cookies in that file. Export them while youtube.com is open.")
    p = Path(config.YT_COOKIES)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, p)
    os.utime(p, (time.time(), time.time()))
    return cookies_info()


def remove_cookies() -> dict:
    if _cookies_from_env():
        raise ValueError("The cookies file is set with PEAKCUT_YT_COOKIES in the .env file. Remove it there.")
    try:
        Path(config.YT_COOKIES).unlink()
    except FileNotFoundError:
        pass
    return cookies_info()


def public() -> dict:
    x, y = cam()
    return {"cam_x": x, "cam_y": y, "cam_default": {"x": int(config.CAM_X), "y": int(config.CAM_Y)},
            "clip": {"w": CLIP_W, "h": CLIP_H}, "yt_transcript": yt_transcript(), "cookies": cookies_info()}
