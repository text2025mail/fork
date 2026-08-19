import json, os, hashlib
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import pytz

SHARD_ID = 9
SOURCE_BASE_URL = "https://districtdata2026.pages.dev/advance"
DISTRICT_VENUES_FILE = "districtvenues.json"
ALL_DISTRICT_VENUES_FILE = "alldistrictvenues.json"
REQUEST_TIMEOUT = 30
IST = pytz.timezone("Asia/Kolkata")

NOW_IST = datetime.now(IST)
TARGET_DATE_IST = NOW_IST + timedelta(days=1)
DATE_CODE = TARGET_DATE_IST.strftime("%Y%m%d")
DATE_DISTRICT = TARGET_DATE_IST.strftime("%Y-%m-%d")

BASE_DIR = os.path.join("advance", "data", DATE_CODE)
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
DETAILED_FILE = os.path.join(BASE_DIR, f"detailed{SHARD_ID}.json")
SUMMARY_FILE = os.path.join(BASE_DIR, f"movie_summary{SHARD_ID}.json")
LOG_FILE = os.path.join(LOG_DIR, f"district{SHARD_ID}.log")

def log(message):
    timestamp = datetime.now(IST).strftime("%H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def load_json_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def normalize_venue_name(value):
    if value is None:
        return ""
    value = str(value)
    value = " ".join(value.split())
    return value.strip().casefold()

def format_state(value):
    if not value:
        return "Unknown"
    return " ".join(word.capitalize() for word in str(value).replace("-", " ").split())

def format_chain(value):
    if not value:
        return "Unknown"
    return " ".join(word.capitalize() for word in str(value).replace("-", " ").split())

def load_and_match_venues():
    district_venues = load_json_file(DISTRICT_VENUES_FILE)
    all_venues = load_json_file(ALL_DISTRICT_VENUES_FILE)
    log(f"📍 Selected venue IDs: {len(district_venues)}")
    log(f"📍 Master venue records: {len(all_venues)}")
    master_by_id = {}
    for venue in all_venues:
        if not isinstance(venue, dict):
            continue
        venue_id = venue.get("id")
        if venue_id is None:
            continue
        master_by_id[str(venue_id)] = venue
    selected_master = []
    missing_ids = []
    missing_names = []
    for selected in district_venues:
        if not isinstance(selected, dict):
            continue
        selected_id = selected.get("id")
        if selected_id is None:
            continue
        master = master_by_id.get(str(selected_id))
        if master is None:
            missing_ids.append(selected_id)
            continue
        official_name = str(master.get("name", "") or "").strip()
        if not official_name:
            missing_names.append(selected_id)
            continue
        selected_master.append({
            "selected_id": selected_id,
            "master_id": master.get("id"),
            "name": official_name,
            "address": str(master.get("address", "") or ""),
            "city": str(master.get("city", "Unknown") or "Unknown"),
            "state": str(master.get("state", "Unknown") or "Unknown"),
            "chainKey": str(master.get("chainKey", "Unknown") or "Unknown")
        })
    log(f"✅ ID → ID matched: {len(selected_master)}")
    log(f"⚠️ IDs missing from master: {len(missing_ids)}")
    log(f"⚠️ Master records without name: {len(missing_names)}")
    if missing_ids:
        for venue_id in missing_ids[:20]:
            log(f"   ❌ Master ID missing: {venue_id}")
        if len(missing_ids) > 20:
            log(f"   ... and {len(missing_ids) - 20} more")
    if missing_names:
        for venue_id in missing_names[:20]:
            log(f"   ❌ No master name: {venue_id}")
        if len(missing_names) > 20:
            log(f"   ... and {len(missing_names) - 20} more")
    return selected_master

def fetch_source():
    url = f"{SOURCE_BASE_URL}/{DATE_DISTRICT}_Detailed.json"
    log("📡 Fetching Advance Detailed JSON:")
    log(f"   {url}")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; BMSAdvance9/1.0)"})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            raw = response.read()
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Source JSON is not an object")
        if "dicts" not in data:
            raise ValueError("Missing dicts")
        if "movies" not in data:
            raise ValueError("Missing movies")
        log("✅ Source loaded")
        log(f"   Source date: {data.get('date')}")
        log(f"   Last updated: {data.get('lastUpdated')}")
        log(f"   Movie keys: {len(data.get('movies', {}))}")
        return data
    except HTTPError as e:
        if e.code == 404:
            log("❌ Source file not found (404) – will create empty outputs")
        else:
            log(f"❌ HTTP {e.code} – will create empty outputs")
        return None
    except URLError as e:
        log(f"❌ URL error: {e.reason} – will create empty outputs")
        return None
    except Exception as e:
        log(f"❌ Source error: {type(e).__name__}: {e} – will create empty outputs")
        return None

