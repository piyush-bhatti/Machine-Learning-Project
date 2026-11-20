# Day-ahead solar generation forecast for Belgium

Group project for Introduction to Machine Learning, MSc in Financial Engineering, EDHEC (2026-2027).

**Product.** A day-ahead forecast of solar generation per Belgian province, built from weather forecasts, for a power trading desk or renewable aggregator. It supports the decision of how much volume to sell in the day-ahead market, where forecast errors become imbalance costs.

**Working area: Antwerp.** The team is currently working on the province of Antwerp only. Every notebook has a `PROVINCE = "Antwerp"` setting near the top and runs its analysis on that area. The data files keep all eleven areas, so switching area means changing that one line.

**Benchmarks.** A persistence forecast (same hour yesterday) and the grid operator's own day-ahead forecast (Elia).

**Team.** Charles Perret, Hemangini Jena, Kshitij Kochar, Piyush Bhatti, Sharmistha Mookerjee.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Order of execution

| Step | Command or file | What it does | Output |
|---|---|---|---|
| 1 | `python download_elia.py` | Downloads the Elia solar data (about 150 MB) | `ods032.parquet` |
| 2 | `python download_weather.py` | Downloads hourly weather for the 11 areas. Optional: the file is already in the repository | `weather_belgium.parquet` |
| 3 | `explore_elia.ipynb` | Quality checks and first look at the Elia data for Antwerp, and the accuracy of Elia's own forecasts | in the notebook |
| 4 | `explore_weather.ipynb` | Visual exploration and quality checks of the weather data for Antwerp | in the notebook |
| 5 | `01_prepare_data.ipynb` | Cleans both sources, joins them, builds the target, flags daylight and the train/test split. Keeps all areas | `model_table.parquet` |

Steps 3 and 4 are exploration and can be skipped when rerunning. Step 5 is the start of the modelling pipeline: every later notebook reads `model_table.parquet` (also in the repository), not the raw files.

`analyse_solar_weather.ipynb` is an earlier exploratory analysis of weather against output for Antwerp, kept for reference.

Modelling notebooks (`02_...`, `03_...`) will be added here as they are built.

## Data

| File | Source | Content | In the repository? |
|---|---|---|---|
| `ods032.parquet` | [Elia Open Data, dataset ods032](https://opendata.elia.be/explore/dataset/ods032/information/) | Solar generation, Elia's forecasts and monitored capacity. Quarter-hourly, 14 areas, to 25 October 2026 | No (too large). Run step 1 |
| `weather_belgium.parquet` | [Open-Meteo Historical Forecast API](https://open-meteo.com/en/docs/historical-forecast-api) | 16 weather variables, hourly, 11 areas, January 2021 to 25 October 2026 | Yes |
| `model_table.parquet` | Built by `01_prepare_data.ipynb` | One row per area per hour from January 2023: target, 18 raw features, Elia benchmark, daylight and split flags | Yes |

**Column names are the source names, unchanged.** Elia columns are named as in the Elia download (`datetime`, `region`, `measured`, `monitoredcapacity`, `dayahead11hforecast`, ...). Weather columns are named as in the Open-Meteo API (`time`, `shortwave_radiation`, `cloud_cover`, `temperature_2m`, ...). The weather file adds `region`, `latitude` and `longitude` to say which point each row belongs to. `model_table.parquet` adds three columns: `lf`, `is_daylight` and `split`.

The target is the load factor `lf`: `measured` divided by `monitoredcapacity`. The sample starts in January 2023. Rows before 2025 are for training and tuning, and rows from 2025 are the test set.

Weather data by Open-Meteo.com, licensed under CC BY 4.0.

## Known data issues

- **Elia, March 2022:** in Brussels, `measured` exceeds `monitoredcapacity` on 21 to 24 March 2022, because output was rescaled four days before the capacity figure was updated. Antwerp never exceeds its capacity.
- **Elia, small gaps:** the 23:45 reading is missing on every day from January 2023 to mid October 2024. All are night values, kept as zero.
- **Elia, capacity corrections:** `monitoredcapacity` moves in small monthly steps with a few large corrections (for Antwerp: 25 March 2022, 1 February 2023, 1 November 2023, 23 May 2024, and a reversal on 20 June 2024). `measured` is scaled up to this capacity, so it steps on the same dates. The load factor stays consistent, except for a few days around a correction when the two are updated on different dates (Antwerp: 21 to 24 March 2022, and probably 23 to 25 May 2024).
- **Weather, 26 to 28 June 2024:** relative humidity and dew point are corrupted in all areas and must be set to missing.
- **Weather, from mid 2024:** wind speed, wind gusts and mid-level cloud cover shift to a lower level, which points to a change in the source weather model. Global irradiance is unaffected.
- **Weather is a short-range forecast.** The Open-Meteo archive stitches together the first hours of each model run, so it is more accurate than what was known the day before delivery.

## Working together

- Run `git pull` before starting, and push small commits often.
- Avoid two people editing the same notebook at the same time. Put shared functions in `.py` files.
- Never commit the Elia parquet files. `.gitignore` already excludes them.
