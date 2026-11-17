#!/usr/bin/env python3
"""MCCF audio render helper (DRAFT, 2026-11-10). Offline. Prepares and checks ElevenLabs renders; it never calls ElevenLabs itself
(you or Claude run the MCP text_to_speech calls from the run sheet) and never edits a scene in place.

  manifest SCENE VOICES.json LEDGER.json OUT.json [--audio-root DIR] [--run-sheet OUT.md]
  adopt    LEDGER.json MANIFEST.json               record existing audio as current (baseline, assumes the files match the text)
  record   LEDGER.json MANIFEST.json LINEID=FILE ...    record freshly rendered files
  propose  SCENE LEXICON.xml MAPPING.json OUT.json [--field FIELD.json] [--include-tagged]
  apply    SCENE PROPOSALS.json OUT_SCENE.xml       copies the scene, applying proposals marked "accepted": true
  verify   MANIFEST.json TRANSCRIPT_DIR OUT.json    compare speech_to_text transcripts (TRANSCRIPT_DIR/<lineId>.txt) with the line text
"""
import sys, os, re, json, hashlib, difflib, datetime
from lxml import etree
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import mccf_annotate as A

TOOL_VERSION = "1"
BR = re.compile(r"\[([^\]]*)\]")
def jdump(o): return json.dumps(o, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
def h(o): return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
def lines_of(scene): return list(etree.parse(scene).getroot().iter("Line"))
def spoken_words(tts): return re.findall(r"[a-z0-9']+", BR.sub(" ", tts or "").lower().replace("’", "'"))
def tag_segments(tts): return [x.strip() for m in BR.findall(tts or "") for x in m.split(",") if x.strip()]

# ---------------------------------------------------------------- manifest / ledger
def render_hash(line, voice):
    return h({"v": TOOL_VERSION, "ttsText": line.get("ttsText") or "".join(line.itertext()).strip(), "voice": voice})

def sfx_and_silence(tts):
    sfx, gaps = [], []
    for sg in tag_segments(tts):
        w = sg.lower()
        if re.search(r"inhal|exhal|breath|sigh|mutter", w): sfx.append({"tag": sg, "prompt": "a quiet, close human %s, room tone, no speech" % w, "duration_seconds": 2})
        elif "pause" in w: gaps.append({"tag": sg, "suggested_gap_seconds": 1.5 if "long" in w else 0.6, "note": "default guess; tune by ear"})
    return sfx, gaps

def manifest(scene, voices, ledger, out, audio_root=None, run_sheet=None):
    V = json.load(open(voices)); L = json.load(open(ledger)) if os.path.exists(ledger) else {}
    items = []
    for ln in lines_of(scene):
        actor = ln.get("actor") or "unknown"
        voice = V.get(actor) or V.get("default") or {}
        tts = ln.get("ttsText") or "".join(ln.itertext()).strip()
        digest = render_hash(ln, voice)
        led = L.get(ln.get("id")); af = ln.get("audioFile") or ""
        present = bool(audio_root and af and os.path.exists(os.path.join(audio_root, af)))
        if led and led["hash"] == digest and (present or not audio_root): st = "current"
        elif led: st = "stale"
        elif present: st = "untracked"
        else: st = "missing"
        sfx, gaps = sfx_and_silence(tts)
        items.append({"lineId": ln.get("id"), "actor": actor, "text": tts, "voice": voice, "audioFile": af or "Dialog/%s.mp3" % ln.get("id"),
                      "hash": digest, "status": st, "sfxCandidates": sfx, "silenceCandidates": gaps})
    m = {"scene": etree.parse(scene).getroot().get("id"), "toolVersion": TOOL_VERSION, "items": items,
         "summary": {s: sum(1 for i in items if i["status"] == s) for s in ("current", "stale", "missing", "untracked")}}
    open(out, "w").write(jdump(m))
    if run_sheet:
        todo = [i for i in items if i["status"] in ("stale", "missing")]
        r = ["# Render run sheet: %s" % m["scene"], "", "Summary: %s" % m["summary"], "",
             "Before running: `check_subscription` to confirm credits. For each item below call `text_to_speech` with the text and voice shown, save into the scene's Dialog folder, then run `record`.",
             "Parameter names are to be confirmed against the tool's schema on your machine.", ""]
        for i in todo:
            r += ["## %s (%s) [%s]" % (i["lineId"], i["actor"], i["status"]), "- text: `%s`" % i["text"], "- voice: `%s`" % json.dumps(i["voice"], sort_keys=True),
                  "- target file: `%s`" % i["audioFile"], "- hash: `%s`" % i["hash"], ""]
        open(run_sheet, "w").write("\n".join(r) + "\n")
    return m

def _ledger_set(ledger, mpath, pairs, source):
    L = json.load(open(ledger)) if os.path.exists(ledger) else {}
    M = {i["lineId"]: i for i in json.load(open(mpath))["items"]}
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    for lid, f in pairs:
        it = M[lid]; L[lid] = {"hash": it["hash"], "file": f or it["audioFile"], "voice": it["voice"], "source": source, "recorded": now}
    open(ledger, "w").write(jdump(L)); return L

# ---------------------------------------------------------------- tag proposals
def propose(scene, lexicon, mapping, out, field=None, include_tagged=False):
    terms, forms = A.load_lexicon(lexicon); M = json.load(open(mapping)); F = json.load(open(field)) if field else {}
    props = []
    for ln in lines_of(scene):
        tts = ln.get("ttsText") or "".join(ln.itertext()).strip()
        if tag_segments(tts) and not include_tagged: continue
        reasons, tags = [], []
        words = A.words(A.spoken(ln))
        for w, term in A.hits(words, forms, "text"):
            for t in M.get("emotion_terms", {}).get(term, []):
                if t not in tags: tags.append(t); reasons.append("word '%s' -> term %s -> tag [%s]" % (w, term, t))
        ebps = F.get(ln.get("id"))
        for rule in M.get("field", []):
            c = rule["if"]; v = (ebps or {}).get(c["channel"])
            if v is None: continue
            if ("below" in c and v < c["below"]) or ("above" in c and v > c["above"]):
                if rule["tag"] not in tags: tags.append(rule["tag"]); reasons.append("field %s=%.2f %s %s -> tag [%s]" % (c["channel"], v, "below" if "below" in c else "above", c.get("below", c.get("above")), rule["tag"]))
        if not tags: continue
        pref = "[%s] " % ", ".join(tags)
        props.append({"lineId": ln.get("id"), "actor": ln.get("actor"), "current_ttsText": tts, "proposed_ttsText": pref + BR.sub("", tts).lstrip(),
                      "tags": tags, "reasons": reasons, "tagSource": "algorithmic", "accepted": False})
    doc = {"scene": etree.parse(scene).getroot().get("id"), "mapping": M.get("status", "unknown"), "note": "Proposals only. The author sets accepted:true; nothing here changes a scene until `apply`.", "proposals": props}
    open(out, "w").write(jdump(doc)); return doc

def apply(scene, proposals, out):
    raw = open(scene, newline="", encoding="utf-8").read(); n = 0
    for p in json.load(open(proposals))["proposals"]:
        if not p.get("accepted"): continue
        pat = re.compile(r'(<Line\b[^>]*\bid="%s"[^>]*>)' % re.escape(p["lineId"]))
        m = pat.search(raw)
        if not m: continue
        tag = m.group(1); esc = p["proposed_ttsText"].replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
        new = re.sub(r'ttsText="[^"]*"', lambda _: 'ttsText="%s"' % esc, tag, count=1)
        new = re.sub(r'tagSource="[^"]*"', 'tagSource="algorithmic"', new, count=1)
        raw = raw[:m.start()] + new + raw[m.end():]; n += 1
    open(out, "w", newline="", encoding="utf-8").write(raw); return n

# ---------------------------------------------------------------- verification of renders
def verify(manifest_path, tdir, out):
    res = []
    for it in json.load(open(manifest_path))["items"]:
        f = os.path.join(tdir, it["lineId"] + ".txt")
        if not os.path.exists(f): res.append({"lineId": it["lineId"], "status": "no-transcript"}); continue
        want = spoken_words(it["text"]); got = re.findall(r"[a-z0-9']+", open(f, encoding="utf-8").read().lower().replace("’", "'"))
        sm = difflib.SequenceMatcher(None, want, got, autojunk=False)
        dropped = [w for op, a, b, c, d in sm.get_opcodes() if op in ("delete", "replace") for w in want[a:b]]
        extra = [w for op, a, b, c, d in sm.get_opcodes() if op in ("insert", "replace") for w in got[c:d]]
        tagwords = {w for sg in tag_segments(it["text"]) for w in re.findall(r"[a-z']+", sg.lower())}
        aloud = [w for w in extra if w in tagwords]
        ratio = round(sm.ratio(), 3)
        res.append({"lineId": it["lineId"], "ratio": ratio, "dropped": dropped, "extra": extra, "tagsReadAloud": aloud,
                    "status": "ok" if ratio >= 0.97 and not aloud else "check"})
    open(out, "w").write(jdump({"results": res})); return res

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    def opt(name):
        if name in a: i = a.index(name); v = a[i + 1]; del a[i:i + 2]; return v
    def flag(name):
        if name in a: a.remove(name); return True
    cmd = a.pop(0)
    if cmd == "manifest":
        ar, rs = opt("--audio-root"), opt("--run-sheet"); print(manifest(a[0], a[1], a[2], a[3], ar, rs)["summary"])
    elif cmd in ("adopt", "record"):
        M = json.load(open(a[1]))["items"]
        pairs = [(i["lineId"], None) for i in M if i["status"] in ("untracked",)] if cmd == "adopt" else [tuple(x.split("=", 1)) for x in a[2:]]
        _ledger_set(a[0], a[1], pairs, "adopted" if cmd == "adopt" else "rendered"); print(len(pairs), "recorded")
    elif cmd == "propose":
        fl, it = opt("--field"), flag("--include-tagged"); print(len(propose(a[0], a[1], a[2], a[3], fl, it)["proposals"]), "proposals")
    elif cmd == "apply": print(apply(*a[:3]), "applied")
    elif cmd == "verify": print(sum(1 for r in verify(*a[:3]) if r["status"] != "ok"), "to check")
    else: sys.exit(__doc__)
