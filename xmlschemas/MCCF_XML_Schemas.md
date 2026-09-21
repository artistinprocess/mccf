# MCCF XML Schemas — Design Rationale

**Version:** 1.1 (Sept 2026) — combined into a single-namespace schema
**Scope:** `mccf.xsd` (supersedes the original three-file split)

---

## Why XML as ground truth

MCCF is built on a deliberate architectural bet: XML documents are the
canonical, authoritative representation of everything the system
knows — a character, a scene, a recorded take — and every other
representation (the compiled X3D geometry a browser renders, the JSON
payloads that move between Composer and the backend, the in-memory
Python objects a running server holds) is a *derivation* of that XML,
not a second source of truth living alongside it.

That bet pays off in a specific, concrete way: it means the complete
state of the system, at any point, is something a person can open in a
text editor and read. Not reverse-engineer from a database dump, not
decode from a binary format, not reconstruct from server logs — read.
For a project meant to be legible, inspectable, and eventually handed
to other people to build on, that property is worth protecting
deliberately, not something that falls out for free.

An XSD is how that protection gets written down. It is not primarily a
validation tool here — though it is that too — it is a **formal
statement of the contract**, in a notation designed for exactly this
purpose, that says: this is the complete, authoritative shape of an
MCCF document. Every other representation is allowed to be a lossy or
reshaped view of this one; this one is not allowed to quietly drift
from what the schema says it is.

## What an XSD does *not* buy you — stated honestly

It's worth being precise about the limits, because the failure this
project actually hit today illustrates them exactly.

**An XSD validates document shape, not code correctness.** Today's real
bug — a character's portrait vanishing on every reload — involved
seven separate places in one Python file that each independently
represent a `CultivarDefinition`: the dataclass, `to_dict()`,
`to_xml()`, `from_xml()`, `from_dict()`, the POST handler, and the
bulk-list GET response. Six of the seven correctly carried the
`portrait` field. The seventh — the bulk GET, the one Character
Creator's own list actually calls — simply didn't. Every document that
seventh function ever produced was perfectly schema-valid XML (missing
optional fields validate fine); the bug was in Python code, not XML
shape, and no XSD would have caught it.

**An XSD validates one document at a time, not identity collisions
across documents.** The same session found a second real bug: two
files, `cultivar_anna.xml` and `cultivar_AnnaOld.xml`, each internally
declared `name="Anna"`. Both were individually, perfectly valid
`CultivarDefinition` documents. The problem was that the *registry*
loading both of them keys by that name attribute, and processes files
in alphabetical order — so the stale file silently overwrote the
correct one, every single server restart, with no error anywhere. XSD
validates a document against a schema; it has no native concept of "no
two documents in this directory may share this attribute value." That
kind of cross-document identity constraint needs to live in the loader
itself (a "duplicate name → hard error, not silent overwrite" check),
not in the schema.

Both of today's bugs are documented directly in the XSD annotations
where they're structurally relevant — `mccf.xsd`'s `@name`
documentation states the collision risk explicitly, and its `Portrait`
element documentation states the seven-representations risk — not as
retrospective color commentary, but because a future person reading
this schema to build a new integration should hit that warning before
they rediscover the bug the hard way.

## What an XSD *does* buy you

- **A parameterizable authoring surface.** Several mature XML editors
  (oXygen, XMLSpy, and others) load an XSD and use it to drive their
  UI — autocomplete for element/attribute names, inline documentation
  from the `xs:annotation` blocks, structural validation as you type.
  Point one of these at `mccf.xsd` and a scene file becomes
  editable by someone who has never seen `_doExportSceneXML()`'s
  source, guided entirely by the schema's own documentation.
- **A stable target for future XSL.** Transforming MCCF documents into
  other formats — a different game engine's scene format, a
  documentation report, an alternate character-sheet representation —
  is far more tractable against a formally described source shape than
  against "whatever the current JavaScript serializer happens to
  produce this week."
- **A version-pinned contract, alongside a user's guide and systems
  manual, not instead of them.** Code changes; the schema is the
  artifact that says, as of this version, here is the actual shape of
  the data — checked in, dated, diffable against the previous version
  when the format changes.
- **A single place that names known gaps and rough edges honestly.**
  Several are called out directly in these three files rather than
  smoothed over: the `RecordedPaths` element's real per-path shape
  (owned by `path-recorder.js`, not yet gathered); the `EventCues/Cue`
  element's track-dependent attribute set, which XSD 1.0 can't express
  as a true conditional constraint without either duplicating the
  whole type per track value or reaching for XSD 1.1's `xs:assert` /
  a Schematron pass on top; the `EmotionalArc` element name being
  reused, unrelatedly, across all three schemas plus one deprecated
  legacy format — four different meanings for one string, now written
  down in one place instead of four separate points of confusion.

## The naming collision — resolved, not just documented

The original three-file split (v1.0) could only *footnote* this
collision, since XSD has no native way to say "these two things named
the same are actually different" within separately-namespaced files. A
true single-file combination changes that: XSD requires every global
element in one namespace to have a unique name, so merging the three
schemas into `http://mccf.artistinprocess.com/v1` forced an actual
resolution rather than another footnote.

