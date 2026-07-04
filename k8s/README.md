# Kubernetes manifests (Tahap 8 — MASTER_INSTRUCTION.md Bab 38)

These map the existing `docker-compose.yml` services onto Kubernetes, using
plain `kubectl`-bundled Kustomize (no Helm — Bab 45.3, avoid a new tool
where one isn't needed).

**Verified live on a local `kind` cluster** (2026-07-05, see ADR-0011
addendum). `kubectl apply -k` against `k8s/base` (via a registry-remapped
overlay, since kind needs images pushed to a registry it can pull from) got
all 6 pods to `1/1 Running`: Postgres, Redis, API, both workers. Confirmed
live: `/health/`, `/health/ready` return 200 both pod-direct and through the
`ai-engine-api` ClusterIP Service; RQ workers bind `ai_queue`/`gis_queue`
against in-cluster Redis; API connects to in-cluster Postgres and runs
`init_db()`. One real bug found and fixed in this pass (see below). The
`ai-engine-uploads`/`ai-engine-reports` RWX PVCs behave exactly as predicted
below — they do NOT bind on kind's default StorageClass.

## What maps to what

| docker-compose service | Kubernetes resource |
|---|---|
| `postgres` (custom `docker/Dockerfile.postgres`, pgvector) | `postgres` StatefulSet + headless Service + PVC |
| `redis` | `redis` Deployment + Service + PVC |
| `api` | `ai-engine-api` Deployment (2 replicas) + Service |
| `worker_ai` | `ai-engine-worker-ai` Deployment (2 replicas) |
| `worker_gis` | `ai-engine-worker-gis` Deployment (1 replica) |
| `rq_dashboard` | not migrated — internal debugging tool; add if you need it in-cluster |
| `ollama` (host-network `172.29.239.93:11434` in dev) | **not included** — point `OLLAMA_BASE_URL` at your own in-cluster Ollama Service or reachable external host |

Config/Secret split mirrors `api/config.py` exactly: `configmap.yaml` has
every non-sensitive setting, `secret.yaml` has `SECRET_KEY`, `DATABASE_URL`,
`REDIS_URL`, the three provider API keys, `API_KEYS`, and the Postgres
credentials. See `secret.yaml`'s header for how to fill in real values
without ever writing them into a file in this repo.

## Prerequisites before applying

1. **Build and push three images** to a registry the cluster can pull from —
   these manifests don't build anything:
   ```bash
   docker build -f docker/Dockerfile.api      -t <registry>/ai_engine-api:<tag>      .
   docker build -f docker/Dockerfile.worker   -t <registry>/ai_engine-worker:<tag>   .
   docker build -f docker/Dockerfile.postgres -t <registry>/ai_engine-postgres:<tag> .
   docker push <registry>/ai_engine-api:<tag>
   docker push <registry>/ai_engine-worker:<tag>
   docker push <registry>/ai_engine-postgres:<tag>
   ```
   A natural follow-up (not done here, see Gaps) is extending
   `.github/workflows/ci.yml` to build+push these on tag/release.
2. Point `k8s/overlays/production/kustomization.yaml`'s `images:` block at
   those real references (the `CHANGE_ME_TO_A_REAL_BUILD_TAG` placeholders).
3. Fill in `secret.yaml` with real values via one of the methods in its
   header comment — never edit the file in place with real secrets and
   commit it.
4. Provide `RWX`-capable storage for `ai-engine-uploads`/`ai-engine-reports`
   PVCs if you plan to run `ai-engine-api` at >1 replica (most default
   `StorageClass`es are `RWO`-only — see Gaps).

## Applying

```bash
kubectl apply -k k8s/base                    # dev/staging-ish, single-node friendly defaults
kubectl apply -k k8s/overlays/production      # real registry images, higher replica counts
```

## Gaps (deliberately not solved here)

- **RWX storage assumption** — `api-deployment.yaml`'s `uploads`/`reports`
  PVCs request `ReadWriteMany` so every API replica sees the same files;
  most default `StorageClass`es (e.g. plain `local-path`, most cloud block
  storage) only support `ReadWriteOnce`. **Confirmed live on kind**: the PVCs
  sit `Pending` with `ProvisioningFailed: NodePath only supports
  ReadWriteOnce and ReadWriteOncePod access modes`, blocking every pod that
  mounts them. Either pick a `StorageClass` that supports RWX (NFS, EFS,
  Filestore, Longhorn) or move `uploads`/`reports` to object storage
  (S3-compatible) — a bigger change than this tahap's scope, since
  `agent/tools/readers.py`/`writers.py` (protected, Bab 45.1) currently
  assume local filesystem paths.
- **Postgres and Redis are single instances**, not HA — a real production
  deployment needs a Postgres operator (Patroni, CloudNativePG) and Redis
  Sentinel/Cluster; out of scope here.
- **Worker Deployments have no liveness/readiness probe** — RQ has no HTTP
  surface, and a meaningful `exec` probe needs process-inspection tooling
  (`pgrep`/`ps`) this image doesn't ship; `restartPolicy: Always` plus RQ's
  own warm-shutdown handling (verified against the installed `rq==1.16.2`,
  see ADR-0011) cover crash recovery and graceful termination without one.
- **Docker images aren't multi-stage** (Bab 37 rule 2 asks for this) —
  `docker/Dockerfile.api`/`Dockerfile.worker` install build tooling
  (gcc, gdal headers) into the final image rather than a separate builder
  stage. Rewriting them safely (keeping GDAL/PostGIS runtime libs working
  for `fiona`/`shapely`) needs careful testing against a currently-working
  deployment (see the ADR-0009 Docker-rebuild incident) — deferred to its
  own session rather than risked here.
- **CI doesn't build/push images** — `.github/workflows/ci.yml` still only
  runs `pytest --cov`; wiring image build+push (and this manifest's apply)
  into CI/CD is a natural next step, not done in this tahap.
