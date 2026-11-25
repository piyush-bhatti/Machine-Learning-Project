"""
Turn the TIGGE weather maps in tigge_grib/ into one table: weather_belgium_tigge.parquet.

Run this after download_weather_tigge.py. It needs no ECMWF account.

What it does
    Each downloaded file holds small weather maps of a box around Belgium: one map per forecast
    run, per lead time and per variable. For every area (the 10 provinces and Brussels), this
    script averages the map points that lie around the area's weather point, and writes the
    result as one row per area, per run and per lead time.

Why an average of several map points
    The archive stores the maps on a fine grid (about 10 km) in the early years and on a coarser
    one (about 25 km) later. Averaging every point within 0.25 degrees of the area's weather
    point (a square of roughly 55 km by 35 km) gives a comparable figure on both grids.

Nothing else is changed
    - Column names are the names used by the TIGGE download form, unchanged.
    - Units are the archive's own: temperatures in kelvin, pressure in pascal, cloud in percent.
    - Seven variables are RUNNING TOTALS counted from the start of the run, exactly as stored:
      sunshine_duration, surface_net_solar_radiation, surface_net_thermal_radiation,
      top_net_thermal_radiation, surface_latent_heat_flux, surface_sensible_heat_flux,
      total_precipitation. The amount for a 6-hour block is the value at one lead time minus the
      value at the lead time before it, within the same run. That step is left to the
      preparation notebook, where it is explained.

Columns of the output
    run             start of the forecast run (UTC). Always 00:00
    leadtime_hour   18, 24, 30, 36, 42 or 48: hours after the start of the run
    time            the moment the row describes (UTC) = run + leadtime_hour
    region          area name, as in the Elia file
    latitude, longitude    the area's weather point (the same points as download_weather.py)
    then the 19 weather variables

    The run of day D-1 is the one a trader has at 11:00 Belgian time on D-1. Its lead times
    24 to 48 cover delivery day D. Two runs describe some of the same moments, so always select
    rows by run, not only by time.

Usage
    python build_weather_tigge.py
    python build_weather_tigge.py --in-dir tigge_grib --out weather_belgium_tigge.parquet

Needs: pandas, pyarrow, numpy, eccodes  (pip install eccodes)
Source: TIGGE archive, ECMWF. TIGGE and ECMWF must be credited as the source.
"""
import argparse
from pathlib import Path

import eccodes
import numpy as np
import pandas as pd

from download_weather import POINTS          # one weather point per Elia area: (latitude, longitude)

HALF_WIDTH_DEG = 0.25                        # map points within this distance (in latitude and in longitude) are averaged

NAMES = {   # code used inside the files: name used by the TIGGE download form
    "10u": "10_m_u_component_of_wind",
    "10v": "10_m_v_component_of_wind",
    "2d": "2_m_dewpoint_temperature",
    "2t": "2_m_temperature",
    "cape": "convective_available_potential_energy",
    "mx2t6": "maximum_2_m_temperature_in_the_last_6_hours",
    "msl": "mean_sea_level_pressure",
    "mn2t6": "minimum_2_m_temperature_in_the_last_6_hours",
    "skt": "skin_temperature",
    "sund": "sunshine_duration",
    "sp": "surface_pressure",
    "tcc": "total_cloud_cover",
    "tcw": "total_column_water",
    "slhf": "surface_latent_heat_flux",
    "ssr": "surface_net_solar_radiation",
    "str": "surface_net_thermal_radiation",
    "sshf": "surface_sensible_heat_flux",
    "ttr": "top_net_thermal_radiation",
    "tp": "total_precipitation",
}
VARIABLES = list(NAMES.values())
LEADS = [18, 24, 30, 36, 42, 48]


def points_per_region(lats, lons):
    """For one map grid: which map points belong to each area."""
    out = {}
    for region, (lat, lon) in POINTS.items():
        inside = (np.abs(lats - lat) <= HALF_WIDTH_DEG) & (np.abs(lons - lon) <= HALF_WIDTH_DEG)
        if not inside.any():
            raise ValueError(f"no map point near {region}: the downloaded box does not cover it")
        out[region] = np.flatnonzero(inside)
    return out


