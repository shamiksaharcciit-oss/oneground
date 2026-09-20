# INTERFACE.md, addition — the front door

*To be merged into `docs/INTERFACE.md` — it replaces §4.1 and closes the
first item of §7. Ruled 20 September 2026.*

---

## Why this addition exists

§7 left one thing open: *the front door for a user with documents and no
vectors — the moment before `chunk`, which is a form nobody has
designed.* The end-to-end story now runs from documents to a checkable
decision, and the only step with no design was the first one.

§4.1 said the UI writes `requirements.yaml` and left the how unstated.
This settles it.

## 1. Three paths in, one artifact out

All three end at the same file, and that is the property worth keeping:
the YAML remains the thing that runs and the thing someone else can
reproduce from.

**Fill in the form.** Each field explained beside it, validated as it is
typed by the CLI's own validator — so the form refuses exactly what the
command refuses, with the same message. The file is shown live as it is
edited. Saving writes it.

**Upload one you have.** Validated on arrival, with any error named
against the field it belongs to rather than as a parse failure, and then
editable in the same form. A user arriving with a file from a colleague,
a repository or an earlier run lands in the same place as a user starting
empty.

**Download a template.** For someone who wants the file in their
repository, in CI, or reviewed before anyone touches the tool. See §2 —
it is not a blank form.

**Why the form is primary and the template is the fallback.** A template
downloaded, edited in a text editor without validation, and uploaded is
the command-line experience with extra steps: the user finds out what was
wrong from a refusal rather than while typing. The template exists for
people who want a file under review, not as the ordinary way in.

## 2. The file explains itself

The form writes its reasoning into the file as comments. Not field names
restated — the *why*, in the words the form used beside each field:

```yaml
corpus:
  sample:
    # Ten to twenty thousand vectors, not your whole corpus. The exact
    # answer key is computed by brute force over this sample, which is
    # what makes it cheap; at full scale it would not be.
    vectors: ./data/sample.npy
    queries: ./data/queries.npy    # 50+ or the ambiguity measure
                                   # cannot be computed
  # Your real corpus size. Used for capacity arithmetic and for the
  # caveat printed on every result: a sample does not tell you how the
  # whole corpus behaves.
  size_now: 2_100_000

constraints:
  # Measured at this concurrency, in the same environment, for the
  # configuration the engine was actually built with. Anything else is
  # reported couldn't-check rather than guessed.
  latency_p95: {ms: 40, at_qps: 200, concurrency: 32}
```

Three consequences:

- **The downloaded template is the tool explaining itself** in a file the
  user keeps, rather than a blank form they must look up.
- **A file that leaves the tool carries its own reasoning**, so a
  colleague reading it in a pull request learns the schema from the
  artifact.
- **The comments are generated from the same strings the form shows**,
  so they cannot drift from the interface. A test asserts that every
  field with an explanation in the form has it in the written file, and
  that the two are the same string.

Comments are not read back as data. A user editing them by hand changes
nothing about the run, and re-saving through the form rewrites them from
the current strings — stated in the file itself, once, at the top.

## 3. What does not change

The file is the artifact. The UI writes it and never replaces it. The
form's validation is the CLI's validation, not a second implementation —
if the two could disagree, the front door would be the first place the
UI drifted from the tool it is a front-end to.

## Acceptance, added to the interface brief for slice 2

- All three paths produce the same file for the same inputs, tested.
- An uploaded file with an error names the field, not a parse position.
- The written file carries the form's own explanations as comments, and
  a test asserts form string and file comment are one string.
- Comments are never read back as data, and the file says so.
- The form refuses what the CLI refuses, with the CLI's message.
