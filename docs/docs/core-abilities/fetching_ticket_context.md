# Fetching Ticket Context

`Supported on: GitHub, GitLab, Bitbucket`

!!! note "Branch-name detection: GitHub only (for now)"
    Extracting issue references from **branch names** (and the optional `branch_issue_regex` setting) is currently GitHub-only. GitLab, Bitbucket, and other platform support is on the roadmap. GitHub was the natural starting point; other providers will follow.

## What It Does

MergeMate pulls relevant ticket information directly into the review, giving the model the full picture of *why* a PR exists — not just *what* changed.

**Ticket systems supported:**

- GitHub Issues / GitLab Issues
- Jira (Cloud and Data Center/Server)

**What gets fetched:**

1. Ticket title
2. Description
3. Custom fields (e.g. acceptance criteria)
4. Subtasks
5. Labels
6. Attached images and screenshots

## How Tools Use Ticket Data

For the system to recognise a ticket:
- The PR description should link to the ticket, **or** the branch name should start with the ticket ID/number.
- For Jira, you'll need to configure authentication (see below).

### `/describe`

MergeMate uses the ticket title, description, and labels to enrich its understanding of the code changes. Knowing the intent behind a PR leads to more insightful analysis.

### `/review`

The review tool uses ticket content the same way, and goes one step further — it evaluates how well the PR actually fulfils the ticket's stated purpose. Each PR gets a compliance label:

- **Fully Compliant** — the PR covers everything the ticket asks for
- **Partially Compliant** — some requirements are addressed, some aren't
- **Not Compliant** — the PR doesn't match the ticket's intent
- **PR Code Verified** — the code looks right, but needs manual QA (e.g. UI testing across platforms)

![Ticket compliance review](https://www.mergemate.ai/images/mergemate/ticket_compliance_review.png){width=768}

#### Configuration

- Disable ticket compliance checking:

    ```toml
    [pr_reviewer]
    require_ticket_analysis_review = false
    ```

- Flag unrelated content in the PR:

    ```toml
    [pr_reviewer]
    check_pr_additional_content = true
    ```

    When enabled (default: `false`), the review tool checks for code that doesn't relate to the ticket. If found, the PR caps at `PR Code Verified` and MergeMate surfaces the extraneous content in a comment.

---

## GitHub / GitLab Issues

MergeMate automatically detects issue references in PR descriptions. Valid formats:

- `https://github.com/<ORG>/<REPO>/issues/<NUMBER>`
- `https://gitlab.com/<ORG>/<REPO>/-/issues/<NUMBER>`
- `#<NUMBER>`
- `<ORG>/<REPO>#<NUMBER>`

Branch names also work for issue linking on GitHub:

- `123-fix-bug` (where `123` is the issue number)

Because MergeMate is already authenticated with GitHub, no extra config is needed to fetch GitHub issues.

---

## Jira Integration

MergeMate supports Jira Cloud and Jira Server/Data Center.

### Jira Cloud (Email/Token)

1. Head to [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens) and create one.

2. Add it to your config:

    ```toml
    [jira]
    jira_api_token = "YOUR_API_TOKEN"
    jira_api_email = "YOUR_EMAIL"
    ```

### Jira Data Center/Server (Basic Auth)

Use your Jira username and password:

```toml
jira_api_email = "your_username"
jira_api_token = "your_password"
```

!!! note
    The `jira_api_email` field holds your username; `jira_api_token` holds your password. The naming carries over from the Cloud flow.

#### Validating Basic Auth

If tickets aren't coming through, test the connection directly:

1. `pip install jira==3.8.0`
2. Run this script (swap in your actual values):

```python
from jira import JIRA

if __name__ == "__main__":
    try:
        server = "https://..."
        username = "..."
        password = "..."
        ticket_id = "..."

        jira = JIRA(server=server, basic_auth=(username, password), timeout=30)
        if jira:
            print("JIRA client initialised successfully")
        ticket = jira.issue(ticket_id)
        print(f"Ticket title: {ticket.fields.summary}")
    except Exception as e:
        print(f"Error fetching JIRA ticket: {e}")
```

### Jira Data Center/Server (PAT)

1. [Create a Personal Access Token](https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html) in Jira.
2. Configure:

    ```toml
    [jira]
    jira_base_url = "https://jira.example.com"
    jira_api_token = "YOUR_API_TOKEN"
    ```

#### Validating PAT Auth

```python
from jira import JIRA

if __name__ == "__main__":
    try:
        server = "https://..."
        token_auth = "..."
        ticket_id = "..."

        jira = JIRA(server=server, token_auth=token_auth, timeout=30)
        if jira:
            print("JIRA client initialised successfully")
        ticket = jira.issue(ticket_id)
        print(f"Ticket title: {ticket.fields.summary}")
    except Exception as e:
        print(f"Error fetching JIRA ticket: {e}")
```

### Multi-Server Jira

MergeMate can talk to multiple Jira instances with mixed auth types.

=== "Email/Token (Basic Auth)"

    ```toml
    [jira]
    jira_servers = ["https://company.atlassian.net", "https://datacenter.jira.com"]
    jira_api_token = ["cloud_api_token", "datacenter_password"]
    jira_api_email = ["user@company.com", "datacenter_username"]
    jira_base_url = "https://company.atlassian.net"
    ```

=== "PAT Auth"

    ```toml
    [jira]
    jira_servers = ["https://server1.jira.com", "https://server2.jira.com"]
    jira_api_token = ["pat_token_1", "pat_token_2"]
    jira_base_url = "https://server1.jira.com"
    ```

=== "Mixed Auth"

    ```toml
    [jira]
    jira_servers = ["https://company.atlassian.net", "https://server.jira.com"]
    jira_api_token = ["cloud_api_token", "server_pat_token"]
    jira_api_email = ["user@company.com", ""]   # empty for PAT entries
    ```

Each repository can set its own `jira_base_url` locally (in `.mergemate.toml`) to pick which server handles bare ticket IDs like `PROJ-123`.

### Linking a PR to a Jira Ticket

**Method 1 — PR description:** Include a full Jira URL (`https://<ORG>.atlassian.net/browse/ISSUE-123`) or just the ticket ID (`ISSUE-123`).

**Method 2 — Branch name:** Prefix your branch with the ticket ID: `ISSUE-123-fix-thing` or `ISSUE-123/fix-thing`.

!!! note "Jira base URL required"
    For bare ticket IDs or branch detection (Cloud), configure the base URL:
    ```toml
    [jira]
    jira_base_url = "https://<ORG>.atlassian.net"
    ```
    Where `<ORG>` is your Jira organisation identifier (the subdomain before `.atlassian.net`).
