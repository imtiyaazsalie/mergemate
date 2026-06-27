FROM python:3.12.13-slim AS base

RUN apt update && apt install --no-install-recommends -y git curl && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ADD pyproject.toml .
ADD requirements.txt .
ADD docs docs
RUN pip install --no-cache-dir . && rm pyproject.toml requirements.txt
ENV PYTHONPATH=/app

FROM base AS github_app
ADD mergemate mergemate
CMD ["python", "-m", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-c", "mergemate/servers/gunicorn_config.py", "--forwarded-allow-ips", "*", "mergemate.servers.github_app:app"]

FROM base AS bitbucket_app
ADD mergemate mergemate
CMD ["python", "mergemate/servers/bitbucket_app.py"]

FROM base AS bitbucket_server_webhook
ADD mergemate mergemate
CMD ["python", "mergemate/servers/bitbucket_server_webhook.py"]

FROM base AS github_polling
ADD mergemate mergemate
CMD ["python", "mergemate/servers/github_polling.py"]

FROM base AS gitlab_webhook
ADD mergemate mergemate
CMD ["python", "-m", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-c", "mergemate/servers/gunicorn_config.py", "--forwarded-allow-ips", "*", "mergemate.servers.gitlab_webhook:app"]

FROM base AS azure_devops_webhook
ADD mergemate mergemate
CMD ["python", "mergemate/servers/azuredevops_server_webhook.py"]

FROM base AS gitea_app
ADD mergemate mergemate
CMD ["python", "-m", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-c", "mergemate/servers/gunicorn_config.py","mergemate.servers.gitea_app:app"]

FROM base AS mosaico_agent
ADD mergemate mergemate
EXPOSE 9000
CMD ["python", "mergemate/mosaico/server.py"]


FROM base AS test
ADD requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt && rm requirements-dev.txt
ADD mergemate mergemate
ADD tests tests
ADD docker/mosaico docker/mosaico

FROM base AS cli
ADD mergemate mergemate
ENTRYPOINT ["python", "mergemate/cli.py"]
