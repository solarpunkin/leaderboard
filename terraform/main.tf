terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 7.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

provider "google-beta" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

data "google_project" "project" {}

# --- Service APIs ---
resource "google_project_service" "gcp_apis" {
  for_each = toset([
    "compute.googleapis.com",
    "container.googleapis.com",
    "storage-component.googleapis.com",
    "iamcredentials.googleapis.com",
    "artifactregistry.googleapis.com",
    "redis.googleapis.com",
    "servicenetworking.googleapis.com",
    "dataflow.googleapis.com",
    "pubsub.googleapis.com" # Added for Pub/Sub
  ])
  service = each.key
}

# --- GKE Cluster ---

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
    tags            = ["gke-node"]
  }
}

# --- IAM & Service Accounts ---

resource "google_service_account" "app_sa" {
  account_id   = "leaderboard-app-sa"
  display_name = "Service Account for Leaderboard App"
}

resource "google_project_iam_member" "sa_permissions" {
  for_each = toset([
    "roles/dataflow.admin",
    "roles/dataflow.worker",
    "roles/iam.serviceAccountTokenCreator",
    "roles/storage.objectAdmin", # Broad access for GCS
    "roles/artifactregistry.reader",
    "roles/pubsub.editor" # Added for Pub/Sub
  ])
  project = var.gcp_project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.app_sa.email}"
}

# --- Pub/Sub Topic and Subscription ---
resource "google_pubsub_topic" "leaderboard_events" {
  name    = "leaderboard_events"
  project = var.gcp_project_id
}

resource "google_pubsub_subscription" "leaderboard_batch_sub" {
  name    = "leaderboard-batch-sub"
  topic   = google_pubsub_topic.leaderboard_events.id
  project = var.gcp_project_id

  ack_deadline_seconds = 600 # 10 minutes
  message_retention_duration = "604800s" # 7 days

  depends_on = [google_pubsub_topic.leaderboard_events]
}

resource "google_pubsub_subscription" "leaderboard_realtime_sub" {
  name    = "leaderboard-realtime-sub"
  topic   = google_pubsub_topic.leaderboard_events.id
  project = var.gcp_project_id

  ack_deadline_seconds = 20
  message_retention_duration = "604800s" # 7 days

  depends_on = [google_pubsub_topic.leaderboard_events]
}

# --- Networking & Other Resources (Unchanged) ---

resource "google_storage_bucket" "dataflow_staging" {
  name          = "${var.gcs_bucket_name}-dataflow-staging"
  location      = var.gcp_region
  force_destroy = true
}

data "google_storage_bucket" "data_lake" {
  name = var.gcs_bucket_name
  depends_on = [google_project_service.gcp_apis]
}

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

resource "google_compute_firewall" "allow_internal_redis" {
  name    = "allow-internal-redis"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "tcp"
    ports    = ["6378"]
  }

  source_ranges = [google_compute_subnetwork.kafka_subnet.ip_cidr_range]
}

resource "google_compute_firewall" "allow_ssh_via_iap" {
  name    = "allow-ssh-via-iap"
  network = google_compute_network.vpc_network.name
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["gke-node"]
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

output "pubsub_topic_name" {
  description = "The name of the Pub/Sub topic for leaderboard events."
  value       = google_pubsub_topic.leaderboard_events.name
}

output "pubsub_batch_subscription_name" {
  description = "The name of the Pub/Sub subscription for the batch pipeline."
  value       = google_pubsub_subscription.leaderboard_batch_sub.name
}

output "pubsub_realtime_subscription_name" {
  description = "The name of the Pub/Sub subscription for the realtime pipeline."
  value       = google_pubsub_subscription.leaderboard_realtime_sub.name
}
