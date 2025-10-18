terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

data "google_project" "project" {}

resource "google_project_service" "gcp_apis" {
  for_each = toset([
    "compute.googleapis.com",
    "container.googleapis.com",
    "storage-component.googleapis.com",
    "iamcredentials.googleapis.com",
    "artifactregistry.googleapis.com",
    "managedkafka.googleapis.com",
    "redis.googleapis.com",
    "servicenetworking.googleapis.com",
    "dataflow.googleapis.com"
  ])
  service            = each.key
}

resource "google_storage_bucket" "dataflow_staging" {
  name          = "${var.gcs_bucket_name}-dataflow-staging"
  location      = var.gcp_region
  force_destroy = true
}

# --- Existing Resources to be Read/Imported ---

# Read the existing GCS bucket
data "google_storage_bucket" "data_lake" {
  name = var.gcs_bucket_name
  depends_on = [google_project_service.gcp_apis]
}

# Define the Kafka cluster resource so we can import it
resource "google_managed_kafka_cluster" "main_cluster" {
  cluster_id = "leaderboard-kafka-cluster-main"
  location   = var.gcp_region


  capacity_config {
    vcpu_count   = 6
    memory_bytes = "6442450944" # 6 GiB
  }

  gcp_config {
    access_config {
      network_configs {
        subnet = google_compute_subnetwork.kafka_subnet.id
      }
    }
  }
  depends_on = [google_project_service.gcp_apis]
}

# --- Managed Resources ---

resource "google_container_cluster" "primary" {
  name                   = var.gke_cluster_name
  location               = var.gcp_zone
  network                = google_compute_network.vpc_network.id
  subnetwork             = google_compute_subnetwork.kafka_subnet.id
  deletion_protection    = false
  remove_default_node_pool = true
  initial_node_count     = 1
}

resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  cluster    = google_container_cluster.primary.id
  location   = var.gcp_zone

  autoscaling {
    min_node_count = 1
    max_node_count = 3
  }

  node_config {
    machine_type    = "e2-standard-2"
    service_account = google_service_account.app_sa.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
  }
}

resource "google_service_account" "app_sa" {
  account_id   = "leaderboard-app-sa"
  display_name = "Service Account for Leaderboard App"
}

resource "google_project_iam_member" "dataflow_admin" {
  project = var.gcp_project_id
  role    = "roles/dataflow.admin"
  member  = "serviceAccount:${google_service_account.app_sa.email}"
}

resource "google_project_iam_member" "dataflow_worker" {
  project = var.gcp_project_id
  role    = "roles/dataflow.worker"
  member  = "serviceAccount:${google_service_account.app_sa.email}"
}

resource "google_project_iam_member" "sa_token_creator" {
  project = var.gcp_project_id
  role    = "roles/iam.serviceAccountTokenCreator"
  member  = "serviceAccount:${google_service_account.app_sa.email}"
}

resource "google_project_iam_member" "gcr_pull_access" {
  project = var.gcp_project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.app_sa.email}"
}

resource "google_project_iam_member" "ar_pull_access" {
  project = var.gcp_project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.app_sa.email}"
}

resource "google_project_iam_member" "kafka_client" {
  project = var.gcp_project_id
  role    = "roles/managedkafka.client"
  member  = "serviceAccount:${google_service_account.app_sa.email}"
}

resource "google_service_account_iam_member" "workload_identity_user" {
  service_account_id = google_service_account.app_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.gcp_project_id}.svc.id.goog[default/leaderboard-app-sa]"
  depends_on         = [google_container_cluster.primary]
}

resource "google_storage_bucket_iam_member" "gcs_bucket_access" {
  bucket = data.google_storage_bucket.data_lake.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.app_sa.email}"
}

resource "google_managed_kafka_acl" "topic_access_acl" {
  acl_id   = "topic/leaderboard_events"
  cluster  = google_managed_kafka_cluster.main_cluster.cluster_id
  location = google_managed_kafka_cluster.main_cluster.location
  acl_entries {
    host            = "*"
    permission_type = "ALLOW"
    principal       = "User:*"
    operation       = "WRITE"
  }
  acl_entries {
    host            = "*"
    permission_type = "ALLOW"
    principal       = "User:*"
    operation       = "READ"
  }
}

resource "google_managed_kafka_acl" "consumer_group_acl" {
  acl_id   = "consumerGroup/*"
  cluster  = google_managed_kafka_cluster.main_cluster.cluster_id
  location = google_managed_kafka_cluster.main_cluster.location
  acl_entries {
    host            = "*"
    permission_type = "ALLOW"
    principal       = "User:*"
    operation       = "READ"
  }
}

# --- Networking for Redis ---
resource "google_compute_network" "vpc_network" {
  name = "leaderboard-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "kafka_subnet" {
  name          = "leaderboard-subnet"
  ip_cidr_range = "10.10.0.0/24"
  region        = var.gcp_region
  network       = google_compute_network.vpc_network.id
  private_ip_google_access = true
}

resource "google_compute_firewall" "dataflow_internal" {
  name    = "dataflow-internal-communication"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "tcp"
    ports    = ["12345-12346"]
  }

  source_ranges = [google_compute_subnetwork.kafka_subnet.ip_cidr_range]
  target_tags   = ["dataflow"]
}

resource "google_compute_global_address" "private_ip_alloc" {
  name          = "leaderboard-redis-ip-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc_network.id
}

resource "google_service_networking_connection" "private_service_connection" {
  network                 = google_compute_network.vpc_network.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_alloc.name]
}

# --- Redis Instance (Memorystore) ---
resource "google_redis_instance" "leaderboard_cache" {
  name           = "leaderboard-redis"
  tier           = "BASIC"
  memory_size_gb = 1
  location_id    = var.gcp_zone
  authorized_network = google_compute_network.vpc_network.id
  connect_mode   = "PRIVATE_SERVICE_ACCESS"
  transit_encryption_mode = "SERVER_AUTHENTICATION"
  depends_on = [google_service_networking_connection.private_service_connection]
}

# --- Outputs ---

output "kafka_bootstrap_address" {
  description = "The authoritative bootstrap address for the Kafka cluster, constructed manually."
  value       = "bootstrap.${google_managed_kafka_cluster.main_cluster.cluster_id}.${var.gcp_region}.managedkafka.${var.gcp_project_id}.cloud.goog:9092"
}

output "redis_host" {
  value = google_redis_instance.leaderboard_cache.host
}

output "redis_port" {
  value = google_redis_instance.leaderboard_cache.port
}

output "dataflow_staging_bucket_name" {
  value = google_storage_bucket.dataflow_staging.name
}

output "gcs_bucket_name" {
  description = "The name of the main GCS data lake bucket."
  value       = var.gcs_bucket_name
}
