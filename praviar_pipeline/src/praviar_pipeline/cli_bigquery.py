"""Verify BigQuery access and run a sample query against Google Patents Public Data.

Usage:
    praviar-pipeline check-bigquery

Prerequisites:
    - GOOGLE_APPLICATION_CREDENTIALS env var pointing to a service account JSON
    - Or: gcloud auth application-default login
    - BIGQUERY_PROJECT_ID set in .env
"""

from __future__ import annotations

from pathlib import Path

from praviar_pipeline.utils.safe_diagnostics import safe_exception_type


def check_credentials():
    """Check if BigQuery credentials are configured."""
    import os

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if creds_path and Path(creds_path).exists():
        print("  Credentials file: configured")
        return True

    # Check for application default credentials
    default_path = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    if default_path.exists():
        print("  Using application default credentials")
        return True

    print("  WARNING: No credentials found.")
    print("  Run: gcloud auth application-default login")
    print("  Or set GOOGLE_APPLICATION_CREDENTIALS in your .env")
    return False


def check_project():
    """Check BigQuery project ID is configured."""
    from praviar_pipeline.config import get_settings

    settings = get_settings()
    project_id = settings.bigquery_project_id

    if not project_id or project_id == "your-gcp-project-id":
        print("  WARNING: BIGQUERY_PROJECT_ID not set in .env")
        print("  Set it to your GCP project ID that has BigQuery access")
        return None

    print(f"  Project ID: {project_id}")
    return project_id


def test_query(project_id: str):
    """Run a minimal query against Google Patents Public Data."""
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)

    # Test 1: Basic connectivity
    print("\n  Test 1: Basic connectivity...")
    query = "SELECT 1 as test"
    result = client.query(query).result()
    rows = list(result)
    assert rows[0].test == 1
    print("  PASS: BigQuery connection works")

    # Test 2: Google Patents Public Data access
    print("\n  Test 2: Google Patents Public Data access...")
    query = """
    SELECT
        publication_number,
        title.text as title
    FROM `patents-public-data.patents.publications`
    WHERE
        title.text LIKE '%succinic acid%'
        AND country_code = 'US'
    LIMIT 5
    """
    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=1 * 1024**3,  # 1 GB safety limit for test
    )
    result = client.query(query, job_config=job_config).result()
    rows = list(result)
    print(f"  Found {len(rows)} sample patents mentioning 'succinic acid'")
    for row in rows[:3]:
        title = row.title[:80] if row.title else "N/A"
        print(f"    {row.publication_number}: {title}")
    print("  PASS: Google Patents Public Data accessible")

    # Test 3: Check available tables
    print("\n  Test 3: Key tables in patents-public-data...")
    tables = [
        "patents-public-data.patents.publications",
        "patents-public-data.patents.publications_202501",
    ]
    for table_id in tables:
        try:
            table = client.get_table(table_id)
            size_gb = table.num_bytes / 1024**3
            print(f"    {table_id}: {table.num_rows:,} rows, {size_gb:.1f} GB")
        except Exception as e:
            print(f"    {table_id}: Not accessible ({safe_exception_type(e)})")

    client.close()


def main(argv: list[str] | None = None):
    print("=" * 60)
    print("Praviar Pipeline BigQuery Setup Verification")
    print("=" * 60)

    print("\n--- Credentials ---")
    has_creds = check_credentials()

    print("\n--- Project ---")
    project_id = check_project()

    if has_creds and project_id:
        print("\n--- Query Tests ---")
        try:
            test_query(project_id)
            print("\n" + "=" * 60)
            print("BigQuery is fully configured and ready.")
            print("=" * 60)
            return 0
        except Exception as e:
            print(f"\n  FAILED ({safe_exception_type(e)})")
            print("\nTroubleshooting:")
            print("  1. Ensure your GCP project has BigQuery API enabled")
            print("  2. Ensure your credentials have BigQuery User role")
            print("  3. Run: gcloud services enable bigquery.googleapis.com")
            return 1
    else:
        print("\n" + "=" * 60)
        print("BigQuery is NOT fully configured. Fix the warnings above.")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
