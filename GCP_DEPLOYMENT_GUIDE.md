# Production Deployment Guide for Leaderboard System on GCP

This guide provides a comprehensive, step-by-step methodology for deploying the leaderboard system in a production-grade environment on Google Cloud Platform (GCP). It covers infrastructure provisioning, security, and application deployment best practices.

## The Case for Managed Apache Kafka on GCP

While Google Cloud's native messaging service is Pub/Sub, our application and the original specification are built around the Apache Kafka API. To meet this requirement without incurring significant operational overhead, a **managed Kafka service** is the ideal solution.

**Why a Managed Service?**

-   **Reduced Operational Burden**: Self-hosting Kafka requires deep expertise in cluster management, including setup, scaling, patching, and monitoring of brokers, Zookeeper nodes, and networking. A managed service abstracts this complexity away.
-   **High Availability and Reliability**: Managed providers offer SLAs, automatic failure recovery, and multi-zone replication out of the box, ensuring your event stream is durable and highly available.
-   **Scalability**: Easily scale your Kafka cluster's throughput and storage capacity with a few clicks or an API call, without manual intervention.
-   **Security**: Managed services provide robust, built-in security features, including encryption in transit and at rest, authentication, and authorization.

**Recommended Service: Confluent Cloud on GCP**

**Confluent Cloud** is a fully managed, cloud-native Apache Kafka service available directly on the Google Cloud Marketplace. It is the most common and robust way to run Kafka on GCP.

-   **Seamless Integration**: It integrates natively with GCP billing, networking (VPC Peering), and IAM.
-   **Latest Features**: Always provides the latest, stable versions of Apache Kafka and additional tools like Kafka Connect, ksqlDB, and Schema Registry.

This guide will proceed with the assumption that a Confluent Cloud Kafka cluster has been provisioned.

---

## Phase 1: Production-Grade Infrastructure with Terraform

This phase expands on the Terraform setup to include production-level networking and security.

### Prerequisites
-   A GCP project with billing enabled.
-   `gcloud` CLI installed and authenticated (`gcloud auth login`).
-   Terraform installed.

### Step 1: Define Production-Ready GKE Cluster

Update your `terraform/main.tf` to define a VPC-native GKE cluster. This ensures the cluster has its own isolated network and that pod IPs are native VPC IPs.

```terraform
# In terraform/main.tf

# 1. Dedicated VPC Network
resource "google_compute_network" "vpc_network" {
  name                    = "${var.project_name}-vpc"
  auto_create_subnetworks = false
}

# 2. Subnet for GKE
resource "google_compute_subnetwork" "gke_subnet" {
  name          = "${var.project_name}-gke-subnet"
  ip_cidr_range = "10.10.0.0/24"
  network       = google_compute_network.vpc_network.id
  region        = var.gcp_region
}

# 3. Production GKE Cluster
resource "google_container_cluster" "primary" {
  name     = "${var.project_name}-gke-cluster"
  location = var.gcp_region
  network    = google_compute_network.vpc_network.self_link
  subnetwork = google_compute_subnetwork.gke_subnet.self_link

  initial_node_count = 1

  # Define a specific node pool
  node_pool {
    name       = "default-pool"
    node_count = 2
    node_config {
      machine_type = "e2-medium"
      # Define scopes and the service account for the nodes
      oauth_scopes = [
        "https://www.googleapis.com/auth/cloud-platform"
      ]
    }
  }

  # Enable Workload Identity
  workload_identity_config {
    workload_pool = "${var.gcp_project_id}.svc.id.goog"
  }
}
```

### Step 2: Define Firewall Rules

Create firewall rules to control traffic to and from your GKE nodes.