| Document | Root element | Meaning |
|---|---|---|
| `mccf.xsd`: CultivarDefinition | `CultivarDefinition` | A character's full constitutional data |
| Legacy cultivar format (deprecated, unnamespaced, read-only, **outside this schema**) | `EmotionalArc` (nested `Cultivar`) | The *old* shape of the same character data — predates namespacing entirely |
| `mccf.xsd`: Scene | `Scene`, containing child `AgentPlacement` elements | **Renamed** from `EmotionalArc` as part of this consolidation — one placed agent's starting position, nothing more |
| `mccf.xsd`: EmotionalArc | `EmotionalArc` | A recorded take's ordered waypoint/beat sequence, plus its resolved PRNG seed |

The take-recording root element keeps the name `EmotionalArc` — it's
the more established usage, and renaming it would mean changing a live
backend endpoint's actual wire format (`mccf_api.py`'s
`arc_export_save`) for a purely cosmetic gain. Scene Composer's
per-agent placement stub is renamed to `AgentPlacement`, its actual
meaning.

**This is a real, not-yet-landed change to the writer code.**
`_doExportSceneXML()` and its load counterpart in
`mccf_scene_composer.html` still emit/read the literal string
`EmotionalArc` for this element as of this schema version. The schema
now states the target shape; the code hasn't caught up to it yet. Any
validation run against a live-exported Scene document will fail on
this one element until that update lands — worth knowing before
assuming a validation failure means the schema is wrong.

The old, deprecated cultivar format's own `EmotionalArc` root remains
completely outside this schema's scope by design — it predates
namespacing, nothing in the live system writes it anymore, and it's a
migration candidate, not a fourth thing to keep in sync.

## Coverage and known gaps, honestly

**Fully covered, validated against real sample documents:**
`CultivarDefinition` (current schema), Composer's `Scene` save/load
format — including the `Dialogue` block, closed out below — and the
`/arc/export` waypoint recording format.

**Resolved gap (Sept 2026):** `Scene`'s `Dialogue` element. The
original three-file schema left this as a stated, honest gap — the
Dialogue Editor's own serializer used a different escaping convention
than the rest of the file, and its exact shape hadn't been traced yet.
Direct code trace confirmed it's real, complete, working code: a
*second*, separate dialogue mechanism from `Waypoint`'s own
Question/Response/Statement children (the original design, still
live), with its own trigger vocabulary, TTS tagging, and audio-file
linkage. Both mechanisms coexist in the same document. Now fully
schematized (`DialogueType`/`DialogueEditorLineType`) and validated
against a real sample. Worth noting as the audit process actually
working as intended — a documented gap got closed by tracing real
code rather than either guessing at a shape or leaving the gap
indefinitely.

One real behavioral caveat carried into the schema's own
documentation, not just noted here: the Dialogue Editor's lines only
make it into `_lastDialogueLines` (the writer's source) via an
explicit "Save to Composer" action or a scene reload — author dialogue
in that tab, export without saving to Composer first, and the
`Dialogue` element is written empty with no error. An absent or empty
`Dialogue` element is therefore not reliable evidence a scene has no
dialogue, only that this particular export doesn't record any.

**Explicitly out of scope, by design:** the compiled X3D geometry
output. That document is real, standard X3D — the Web3D/ISO schema
already governs its shape, plus this project's own EXTERNPROTOs. An
MCCF-authored XSD has no business redefining a standard that already
exists; if the EXTERNPROTO interfaces themselves ever need formal
documentation, that's a narrower, separate artifact (an X3D
ProtoInterface listing, not a general XSD).

**Known gap, not yet gathered:** `RecordedPaths`' actual per-path
element shape, owned by `path-recorder.js`. The `RecordedPaths`
wrapper element is schematized; its `RecordedPath` children are
currently `xs:anyType` placeholders. Next fragment-gathering pass
should pull that module's serializer the same way today's pass pulled
Composer's and the cultivar backend's.

**Known looseness, stated rather than hidden:** `mccf.xsd`'s
`Cue` type declares the full union of every track type's possible
attributes as optional, rather than true per-track constraints (XSD
1.0's `xs:choice`-per-enumeration-value would require duplicating the
shared attributes across ten near-identical branches). A
`track="camera"` cue carrying `degrees`/`invert` (turn-only attributes)
would validate against this schema even though the Loader ignores the
nonsensical combination. Tightening this correctly needs either XSD
1.1's `xs:assert` or a Schematron layer on top — noted as real,
scoped follow-on work.

## Where these files live

```
mccf.xsd                    — combined schema, single namespace,
                               three root elements (CultivarDefinition,
                               Scene, EmotionalArc)
samples/
  sample_cultivar_v1.xml    — validates against mccf.xsd
  sample_scene_v1.xml       — validates against mccf.xsd
                               (uses the new AgentPlacement name —
                               see the naming-collision section above
                               for why current writer code doesn't
                               emit this yet)
  sample_arc_v1.xml         — validates against mccf.xsd
```

All three sample documents validate against the SAME schema object —
that's the actual point of combining into one file, confirmed with a
real XML Schema processor (lxml/libxml2), not just asserted. A single
`xsi:schemaLocation` reference or a single load in an XML editor now
covers every MCCF-invented document type at once.

The original three-file split (`mccf_cultivar.xsd`, `mccf_scene.xsd`,
`mccf_arc.xsd`, each with its own namespace) is superseded by this
combined file and not needed going forward, though nothing about the
older files was wrong — namespace-per-document-type is a legitimate,
common XSD pattern too, just not what best fits "one schema an editor
loads once."
