# picoclaw-agent image: the §7 agent-loop wrapper + roles + souls + fixtures.
# Stdlib only -> no pip install, no package index needed at build time.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/agent
WORKDIR /app

COPY agent/ /app/agent/
COPY bridge/ /app/bridge/
COPY souls/ /app/souls/
COPY test_fixtures/ /app/test_fixtures/

# default; overridden per service in compose
ENV BLACKBOARD=/blackboard FIXTURES=/app/test_fixtures MODEL_PROVIDER=mock

CMD ["python", "/app/agent/loop.py"]
