"""The one place a human authorises spending.

This module is small on purpose. It is the entire non-interactive-create
defence, and it is the only code in `oneground.pod` that reads stdin.

`ask_to_create()` returns a `CreateAuthorization` -- a value that cannot be
constructed by accident from a flag or a config file -- which is the only
thing `api.RunPodClient.allow_create()` accepts. So the chain from a typed
keystroke to a billable HTTP request is one function long and can be read in
full on one screen.

Refusal conditions, all of them before anything is created:

    stdin is not a TTY     a pipe, a CI runner, an agent harness, `< /dev/null`
    the answer is not 'y'  "yes", "Y", "" and everything else are refusals,
                           because a prompt that accepts several spellings of
                           consent is a prompt people learn to dismiss
    the cap is missing     a session with no max_usd/max_hours cannot be
                           confirmed; there would be nothing to confirm *to*
"""

import sys
import time


class ConfirmationRefused(RuntimeError):
    """The developer did not confirm, or could not be asked."""


class CreateAuthorization:
    """Proof that a human typed 'y' to a specific, priced plan.

    Carries what was actually shown, so the deploy path can assert it is
    creating the thing that was agreed to rather than something re-resolved a
    moment later at a different price.
    """

    __slots__ = ("session_name", "usd_per_hr", "max_hours", "max_usd",
                 "granted_at", "_used")

    def __init__(self, session_name, usd_per_hr, max_hours, max_usd):
        self.session_name = session_name
        self.usd_per_hr = usd_per_hr
        self.max_hours = max_hours
        self.max_usd = max_usd
        self.granted_at = time.time()
        self._used = False

    def check_valid(self):
        """A confirmation is good for one creation, soon after it was given.

        Ten minutes: long enough for an image pull decision, short enough that
        a 'y' typed before lunch cannot deploy after it.
        """
        age = time.time() - self.granted_at
        if age > 600:
            raise ConfirmationRefused(
                "this confirmation is %.0f minutes old; confirm again"
                % (age / 60.0))
        return True

    def consume(self):
        if self._used:
            raise ConfirmationRefused(
                "this confirmation has already created a pod; one 'y' is one "
                "pod")
        self._used = True
        return self

    def __repr__(self):
        return ("CreateAuthorization(%s, $%.2f/hr, cap %sh/$%.2f)"
                % (self.session_name, self.usd_per_hr, self.max_hours,
                   self.max_usd))


def stdin_is_interactive(stream=None):
    s = stream if stream is not None else sys.stdin
    try:
        return bool(s.isatty())
    except Exception:
        return False


def ask_to_create(session_name, usd_per_hr, max_hours, max_usd,
                  stream=None, out=None, usd_min=None):
    """Prompt the developer. Return a CreateAuthorization, or raise.

    `usd_per_hr` is the **top** of the live price range, and it is what the
    authorization is granted against. `usd_min` is shown for context only.

    Task 006b prompted with the bottom of the range -- $0.34/hr -- and the pod
    billed $0.72/hr. The prompt now states the worst case first, because that
    is the number the developer is actually agreeing to be liable for, and
    quotes the range so the spread is visible rather than hidden.
    """
    stream = sys.stdin if stream is None else stream
    out = sys.stdout if out is None else out

    if max_hours is None or max_usd is None:
        raise ConfirmationRefused(
            "session '%s' declares no caps.max_hours / caps.max_usd; there is "
            "nothing to confirm to. Add caps to the session spec."
            % session_name)

    if usd_per_hr is None:
        raise ConfirmationRefused(
            "session '%s' has no worst-case price (couldn't-check), so there "
            "is no number to confirm against. `up` refuses rather than "
            "falling back to the datacenter floor." % session_name)

    if not stdin_is_interactive(stream):
        raise ConfirmationRefused(
            "stdin is not a terminal, so no one can be asked. `up` has no "
            "non-interactive path and no --yes flag: creating a billable "
            "resource requires a person at a keyboard. Run it in a terminal, "
            "or use `plan` for the dry run.")

    rng = ("" if usd_min is None or usd_min >= usd_per_hr
           else " (range $%.2f-$%.2f)" % (usd_min, usd_per_hr))
    prompt = ("Create this pod at up to $%.2f/hr%s with a hard cap of %g "
              "hours = up to $%.2f? [y/N] "
              % (usd_per_hr, rng, max_hours, usd_per_hr * max_hours))
    out.write("\n" + prompt)
    out.flush()
    answer = stream.readline()
    if answer is None:
        raise ConfirmationRefused("no answer on stdin")
    # Only the line terminator is stripped, not surrounding whitespace: " y "
    # is not the same keystroke as "y", and a prompt that quietly normalises
    # what it was given is a prompt that can be satisfied by something other
    # than a person deliberately typing one letter.
    answer = answer.rstrip("\r\n")

    if answer != "y":
        raise ConfirmationRefused(
            "answer was %r; only a bare 'y' proceeds. Nothing was created."
            % answer)

    return CreateAuthorization(session_name, usd_per_hr, max_hours, max_usd)
