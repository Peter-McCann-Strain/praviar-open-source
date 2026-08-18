from __future__ import annotations

import json
from types import SimpleNamespace

from praviar_pipeline.pipeline.runtime import output as runtime_output


class _Manifest:
    def model_dump_json(self, *, indent: int) -> str:
        assert indent == 2
        return json.dumps({"manifest": "ok"}, indent=indent)


class _Report:
    report_id = "abcdef1234567890"

    def __init__(self, manifest=None) -> None:
        self.manifest = manifest

    def model_dump(self, *, mode: str) -> dict:
        assert mode == "json"
        return {"report_id": self.report_id, "status": "complete"}


async def test_write_pipeline_outputs_writes_json_and_manifest(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_output,
        "get_settings",
        lambda: SimpleNamespace(resolved_output_dir=tmp_path),
    )

    report_dict = await runtime_output.write_pipeline_outputs(_Report(_Manifest()), "json")

    assert report_dict == {"report_id": _Report.report_id, "status": "complete"}
    assert (tmp_path / "fto_report_abcdef12.json").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "fto_report_abcdef12.manifest.json").read_text()) == {
        "manifest": "ok"
    }


async def test_write_pipeline_outputs_writes_markdown(tmp_path, monkeypatch) -> None:
    import praviar_pipeline.rendering as rendering

    monkeypatch.setattr(
        runtime_output,
        "get_settings",
        lambda: SimpleNamespace(resolved_output_dir=tmp_path),
    )
    monkeypatch.setattr(rendering, "render_markdown", lambda report: f"# {report.report_id}")

    await runtime_output.write_pipeline_outputs(_Report(), "markdown")

    assert (tmp_path / "fto_report_abcdef12.md").read_text(encoding="utf-8") == (
        "# abcdef1234567890"
    )


async def test_write_pipeline_outputs_writes_pdf(tmp_path, monkeypatch) -> None:
    import praviar_pipeline.rendering as rendering

    monkeypatch.setattr(
        runtime_output,
        "get_settings",
        lambda: SimpleNamespace(resolved_output_dir=tmp_path),
    )

    def fake_render_pdf(report, path) -> None:
        path.write_bytes(f"PDF:{report.report_id}".encode())

    monkeypatch.setattr(rendering, "render_pdf", fake_render_pdf)

    await runtime_output.write_pipeline_outputs(_Report(), "pdf")

    assert (tmp_path / "fto_report_abcdef12.pdf").read_bytes() == b"PDF:abcdef1234567890"
