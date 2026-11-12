> Disclaimer: Due to ongoing health issues I am no longer able to concentrate on developing software by myself. This project is therefore vibe-coded: written together with an AI assistant (Claude) and directed, tested and run by me. It is not a demo or proof of concept. It exists because I need it: it fixes a real problem in my day-to-day life and is in daily use. Read the code and the security notes below with that in mind.

# Bunny Save

Self-hosted backup and restore web app (Python 3.12, Flask, vanilla-JS PWA) for a homelab. It archives local folders, the
mounted host filesystem and SFTP servers (including over Tailscale SSH) into `tar.gz`, `tar.zst`, `tar.bz2` or `zip`, optionally
encrypted, with scheduling, retention, hooks, an archive browser with previews, and a restore planner.

**There is no authentication.** Bind it to localhost or your tailnet only.

## Architecture

```
browser (PWA) ──REST/JSON──▶ Flask app (gunicorn, 1 worker, 16 threads)
                               ├─ SQLite  /data/bunnysave.db   (setups, backup history)
                               ├─ JobManager (thread pool, max 2 jobs, 1 per setup, in-memory job state)
                               ├─ APScheduler (interval / daily triggers → backup jobs)
                               └─ sources: LocalFs | HostFs (mounted host root) | SftpFs (paramiko)
```

**Backup pipeline** (`backup.py`, `archive_io.py`): hooks (pre) → scan (glob/exclude/skeleton, cancellable) → free-space check →
Python `tarfile` stream → `gzip|bzip2|zstd` → optional `gpg|age` → `<name>.part` → fsync → atomic rename → SHA-256 →
verification (`tar -tf` over the fully decrypted/decompressed stream, entry count and manifest check; zip: CRC/HMAC read-back) →
retention → hooks (post). A partial `.part` file never survives a failed or cancelled job. Zip is written in-process with `pyzipper`.

**Archive layout:** `.bunnysave/manifest.json` is the first entry (name, timestamp, hostname, version, sources without credentials,
excludes, skeleton paths, permission flag, post-restore commands, totals). Local files are stored root-relative
(`opt/myapp/app.py`), host-filesystem files host-relative, SFTP files under `sftp/<source-id>/…`.
Next to each archive: `<archive>.json` (non-secret metadata) and, for tar formats, `<archive>.idx` (browse index).

**Browse index:** a gzip-JSON sidecar written after a verified backup: manifest, per-entry metadata, and the text of small
text files (≤128 KiB each, ≤8 MiB total). It is encrypted with the archive's own tool and secret when the archive is
encrypted. Browsing and most previews read only the index. Without a valid index (missing, or its stored SHA-256 does not match
the archive) the app falls back to reading the whole archive as a stream and then writes the index. Larger text files are streamed from
the archive up to the entry; zip reads a single member directly (zip has no index file, its central directory is already random-access).

**Restore** (`restore.py`): destinations *original locations*, *local folder* or *SFTP server*; optional start point (prefix stripped)
and path selection; conflict policy `skip` / `overwrite` / `rename` (existing file renamed to `.bak-<timestamp>`). Directories are
merged or moved aside, never deleted. Paths with `..` and symlink escapes out of the target are refused. *Plan* computes and shows
what would happen without writing anything. Post-restore commands from the manifest are off by default (see Security).

**Sources:** *Container* (paths inside the container), *Host* (paths as on the host, via a mount at `BUNNYSAVE_HOST_ROOT`; cannot be
combined with Container sources in one setup), *SFTP* (password, key file, or Tailscale SSH with no credentials). Include entries accept
globs and a *skeleton* flag (directory and permissions only, no contents); excludes are patterns or paths. "Test validity" checks
connection, existence and size of each entry.

**Retention:** keep all, last N, younger than N days, or GFS (daily/weekly/monthly/yearly). The newest backup is never deleted.
Runs only after a successful, verified backup. Deleting a backup removes the archive, `.json` and `.idx`.

## Authentication and encryption

* **No app authentication.** Anyone who can reach the port can read, restore and delete everything.
* **Encryption, tar formats:** `gpg` symmetric (AES-256, SHA-512 S2K) or recipient key; `age` passphrase (scrypt) or recipient.
  The whole compressed tar is encrypted, so file names are hidden. Compression runs before encryption.
