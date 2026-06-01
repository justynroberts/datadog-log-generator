# Operations Runbook — Payment Platform

## Table of Contents

1. [Quick Reference](#quick-reference)
1. [K8s Operations](#k8s-ops)
    1. [Restarting a Pod](#pod-restart)
    1. [Restarting a Rollout](#rollout-restart)
    1. [Rolling Forward via ArgoCD](#rolling-forward)
1. [Payment API Operations](#payment-api-ops)
    1. [Pod CrashLoopBackOff — payment-api](#crashloopbackoff)
    1. [Deployment Rollout Failed — payment-api](#rollout-failed)
    1. [ImagePullBackOff — payment-api](#imagepullbackoff)
1. [Payment Processor Operations](#payment-processor-ops)
    1. [Node NotReady — payment-processor](#node-notready)
    1. [PVC Pending — payment-processor](#pvc-pending)
    1. [HPA Max Replicas — payment-processor](#hpa-max-replicas)
1. [Payment Reconciliation Operations](#payment-recon-ops)
    1. [OOMKilled — payment-reconciliation](#oomkilled)
    1. [Service Endpoint NotReady — payment-reconciliation](#endpoint-notready)
1. [Database Operations](#db-ops)
    1. [Database latency or connection failures](#db-latency)
1. [Miscellaneous](#misc)
    1. [Reverting a Merged PR (emergency rollback)](#revert-pr)
    1. [Escalation Path](#escalation)

## Quick Reference <a name="quick-reference"></a>

| Description | Details |
|-------------|---------|
| Datadog Dashboard | [Payment Platform K8s](https://app.datadoghq.eu/logs?query=kube_namespace%3Aproduction%20service%3Apayment-*) |
| Logging | `cluster=workshop-cluster namespace=production service:payment-*` |
| Monitors | `kube_namespace:production kube_cluster_name:workshop-cluster` |
| ArgoCD | [Payment Apps](https://argocd.internal/applications?namespace=production&search=payment) |
| Cluster | `workshop-cluster` / `us-east-1` |
| Namespace | `production` |
| Services | `payment-api`, `payment-processor`, `payment-reconciliation` |
| Image Registry | `registry.example.com/payment-*:v2.1.0` |
| Team | payments |

## K8s Operations <a name="k8s-ops"></a>

### Restarting a Pod <a name="pod-restart"></a>

To restart a pod, you simply delete it. Go to the ArgoCD UI and find the specific pod you want to restart. Click the 3-dots (or hamburger) on the pod and click delete. Kubernetes will automatically spin up a new pod thus restarting.

Alternatively via kubectl:
```bash
kubectl delete pod <pod-name> -n production --context workshop-cluster
```

### Restarting a Rollout <a name="rollout-restart"></a>

To perform a rolling restart of the entire deployment you must restart the Rollout. Go to the ArgoCD UI and find the rollout of the app you're interested in. Click the 3-dots (or hamburger) on the rollout and click restart. The rollout will restart all of its pods, 1-by-1.

Alternatively via kubectl:
```bash
kubectl rollout restart deployment/<deployment-name> -n production --context workshop-cluster
```

### Rolling Forward via ArgoCD <a name="rolling-forward"></a>

When an issue is caused by a bad deployment and a fix is available, the preferred approach is to **roll forward** rather than roll back. This avoids reverting database migrations, feature flags, or dependent service changes.

**Steps to roll forward:**

1. **Identify the fix** — Confirm a corrective commit exists in the main branch or create a hotfix branch
2. **Merge the fix** — Merge the PR to the main branch. Ensure CI passes
3. **Monitor ArgoCD sync** — ArgoCD will detect the new image tag and begin syncing:
    - Go to [ArgoCD UI](https://argocd.internal/applications?namespace=production&search=payment)
    - Find the relevant payment application (`payment-api`, `payment-processor`, or `payment-reconciliation`)
    - Verify the app status shows **Syncing** or **OutOfSync**
4. **Force sync if needed** — If ArgoCD has not picked up the change automatically:
    - Click the application in ArgoCD
    - Click **Sync** > **Synchronize**
    - Enable **Prune** if old resources need to be cleaned up
    - Enable **Force** only if resources are stuck
5. **Verify the rollout**:
    ```bash
    kubectl rollout status deployment/payment-api -n production --context workshop-cluster
    kubectl get pods -n production -l app=payment-api --context workshop-cluster
    ```
6. **Validate in Datadog** — Confirm error rates are dropping:
    - Search: `cluster=workshop-cluster namespace=production service:payment-api status:error`
    - Check the dashboard for the affected service

**If the roll forward fails:**
- Check ArgoCD Events tab for sync errors
- Check pod Events for image pull or resource issues
- Fall back to [Reverting a Merged PR](#revert-pr) if the fix itself introduces new problems

## Payment API Operations <a name="payment-api-ops"></a>

### Pod CrashLoopBackOff — payment-api <a name="crashloopbackoff"></a>

**Severity:** Critical

**What it means:** The payment-api container (`api-server`) is repeatedly crashing and Kubernetes is backing off restart attempts. The exit code and restart count indicate the severity.

**Datadog search:**
```
cluster=workshop-cluster namespace=production service:payment-api CrashLoopBackOff
```

**Diagnosis:**

1. Check the pod events and logs in ArgoCD:
    - Go to [ArgoCD](https://argocd.internal/applications?namespace=production&search=payment-api)
    - Find the crashing pod (e.g. `payment-api-7d4f8c9b5-x2k9m`)
    - Check the **Events** tab for `BackOff` and `Failed` events
    - Check the **Logs** tab for application errors before the crash
2. Check restart count and exit code:
    ```bash
    kubectl describe pod payment-api-7d4f8c9b5-x2k9m -n production --context workshop-cluster
    ```
    - `exit_code=1` — Application error (check logs)
    - `exit_code=137` — OOMKilled (see [OOMKilled](#oomkilled))
    - `exit_code=143` — SIGTERM (graceful shutdown failed)
3. Check if a recent deployment caused the issue:
    ```bash
    kubectl rollout history deployment/payment-api -n production --context workshop-cluster
    ```

**Resolution — Roll Forward:**

1. Identify the root cause from the logs (e.g. missing env var, bad config, dependency failure)
2. Create and merge a fix to the main branch
3. Follow the [Rolling Forward via ArgoCD](#rolling-forward) procedure
4. Verify the pod stabilises and restart count stops increasing:
    ```bash
    kubectl get pods -n production -l app=payment-api -w --context workshop-cluster
    ```

**Short-term mitigation:** If the fix is not immediately available, restart the rollout to buy time:
```bash
kubectl rollout restart deployment/payment-api -n production --context workshop-cluster
```

### Deployment Rollout Failed — payment-api <a name="rollout-failed"></a>

**Severity:** Error

**What it means:** The payment-api deployment has exceeded its progress deadline. Desired replicas (5) are not available — only a subset (0-2) are running. This typically means new pods cannot start.

**Datadog search:**
```
cluster=workshop-cluster namespace=production service:payment-api ProgressDeadlineExceeded
```

**Diagnosis:**

1. Check the deployment status:
    ```bash
    kubectl describe deployment payment-api-deploy -n production --context workshop-cluster
    ```
    Look for `Conditions` — specifically `Progressing=False` with reason `ProgressDeadlineExceeded`
2. Check pending pods for issues:
    ```bash
    kubectl get pods -n production -l app=payment-api --context workshop-cluster
    kubectl describe pod <pending-pod-name> -n production --context workshop-cluster
    ```
3. Common causes:
    - Image pull failures (see [ImagePullBackOff](#imagepullbackoff))
    - Insufficient cluster resources (CPU/memory)
    - Failing readiness probes
    - Bad application config in the new version

**Resolution — Roll Forward:**

1. Fix the underlying issue (image tag, resource requests, probe config, or application bug)
2. Merge the fix and follow [Rolling Forward via ArgoCD](#rolling-forward)
3. Monitor the rollout:
    ```bash
    kubectl rollout status deployment/payment-api-deploy -n production --context workshop-cluster
    ```
4. Confirm all 5 replicas are available:
    ```bash
    kubectl get deployment payment-api-deploy -n production --context workshop-cluster
    ```

### ImagePullBackOff — payment-api <a name="imagepullbackoff"></a>

**Severity:** Warning

**What it means:** Kubernetes cannot pull the container image `registry.example.com/payment-api:v2.1.0`. This prevents new pods from starting and will block deployments.

**Datadog search:**
```
cluster=workshop-cluster namespace=production service:payment-api ImagePullBackOff
```

**Diagnosis:**

1. Check the pod events:
    ```bash
    kubectl describe pod payment-api-6c9d2f4a1-j8n3p -n production --context workshop-cluster
    ```
    Look for `Failed to pull image: unauthorized` or `image not found`
2. Common causes:
    - Image tag does not exist in the registry
    - Registry credentials have expired or are misconfigured
    - Registry is experiencing an outage
    - Typo in image name or tag

**Resolution — Roll Forward:**

1. If the image tag is wrong — fix the image tag in the deployment manifest and merge
2. If registry credentials expired — rotate the `imagePullSecret` in the namespace:
    ```bash
    kubectl get secrets -n production --context workshop-cluster | grep registry
    ```
3. If the image was never pushed — ensure the CI pipeline built and pushed the image, then re-sync in ArgoCD
4. Follow [Rolling Forward via ArgoCD](#rolling-forward) once the fix is in place

## Payment Processor Operations <a name="payment-processor-ops"></a>

### Node NotReady — payment-processor <a name="node-notready"></a>

**Severity:** Critical

**What it means:** A worker node (e.g. `worker-node-3a7f2`) hosting payment-processor pods has become NotReady. The kubelet is not responding and pods on this node may be evicted or unreachable.

**Datadog search:**
```
cluster=workshop-cluster namespace=production service:payment-processor NotReady
```

**Diagnosis:**

1. Check node status:
    ```bash
    kubectl get nodes --context workshop-cluster
    kubectl describe node worker-node-3a7f2 --context workshop-cluster
    ```
    Look for `Conditions` — `Ready=Unknown` or `Ready=False`
2. Check if pods have been rescheduled:
    ```bash
    kubectl get pods -n production -l app=payment-processor -o wide --context workshop-cluster
    ```
3. Check cloud provider console for the underlying instance health

**Resolution — Roll Forward:**

1. If the node is recoverable — the cloud provider may auto-heal it. Monitor for 5 minutes
2. If pods need rescheduling — Kubernetes will automatically reschedule pods to healthy nodes if the node remains NotReady beyond the `pod-eviction-timeout`
3. If the node pool needs scaling — add nodes via the cloud provider or update the node pool configuration and push through ArgoCD
4. To force pod rescheduling immediately:
    ```bash
    kubectl drain worker-node-3a7f2 --ignore-daemonsets --delete-emptydir-data --context workshop-cluster
    ```
5. Verify payment-processor pods are running on healthy nodes:
    ```bash
    kubectl get pods -n production -l app=payment-processor -o wide --context workshop-cluster
    ```

### PVC Pending — payment-processor <a name="pvc-pending"></a>

**Severity:** Warning

**What it means:** The PersistentVolumeClaim `data-volume-payment-processor` cannot be provisioned. Storage class `gp3` failed to provision the requested `100Gi` volume. Pods depending on this PVC will not start.

**Datadog search:**
```
cluster=workshop-cluster namespace=production service:payment-processor PVC Pending ProvisioningFailed
```

**Diagnosis:**

1. Check PVC status:
    ```bash
    kubectl get pvc -n production --context workshop-cluster
    kubectl describe pvc data-volume-payment-processor -n production --context workshop-cluster
    ```
2. Check events for provisioning errors
3. Common causes:
    - Storage quota exceeded in the region
    - Storage class `gp3` misconfigured or unavailable
    - Availability zone mismatch between node and volume

**Resolution — Roll Forward:**

1. If quota exceeded — request a quota increase or reduce the requested size in the PVC manifest
2. If storage class issue — fix the storage class configuration and push via ArgoCD
3. If AZ mismatch — update node affinity or storage topology constraints
4. Merge the fix and follow [Rolling Forward via ArgoCD](#rolling-forward)

### HPA Max Replicas — payment-processor <a name="hpa-max-replicas"></a>

**Severity:** Warning

**What it means:** The HorizontalPodAutoscaler `payment-processor-autoscaler` has scaled to its maximum (10 replicas) and CPU utilisation remains above 90%. The service cannot scale further to handle load.

**Datadog search:**
```
cluster=workshop-cluster namespace=production service:payment-processor HPA ScalingLimited
```

**Diagnosis:**

1. Check HPA status:
    ```bash
    kubectl get hpa -n production --context workshop-cluster
    kubectl describe hpa payment-processor-autoscaler -n production --context workshop-cluster
    ```
2. Check current CPU utilisation and pod count
3. Determine if load increase is expected (peak hours, batch jobs) or anomalous

**Resolution — Roll Forward:**

1. If sustained load — increase `maxReplicas` in the HPA manifest (e.g. from 10 to 20)
2. If resource-bound — increase CPU requests/limits per pod in `values.yaml`
3. Merge the change and follow [Rolling Forward via ArgoCD](#rolling-forward)
4. Monitor the HPA scaling:
    ```bash
    kubectl get hpa payment-processor-autoscaler -n production -w --context workshop-cluster
    ```

## Payment Reconciliation Operations <a name="payment-recon-ops"></a>

### OOMKilled — payment-reconciliation <a name="oomkilled"></a>

**Severity:** Critical

**What it means:** The reconciliation worker container is being killed by the kernel because it exceeded its memory limit of `512Mi` (usage peaked at `548Mi`+). Exit code `137` confirms the OOM kill. Reconciliation jobs will fail and retry.

**Datadog search:**
```
cluster=workshop-cluster namespace=production service:payment-reconciliation OOMKilled
```

**Diagnosis:**

1. Check the killed pod:
    ```bash
    kubectl describe pod payment-reconciliation-5b8c1d3e7-q4w2r -n production --context workshop-cluster
    ```
    Look for `Last State: Terminated` with `Reason: OOMKilled` and `Exit Code: 137`
2. Check memory usage trends in Datadog — is this a gradual leak or a spike?
3. Check if recent reconciliation runs are processing larger datasets than usual

**Resolution — Roll Forward:**

1. **Short term** — Increase the memory limit from `512Mi` to `768Mi` or `1Gi` in the job/cronjob manifest
2. **Long term** — Investigate the memory usage pattern:
    - If a leak — identify and fix in application code
    - If dataset growth — implement pagination or streaming in the reconciliation logic
3. Merge the fix and follow [Rolling Forward via ArgoCD](#rolling-forward)
4. Monitor the next reconciliation run:
    ```bash
    kubectl get pods -n production -l app=payment-reconciliation -w --context workshop-cluster
    ```

### Service Endpoint NotReady — payment-reconciliation <a name="endpoint-notready"></a>

**Severity:** Error

**What it means:** The service `payment-reconciliation-svc` has 0 out of 3 endpoints ready on port `8080`. No traffic can be routed to the reconciliation service. This is often a downstream effect of pods crashing (CrashLoopBackOff, OOMKilled) or failing readiness probes.

**Datadog search:**
```
cluster=workshop-cluster namespace=production service:payment-reconciliation EndpointNotReady
```

**Diagnosis:**

1. Check endpoint status:
    ```bash
    kubectl get endpoints payment-reconciliation-svc -n production --context workshop-cluster
    ```
2. Check the backing pods:
    ```bash
    kubectl get pods -n production -l app=payment-reconciliation --context workshop-cluster
    ```
3. If pods are running but not ready — check readiness probe configuration and application health endpoint
4. If pods are crashing — see [OOMKilled](#oomkilled) or check pod logs

**Resolution — Roll Forward:**

1. Fix the underlying pod issue (OOM, crash, probe misconfiguration)
2. Merge the fix and follow [Rolling Forward via ArgoCD](#rolling-forward)
3. Verify endpoints become ready:
    ```bash
    kubectl get endpoints payment-reconciliation-svc -n production -w --context workshop-cluster
    ```
4. Confirm ready endpoints returns to 3/3

## Database Operations <a name="db-ops"></a>

### Database latency or connection failures <a name="db-latency"></a>

High database latency or connection failures can cascade across all three payment services, causing job failures in the processor, reconciliation timeouts, and slow API responses.

**Datadog search:**
```
cluster=workshop-cluster namespace=production service:payment-* ("Database connection" OR "deadlock" OR "query timeout")
```

**Diagnosis:**

1. Check Datadog for database metrics — connection pool usage, query latency, error rates
2. Check if a specific query pattern is causing lock contention
3. Review recent deployments for query changes

**Resolution:**

1. If connection pool exhaustion — increase pool size in application config and roll forward via ArgoCD
2. If slow queries — add indexes or optimise queries, merge and roll forward
3. If database resource constraints — scale the database instance via infrastructure config

## Miscellaneous <a name="misc"></a>

### Reverting a Merged PR (emergency rollback) <a name="revert-pr"></a>

If a roll forward is not possible and the issue is caused by a recent merge, revert the PR:

1. Go to the merged PR in GitHub
2. Click **Revert** to create a revert PR
3. Merge the revert PR — CI will build a new image
4. ArgoCD will detect the new image and sync automatically
5. If ArgoCD does not sync — force sync from the ArgoCD UI
6. Verify the rollback:
    ```bash
    kubectl rollout status deployment/<deployment-name> -n production --context workshop-cluster
    ```

**Note:** Always prefer [Rolling Forward](#rolling-forward) over reverting. Reverts can cause issues with database migrations, feature flags, and dependent services.

### Escalation Path <a name="escalation"></a>

| Level | Who | When |
|-------|-----|------|
| L1 | On-call engineer (payments team) | First responder — follow this runbook |
| L2 | Payments team lead | If issue persists after 15 minutes |
| L3 | Platform engineering | If cluster-level or infrastructure issue |
