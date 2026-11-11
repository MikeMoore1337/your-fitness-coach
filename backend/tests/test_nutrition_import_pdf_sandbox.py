"""OS-level tests; execute in a non-root Linux backend environment."""

from __future__ import annotations

import io
import json
import os
import platform
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from reportlab.pdfbase import pdfdoc
from reportlab.pdfgen.canvas import Canvas

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or platform.machine() != "x86_64" or os.geteuid() == 0,
    reason="requires a non-root x86_64 Linux worker",
)

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "backend/fitminiapp_api/services/nutrition_import_adapter_worker.py"
PROBE = ROOT / "backend/tests/fixtures/nutrition_import/pdf_sandbox_probe.py"
PARSER = ROOT / "backend/fitminiapp_api/services/nutrition_import_fatsecret_pdf.py"


def run_worker(module, source, *, pass_fds=()):
    return subprocess.run(
        [sys.executable, "-I", str(WORKER), str(module), "pdf"],
        input=source,
        capture_output=True,
        timeout=8,
        pass_fds=pass_fds,
        check=False,
    )


def test_worker_denies_network_files_process_and_inherited_descriptors():
    fd = os.open("/etc/hostname", os.O_RDONLY)
    try:
        result = run_worker(PROBE, str(fd).encode(), pass_fds=(fd,))
    finally:
        os.close(fd)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert json.loads(result.stdout) == {
        "tcp": "denied",
        "udp": "denied",
        "external_connect": "denied",
        "read": "denied",
        "write": "denied",
        "list": "denied",
        "process": "denied",
        "inherited_fd": "closed",
        "connect": "denied",
        "execve": "denied",
        "execveat": "denied",
        "clone": "denied",
        "clone3": "denied",
        "openat2": "denied",
        "open_by_handle_at": "denied",
        "io_uring": "denied",
        "pidfd_getfd": "denied",
    }


@pytest.mark.parametrize("mode", [b"x32", b"int80"])
def test_alternate_abi_cannot_escape_filter(mode):
    result = run_worker(PROBE, mode)
    assert result.returncode == -signal.SIGSYS or (
        result.returncode == 0 and json.loads(result.stdout)["result"] < 0
    )


def test_worker_cpu_and_memory_limits():
    result = run_worker(PROBE, b"memory")
    assert result.returncode == 0 and json.loads(result.stdout)["memory"] == "denied"
    assert run_worker(PROBE, b"cpu").returncode in {-signal.SIGKILL, -signal.SIGXCPU}


def test_worker_processes_valid_pdf_after_filter():
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(1800, 800), pageCompression=0)
    pdf.drawString(20, 770, "Report Details")
    for index, text in enumerate(
        (
            "Calories",
            "Fat",
            "Sat. Fat",
            "Carbs",
            "Fiber",
            "Sugar",
            "Protein",
            "Sodium",
            "Chol",
            "Potassium",
        )
    ):
        pdf.drawString(400 + 130 * index, 740, text)
    pdf.drawString(20, 700, "Date: 02.03.2024")
    pdf.drawString(20, 670, "Breakfast")
    pdf.drawString(20, 640, "100 g")
    pdf.drawString(160, 640, "Synthetic food")
    pdf.drawString(400, 640, "12.3")
    pdf.save()
    result = run_worker(PARSER, stream.getvalue())
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    document = json.loads(result.stdout)
    assert len(document["rows"]) == 1
    assert document["rows"][0]["food"]["name"] == "Synthetic food"


def test_worker_rejects_embedded_file():
    stream = io.BytesIO()
    pdf = Canvas(stream)
    pdf.drawString(50, 700, "Synthetic")
    embedded = pdfdoc.PDFStream(
        pdfdoc.PDFDictionary({"Type": pdfdoc.PDFName("EmbeddedFile")}), b"synthetic attachment"
    )
    file_spec = pdfdoc.PDFDictionary(
        {
            "Type": pdfdoc.PDFName("Filespec"),
            "F": pdfdoc.PDFString("synthetic.txt"),
            "EF": pdfdoc.PDFDictionary({"F": pdf._doc.Reference(embedded)}),
        }
    )
    pdf._doc.Catalog.Names = pdfdoc.PDFDictionary(
        {
            "EmbeddedFiles": pdfdoc.PDFDictionary(
                {"Names": pdfdoc.PDFArray([pdfdoc.PDFString("synthetic.txt"), file_spec])}
            )
        }
    )
    pdf.save()
    result = run_worker(PARSER, stream.getvalue())
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    document = json.loads(result.stdout)
    assert document["rows"] == []
    assert document["diagnostics"][0]["code"] == "pdf_active_content"