```terraform
# In a new file, e.g., terraform/networking.tf

resource "google_compute_firewall" "allow_internal" {
  name    = "${var.project_name}-allow-internal"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "all"
  }

  source_ranges = [google_compute_subnetwork.gke_subnet.ip_cidr_range]
}

resource "google_compute_firewall" "allow_egress_internet" {
  name    = "${var.project_name}-allow-egress-internet"
  network = google_compute_network.vpc_network.name
  direction = "EGRESS"

  allow {
    protocol = "all"
  }
  destination_ranges = ["0.0.0.0/0"]
}
```

---

## Phase 2: Secure Credentials with IAM and Workload Identity

Workload Identity is the recommended way to grant Kubernetes pods access to GCP resources without using static service account keys.

### Step 1: Create a GCP Service Account (IAM)

This service account will be used by our application pods.

```bash
# Create the GCP service account
gcloud iam service-accounts create leaderboard-app-sa --display-name="Leaderboard App Service Account"

# Grant it permission to access the GCS bucket
# Replace <GCS_BUCKET_NAME> with your bucket name
gcloud projects add-iam-policy-binding <YOUR_GCP_PROJECT_ID> \
    --member="serviceAccount:leaderboard-app-sa@<YOUR_GCP_PROJECT_ID>.iam.gserviceaccount.com" \
    --role="roles/storage.objectAdmin"
```

### Step 2: Link GCP SA with Kubernetes SA (Workload Identity)

1.  **Create a Kubernetes Service Account** (`k8s/serviceaccount.yaml`):

    ```yaml
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: leaderboard-k8s-sa
      namespace: default
      annotations:
        iam.gke.io/gcp-service-account: leaderboard-app-sa@<YOUR_GCP_PROJECT_ID>.iam.gserviceaccount.com
    ```

2.  **Apply it to the cluster**:
    ```sh
    kubectl apply -f k8s/serviceaccount.yaml
    ```

3.  **Create the IAM Policy Binding**:

    ```bash
    gcloud iam service-accounts add-iam-policy-binding \
        leaderboard-app-sa@<YOUR_GCP_PROJECT_ID>.iam.gserviceaccount.com \
        --role="roles/iam.workloadIdentityUser" \
        --member="serviceAccount:<YOUR_GCP_PROJECT_ID>.svc.id.goog[default/leaderboard-k8s-sa]"
    ```

### Step 3: Update Kubernetes Deployments

Modify your `k8s/deployment.yaml` to use the new Kubernetes service account in the pod spec for each Deployment and CronJob:

```yaml
# In k8s/deployment.yaml, inside each template.spec
      spec:
        serviceAccountName: leaderboard-k8s-sa # Add this line
        containers:
        # ... rest of the container spec
```

---

## Phase 3: Application Deployment

1.  **Build and Push the Docker Image** to GCR or Artifact Registry as described in the `README.md`.

2.  **Update `k8s/configmap.yaml`**:
    -   Fill in the `GCS_BUCKET_NAME` from your Terraform output.
    -   Fill in the `KAFKA_BROKERS` with the connection string from your Confluent Cloud cluster.
    -   You will also need to store the Kafka API key and secret. The best practice is to use Kubernetes secrets, not a ConfigMap.

3.  **Create a Kubernetes Secret for Kafka Credentials**:

    ```bash
    kubectl create secret generic kafka-credentials \
        --from-literal=KAFKA_API_KEY='YOUR_CONFLUENT_API_KEY' \
        --from-literal=KAFKA_API_SECRET='YOUR_CONFLUENT_API_SECRET'
    ```

4.  **Update `k8s/deployment.yaml`** to mount the secret as environment variables in your containers:

    ```yaml
    # In k8s/deployment.yaml, for each container
        envFrom:
        - configMapRef:
            name: leaderboard-config
        - secretRef:
            name: kafka-credentials
    ```

5.  **Deploy the Application**:

    ```sh
    kubectl apply -f k8s/serviceaccount.yaml
    kubectl apply -f k8s/configmap.yaml
    kubectl apply -f k8s/deployment.yaml
    ```

Your application is now deployed on GKE, securely authenticating to GCP services using Workload Identity and connecting to a managed Kafka cluster.
