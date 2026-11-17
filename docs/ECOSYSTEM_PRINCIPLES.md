# MCCF ecosystem principles (draft for the V6 design notes)

DRAFT. Len Bullard's rules are quoted as he stated them. The checks at the end
are proposals.

## Rules

1. **The ten-year-old test.** If a ten year old can use it, it is well done work.
   If a poor-as-dirt ten year old can lay hands on it and work unmolested, it is a
   well done spiritual work.
2. **Ecosystem fitness.** "A system's fitness as an ecosystem member is measured
   by how easily and transparently it is improving other ecosystem members."
3. **Resilience through licensing.** An information ecosystem is as resilient as
   its licensing enables cross-fertilization, which is the engine of ecosystem
   evolution. Respectful but promiscuous: keep the credit, say what changed.
4. **Standards are law.** Human decisions govern the authoritative rules, written
   as regular text, diagrams and code. Regular structure (schemas, codes, fixed
   module shapes) keeps the system stable and lets people, programs and language
   models check one another's work.
5. **Open, with boundaries.** XML is human-facing and open with boundaries: scenes,
   lessons, schemas. The schema is as vital as it is used to construct and validate
   a human message. JSON is for objects and short messages, and is an excellent
   serialization. Authored artifacts are XML. Machine logs and fire-and-forget
   messages may be JSON Lines.
6. **Trajectory over query, pattern over indexing.** Work with a language model is
   a long conversation. Keep the thread regular (registers, codes, hand-off files)
   and tolerate latency to get a high quality answer.
7. **Least commitment.** Unknown stays unknown. Do not invent an interpretation.
8. **Show the clipping.** A system reports what was requested and what was applied,
   and the bound that made them differ, not only a tidy result.

## Test categories (kept separate)
- Component tests: a piece does what it says.
- Integration tests: pieces work together.
- Complete narrative-use tests: an author and an audience use the assembled system.
Independent trials report which of these they are.

## Proposed checks
- Time for an outsider to get a first scene running from the documentation.
- Defects found by outsiders, and how many fixes come back upstream.
- Whether another tool can read what MCCF writes, and MCCF can read what it writes
  (schemas, XML, MIDI, X3D, OpenAI-compatible model endpoints).
- Whether every default, port and budget can be changed without editing code.
