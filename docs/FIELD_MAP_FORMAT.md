# MCCF Field-Map Serialization Format v1

*Item 2 of the Day 72 build schedule. Implements design doc §4.1's manifest
shape as a concrete on-disk artifact. This doc is the grammar; `field-map.js`
is the reference implementation (serialize / parse / validate); the three
worked manifests from design doc §4.2 are the first real test fixtures.*

## Format decision

**Inline X3D metadata**, using the native `MetadataSet`/`MetadataString`
nodes, co-located inside each Actor type's `ProtoDeclare`/`ProtoInterface` —
not a separate JSON sidecar file.

Reasoning, per the criterion the build schedule set for this decision
("does the manifest need to survive being opened in a plain X3D viewer with
no MCCF tooling?"): yes — a scene author using Kamala/Vivaty-class tooling,
or any generic X3D editor, should be able to see what an Actor exposes
without MCCF's pipeline present, consistent with this project's stated
respect for tooling that still runs on its own. No blocker to inline
metadata turned up in implementing this, so the schedule's default holds.

A JSON sidecar was the alternative; it's simpler to parse but detaches the
manifest from the proto it describes, and risks drifting out of sync if the
two files are edited independently. Not chosen.

## Grammar

```
<MetadataSet name='fieldMap' DEF='FieldMap_<ActorType>'>
  <MetadataString name='actorType' value='"<ActorType>"'/>

  <!-- zero or more field entries; zero entries is legal (§4.1) -->
  <MetadataSet name='field:<fieldName>'>
    <MetadataString name='reach' value='"track-only" | "affect-writable" | "telemetry"'/>

    <!-- required IFF reach == "affect-writable"; absent otherwise -->
    <MetadataString name='channel' value='"<channel>"'/>
    <MetadataString name='curve' value='"direct" | "inverse" | "custom"'/>
    <MetadataString name='arbitration' value='"replace" | "blend" | "track-wins"'/>

    <!-- optional for any reach; omit entirely for range: n/a -->
    <MetadataString name='range' value='"<min> – <max>"'/>
  </MetadataSet>
</MetadataSet>
```

Placement: as a child of the Actor type's `ProtoInterface`, e.g.:

```xml
<ProtoDeclare name='Avatar'>
  <ProtoInterface>
    ...
    <MetadataSet containerField='metadata' name='fieldMap'>
      ...
    </MetadataSet>
  </ProtoInterface>
  <ProtoBody>...</ProtoBody>
</ProtoDeclare>
```

## Rules a validator enforces

1. **A `fieldMap` MetadataSet must be present.** An Actor type with no
   manifest at all is not legal to export (§4.1) — this is checked at the
   proto level, not the field level.
2. **Zero field entries is legal** — an explicit, honest "narrative-inert,
   tracks-only" declaration (§4.1). This is different from rule 1: the
   `fieldMap` node itself must exist even if it has no `field:*` children.
3. Every field entry must declare `reach`, and `reach` must be one of the
   three legal values.
4. `channel`, `curve`, and `arbitration` are **required together** when
   `reach == "affect-writable"`, and **forbidden** otherwise. This matches
   every worked example in design doc §4.2 without exception — no
   affect-writable field there is missing any of the three, and no
   track-only/telemetry field carries any of them.
5. `range` is always optional (some track-only/telemetry fields have no
   natural range, e.g. `dialogueText`, `hingeAngle` before a concrete unit is
   chosen) — its absence means "n/a," not an error.
6. Field names must be unique within one Actor type's manifest — this is the
   same identity discipline as build-schedule item 1, applied to field maps
   rather than scene entities. A duplicate `field:<name>` block is rejected
   at parse time, not silently last-write-wins.

## Round-trip contract

`parseFieldMap(serializeFieldMap(m))` must deep-equal `m` for any manifest
`m` that passes `validateFieldMap`. This is the acceptance test for this
format — see `test-field-map.js`.
