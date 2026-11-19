"""Settings, Clips & YouTube: the facecam's place, YouTube's transcript and the YouTube cookies file, all from the
dashboard. Only an admin may see or change them. Runs against the app directly, with its own empty data folder."""
import os, stat, sys, tempfile
os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-prefs-")
os.environ.update(DATABASE_URL="", PEAKCUT_ACCOUNTS="1", PEAKCUT_PUBLIC_URL="https://clips.example.com",
                  PEAKCUT_VERIFY_EMAIL="0", PEAKCUT_AI_KEY="")
for k in ("PEAKCUT_YT_COOKIES", "PEAKCUT_CAM_X", "PEAKCUT_CAM_Y", "PEAKCUT_YT_TRANSCRIPT"):
    os.environ.pop(k, None)
sys.path.insert(0, ".")
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from studio import auth, config, db, media, prefs, render, server
db.init()
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

BASE = "https://clips.example.com"
ORIGIN = {"Origin": BASE}
def person(email, admin=False):
    u, _ = auth._create(email, email.split("@")[0], password_hash="x")
    if admin:
        with db.engine.begin() as c:
            c.execute(db.users.update().where(db.users.c.id == u.id).values(is_admin=True))
    cl = TestClient(server.app, base_url=BASE, follow_redirects=False)
    cl.cookies.set(auth.COOKIE, auth.start_session(u.id))
    return u, cl
boss, a = person("boss@example.com", admin=True)
user, b = person("user@example.com")

COOKIES = ("# Netscape HTTP Cookie File\n"
           ".youtube.com\tTRUE\t/\tTRUE\t2000000000\tPREF\tf6=40000000\n"
           ".youtube.com\tTRUE\t/\tTRUE\t2000000000\tSID\tabc\n")

# ---- only an admin
check("a normal user cannot see these settings", b.get("/api/prefs").status_code, 404)
check("...or change them", b.put("/api/prefs", json={"cam_x": 5}, headers=ORIGIN).status_code, 404)
check("...or upload cookies", b.post("/api/prefs/youtube-cookies", files={"file": ("c.txt", COOKIES)}, headers=ORIGIN).status_code, 404)
check("a change from another website is refused",
      a.put("/api/prefs", json={"cam_x": 5}, headers={"Origin": "https://evil.example"}).status_code, lambda s: s >= 400)

# ---- the facecam's place
p = a.get("/api/prefs").json()
check("at first the facecam goes in the recommended place", (p["cam_x"], p["cam_y"], p["cam_default"]), (0, 500, {"x": 0, "y": 500}))
p = a.put("/api/prefs", json={"cam_x": 120, "cam_y": 640}, headers=ORIGIN).json()
check("a new place is saved", (p["cam_x"], p["cam_y"]), (120, 640))
check("and the clips use it", render._pip_box([0, 460, 387, 242])[:2], (120, 640))
check("it lasts: it is kept in the data folder", (Path(config.DATA_DIR) / "prefs.json").is_file(), True)
p = a.put("/api/prefs", json={"cam_x": 99999, "cam_y": -5}, headers=ORIGIN).json()
check("a place outside the clip is kept inside it", (p["cam_x"], p["cam_y"]), (1080, 0))
check("nonsense is refused", a.put("/api/prefs", json={"cam_x": "left"}, headers=ORIGIN).status_code, 400)
p = a.put("/api/prefs", json={"reset_cam": True}, headers=ORIGIN).json()
check("back to the recommended place", (p["cam_x"], p["cam_y"]), (0, 500))

# ---- YouTube's own transcript
check("YouTube's transcript is used by default", a.get("/api/prefs").json()["yt_transcript"], True)
a.put("/api/prefs", json={"yt_transcript": False}, headers=ORIGIN)
check("it can be turned off from the dashboard", (prefs.yt_transcript(), a.get("/api/prefs").json()["yt_transcript"]), (False, False))
a.put("/api/prefs", json={"yt_transcript": True}, headers=ORIGIN)

# ---- the YouTube cookies file
check("at first there are no cookies", a.get("/api/prefs").json()["cookies"]["present"], False)
r = a.post("/api/prefs/youtube-cookies", files={"file": ("cookies.txt", COOKIES)}, headers=ORIGIN)
ck = r.json()
check("a cookies.txt file is taken", (r.status_code, ck["present"], ck["count"], ck["youtube"], ck["signed_in"]), (200, True, 2, True, True))
check("it is kept where downloads look for it", Path(config.YT_COOKIES).read_text(), COOKIES)
check("only PeakCut can read it", stat.S_IMODE(os.stat(config.YT_COOKIES).st_mode) & 0o077, 0)
check("the cookies themselves are never sent to the page", "abc" not in r.text and "f6=40000000" not in r.text, True)
with media._ydl({}) as ydl:
    check("downloads use them straight away", bool(ydl.params.get("cookiefile")), True)
check("a file that isn't cookies.txt is refused",
      a.post("/api/prefs/youtube-cookies", files={"file": ("x.txt", "hello world")}, headers=ORIGIN).status_code, 400)
check("cookies with nothing from YouTube are refused",
      a.post("/api/prefs/youtube-cookies", files={"file": ("x.txt", ".example.com\tTRUE\t/\tTRUE\t2000000000\tA\tb\n")},
             headers=ORIGIN).status_code, 400)
check("a refused file leaves the good one in place", Path(config.YT_COOKIES).read_text(), COOKIES)
signed_out = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2000000000\tPREF\tf6=1\n"
ck = a.post("/api/prefs/youtube-cookies", files={"file": ("c.txt", signed_out)}, headers=ORIGIN).json()
check("cookies from a signed-out browser are taken, and said to be signed out", (ck["present"], ck["signed_in"]), (True, False))
ck = a.delete("/api/prefs/youtube-cookies", headers=ORIGIN).json()
check("the cookies can be removed", (ck["present"], Path(config.YT_COOKIES).exists()), (False, False))

# ---- a cookies file set in .env is shown, not changed from the dashboard
with patch.dict(os.environ, {"PEAKCUT_YT_COOKIES": "/somewhere/cookies.txt"}):
    ck = a.get("/api/prefs").json()["cookies"]
    check("a file set in .env is said to be set there", ck["from_env"], True)
    check("...and can't be replaced from the dashboard",
          a.post("/api/prefs/youtube-cookies", files={"file": ("c.txt", COOKIES)}, headers=ORIGIN).status_code, 400)

# ---- the swear filter is offered to the page
check("the page is told the swear filter's choices", list(a.get("/api/status").json()["cleans"]), ["off", "text", "bleep"])

print("\nALL PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
