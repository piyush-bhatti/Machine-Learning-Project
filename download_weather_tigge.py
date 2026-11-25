"""
Download day-ahead weather forecasts for Belgium from the TIGGE archive (ECMWF),
in small files of a few days each, into the folder tigge_grib/.

Why this script exists
    download_weather_dayahead.py gives hourly day-ahead forecasts, but only from March 2024.
    TIGGE keeps the forecasts ECMWF actually issued, back to 2006. That gives the full Elia
    history (from October 2020), at the price of 6-hour steps instead of hourly ones.

What is downloaded, for every day
    - the ECMWF high-resolution forecast started at 00:00 UTC (the run a trader has at 11:00
      Belgian time on that day),
    - lead times 18 to 48 hours, which cover the whole of the NEXT day (the delivery day),
    - 19 weather variables, on a box around Belgium (all eleven areas at once).
    Some variables are running totals counted from the start of the run (sunlight, rain, heat
    flows). build_weather_tigge.py then turns the maps into a table, and the preparation
    notebook turns the running totals into 6-hour amounts.

Why a few days per request
    The archive serves small requests first. A request for a whole month waited more than an
    hour in the queue, while requests for one to three days started within seconds. Requests
    are sent strictly one after another, as ECMWF asks.

Before running
    1. pip install cdsapi
    2. Save your ECMWF Data Store key in the file ~/.cdsapirc (see "Your profile" on
       https://ecds.ecmwf.int). Keep the key out of this folder and out of GitHub.
    3. Accept the "TIGGE licence" under Licences in your profile.

Usage
    python download_weather_tigge.py                 everything, October 2020 to October 2026
    python download_weather_tigge.py --dry-run       only print what would be requested
    python download_weather_tigge.py --start 2024-01 --end 2024-03      some months only
    python download_weather_tigge.py --days 5        five days per request instead of three

    It can be stopped (Ctrl+C) and started again at any time: files already downloaded are skipped.
    About 740 requests of three days each. It stops by itself after three failures in a row.

Source: TIGGE archive, ECMWF Data Store, dataset "tigge-forecasts"
        https://ecds.ecmwf.int/datasets/tigge-forecasts
        Free for research and education. TIGGE and ECMWF must be credited as the source.
"""
import argparse
import calendar
import time
from pathlib import Path

DATASET = "tigge-forecasts"
OUT_DIR = Path("tigge_grib")

FIRST_RUN = "2020-10-01"      # Elia's solar data starts on 1 October 2020
LAST_RUN = "2026-10-24"       # the run of 24 October covers delivery day 25 October 2026, the last day of the Elia file
DAYS_PER_REQUEST = 3          # tested: a three-day request starts within seconds
PAUSE_SECONDS = 2             # short pause between requests
MAX_FAILURES_IN_A_ROW = 3     # then stop, so that a problem is not repeated hundreds of times

VARIABLES = [   # names as the TIGGE download form writes them
    "10_m_u_component_of_wind",
    "10_m_v_component_of_wind",
    "2_m_dewpoint_temperature",
    "2_m_temperature",
    "convective_available_potential_energy",
    "maximum_2_m_temperature_in_the_last_6_hours",
    "mean_sea_level_pressure",
    "minimum_2_m_temperature_in_the_last_6_hours",
    "skin_temperature",
    "sunshine_duration",
    "surface_pressure",
    "total_cloud_cover",
    "total_column_water",
    "surface_latent_heat_flux",
    "surface_net_solar_radiation",
    "surface_net_thermal_radiation",
    "surface_sensible_heat_flux",
    "top_net_thermal_radiation",
    "total_precipitation",
]   # convective_inhibition is left out: the test files showed it is mostly blank, with placeholder values

BASE = {
    "origin": "ecmwf",
    "time": "00:00",                                          # the run started at midnight UTC
    "level_type": "single_level",
    "variable": VARIABLES,
    "forecast_type": "high_resolution_forecast",
    "leadtime_hour": ["18", "24", "30", "36", "42", "48"],   # hours after the start of the run
    "data_format": "grib",
    "area": [52, 2, 49, 7],                                   # north, west, south, east: a box around Belgium
}


