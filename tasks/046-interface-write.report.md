# Task 046 — the interface write slice

*In progress. Sections are written as they are settled rather than at the
end, because a claim written three days after the measurement is a
recollection.*

## The guard did not move when the comments arrived

The write guard's identity is

    parse(write(D)) == D

over the **parsed document**, not over the bytes. That was settled in step 1,
before `render` wrote a single comment, and of everything decided in this
slice it was the ruling most likely to have been wrong. A guard over bytes is
the obvious thing to reach for: it is stricter, it is easier to explain, and
it catches more. Choosing the weaker-looking identity was an argument — that
a file's meaning is what it parses to, and that anything a parser discards is
presentation, so a byte guard would be checking the writer's layout rather
than the document's content.

Step 2 is the experiment that argument was making a prediction about. It put
an explanation above **every field in every file this tool writes**, a
preamble at the top, and wrapping that depends on indentation depth. Under a
byte identity, every one of those is a change to what the guard compares.

**Nothing in the guard moved.** Not the identity, not `check_write_path`, not
`write_violations`, not one line of the round-trip tests — which passed
unmodified against a writer whose output had grown by a comment per field.

That is the identity having been drawn in the right place, **proved rather
than argued**. It is the difference between a design decision with a good
reason behind it and one with evidence behind it, and it is worth saying
plainly because the reason and the evidence are not the same claim: the
reason predicted that comments would not disturb the guard, and step 2 is
what turned the prediction into a result. Had the guard needed a single
exemption to accommodate comments, the byte identity would have been the
right one all along and the argument would have been a rationalisation.

The general form, for whichever guard comes next: **an identity is in the
right place when the first thing built on top of it does not touch it.** Not
when it is well argued — when something new arrives and it stays still.
