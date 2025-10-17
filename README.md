# Leaderboard System

This project is a cloud-native, production-ready implementation of a high-throughput leaderboard system based on the Lambda Architecture. It is designed to run on Google Cloud Platform (GCP) and leverages Kubernetes for orchestration.

It provides two pipelines for processing events:
1.  **Real-time Approximate Pipeline**: Uses a Count-Min Sketch algorithm to provide fast, low-latency, approximate leaderboard results.
2.  **Batch Exact Pipeline**: A periodic batch job that computes perfectly accurate leaderboards.

## Architecture

The system is designed to run as a distributed application on Google Kubernetes Engine (GKE).

-   **Orchestration**: Google Kubernetes Engine (GKE) runs the application services as scalable, resilient deployments.
-   **Event Streaming**: A managed Kafka cluster handles the ingestion of high-volume event data.
-   **Data Storage**: Google Cloud Storage (GCS) serves as the data lake, storing batch files and the state of the Count-Min Sketch.

### Services
-   `event-publisher`: A service to generate and publish events to the Kafka topic.
-   `realtime-processor`: Consumes events from Kafka in real-time and continuously updates the Count-Min Sketch in GCS.
-   `batch-processor`: Runs as a periodic CronJob in Kubernetes, consuming events from Kafka to compute exact counts and storing the results in GCS.
-   `leaderboard-api`: A service that provides leaderboard data by querying GCS. It also exposes a `/metrics` endpoint for Prometheus monitoring.

## Getting Started

### Prerequisites

-   Python 3.11+
-   Docker and Docker Compose
-   Google Cloud SDK (`gcloud`)
-   Terraform
-   `kubectl`

### 1. Provision Cloud Infrastructure

The infrastructure is defined as code using Terraform. First, you must configure your GCP credentials for Terraform.

1.  **Configure Variables**:
    -   Navigate to the `terraform/` directory.
    -   Rename `variables.tf.example` to `variables.tf` (or create it).
    -   Fill in the placeholder values for `gcp_project_id` and any other variables.

2.  **Apply Terraform**:
    From within the `terraform/` directory, run:
    ```sh
    terraform init
    terraform plan
    terraform apply
    ```
    Take note of the outputs, such as the GCS bucket name, which you will need later.

### 2. Build and Push the Docker Image

Your GKE cluster needs access to the application's Docker image. You must build it and push it to a container registry like Google Container Registry (GCR) or Artifact Registry.

1.  **Enable the registry service** for your GCP project.
2.  **Configure Docker authentication**:
    ```sh
    gcloud auth configure-docker
    ```
3.  **Build, tag, and push the image** (replace `your-gcp-project-id` and `leaderboard`):
    ```sh
    docker build -t gcr.io/your-gcp-project-id/leaderboard:latest .
    docker push gcr.io/your-gcp-project-id/leaderboard:latest
    ```

## Running the System

### Deploying to Kubernetes (GKE)

1.  **Configure `kubectl`** to connect to your new GKE cluster:
    ```sh
    gcloud container clusters get-credentials <your-cluster-name> --region <your-cluster-region>
    ```

2.  **Configure the Application**:
    -   In the `k8s/` directory, edit `configmap.yaml`.
    -   Replace the placeholder values for `GCS_BUCKET_NAME` and `KAFKA_BROKERS` with your actual resource details.

3.  **Update the Image Path**:
    -   In `k8s/deployment.yaml`, replace the placeholder image URL (`gcr.io/your-gcp-project-id/leaderboard:latest`) with the actual path to your container image.

4.  **Deploy the Application**:
    ```sh
    kubectl apply -f k8s/configmap.yaml
    kubectl apply -f k8s/deployment.yaml
    ```
    Your services will now be running in the GKE cluster.

### Local Development with Docker Compose

You can run the services locally against your provisioned cloud infrastructure using Docker Compose.

1.  **Create an environment file**:
    -   Copy `.env.example` to a new file named `.env`.
    -   Fill in the values for your GCP project, GCS bucket, and Kafka brokers.

2.  **Launch the services**:
    ```sh
    docker-compose up --build
    ```
    This will start the `leaderboard-api` and `realtime-processor`.

3.  **Run other services on demand**:
    -   To publish an event:
        ```sh
        docker-compose run --rm event-publisher my_event_1
        ```
    -   To run a batch processing job:
        ```sh
        docker-compose run --rm batch-processor
        ```

## Testing

To run the automated tests, use `pytest`:

```sh
pytest
```

## CI/CD

A Continuous Integration pipeline is defined in `.github/workflows/ci.yml`. It automatically runs the linter and tests on every push and pull request to the `main` branch.