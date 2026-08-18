from scripts.check_no_terraform_artifacts import _is_terraform_artifact


def test_rejects_saved_plan_and_state_names() -> None:
    assert _is_terraform_artifact("infra/prod/tfplan-prod")
    assert _is_terraform_artifact("infra/prod/tfplan.binary")
    assert _is_terraform_artifact("infra/prod/release.tfplan")
    assert _is_terraform_artifact("infra/prod/terraform.tfstate")
    assert _is_terraform_artifact("infra/prod/terraform.tfstate.backup")


def test_allows_terraform_source_and_lock_files() -> None:
    assert not _is_terraform_artifact("infra/prod/main.tf")
    assert not _is_terraform_artifact("infra/prod/terraform.tfstate.example")
    assert not _is_terraform_artifact("infra/prod/.terraform.lock.hcl")
