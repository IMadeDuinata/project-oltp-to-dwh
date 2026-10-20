"""
Helper modul untuk visualisasi progress eksekusi ETL menggunakan library Rich.
Menampilkan tampilan TUI vertikal terpadu (Progress Panel di atas, Live Logs 20 baris di bawah)
tanpa ikon/emoji, serta menyediakan file audit log lengkap untuk inspeksi mendalam.
"""

import os
import time
import logging
from pathlib import Path
from collections import deque
from typing import Any, Dict, List, Optional
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    MofNCompleteColumn,
)
from rich.table import Table, Column
from rich.text import Text


class TextStatusColumn(SpinnerColumn):
    """
    Status kolom berbasis teks murni (tanpa ikon emoji):
    - running: [RUN ]
    - success: [DONE]
    - failed:  [FAIL]
    - pending: [WAIT]
    """

    def render(self, task) -> Text:
        status = task.fields.get("status", "pending")
        if status == "success":
            return Text("[DONE] ", style="bold green")
        elif status == "failed":
            return Text("[FAIL] ", style="bold red")
        elif status == "running":
            return Text("[RUN ] ", style="bold cyan")
        return Text("[WAIT] ", style="dim")


class StepTimeElapsedColumn(TimeElapsedColumn):
    """
    TimeElapsedColumn dengan format durasi ringkas (contoh: '  3.2s').
    Mendukung nilai duration tetap setelah step selesai.
    """

    def __init__(self):
        super().__init__(table_column=Column(min_width=6, no_wrap=True, justify="right"))

    def render(self, task) -> Text:
        status = task.fields.get("status", "pending")
        if status == "pending":
            return Text("   -  ", style="dim")
        elapsed = task.fields.get("duration")
        if elapsed is None:
            elapsed = task.elapsed
        if elapsed is None:
            return Text(" 0.0s ", style="dim")
        return Text(f"{elapsed:>5.1f}s", style="cyan")


class LogCaptureHandler(logging.Handler):
    """
    Logging Handler yang menangkap log terbaru ke dalam memory buffer
    (untuk Live Logs panel) dan menulis log secara lengkap ke dua file audit:
    1. reports/etl_<run_id>.log (file spesifik per-run)
    2. log_etl.txt (file global latest)
    """

    def __init__(
        self,
        maxlen: int = 20,
        run_log_filepath: Optional[str] = None,
        global_log_filepath: str = "log_etl.txt",
    ):
        super().__init__()
        self.buffer: deque[Text] = deque(maxlen=maxlen)
        self.maxlen = maxlen
        self.run_log_filepath = run_log_filepath
        self.global_log_filepath = global_log_filepath

        # Pastikan direktori file log ada
        if self.run_log_filepath:
            Path(self.run_log_filepath).parent.mkdir(parents=True, exist_ok=True)

    def emit(self, record: logging.LogRecord):
        try:
            ts = time.strftime("%H:%M:%S", time.localtime(record.created))
            lvl = record.levelname
            msg = record.getMessage()

            # Format log audit lengkap
            full_ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
            log_entry = f"{full_ts} [{lvl}] {record.name}: {msg}\n"
            if record.exc_info:
                import traceback
                log_entry += "".join(traceback.format_exception(*record.exc_info)) + "\n"

            # Tulis ke file run audit log
            if self.run_log_filepath:
                try:
                    with open(self.run_log_filepath, "a", encoding="utf-8") as f:
                        f.write(log_entry)
                except Exception:
                    pass

            # Tulis ke file global log audit
            try:
                with open(self.global_log_filepath, "a", encoding="utf-8") as f:
                    f.write(log_entry)
            except Exception:
                pass

            # Format untuk TUI Live Logs panel (tanpa emoji, clean text styling)
            style_lvl = "green" if lvl == "INFO" else ("yellow" if lvl == "WARNING" else "bold red")
            line = Text(no_wrap=True)
            line.append(f"{ts} ", style="dim")
            line.append(f"[{lvl[:4]:4s}] ", style=style_lvl)
            src_name = record.name.split(".")[-1]
            line.append(f"{src_name:<11}: ", style="cyan dim")
            line.append(msg, style="white")

            self.buffer.append(line)
        except Exception:
            pass


