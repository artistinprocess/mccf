# For Kate — how Anna, Cindy, and everyone else "feel" things, and where we're taking it

You've been in the room for the character design (Cindy's whole
brief, the archer-versus-bartender split, all of it), so this is the
part that happens after your work — how a character's emotional state
actually gets computed and carried through a scene. No code, just the
shape of it.

## The four numbers

Every character is tracked on four channels, shorthanded **E/B/P/S**:

- **E — Emotional.** Affective intensity, warmth, how much is felt.
- **B — Behavioral.** How consistent the character's actions are with
  what they'd say about themselves.
- **P — Predictive.** How well the character seems to be reading the
  situation — anticipating what's coming, versus caught off guard.
- **S — Social.** How attuned the character is to whoever they're with.

Every line of dialogue, every scene beat, nudges these four numbers.
That's the whole engine underneath the "emotional field" — not a
script writing feelings, a live system computing them.

## Two very different things share the same four letters

This is the part worth being precise about, because we found real
confusion here this week.

**A cultivar is a template.** It's how a character gets *designed* —
Anna's baseline E/B/P/S, Cindy's, anyone's. A cultivar has no history.
You can test the same cultivar over and over, the way we tested "does
this character's emotional state return to baseline after a stressful
exchange" months ago, using a fixed set of seven scripted questions.
That test worked — the subject character genuinely settled back down
after pressure, which is the whole point of "constitutional" design:
the character has a stable core, not just a starting mood.

**A character is the opposite of a template — it's pure accumulated
history.** Once Anna is actually in a scene, her E/B/P/S evolves from
what's actually happened to her: what was said, what pressure she was
under, what happened in the scene before this one. That state is
supposed to be hers alone, carried forward, not reset by every new
scene starting fresh from the template.

We found this week that the system wasn't actually keeping those two
things apart — testing a cultivar and playing a character with the
same name could, in principle, write into the same slot, so a test run
could leave residue a real scene would silently inherit. That's fixed
now — testing and playing are structurally separate, not just "please
remember not to mix these up."

## A real bug, now fixed

Separately: there was a genuine miscalculation in how a character's
*current* emotional state got computed right after each new beat of a
scene — it was landing at roughly double what it should have been,
for every character, regardless of how emotionally "regulated" they
were designed to be. Practically: a character meant to hold themselves
together under pressure wasn't actually being protected by that design
the way it was supposed to work. That's corrected — verified against
the original written spec for how this was meant to behave, not just
patched and hoped.

## Where this is going: scenes aren't always in a line

Here's the part I think you'll find genuinely interesting, given how
much of the story lives in flashback and non-linear reveal (Aislyn,
the changeling ancestry, all of it).

Right now, everything runs one scene at a time. The next piece of
architecture — not built yet, deliberately deferred until the
animation pipeline (the facial displacers, the gesture system) is
fully solid — is a **Series Editor**: a tool where an author chooses
scene files and explicitly sets how they connect. Ordered ("this
follows that"), unordered ("these have no defined relationship"), or
**flashback** — a scene that reaches back to an *earlier* point in a
character's history, regardless of when it's actually being written
or rendered.

The reason this needs real design rather than "just play scenes in
order": Cindy's emotional state during a flashback to her time alone
with the bear has to reflect who she was *then*, not whatever she's
become by the time that flashback gets written into the story. A
naive system that just carries forward "whatever happened most
recently" gets flashbacks wrong by construction. The plan is a system
where each scene's ending state is a saved checkpoint, and every scene
declares — the author declares, explicitly, every time — which
checkpoint it continues from. That's exactly how the story already
wants to be told; the tool just needs to catch up to it.

If any of this raises questions — especially anything about how a
character's emotional continuity should or shouldn't survive into a
flashback, since that's as much a story decision as a technical one —
I'd genuinely like to hear them. This is exactly the kind of thing
where the person who understands the characters should have more say
than the system architecture does.
