# FAQ

---

??? note "Does MergeMate replace human reviewers?"

    No — it works alongside them.

    Code review is essential but exhausting. Long PRs get short feedback. MergeMate fills the gaps: it catches oversights, suggests improvements, and gives reviewers a running start. But the final call always belongs to a person.

    A few safeguards built into the design:

    - Your original PR description always stays on top
    - MergeMate never approves a PR
    - Suggestions are optional and structured so you can scan them fast
    - The goal is to encourage self-review, not to automate it away

---

??? note "I got a suggestion that doesn't make sense. What gives?"

    AI models are powerful but not perfect. Even the best ones occasionally misfire.

    The real value isn't in blindly accepting every suggestion — it's in the moments where the model spots something you missed. Spending 30 seconds skimming suggestions is worth it when it catches a bug before production.

    **Quick filter technique:**
    1. Glance at the category header. If it's irrelevant, skip.
    2. Read the one-line summary. Still irrelevant? Skip.
    3. Expand only the suggestions that matter.

    Want better results? Use `extra_instructions` to steer the model toward what your project cares about. [Learn how →](../tools/improve.md#extra-instructions-and-best-practices)

---

??? note "Can I customize the suggestions I get?"

    Absolutely. The `extra_instructions` and `best_practices` knobs let you tune the output. [Details here →](../tools/improve.md#extra-instructions-and-best-practices)

---

??? note "Do you keep my code?"

    No storage. No training. No exceptions. See the [data privacy page](../overview/data_privacy.md) for the full breakdown.

---

??? note "Can MergeMate review draft PRs?"

    Yes — just trigger it manually with a comment (`/review`, `/describe`, etc.). Draft PRs won't trigger automatic runs unless you opt in. [More on automations →](../usage-guide/automations_and_usage.md#mergemate-automatic-feedback)

---

??? note "Can I calibrate the review effort estimates?"

    Yes. Use `extra_instructions` to map effort levels to your team's expectations. Example:

    - Effort 1 → under 30 minutes
    - Effort 2 → 30–60 minutes
    - Effort 3 → 60–90 minutes

    The scale (1–5) is meant for quick comparison between PRs, not exact timekeeping. [Configuration reference →](../tools/review.md#configuration-options)

---

??? note "MergeMate feels noisy. How do I dial it down?"

    The defaults are tuned for signal over noise, but every team has different tolerances. Here's what's already in place:

    - Structured, scannable output (not wall-of-text comments)
    - Suggestions grouped in tables, not inline commits
    - Verbose sections folded by default
    - No "I'm working on it…" placeholder messages

    If you still want less:

    - Raise the [score threshold for suggestions](../tools/improve.md#configuration-options)
    - Limit [which tools run automatically](../usage-guide/automations_and_usage.md#github-app-automatic-tools-when-a-new-pr-is-opened)
    - Use [`extra_instructions`](../tools/improve.md#extra-instructions) for laser-focused feedback

    Prefer *more* output? Flip the knobs the other way — [dual-publishing mode](../tools/improve.md#dual-publishing-mode) and [interactive usage](../core-abilities/interactivity.md) are good starting points.
