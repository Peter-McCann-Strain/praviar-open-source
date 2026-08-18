"""Aggregate roots for generated cross-runtime TypeScript contracts."""

from pydantic import BaseModel, ConfigDict

from praviar_pipeline.models.accused_acts import ClaimedUseMatchReceipt
from praviar_pipeline.models.report import FTOReport


class SharedRuntimeContracts(BaseModel):
    """Keep every generated contract reachable from one explicit root."""

    model_config = ConfigDict(extra="forbid")

    report: FTOReport
    claimed_use_match_receipt: ClaimedUseMatchReceipt
