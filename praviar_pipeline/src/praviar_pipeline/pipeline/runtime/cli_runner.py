"""CLI and reanalysis orchestration helpers for the runtime entrypoint."""

from __future__ import annotations

import asyncio
import time

from praviar_pipeline.utils.private_artifacts import atomic_write_text, ensure_private_directory


async def reanalyze_failed_impl(
    checkpoint_dir_path: str,
    *,
    load_reanalysis_context_fn,
    select_failed_patents_fn,
    analyze_patents_fn,
    merge_reanalysis_results_fn,
    write_reanalysis_checkpoint_fn,
    run_pipeline_fn,
    logger,
    checkpoint_integrity_keys,
) -> dict:
    """Re-run analysis on patents that failed in a previous run."""
    context = load_reanalysis_context_fn(
        checkpoint_dir_path,
        integrity_keys=checkpoint_integrity_keys,
    )
    failed_ids, retry_patents = select_failed_patents_fn(
        context.patent_hits,
        context.analysis_failures,
    )
    if not failed_ids:
        logger.info("reanalyze_no_failures")
        raise ValueError("No failed analyses found in checkpoint")

    logger.info(
        "reanalyze_starting",
        failed_count=len(failed_ids),
        retry_count=len(retry_patents),
    )

    new_analyses, new_failures, _new_traces = await analyze_patents_fn(
        retry_patents,
        context.compound,
        context.triage_results,
    )

    merged_analyses, merged_failures = merge_reanalysis_results_fn(
        context.analyses,
        context.analysis_failures,
        new_analyses,
        new_failures,
    )
    logger.info(
        "reanalyze_step4_complete",
        new_analyzed=len(new_analyses),
        still_failed=len(new_failures),
        total_analyses=len(merged_analyses),
    )

    write_reanalysis_checkpoint_fn(
        checkpoint_dir_path=checkpoint_dir_path,
        checkpoint=context.checkpoint,
        state=context.state,
        patent_hits=context.patent_hits,
        triage_results=context.triage_results,
        merged_analyses=merged_analyses,
        merged_failures=merged_failures,
        integrity_keys=context.checkpoint_integrity_keys,
    )

    result = await run_pipeline_fn(
        user_input=context.checkpoint.compound_input,
        resume_from=checkpoint_dir_path,
    )
    if not isinstance(result, dict):
        raise TypeError("Reanalysis pipeline returned a non-mapping result")
    return result


def run_cli(
    argv: list[str],
    *,
    parse_run_args_fn,
    print_usage_fn,
    configure_logging_fn,
    reanalyze_failed_fn,
    run_pipeline_fn,
    sync_to_database_fn,
    emit_json_report_fn,
) -> int:
    """Execute the CLI flow and return a process exit code."""
    if len(argv) < 2:
        print_usage_fn()
        return 1

    cli_args = parse_run_args_fn(argv[1:])

    if cli_args.reanalyze_dir:
        configure_logging_fn()
        result = asyncio.run(reanalyze_failed_fn(cli_args.reanalyze_dir))
        user_input = result.get("compound", {}).get("name", "reanalyzed")
        sync_to_database_fn(result, user_input, 0.0)
        if cli_args.output_format == "json":
            emit_json_report_fn(result, banner=False)
        return 0

    configure_logging_fn()

    if getattr(cli_args, "dry_run", False):
        return _run_dry_run(
            cli_args=cli_args,
            run_pipeline_fn=run_pipeline_fn,
            emit_json_report_fn=emit_json_report_fn,
        )

    pipeline_start = time.time()
    result = asyncio.run(
        run_pipeline_fn(
            cli_args.user_input,
            output_format=cli_args.output_format,
            resume_from=cli_args.resume_from,
        )
    )
    duration = time.time() - pipeline_start
    sync_to_database_fn(result, cli_args.user_input, duration)

    if cli_args.output_format == "json":
        emit_json_report_fn(result, banner=True)

    return 0


def _run_dry_run(*, cli_args, run_pipeline_fn, emit_json_report_fn) -> int:
    """Execute the pipeline under the dry-run harness with a 60s timeout."""
    import json as _json
    from pathlib import Path as _Path

    from praviar_pipeline.dryrun import (
        DryRunAssertionError,
        DryRunError,
        assert_report_valid,
        attach_showcase_run_receipt,
        install_dry_run_harness,
        showcase_runtime_overrides,
        validate_showcase_input,
    )

    try:
        validate_showcase_input(cli_args.user_input)
    except DryRunError:
        print("DRY-RUN FAILED: input is not the canonical fictional showcase", flush=True)
        return 2
    if cli_args.resume_from:
        print("DRY-RUN FAILED: canonical showcase runs cannot resume checkpoints", flush=True)
        return 2

    # Dry-run output is synthetic and ensure_private_directory immediately
    # rejects unsafe path components and enforces owner-only permissions.
    output_dir = _Path(cli_args.output_dir or "/tmp/praviar_pipeline-dryrun")  # nosec B108
    ensure_private_directory(output_dir)

    async def _run() -> tuple[dict, int]:
        with install_dry_run_harness(
            checkpoint_dir=output_dir / ".checkpoints",
        ) as cache:
            result = await asyncio.wait_for(
                run_pipeline_fn(
                    cli_args.user_input,
                    output_format="json",
                    resume_from=cli_args.resume_from,
                    config_overrides=showcase_runtime_overrides(output_dir=output_dir),
                ),
                timeout=60.0,
            )
            return result, int(getattr(cache, "showcase_blocked_external_calls", 0))

    try:
        result, blocked_external_calls = asyncio.run(_run())
    except TimeoutError:
        print("DRY-RUN FAILED: pipeline exceeded 60s timeout", flush=True)
        return 2
    except Exception as exc:
        from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

        print(
            f"DRY-RUN FAILED: pipeline raised {safe_exception_type(exc)}",
            flush=True,
        )
        return 2

    try:
        assert_report_valid(result)
        attach_showcase_run_receipt(
            result,
            blocked_external_calls=blocked_external_calls,
        )
    except DryRunAssertionError as exc:
        from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

        print(
            f"DRY-RUN ASSERTION FAILED ({safe_exception_type(exc)})",
            flush=True,
        )
        return 3

    report_path = output_dir / "dryrun-report.json"
    atomic_write_text(report_path, _json.dumps(result, indent=2, default=str))

    print(
        "DRY-RUN OK: 8 stages; 0 external provider calls; $0.00; "
        f"substantive_sha256={result['showcase_run']['substantive_sha256']}",
        flush=True,
    )
    if cli_args.output_format == "json":
        emit_json_report_fn(result, banner=False)
    return 0


def exit_cli(argv: list[str], **kwargs) -> None:
    """Run the CLI and exit the process on failure."""
    raise SystemExit(run_cli(argv, **kwargs))
