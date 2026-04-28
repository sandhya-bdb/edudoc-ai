# Azure Deployment — Steering Doc

End-to-end playbook for deploying the MediShield Document Classifier to Azure Container Apps. Covers the **one-time bootstrap** (run locally) and the **ongoing CI/CD path** (GitHub Actions on every push to `main`).

---

## 1. Local prerequisites (one-time bootstrap only)

| Tool | Purpose | Verify |
|---|---|---|
| Azure CLI (`az`) | Provisions all Azure resources | `az --version` |
| Docker Desktop | Builds & pushes the container image | `docker info` |
| Bash | Runs `infra/deploy.sh` (Git Bash on Windows is fine) | `bash --version` |
| `az login` session | Authenticates the bootstrap script | `az account show` |
| Active Azure subscription | Pays for the resources | `az account show --query name` |

A `.env` file at the repo root with at minimum:

```
GOOGLE_API_KEY=...                  # required — Gemini API key
LANGCHAIN_API_KEY=...               # optional — enables LangSmith tracing
LANGCHAIN_PROJECT=medishield-classification   # optional
```

---

## 2. Azure resources created (all in `medishield-rg`, region `eastus`)

| # | Resource | Name | Why it exists |
|---|---|---|---|
| 1 | Resource Group | `medishield-rg` | A single container for every resource so teardown is one command |
| 2 | Azure Container Registry (ACR) | `medishieldacr27529` | Private Docker registry for the app image; Container Apps pulls from here |
| 3 | Log Analytics Workspace | `medishield-logs` | Captures container stdout/stderr — without it the app runs blind |
| 4 | Container Apps Environment | `medishield-env` | Networking + logging boundary that hosts the Container App |
| 5 | Container App | `medishield-classifier` | The running FastAPI service: `cpu=2.0`, `memory=4.0Gi`, `1–3 replicas`, public ingress on port 8000 |

> ⚠️ The bootstrap script defaults `ACR_NAME=medishieldacr$RANDOM`. Always pin `ACR_NAME=medishieldacr27529` when re-running so you don't create a duplicate registry.

---

## 3. The bootstrap script — step by step (what & why)

`infra/deploy.sh` runs these 8 stages. All are **idempotent** except the `$RANDOM` ACR-name default.

| Step | What it does | Why it's needed |
|---|---|---|
| 0 | `set -euo pipefail` + load `.env` | Fail fast on any error; pull `GOOGLE_API_KEY` from `.env` so it's not hardcoded |
| 1 | `az group create` | Creates the resource group; the parent of everything else |
| 2 | `az acr create --sku Basic --admin-enabled true` | Private registry; admin user enabled so we have a username/password to give Container Apps |
| 3 | `az acr login` + `docker build` + `docker push` | Authenticates Docker against ACR, builds the image, pushes it. Container Apps can only deploy images that already exist in a registry |
| 4 | `az monitor log-analytics workspace create` + read `customerId` & `primarySharedKey` | Creates the log sink and grabs the keys we'll wire into the Container Apps environment |
| 5 | `az containerapp env create --logs-workspace-id … --logs-workspace-key …` | Provisions the shared environment that runs the Container App and forwards logs to step 4 |
| 6 | Build `SECRETS` & `ENV_VARS` strings | Maps secret values once, then references them by name (`secretref:google-api-key`) so the secret never appears as a plaintext env var in the Azure portal |
| 7 | `az containerapp create` | Actually creates the running service: pulls the image with the ACR admin creds, exposes port 8000 publicly, sets resources & autoscale |
| 8 | `az containerapp show --query …ingress.fqdn` | Reads back the auto-assigned public URL and prints it |

---

## 4. Container App secrets & env vars

