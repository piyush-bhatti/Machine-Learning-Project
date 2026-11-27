# Day-ahead solar generation forecast for Belgium

Group project for Introduction to Machine Learning, MSc in Financial Engineering, EDHEC (2026-2027).

**Product.** A day-ahead forecast of solar generation per Belgian province, built from weather forecasts, for a power trading desk or renewable aggregator. It supports the decision of how much volume to sell in the day-ahead market, where forecast errors become imbalance costs.

**Working area: Antwerp.** The team is currently working on the province of Antwerp only. Every notebook has a `PROVINCE = "Antwerp"` setting near the top and runs its analysis on that area. The Elia file and the older weather file hold all eleven areas. The day-ahead weather file and `model_table.parquet` hold Antwerp only for now: to work on another area, download its day-ahead weather first (`python download_weather_dayahead.py --regions all`) and rerun `01_prepare_data.ipynb`.

**Benchmarks.** A persistence forecast (same hour two days before delivery, the last day fully observed when the forecast is made at 11:00) and the grid operator's own day-ahead forecast (Elia).

**Team.** Charles Perret, Hemangini Jena, Kshitij Kochar, Piyush Bhatti, Sharmistha Mookerjee.

**New to the project?** `PROJECT_CONTEXT.md` explains the business side in plain language: the client, how power is sold, and what the forecast is worth.

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
| 2 | `python download_weather_dayahead.py` | Downloads day-ahead weather forecasts (see the note below the table). Antwerp by default. Optional: the file is already in the repository | `weather_belgium_dayahead.parquet` |
| | `python download_weather.py` | Downloads the older weather file for the 11 areas. Only needed for the comparison in `explore_weather_dayahead.ipynb`. Optional: the file is already in the repository | `weather_belgium.parquet` |
| 3 | `explore_elia.ipynb` | Quality checks and first look at the Elia data for Antwerp, and the accuracy of Elia's own forecasts | in the notebook |
| 4 | `explore_weather_dayahead.ipynb` | Visual exploration and quality checks of the day-ahead weather file for Antwerp, and a comparison with the older weather file | in the notebook |
| | `explore_weather.ipynb` | The same exploration for the older weather file, kept for reference | in the notebook |
| 5 | `01_prepare_data.ipynb` | Cleans Elia and the day-ahead weather, joins them, builds the target, flags daylight and the train/test split. Keeps every area in the weather file | `model_table.parquet` |
| | `explore_model_table.ipynb` | Explores the table built in step 5: the target, how the weather forecast relates to output, the benchmark scores on the training period, and training against test. Optional | in the notebook |
| 6 | `02_features.ipynb` | Adds the engineered inputs for the working area: sun position, clear-sky irradiance, clear-sky index, calendar and wind direction cycles | `features_table.parquet`, `features.json` |
| 7 | `03_models.ipynb` | Scores the two benchmarks, then tunes and scores a random forest, on time-ordered validation folds inside the training period. The test period is not opened | `model_settings.json`, `cv_predictions.parquet` |
| 8 | `04_evaluation.ipynb` | Opens the test period once: trains the forest with the settings from step 7 on the whole training period, scores it and the two benchmarks on the test year, and converts the errors into mis-sold MWh. Also checks monthly retraining, separately | `test_predictions.parquet`, `test_scores.json`, `report/figures/test_*.png` |

**Two weather files.** `weather_belgium.parquet` is close to the weather that actually happened, because it is built from the first few hours of every forecast. A trader deciding at 11:00 for the next day does not have that. `weather_belgium_dayahead.parquet` holds the forecast as it stood the morning before, which is what the trader really sees, but it only exists from March 2024. The model is therefore trained and tested on the day-ahead file: `01_prepare_data.ipynb` builds `model_table.parquet` from it. The older file is kept only to measure how much accuracy is lost a day ahead.

Steps 3 and 4 are exploration and can be skipped when rerunning. Step 5 is the start of the modelling pipeline: every later notebook reads `model_table.parquet` (also in the repository), not the raw files.

`analyse_solar_weather.ipynb` is an earlier exploratory analysis of weather against output for Antwerp. It uses the older weather file, so its numbers no longer describe the model table: `explore_model_table.ipynb` replaces it. It is kept for reference.

Further models will be added here as they are built. `04_evaluation.ipynb` must stay the last step: nothing may be tuned after it has been run.

## Data

