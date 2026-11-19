"""The swear filter: off, text (masked in captions, heading and post text), bleep (and beeped in the sound).

Runs against the code directly, with its own empty data folder. Nothing is downloaded."""
import os, subprocess, sys, tempfile
os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-swear-")
os.environ["PEAKCUT_AI_KEY"] = ""
sys.path.insert(0, ".")
from pathlib import Path
from studio import jobs, posting, profanity, render
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)


P = profanity
# ---- which words count
for w in ("fuck", "Fucking!", "motherfuckers", "shit,", "SHIIIT", "fuuuck", "bullshit", "ass", "bc", "madarchod",
          "Bhenchod", "chutiya", "bsdk"):
    check(f"'{w}' is a swear word", P.is_swear(w), True)
for w in ("assist", "class", "Scunthorpe", "cocktail", "hello", "shitake", "pussycat", "damn", "hell", "I'm", "GTA6"):
    check(f"'{w}' is left alone", P.is_swear(w), False)

# ---- masking keeps the first letter, the length and the punctuation
check("a word is masked with its first letter kept", P.mask_word("fucking"), "f******")
check("capitals and punctuation stay", P.mask_word("Fuck!"), "F***!")
check("a sentence is masked word by word", P.clean_text("What the fuck, this is bullshit bro!"), "What the f***, this is b******* bro!")
check("a swear hashtag is dropped, not masked", P.clean_tags(["gta6", "fuckyeah", "ishowspeed"]), ["gta6", "ishowspeed"])
clip = {"hook": "WHAT THE FUCK", "title": "Shit goes wrong", "description": "He said fuck", "hashtags": ["shit", "gta"],
        "highlight_words": ["FUCK", "WRONG"]}
P.clean_clip_text(clip)
check("a clip's heading, title, description and hashtags are masked",
      (clip["hook"], clip["title"], clip["description"], clip["hashtags"], clip["highlight_words"]),
      ("WHAT THE F***", "S*** goes wrong", "He said f***", ["gta"], ["WRONG"]))
check("caption words keep their timings", P.clean_words([{"w": "fuck", "s": 1.0, "e": 1.3}]), [{"w": "f***", "s": 1.0, "e": 1.3}])

# ---- where to beep
ws = [{"w": "what", "s": 10.0, "e": 10.2}, {"w": "fuck", "s": 10.2, "e": 10.5}, {"w": "shit!", "s": 10.52, "e": 10.8},
      {"w": "bro", "s": 11.0, "e": 11.2}, {"w": "fuck", "s": 30.0, "e": 30.3}]
check("next-door swear words become one beep, timed from the clip's start", P.bleeps(ws, 9.0, 20.0), [(1.16, 1.84)])
check("words outside the clip are not beeped", P.bleeps(ws[4:], 9.0, 20.0), [])

# ---- the setting itself
check("the setting is offered with three choices", list(P.MODES), ["off", "text", "bleep"])
check("a video's options keep the swear filter", jobs.clean_options({"clean": "bleep"}), {"clean": "bleep"})
check("an unknown choice falls back to off", jobs.clean_options({"clean": "loud"}), {"clean": "off"})
check("by default nothing is changed", jobs.DEFAULTS["clean"], "off")
from studio import creators
check("a creator can have it as a default", creators.DEFAULTS["clean"], "off")

# ---- the sound: muted and beeped where the swear words are
graph, label = render._audio([(1.2, 1.6)], 10.0)
check("with beeps, the swear word is muted", "volume=0:enable='between(t,1.200,1.600)'" in graph, True)
check("and a tone plays in its place", "sine=frequency=1000" in graph and "amix" in graph, True)
check("the loudness is still made even", "loudnorm=I=-14" in graph, True)
check("without beeps, the sound is only made even", render._audio([], 10.0), (";[0:a:0]loudnorm=I=-14:TP=-1.5:LRA=11[a]", "[a]"))

# ---- a real render: a beep where the word was, the rest untouched
work = Path(tempfile.mkdtemp(prefix="pc-swear-work-"))
src = work / "talk.mp4"
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x334455:s=1280x720:r=25",
                "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=0.3:sample_rate=48000", "-t", "6",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)], check=True)
words = [{"w": "what", "s": 1.0, "e": 1.4}, {"w": "the", "s": 1.4, "e": 1.6}, {"w": "fuck", "s": 2.0, "e": 2.6}]
out = render.render_clip(src, work, "beeped", {"start": 0.0, "end": 6.0, "hook": "WHAT THE FUCK", "layout": "crop",
                                               "style": "bounce", "captions": True, "clean": "bleep"}, words, 1280, 720)
ass = (work / "beeped.ass").read_text()
check("the captions show the word masked", "F***" in ass.upper() and "FUCK" not in ass.upper(), True)
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(work / "beeped.mp4"), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                     capture_output=True).stdout
import array, math
pcm = array.array("h", raw)
def tone(a, b, hz=1000):
    seg = pcm[int(a * 16000):int(b * 16000)]
    re_ = sum(v * math.cos(2 * math.pi * hz * i / 16000) for i, v in enumerate(seg))
    im = sum(v * math.sin(2 * math.pi * hz * i / 16000) for i, v in enumerate(seg))
    power = sum(v * v for v in seg) or 1
    return 2 * (re_ * re_ + im * im) / (len(seg) * power)     # share of the sound that is the tone
check("the swear word is a beep in the sound", tone(2.1, 2.5) > 0.8, True)
check("the rest of the sound is not", tone(3.5, 4.5) < 0.05, True)

# ---- what is posted
c = {"description": "That was shit", "hashtags": ["fuck", "gta6"], "clean": "text"}
check("posted text is masked too", posting._caption(c, {"post_footer": ""}), "That was s***\n\n#gta6")
c["clean"] = "off"
check("with the filter off, posted text is as written", posting._caption(c, {"post_footer": ""}), "That was shit\n\n#fuck #gta6")

print("\nALL PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
