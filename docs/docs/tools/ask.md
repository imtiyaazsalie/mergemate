# Ask

**Answers free-text questions about the PR diff — about the whole PR, specific lines, or even screenshots.**

```
/ask "Why was the retry logic moved out of the transaction block?"
```

MergeMate reads the code changes and responds inline. Each question is stateless — it doesn't remember earlier queries.

![Ask](https://mergemate.ai/images/mergemate/ask.png){width=512}

## Asking about specific lines

From the PR diff view, select one or more lines (click the `+` next to the line number, then drag), type your question, and post:

```
/ask "Is this null check redundant given the guard above?"
```

![Ask Line](https://mergemate.ai/images/mergemate/Ask_line.png){width=512}

The tool sees only the selected lines plus surrounding file context.

## Asking about images

Attach an image and the full PR diff acts as context:

```
/ask "Does this wireframe match the API contract in the changes?"

[Image](https://example.com/wireframe.png)
```

To get a direct image URL on GitHub:

1. Post a comment containing **only** the pasted image.
2. Quote-reply to that comment.
3. Type your `/ask` question above or below the image link.
4. Post — MergeMate uses both the image and the diff.

## Tips

- **Be specific.** "Why is the cache TTL set to 300?" works better than "Is this okay?"
- **Ask per-file or per-function** to keep responses focused.
- **Images work best with concrete questions** — architectural feedback may need the full codebase beyond the diff.
