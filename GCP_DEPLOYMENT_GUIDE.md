# GCP Deployment Guide for Real-Time Leaderboard

This guide provides step-by-step instructions to deploy the real-time leaderboard application on Google Cloud Platform (GCP).

**Architecture Overview:**
- **GKE:** Hosts the stateless API and processing services.
- **Google Cloud Managed Kafka:** Ingests the real-time event stream.
- **Google Cloud Memorystore (Redis):** Stores the final leaderboard data for fast reads.
- **Google Cloud Dataflow:** Runs a continuous streaming pipeline to process events from Kafka and update the Redis leaderboard.
- **GCS:** Stores the real-time Count-Min Sketch state and serves as a staging area for Dataflow.

## 1. Prerequisites

- A GCP account with billing enabled.
- `gcloud` CLI, `terraform`, `docker`, and `kubectl` installed.

## 2. GCP Project Setup

1.  **Create and Configure Your Project:** Replace `YOUR_PROJECT_ID` and `YOUR_BILLING_ACCOUNT_ID`.
    ```bash
    export PROJECT_ID="YOUR_PROJECT_ID"
    gcloud projects create $PROJECT_ID --name="Leaderboard Project"
    gcloud config set project $PROJECT_ID
    gcloud billing projects link $PROJECT_ID --billing-account=YOUR_BILLING_ACCOUNT_ID
    ```

2.  **Grant Permissions:** Grant your user account permissions to enable APIs. Replace `YOUR_EMAIL_ADDRESS`.
    ```bash
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="user:YOUR_EMAIL_ADDRESS" \
        --role="roles/serviceusage.serviceUsageAdmin"
    ```

## 3. Infrastructure Provisioning with Terraform

This step uses Terraform to provision all the necessary cloud infrastructure.

1.  **Initialize Terraform:**
    ```bash
    cd terraform
    terraform init
    ```

2.  **Apply Terraform Configuration:** This will provision the GKE cluster, Kafka, Redis, and GCS buckets. It may take several minutes.
    ```bash
    terraform apply -var="gcp_project_id=$PROJECT_ID" -var="gcs_bucket_name=your-unique-bucket-name"
    ```

## 4. Application Deployment

### 4.1. Build and Push the Master Docker Image

Since the Python code contains all services (API, real-time processor, Dataflow pipeline), you only need to build one master image.

```bash
# In the project root directory
docker buildx create --use
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t gcr.io/$PROJECT_ID/leaderboard:latest \
  --push .
```

### 4.2. Configure and Deploy GKE Services

1.  **Connect `kubectl` to GKE:**
    ```bash
    gcloud container clusters get-credentials leaderboard-cluster --zone us-central1-c
    ```

2.  **Gather Terraform Outputs:** Collect the connection details from your infrastructure.
    ```bash
    cd terraform
    export KAFKA_BOOTSTRAP_SERVERS=$(terraform output -raw kafka_bootstrap_address)
    export REDIS_HOST=$(terraform output -raw redis_host)
    export REDIS_PORT=$(terraform output -raw redis_port)
    export GCS_BUCKET_NAME=$(terraform output -raw gcs_bucket_name)
    cd ..
    ```

3.  **Update and Apply `ConfigMap`:** This script injects the connection details into your Kubernetes configuration.
    ```bash
    # For macOS
    sed -i.bak "s|<kafka-bootstrap-address>|$KAFKA_BOOTSTRAP_SERVERS|g" k8s/configmap.yaml
    sed -i.bak "s|<redis-host>|$REDIS_HOST|g" k8s/configmap.yaml
    sed -i.bak "s|<redis-port>|$REDIS_PORT|g" k8s/configmap.yaml

    # For Linux, remove .bak
    # sed -i "s|<kafka-bootstrap-address>|$KAFKA_BOOTSTRAP_SERVERS|g" k8s/configmap.yaml
    # ...etc

    kubectl apply -f k8s/configmap.yaml
    ```

4.  **Deploy the GKE Applications:**
    ```bash
    kubectl apply -f k8s/deployment.yaml
    ```

5.  **Verify GKE Deployments:** Check that the `leaderboard-api`, `realtime-processor`, and `event-publisher` pods are `Running`.
    ```bash
    kubectl get pods -w
    ```

### 4.3. Launch the Streaming Dataflow Pipeline

This final step launches the continuous pipeline that powers the main leaderboard.

1.  **Gather Dataflow Configuration:**
    ```bash
    cd terraform
    export STAGING_BUCKET_NAME=$(terraform output -raw dataflow_staging_bucket_name)
    export DATAFLOW_SA_EMAIL=$(gcloud iam service-accounts list --filter="displayName:'Service Account for Leaderboard App'" --format="value(email)")
    cd ..
    ```

2.  **Run the Pipeline:**
    ```bash
    python3 -m src.dataflow.batch_pipeline \
        --runner=DataflowRunner \
        --project=$GCP_PROJECT_ID \
        --region=$REGION \
        --temp_location=gs://$STAGING_BUCKET_NAME/temp \
        --service_account_email=$DATAFLOW_SA_EMAIL \
        --ip_configuration=WORKER_IP_PRIVATE \
        --tags=dataflow \
        --network=leaderboard-vpc \
        --subnetwork=regions/$REGION/subnetworks/leaderboard-subnet \
        --streaming \
        --kafka_bootstrap_servers=$KAFKA_BOOTSTRAP_SERVERS \
        --redis_host=$REDIS_HOST \
        --redis_port=$REDIS_PORT \
        --dead_letter_gcs_path=gs://$STAGING_BUCKET_NAME/dead_letter/errors
    ```

## 5. Testing the System

1.  **Monitor the Dataflow Job:** In the GCP Console, navigate to **Dataflow -> Jobs** to see your pipeline running and processing data.

2.  **Get the API External IP:**
    ```bash
    export API_IP=$(kubectl get service leaderboard-api-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
    echo "API IP Address: $API_IP"
    ```

3.  **Query the Leaderboard:** The Dataflow pipeline updates the leaderboard hourly. After the first hour, you can query the main endpoint.
    ```bash
    curl http://$API_IP/leaderboard?k=5
    ```

4.  **Query Approximate Results:** Get real-time estimates for specific events by pulling IDs from the publisher logs.
    ```bash
    # In one terminal, watch the publisher
    kubectl logs -f deployment/event-publisher

    # In another terminal, query for an ID you see
    curl "http://$API_IP/leaderboard/approximate?event_ids=YOUR_EVENT_ID_HERE"
    ```

## 6. Cleanup

To avoid incurring charges, destroy all resources.

1.  **Stop the Dataflow Job:** Find the `JOB_ID` and `drain` it.
    ```bash
    export JOB_ID=$(gcloud dataflow jobs list --region=us-central1 --filter="name:batch-pipeline" --format="value(id)")
    gcloud dataflow jobs drain $JOB_ID --region=us-central1
    ```

2.  **Delete Kubernetes Resources:**
    ```bash
    kubectl delete -f k8s/deployment.yaml
    kubectl delete -f k8s/configmap.yaml
    ```

3.  **Destroy Terraform Infrastructure:**
    ```bash
    cd terraform
    terraform destroy -auto-approve
    ```

4.  **Delete Docker Image:**
    ```bash
    gcloud container images delete gcr.io/$PROJECT_ID/leaderboard:latest --force-delete-tags
    ```