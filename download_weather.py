"""
Download archived weather forecasts for the Belgian provinces from Open-Meteo
and save them as one parquet file.

Usage:  python download_weather.py                     (January 2021 to 25 October 2026, writes weather_belgium.parquet)
                                                       This is what the project uses.
        python download_weather.py --start 2025-01-01 --end 2025-12-31 --out sample.parquet    (optional: other dates)

Needs: pandas, pyarrow, requests
Source: Open-Meteo Historical Forecast API, ECMWF IFS model (CC BY 4.0, free for non-commercial use)
        https://open-meteo.com/en/docs/historical-forecast-api
"""
import argparse
import time

import pandas as pd
import requests

URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

# One named weather model for the whole period. Without this, Open-Meteo picks its "best match",
# which was ECMWF IFS until mid 2024 and the Dutch KNMI model afterwards, so the data changed character.
# ECMWF IFS covers January 2021 to today for Belgium.
MODEL = "ecmwf_ifs"

# One point per Elia area: approximate centre of each province (latitude, longitude)
POINTS = {
    "Antwerp": (51.23, 4.72),
    "Brussels": (50.85, 4.35),
    "East-Flanders": (51.03, 3.80),
    "Flemish-Brabant": (50.87, 4.60),
    "Hainaut": (50.47, 3.95),
    "Limburg": (50.98, 5.45),
    "Liège": (50.52, 5.72),
    "Luxembourg": (49.95, 5.50),
    "Namur": (50.30, 4.85),
    "Walloon-Brabant": (50.67, 4.55),
    "West-Flanders": (51.00, 3.05),
}

VARIABLES = [   # Open-Meteo hourly variables. Column names in the parquet file are these names, unchanged
    "shortwave_radiation",        # global horizontal irradiance, W/m2
    "direct_radiation",           # direct, on a horizontal plane, W/m2
    "diffuse_radiation",          # W/m2
    "direct_normal_irradiance",   # W/m2
    "cloud_cover",                # total, %
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "temperature_2m",             # deg C
    "dew_point_2m",               # deg C
    "relative_humidity_2m",       # %
    "surface_pressure",           # hPa
    "precipitation",              # mm
    "wind_speed_10m",             # km/h
    "wind_gusts_10m",             # km/h
    "wind_direction_10m",         # degrees
]


def fetch(region, lat, lon, start, end):
    params = {
        "latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
        "hourly": ",".join(VARIABLES), "models": MODEL, "timezone": "UTC",
    }
    r = None
    for attempt in range(8):                 # retry on dropped connections and rate limits
        try:
            r = requests.get(URL, params=params, timeout=120)
            if r.status_code == 200:
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(5 * (attempt + 1))
    if r is None or r.status_code != 200:
        raise RuntimeError(f"could not download {region} {start} to {end}")
    js = r.json()
    df = pd.DataFrame(js["hourly"])                      # columns: time + the variables, as named by Open-Meteo
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df.insert(1, "region", region)                       # added: which Elia area this point belongs to
    df["latitude"], df["longitude"] = js["latitude"], js["longitude"]
    return df[["time", "region", "latitude", "longitude", *VARIABLES]]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2021-01-01")
    p.add_argument("--end", default="2026-10-25")
    p.add_argument("--out", default="weather_belgium.parquet")
    args = p.parse_args()

    years = range(int(args.start[:4]), int(args.end[:4]) + 1)
    frames = []
    for region, (lat, lon) in POINTS.items():
        for y in years:                      # one request per point per year keeps each call small
            s = max(args.start, f"{y}-01-01")
            e = min(args.end, f"{y}-12-31")
            frames.append(fetch(region, lat, lon, s, e))
            time.sleep(0.5)
        print(f"{region}: done")
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(args.out, index=False)
    print(f"wrote {args.out}: {len(df):,} rows, {df['time'].min()} to {df['time'].max()}")


if __name__ == "__main__":
    main()