* **Encryption, zip:** WinZip-AES-256 via `pyzipper` only (never ZipCrypto). File names and sizes are not encrypted: use tar+gpg/age if names are sensitive.
* **Secret sources per setup:**

| Mode | Behaviour |
|---|---|
| `prompt` | typed in the UI per job, held in memory only |
| `env` | per-setup passphrase derived with scrypt from the master key and the setup's `secret_ref`; needed for unattended encrypted schedules. Re-derive by hand: `BUNNYSAVE_MASTER_KEY=… python -m bunnysave.secretstore derive <secret_ref>` (`secret_ref` is in the `<archive>.json` sidecar) |
| `keyring` | `keyring` library; inside Docker there is normally no keyring backend, so this is mainly for non-container use |

* Secrets are never written to the DB, config, manifest, logs or sidecars. gpg receives its passphrase on an inherited pipe fd, age through a pty, never on the command line. All logs, job output and UI-facing text pass through a redactor (registered secrets plus `password=`-style patterns).
* Passphrase-protected age identities go in `/data/keys/`; gpg secret keys are imported into `/data/gnupg` (`docker compose exec bunnysave gpg --import key.asc`).
* **SFTP host keys:** trust on first use, stored in `/data/known_hosts`; a changed key is rejected.
* **Tailscale SSH:** select auth "Tailscale SSH". No password or key is sent; the SFTP server authenticates the tailnet identity. In Docker the connection leaves via the host's Tailscale node, so your tailnet SSH ACL must allow that node (or the container, with `network_mode: host` / its own Tailscale). Tailscale SSH "check" mode (browser re-auth) is not supported.

## Deployment

```bash
git clone https://github.com/lyvielle/bunny-save && cd bunny-save
# edit docker-compose.yml: mount what you want to back up, set TZ
docker compose up -d --build        # http://127.0.0.1:8484
```

* Compose publishes `127.0.0.1:8484` only. Do not publish on a LAN.
* `./data` → `/data` holds DB, backups, keys, gnupg, logs, known_hosts. `./restore` → `/restore` is a staging directory.
* Container sources: mount folders at the same absolute path as on the host (`:ro` is enough for backups).
* Host source: mount `- /:/hostfs:ro` (or a subtree). "Restore to original locations" onto the host needs a read-write mount.
* The container runs as root so ownership and modes can be read and restored.
* Image: `python:3.12-slim` with `tar gzip bzip2 zstd zip unzip gnupg age`; `gunicorn -w 1 --threads 16 --timeout 0`. One worker on purpose: scheduler and job state live in the process. Healthcheck: `/api/info`.
* PWA: needs HTTPS or localhost to install (e.g. Tailscale serve or a reverse proxy). Icons and the manifest are versioned (`?v=<hash>`); the service worker is network-first and never caches `/api`.
* Local development (needs `tar gzip bzip2 zstd gpg age` on PATH): `pip install -r requirements-dev.txt && BUNNYSAVE_DATA=./data python -m bunnysave.app`

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `BUNNYSAVE_DATA` | `/data` | data directory (DB, backups, keys, gnupg, logs, known_hosts) |
| `BUNNYSAVE_PORT` | `8484` | listen port (gunicorn / dev server) |
| `BUNNYSAVE_HOST_ROOT` | `/hostfs` | mount point of the host filesystem; the Host source appears when it exists and is non-empty |
| `BUNNYSAVE_MASTER_KEY` | unset | master key for `env` secret mode (visible in `docker inspect`; prefer the file variant) |
| `BUNNYSAVE_MASTER_KEY_FILE` | unset | file containing the master key (e.g. a Docker secret) |
| `BUNNYSAVE_SCHEDULER` | `1` | `0` disables APScheduler |
| `TZ` | image default (UTC) | time zone for "daily at" schedules and displayed times |

Both master-key variables are removed from the process environment at start-up, and hooks never receive `BUNNYSAVE_MASTER*`.
Hooks and post-restore commands get `BUNNYSAVE_JOB_ID`, `BUNNYSAVE_ARCHIVE`, `BUNNYSAVE_SOURCE` (restore: the target) and, after a backup, `BUNNYSAVE_STATUS`.

## Repo layout

