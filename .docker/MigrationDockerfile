FROM ubuntu:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
  curl \
  ca-certificates \
  build-essential \
  && rm -rf /var/lib/apt/lists/*

ADD https://astral.sh/uv/install.sh /uv-installer.sh

RUN sh /uv-installer.sh && rm /uv-installer.sh

ENV PATH="/root/.local/bin/:$PATH"

COPY . /app

WORKDIR /app

RUN uv sync --locked
RUN chmod +x /app/scripts/migrate_db.sh

CMD ["/app/scripts/migrate_db.sh"]