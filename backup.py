import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests


# ============================================================
# CONFIG
# ============================================================

IST = ZoneInfo("Asia/Kolkata")

START_DATE = datetime(
    2026, 7, 30,
    tzinfo=IST
).date()

TODAY_IST = datetime.now(IST).date()

# Today IST + 5 days
END_DATE = TODAY_IST + timedelta(days=5)

SOURCE_BASE_URL = (
    "https://bfilmyapi2026.pages.dev/advance/data"
)

OUTPUT_ROOT = "advance/data"

MAX_WORKERS = 50

FILES = [
    "finaldetailed.json",
    "finalsummary.json",
]


# ============================================================
# DATES
# ============================================================

dates = []

current = START_DATE

while current <= END_DATE:

    dates.append(current)

    current += timedelta(days=1)


jobs = [
    (date, filename)
    for date in dates
    for filename in FILES
]


# ============================================================
# HEADER
# ============================================================

print("=" * 60)
print("🚀 ADVANCE DATA BACKUP")
print("=" * 60)

print(
    f"📅 Start       : {START_DATE}"
)

print(
    f"📅 End         : {END_DATE} "
    f"(today IST + 5 days)"
)

print(
    f"📆 Dates       : {len(dates)}"
)

print(
    f"📄 Files/date  : {len(FILES)}"
)

print(
    f"📦 Total jobs  : {len(jobs)}"
)

print(
    f"⚡ Workers     : {MAX_WORKERS}"
)

print("=" * 60)


# ============================================================
# DOWNLOAD
# ============================================================

def download(item):

    date, filename = item

    # --------------------------------------------------------
    # SOURCE
    #
    # YYYY/MM-DD_finalsummary.json
    # YYYY/MM-DD_finaldetailed.json
    # --------------------------------------------------------

    year = date.strftime("%Y")
    month_day = date.strftime("%m-%d")

    source_filename = (
        f"{month_day}_{filename}"
    )

    url = (
        f"{SOURCE_BASE_URL}/"
        f"{year}/"
        f"{source_filename}"
    )

    # --------------------------------------------------------
    # DESTINATION
    #
    # advance/data/YYYYMMDD/finalsummary.json
    # advance/data/YYYYMMDD/finaldetailed.json
    # --------------------------------------------------------

    date_code = date.strftime("%Y%m%d")

    output_dir = os.path.join(
        OUTPUT_ROOT,
        date_code
    )

    output_file = os.path.join(
        output_dir,
        filename
    )

    try:

        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        # ----------------------------------------------------
        # 404 = normal missing file
        # ----------------------------------------------------

        if response.status_code == 404:

            return (
                date_code,
                filename,
                0,
                "404"
            )

        # ----------------------------------------------------
        # Other HTTP errors = REAL ERROR
        # ----------------------------------------------------

        response.raise_for_status()

        content = response.content

        # ----------------------------------------------------
        # Empty response = REAL ERROR
        # ----------------------------------------------------

        if not content:

            return (
                date_code,
                filename,
                0,
                "Empty response"
            )

        # ----------------------------------------------------
        # Save only after successful download
        # ----------------------------------------------------

        os.makedirs(
            output_dir,
            exist_ok=True
        )

        with open(
            output_file,
            "wb"
        ) as f:

            f.write(content)

        return (
            date_code,
            filename,
            len(content),
            None
        )

    except Exception as e:

        return (
            date_code,
            filename,
            0,
            str(e)
        )


# ============================================================
# PARALLEL FETCH
# ============================================================

success = 0
not_found = 0
failed = []


with ThreadPoolExecutor(
    max_workers=MAX_WORKERS
) as executor:

    futures = [
        executor.submit(
            download,
            job
        )
        for job in jobs
    ]

    for future in as_completed(
        futures
    ):

        (
            date_code,
            filename,
            size,
            error
        ) = future.result()

        # ----------------------------------------------------
        # 404
        # ----------------------------------------------------

        if error == "404":

            not_found += 1

            print(
                f"⚪ {date_code}/{filename}"
                f" → 404, skipped"
            )

        # ----------------------------------------------------
        # REAL ERROR
        # ----------------------------------------------------

        elif error:

            failed.append(
                (
                    date_code,
                    filename,
                    error
                )
            )

            print(
                f"❌ {date_code}/{filename}"
                f" → {error}"
            )

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        else:

            success += 1

            print(
                f"✅ {date_code}/{filename}"
                f" ({size:,} bytes)"
            )


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 60)
print("📊 SUMMARY")
print("=" * 60)

print(
    f"✅ Downloaded : {success}"
)

print(
    f"⚪ 404 skipped : {not_found}"
)

print(
    f"❌ Other fail  : {len(failed)}"
)

print(
    f"📦 Total jobs  : {len(jobs)}"
)


# ============================================================
# REAL DOWNLOAD ERRORS = STOP
# ============================================================

if failed:

    print()
    print("❌ FAILED FILES:")

    for (
        date_code,
        filename,
        error
    ) in failed:

        print(
            f"   {date_code}/{filename}"
            f" → {error}"
        )

    print()
    print(
        "🛑 NOT PUSHING — "
        "REAL DOWNLOAD ERRORS FOUND."
    )

    raise SystemExit(1)


# ============================================================
# COMPLETE
# ============================================================

print()
print("✅ Advance downloads completed.")
print("📦 Git commit/push will be handled by GitHub Actions.")
