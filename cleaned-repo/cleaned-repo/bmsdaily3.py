import json
import os
import random
import time
import threading
import signal
from datetime import datetime, timedelta, timezone
import cloudscraper

# =====================================================
# =====================================================
SHARD_ID = 3
API_TIMEOUT = 12
HARD_TIMEOUT = 15
MAX_RECOVERY_ROUNDS = 5           # max retries per venue (initial + retry rounds)
IDENTITY_ROTATE_EVERY = 10        # new identity after every N requests
FAILURE_THRESHOLD = 5             # consecutive failures before cooldown
COOLDOWN_SECONDS = 90             # pause when too many failures
BASE_DELAY = 0.45                  # minimum seconds between requests
MAX_DELAY = 1.75                   # maximum seconds between requests (adaptive)

# ⏱️ cutoff window (minutes)
CUTOFF_MINUTES = 210              # ≈ 3h 30m – only shows within this window are kept

IST = timezone(timedelta(hours=5, minutes=30))

# 🔥 TODAY ONLY (daily tracking)
DATE_CODE = datetime.now(IST).strftime("%Y%m%d")

BASE_DIR = os.path.join("daily", "data", DATE_CODE)
LOG_DIR  = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

DETAILED_FILE = f"{BASE_DIR}/detailed{SHARD_ID}.json"
SUMMARY_FILE  = f"{BASE_DIR}/movie_summary{SHARD_ID}.json"
LOG_FILE      = f"{LOG_DIR}/bmsdaily{SHARD_ID}.log"

# =====================================================
# LOGGING
# =====================================================
def log(msg):
    ts = datetime.now(IST).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# =====================================================
# HARD TIMEOUT
# =====================================================
class TimeoutError(Exception):
    pass

def _timeout_handler(signum, frame):
    raise TimeoutError("Hard timeout hit")

def hard_timeout(seconds):
    def deco(fn):
        def wrapper(*args, **kwargs):
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(seconds)
            try:
                return fn(*args, **kwargs)
            finally:
                signal.alarm(0)
        return wrapper
    return deco

# =====================================================
# IDENTITY / UA ROTATION (enhanced)
# =====================================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
]

thread_local = threading.local()
request_counter = 0

class Identity:
    def __init__(self):
        self.ua = random.choice(USER_AGENTS)
        self.ip = ".".join(str(random.randint(20, 230)) for _ in range(4))
        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "desktop": True}
        )

    def headers(self):
        # Full browser-like headers
        return {
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-IN,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Origin": "https://in.bookmyshow.com",
            "Referer": "https://in.bookmyshow.com/",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "X-Forwarded-For": self.ip,
        }

def get_identity():
    global request_counter
    if not hasattr(thread_local, "identity"):
        thread_local.identity = Identity()
        log("🧠 New identity created")
    request_counter += 1
    # Rotate proactively every N requests
    if request_counter % IDENTITY_ROTATE_EVERY == 0:
        reset_identity()
        thread_local.identity = Identity()
        log(f"🔄 Identity rotated (every {IDENTITY_ROTATE_EVERY} requests)")
    return thread_local.identity

def reset_identity():
    if hasattr(thread_local, "identity"):
        del thread_local.identity
    log("🔄 Identity reset")

