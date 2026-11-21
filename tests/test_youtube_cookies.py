"""YouTube cookies, for servers YouTube asks to "confirm you're not a bot".

The cookies file is handed to yt-dlp as a copy, so the owner's file is only ever read. No file, or an empty
one, changes nothing. YouTube's JavaScript puzzle is handed to Node.js or Deno when one is installed.

Runs against the code directly, with its own empty data folder. Nothing is downloaded."""
import os, sys, tempfile, time
os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-cookies-")
os.environ.pop("PEAKCUT_YT_COOKIES", None)
sys.path.insert(0, ".")
from pathlib import Path
from unittest.mock import patch
from studio import config, media
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)


COOKIES = ("# Netscape HTTP Cookie File\n"
           ".youtube.com\tTRUE\t/\tTRUE\t2000000000\tPREF\tf6=40000000\n")


def params():
    with media._ydl({}) as ydl:
        return dict(ydl.params)


# ---- no cookies file: nothing is added
check("by default the file is looked for in the data folder",
      Path(config.YT_COOKIES), Path(config.DATA_DIR) / "youtube-cookies.txt")
check("with no cookies file, yt-dlp is given none", "cookiefile" in params(), False)

# ---- a cookies file in the data folder is used, as a copy
own = Path(config.YT_COOKIES)
own.write_text(COOKIES)
got = params().get("cookiefile")
check("a cookies file in the data folder is used", bool(got), True)
check("yt-dlp gets a copy, not the owner's file", got and Path(got) != own, True)
# (yt-dlp writes the copy back in its own layout when it closes, which is why it gets a copy)
check("the copy holds the owner's cookies", got and "f6=40000000" in Path(got).read_text(), True)
check("the copy can only be read by PeakCut", got and (os.stat(got).st_mode & 0o077) == 0, True)

# yt-dlp writes cookies back when it is done: that lands on the copy, never on the owner's file
Path(got).write_text(COOKIES + ".youtube.com\tTRUE\t/\tTRUE\t2000000000\tNEW\tx\n")
check("what yt-dlp writes back does not touch the owner's file", own.read_text(), COOKIES)

# ---- a changed file is picked up without a restart
time.sleep(0.05)
own.write_text(COOKIES + ".youtube.com\tTRUE\t/\tTRUE\t2000000000\tSID\tabc\n")
os.utime(own, (time.time() + 5, time.time() + 5))
check("a changed cookies file is picked up on the next download", "SID" in Path(params()["cookiefile"]).read_text(), True)

# ---- an empty file is not cookies
own.write_text("")
check("an empty cookies file is ignored", "cookiefile" in params(), False)
own.unlink()

# ---- PEAKCUT_YT_COOKIES points at a file anywhere
elsewhere = Path(tempfile.mkdtemp(prefix="pc-cookies-elsewhere-")) / "mine.txt"
elsewhere.write_text(COOKIES)
with patch.object(config, "YT_COOKIES", elsewhere):
    got = params().get("cookiefile")
    check("a file set in PEAKCUT_YT_COOKIES is used", got and "f6=40000000" in Path(got).read_text(), True)
with patch.object(config, "YT_COOKIES", elsewhere.with_name("missing.txt")):
    check("a file set in PEAKCUT_YT_COOKIES that is not there changes nothing", "cookiefile" in params(), False)

# ---- YouTube's JavaScript puzzle
with patch.object(media.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None):
    check("Node.js is handed YouTube's puzzle when it is installed", params().get("js_runtimes"), {"node": {}})
with patch.object(media.shutil, "which", lambda name: None):
    check("with neither Node.js nor Deno, PeakCut adds nothing to yt-dlp's own default",
          "node" in (params().get("js_runtimes") or {}), False)

# ---- the options the caller passes still win
with patch.object(media.shutil, "which", lambda name: None):
    with media._ydl({"format": "ba"}) as ydl:
        check("the caller's own options are kept", ydl.params.get("format"), "ba")

# ---- when YouTube refuses, the message says what fixes it on a server
check("the 'YouTube refused' message points to the cookies setting", "cookies" in media.YT_BLOCKED, True)

# ---- live recordings use the same copy and the same JavaScript runtimes
own.write_text(COOKIES)
check("live recordings get the copy too, not the saved file", media.cookie_opts().get("cookiefile") not in (None, str(own)), True)
own.unlink()
with patch.object(media.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None):
    check("live recordings can solve YouTube's puzzle with Node.js", media.js_opts(), {"js_runtimes": {"node": {}}})

print("\nALL PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