def reverse_dictionary(dictionary):
    if not isinstance(dictionary, dict):
        return {}
    return {int(value): key for key, value in dictionary.items()}

def build_reverse_dicts(source):
    dicts = source.get("dicts", {})
    return {
        "cities": reverse_dictionary(dicts.get("cities", {})),
        "states": reverse_dictionary(dicts.get("states", {})),
        "venues": reverse_dictionary(dicts.get("venues", {})),
        "chains": reverse_dictionary(dicts.get("chains", {})),
        "showtimes": reverse_dictionary(dicts.get("showtimes", {})),
        "audis": reverse_dictionary(dicts.get("audis", {}))
    }

def build_source_venue_lookup(reverse):
    lookup = {}
    source_venues = reverse["venues"]
    for source_id, source_name in source_venues.items():
        normalized = normalize_venue_name(source_name)
        if not normalized:
            continue
        lookup[normalized] = {"source_id": source_id, "source_name": source_name}
    return lookup

def match_master_to_source(selected_master, source_venue_lookup):
    matched = {}
    unmatched = []
    for venue in selected_master:
        master_name = venue["name"]
        normalized = normalize_venue_name(master_name)
        source_match = source_venue_lookup.get(normalized)
        if source_match is None:
            unmatched.append({"master_id": venue["master_id"], "name": master_name})
            continue
        source_id = source_match["source_id"]
        matched[source_id] = {**venue, "source_id": source_id, "source_name": source_match["source_name"]}
    log(f"🎯 Master-name → Source-name matches: {len(matched)}")
    log(f"⚠️ Master venues not found in source: {len(unmatched)}")
    if unmatched:
        for item in unmatched[:20]:
            log(f"   ❌ {item['master_id']} → {item['name']}")
        if len(unmatched) > 20:
            log(f"   ... and {len(unmatched) - 20} more")
    return matched

def decompress_show(row, reverse):
    if not isinstance(row, list) or len(row) < 12:
        return None
    try:
        city_id, state_id, venue_id, chain_id, time_id, audi_id = row[0], row[1], row[2], row[3], row[4], row[5]
        total = int(row[6] or 0)
        available = int(row[7] or 0)
        sold = int(row[8] or 0)
        gross_cents = int(row[9] or 0)
        occupancy_raw = int(row[10] or 0)
        mins_left = float(row[11] or 0)
        return {
            "city": reverse["cities"].get(city_id, "Unknown"),
            "state": reverse["states"].get(state_id, "Unknown"),
            "venue": reverse["venues"].get(venue_id, "Unknown"),
            "venue_id": venue_id,
            "chain": reverse["chains"].get(chain_id, "Unknown"),
            "time": reverse["showtimes"].get(time_id, ""),
            "audi": reverse["audis"].get(audi_id, ""),
            "totalSeats": total,
            "available": available,
            "sold": sold,
            "gross": gross_cents / 100,
            "occupancy": occupancy_raw / 100,
            "minsLeft": mins_left
        }
    except Exception:
        return None