# =====================================================
# FETCH API (with retry and block detection)
# =====================================================
@hard_timeout(HARD_TIMEOUT)
def fetch_api_raw(venue_code):
    ident = get_identity()
    url = (
        "https://in.bookmyshow.com/api/v2/mobile/showtimes/byvenue"
        f"?venueCode={venue_code}&dateCode={DATE_CODE}"
    )
    r = ident.scraper.get(url, headers=ident.headers(), timeout=API_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    text = r.text.strip()
    if not text.startswith("{"):
        snippet = text[:200].replace("\n", " ")
        raise RuntimeError(f"Blocked / HTML (snippet: {snippet})")
    return r.json()

def fetch_with_retry(venue_code, attempt=1):
    try:
        return fetch_api_raw(venue_code)
    except Exception as e:
        if attempt >= MAX_RECOVERY_ROUNDS:
            log(f"❌ {venue_code} failed after {MAX_RECOVERY_ROUNDS} attempts")
            raise
        delay = (2 ** attempt) + random.uniform(0, 1)   # exponential backoff
        log(f"🔄 Retry {attempt}/{MAX_RECOVERY_ROUNDS} for {venue_code} in {delay:.1f}s")
        reset_identity()
        time.sleep(delay)
        return fetch_with_retry(venue_code, attempt + 1)

# =====================================================
# TIME HELPERS (CUTOFF)
# =====================================================
def minutes_left(show_time_str):
    """
    Convert 'hh:mm AM/PM' to minutes left from now (IST).
    """
    try:
        now = datetime.now(IST)
        t = datetime.strptime(show_time_str, "%I:%M %p")
        t = t.replace(
            year=now.year,
            month=now.month,
            day=now.day,
            tzinfo=IST
        )
        return (t - now).total_seconds() / 60
    except Exception:
        return 9999

# =====================================================
# PARSER
# =====================================================
def parse_payload(data):
    out = []

    sd = data.get("ShowDetails", [])
    if not sd:
        return out

    venue = sd[0].get("Venues", {})
    venue_name = venue.get("VenueName", "")
    venue_add  = venue.get("VenueAdd", "")
    chain      = venue.get("VenueCompName", "Unknown")

    for ev in sd[0].get("Event", []):
        title = ev.get("EventTitle", "Unknown")

        for ch in ev.get("ChildEvents", []):
            dim  = ch.get("EventDimension", "").strip()
            lang = ch.get("EventLanguage", "").strip()
            suffix = " | ".join(x for x in (dim, lang) if x)
            movie = f"{title} [{suffix}]" if suffix else title

            for sh in ch.get("ShowTimes", []):
                if sh.get("ShowDateCode") != DATE_CODE:
                    continue

                total = sold = avail = gross = 0
                for cat in sh.get("Categories", []):
                    seats = int(cat.get("MaxSeats", 0))
                    free  = int(cat.get("SeatsAvail", 0))
                    price = float(cat.get("CurPrice", 0))
                    total += seats
                    avail += free
                    sold  += seats - free
                    gross += (seats - free) * price

                out.append({
                    "movie": movie,
                    "venue": venue_name,
                    "address": venue_add,
                    "chain": chain,
                    "time": sh.get("ShowTime", ""),
                    "audi": sh.get("Attributes", "") or "",
                    "session_id": str(sh.get("SessionId", "")),
                    "totalSeats": total,
                    "available": avail,
                    "sold": sold,
                    "gross": round(gross, 2)
                })

    return out

# =====================================================
# STABLE SHOW KEY
# =====================================================
def show_key(r):
    return (
        r["venue"],
        r["time"],
        r["session_id"],
        r["audi"]
    )

# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    log("🚀 BMS DAILY TRACKER STARTED (enhanced anti‑detection)")

    with open(f"venues{SHARD_ID}.json", "r", encoding="utf-8") as f:
        venues = json.load(f)

    fetched = []
    retry = set()
    failure_count = 0

    # ------ INITIAL PASS ------
    for i, vcode in enumerate(venues, 1):
        log(f"[{i}/{len(venues)}] {vcode}")

        # Adaptive delay: increase after failures
        delay = BASE_DELAY + (failure_count * 0.2)
        delay = min(delay, MAX_DELAY)
        time.sleep(random.uniform(delay, delay + 0.3))

        try:
            raw = fetch_with_retry(vcode)   # retry wrapper
            for r in parse_payload(raw):
                mins = minutes_left(r["time"])
                if mins <= CUTOFF_MINUTES:
                    r["minsLeft"] = round(mins, 1)
                    r["city"]   = venues[vcode].get("City", "Unknown")
                    r["state"]  = venues[vcode].get("State", "Unknown")
                    r["source"] = "BMS"
                    r["date"]   = DATE_CODE
                    fetched.append(r)
            failure_count = 0   # reset on success
        except Exception as e:
            retry.add(vcode)
            failure_count += 1
            if failure_count >= FAILURE_THRESHOLD:
                log(f"⛔ {failure_count} consecutive failures – cooling down {COOLDOWN_SECONDS}s")
                time.sleep(COOLDOWN_SECONDS)
                failure_count = 0
            reset_identity()
            log(f"❌ {vcode} final failure | {type(e).__name__} | {str(e)[:100]}")

    # ------ RETRY ROUNDS (for failed venues) ------
    for attempt in range(1, MAX_RECOVERY_ROUNDS + 1):
        if not retry:
            break

        log(f"🔁 RETRY ROUND {attempt} | Remaining: {len(retry)}")
        current_retry = list(retry)
        retry.clear()

        for vcode in current_retry:
            log(f"[RETRY-{attempt}] {vcode}")
            # Adaptive delay inside retry (slightly longer)
            time.sleep(random.uniform(1.0, 2.5))

            try:
                raw = fetch_with_retry(vcode, attempt=1)  # will use its own retries
                for r in parse_payload(raw):
                    mins = minutes_left(r["time"])
                    if mins <= CUTOFF_MINUTES:
                        r["minsLeft"] = round(mins, 1)
                        r["city"]   = venues[vcode].get("City", "Unknown")
                        r["state"]  = venues[vcode].get("State", "Unknown")
                        r["source"] = "BMS"
                        r["date"]   = DATE_CODE
                        fetched.append(r)
            except Exception as e:
                retry.add(vcode)
                reset_identity()
                log(f"❌ RETRY FAIL {vcode} | {type(e).__name__}")

            time.sleep(random.uniform(0.5, 1.0))   # small delay between retry items

    if retry:
        log(f"⚠️ FINAL FAILED VENUES: {len(retry)}")
        log(f"FAILED LIST: {list(retry)}")

    # =====================================================
    # LOAD OLD DETAILED (NEVER DELETE)
    # =====================================================
    if os.path.exists(DETAILED_FILE):
        with open(DETAILED_FILE, "r", encoding="utf-8") as f:
            old_rows = json.load(f)
    else:
        old_rows = []

    old_map = {show_key(r): r for r in old_rows}
    new_map = {}

    for r in fetched:
        key = show_key(r)
        if key in old_map:
            # 🔁 overwrite live fields only
            old_map[key].update({
                "totalSeats": r["totalSeats"],
                "available":  r["available"],
                "sold":       r["sold"],
                "gross":      r["gross"],
                "minsLeft":   r.get("minsLeft")
            })
            new_map[key] = old_map[key]
        else:
            new_map[key] = r

    # 🧠 keep disappeared shows forever
    for key, r in old_map.items():
        if key not in new_map:
            new_map[key] = r

    detailed = list(new_map.values())

    # =====================================================
    # SUMMARY (REBUILT FROM DETAILED)
    # =====================================================
    summary = {}

    for r in detailed:
        movie = r["movie"]
        city  = r["city"]
        venue = r["venue"]

        total = r["totalSeats"]
        sold  = r["sold"]
        gross = r["gross"]
        occ   = (sold / total * 100) if total else 0

        if movie not in summary:
            summary[movie] = {
                "shows": 0,
                "gross": 0.0,
                "sold": 0,
                "totalSeats": 0,
                "venues": set(),
                "cities": set(),
                "fastfilling": 0,
                "housefull": 0
            }

        m = summary[movie]
        m["shows"] += 1
        m["gross"] += gross
        m["sold"] += sold
        m["totalSeats"] += total
        m["venues"].add(venue)
        m["cities"].add(city)

        if occ >= 98:
            m["housefull"] += 1
        elif occ >= 50:
            m["fastfilling"] += 1

    final_summary = {
        movie: {
            "shows": m["shows"],
            "gross": round(m["gross"], 2),
            "sold": m["sold"],
            "totalSeats": m["totalSeats"],
            "venues": len(m["venues"]),
            "cities": len(m["cities"]),
            "fastfilling": m["fastfilling"],
            "housefull": m["housefull"],
            "occupancy": round((m["sold"] / m["totalSeats"]) * 100, 2) if m["totalSeats"] else 0.0
        }
        for movie, m in summary.items()
    }

    # =====================================================
    # SAVE
    # =====================================================
    with open(DETAILED_FILE, "w", encoding="utf-8") as f:
        json.dump(detailed, f, indent=2, ensure_ascii=False)

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(final_summary, f, indent=2, ensure_ascii=False)

    log(f"✅ DONE | Shows={len(detailed)} | Movies={len(final_summary)}")