| Kind | Name | Source | Why |
|---|---|---|---|
| Secret | `google-api-key` | `.env` locally / `GOOGLE_API_KEY` GitHub secret in CI | Stored encrypted in the Container App; not visible as a plain env var |
| Secret | `langchain-api-key` | `.env` / `LANGCHAIN_API_KEY` GitHub secret (optional) | Same — only created if LangSmith tracing is enabled |
| Env var | `GOOGLE_API_KEY` | `secretref:google-api-key` | The app reads this at startup; the `secretref:` indirection keeps the value out of the env-var blob |
| Env var | `LANGCHAIN_API_KEY` | `secretref:langchain-api-key` (optional) | Same indirection for LangSmith |
| Env var | `LANGCHAIN_TRACING_V2` | `true` (only if LangSmith key present) | Switches the LangChain SDK into tracing mode |
| Env var | `LANGCHAIN_PROJECT` | `medishield-classification` | LangSmith project bucket |
| Env var | `PYTHONUNBUFFERED` | `1` | Forces Python to flush stdout/stderr immediately so logs show up in Log Analytics in real time |

---

## 5. GitHub Actions — ongoing CI/CD

Workflow: [.github/workflows/deploy.yml](../.github/workflows/deploy.yml). Triggers on push to `main` and manual `workflow_dispatch`. Job order: **test → deploy** (deploy is gated on tests passing).

### Deploy job steps & rationale

| Step | Why |
|---|---|
| `azure/login@v2` (OIDC) | Federated token — no long-lived service-principal password stored in GitHub |
| `az acr credential show` + `docker login` | ACR admin creds for the runner to push |
| `docker build -t :sha -t :latest` + `docker push` (both tags) | SHA tag = immutable rollback target; `:latest` for convenience |
| `az containerapp secret set` | **Must run before `update`** because `az containerapp update` does not accept `--secrets` (commit `d3a46be`) |
| `az containerapp update --image …:sha` | Triggers a rolling deploy of a new revision pointing at the immutable SHA-tagged image |
| `curl --fail --retry 5 /health` | Smoke test — fails the workflow if the new revision isn't healthy |
| Print app URL | Visible in the workflow log for quick access |

### GitHub repo secrets required

| Secret | Purpose |
|---|---|
| `AZURE_CLIENT_ID` | App registration client ID with federated credential for this repo |
| `AZURE_TENANT_ID` | Azure AD tenant |
| `AZURE_SUBSCRIPTION_ID` | Subscription containing `medishield-rg` |
| `GOOGLE_API_KEY` | Synced to Container App secret on every deploy |
| `LANGCHAIN_API_KEY` | Optional, for LangSmith tracing |

### Azure-side prerequisites for OIDC

1. App registration in Azure AD.
2. Federated credential scoped to `repo:<org>/<repo>:ref:refs/heads/main` and `repo:<org>/<repo>:environment:production` (the deploy job uses `environment: production`).
3. Role assignments on `medishield-rg`: `Contributor` (or narrower: `AcrPush` on ACR + `Container Apps Contributor` on the app).
4. GitHub `production` environment created in repo settings.

---

## 6. Application contract (what the image must expose)

- Listens on **port 8000** (matches `--target-port 8000`).
- Implements `GET /health` returning HTTP 200 — the deploy workflow uses it as the smoke-test gate.
- Also exposes `/docs` (FastAPI Swagger) and `/metrics` (Prometheus).
- Reads `GOOGLE_API_KEY` from env at startup.

---

## 7. All commands you'll need (and why)

### Bootstrap (one time)

```bash
# 1. Authenticate to Azure
az login                                            # opens browser; required before any az command

# 2. Pick the right subscription (if you have multiple)
az account set --subscription "<subscription-id>"   # all resources land here

# 3. Run the full bootstrap (always pin ACR_NAME on re-runs)
ACR_NAME=medishieldacr27529 bash infra/deploy.sh    # creates RG → ACR → image → Logs → env → app
```

### Day-to-day deploys

```bash
# CI handles this — push to main:
git push origin main                                # triggers .github/workflows/deploy.yml

# Manual trigger from CLI:
gh workflow run "Deploy to Azure Container Apps"    # same workflow, on demand
```

### Operations

