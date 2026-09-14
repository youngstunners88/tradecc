---
name: verified-correction
description: How to prove a fix actually fires, and how to correct a claim you already made. Use after fixing any bug, before reporting that something is verified or passing, when a verification result looks clean, and whenever you notice an earlier statement of yours was wrong. Guards against the failure where the checking apparatus is broken and reports success.
---

# Verified Correction

Most of the defects in `failure-modes` were found. The ones that got expensive
were the ones **reported as fixed when they were not**, or **reported as
verified by something that had not run**. This skill is about the second layer:
the reliability of the checking, and the honesty of the report.

---

## 1. A fix is not verified until you have seen the test fail without it

Writing a test alongside a fix proves the test passes. It does not prove the
test *detects the bug* — a test asserting the wrong thing passes both before
and after.

**The procedure, every time:**

```bash
cp src/thing.py /tmp/thing.bak
# revert ONLY the fix
<edit>
.venv/bin/python -m pytest -q 2>&1 | grep -E "^FAILED"   # must list your new tests
cp /tmp/thing.bak src/thing.py
.venv/bin/python -m pytest -q 2>&1 | tail -1             # must be green again
```

Report the count: *"reverting the price derivation fails 4 of the new tests and
6 suite-wide."* A fix described without that number has not been verified, it
has been asserted.

### A test that cannot fail

This shipped here: a test asserted a key-shaped value was absent from
`subject + body` — a field it had never been written to. It passed with
redaction on and with redaction off. Disabling the control is what exposed it.

If disabling the control does **not** fail your new test, the test is the bug.

---

## 2. An implausibly clean result is a broken harness until proven otherwise

Twice on this project a verification script reported **"0 failed"** across six
separate disabled controls. Both times the correct answer was 4, 1, 1, 2, 2 —
the script itself was broken (a nested heredoc in a shell function never
expanded, so nothing was ever patched) and it reported success.

> **A checking apparatus that reports perfection is more likely broken than
> the code is perfect.**

**Detection recipe — before trusting any verification run:**

1. **Make it fail on purpose first.** Break something you know is covered. If
   the harness stays green, it is not running.
2. **Predict the number, then compare.** "Disabling the fingerprint check
   should fail ~4 tests." Zero against a prediction of four is a harness bug,
   not good news.
3. **Never accept a summary line you did not see produced.** Collection can
   abort and still print something that scans as clean. Check for `ERROR`
   and `INTERNALERROR`, not just `failed`.
4. **Prefer explicit repetition to clever automation.** Six copy-pasted runs
   that obviously work beat one elegant loop that silently does not. The loop
   is the thing that broke, twice.

---

## 3. Correcting your own earlier claim

Three things went wrong here that were reports, not code:

- **A verdict delivered before the evidence was in.** A model was described as
  having "contributed nothing" while it was still mid-reasoning; it went on to
  find a real bug the local pass had missed.
- **A claim of "purely additive"** about a test helper that in fact collided
  with an existing subclass attribute.
- **A commit message stating the wrong test count** (six/392 when it was
  eight/394).

**The rule:** correct anything that changes what someone would do or believe —
plainly, once, in the same place the claim was made. Amend the commit, edit the
PR body, say it in the next message. Then continue.

Do **not** pad the correction with apology, re-litigation, or a tally of past
mistakes. The correction is information; the performance around it is noise.
For a slip that changes nothing — a typo, a mislabeled variable in prose — just
fix it and move on.

**Stale artefacts are uncorrected claims.** A PR description that no longer
matches its diff is a false statement with a URL. Refresh it when the branch
moves; this has needed doing more than once.

---

## 4. Destructive commands on unverified state

`git checkout src/cli.py` — intended to clean up a probe — destroyed an entire
unstaged command. Four tests caught it; nothing else would have.

Before any command that discards work (`checkout --`, `reset --hard`,
`stash drop`, `rm`), state what is in the working tree and what you are about
to lose. `git status --short` first, every time. On a money-path repo the cost
of a five-second check is nothing against the cost of silently reverting a
safety control.

---

## 5. What "done" means

Before saying a task is complete:

- [ ] The full suite passes, and you ran it after the last edit
- [ ] Each new control was disabled and the failures counted
- [ ] The fake was fixed in the same commit as the real thing (`failure-modes`, Shape E)
- [ ] Numbers in the commit message and PR body match the run you actually did
- [ ] Anything you could not finish is named explicitly, not omitted

If part is blocked, say which part and why. Scaling the work down is the user's
call, and an unreported gap is indistinguishable from a lie once it ships.
