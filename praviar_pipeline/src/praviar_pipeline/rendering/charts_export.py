"""Matplotlib bootstrap and figure serialisation helpers for charts."""

from __future__ import annotations

import base64
import io
import threading
from typing import TYPE_CHECKING

from praviar_pipeline.rendering.design import CHART_STYLE

if TYPE_CHECKING:
    from matplotlib.figure import Figure

_PLT_LOCK = threading.Lock()
_PLT_INITIALIZED = False


def get_plt():
    """Import matplotlib with Agg backend and apply the design-system style."""
    global _PLT_INITIALIZED

    with _PLT_LOCK:
        if not _PLT_INITIALIZED:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            plt.rcParams.update(CHART_STYLE)
            _PLT_INITIALIZED = True
        else:
            import matplotlib.pyplot as plt

    return plt


def fig_to_base64(fig: Figure) -> str:
    """Convert a matplotlib figure to a base64-encoded PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
    fig.clear()
    import matplotlib.pyplot as plt

    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")