```bash
# Tail live logs (Ctrl-C to stop)
az containerapp logs show -n medishield-classifier -g medishield-rg --follow

# Get the public URL
az containerapp show -n medishield-classifier -g medishield-rg \
  --query properties.configuration.ingress.fqdn -o tsv

# List revisions (each deploy creates a new one)
az containerapp revision list -n medishield-classifier -g medishield-rg -o table

# Restart the active revision (clears stuck state without redeploying)
az containerapp revision restart -n medishield-classifier -g medishield-rg \
  --revision $(az containerapp show -n medishield-classifier -g medishield-rg \
               --query properties.latestRevisionName -o tsv)

# Roll back to a previous revision
az containerapp ingress traffic set -n medishield-classifier -g medishield-rg \
  --revision-weight <old-revision-name>=100

# Update only the secret (e.g. rotated GOOGLE_API_KEY) without redeploying image
az containerapp secret set -n medishield-classifier -g medishield-rg \
  --secrets google-api-key=<new-value>
az containerapp revision restart -n medishield-classifier -g medishield-rg \
  --revision <active-revision>                      # restart so the new secret is read

# Tear down EVERYTHING (deletes the resource group)
bash infra/teardown.sh
```

### Manual image rebuild (if CI is broken)

```bash
az acr login --name medishieldacr27529              # refresh Docker creds against ACR
docker build -t medishieldacr27529.azurecr.io/classifier:latest .
docker push medishieldacr27529.azurecr.io/classifier:latest
az containerapp update -n medishield-classifier -g medishield-rg \
  --image medishieldacr27529.azurecr.io/classifier:latest
```

---

## 8. FAQ — what to do when errors come

### Q: `docker push` fails partway through with `unauthorized:`
The ACR access token (~3 hr lifetime) expired during a slow upload of large layers (easyocr models, Python venv). Re-run:
```bash
az acr login --name medishieldacr27529
docker push medishieldacr27529.azurecr.io/classifier:latest
```
Already-uploaded layers skip instantly, so the retry is fast.

### Q: `az acr build` fails with "ACR Tasks not enabled"
Don't use `az acr build` — this project intentionally builds locally / in the GitHub runner and pushes (commit `8fa7cc7`). Use `docker build` + `docker push` instead.

### Q: `az containerapp update --secrets …` errors with `unrecognized arguments`
`update` does not accept `--secrets`. Use two calls (commit `d3a46be`):
```bash
az containerapp secret set -n <app> -g <rg> --secrets key=value
az containerapp update    -n <app> -g <rg> --image <new-image>
```

