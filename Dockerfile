# syntax=docker/dockerfile:1

# ---- build wheels (compilers stay in this stage) --------------------------
FROM python:3.12-slim-bookworm AS build
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

# ---- runtime ---------------------------------------------------------------
FROM python:3.12-slim-bookworm
LABEL org.opencontainers.image.title="LobbyShift" \
      org.opencontainers.image.description="Split-tunnel gateway routing console matchmaking through WireGuard" \
      org.opencontainers.image.source="https://github.com/Watashi199/LobbyShift" \
      org.opencontainers.image.licenses="CC-BY-NC-4.0"

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      iproute2 wireguard-tools nftables iptables iputils-ping \
 && rm -rf /var/lib/apt/lists/*

COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

ENV PYTHONUNBUFFERED=1 \
    LOBBYSHIFT_DATA_DIR=/var/lib/lobbyshift \
    LOBBYSHIFT_LEGACY_DIR=/etc/lobbyshift \
    LOBBYSHIFT_CONFIG_FILE=/etc/lobbyshift/config.yaml

VOLUME ["/var/lib/lobbyshift"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('LOBBYSHIFT_WEB_PORT','8080'), timeout=3)"

# Runs as root inside the container, but docker-compose.yml drops every
# capability except NET_ADMIN / NET_RAW.
ENTRYPOINT ["lobbyshift"]
CMD ["serve"]
