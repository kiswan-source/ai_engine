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
`init_db()`. One real bug found and fixed in this pass (see below). At the
time, `ai-engine-uploads`/`ai-engine-reports` RWX PVCs did NOT bind on
kind's default StorageClass — since fixed by `storage-nfs.yaml`, see "RWX
storage" below.

**RWX storage verified live on a fresh `kind` cluster** (2026-07-06). Both
PVCs now reach `Bound` (previously stuck `Pending` forever, see above); two
throwaway `busybox` Pods mounting the same `ai-engine-uploads` PVC
concurrently confirmed genuine cross-pod RWX access (one wrote a file, the
other read it back). Two real problems found and fixed in this pass: (1)
the kubelet mounts an `nfs:`-type PV from the *node's own* network
namespace, not the pod network — the cluster-DNS name
(`nfs-server.<ns>.svc.cluster.local`) fails to resolve there
(`mount.nfs: Failed to resolve server ...: Name or service not known`);
fixed by pinning the `nfs-server` Service's `ClusterIP` and referencing
that raw IP in the PVs instead of a DNS name. (2) The `janeczku/nfs-ganesha`
image's startup script gets OOMKilled well below a 1-3Gi memory limit on
this test host, despite settling to ~8MB RSS once running — it appears to
size an internal buffer off *detected host memory* (31Gi here) rather than
actual need; worked reliably at an 8Gi limit. Neither issue is specific to
this repo's manifests — they're generic gotchas for anyone self-hosting an
in-cluster NFS server this way, documented here so the next person doesn't
have to rediscover them.

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
4. `ai-engine-uploads`/`ai-engine-reports` now come with a reference RWX
   backend out of the box (`storage-nfs.yaml` — see "RWX storage" below);
   no extra step needed for `kubectl apply -k k8s/base` to work, but read
   that section before running `ai-engine-api` at >1 replica in real
   production.

## Applying

```bash
kubectl apply -k k8s/base                    # dev/staging-ish, single-node friendly defaults
kubectl apply -k k8s/overlays/production      # real registry images, higher replica counts
```

## RWX storage for uploads/reports

`ai-engine-uploads`/`ai-engine-reports` request `ReadWriteMany` so every
`ai-engine-api` replica sees the same uploaded/generated files
(`agent/tools/readers.py`/`writers.py`, `core/chat/engine.py`'s
`UPLOADS_DIR`/`REPORTS_DIR` all assume a shared local filesystem path).
Most default `StorageClass`es (kind's `local-path`, most cloud block
storage) only support `ReadWriteOnce` — confirmed live, these PVCs used to
sit `Pending` forever with `ProvisioningFailed: NodePath only supports
ReadWriteOnce and ReadWriteOncePod access modes`.

`storage-nfs.yaml` fixes this with a reference implementation: a single
userspace NFS-Ganesha server (no kernel `nfsd` module needed — works in
nested/containerized runtimes where loading a kernel NFS server module
isn't possible) exporting `uploads/`+`reports/` subdirectories, bound via
two static `PersistentVolume`s. Applying `k8s/base` as-is now gets both
PVCs to `Bound` with no extra steps — verified live on a fresh `kind`
cluster (see the note near the top of this file for the two gotchas that
came up: DNS resolution from the node's mount namespace, and this specific
Ganesha image's memory-limit sizing).

**This is a reference pattern, not a production mandate.** For real
production, swap it for your platform's managed RWX backend — AWS EFS,
GCP Filestore, Azure Files — or a properly installed Longhorn/Rook-Ceph:
point the two `PersistentVolume`s in `storage-nfs.yaml` at that backend's
NFS endpoint (or replace them with that backend's own dynamic
`StorageClass` and drop the `nfs-server` Deployment/Service/PVC entirely).
A hand-rolled single-replica NFS server is a single point of failure and
not something to run as-is in production.

The alternative path — moving `uploads`/`reports` to S3-compatible object
storage instead of any RWX filesystem — remains a bigger, separate change
(needs rewriting file I/O across `agent/tools/readers.py`/`writers.py`,
protected Bab 45.1), out of scope here; this fix keeps the existing
local-filesystem assumption intact and solves the gap underneath it.

## Gaps (deliberately not solved here)

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
