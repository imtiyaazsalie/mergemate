# Dynamic Context

`Supported on: GitHub, GitLab, Bitbucket`

MergeMate uses an **asymmetric, dynamic context strategy** to help models understand code changes without drowning them in irrelevant lines. The idea is simple: more context *before* a change than after it, and expand up to the enclosing code structure when it helps.

## The Problem with Unified Diffs

Pull request diffs come in a standard unified format — three lines of context above and below each change, with `+` marking additions and `-` marking deletions:

```diff
@@ -12,5 +12,5 @@ def func1():
 code line that already existed...
 code line that already existed...
 code line that already existed...
-code line that was removed in the PR
+new code line added in the PR
 code line that already existed...
 code line that already existed...
 code line that already existed...
```

This format is tough for AI models. The `+`/`-`/` ` prefix convention doesn't match the plain code formatting models were trained on, and three lines of surrounding context is often not enough to understand *why* a change was made.

## The Context Trade-off

Expanding the context window sounds like an obvious win, but it's not free:

**Upsides:**
- More context means the model can better localise changes and produce sharper analysis.

**Downsides:**
- Too much context creates a "needle in a haystack" problem — the model struggles to focus on what actually changed. LLM output quality is known to degrade as context windows grow.
- More tokens equals more latency and higher cost. Large PRs can easily exceed single-pass limits.

## The Solution: Asymmetric + Dynamic

**Asymmetric:**

Context *before* a change is usually more valuable than context *after* it. MergeMate splits the context window into two independently adjustable segments — one for code that precedes the change, one for what follows. This lets MergeMate allocate more tokens where they'll actually help.

**Dynamic:**

Fixed line counts are a blunt instrument. The optimal context for a change is often its enclosing code component — the function, method, or class that contains it. MergeMate dynamically expands the context window until it hits an enclosing structure, rather than stopping at an arbitrary line count.

To keep things bounded, there's a hard limit on how many lines are searched when looking for the enclosing component. This keeps the strategy efficient without letting context balloon.

## Relevant Config

```toml
[config]
patch_extension_skip_types = [".md", ".txt"]   # Skip these extensions when expanding context
allow_dynamic_context = true                     # Enable dynamic context extension
max_extra_lines_before_dynamic_context = 8      # Max lines to search backwards for an enclosing function/class
patch_extra_lines_before = 3                     # Extra lines (on top of the default 3) before each hunk
patch_extra_lines_after = 1                      # Extra lines (on top of the default 3) after each hunk
```
