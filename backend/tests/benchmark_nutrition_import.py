"""Manual benchmark: creates synthetic accounts and foods in an isolated dev database."""

import csv
import io
import math
import os
import re
import statistics
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

BASE = "http://127.0.0.1:18089"
RUN = int(os.environ.get("QA888_RUN", "0"))
STAT_NAMES = ("yfc-qa888-api2", "yfc-qa888-pg2")
samples = {name: [] for name in STAT_NAMES}
active_sessions = []
stop = threading.Event()


def collect():
    while not stop.is_set():
        result = subprocess.run(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}",
                *STAT_NAMES,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        for row in result.stdout.splitlines():
            name, cpu, memory = row.split("|")
            amount = memory.split("/")[0].strip()
            match = re.fullmatch(r"([0-9.]+)\s*(GiB|MiB|KiB)", amount)
            if not match:
                raise RuntimeError("unrecognized Docker memory format")
            number, unit = match.groups()
            mib = float(number) * (1024 if unit == "GiB" else 1 if unit == "MiB" else 1 / 1024)
            samples[name].append((float(cpu.strip("%")), mib))
        db = subprocess.run(
            [
                "docker",
                "exec",
                "yfc-qa888-pg2",
                "psql",
                "-U",
                "yfc_test",
                "-d",
                "yfc_perf",
                "-Atc",
                "select count(*) from pg_stat_activity where backend_type='client backend' and state='active'",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        active_sessions.append(int(db.stdout.strip()))
        stop.wait(0.5)


def csv_report(count):
    nutrient = ["65", "3", "0", "5", "0", "0", "4", "1", "0", "0"]
    header = [
        "Метка",
        "Кал ( ккал)",
        "Жир( г)",
        "Н/жир( г)",
        "Углев( г)",
        "Клетч( г)",
        "Сахар( г)",
        "Белк( г)",
        "Натри( мг)",
        "Холес( мг)",
        "Калий( мг)",
    ]
    rows = [
        ["# Food Diary Report - Detailed Report", "Четверг, февраля 29, 2024"],
        ["# Report Details"],
        header,
        ["Четверг, февраля 29, 2024", *nutrient],
        ["Завтрак", *nutrient],
    ]
    for i in range(count):
        rows.extend([[f"QA Synthetic {i}", *nutrient], ["100 г"]])
    out = io.StringIO(newline="")
    csv.writer(out, lineterminator="\r\n").writerows(rows)
    return out.getvalue().encode()


def request_with_timing(client, method, path, **kwargs):
    start = time.perf_counter()
    response = client.request(method, path, **kwargs)
    return response, time.perf_counter() - start


def run(index):
    with httpx.Client(base_url=BASE, timeout=90) as c:
        login = c.post(
            "/api/v1/auth/dev-login", json={"telegram_user_id": 98970000 + RUN * 100 + index}
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": "Bearer " + token}
        response, upload = request_with_timing(
            c,
            "POST",
            "/api/v1/nutrition/imports",
            headers={**headers, "Idempotency-Key": f"qa888-load-{index}"},
            data={"adapter_id": "fatsecret-csv-v1"},
            files={"file": ("synthetic.csv", source, "text/csv")},
        )
        if response.status_code != 201:
            return {
                "error": "upload",
                "status": response.status_code,
                "detail": response.json().get("detail"),
            }
        draft = response.json()
        if len(draft["rows"]) != 200:
            return {"error": "rows", "count": len(draft["rows"])}
        row = draft["rows"][0]["index"]
        root = f"/api/v1/nutrition/imports/{draft['id']}/catalog"
        correction = {
            "index": row,
            "name": f"QA Synthetic Load Product Diagnostic {RUN} {index}",
            "kind": "standard_food",
            "nutrition": {
                "source_basis": "per_100_g",
                "energy_kcal": "65",
                "protein_g": "4",
                "fat_g": "3",
                "carbohydrate_g": "5",
            },
            "confirmed": True,
        }
        body = {"revision": draft["revision"], "corrections": [correction], "choices": []}
        preview, review = request_with_timing(
            c, "POST", root + "/review", headers=headers, json=body
        )
        if preview.status_code != 200:
            return {
                "error": "review",
                "index": index,
                "status": preview.status_code,
                "detail": preview.json().get("detail"),
                "header_matches": preview.request.headers.get("Authorization")
                == headers["Authorization"],
            }
        outcome = preview.json()["rows"][row]["outcome"]
        if outcome != "publish":
            return {"error": "review_outcome", "index": index, "outcome": outcome}
        confirm_body = {
            **body,
            "preview_signature": preview.json()["preview_signature"],
            "confirm_key": f"qa888-confirm-{index}",
            "row_indexes": [row],
            "confirmed": True,
        }
        result, confirm = request_with_timing(
            c, "POST", root + "/confirm", headers=headers, json=confirm_body
        )
        if result.status_code != 200:
            return {
                "error": "confirm",
                "index": index,
                "status": result.status_code,
                "detail": result.json().get("detail"),
                "header_matches": result.request.headers.get("Authorization")
                == headers["Authorization"],
            }
        receipt_rows = result.json()["rows"]
        if (
            len(receipt_rows) != 1
            or receipt_rows[0]["outcome"] != "publish"
            or receipt_rows[0]["food_id"] is None
        ):
            return {"error": "confirm_receipt", "index": index}
        return {"upload": upload, "review": review, "confirm": confirm}


source = csv_report(200)
if __name__ == "__main__":
    configuration = httpx.get(BASE + "/api/v1/public/config", timeout=10)
    configuration.raise_for_status()
    if configuration.json().get("app_env") != "dev" or not configuration.json().get(
        "enable_dev_auth"
    ):
        raise RuntimeError("benchmark requires an isolated dev-auth test server")
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as pool:
        sampler = pool.submit(collect)
        try:
            results = list(pool.map(run, range(20)))
        finally:
            elapsed = time.perf_counter() - started
            stop.set()
        sampler.result()
    errors = [r for r in results if "error" in r]
    print(
        f"rows=200 bytes={len(source)} concurrency=2 total=20 elapsed={elapsed:.3f}s errors={errors}"
    )
    good = [r for r in results if "error" not in r]
    for key in ("upload", "review", "confirm"):
        values = sorted(item[key] for item in good)
        if values:
            print(
                f"{key}: n={len(values)} p50={statistics.median(values):.3f}s p95={values[math.ceil(0.95 * len(values)) - 1]:.3f}s max={max(values):.3f}s"
            )
    for name, readings in samples.items():
        if readings:
            print(
                f"{name}: samples={len(readings)} sampled_peak_cpu={max(x[0] for x in readings):.2f}% sampled_peak_memory={max(x[1] for x in readings):.1f}MiB"
            )
    print(f"postgres_active_client_backends_sampled_peak={max(active_sessions, default=0)}")
    if errors or any(not readings for readings in samples.values()):
        raise SystemExit(1)
