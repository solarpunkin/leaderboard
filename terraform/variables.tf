variable "gcp_project_id" {
  description = "The GCP project ID to deploy resources in."
  type        = string
}

variable "gcp_region" {
  description = "The GCP region to deploy resources in."
  type        = string
  default     = "us-central1"
}

variable "gcp_zone" {
  description = "The GCP zone to deploy resources in."
  type        = string
  default     = "us-central1-c"
}

variable "gke_cluster_name" {
  description = "The name for the GKE cluster."
  type        = string
  default     = "leaderboard-cluster-v2"
}

variable "gcs_bucket_name" {
  description = "The name for the GCS bucket."
  type        = string
}

variable "archive_gcs_path" {
  description = "The GCS path for the archived Parquet files."
  type        = string
}

variable "bigquery_dataset_name" {
  description = "The name for the BigQuery dataset."
  type        = string
  default     = "leaderboard_dataset"
}