def read_file(path, grids):
    """All maps of one file, as rows of (run, lead, variable, region, value)."""
    rows = []
    with open(path, "rb") as f:
        while True:
            g = eccodes.codes_grib_new_from_file(f)
            if g is None:
                break
            try:
                short = eccodes.codes_get(g, "shortName")
                if short not in NAMES:                       # for example convective inhibition in the test files
                    continue
                run = pd.Timestamp(f"{eccodes.codes_get(g, 'dataDate')} {eccodes.codes_get(g, 'dataTime'):04d}", tz="UTC")
                lead = int(eccodes.codes_get(g, "endStep"))
                values = eccodes.codes_get_array(g, "values")
                missing = eccodes.codes_get(g, "missingValue")
                values = np.where(values == missing, np.nan, values)

                # The grid is the same for many maps: work out the points of each area once per grid
                key = (eccodes.codes_get(g, "gridType"), len(values),
                       round(eccodes.codes_get(g, "latitudeOfFirstGridPointInDegrees"), 4),
                       round(eccodes.codes_get(g, "longitudeOfFirstGridPointInDegrees"), 4))
                if key not in grids:
                    lats = eccodes.codes_get_array(g, "latitudes")
                    lons = eccodes.codes_get_array(g, "longitudes")
                    lons = np.where(lons > 180, lons - 360, lons)
                    grids[key] = points_per_region(lats, lons)
                    sizes = sorted({len(i) for i in grids[key].values()})
                    print(f"  new map grid in {path.name}: {key[0]}, {key[1]} points, "
                          f"{sizes[0]} to {sizes[-1]} points averaged per area", flush=True)
                for region, idx in grids[key].items():
                    rows.append((run, lead, NAMES[short], region, np.nanmean(values[idx])))
            finally:
                eccodes.codes_release(g)
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in-dir", default="tigge_grib")
    p.add_argument("--out", default="weather_belgium_tigge.parquet")
    args = p.parse_args()

    files = sorted(Path(args.in_dir).glob("*.grib"))
    if not files:
        raise SystemExit(f"no .grib files in {args.in_dir}/: run download_weather_tigge.py first")
    print(f"{len(files)} files to read")

    grids, rows = {}, []
    for n, path in enumerate(files, 1):
        rows.extend(read_file(path, grids))
        if n % 10 == 0 or n == len(files):
            print(f"  {n} / {len(files)} files read", flush=True)

    long = pd.DataFrame(rows, columns=["run", "leadtime_hour", "variable", "region", "value"])
    long = long.drop_duplicates(["run", "leadtime_hour", "variable", "region"])          # a day held in two files counts once
    table = (long.pivot(index=["region", "run", "leadtime_hour"], columns="variable", values="value")
                 .reindex(columns=VARIABLES).reset_index())
    table.columns.name = None
    table["time"] = table["run"] + pd.to_timedelta(table["leadtime_hour"], unit="h")
    table["latitude"] = table["region"].map(lambda r: POINTS[r][0])
    table["longitude"] = table["region"].map(lambda r: POINTS[r][1])
    table = (table[["run", "leadtime_hour", "time", "region", "latitude", "longitude", *VARIABLES]]
             .sort_values(["region", "run", "leadtime_hour"]).reset_index(drop=True))
    table.to_parquet(args.out, index=False)

    # Report what is there and what is not
    runs = pd.DatetimeIndex(sorted(table["run"].unique()))
    expected = pd.date_range(runs.min(), runs.max(), freq="D")
    gaps = expected.difference(runs)
    full = table.groupby(["region", "run"]).size().eq(len(LEADS)).all()
    print(f"\nwrote {args.out}: {len(table):,} rows, {table['region'].nunique()} areas, {len(runs):,} runs")
    print(f"runs from {runs.min():%Y-%m-%d} to {runs.max():%Y-%m-%d}; days without a run in between: {len(gaps)}")
    if len(gaps):
        print("  first missing days:", ", ".join(d.strftime("%Y-%m-%d") for d in gaps[:10]))
    print(f"every run has all {len(LEADS)} lead times: {full}")
    print(f"missing values: {int(table[VARIABLES].isna().sum().sum())}")


if __name__ == "__main__":
    main()
