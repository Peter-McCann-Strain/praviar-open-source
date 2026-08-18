from __future__ import annotations

import json

import pytest

from praviar_pipeline.cli_models import main


def test_models_list_json_reports_fail_closed_policy(capsys) -> None:
    assert main(["list", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload
    assert all(item["automated_download_allowed"] is False for item in payload)
    assert all(item["local_activation_allowed"] is False for item in payload)
    assert all(item["upstream_page_url"].startswith("https://") for item in payload)


def test_models_fetch_link_only_entry_exits_with_upstream_url(capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["fetch", "moldet/yolo11l_960_doc", "--accept-license"])

    assert raised.value.code == 1
    assert "https://huggingface.co/UniParser/MolDet" in capsys.readouterr().err


def test_models_verify_missing_entry_returns_failure(tmp_path, capsys) -> None:
    exit_code = main(
        [
            "--model-root",
            str(tmp_path),
            "verify",
            "moldet/yolo11l_960_doc",
            "--json",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == [
        {
            "error": (
                "installed model does not exist: "
                f"{tmp_path.resolve()}/moldet/moldet_yolo11l_960_doc.pt"
            ),
            "model_id": "moldet/yolo11l_960_doc",
            "verified": False,
        }
    ]
