import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

# ============================================================
# CONFIG
# ============================================================

START_DATE = datetime(2026, 1, 1, tzinfo=ZoneInfo("Asia/Kolkata"))
TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()

BASE_URL = "https://bfilmyapi.pages.dev/daily/data"
OUTPUT_ROOT = "daily/data"

MAX_WORKERS = 50

FILES = [
    *(f"detailed{i}.json" for i in range(1, 10)),
    "finaldetailed.json",
    "finalsummary.json",
    *(f"movie_summary{i}.json" for i in range(1, 10)),
]

# ============================================================
# BUILD DATE LIST
# ============================================================

dates = []

current = START_DATE.date()

while current <= TODAY:
    dates.append(current)
    current += timedelta(days=1)

print("=" * 60)
print("🚀 BULK DAILY DATA FETCH")
print("=" * 60)
print(f"📅 Start : {START_DATE:%Y-%m-%d} IST")
print(f"📅 End   : {TODAY:%Y-%m-%d} IST")
print(f"📆 Dates : {len(dates)}")
print(f"📄 Files/date : {len(FILES)}")
print(f"📦 Total files: {len(dates) * len(FILES)}")
print(f"⚡ Workers: {MAX_WORKERS}")
print("=" * 60)

# ============================================================
# DOWNLOAD
# ============================================================

def download(item):
    date, filename = item

    date_str = date.strftime("%Y%m%d")
    url = f"{BASE_URL}/{date_str}/{filename}"

    output_dir = os.path.join(OUTPUT_ROOT, date_str)
    output_file = os.path.join(output_dir, filename)

    os.makedirs(output_dir, exist_ok=True)

    try:
        r = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        if r.status_code == 404:
            return date_str, filename, 0, "404"

        r.raise_for_status()

        with open(output_file, "wb") as f:
            f.write(r.content)

        return date_str, filename, len(r.content), None

    except Exception as e:
        return date_str, filename, 0, str(e)


# Create all jobs
jobs = [
    (date, filename)
    for date in dates
    for filename in FILES
]

success = 0
failed = []

# ============================================================
# PARALLEL DOWNLOAD
# ============================================================

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

    futures = [
        executor.submit(download, job)
        for job in jobs
    ]

    for future in as_completed(futures):

        date_str, filename, size, error = future.result()

        if error:
            failed.append((date_str, filename, error))

            print(
                f"❌ {date_str}/{filename} → {error}"
            )

        else:
            success += 1

            print(
                f"✅ {date_str}/{filename} "
                f"({size:,} bytes)"
            )

# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 60)
print("📊 DOWNLOAD SUMMARY")
print("=" * 60)

print(f"✅ Successful : {success}")
print(f"❌ Failed     : {len(failed)}")
print(f"📦 Total      : {len(jobs)}")

if failed:
    print()
    print("❌ FAILED FILES:")

    for date_str, filename, error in failed:
        print(f"   {date_str}/{filename} → {error}")

# ============================================================
# DON'T PUSH IF DOWNLOADS FAILED
# ============================================================

if failed:
    print()
    print("🛑 NOT PUSHING — SOME FILES FAILED.")
    raise SystemExit(1)

# ============================================================
# GIT ADD
# ============================================================

print()
print("📦 Git add...")

subprocess.run(
    ["git", "add", "--", OUTPUT_ROOT],
    check=True
)

# ============================================================
# CHECK CHANGES
# ============================================================

status = subprocess.run(
    ["git", "status", "--porcelain"],
    capture_output=True,
    text=True,
    check=True
)

if not status.stdout.strip():
    print("ℹ️ No changes to commit.")
    raise SystemExit(0)

# ============================================================
# COMMIT
# ============================================================

print("💾 Creating commit...")

subprocess.run(
    [
        "git",
        "commit",
        "-m",
        f"Import daily data {START_DATE:%Y-%m-%d} to {TODAY:%Y-%m-%d}"
    ],
    check=True
)

# ============================================================
# FORCE PUSH
# ============================================================

branch = subprocess.run(
    ["git", "branch", "--show-current"],
    capture_output=True,
    text=True,
    check=True
).stdout.strip()

if not branch:
    raise SystemExit("❌ Could not determine current branch.")

print()
print(f"🚀 Force pushing branch: {branch}")

subprocess.run(
    [
        "git",
        "push",
        "origin",
        branch,
        "--force"
    ],
    check=True
)

print()
print("=" * 60)
print("✅ COMPLETE")
print("=" * 60)
print(f"📅 {START_DATE:%Y-%m-%d} → {TODAY:%Y-%m-%d}")
print(f"📦 {success} files downloaded")
print(f"🚀 Force push completed")
print("=" * 60)