class ETLProgress:
    """
    Context Manager untuk mengelola TUI display pada pipeline ETL secara vertikal:
    - Panel Atas: Step Progress (Extract, Reconcile, Clean, Transform, Load Dims, Load Facts)
      dengan teks status [WAIT], [RUN ], [DONE], [FAIL], progress bar, dan durasi.
    - Panel Bawah: Live Logs (20 baris log berjalan real-time).
    - Akhir Proses: Summary Table dan Panel Petunjuk Audit Log Lengkap.
    """

    DEFAULT_STEPS = [
        {"key": "extract", "label": "[1/4] Extract", "message": "Menunggu extract...", "total": 6},
        {"key": "reconcile", "label": "[1.5] Reconcile", "message": "Menunggu harmonisasi...", "total": 6},
        {"key": "clean", "label": "[2/4] Clean", "message": "Menunggu cleansing...", "total": 6},
        {"key": "transform", "label": "[3/4] Transform", "message": "Menunggu transformasi...", "total": 8},
        {"key": "load_dims", "label": "[4a/4] Load Dims", "message": "Menunggu pemuatan dimensi...", "total": 5},
        {"key": "load_facts", "label": "[4b/4] Load Facts", "message": "Menunggu pemuatan fakta...", "total": 3},
    ]

    def __init__(
        self,
        run_id: str,
        mode: str = "Full",
        pipeline_name: str = "olist_pipeline",
        console: Optional[Console] = None,
        max_logs: int = 20,
    ):
        self.run_id = run_id
        self.mode = mode
        self.pipeline_name = pipeline_name
        self.console = console or Console()
        self.max_logs = max_logs

        # File path audit log
        self.run_log_file = f"reports/etl_{self.run_id}.log"
        self.global_log_file = "log_etl.txt"

        # Inisialisasi Rich Progress dengan kolom teks terstandar (tanpa emoji, spacing renggang)
        self.progress = Progress(
            TextColumn("  [cyan]{task.fields[label]:<14}[/cyan]  ", table_column=Column(no_wrap=True)),
            TextStatusColumn(),
            TextColumn("  {task.fields[message]}", table_column=Column(ratio=1)),
            BarColumn(bar_width=10, complete_style="green", finished_style="bold green", table_column=Column(no_wrap=True)),
            MofNCompleteColumn(table_column=Column(min_width=7, no_wrap=True, justify="right")),
            StepTimeElapsedColumn(),
            console=self.console,
            expand=True,
        )

        # Mapping key -> task_id dan metadata step
        self._task_ids: Dict[str, Any] = {}
        self._step_data: Dict[str, Dict[str, Any]] = {}
        self._current_step_key: Optional[str] = None
        self._step_order: List[str] = []

        for step_cfg in self.DEFAULT_STEPS:
            key = step_cfg["key"]
            label = step_cfg["label"]
            msg = step_cfg["message"]
            total = step_cfg["total"]
            self._step_order.append(key)

            task_id = self.progress.add_task(
                description="",
                label=label,
                message=msg,
                status="pending",
                duration=None,
                total=total,
                completed=0,
                start=False,
            )
            self._task_ids[key] = task_id
            self._step_data[key] = {
                "key": key,
                "label": label,
                "status": "PENDING",
                "rows": None,
                "duration": None,
                "start_time": None,
                "message": msg,
                "total": total,
            }

        # Handler untuk menangkap log ke panel Live Logs dan file audit
        self.log_handler = LogCaptureHandler(
            maxlen=self.max_logs,
            run_log_filepath=self.run_log_file,
            global_log_filepath=self.global_log_file,
        )
        self._saved_stream_handlers: List[logging.Handler] = []

        # Live Display dengan layout vertikal via callable get_renderable
        self._live = Live(
            self._render_view(),
            get_renderable=self._render_view,
            console=self.console,
            refresh_per_second=6,
            transient=False,
        )

    def _render_view(self) -> Table:
        """Menghasilkan renderable layout vertikal (Progress Panel di atas, Live Logs 20 baris di bawah)."""
        # Panel Atas: Progress Steps (elemen direnggangkan dengan padding dan spacing lapang)
        title_capsule = (
            f"   ETL Pipeline: [bold cyan]{self.pipeline_name}[/bold cyan]     │     "
            f"Run ID: [bold yellow]{self.run_id}[/bold yellow]     │     "
            f"Mode: [bold green]{self.mode}[/bold green]   "
        )
        p_top = Panel(
            self.progress,
            title=title_capsule,
            border_style="blue",
            padding=(1, 2),
        )

        # Panel Bawah: Live Logs setinggi max_logs (20 baris stabil)
        log_lines: List[Text] = list(self.log_handler.buffer)
        if not log_lines:
            log_lines = [Text("Menunggu aktivitas pipeline...", style="dim")]

        # Padding vertikal agar tinggi panel stabil 20 baris
        while len(log_lines) < self.max_logs:
            log_lines.append(Text(" ", style="dim"))

        log_text = Text("\n").join(log_lines)
        p_bottom = Panel(
            log_text,
            title=f"   Live Execution Logs   ",
            border_style="cyan",
            padding=(0, 1),
        )

        # Susun secara vertikal menggunakan Table.grid
        grid = Table.grid(expand=True)
        grid.add_column()
        grid.add_row(p_top)
        grid.add_row(p_bottom)
        return grid

    def __enter__(self) -> "ETLProgress":
        # Simpan dan alihkan StreamHandler console agar tidak bentrok dengan Live display
        root_logger = logging.getLogger()
        if root_logger.level > logging.INFO:
            root_logger.setLevel(logging.INFO)

        self._saved_stream_handlers = []
        for h in list(root_logger.handlers):
            if isinstance(h, logging.StreamHandler):
                self._saved_stream_handlers.append(h)
                root_logger.removeHandler(h)

        # Tambahkan log handler panel
        root_logger.addHandler(self.log_handler)

        self._live.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            # Jika keluar karena exception, tandai step aktif sebagai gagal
            if self._current_step_key and self._step_data.get(self._current_step_key, {}).get("status") == "RUNNING":
                raw_err = str(exc_val).strip()
                err_summary = raw_err.split("\n")[0][:80]
                self.fail_step(self._current_step_key, error_message=err_summary)

            # Tandai step yang masih pending sebagai dilewati (SKIPPED)
            for k in self._step_order:
                if self._step_data[k]["status"] == "PENDING":
                    self._step_data[k]["status"] = "SKIPPED"
                    tid = self._task_ids.get(k)
                    if tid is not None:
                        self.progress.update(
                            tid,
                            status="pending",
                            message="[dim]Dilewati[/dim]",
                        )

        # Hentikan Live display
        try:
            self._live.stop()
        except Exception:
            pass

        # Kembalikan handler logging asli
        root_logger = logging.getLogger()
        root_logger.removeHandler(self.log_handler)
        for h in self._saved_stream_handlers:
            root_logger.addHandler(h)

        # Cetak tabel ringkasan dan petunjuk audit log
        self.print_summary_table()
        self.print_audit_notice()
        return False

    def start_step(
        self,
        key: str,
        message: str = "Sedang diproses...",
        total: Optional[int] = None,
        **kwargs,
    ):
        """Memulai sebuah step di pipeline progress."""
        self._current_step_key = key
        task_id = self._task_ids.get(key)
        now = time.time()

        if key in self._step_data:
            self._step_data[key]["status"] = "RUNNING"
            self._step_data[key]["start_time"] = now
            self._step_data[key]["message"] = message

        if task_id is not None:
            self.progress.start_task(task_id)
            update_kwargs: Dict[str, Any] = {
                "status": "running",
                "message": message,
            }
            if total is not None:
                update_kwargs["total"] = total
                update_kwargs["completed"] = 0
            self.progress.update(task_id, **update_kwargs)

    def update_step(
        self,
        key: str,
        message: Optional[str] = None,
        completed: Optional[int] = None,
        total: Optional[int] = None,
        advance: Optional[int] = None,
    ):
        """Memperbarui status progress bar atau teks informasi pada step tertentu."""
        task_id = self._task_ids.get(key)
        if task_id is not None:
            kwargs: Dict[str, Any] = {}
            if message is not None:
                kwargs["message"] = message
                if key in self._step_data:
                    self._step_data[key]["message"] = message
            if completed is not None:
                kwargs["completed"] = completed
            if total is not None:
                kwargs["total"] = total
            if advance is not None:
                kwargs["advance"] = advance
            self.progress.update(task_id, **kwargs)

    def complete_step(
        self,
        key: str,
        message: str = "Selesai",
        rows: Any = None,
    ):
        """Menyelesaikan step dengan status sukses."""
        task_id = self._task_ids.get(key)
        now = time.time()

        duration = 0.0
        if key in self._step_data:
            start_time = self._step_data[key].get("start_time")
            if start_time:
                duration = max(0.0, now - start_time)
            self._step_data[key]["status"] = "SUCCESS"
            self._step_data[key]["duration"] = duration
            self._step_data[key]["rows"] = rows
            self._step_data[key]["message"] = message

        if task_id is not None:
            task = self.progress.tasks[task_id]
            task_duration = task.elapsed if task.elapsed is not None else duration
            target_total = task.total if task.total is not None else self._step_data[key]["total"]
            self.progress.stop_task(task_id)
            self.progress.update(
                task_id,
                status="success",
                message=message,
                duration=task_duration,
                completed=target_total,
                total=target_total,
            )

        if self._current_step_key == key:
            self._current_step_key = None

    def fail_step(
        self,
        key: str,
        error_message: str = "",
        rows: Any = None,
    ):
        """Menandai step sebagai gagal."""
        task_id = self._task_ids.get(key)
        now = time.time()

        duration = 0.0
        short_err = error_message.split("\n")[0][:80] if error_message else "Gagal"
        if key in self._step_data:
            start_time = self._step_data[key].get("start_time")
            if start_time:
                duration = max(0.0, now - start_time)
            self._step_data[key]["status"] = "FAILED"
            self._step_data[key]["duration"] = duration
            self._step_data[key]["rows"] = rows
            self._step_data[key]["message"] = f"[red]{short_err}[/red]"

        if task_id is not None:
            task = self.progress.tasks[task_id]
            task_duration = task.elapsed if task.elapsed is not None else duration
            self.progress.stop_task(task_id)
            self.progress.update(
                task_id,
                status="failed",
                message=f"[red]{short_err}[/red]",
                duration=task_duration,
            )

        if self._current_step_key == key:
            self._current_step_key = None

    def print_summary_table(self):
        """Mencetak tabel ringkasan eksekusi ETL (Step | Rows | Duration | Status)."""
        table = Table(
            title=f"Ringkasan Eksekusi Pipeline ETL ({self.run_id})",
            caption=f"Mode: {self.mode}",
            header_style="bold cyan",
            border_style="blue",
            show_lines=True,
        )
        table.add_column("Step", style="cyan", no_wrap=True)
        table.add_column("Rows", justify="right", style="green")
        table.add_column("Duration", justify="right", style="yellow")
        table.add_column("Status", justify="center")

        for key in self._step_order:
            step_info = self._step_data[key]
            label = step_info["label"]
            rows_val = step_info.get("rows")
            duration_val = step_info.get("duration")
            status = step_info.get("status", "PENDING")

            # Format rows
            if rows_val is None:
                rows_str = "-"
            elif isinstance(rows_val, (int, float)):
                rows_str = f"{int(rows_val):,}"
            else:
                rows_str = str(rows_val)

            # Format duration
            if duration_val is None:
                duration_str = "-"
            else:
                duration_str = f"{duration_val:.1f}s"

            # Format status
            if status == "SUCCESS":
                status_str = "[bold green]SUCCESS[/bold green]"
            elif status == "FAILED":
                err_msg = step_info.get("message", "")
                if err_msg and err_msg != "[red]Gagal[/red]":
                    clean_msg = err_msg.replace("[red]", "").replace("[/red]", "")
                    status_str = f"[bold red]FAILED[/bold red] ({clean_msg})"
                else:
                    status_str = "[bold red]FAILED[/bold red]"
            elif status == "SKIPPED":
                status_str = "[dim]SKIPPED[/dim]"
            else:
                status_str = f"[dim]{status}[/dim]"

            table.add_row(label, rows_str, duration_str, status_str)

        self.console.print()
        self.console.print(table)

    def print_audit_notice(self):
        """Mencetak panel informasi lokasi file audit log lengkap beserta perintah untuk membacanya."""
        info_text = Text()
        info_text.append("Log audit lengkap tersimpan secara persisten di:\n", style="bold")
        info_text.append("  - File Run   : ", style="cyan")
        info_text.append(f"{self.run_log_file}\n", style="green")
        info_text.append("  - File Global: ", style="cyan")
        info_text.append(f"{self.global_log_file}\n\n", style="green")
        info_text.append("Perintah untuk membaca log audit secara rinci:\n", style="bold")
        info_text.append(f"  $ less +G {self.run_log_file}\n", style="yellow")
        info_text.append(f"  $ tail -n 100 {self.global_log_file}", style="yellow")

        panel = Panel(
            info_text,
            title="Audit & Inspection Log Reference",
            border_style="dim",
        )
        self.console.print(panel)
        self.console.print()