def normalize_movie_name(value):
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()

def build_movie_key(movie_name, language):
    movie_name = normalize_movie_name(movie_name)
    language = str(language or "").strip()
    if not language:
        language = "Unknown"
    return f"{movie_name} [2D | {language}]"

def generate_session_id(movie, venue, time, audi):
    raw = "|".join([str(movie), str(venue), str(time), str(audi)])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"DISTRICT_{digest}"

def dedupe(rows):
    seen = set()
    output = []
    for row in rows:
        key = (row.get("venue", ""), row.get("time", ""), row.get("session_id", ""), row.get("audi", ""))
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output

def parse_source(source, matched_venues, reverse):
    detailed = []
    movies = source.get("movies", {})
    total_movie_keys = len(movies)
    matched_rows = 0
    ignored_rows = 0
    for raw_movie_key, rows in movies.items():
        if not isinstance(rows, list):
            continue
        if "|" in raw_movie_key:
            parts = [p.strip() for p in raw_movie_key.split("|")]
            movie_name = parts[0] if parts else raw_movie_key
            language = parts[-1] if len(parts) > 1 else "Unknown"
        else:
            movie_name = raw_movie_key.strip()
            language = "Unknown"
        movie_key = build_movie_key(movie_name, language)
        for compressed in rows:
            show = decompress_show(compressed, reverse)
            if not show:
                continue
            source_venue_id = show["venue_id"]
            selected_venue = matched_venues.get(source_venue_id)
            if selected_venue is None:
                ignored_rows += 1
                continue
            matched_rows += 1
            city = selected_venue.get("city") or "Unknown"
            state = format_state(selected_venue.get("state"))
            venue_name = selected_venue["name"]
            address = selected_venue.get("address") or ""
            chain = format_chain(selected_venue.get("chainKey"))
            time = str(show.get("time", "") or "").strip()
            audi = str(show.get("audi", "") or "")
            total = int(show.get("totalSeats", 0) or 0)
            available = int(show.get("available", 0) or 0)
            sold = total - available
            if sold < 0:
                sold = 0
            gross = float(show.get("gross", 0) or 0)
            session_id = generate_session_id(movie_key, venue_name, time, audi)
            detailed.append({
                "movie": movie_key,
                "city": city,
                "state": state,
                "venue": venue_name,
                "address": address,
                "time": time,
                "audi": audi,
                "session_id": session_id,
                "totalSeats": total,
                "available": available,
                "sold": sold,
                "gross": round(gross, 2),
                "occupancy": f"{round(show.get('occupancy', 0), 2)}%",
                "source": "District",
                "date": DATE_CODE,
                "chain": chain
            })
    detailed = dedupe(detailed)
    log(f"🎬 Source movie keys: {total_movie_keys}")
    log(f"🎟️ Selected-venue show rows: {matched_rows}")
    log(f"🚫 Non-selected show rows ignored: {ignored_rows}")
    log(f"🧹 After dedupe: {len(detailed)}")
    return detailed

