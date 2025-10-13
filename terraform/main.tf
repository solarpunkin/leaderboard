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
    "managedkafka.googleapis.com"
  ])
  service            = each.key
  disable_on_destroy = false
}

resource "google_storage_bucket" "data_lake" {
  name          = var.gcs_bucket_name
  location      = var.gcp_region
  force_destroy = true
}

resource "google_managed_kafka_cluster" "main_cluster" {
  cluster_id = "leaderboard-kafka-cluster-main"
  location   = var.gcp_region

  capacity_config {
    vcpu_count   = 3
    memory_bytes = 3221225472 # 3 GiB
  }

  gcp_config {
    access_config {
      network_configs {
        subnet = "projects/${data.google_project.project.number}/regions/${var.gcp_region}/subnetworks/default"
      }
    }
  }
  depends_on = [google_project_service.gcp_apis]
}

resource "google_managed_kafka_topic" "leaderboard_topic" {
  topic_id         = "leaderboard_events"
  cluster          = google_managed_kafka_cluster.main_cluster.cluster_id
  location         = google_managed_kafka_cluster.main_cluster.location
  partition_count  = 3
  replication_factor = 3
}

resource "google_container_cluster" "primary" {
  name     = var.gke_cluster_name
  location = var.gcp_zone

  initial_node_count = 1
  node_config {
    machine_type = "n1-standard-1"
  }

  workload_identity_config {
    workload_pool = "${var.gcp_project_id}.svc.id.goog"
  }

  depends_on = [google_project_service.gcp_apis]
}

resource "google_service_account" "app_sa" {
  account_id   = "leaderboard-app-sa"
  display_name = "Service Account for Leaderboard App"
}

resource "google_service_account_iam_member" "workload_identity_user" {
  service_account_id = google_service_account.app_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.gcp_project_id}.svc.id.goog[default/leaderboard-app-sa]"
}

resource "google_storage_bucket_iam_member" "gcs_bucket_access" {
  bucket = google_storage_bucket.data_lake.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.app_sa.email}"
}

resource "google_managed_kafka_acl" "producer_acl" {
  acl_id = "topic/leaderboard_events"
  cluster  = google_managed_kafka_cluster.main_cluster.cluster_id
  location = google_managed_kafka_cluster.main_cluster.location
  acl_entries {
    host = "*"
    permission_type = "ALLOW"
    principal = "User:${google_service_account.app_sa.email}"
    operation = "WRITE"
  }
}

resource "google_managed_kafka_acl" "consumer_acl" {
  acl_id = "topic/leaderboard_events"
  cluster  = google_managed_kafka_cluster.main_cluster.cluster_id
  location = google_managed_kafka_cluster.main_cluster.location
  acl_entries {
    host = "*"
    permission_type = "ALLOW"
    principal = "User:${google_service_account.app_sa.email}"
    operation = "READ"
  }
}

resource "google_managed_kafka_acl" "consumer_group_acl" {
  acl_id = "consumerGroup/*"
  cluster  = google_managed_kafka_cluster.main_cluster.cluster_id
  location = google_managed_kafka_cluster.main_cluster.location
  acl_entries {
    host = "*"
    permission_type = "ALLOW"
    principal = "User:${google_service_account.app_sa.email}"
    operation = "READ"
  }
}

output "kafka_bootstrap_address" {
  value = "${google_managed_kafka_cluster.main_cluster.cluster_id}.kafka.${var.gcp_region}.managedkafka.gcp.internal:9092"
}