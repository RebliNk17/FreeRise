## Run FreeRise {version}

All you need is [Docker](https://docs.docker.com/get-docker/). This sets up a `freerise` folder
with this release's files and a `.env` with fresh random secrets, then starts it:

```bash
mkdir freerise && cd freerise
curl -fsSLO https://github.com/RebliNk17/FreeRise/releases/download/v{version}/docker-compose.prebuilt.yml
curl -fsSL https://github.com/RebliNk17/FreeRise/releases/download/v{version}/env.example | sed \
  -e "s|^CREDENTIALS_KEY=.*|CREDENTIALS_KEY=$(openssl rand -base64 32)|" \
  -e "s|^SESSION_SECRET=.*|SESSION_SECRET=$(openssl rand -base64 32)|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 16)|" \
  -e "s|^# FREERISE_VERSION=.*|FREERISE_VERSION={version}|" > .env
docker compose -f docker-compose.prebuilt.yml up -d
docker compose -f docker-compose.prebuilt.yml exec api freerise create-user <your-username>
```

Then open <http://localhost:3000>. **Back up `.env`**: its `CREDENTIALS_KEY` encrypts your saved
bank logins.

**Already running FreeRise?** From your `freerise` folder (if `.env` pins `FREERISE_VERSION`, set it
to `{version}` first):

```bash
docker compose -f docker-compose.prebuilt.yml pull && docker compose -f docker-compose.prebuilt.yml up -d
```

Images, tagged `{version}`: `freeriseil/api`, `freeriseil/worker` and `freeriseil/web` on
[Docker Hub](https://hub.docker.com/u/freeriseil), and `ghcr.io/reblink17/freerise-api`, `-worker`
and `-web` on GHCR. The [README](https://github.com/RebliNk17/FreeRise#quick-start-with-docker) has
the full guide.

