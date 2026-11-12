FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BUNNYSAVE_DATA=/data \
    BUNNYSAVE_PORT=8484

# tar/gzip/bzip2/zstd: archive + compression pipeline; gnupg/age: tar encryption; zip: tooling
RUN apt-get update \
 && apt-get install -y --no-install-recommends tar gzip bzip2 zstd zip unzip gnupg age \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY bunnysave ./bunnysave

VOLUME /data
EXPOSE 8484

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/api/info'%os.environ.get('BUNNYSAVE_PORT','8484'),timeout=4)" || exit 1

# ONE worker on purpose: the scheduler and in-memory job state live in this process.
# Runs as root so file ownership/permissions can be read and restored; see README "Security".
CMD ["sh", "-c", "exec gunicorn -w 1 --threads 16 --timeout 0 -b 0.0.0.0:${BUNNYSAVE_PORT} 'bunnysave.app:create_app()'"]