| File | Source | Content | In the repository? |
|---|---|---|---|
| `ods032.parquet` | [Elia Open Data, dataset ods032](https://opendata.elia.be/explore/dataset/ods032/information/) | Solar generation, Elia's forecasts and monitored capacity. Quarter-hourly, 14 areas, to 25 October 2026 | No (too large). Run step 1 |
| `weather_belgium.parquet` | [Open-Meteo Historical Forecast API](https://open-meteo.com/en/docs/historical-forecast-api), ECMWF IFS HRES model (9 km) | 16 weather variables, hourly, 11 areas, January 2021 to 25 October 2026 | Yes |
| `weather_belgium_dayahead.parquet` | [Open-Meteo Single Runs API](https://open-meteo.com/en/docs/single-runs-api), ECMWF IFS HRES model (9 km) | The same 16 weather variables, as forecast at midnight UTC the day before delivery. Hourly, Antwerp only, 15 March 2024 to 25 October 2026 | Yes |
| `model_table.parquet` | Built by `01_prepare_data.ipynb` | One row per area per hour from 15 March 2024, Antwerp only for now: target, 18 raw features (weather as forecast the day before), Elia benchmark, daylight and split flags | Yes |

**Column names are the source names, unchanged.** Elia columns are named as in the Elia download (`datetime`, `region`, `measured`, `monitoredcapacity`, `dayahead11hforecast`, ...). Weather columns are named as in the Open-Meteo API (`time`, `shortwave_radiation`, `cloud_cover`, `temperature_2m`, ...). The weather file adds `region`, `latitude` and `longitude` to say which point each row belongs to. `model_table.parquet` adds three columns: `lf`, `is_daylight` and `split`.

The target is the load factor `lf`: `measured` divided by `monitoredcapacity`. The sample starts on 15 March 2024, the first day covered by the day-ahead weather forecasts. The `split` column currently marks the last twelve months (from 26 October 2025) as test and everything before as train. This cut is a placeholder until the team agrees on one.

Weather data by Open-Meteo.com, licensed under CC BY 4.0.

## Known data issues

- **Elia, March 2022:** in Brussels, `measured` exceeds `monitoredcapacity` on 21 to 24 March 2022, because output was rescaled four days before the capacity figure was updated. Antwerp never exceeds its capacity.
- **Elia, small gaps:** the 23:45 reading is missing on every day from mid November 2022 to mid October 2024. All are night values, kept as zero.
- **Elia, capacity corrections:** `monitoredcapacity` moves in small monthly steps with a few large corrections (for Antwerp: 25 March 2022, 1 February 2023, 1 November 2023, 23 May 2024, and a reversal on 20 June 2024). `measured` is scaled up to this capacity, so it steps on the same dates. The load factor stays consistent, except for a few days around a correction when the two are updated on different dates (Antwerp: 21 to 24 March 2022, and probably 23 to 25 May 2024).
- **Weather, one model:** the weather file is requested from a single named model, ECMWF IFS HRES (9 km), set as `MODEL` in `download_weather.py`. Without a named model, Open-Meteo returns its "best match", which for Belgium switched from ECMWF to the Dutch KNMI model on 26 June 2024. That switch changed the level of wind speed and the character of the cloud layers, and produced corrupted humidity values on 26 to 28 June 2024. Do not download weather by hand from the website without selecting the same model.
- **Older weather file is a short-range forecast.** `weather_belgium.parquet` comes from an Open-Meteo archive that stitches together the first hours of each model run, so it is more accurate than what was known the day before delivery. For that reason it is no longer used for modelling. `weather_belgium_dayahead.parquet` replaces it.
- **Day-ahead weather, short history:** day-ahead forecasts are archived from 14 March 2024 only, so the sample is about two and a half years and each season appears two or three times.
- **Day-ahead weather, one older forecast:** for delivery day 24 June 2026 the forecast of the morning before is incomplete in the archive, so the download script uses the forecast of one day earlier. It prints a note when it does this.
- **Day-ahead weather, model upgrade:** ECMWF moved to a new version of its forecasting system on 12 May 2026, inside the current test period. Section 8 of `explore_weather_dayahead.ipynb` compares the same months across years.

## Working together

- Run `git pull` before starting, and push small commits often.
- Avoid two people editing the same notebook at the same time. Put shared functions in `.py` files.
- Never commit the Elia parquet files. `.gitignore` already excludes them.
