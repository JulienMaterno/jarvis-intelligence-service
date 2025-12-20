# ☁️ Cloud Architecture & Deployment Guide

## Overview

The Jarvis Intelligence Service is deployed on **Google Cloud Platform (GCP)** using **Google Cloud Run** with automated CI/CD via **Google Cloud Build**. This document explains how the cloud deployment works.

## Table of Contents

1. [Cloud Deployment Architecture](#cloud-deployment-architecture)
2. [Google Cloud Build (CI/CD)](#google-cloud-build-cicd)
3. [Google Cloud Run (Runtime)](#google-cloud-run-runtime)
4. [Secrets Management](#secrets-management)
5. [Deployment Flow](#deployment-flow)
6. [Monitoring & Logs](#monitoring--logs)
7. [Troubleshooting](#troubleshooting)

---

## Cloud Deployment Architecture

### Components

```
┌─────────────────────────────────────────────────────────┐
│                    GitHub Repository                     │
│              (jarvis-intelligence-service)              │
└───────────────────┬─────────────────────────────────────┘
                    │ Push to master
                    ▼
┌─────────────────────────────────────────────────────────┐
│              Google Cloud Build Trigger                  │
│  • Watches master branch                                │
│  • Reads cloudbuild.yaml                                │
└───────────────────┬─────────────────────────────────────┘
                    │ Executes build steps
                    ▼
┌─────────────────────────────────────────────────────────┐
│              Build Steps (cloudbuild.yaml)              │
│  1. Build Docker image                                  │
│  2. Push to Container Registry                          │
│  3. Deploy to Cloud Run                                 │
└───────────────────┬─────────────────────────────────────┘
                    │ Deploys container
                    ▼
┌─────────────────────────────────────────────────────────┐
│              Google Cloud Run Service                    │
│  • Service: jarvis-intelligence-service                 │
│  • Region: asia-southeast1                              │
│  • Container: gcr.io/.../jarvis-intelligence-service    │
│  • Secrets: Injected from Secret Manager                │
└─────────────────────────────────────────────────────────┘
                    │ Serves HTTP API
                    ▼
            ┌───────────────┐
            │  Public URL   │
            │  (HTTPS)      │
            └───────────────┘
```

### Technology Stack

- **Container Platform**: Google Cloud Run (serverless)
- **Container Registry**: Google Container Registry (GCR)
- **CI/CD**: Google Cloud Build
- **Secrets**: Google Secret Manager
- **Region**: asia-southeast1 (Singapore)

---

## Google Cloud Build (CI/CD)

### What is Cloud Build?

Google Cloud Build is a serverless CI/CD platform that executes builds defined in `cloudbuild.yaml`. It's triggered automatically when you push code to the `master` branch.

### Build Configuration (`cloudbuild.yaml`)

```yaml
steps:
  # Step 1: Build Docker image
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/jarvis-intelligence-service:latest', '.']

  # Step 2: Push to Container Registry
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/jarvis-intelligence-service:latest']

  # Step 3: Deploy to Cloud Run
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: gcloud
    args:
      - 'run'
      - 'deploy'
      - 'jarvis-intelligence-service'
      - '--image'
      - 'gcr.io/$PROJECT_ID/jarvis-intelligence-service:latest'
      - '--region'
      - 'asia-southeast1'
      - '--platform'
      - 'managed'
      - '--allow-unauthenticated'
      - '--set-secrets'
      - 'SUPABASE_URL=SUPABASE_URL:latest,SUPABASE_KEY=SUPABASE_KEY:latest,ANTHROPIC_API_KEY=CLAUDE_API_KEY:latest'

images:
  - 'gcr.io/$PROJECT_ID/jarvis-intelligence-service:latest'
```

### Step-by-Step Explanation

#### Step 1: Build Docker Image
- Uses the official Docker builder
- Reads the `Dockerfile` in the repository root
- Tags the image with the GCP project ID and `latest` tag
- Image name format: `gcr.io/{PROJECT_ID}/jarvis-intelligence-service:latest`

#### Step 2: Push to Container Registry
- Pushes the built image to Google Container Registry (GCR)
- GCR is a private Docker registry hosted by Google
- Other GCP services can pull images from here

#### Step 3: Deploy to Cloud Run
- Uses the Google Cloud SDK to deploy the container
- Key deployment parameters:
  - **Service name**: `jarvis-intelligence-service`
  - **Region**: `asia-southeast1` (Singapore - closest to your location)
  - **Platform**: `managed` (fully managed by Google, serverless)
  - **Authentication**: `--allow-unauthenticated` (public API access)
  - **Secrets**: Injected from Secret Manager (see below)

---

## Google Cloud Run (Runtime)

### What is Cloud Run?

Cloud Run is a **serverless container platform**. You provide a container, and Google handles:
- Auto-scaling (0 to N instances based on traffic)
- Load balancing
- HTTPS certificates
- Health checks
- Logging

### Key Features

1. **Serverless**: Scales to zero when not in use (no idle costs)
2. **Auto-scaling**: Handles traffic spikes automatically
3. **Pay-per-use**: Only pay for actual request time
4. **HTTPS by default**: Automatic SSL certificates
5. **Fast cold starts**: Containers start in < 1 second

### Service Configuration

```
Service Name:  jarvis-intelligence-service
Region:        asia-southeast1
URL:           https://jarvis-intelligence-service-{hash}-as.a.run.app
Port:          8080 (container port)
Memory:        512 MB (default)
CPU:           1 vCPU (default)
Max instances: Unlimited (default)
```

### Environment Variables

Cloud Run injects environment variables from **Google Secret Manager**:

```bash
SUPABASE_URL      → Secret: SUPABASE_URL:latest
SUPABASE_KEY      → Secret: SUPABASE_KEY:latest
ANTHROPIC_API_KEY → Secret: CLAUDE_API_KEY:latest
```

These are **NOT** visible in logs or the container - they're securely injected at runtime.

---

## Secrets Management

### Google Secret Manager

Sensitive values (API keys, database credentials) are stored in **Secret Manager**, not in code or environment files.

### Secret Configuration

| Secret Name in GCP    | Environment Variable  | Purpose                    |
|-----------------------|----------------------|----------------------------|
| `SUPABASE_URL`        | `SUPABASE_URL`       | Supabase database URL      |
| `SUPABASE_KEY`        | `SUPABASE_KEY`       | Supabase API key           |
| `CLAUDE_API_KEY`      | `ANTHROPIC_API_KEY`  | Claude API key for AI      |

### How Secrets are Injected

The `--set-secrets` flag in Cloud Build tells Cloud Run to:
1. Fetch secrets from Secret Manager
2. Inject them as environment variables into the container
3. Keep them encrypted in transit and at rest

### Adding a New Secret

If you need to add a new secret:

```bash
# 1. Create the secret in Secret Manager
echo -n "your-secret-value" | gcloud secrets create SECRET_NAME --data-file=-

# 2. Grant Cloud Run access
gcloud secrets add-iam-policy-binding SECRET_NAME \
  --member=serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor

# 3. Update cloudbuild.yaml
# Add to --set-secrets: NEW_VAR=SECRET_NAME:latest
```

---

## Deployment Flow

### End-to-End Deployment Process

```
1. Developer pushes code to master
   ↓
2. GitHub webhook triggers Cloud Build
   ↓
3. Cloud Build reads cloudbuild.yaml
   ↓
4. Docker builds image from Dockerfile
   ↓
5. Image pushed to Container Registry
   ↓
6. Cloud Run pulls new image
   ↓
7. Cloud Run performs rolling update
   ↓
8. New version is live (old version terminated)
   ↓
9. URL serves traffic to new container
```

### Deployment Time

- **Total time**: ~2-4 minutes
- Build: 1-2 minutes
- Deploy: 30-60 seconds
- Health check: ~10 seconds

### Zero-Downtime Deployments

Cloud Run uses **rolling updates**:
1. New container starts receiving traffic
2. Old container continues serving existing requests
3. Once old requests complete, old container shuts down

This ensures **no downtime** during deployments.

---

## Monitoring & Logs

### Viewing Logs

**Option 1: Google Cloud Console**
```
1. Go to Cloud Console → Cloud Run
2. Select jarvis-intelligence-service
3. Click "LOGS" tab
```

**Option 2: gcloud CLI**
```bash
# Real-time logs
gcloud run services logs tail jarvis-intelligence-service --region=asia-southeast1

# Filter by severity
gcloud run services logs read jarvis-intelligence-service \
  --region=asia-southeast1 \
  --filter="severity=ERROR"
```

**Option 3: Cloud Build Logs**
```bash
# View build history
gcloud builds list --limit=10

# View specific build logs
gcloud builds log BUILD_ID
```

### Key Metrics to Monitor

1. **Request latency**: Response time for API calls
2. **Error rate**: 5xx errors indicate service issues
3. **Instance count**: Number of running containers
4. **Memory usage**: If high, may need to increase allocation
5. **Cold starts**: Frequency of container initialization

### Setting Up Alerts

```bash
# Example: Alert on high error rate
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="High Error Rate" \
  --condition-threshold-value=5 \
  --condition-threshold-duration=60s
```

---

## Troubleshooting

### Common Issues

#### 1. Build Fails

**Symptom**: Cloud Build shows red X

**Check**:
```bash
# View build logs
gcloud builds list
gcloud builds log <BUILD_ID>
```

**Common causes**:
- Syntax error in `cloudbuild.yaml`
- Dockerfile errors
- Missing dependencies in `requirements.txt`

**Fix**: Review logs, fix errors, push again

---

#### 2. Deployment Fails

**Symptom**: Build succeeds but deployment fails

**Check**:
```bash
# Check Cloud Run service status
gcloud run services describe jarvis-intelligence-service --region=asia-southeast1
```

**Common causes**:
- Container port mismatch (should be 8080)
- Missing environment variables
- Health check failing (app not starting)

**Fix**: Ensure `Dockerfile` exposes port 8080 and app binds to `0.0.0.0:8080`

---

#### 3. Service Returns 500 Errors

**Symptom**: API returns internal server errors

**Check**:
```bash
# View application logs
gcloud run services logs tail jarvis-intelligence-service --region=asia-southeast1
```

**Common causes**:
- Missing or incorrect secrets
- Database connection failure
- API key invalid

**Fix**: Verify secrets in Secret Manager, check database connectivity

---

#### 4. Secrets Not Working

**Symptom**: App crashes with "API key not found" or similar

**Check**:
```bash
# List secrets
gcloud secrets list

# View secret versions
gcloud secrets versions list SECRET_NAME

# Check IAM permissions
gcloud secrets get-iam-policy SECRET_NAME
```

**Fix**: Ensure Cloud Run service account has `secretAccessor` role

---

#### 5. Service is Slow

**Symptom**: API responses take > 5 seconds

**Possible causes**:
- **Cold starts**: First request after idle period
- **Insufficient resources**: Need more CPU/memory
- **Database latency**: Supabase connection slow

**Solutions**:
```bash
# Increase memory (reduces cold starts)
gcloud run services update jarvis-intelligence-service \
  --memory=1Gi \
  --region=asia-southeast1

# Set minimum instances (eliminates cold starts)
gcloud run services update jarvis-intelligence-service \
  --min-instances=1 \
  --region=asia-southeast1
```

**Note**: Minimum instances cost money even when idle

---

### Rollback to Previous Version

If a deployment breaks production:

```bash
# List revisions
gcloud run revisions list --service=jarvis-intelligence-service --region=asia-southeast1

# Route traffic to previous revision
gcloud run services update-traffic jarvis-intelligence-service \
  --to-revisions=PREVIOUS_REVISION=100 \
  --region=asia-southeast1
```

---

## Best Practices

### 1. Use Versioned Tags

Instead of `:latest`, use semantic versioning:
```yaml
# In cloudbuild.yaml
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '-t', 'gcr.io/$PROJECT_ID/jarvis-intelligence-service:v1.2.3', '.']
```

### 2. Health Checks

Ensure your app has a health endpoint:
```python
@app.get("/health")
async def health():
    return {"status": "healthy"}
```

Cloud Run uses this to verify the service is ready.

### 3. Structured Logging

Use JSON logging for better log analysis:
```python
import json
logger.info(json.dumps({
    "event": "request_processed",
    "transcript_id": transcript_id,
    "duration_ms": duration
}))
```

### 4. Graceful Shutdown

Handle SIGTERM to finish processing before shutdown:
```python
import signal
import sys

def handle_sigterm(*args):
    logger.info("Received SIGTERM, shutting down gracefully")
    # Clean up resources
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)
```

### 5. Resource Limits

Set appropriate CPU and memory:
```bash
gcloud run services update jarvis-intelligence-service \
  --cpu=2 \
  --memory=2Gi \
  --region=asia-southeast1
```

### 6. Concurrency Settings

Control requests per container:
```bash
gcloud run services update jarvis-intelligence-service \
  --concurrency=80 \
  --region=asia-southeast1
```

---

## Cost Optimization

### Understanding Costs

Cloud Run pricing:
- **vCPU-seconds**: CPU time used
- **GiB-seconds**: Memory time used
- **Requests**: Number of requests
- **Networking**: Egress traffic

### Free Tier (per month)
- 2M requests
- 360,000 vCPU-seconds
- 180,000 GiB-seconds
- 1 GB egress

### Reducing Costs

1. **Scale to zero**: Don't set `--min-instances` unless needed
2. **Right-size resources**: Don't over-provision CPU/memory
3. **Optimize cold starts**: Keep Docker image small
4. **Cache responses**: Reduce processing time
5. **Use Cloud CDN**: For static content

---

## Next Steps

- **Learn more**: [Cloud Run documentation](https://cloud.google.com/run/docs)
- **Monitor costs**: [Cloud Billing reports](https://console.cloud.google.com/billing)
- **Set budgets**: [Budget alerts](https://cloud.google.com/billing/docs/how-to/budgets)
- **Explore metrics**: [Cloud Monitoring](https://console.cloud.google.com/monitoring)

For the complete ecosystem architecture (all 4 services), see [ECOSYSTEM_ARCHITECTURE.md](./ECOSYSTEM_ARCHITECTURE.md).
