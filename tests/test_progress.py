"""
Unit tests untuk komponen ETLProgress dan rich progress display.
"""

import time
import pytest
from io import StringIO
from rich.console import Console

from etl.progress import ETLProgress


def test_etl_progress_success_flow():
    """Memverifikasi lifecycle normal ETLProgress dengan status SUCCESS."""
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=120)

    with ETLProgress(run_id="TEST_RUN_SUCCESS", mode="Full", console=console) as ep:
        ep.start_step("extract", message="Extracting...")
        ep.complete_step("extract", message="Extract done", rows=1000)

        ep.start_step("reconcile", message="Reconciling...")
        ep.complete_step("reconcile", message="Reconcile done", rows=1000)

        ep.start_step("clean", message="Cleaning...")
        ep.complete_step("clean", message="Clean done", rows=950)

        ep.start_step("transform", message="Transforming...")
        ep.complete_step("transform", message="Transform done", rows="5 dims")

        ep.start_step("load_dims", message="Loading dims...", total=5, show_bar=True)
        ep.update_step("load_dims", message="dim 5/5", completed=5, total=5)
        ep.complete_step("load_dims", message="Load dims done", rows="5 dims")

        ep.start_step("load_facts", message="Loading facts...")
        ep.complete_step("load_facts", message="Load facts done", rows=950)

    rendered = output.getvalue()
    assert "TEST_RUN_SUCCESS" in rendered
    assert "Mode: Full" in rendered
    assert "[1/4] Extract" in rendered
    assert "[1.5] Reconcile" in rendered
    assert "[2/4] Clean" in rendered
    assert "[3/4] Transform" in rendered
    assert "[4a/4] Load Dims" in rendered
    assert "[4b/4] Load Facts" in rendered
    assert "Ringkasan Eksekusi Pipeline ETL" in rendered
    assert "SUCCESS" in rendered


def test_etl_progress_failure_flow():
    """Memverifikasi penanganan error dan status FAILED pada ETLProgress."""
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=120)

    with pytest.raises(ValueError):
        with ETLProgress(run_id="TEST_RUN_FAIL", mode="Incremental", console=console) as ep:
            ep.start_step("extract", message="Extracting...")
            ep.complete_step("extract", message="Extract done", rows=500)

            ep.start_step("reconcile", message="Reconciling...")
            raise ValueError("Reconcile schema failure")

    rendered = output.getvalue()
    assert "TEST_RUN_FAIL" in rendered
    assert "Mode: Incremental" in rendered
    assert "Reconcile schema failure" in rendered
    assert "FAILED" in rendered
    assert "SKIPPED" in rendered
