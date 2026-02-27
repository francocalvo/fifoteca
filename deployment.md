# Fifoteca Deployment (Current Production Flow)

This document describes the deployment we actually use today.

It replaces the old Traefik-first template deployment instructions.

## Topology

- **App host**: `muad@192.168.1.4`
  - Repo path: `/home/muad/fifoteca`
  - Runs app stack with `docker compose` (Podman provider)
  - Exposes:
    - frontend on `53172`
    - backend on `18437`
- **Proxy host**: `muad@192.168.1.100`
  - Runs SWAG (nginx + TLS)
  - SWAG config path:
    - `/mnt/arrakis/swag/nginx/proxy-confs/subdomains/fifoteca.subdomain.conf`

Public routing:

- `https://fif.calvo.dev/` -> frontend (`192.168.1.4:53172`)
- `https://fif.calvo.dev/api/` -> backend (`192.168.1.4:18437`)
- `https://fif.calvo.dev/api/v1/fifoteca/ws/` -> websocket backend route

We do **not** rely on `api.fif.calvo.dev` for API traffic.

## Runtime Config on App Host

Required `.env` values (on `192.168.1.4`):

```env
DOMAIN=fif.calvo.dev
FRONTEND_HOST=https://fif.calvo.dev
VITE_API_URL=https://fif.calvo.dev
BACKEND_CORS_ORIGINS="https://fif.calvo.dev,https://www.fif.calvo.dev"

HOST_BACKEND_PORT=18437
HOST_FRONTEND_PORT=53172

# Optional override for DB bind mount path
HOST_DB_DATA_PATH=/home/muad/fifoteca/data/postgres
```

## Compose Files Used

Deploy with:

```bash
docker compose -f compose.yml -f compose.deploy.yml up -d --build
```

`compose.deploy.yml` provides:

- host port mappings for backend/frontend
- build arg override for frontend API URL
- DB bind mount support:
  - `${HOST_DB_DATA_PATH:-/home/muad/fifoteca/data/postgres}:/var/lib/postgresql/data/pgdata`

## Standard Deploy Procedure

On app host (`192.168.1.4`):

```bash
ssh muad@192.168.1.4
cd /home/muad/fifoteca
git pull
sudo docker compose -f compose.yml -f compose.deploy.yml up -d --build
```

## Podman Networking Caveat (Important)

In this environment, with Podman-backed compose, app containers can become attached to both
`fifoteca_default` and `fifoteca_traefik-public`, which has caused external reachability issues.

After deploy, run:

```bash
sudo podman network disconnect -f fifoteca_traefik-public fifoteca_frontend_1
sudo podman network disconnect -f fifoteca_traefik-public fifoteca_backend_1
sudo podman network disconnect -f fifoteca_traefik-public fifoteca_prestart_1 || true
```

## SWAG Config

File on proxy host:

- `/mnt/arrakis/swag/nginx/proxy-confs/subdomains/fifoteca.subdomain.conf`

Expected config:

```nginx
server {
  listen 443 ssl;
  listen [::]:443 ssl;
  server_name fif.calvo.dev;

  include /config/nginx/ssl.conf;
  client_max_body_size 100M;

  location /api/v1/fifoteca/ws/ {
    include /config/nginx/proxy.conf;
    include /config/nginx/resolver.conf;
    proxy_pass http://192.168.1.4:18437;
  }

  location /api/ {
    include /config/nginx/proxy.conf;
    include /config/nginx/resolver.conf;
    proxy_pass http://192.168.1.4:18437;
  }

  location / {
    include /config/nginx/proxy.conf;
    include /config/nginx/resolver.conf;
    proxy_pass http://192.168.1.4:53172;
  }
}
```

Notes:

- Do not duplicate `proxy_http_version` or common `proxy_set_header` lines already set in `/config/nginx/proxy.conf`.
- If SWAG config changes, restart/reload SWAG on proxy host.

## Health Checks

From app host:

```bash
curl http://localhost:18437/api/v1/utils/health-check/
curl -I http://localhost:53172/
```

From proxy host:

```bash
curl http://192.168.1.4:18437/api/v1/utils/health-check/
curl -I http://192.168.1.4:53172/
```

Public:

```bash
curl https://fif.calvo.dev/api/v1/utils/health-check/
curl -I https://fif.calvo.dev/
```

## Postgres Data Persistence (Bind Mount)

Current deploy mode stores Postgres data on host path (not only named volume):

- default: `/home/muad/fifoteca/data/postgres`
- configurable via `HOST_DB_DATA_PATH`

When migrating existing named-volume data to bind path:

1. stop stack
2. backup volume data
3. copy to bind directory
4. set ownership to postgres uid/gid (`999:999`)
5. start stack

Example migration backup filename pattern:

- `/home/muad/fifoteca/data/postgres-volume-backup-<timestamp>.tgz`
