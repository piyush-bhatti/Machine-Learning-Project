"""
Download DAY-AHEAD weather forecasts for the Belgian provinces from Open-Meteo
and save them as one parquet file.

Why this script exists
    download_weather.py uses the Historical Forecast API, which stitches together the first few
    hours of every model run. That is close to the weather that actually happened. A trader who
    decides at 11:00 for the next day does not have that: he has a forecast made that morning.
    This script downloads exactly that forecast, so the model is trained and tested on the same
    kind of information the trader really has.

The rule, for each delivery day D (a Belgian calendar day)
    1. Take the ECMWF run started at 00:00 UTC on day D-1. Open-Meteo publishes it at about
       04:00 to 06:00 UTC, so it is available before 11:00 Belgian time on D-1.
    2. Keep only the hours of that run that fall on delivery day D (Belgian time).
    Every row is therefore a forecast made roughly 23 to 48 hours ahead.

Output
    Same layout and same column names as weather_belgium.parquet: time (UTC, end of the hour),
    region, latitude, longitude, then the 16 Open-Meteo variables.

Usage
    python download_weather_dayahead.py                       Antwerp, 15 March 2024 to 25 October 2026
                                                              (about 950 requests, 5 to 10 minutes)
    python download_weather_dayahead.py --regions all         all 11 areas (about 10,500 requests:
                                                              may need two days on the free tier)
    python download_weather_dayahead.py --start 2025-06-01 --end 2025-06-30 --out sample.parquet

Needs: pandas, pyarrow, requests
Source: Open-Meteo Single Runs API, ECMWF IFS HRES 9 km (CC BY 4.0, free for non-commercial use)
        https://open-meteo.com/en/docs/single-runs-api
        Runs are archived from 14 March 2024, so the first delivery day is 15 March 2024.
"""
import argparse
import time

import pandas as pd
import requests

from download_weather import MODEL, POINTS, VARIABLES     # same model, same points, same variables

URL = "https://single-runs-api.open-meteo.com/v1/forecast"
LOCAL_TZ = "Europe/Brussels"
FIRST_DELIVERY_DAY = "2024-03-15"     # the day after the first archived run
SESSION = requests.Session()          # one connection reused for every request: faster and more reliable


def get_run(lat, lon, run_day, days):
    """One model run: the forecast started at 00:00 UTC on run_day, for the next `days` days."""
    params = {
        "latitude": lat, "longitude": lon, "hourly": ",".join(VARIABLES), "models": MODEL,
        "run": f"{run_day:%Y-%m-%d}T00:00", "forecast_days": days, "timezone": "UTC",
    }
    global SESSION
    for attempt in range(6):                 # retry on dropped connections and rate limits
        try:
            r = SESSION.get(URL, params=params, timeout=(10, 30))
            if r.status_code == 200:
                return r.json()
            if r.status_code == 400:         # this run is not in the archive
                return None
        except requests.exceptions.RequestException:
            SESSION = requests.Session()     # the connection dropped: open a new one
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"could not download run {run_day:%Y-%m-%d}")


def fetch_day(region, lat, lon, delivery_day):
    """Weather forecast for one area and one Belgian delivery day, as known the morning before."""
    # Delivery day D in Belgian time. Hours are labelled by their END, like the Elia table,
    # so the day is the hours ending from 01:00 on D to 00:00 on D+1.
    day_start = pd.Timestamp(delivery_day, tz=LOCAL_TZ)
    day_end = pd.Timestamp(pd.Timestamp(delivery_day) + pd.Timedelta(days=1), tz=LOCAL_TZ)   # next midnight, also right on clock-change days (23 or 25 hours)

    # Normal case: the run of D-1. If it is missing from the archive, or has holes in it,
    # fall back to the run of D-2, which is older and was therefore also available at decision time.
    df = None
    for back, days in ((1, 3), (2, 4)):
        run_day = pd.Timestamp(delivery_day) - pd.Timedelta(days=back)
        js = get_run(lat, lon, run_day, days)
        if js is None:
            continue
        df = pd.DataFrame(js["hourly"])
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df[(df["time"] > day_start) & (df["time"] <= day_end)].copy()
        if not df[VARIABLES].isna().any().any():
            break
    if df is None:
        return None, f"{region} {delivery_day:%Y-%m-%d}: no run available"

    df.insert(1, "region", region)
    df["latitude"], df["longitude"] = js["latitude"], js["longitude"]
    note = None if back == 1 else f"{region} {delivery_day:%Y-%m-%d}: used the run of two days before"
    return df[["time", "region", "latitude", "longitude", *VARIABLES]], note


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default=FIRST_DELIVERY_DAY, help="first delivery day")
    p.add_argument("--end", default="2026-10-25", help="last delivery day")
    p.add_argument("--regions", default="Antwerp", help='area names separated by commas, or "all"')
    p.add_argument("--out", default="weather_belgium_dayahead.parquet")
    args = p.parse_args()

    regions = list(POINTS) if args.regions == "all" else [r.strip() for r in args.regions.split(",")]
    start = max(args.start, FIRST_DELIVERY_DAY)
    days = pd.date_range(start, args.end, freq="D")
    jobs = [(r, *POINTS[r], d) for r in regions for d in days]
    print(f"{len(regions)} area(s), {len(days)} delivery days, {len(jobs)} requests")

    frames, notes, done = [], [], 0
    for job in jobs:
        df, note = fetch_day(*job)
        if df is not None and len(df):
            frames.append(df)
        if note:
            notes.append(note)
        done += 1
        if done % 100 == 0:
            print(f"  {done} / {len(jobs)}", flush=True)

    out = pd.concat(frames, ignore_index=True).sort_values(["region", "time"]).reset_index(drop=True)
    assert not out.duplicated(["region", "time"]).any(), "duplicate (area, hour) rows"
    out.to_parquet(args.out, index=False)
    print(f"wrote {args.out}: {len(out):,} rows, {out['time'].min()} to {out['time'].max()}")
    for n in notes:
        print("  note:", n)


if __name__ == "__main__":
    main()
