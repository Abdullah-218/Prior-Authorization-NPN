# ProAuth IQ — Deployment

Live deployment record: what we ran, in order, and why. App `proauth-iq`, environment `test`,
region `ap-south-1`, account `663981373942`.

**Live URLs**
- Frontend: http://proaut-Publi-o9CFLIlXCkqI-540122485.ap-south-1.elb.amazonaws.com
- Backend API: http://proaut-Publi-o9CFLIlXCkqI-540122485.ap-south-1.elb.amazonaws.com/api

## Why AWS Copilot CLI

Three services (Node backend, Python ML/RAG service, React frontend) needed real ECS Fargate
infrastructure — VPC, ALB, Service Connect networking, ECR repos, CloudFormation stacks, IAM
roles, Secrets Manager wiring. Copilot generates and manages all of that from a short YAML
manifest per service instead of hand-writing raw CloudFormation/Terraform, while still allowing
custom resources (RDS, S3) via "addons" — a CloudFormation snippet scoped to the environment or
to one service, which Copilot merges into its own stacks automatically. That gave us a real,
production-shaped deployment (private ML service via Service Connect, one shared ALB with
path-based routing for frontend `/` + backend `/api`, least-privilege IAM per task) without
building the plumbing by hand.

---

## 1. Local build + compose validation (before touching AWS)

Confirms all three Docker images actually build and the whole stack talks to itself correctly —
catches bugs (e.g. a missing file in the ML image) before they become a stuck AWS deploy.

```bash
docker compose build frontend
docker compose build backend
docker compose build ml

docker compose up -d postgres
docker compose up -d ml && docker compose ps ml
docker compose up -d backend && docker compose ps backend
docker compose up -d frontend && docker compose ps frontend

docker compose down
```

## 2. Bootstrap the Copilot app and environment

`app init` sets up Copilot's own IAM roles/bookkeeping (no billed resources yet). `env init`
registers the environment config. `env deploy` is the real infrastructure step — creates the VPC,
subnets, ALB, ECS cluster, **and** everything defined in `copilot/environments/addons/` (our RDS
instance and, later, per-service S3 buckets).

```bash
copilot app init proauth-iq
copilot env init --name test --region ap-south-1 --default-config
copilot env deploy --name test
```

## 3. Enable pgvector on RDS

The RDS addon (`copilot/environments/addons/rds.yml`) provisions plain Postgres 17 — the
`vector` extension has to be created once, manually, before the backend's first schema sync tries
to create a `vector`-typed column. RDS has no public endpoint, so this runs as a one-off Fargate
task inside the environment's VPC rather than from a local `psql`:

```bash
copilot task run \
  --app proauth-iq --env test \
  --task-group-name pgvector-init \
  --image postgres:17-alpine \
  --secrets PGPASSWORD=arn:aws:secretsmanager:ap-south-1:663981373942:secret:/copilot/proauth-iq/test/secrets/DB_PASSWORD-HqkpuY \
  --command 'psql -h proauth-iq-test-addonsstack-1e6rcb79bo1-dbinstance-fgaccrboftfn.cpwgoqcai30p.ap-south-1.rds.amazonaws.com -U proauth -d proauth_ai -c "CREATE EXTENSION IF NOT EXISTS vector;"' \
  --acknowledge-secrets-access \
  --follow
```

Output should show `CREATE EXTENSION`.

## 4. Secrets