```
bunnysave/
  app.py          Flask app, REST API, PWA routes (/, /sw.js, /manifest.webmanifest)
  model.py        setup validation/normalisation, secret stripping
  backup.py       backup job, tar/zip writers, retention application, browse-index capture
  restore.py      restore planner and executor (local / SFTP targets, safety checks, post-restore commands)
  archive_io.py   compress/encrypt/decrypt pipelines, readers, verification, index read/write
  browse.py       listing and previews (index fast path, archive fallback, in-RAM cache)
  sources.py      LocalFs / HostFs / SftpFs, glob, excludes, scanning
  testing.py      "Test validity" for sources
  secretstore.py  prompt / master-key (scrypt) / keyring secrets
  redact.py       secret redaction and JSON logging
  hooks.py        pre/post/post-restore command runner (timeouts, captured output)
  jobs.py         job manager and progress state
  scheduler.py    APScheduler glue
  retention.py    retention policies (pure)   conflict.py  restore conflict policy (pure)
  manifest.py     manifest build/parse        db.py        SQLite storage
  settings.py     paths and master key        util.py      helpers
  static/         index.html, app.js, style.css, sw.js, manifest.webmanifest, icons
tests/            pytest suite
Dockerfile  docker-compose.yml  requirements*.txt
```

REST API (all JSON): `/api/info`, `/api/setups` (+ `/<id>`, `/<id>/run`, `/<id>/keyring`), `/api/test-source`, `/api/jobs` (+ `/<id>`, `/<id>/cancel`),
`/api/backups` (+ `/<id>`, `/<id>/download`, `/<id>/entries`, `/<id>/preview`, `/<id>/restore/plan`, `/<id>/restore/run`).

## Security notes

* **No authentication, plain HTTP.** Restrict at the network layer (localhost, tailnet ACLs). The download endpoint serves archives as stored (still encrypted if they are).
* **Root in the container**, with whatever mounts you give it. Read-write host or source mounts let restores overwrite them.
* **Passwords travel in request bodies** (prompt mode) over whatever transport you expose; use HTTPS when not on localhost.
* **Post-restore commands are arbitrary shell code from the archive.** Off by default; they run only if you enable them, tick each command, type `RUN` and confirm a dialog. The API enforces the same confirmation. A tampered archive could carry malicious commands: read them first. Pre/post-backup hooks are trusted, user-configured commands.
* **Master key** in an environment variable is visible via `docker inspect`; use `BUNNYSAVE_MASTER_KEY_FILE`.
* An archive's integrity is checked after writing (and its SHA-256 recorded); there is no signature, so a modified archive with a re-computed sidecar is not detected.
* Not security-audited. Vibe-coded: review before trusting it with data you cannot lose.

## Limitations

* Automated tests cover Flask test-client flows and subprocess round trips (gpg, age, tar.gz); the JS only gets a syntax check. SFTP/Tailscale SSH, zip AES, APScheduler, keyring, zstd, the Docker build and the browser UI were not covered by automated tests.
* Scheduled (unattended) runs need `env` or `keyring` secrets; `prompt` setups fail with a clear message.
* Job state and logs shown in the UI are in memory (last 60 jobs); a restart clears them. Backup history is in SQLite.
* Verifying a recipient-mode archive needs the private key available in the container.
* Hard links are stored as separate copies; sockets, FIFOs and devices are skipped (logged).
* Free-space check: `size × ratio + max(10 %, 64 MiB)`, ratio default 1.0 (no compression assumed).
* Browse listings cap at 200 000 entries; restore plans show at most 2000 rows (counts are complete). Previews are capped at 10 MiB and text-like files only.
* Zip cancellation is cooperative (per chunk); tar jobs terminate the compressor/encryptor subprocesses. Zip file names/sizes are not encrypted.
* Permissions flag off stores normalised modes (0644/0755) and uid/gid 0; on stores mode/uid/gid (names for local). Zip stores mode only.
* Tailscale SSH "check" mode is not supported.

## Tests

`pip install -r requirements-dev.txt && pytest`: manifest, retention, conflict policy and path safety, verification (corruption, truncation),
tar.gz/gpg/age round trips, selection/start-point restore, hooks and post-restore confirmation, cancel, master-key derivation, secret
non-persistence, host source, browse index (plain, encrypted, old-backup upgrade). The zip test is skipped when `pyzipper` is missing.
