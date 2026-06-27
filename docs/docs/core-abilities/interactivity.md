# Interactivity

`Supported on: GitHub, GitLab`

MergeMate turns static code review into a conversation. Instead of copying suggestions into your editor and manually tracking what's been addressed, you drive the review directly from PR comments with simple checkboxes.

## How It Works

Every interactive action lives inside the PR — no context switching, no separate dashboards. Click a checkbox and MergeMate responds in-place.

### `/improve` — Interactive Suggestions

The [`/improve`](../tools/improve.md) command delivers a fully interactive experience:

- **Apply this suggestion** — one click turns a recommendation into a committable code change. Once committed, the suggestion is marked with a check so you can see what's been done at a glance.

- **More** — asks MergeMate to generate additional suggestions beyond the initial batch, keeping each one as focused as the originals.

- **Update** — triggers a fresh analysis against the latest code, giving you updated suggestions after you've made changes.

- **Author self-review** — developers can acknowledge they've reviewed collapsed suggestions, giving the team visibility into what's been seen.

### `/help` — An Interactive Command Palette

The [`/help`](../tools/help.md) command lists every available tool — but it's more than a reference page. Each tool has a checkbox next to it. Tick one and MergeMate fires that tool immediately, right in the PR thread. It's a help menu that doubles as a launcher, keeping your entire workflow inside the pull request.
