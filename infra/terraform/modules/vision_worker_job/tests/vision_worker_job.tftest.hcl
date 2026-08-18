mock_provider "google" {}

variables {
  project_id                     = "praviar-test"
  env                            = "staging"
  job_name                       = "staging-vision-preflight"
  region                         = "europe-west2"
  image                          = "europe-west2-docker.pkg.dev/praviar-test/praviar/vision-worker@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  approved_image_repository      = "europe-west2-docker.pkg.dev/praviar-test/praviar/vision-worker"
  required_image_digest          = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  roster_sha256                  = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  ml_bom_sha256                  = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
  deployer_service_account_email = "deploy@praviar-test.iam.gserviceaccount.com"
  network_id                     = "projects/praviar-test/global/networks/main"
  subnetwork_id                  = "projects/praviar-test/regions/europe-west2/subnetworks/run"
}

run "private_digest_bound_job" {
  command = plan

  assert {
    condition     = output.job_name == "staging-vision-preflight"
    error_message = "The dedicated vision job name was not preserved."
  }
}