def build_summary(detailed):
    summary = {}
    for row in detailed:
        movie = row["movie"]
        city = row["city"]
        state = row["state"]
        venue = row["venue"]
        chain = row["chain"]
        total = int(row.get("totalSeats", 0) or 0)
        sold = int(row.get("sold", 0) or 0)
        gross = float(row.get("gross", 0) or 0)
        occ = (sold / total * 100) if total else 0
        if movie not in summary:
            summary[movie] = {
                "shows": 0, "gross": 0.0, "sold": 0, "totalSeats": 0,
                "venues": set(), "cities": set(),
                "fastfilling": 0, "housefull": 0,
                "details": {}, "Chain_details": {}
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

        city_key = (city, state)
        if city_key not in m["details"]:
            m["details"][city_key] = {
                "city": city, "state": state,
                "venues": set(), "shows": 0, "gross": 0.0,
                "sold": 0, "totalSeats": 0,
                "fastfilling": 0, "housefull": 0
            }
        d = m["details"][city_key]
        d["venues"].add(venue)
        d["shows"] += 1
        d["gross"] += gross
        d["sold"] += sold
        d["totalSeats"] += total
        if occ >= 98:
            d["housefull"] += 1
        elif occ >= 50:
            d["fastfilling"] += 1

        if chain not in m["Chain_details"]:
            m["Chain_details"][chain] = {
                "chain": chain,
                "venues": set(), "shows": 0, "gross": 0.0,
                "sold": 0, "totalSeats": 0,
                "fastfilling": 0, "housefull": 0
            }
        c = m["Chain_details"][chain]
        c["venues"].add(venue)
        c["shows"] += 1
        c["gross"] += gross
        c["sold"] += sold
        c["totalSeats"] += total
        if occ >= 98:
            c["housefull"] += 1
        elif occ >= 50:
            c["fastfilling"] += 1

    final = {}
    for movie, m in summary.items():
        final[movie] = {
            "shows": m["shows"],
            "gross": round(m["gross"], 2),
            "sold": m["sold"],
            "totalSeats": m["totalSeats"],
            "venues": len(m["venues"]),
            "cities": len(m["cities"]),
            "fastfilling": m["fastfilling"],
            "housefull": m["housefull"],
            "occupancy": round((m["sold"] / m["totalSeats"] * 100) if m["totalSeats"] else 0.0, 2),
            "details": [],
            "Chain_details": []
        }
        for d in m["details"].values():
            final[movie]["details"].append({
                "city": d["city"],
                "state": d["state"],
                "venues": len(d["venues"]),
                "shows": d["shows"],
                "gross": round(d["gross"], 2),
                "sold": d["sold"],
                "totalSeats": d["totalSeats"],
                "fastfilling": d["fastfilling"],
                "housefull": d["housefull"],
                "occupancy": round((d["sold"] / d["totalSeats"] * 100) if d["totalSeats"] else 0.0, 2)
            })
        for c in m["Chain_details"].values():
            final[movie]["Chain_details"].append({
                "chain": c["chain"],
                "venues": len(c["venues"]),
                "shows": c["shows"],
                "gross": round(c["gross"], 2),
                "sold": c["sold"],
                "totalSeats": c["totalSeats"],
                "fastfilling": c["fastfilling"],
                "housefull": c["housefull"],
                "occupancy": round((c["sold"] / c["totalSeats"] * 100) if c["totalSeats"] else 0.0, 2)
            })
    return final

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def main():
    log("🚀 DISTRICT ADVANCE → BMS9 CONVERTER STARTED")
    log(f"📅 Date: {DATE_DISTRICT}")
    log("🚫 Worker logic: DISABLED")
    selected_master = load_and_match_venues()
    source = fetch_source()
    if source is None:
        log("⚠️ No source data – saving empty JSON files")
        save_json(DETAILED_FILE, [])
        save_json(SUMMARY_FILE, {})
        log(f"✅ DONE (empty) | Shows=0 | Movies=0")
        log(f"📄 Detailed: {DETAILED_FILE}")
        log(f"📄 Summary: {SUMMARY_FILE}")
        return
    reverse = build_reverse_dicts(source)
    source_venue_lookup = build_source_venue_lookup(reverse)
    matched_venues = match_master_to_source(selected_master, source_venue_lookup)
    detailed = parse_source(source, matched_venues, reverse)
    summary = build_summary(detailed)
    save_json(DETAILED_FILE, detailed)
    save_json(SUMMARY_FILE, summary)
    log(f"✅ DONE | Shows={len(detailed)} | Movies={len(summary)}")
    log(f"📄 Detailed: {DETAILED_FILE}")
    log(f"📄 Summary: {SUMMARY_FILE}")

if __name__ == "__main__":
    main()
