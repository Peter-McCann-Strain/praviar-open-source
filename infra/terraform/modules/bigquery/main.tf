# BigQuery — patent search dataset for the hybrid BM25+SPECTER2 vector retrieval path.
#
# This module provisions the dataset and table skeleton only. Table data
# (patent records + embedding vectors) is loaded out-of-band via the pipeline
# CLI command: `praviar-pipeline load-bigquery-patents`.
#
# After the first data load, create the full-text search index manually:
#   bq query --use_legacy_sql=false "
#     CREATE SEARCH INDEX patents_search_idx
#     ON \`<project>.patents.patents\` (ALL COLUMNS)
#   "
#
# The pipeline falls back to BM25-only when the embedding column is absent,
# so the table can be used immediately before embeddings are generated.

resource "google_bigquery_dataset" "patents" {
  project    = var.project_id
  dataset_id = var.dataset_id
  location   = var.region

  description = "Praviar hybrid patent search — BM25 full-text + SPECTER2 vector retrieval"

  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }

  # Runtime SAs need read access to query the patent table.
  dynamic "access" {
    for_each = var.reader_service_accounts
    content {
      role          = "READER"
      user_by_email = access.value
    }
  }

  labels = {
    env         = var.env
    owner       = "praviar"
    cost-center = "engineering"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Patent search table — schema matches what hybrid_bigquery.py SELECTs.
# Partitioned by filing_date to reduce per-query bytes scanned.
# Clustered by jurisdiction + classification for common FTO filter patterns.
resource "google_bigquery_table" "patents" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.patents.dataset_id
  table_id   = var.table_id

  deletion_protection = true

  description = "Patent records with SPECTER2 embeddings for hybrid BM25+vector search"

  time_partitioning {
    type  = "MONTH"
    field = "filing_date"
  }

  clustering = ["jurisdiction", "classification"]

  schema = jsonencode([
    {
      name        = "patent_number"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Unique patent publication number (e.g. US-12345678-A1)"
    },
    {
      name        = "title"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Patent title (English)"
    },
    {
      name        = "abstract"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Patent abstract (English)"
    },
    {
      name        = "assignee"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Patent assignee / owner name"
    },
    {
      name        = "filing_date"
      type        = "DATE"
      mode        = "NULLABLE"
      description = "Patent filing date — used for partition pruning"
    },
    {
      name        = "expiry_date"
      type        = "DATE"
      mode        = "NULLABLE"
      description = "Estimated patent expiry date"
    },
    {
      name        = "jurisdiction"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "2-letter country / jurisdiction code (e.g. US, EP, WO)"
    },
    {
      name        = "classification"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Primary CPC/IPC classification code"
    },
    {
      name        = "embedding"
      type        = "FLOAT64"
      mode        = "REPEATED"
      description = "SPECTER2 embedding vector (768 dimensions) for VECTOR_SEARCH"
    },
  ])

  labels = {
    env         = var.env
    owner       = "praviar"
    cost-center = "engineering"
  }

  lifecycle {
    prevent_destroy = true
    # Schema evolves via data loads; ignore drift on the embedding column
    # dimensions to avoid Terraform re-creating the table.
    ignore_changes = [schema]
  }
}
