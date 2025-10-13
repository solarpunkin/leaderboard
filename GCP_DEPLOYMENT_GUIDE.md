# GCP Deployment Guide for Real-Time Leaderboard

This guide provides step-by-step instructions to deploy the real-time leaderboard application on Google Cloud Platform (GCP) using the native Google Cloud Managed Service for Apache Kafka.

## 1. Prerequisites

- **GCP Account:** You need a GCP account with billing enabled.
- **gcloud CLI:** Install and initialize the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install).
- **Terraform:** Install [Terraform](https://learn.hashicorp.com/tutorials/terraform/install-cli).
- **Docker:** Install [Docker](https://docs.docker.com/get-docker/).
- **kubectl:** Install the [Kubernetes command-line tool](https://kubernetes.io/docs/tasks/tools/install-kubectl-gcloud/).

## 2. GCP Project Setup

1.  **Create a GCP Project:**
    ```bash
    gcloud projects create YOUR_PROJECT_ID --name="Leaderboard Project"
    ```

2.  **Set the Project:**
    ```bash
    gcloud config set project YOUR_PROJECT_ID
    ```

3.  **Link Billing Account:**
    ```bash
    gcloud billing projects link YOUR_PROJECT_ID --billing-account=YOUR_BILLING_ACCOUNT_ID
    ```

## 3. Infrastructure Provisioning with Terraform

1.  **Initialize Terraform:**
    ```bash
    cd terraform
    terraform init
    ```

2.  **Apply Terraform Configuration:**
    ```bash
    terraform apply -var="gcp_project_id=YOUR_PROJECT_ID" -var="gcs_bucket_name=your-unique-bucket-name"
    ```
    - This will provision the GKE cluster, GCS bucket, and the Google Cloud Managed Kafka cluster.

3.  **Get Kafka Bootstrap Address:**
    - After Terraform has finished, get the Kafka bootstrap address from the output. You will need this for the next steps.
    ```bash
    cd terraform
    export KAFKA_BOOTSTRAP_ADDRESS=$(terraform output -raw kafka_bootstrap_address)
    echo "Kafka Bootstrap Address: $KAFKA_BOOTSTRAP_ADDRESS"
    ```

## 4. Build and Push Docker Image

### 4.1. Configure Docker for GCP
This command configures the Docker CLI to authenticate with Google Container Registry (GCR).
```bash
gcloud auth configure-docker gcr.io
```

### 4.2. Build and Push the Image (Multi-Architecture)

Your GKE cluster nodes run on `linux/amd64` architecture, but your local machine might be different (e.g., an Apple Silicon Mac is `linux/arm64`). To ensure your image runs correctly on the cluster, it's best to build a multi-architecture image.

1.  **Enable Docker Buildx:**
    ```bash
    docker buildx create --use
    ```

2.  **Build and Push the Multi-arch Image:**
    This command builds the image for both `amd64` and `arm64` platforms and pushes them to GCR under a single tag.
    ```bash
    docker buildx build \
      --platform linux/amd64,linux/arm64 \
      -t gcr.io/YOUR_PROJECT_ID/leaderboard:latest \
      --push .
    ```
    - **Note:** Replace `YOUR_PROJECT_ID` with your actual GCP Project ID.

## 5. Kubernetes Deployment

This section guides you through deploying the containerized application to your GKE cluster.

### 5.1. Connect to the GKE Cluster

First, configure `kubectl` to communicate with your new GKE cluster.

```bash
gcloud container clusters get-credentials leaderboard-cluster --zone us-central1-c --project YOUR_PROJECT_ID
```
- **Explanation:** This command fetches the cluster endpoint and authentication data and creates a `kubeconfig` file that `kubectl` uses to connect to your cluster.

### 5.2. Update Kubernetes Configuration Files

The Kubernetes manifest files (`k8s/configmap.yaml` and `k8s/deployment.yaml`) contain placeholders that need to be replaced with your specific project details. The following script will automate this process.

```bash
# Set your GCP Project ID and GCS Bucket Name
export GCP_PROJECT_ID=$(gcloud config get-value project)
export GCS_BUCKET_NAME="your-unique-bucket-name" # Use the same bucket name as in the terraform apply command

# Verify that the KAFKA_BOOTSTRAP_ADDRESS is set from the previous step
if [ -z "$KAFKA_BOOTSTRAP_ADDRESS" ]; then
    echo "KAFKA_BOOTSTRAP_ADDRESS environment variable is not set. Please get it from terraform output."
    exit 1
fi

echo "Using GCP Project ID: $GCP_PROJECT_ID"
echo "Using GCS Bucket Name: $GCS_BUCKET_NAME"
echo "Using Kafka Bootstrap Address: $KAFKA_BOOTSTRAP_ADDRESS"

# Replace placeholders in configmap.yaml
sed -i.bak "s|<your-gcp-project-id>|$GCP_PROJECT_ID|g" k8s/configmap.yaml
sed -i.bak "s|<your-gcs-bucket-name>|$GCS_BUCKET_NAME|g" k8s/configmap.yaml
sed -i.bak "s|<kafka-bootstrap-address>|$KAFKA_BOOTSTRAP_ADDRESS|g" k8s/configmap.yaml

# Replace placeholders in deployment.yaml
sed -i.bak "s|<your-gcp-project-id>|$GCP_PROJECT_ID|g" k8s/deployment.yaml

echo "Kubernetes files have been updated."
```
- **Explanation:** This script uses `sed` to perform an in-place replacement of the placeholder values. It replaces `<your-gcp-project-id>`, `<your-gcs-bucket-name>`, and `<kafka-bootstrap-address>` with the actual values from your environment. Backup files with a `.bak` extension will be created.

### 5.3. Apply the Kubernetes Manifests

Deploy the application components to your GKE cluster.

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
```
- **Explanation:** This command instructs Kubernetes to create or update the resources defined in the YAML files.

### 5.4. Forcing an Update (If Re-Deploying)

If you are deploying a new version of your Docker image using the same tag (e.g., `:latest`), Kubernetes might not automatically pull the new image. You can force a rolling update to ensure your new image is used.

```bash
kubectl rollout restart deployment realtime-processor
kubectl rollout restart deployment leaderboard-api
kubectl rollout restart deployment event-publisher
```
- **Explanation:** This command safely terminates your existing pods and replaces them with new ones, which forces GKE to pull the latest version of your image from the registry.

### 5.5. Verify the Deployment

Check that all the application pods are running correctly.

```bash
kubectl get pods -w
```
- **Explanation:** The `-w` flag watches for changes. Wait until the `STATUS` for all pods (`leaderboard-api`, `realtime-processor`, and `event-publisher`) shows `Running`. This might take a few minutes as GKE pulls the Docker image.

You can also check the logs for each service to ensure they started without errors.
```bash
# Get the name of one of the realtime-processor pods
REALTIME_POD=$(kubectl get pods -l app=realtime-processor -o jsonpath='{.items[0].metadata.name}')
kubectl logs -f $REALTIME_POD

# Get the name of one of the event-publisher pods
PUBLISHER_POD=$(kubectl get pods -l app=event-publisher -o jsonpath='{.items[0].metadata.name}')
kubectl logs -f $PUBLISHER_POD
```
- **Explanation:** These commands find a pod for a given application and stream its logs to your terminal. You should see the `realtime-processor` connecting to Kafka and the `event-publisher` publishing events.

## 6. Accessing and Testing the Leaderboard

### 6.1. Get the API Service External IP

To access the leaderboard API from outside the cluster, you need the external IP address assigned to the LoadBalancer service.

```bash
kubectl get service leaderboard-api-service
```
- **Explanation:** This command shows the status of your services. It may take a few minutes for the `EXTERNAL-IP` to change from `<pending>` to an actual IP address. Re-run the command until you see the IP.

### 6.2. Query the Leaderboard API

Once the `EXTERNAL-IP` is available, you can query the leaderboard.

```bash
export API_IP=$(kubectl get service leaderboard-api-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
curl http://$API_IP/leaderboard?k=5
```
- **Explanation:** This command queries the `/leaderboard` endpoint to get the top 5 events. Initially, this may return an empty list.

### 6.3. Understanding the Data Flow

- The `event-publisher` deployment is continuously creating new events and publishing them to Kafka.
- The `realtime-processor` is consuming these events to update the Count-Min Sketch for real-time estimations (though this is not exposed in the current API).
- The `batch-processor` runs as a `CronJob` once every hour to aggregate events and write them to GCS as Parquet files. The leaderboard API reads these files.

To get results from the API, you must wait for at least one batch job to complete. You can check the status of the cronjob:
```bash
kubectl get cronjob batch-processor
```

To test the API without waiting for the hourly schedule, you can manually create a new job from the `CronJob`:
```bash
kubectl create job --from=cronjob/batch-processor manual-batch-1
```
- **Explanation:** This command triggers the batch processing job immediately. Wait a minute or two for the job to complete, and then query the API again. You should now see the top-K results.

## 7. Cleanup

To avoid incurring charges, delete the resources you created.

1.  **Delete Kubernetes Resources:**
    ```bash
    kubectl delete -f k8s/deployment.yaml
    kubectl delete -f k8s/configmap.yaml
    ```

2.  **Destroy Terraform Infrastructure:**
    ```bash
    cd terraform
    terraform destroy -var="gcp_project_id=YOUR_PROJECT_ID" -var="gcs_bucket_name=your-unique-bucket-name"
    ```

3.  **Delete Docker Image:**
    ```bash
    gcloud container images delete gcr.io/YOUR_PROJECT_ID/leaderboard:latest --force-delete-tags
    ```