Real credentials never go in a manifest as plain text — `copilot secret init` writes them to SSM
Parameter Store, and the manifests reference the path. Run once per secret (`<value>` = the real
value — generate `JWT_SECRET`/`DATA_ENCRYPTION_KEY` fresh with `openssl rand -base64 48` /
`openssl rand -base64 32`; the rest come from the app's real `.env` files):

```bash
copilot secret init -n JWT_SECRET --values test='<random value>'
copilot secret init -n DATA_ENCRYPTION_KEY --values test='<32 random bytes, base64>'
copilot secret init -n DATABASE_URL --values test='postgresql://proauth:<db password>@proauth-iq-test-addonsstack-1e6rcb79bo1-dbinstance-fgaccrboftfn.cpwgoqcai30p.ap-south-1.rds.amazonaws.com:5432/proauth_ai'
copilot secret init -n MONGODB_URI --values test='<mongodb+srv connection string>'
```

`GROQ_API_KEYS` contains commas (comma-separated key pool), which breaks `--values`' own parsing
— this one has to go through the interactive prompt instead:

```bash
copilot secret init -n GROQ_API_KEYS
# → select env "test", paste the comma-separated key list when prompted
```

The DB master password comes from the same Secrets Manager secret RDS auto-generated
(`copilot/environments/addons/rds.yml`'s `DBSecret`) — fetch it once to build `DATABASE_URL`
above:

```bash
aws secretsmanager get-secret-value --region ap-south-1 \
  --secret-id "arn:aws:secretsmanager:ap-south-1:663981373942:secret:/copilot/proauth-iq/test/secrets/DB_PASSWORD-HqkpuY" \
  --query "SecretString" --output text
```

## 5. Register the three services

`svc init` registers a service with the Copilot app. Since each service's `manifest.yml` already
existed on disk (already fixed for this app pre-deploy), Copilot detects and keeps it rather than
overwriting.

```bash
copilot svc init --name ml --svc-type "Backend Service" --dockerfile ./ProAuth_AI_ML/Dockerfile --port 8002
copilot svc init --name backend --svc-type "Load Balanced Web Service" --dockerfile ./ProAuth_AI_BackEnd/Dockerfile --port 5001
copilot svc init --name frontend --svc-type "Load Balanced Web Service" --dockerfile ./ProAuth_AI_FrontEnd/Dockerfile --port 8080
```

`ml` is a **Backend Service** (no ALB, no public endpoint) — reachable only from `backend` via
Service Connect DNS (`http://ml:8002`), keeping the RAG/LLM pipeline off the public internet.
`backend` and `frontend` are **Load Balanced Web Services** sharing one ALB via path routing.

## 6. Deploy `ml` — and why the first attempt fails on purpose

```bash
copilot svc deploy --name ml --env test
```

This first deploy builds the image, creates the CloudFormation stack, **and** the per-service S3
bucket for model artifacts (`copilot/ml/addons/models-bucket.yml`) — but the bucket starts out
empty, and the container's entrypoint fetches both ML model files from S3 before starting
`uvicorn`. So the first boot fails (`HeadObject: Not Found`) and ECS keeps retrying — expected,
not a bug. Two real issues came up resolving this the first time:

**Bug hit: `from_cfn: ModelsBucketName` doesn't work here.** `from_cfn` resolves a
CloudFormation cross-stack `Export`, but a *workload-level* addon's outputs are plain nested-stack
outputs, never exported — so the deploy failed with `No export named ModelsBucketName found` and
rolled back. Fixed by hardcoding the bucket name in `copilot/ml/manifest.yml` instead — it's fully
deterministic (`${App}-${Env}-ml-models-${AccountId}`), so hardcoding it is correct, not fragile.
Recovery required deleting the failed stacks before retrying (CloudFormation won't update a stack
stuck in `ROLLBACK_COMPLETE`/`REVIEW_IN_PROGRESS`):

```bash
aws cloudformation delete-stack --region ap-south-1 --stack-name proauth-iq-test-ml
aws cloudformation wait stack-delete-complete --region ap-south-1 --stack-name proauth-iq-test-ml

aws cloudformation delete-stack --region ap-south-1 --stack-name proauth-iq-test-ml-AddonsStack-1NFWSP6H99QCF
```

**Upload the model artifacts**, then redeploy — this time the entrypoint's S3 fetch succeeds and
the service stabilizes:

```bash
aws s3 cp ProAuth_AI_ML/policy-rag/ml/models/proauth_best_model.pkl \
  s3://proauth-iq-test-ml-models-663981373942/models/proauth_best_model.pkl
aws s3 cp ProAuth_AI_ML/priority_intelligence/models/priority_ranker.joblib \
  s3://proauth-iq-test-ml-models-663981373942/models/priority_ranker.joblib
aws s3 cp ProAuth_AI_ML/priority_intelligence/models/priority_ranker_metadata.json \
  s3://proauth-iq-test-ml-models-663981373942/models/priority_ranker_metadata.json

copilot svc deploy --name ml --env test
```

## 7. Deploy backend and frontend, then lock down CORS

```bash
copilot svc deploy --name backend --env test
copilot svc deploy --name frontend --env test
```

`backend`'s `FRONTEND_URL` (used for `Access-Control-Allow-Origin`) starts empty — CORS falls
back to reflecting any origin, which is fine for this first pass since frontend's real URL isn't
known yet. Once `frontend` is up, set the real URL in `copilot/backend/manifest.yml` and redeploy
once more:

```yaml
# copilot/backend/manifest.yml
variables:
  FRONTEND_URL: http://proaut-Publi-o9CFLIlXCkqI-540122485.ap-south-1.elb.amazonaws.com
```

```bash
copilot svc deploy --name backend --env test
```

## 8. Seed RDS with the real local database (schema + pgvector data)

RDS started out empty. To make the cloud environment behave identically to local (same patients,
policies, and — critically — the same `policy_chunks` **vector embeddings** the RAG retrieval
depends on), we copied the real local database across rather than reseeding from scratch.

**Why not a plain `pg_dump | psql`:** RDS has no public endpoint (private-subnet-only), so it's
only reachable from inside the VPC. We opened an SSM port-forward tunnel through a *running,
ECS-Exec-enabled* task (`exec: true` is already set on every service) straight to the RDS
instance's port 5432:

```bash
# Find a running task + its container runtime ID (needed for the SSM target string)
aws ecs list-tasks --cluster <cluster> --service-name proauth-iq-test-backend-Service-<id> \
  --region ap-south-1 --query "taskArns[0]"
aws ecs describe-tasks --cluster <cluster> --tasks <task-id> --region ap-south-1 \
  --query "tasks[0].containers[?name=='backend'].runtimeId"

# Open the tunnel: localhost:15432 -> RDS:5432, via that task
aws ssm start-session \
  --target "ecs:<cluster>_<task-id>_<runtime-id>" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<rds-endpoint>"],"portNumber":["5432"],"localPortNumber":["15432"]}' \
  --region ap-south-1
```

**Why data-only, not schema+data:** the local database had accumulated real schema drift (548
duplicate unique constraints from repeated non-idempotent `sequelize.sync({alter:true})` runs
over the project's history). Copying that schema over would carry the mess into a fresh
environment. Instead, RDS keeps its own clean schema (created once by the backend's first real
boot), and only the *data* gets copied on top of it:

```bash
# Local pg_dump client was v14, RDS is v17 — run pg_dump from inside the
# local Postgres container instead, which has matching v17 tools.
docker exec proauth-postgres pg_dump -U proauth -d proauth_ai \
  --data-only --disable-triggers --no-owner --no-privileges \
  -f /tmp/proauth_data.sql
```

**Load it into RDS through the tunnel**, from inside the same container (so the client/server
versions match on that side too — `host.docker.internal` reaches the tunnel bound on the Mac host):

```bash
# Clear out anything already in RDS first (e.g. earlier test rows)
PGPASSWORD='<db password>' psql -h 127.0.0.1 -p 15432 -U proauth -d proauth_ai -c "
TRUNCATE TABLE users, patients, providers, insurance_plans, policies, policy_versions,
  policy_criteria, policy_chunks, authorizations, authorization_evaluations,
  triage_evaluations, documents, notifications, audit_events RESTART IDENTITY CASCADE;
"

docker exec proauth-postgres bash -c "
  PGPASSWORD='<db password>' psql -h host.docker.internal -p 15432 -U proauth -d proauth_ai \
    -f /tmp/proauth_data.sql
"
```

(`--disable-triggers` needs true superuser, which the RDS master user isn't — those specific
`ALTER TABLE ... DISABLE TRIGGER` lines error out with "permission denied", but every `COPY`
still succeeds, because `pg_dump` already orders tables in foreign-key dependency order. Those
errors are harmless noise, not a failed migration — verify with real row counts, not just "no
errors".)

**Why `DATA_ENCRYPTION_KEY` had to change:** clinical/decision fields are encrypted at the
application layer. The migrated ciphertext was encrypted locally under the *local* key — the
fresh AWS secret we generated in step 4 is a different value, so it would fail to decrypt. Fixed
by overwriting the AWS secret with the exact local key value, then forcing a fresh task launch so
the running container picks it up (the manifest reference didn't change, so a normal `svc deploy`
wouldn't necessarily relaunch tasks — `update-service --force-new-deployment` does):

```bash
copilot secret init -n DATA_ENCRYPTION_KEY --values test='<the local key, exactly>' --overwrite

aws ecs update-service --cluster <cluster> \
  --service proauth-iq-test-backend-Service-<id> \
  --force-new-deployment --region ap-south-1
```

**Verify**: row counts match local exactly, a real login + a real `/triage` call return correctly
decrypted data and a real pgvector-retrieved policy match. Then tear the tunnel down — it's bound
to one specific ECS task ID and dies the moment that task gets replaced, so a fresh tunnel is
needed for any future re-sync.

---

## Verification checklist

```bash
curl http://proaut-Publi-o9CFLIlXCkqI-540122485.ap-south-1.elb.amazonaws.com/api/health
curl http://proaut-Publi-o9CFLIlXCkqI-540122485.ap-south-1.elb.amazonaws.com/healthz
copilot svc logs --name ml --env test --since 10m
```

A real end-to-end check: log in, submit a real authorization, call `/api/triage/evaluate`, and
confirm a genuine decision comes back (not a 503 — that would mean `backend` can't reach `ml`).

## Redeploying after a code change

```bash
copilot svc deploy --name backend --env test   # or ml / frontend
```
