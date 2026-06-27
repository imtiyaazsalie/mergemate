# Managing email notifications

GitHub doesn't let you mute notifications from a single user. If MergeMate's PR comments are filling your inbox, here are your options.

---

## Turn off PR comment notifications

The simplest fix — disable comment notifications for the repo:

![GitHub notification settings](https://mergemate.ai/images/mergemate/notifications.png){width=512}

---

## Filter in your mail client

Create a rule that archives or labels emails from the MergeMate bot. [Gmail instructions →](https://www.quora.com/How-can-you-filter-emails-for-specific-people-in-Gmail#:~:text=On%20the%20Filters%20and%20Blocked,the%20body%20of%20the%20email)

![Mail filter](https://mergemate.ai/images/mergemate/filter_mail_notifications.png){width=512}

---

## Trim the comment size

MergeMate includes a collapsible help section at the bottom of each comment. Turn it off per-tool:

```toml
[pr_reviewer]
enable_help_text = false
```

Smaller comments → shorter notification emails. Repeat for any tool where you want to strip the help block.