### Q: GitHub Actions Azure login fails with `AADSTS70021: No matching federated identity record found`
Federated credential subject doesn't match. The workflow's `environment: production` makes the subject `repo:<org>/<repo>:environment:production`, **not** `:ref:refs/heads/main`. Add a federated credential with the `environment:production` subject. (Commit `d28caec` adds the required `id-token: write` permission — verify it's still there.)

### Q: `/classify` returns 503 in Azure (works locally)
The worker is being OOM-killed mid-request. Logs show `Child process [N] died`. EasyOCR (~600 MB resident) + Gemini SDK + parallel docs exceeds 2 GiB. Bump memory:
```bash
az containerapp update -n medishield-classifier -g medishield-rg --cpu 2.0 --memory 4.0Gi
```
Valid combos must follow the matrix (`0.25/0.5Gi`, `0.5/1Gi`, `1/2Gi`, `2/4Gi`, `4/8Gi`, …) — see the FAQ entry below for the full list.

### Q: Deploy succeeds but `/health` smoke test fails
1. Tail logs: `az containerapp logs show -n medishield-classifier -g medishield-rg --follow`
2. Common causes:
   - `GOOGLE_API_KEY` missing or invalid → check `az containerapp secret list -n medishield-classifier -g medishield-rg`
   - Image built for wrong arch (Apple Silicon → linux/amd64) → rebuild with `docker build --platform linux/amd64 …`
   - App needs >2 GiB RAM at boot (easyocr model load) → bump `--memory` to `4.0Gi`
3. Roll back with `az containerapp ingress traffic set …` (see commands above).

### Q: `az containerapp create` says "ContainerAppName already exists"
Bootstrap already ran. Don't re-run `deploy.sh` for updates — push to `main` (CI handles it) or run a one-off `az containerapp update --image …`.

### Q: Re-running `deploy.sh` created a second ACR (`medishieldacr12345`)
The script's `ACR_NAME=medishieldacr$RANDOM` default fired again. Always pin: `ACR_NAME=medishieldacr27529 bash infra/deploy.sh`. Delete the duplicate: `az acr delete -n <duplicate-name> -g medishield-rg --yes`.

### Q: Container App is stuck on an old revision
1. `az containerapp revision list -n medishield-classifier -g medishield-rg -o table` — confirm the new revision is `Provisioned`.
2. If multiple are active, set traffic 100% to the latest: `az containerapp ingress traffic set … --revision-weight <new>=100`.
3. If the new revision is `Failed`, view logs with `--revision <name>` and roll back.

### Q: `easyocr` model download fails during `docker build`
Network blip pulling models from GitHub. Re-run the build; the layer cache will resume. If repeated, build at a different time or pre-fetch the model files.

### Q: Logs aren't appearing in Log Analytics
- Check `PYTHONUNBUFFERED=1` is set on the app (without it Python buffers stdout and logs trickle out slowly).
- Log Analytics has a 1–3 min ingestion delay — wait, then query in the portal under the `medishield-logs` workspace, table `ContainerAppConsoleLogs_CL`.

### Q: I rotated `GOOGLE_API_KEY` — how do I push it without a full redeploy?
```bash
az containerapp secret set -n medishield-classifier -g medishield-rg \
  --secrets google-api-key=<new-value>
az containerapp revision restart -n medishield-classifier -g medishield-rg \
  --revision $(az containerapp show -n medishield-classifier -g medishield-rg \
               --query properties.latestRevisionName -o tsv)
```

### Q: I want to change region from `eastus`
Region is locked once the Container Apps environment is created. To move: `bash infra/teardown.sh`, then re-bootstrap with `LOCATION=<new-region>`.

### Q: How do I tear everything down?
```bash
bash infra/teardown.sh         # deletes the entire resource group
```

---

## 9. How Docker / buildx / push / pull actually work in this deployment

This section explains the mechanics behind the build-and-deploy commands so the FAQ entries make sense in context.

### 9.0 Azure Container Registry (ACR) — what it is and why we use it

**ACR is Azure's private Docker registry** — a managed equivalent of Docker Hub that lives inside your Azure subscription. In this project it's the resource named `medishieldacr27529`, with login server `medishieldacr27529.azurecr.io`.

**Why a registry exists in the flow at all**

Container Apps does not run source code or local images — it only runs images it can `docker pull` from a registry. ACR is that registry. Every deploy is fundamentally:

```
local/CI build  →  docker push to ACR  →  Container Apps pulls from ACR  →  starts revision
```

Without ACR (or some equivalent registry) there is no path from your laptop to the running app.

**Why ACR specifically (vs. Docker Hub, GHCR, etc.)**

| Property | ACR | Docker Hub |
|---|---|---|
| Privacy | Private by default | Public unless you pay |
| Region | Same region as the app (eastus) → sub-second intra-region pulls | Global CDN, but still external network |
| Auth | Native Azure RBAC + admin user; integrates with managed identities | Separate Docker account, separate credentials to manage |
| Billing | Rolled into the same Azure subscription / resource group | Separate provider |
| Teardown | Deleted with the resource group in one command | Manual cleanup of repos |

**The image reference, decoded**

```
medishieldacr27529.azurecr.io  /  classifier  :  latest
└────── registry login server ──┘   └─ repo ─┘   └tag┘
```

- **Login server** = `<acr-name>.azurecr.io` — globally unique DNS name (this is why the script uses `medishieldacr$RANDOM` as a default; the name has to be unique across all of Azure).
- **Repo** = `classifier` — within ACR you can have many repos; we only have one.
- **Tag** = `latest` or `<git-sha>` — points to a specific layer manifest. CI pushes both.

**SKU & admin access**

The bootstrap script creates the registry with:

```bash
az acr create --sku Basic --admin-enabled true
```

- **`--sku Basic`** — cheapest tier (~$5/month). Sufficient for a single app; bigger SKUs add geo-replication, content trust, private endpoints. Upgrade if you ever need them — this is an in-place change.
- **`--admin-enabled true`** — turns on a built-in admin user with a username (= ACR name) and a regenerable password. Container Apps stores this username/password as a registry credential so it can pull. The cleaner production alternative is to give the Container App a managed identity with `AcrPull` role and skip the password entirely; we use admin auth here for simplicity.

**How auth flows in practice**

1. **Local push (`bash infra/deploy.sh`)** — `az acr login --name medishieldacr27529` exchanges your `az login` token for a short-lived (~3 hr) Docker credential and stuffs it into your local Docker config. `docker push` then uses it. The token is what expires mid-push on slow uploads — the FAQ "unauthorized:" entry covers re-running.
2. **GitHub Actions push** — `az acr credential show` fetches the admin password into the runner's env, then `docker login --password-stdin` and `docker push`. No persistent secrets are stored anywhere; everything is fetched on the fly using the OIDC-acquired Azure session.
3. **Container Apps pull** — when the app was created, the script passed `--registry-username` and `--registry-password`; Azure stored these as a registry credential on the Container App. Every time it scales up or starts a new revision, it uses those creds to pull the image. (You'll see the warning `Adding registry password as a secret with name "medishieldacr27529azurecrio-medishieldacr27529"` — that's Azure stashing the password as an internal Container App secret.)

**Useful ACR commands**

```bash
# List all images and tags in the registry
az acr repository list --name medishieldacr27529 -o table
az acr repository show-tags --name medishieldacr27529 --repository classifier -o table

# Inspect a manifest (digest, size, layers)
az acr repository show-manifests --name medishieldacr27529 --repository classifier

# Delete an old image to free space
az acr repository delete --name medishieldacr27529 --image classifier:<old-sha> --yes

# Get the admin credentials (printed only on demand, not stored anywhere readable by default)
az acr credential show --name medishieldacr27529

# See registry storage usage
az acr show-usage --name medishieldacr27529
```

ACR retains every pushed tag forever unless you delete it or set up retention policies — over time the SHA-tagged images accumulate. For this project that's fine; in larger setups you'd configure a retention policy via `az acr config retention update`.

---

### 9.1 The image is the unit of deployment

Container Apps does not run our source code — it runs a **Docker image**. The image is a stack of read-only **layers** built from the [Dockerfile](../Dockerfile):

```
Layer 0  python:3.12-slim base
Layer 1  apt-get install (libgl1, libgomp1, …)        ← ~100 MB, cached forever
Layer 2  uv sync (torch, easyocr, fastapi, …)          ← ~1.5 GB, cached unless uv.lock changes
Layer 3  COPY src/                                      ← invalidated on any code change
Layer 4  COPY frontend/                                 ← invalidated on any UI change
Layer 5  easyocr model download (~100 MB)              ← cached
```

Each layer has a content hash. If a layer's inputs are unchanged, Docker reuses the cached layer instead of rebuilding it. **This is why a code-only change rebuilds in seconds, not minutes** — only layers 3 and 4 are redone.

### 9.2 `docker build` vs `docker buildx build`

| | `docker build` | `docker buildx build` |
|---|---|---|
| Builder | Legacy in-process | BuildKit (separate daemon, parallel, smarter cache) |
| Cross-platform | Host arch only | `--platform linux/amd64` works on any host (Apple Silicon, Windows ARM) |
| Push | Two-step: build → push | One-step: `--push` builds and uploads in one go |
| Cache | Local Docker cache only | Optional registry cache, multi-platform cache |

We use buildx because:
1. **`--platform linux/amd64`** — Container Apps requires amd64 images. If your host is ARM (Apple Silicon, ARM laptops, or Docker Desktop on certain Windows configs), a plain `docker build` produces an ARM image that fails at deploy with `image OS/Arc must be linux/amd64 but found linux/arm64`.
2. **`--push`** combines build and upload into one streamed operation. Layers can start uploading as soon as they're built, instead of waiting for the whole build to finish.

The bootstrap script and the GitHub Actions workflow both use buildx-style flags (`--platform linux/amd64`).

### 9.3 How the push works (it's not a full upload)

`docker push <image>` does **not** upload a monolithic image file. It uploads layers one at a time, and ACR tells the client which layers it already has:

```
094bd3e2f202f: Layer already exists       ← ACR has this hash; nothing to upload
081c23b19c1c: Pushing  [=====>  ] 250MB   ← new layer, uploading
ce3e33cb20ca: Pushing  [==>     ] 80MB    ← new layer, uploading
```

After all layers are uploaded, Docker uploads a tiny **manifest** (a JSON blob listing the layer hashes for the tag `:latest`). The manifest upload is the moment the new image becomes pullable.

This is why:
- **The first push is slow** (~1.5 GB of new layers)
- **Subsequent pushes are fast** (only changed layers upload — usually a few MB for code-only changes)
- **`unauthorized:` errors mid-push** can happen on slow links: the ACR token is ~3 hr but each layer upload negotiates again, and a stalled layer can outlive the token. Re-running `az acr login && docker push` resumes — already-uploaded layers are skipped instantly.

### 9.4 How Container Apps uses the image

When `az containerapp create` or `az containerapp update --image` runs:

1. **Pull credentials**: Container Apps stores ACR username/password as a registry credential on the app (see the warning `Adding registry password as a secret with name "medishieldacr27529azurecrio-…"`).
2. **Pull the image**: The Container Apps platform pulls `medishieldacr27529.azurecr.io/classifier:<tag>` into a fresh worker node. ACR is in the same region as the app, so the pull is fast (gigabit intra-region).
3. **Create a new revision**: Container Apps creates a new immutable revision (e.g. `medishield-classifier--abc1234`) pinned to that exact image digest — even if `:latest` is later overwritten, this revision keeps pointing at the same digest.
4. **Health check**: The new revision starts and must pass startup probes (default: TCP on `--target-port 8000` succeeds). Once healthy, traffic shifts to it (rolling update).
5. **Old revision**: Kept around (deactivated) so you can roll back instantly via `az containerapp ingress traffic set --revision-weight <old>=100`.

### 9.5 Why we tag with both `:latest` and `:<commit-sha>` in CI

The GitHub Actions workflow ([deploy.yml](../.github/workflows/deploy.yml)) does:

```bash
docker build -t .../classifier:${{ github.sha }} -t .../classifier:latest .
docker push  .../classifier:${{ github.sha }}
docker push  .../classifier:latest
az containerapp update --image .../classifier:${{ github.sha }}
```

- **`:<sha>` tag** — immutable. Container Apps records this exact tag against the revision, so rollback is unambiguous (`update --image …:<old-sha>`). Without this you'd be rolling back to a `:latest` that may have been overwritten since.
- **`:latest` tag** — convenience for humans (`docker pull …:latest` for local debugging, copy-paste `az containerapp update --image …:latest` in emergencies).
- **The deploy uses `:<sha>`, not `:latest`** — so even if `:latest` gets overwritten by a parallel pipeline, the deploy is pinned to the exact build that passed tests.

### 9.6 The Dockerfile uses multi-stage build — why that matters

```Dockerfile
FROM python:3.12-slim AS builder       # heavy: uv, build tools
RUN uv sync --frozen --no-dev …

FROM python:3.12-slim AS runtime        # slim: only runtime libs
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
COPY frontend/ ./frontend/
```

The final image only contains the **runtime** stage — the `builder` stage's apt packages, build tools, and uv binary are discarded. Result: smaller image (~2 GB → ~1.5 GB), faster pulls, smaller attack surface.

---

## 10. Known gotchas (summary)

- **Pin `ACR_NAME`** on every re-run of `deploy.sh` — `$RANDOM` default creates duplicates.
- **ACR push tokens expire** — re-run `az acr login` if you see `unauthorized` mid-upload.
- **`az containerapp update` cannot set `--secrets`** — use `secret set` first, then `update --image`.
- **OIDC federated credential subject must include `environment:production`** to match the deploy job.
- **Region is immutable** — chosen at environment-create time only.
- **Always tag images with the commit SHA**, not just `:latest` — gives a clean rollback target.
