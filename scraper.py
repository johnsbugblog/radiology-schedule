"""
Lightning Bolt Schedule Scraper
Fetches the public schedule and writes data.json in the format
expected by index.html.

Run: python3 scraper.py
Cron (every 15 min): */15 * * * * cd /path/to && python3 scraper.py
"""

import json, re, sys
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

URL = "https://lblite.lightning-bolt.com/public/659663dc-49b3-b9fd-a11872df3ca1"
OUTPUT = "data.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ScheduleBot/1.0)"}

# ── Field mapping: Lightning Bolt assignment name → your app's key ──────────
# Edit these to match whatever assignment names appear in the live page.
FIELD_MAP = {
    # IR
    "¶IR 4553151":      "IR Primary",
    "¶IR/CT 4554653":   "IR/CT",
    "¶IR Assist":       "IR Assist",

    # Coverage
    "¶ GMH 1 Upfront\n4553174": "Upfront",
    "¶ PEDS 4553177":   "Peds",
    "¶Neuro Proc\n4557079": "Neuro Proc",

    # Misc — add more as needed
    # "US Flow Tech":   "US Flow Tech",
    # "Charge RN":      "Charge RN",
}

# Assignment names that belong to the PA section
PA_ROLES = {
    "PA IR Outpatient":      "PA IR Outpatient",
    "PA CT":                 "PA CT",
    "PA IR Inpatient 1":     "PA IR Inpatient",
    "PA GOR":                "PA GOR",
    "PA GMH FL 1":           "PA GMH FL",
    "PA Vacation":           "OFF Vacation",
    "PA Not Working":        "OFF",
    "PA Greer Half":         "PA Greer (half)",
    "PA IR Outpatient\nHalf":"PA IR Outpatient (half)",
    "PA GMH FL Half":        "PA GMH FL (half)",
}


def fetch_page():
    resp = requests.get(URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def infer_year(month: int) -> int:
    today = date.today()
    year = today.year
    if month < today.month - 1:
        year += 1
    return year


def parse_schedule(soup: BeautifulSoup) -> dict:
    table = soup.find("table")
    if not table:
        raise ValueError("No <table> found — page may be JS-rendered (use Playwright fallback).")

    rows = table.find_all("tr")
    header = rows[0].find_all(["th", "td"])

    # Build column → date-key map  (e.g. col 2 → "06/25")
    col_to_key: dict[int, str] = {}
    for i, cell in enumerate(header):
        text = cell.get_text(" ", strip=True)
        m = re.search(r"(\d{1,2})/(\d{2})", text)
        if m:
            mo, dy = int(m.group(1)), int(m.group(2))
            col_to_key[i] = f"{mo:02d}/{dy:02d}"

    # schedule[date_key][field] = value
    schedule: dict[str, dict] = {k: {} for k in col_to_key.values()}

    for row in rows[1:]:
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        assignment = cells[0].get_text(" ", strip=True).strip()
        if not assignment:
            continue

        # ── Named fields ────────────────────────────────────────────────
        field = None
        for raw, mapped in FIELD_MAP.items():
            if assignment.replace("\n", " ").strip() == raw.replace("\n", " ").strip():
                field = mapped
                break
        # Fuzzy fallback: strip phone numbers / whitespace
        if field is None:
            clean = re.sub(r"\d{7,}", "", assignment).strip().rstrip("\n").strip()
            for raw, mapped in FIELD_MAP.items():
                if clean == re.sub(r"\d{7,}", "", raw).strip():
                    field = mapped
                    break

        if field:
            for col, key in col_to_key.items():
                if col < len(cells):
                    val = cells[col].get_text(" ", strip=True).strip()
                    if val:
                        schedule[key][field] = val
            continue

        # ── PA section ──────────────────────────────────────────────────
        pa_role = None
        for raw, role in PA_ROLES.items():
            if assignment.replace("\n", " ").strip() == raw.replace("\n", " ").strip():
                pa_role = role
                break

        if pa_role:
            for col, key in col_to_key.items():
                if col < len(cells):
                    val = cells[col].get_text(" ", strip=True).strip()
                    if val:
                        schedule[key].setdefault("PAs", [])
                        # A cell may contain multiple names separated by newlines
                        for name in re.split(r"\n+", val):
                            name = name.strip()
                            if name:
                                schedule[key]["PAs"].append({"name": name, "role": pa_role})

    return schedule


def main():
    print(f"[{datetime.now().isoformat()}] Fetching {URL} ...", file=sys.stderr)
    try:
        soup = fetch_page()
        schedule = parse_schedule(soup)

        output = {"generated_at": datetime.utcnow().isoformat() + "Z", "schedule": schedule}
        with open(OUTPUT, "w") as f:
            json.dump(output, f, indent=2)
        print(f"Wrote {OUTPUT} with {len(schedule)} days.", file=sys.stderr)
        # Also print today's slice for quick verification
        today_key = date.today().strftime("%m/%d")
        print(json.dumps(schedule.get(today_key, {}), indent=2))
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
