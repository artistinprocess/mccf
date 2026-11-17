#!/usr/bin/env python3
"""MCCF lexicon annotator (Increment 1). Deterministic: no model, no random numbers, no clock,
no import of any engine module. Reads a scene's Dialogue lines and a Lexicon v2 file, writes an
Annotations file in the trace namespace. It never writes E, B, P or S.
Usage: mccf_annotate.py LEXICON.xml SCENE.xml OUT.xml [--tags]
  --tags also writes author-intent records read from the [bracket] delivery tags in ttsText.
"""
import sys, re, hashlib
from lxml import etree

LEX = "http://mccf.artistinprocess.com/lexicon/v2"
TRC = "http://mccf.artistinprocess.com/trace/v1"
NEG = {"not", "no", "never", "none", "nothing", "neither", "nor", "without", "cannot"}

def lexicon_ref(path):
    """id@version#sha256 over the canonical (C14N) form, so whitespace and attribute order do not matter."""
    root = etree.parse(path, etree.XMLParser(remove_blank_text=True)).getroot()
    canon = etree.tostring(root, method="c14n")
    return "%s@%s#sha256:%s" % (root.get("id"), root.get("version"), hashlib.sha256(canon).hexdigest()[:16])

def load_lexicon(path):
    root = etree.parse(path).getroot()
    q = lambda t: "{%s}%s" % (LEX, t)
    terms = {}
    for t in root.iter(q("Term")):
        terms[t.get("id")] = [(p.get("dimension"), p.get("level"), p.get("category")) for p in t.iter(q("Profile"))]
    MULTI.clear(); MULTI.update(d.get("id") for d in root.iter(q("Dimension")) if d.get("multi") == "true")
    forms = [(f.get("text").lower(), f.get("match"), f.get("term"), f.get("source") or "text") for f in root.iter(q("Form"))]
    return terms, forms

def spoken(el):
    """Words as spoken: element text, with authored [bracket] delivery cues removed."""
    return re.sub(r"\[[^\]]*\]", " ", "".join(el.itertext()))

def words(text):
    return re.findall(r"[a-z']+", text.lower().replace("’", "'"))

def hits(tokens, forms, source="text"):
    forms = [(t, m, te) for t, m, te, src in forms if src == source]
    out = []
    for w in tokens:
        for text, match, term in forms:
            if (match == "stem" and w.startswith(text)) or (match == "word" and w == text):
                out.append((w, term))
    # phrases
    joined = " ".join(tokens)
    for text, match, term in forms:
        if match == "phrase" and text in joined:
            out.append((text, term))
    return out

def _by_dim(hs, terms):
    by_dim = {}
    for form, term in hs:
        for dim, level, cat in terms[term]:
            by_dim.setdefault(dim, []).append((form, term, level, cat))
    return by_dim

def _header(line, seq, lexref, target, annotator):
    A = etree.Element("{%s}Annotation" % TRC, nsmap={None: TRC})
    for k, v in [("id", "an-%04d" % seq), ("annotates", "dialogue:" + line.get("id")), ("target", target),
                 ("annotator", annotator), ("blind", "na"), ("speaker", line.get("actor") or "unknown"),
                 ("lexicon", lexref), ("sequence", str(seq)), ("validation", "ok")]:
        A.set(k, v)
    return A

MULTI = set()   # ids of multi-valued categorical dimensions, set when a lexicon is loaded

def annotate_line(line, seq, terms, forms, lexref):
    tokens = words(spoken(line))
    by_dim = _by_dim(hits(tokens, forms), terms)
    A = _header(line, seq, lexref, "expression", "lexicon")
    ctx = etree.SubElement(A, "{%s}Context" % TRC); ctx.set("level", "utterance"); ctx.set("computedState", "none")
    _fill(A, by_dim)
    for w in tokens:                                        # negation is recorded, never applied (known gap)
        if w in NEG or w.endswith("n't"):
            C = etree.SubElement(A, "{%s}Cue" % TRC); C.set("kind", "negation"); C.set("word", w)
    return A

def annotate_tags(line, seq, terms, forms, lexref):
    """Authored delivery tags in the line's ttsText, read as the author's stated intent (annotator=author, target=intent).
    Never shown to a blind annotator. Tags with no matching form are kept as deliveryTag cues (vocabulary candidates)."""
    segs = [x.strip().lower() for m in re.findall(r"\[([^\]]+)\]", line.get("ttsText") or "") for x in m.split(",") if x.strip()]
    if not segs: return None
    hs, unmapped = [], []
    for sg in segs:
        h = hits(words(sg), forms, "tag")
        hs += h
        if not h: unmapped.append(sg)
    A = _header(line, seq, lexref, "intent", "author")
    _fill(A, _by_dim(hs, terms))
    for sg in unmapped:
        C = etree.SubElement(A, "{%s}Cue" % TRC); C.set("kind", "deliveryTag"); C.set("word", sg)
    return A

def _fill(A, by_dim):
    conflict_dims, conflict_terms = [], set()
    for dim in sorted(by_dim):
        entries = by_dim[dim]
        D = etree.SubElement(A, "{%s}Dim" % TRC); D.set("id", dim)
        if entries[0][3] is not None:                       # categorical
            cats = sorted({e[3] for e in entries})
            if dim in MULTI: D.set("category", " ".join(cats)); D.set("confidence", "medium")
            elif len(cats) == 1: D.set("category", cats[0]); D.set("confidence", "medium" if len(entries) == 1 else "high")
            else: D.set("status", "conflict")
        else:                                               # scaled: keep disagreement visible, do not average it away
            lv = sorted({int(e[2]) for e in entries})
            if lv[-1] - lv[0] >= 2: D.set("status", "conflict")
            else:
                D.set("level", str(round(sum(int(e[2]) for e in entries) / len(entries) + 1e-9)))
                D.set("confidence", "low" if len(entries) == 1 else "medium")
        if D.get("status") == "conflict":
            conflict_dims.append(dim); conflict_terms |= {e[1] for e in entries}
        for form, term, _, _ in entries:
            E = etree.SubElement(D, "{%s}Evidence" % TRC); E.set("form", form); E.set("term", term); E.set("dimension", dim)
    if conflict_dims:                                       # preserved, never resolved here; the author or a later appraisal may resolve it
        C = etree.SubElement(A, "{%s}Conflict" % TRC)
        C.set("dimensions", " ".join(conflict_dims)); C.set("terms", " ".join(sorted(conflict_terms))); C.set("resolved", "false")
    return A

def run(lex_path, scene_path, out_path, with_tags=False):
    terms, forms = load_lexicon(lex_path)
    lexref = lexicon_ref(lex_path)
    scene = etree.parse(scene_path).getroot()
    root = etree.Element("{%s}Annotations" % TRC, nsmap={None: TRC})
    root.set("scene", scene.get("id") or "unknown"); root.set("lexicon", lexref); root.set("schemaVersion", "1.0")
    for i, line in enumerate(scene.iter("Line"), 1):
        root.append(annotate_line(line, i, terms, forms, lexref))
    if with_tags:                                           # author intent records, numbered after the expression records
        seq = len(root)
        for line in scene.iter("Line"):
            a = annotate_tags(line, seq + 1, terms, forms, lexref)
            if a is not None: seq += 1; root.append(a)
    etree.ElementTree(root).write(out_path, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    return out_path

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--tags"]
    if len(args) != 3: sys.exit(__doc__)
    print(run(*args, with_tags="--tags" in sys.argv))
