# Annotation, Increment 1 (DRAFT, 2026-11-10)
Lexicon v2 + annotation record, validation and a deterministic lookup annotator. Not wired into V5. Writes nothing to EBPS.
- mccf_lexicon_v2.xsd / .sch : Lexicon v2 structure and rules L01-L17
- mccf_annotation.xsd / .sch : Annotation record (V6 trace namespace) and rules A01-A11
- mccf_annotate.py LEXICON SCENE OUT : one `expression` annotation per dialogue Line, with Evidence for every hit; negation is recorded as a Cue and not applied
- fixtures/lexicon_fixture_DRAFT.xml : placeholder dimensions and terms so the tooling can be tested. Kate owns the real content.
- tests/test_annotation.py : run `python3 -I tests/test_annotation.py` (set MCCF_TEST_SCENE to a scene to also run it on a real scene)
Notes: no timestamp in lexicon-annotator output (keeps replays byte-identical; `sequence` orders records). Schematron fires one rule per node per pattern, so rules that must both apply sit in separate patterns.

## Render helper (render/, DRAFT)
Offline preparation and checking for ElevenLabs renders; it never calls ElevenLabs and never edits a scene in place.
`mccf_render.py manifest | adopt | record | propose | apply | verify` (see the file's docstring). Fill in render/voices_DRAFT.json (voice and model per actor; part of the render hash). tag_mapping_DRAFT.json is the author's table from lexicon terms and EBPS values to delivery tags. Tests: `python3 -I tests/test_render.py`.
