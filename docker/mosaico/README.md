# MergeMate MOSAICO Solution Agent — registration

This directory holds the MOSAICO registration template for running settings as a
MOSAICO A2A *solution agent* (in-process A2A server, image target `mosaico_agent`).

## Build & run the image

```bash
# from the settings repo root
docker build --target mosaico_agent -t settings-mosaico -f docker/Dockerfile .
docker run -d -p 9000:9000 --name settings-mosaico settings-mosaico
```

The server exposes (port 9000):
- `GET /.well-known/agent-card.json` — the A2A agent card (streaming=false, observability extension, skills: review/improve/describe/ask)
- `POST /` — A2A JSON-RPC `message/send`
- `GET /health` — LLM-connectivity probe (200 `{"is_healthy": true, ...}` / 503)

MOSAICO LLM env vars (consumed by the Stage-1 env bridge at startup): `API_BASE`,
`API_KEY`, `MODEL_NAME`, and optionally `LANGFUSE_HOST`/`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`.
`HOST` (default `0.0.0.0`) / `PORT` (default `9000`) control the bind address.

## Register with MOSAICO (ENDPOINT mode)

Registration is done by the demonstrator's `register-agent.py`. ENDPOINT mode is
selected when `AGENT_CARD_URL` is set. Example:

```bash
REPOSITORY_API=http://mosaico-app:8080 \
AGENT_NAME="MergeMate Solution Agent" \
AGENT_JSON=/app/settings-solution-agent.json \
AGENT_CARD_URL=http://settings-mosaico:9000/.well-known/agent-card.json \
python register-agent.py
```

- `settings-solution-agent.json` is the template in this directory (kept in MOSAICO's
  `docker/agent-registrations/` at deploy time).
- `AGENT_NAME` is injected as the agent name; the card URL is set as the top-level
  `a2aAgentCardUrl` and `deployment.mode` is forced to `ENDPOINT`.

## Cloud dry-run probe (Path A)

An offline-tested diagnostic (`mergemate/mosaico/probe.py`) that, run behind the VPN, health-checks
the cloud MOSAICO reference agent, sends a PR-review task, and reports which solution agent the
router selected — the automated form of the manual "Path A" dry-run.

Prerequisite: connected to the OpenVPN (vm2 `116.203.57.210` is IP-whitelisted).

```bash
# default target (http://116.203.57.210:4000)
PYTHONPATH=. python -m mergemate.mosaico.probe

# explicit reference-agent URL + task text
PYTHONPATH=. python -m mergemate.mosaico.probe http://116.203.57.210:4000 "Review https://github.com/org/repo/pull/1"

# optional registry baseline (best-effort; repo may be internal-only)
MOSAICO_REPOSITORY_URL=http://116.203.57.210:8080 PYTHONPATH=. python -m mergemate.mosaico.probe
```

If the repository is not reachable the probe reports `registry not reachable` and continues.

Reading the output:
- reference-agent health (`OK` / `UNHEALTHY`);
- classification — whether the reference agent judged the task software-engineering (yes/no);
- the selected solution agent (or `no agent selected`);
- the registry baseline line — `settings-solution-agent` will show **ABSENT (not yet registered)**
  until we register it on vm2; that is the EXPECTED baseline right now, so the router will select
  some OTHER agent or none;
- a final-answer excerpt.

Note: the routing signal is parsed from the reference agent's streamed `status-update` events
(`Calling external agent: ...`), so the probe uses A2A `message/stream`; the exact SSE framing is
the one unverified assumption (no live access yet).