if __name__ == "__main__":
    # Demo simulasi visualisasi ETLProgress vertikal (20 baris log, tanpa icon)
    console = Console()
    with ETLProgress(run_id="RUN_20261020_DEMO", mode="Full", console=console, max_logs=20) as ep:
        logging.info("Memulai ekstraksi data dari dual-source...")
        ep.start_step("extract", message="Mengekstrak data dari OLTP...", total=6)
        time.sleep(0.3)
        for i in range(1, 7):
            logging.info(f"Extract tabel #{i}/6 dari OLTP...")
            ep.update_step("extract", completed=i)
            time.sleep(0.08)
        ep.complete_step(
            "extract",
            message="BR: [green]99,441[/green] | ID: [green]4,972[/green] | Combined: [green]477,243[/green]",
            rows=477243,
        )

        ep.start_step("reconcile", message="Menyelaraskan skema data...", total=6)
        for i in range(1, 7):
            logging.info(f"Harmonisasi skema tabel #{i}/6...")
            ep.update_step("reconcile", completed=i)
            time.sleep(0.06)
        ep.complete_step(
            "reconcile",
            message="[green]477,243[/green] baris diharmonisasi",
            rows=477243,
        )

        ep.start_step("clean", message="Melakukan pembersihan data...", total=6)
        for i in range(1, 7):
            logging.info(f"Validasi data quality tabel #{i}/6...")
            ep.update_step("clean", completed=i)
            time.sleep(0.06)
        ep.complete_step(
            "clean",
            message="[green]476,556[/green] clean | [green]774[/green] rejected",
            rows=476556,
        )

        ep.start_step("transform", message="Membangun dimensi & fakta...", total=8)
        ep.update_step("transform", message="[green]5[/green] dimensi terbuild...", completed=5)
        time.sleep(0.2)

        ep.start_step("load_dims", message="Memuat dimensi...", total=5)
        dims = ["dim_date", "dim_customer", "dim_product", "dim_seller", "dim_payment_type"]
        for i, d in enumerate(dims, 1):
            logging.info(f"Upsert tabel {d} ke Data Warehouse...")
            ep.update_step("load_dims", message=f"{d} [green]{i}/5[/green]...", completed=i)
            time.sleep(0.08)
        ep.complete_step("load_dims", message="[green]5/5[/green] dimensi loaded", rows="5 dims")

        ep.complete_step(
            "transform",
            message="[green]5[/green] dimensi + [green]3[/green] fakta terbuild",
            rows="5 dims + 3 facts",
        )

        ep.start_step("load_facts", message="Memuat tabel fakta transaksional...", total=3)
        facts = ["fact_order_items", "fact_order_delivery", "fact_order_payments"]
        for i, f in enumerate(facts, 1):
            logging.info(f"Insert transaksi tabel {f}...")
            ep.update_step("load_facts", completed=i)
            time.sleep(0.08)
        ep.complete_step(
            "load_facts",
            message="total [green]312,450[/green] baris loaded",
            rows=312450,
        )
