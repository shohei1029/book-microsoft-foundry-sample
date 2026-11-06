FROM ghcr.io/astral-sh/uv:0.12.19 AS uv
FROM python:3.13-slim

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock uv.toml ./
RUN uv sync --locked --no-dev --no-install-project

COPY main.py .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8088

CMD ["python", "main.py"]