def pieces_to_get(start, end, days_per_request):
    """One entry per request: (year, month, list of days). A request never crosses a month end."""
    first = max(start + "-01", FIRST_RUN)
    last_year, last_month = int(end[:4]), int(end[5:7])
    last = min(f"{end}-{calendar.monthrange(last_year, last_month)[1]:02d}", LAST_RUN)
    out, (y, m) = [], (int(first[:4]), int(first[5:7]))
    while (y, m) <= (int(last[:4]), int(last[5:7])):
        days = [d for d in range(1, calendar.monthrange(y, m)[1] + 1)
                if first <= f"{y}-{m:02d}-{d:02d}" <= last]
        for i in range(0, len(days), days_per_request):
            out.append((y, m, days[i:i + days_per_request]))
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out


def file_for(y, m, days):
    return OUT_DIR / f"tigge_{y}-{m:02d}-{days[0]:02d}_to_{days[-1]:02d}.grib"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default=FIRST_RUN[:7], help="first month, as YYYY-MM")
    p.add_argument("--end", default=LAST_RUN[:7], help="last month, as YYYY-MM")
    p.add_argument("--days", type=int, default=DAYS_PER_REQUEST, help="days per request. Keep the same value for a whole download")
    p.add_argument("--dry-run", action="store_true", help="print the plan, download nothing")
    args = p.parse_args()

    plan = pieces_to_get(args.start, args.end, args.days)
    # A piece is done if its own file exists, or if a file for its whole month exists
    # (the first download attempt saved October 2020 as one monthly file).
    def is_done(piece):
        y, m, _ = piece
        return file_for(*piece).exists() or (OUT_DIR / f"tigge_{y}-{m:02d}.grib").exists()

    todo = [piece for piece in plan if not is_done(piece)]
    runs = sum(len(d) for _, _, d in todo)
    print(f"{len(plan)} requests in the plan, {len(plan) - len(todo)} already downloaded, {len(todo)} to get ({runs} forecast runs)")
    if args.dry_run:
        for piece in todo[:5]:
            print(f"  {file_for(*piece).name}")
        if len(todo) > 5:
            print(f"  ... and {len(todo) - 5} more, ending with {file_for(*todo[-1]).name}")
        return
    if not todo:
        return

    import cdsapi                                   # imported here so that --dry-run works without it
    client = cdsapi.Client()
    OUT_DIR.mkdir(exist_ok=True)

    began, done, failures_in_a_row = time.time(), 0, 0
    for n, (y, m, days) in enumerate(todo, 1):
        target = file_for(y, m, days)
        part = target.with_suffix(".part")          # downloaded under a temporary name, renamed when complete
        request = {**BASE, "year": str(y), "month": f"{m:02d}", "day": [f"{d:02d}" for d in days]}
        start = time.time()
        try:
            client.retrieve(DATASET, request, str(part))
            part.replace(target)
            done, failures_in_a_row = done + 1, 0
            left = (time.time() - began) / done * (len(todo) - n) / 60
            print(f"[{n}/{len(todo)}] saved {target.name} in {time.time() - start:.0f} s. About {left:.0f} minutes left", flush=True)
        except KeyboardInterrupt:
            print("\nStopped. Run the script again to continue from here.")
            return
        except Exception as e:
            failures_in_a_row += 1
            print(f"[{n}/{len(todo)}] FAILED {target.name} after {time.time() - start:.0f} s: {type(e).__name__}: {e}", flush=True)
            if failures_in_a_row >= MAX_FAILURES_IN_A_ROW:
                print(f"\n{MAX_FAILURES_IN_A_ROW} failures in a row: stopping. Check the message above, then run the script again.")
                return
        time.sleep(PAUSE_SECONDS)

    have = sum(is_done(piece) for piece in plan)
    print(f"\nFinished. {have} of {len(plan)} requests are covered by the files in {OUT_DIR}/")
    if have < len(plan):
        print("Some requests failed. Run the script again to retry only those.")


if __name__ == "__main__":
    main()
