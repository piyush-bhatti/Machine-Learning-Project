# Project context: who needs this forecast and why

This file explains the business side of the project in plain language. It is the background for the sales presentation and for section 1 of the report ("The product"). No machine learning knowledge is needed to read it.

For how to run the code, see `README.md`.

## 1. The product in one sentence

A forecast, made the morning before, of how much solar power each Belgian province will produce in every hour of the next day, so that a power trader knows how much to sell.

## 2. The client

Solar panels produce whatever the sun gives. Someone has to sell that power. The client is whoever carries that job:

- an energy company that owns solar farms,
- an aggregator, who sells on behalf of many small owners,
- a trading desk (at a utility, a trading firm or a bank) that buys and sells power.

In the market's vocabulary these are "balance responsible parties": each one must make sure that what it sold matches what it actually delivers.

## 3. How the client sells power

Electricity cannot be stored cheaply, so it is sold separately for each small slice of time.

| Step | When | What happens |
|---|---|---|
| Day-ahead auction | Closes at 12:00 the day before delivery | One auction for all of tomorrow. The trader offers a volume for each slice of the day |
| Intraday market | After the auction, until 5 minutes before delivery | The trader can still buy or sell to correct the position as better forecasts arrive |
| Imbalance | At delivery | Any gap left between what was sold and what was produced is covered by the grid operator, Elia, who charges for it |

Until September 2025 the slices of the day-ahead auction were one hour each. Since 30 September 2025 they are 15 minutes each, so Belgium has 96 day-ahead prices per day.

## 4. The client's problem

At noon the trader must commit to tomorrow's volumes, but tomorrow's sunshine is uncertain.

- Sell **too much**: the panels deliver less than promised. The trader must buy the missing power later, usually at a worse price.
- Sell **too little**: the extra power is sold late, usually at a worse price as well.

Either way, a forecast error costs money. The larger the solar portfolio, the larger the bill. Solar capacity is growing fast: in Antwerp alone, monitored capacity went from about 770 MW in 2021 to about 2,030 MW in 2026. The problem grows with it.

## 5. What the product does

It reads the weather forecast for tomorrow (sunlight, cloud, temperature, wind and others) and turns it into an expected solar output for each hour, per province.

It is ready at 11:00, one hour before the auction closes, and it only uses information available at that time.

## 6. What it replaces

We compare the product with two alternatives the client could use today:

| Alternative | What it is | Role |
|---|---|---|
| Naive rule | "Tomorrow will look like the last day we observed" | The simple rule a client without a model would use |
| Elia's day-ahead forecast | The grid operator's own forecast, published for free at 11:00 | The professional standard, and the one to beat |

## 7. The value, in orders of magnitude

Forecast error is measured in percent of installed capacity. A simple way to make it concrete:

- Take a client with a **100 MW** solar portfolio.
- One percentage point of average error is **1 MW** mis-sold in every daylight hour.
- There are roughly 4,500 daylight hours in a year, so one point is about **4,500 MWh per year** sold at the wrong time.

The error of each forecast (the naive rule, Elia's forecast and our model) will be added here once the models have been scored on the test period. Early numbers from the exploratory notebook are not shown, because they were measured with weather data that was more accurate than what a trader really has the day before.

**Still to compute:** the cost in euros. This needs the price paid for each MWh of error, which can be taken from Elia's published imbalance prices.

## 8. What we can and cannot promise

- The forecast is hourly. The market now trades in 15 minute slices.
- It covers day-ahead decisions only, not intraday corrections.
- It forecasts volume, not prices.
- True day-before weather forecasts are only available from March 2024, so the model learns from about two and a half years of history.
- It is built on free public data. Elia has access to data we do not have, so matching Elia would already be a strong result.
- The team is currently working on Antwerp only. The other provinces come later.

## 9. Short glossary

| Term | Meaning |
|---|---|
| Elia | The company that runs Belgium's high-voltage grid and keeps supply and demand in balance |
| Day-ahead market | The daily auction where power for tomorrow is bought and sold |
| Intraday market | The market that stays open after the auction, for last corrections |
| Imbalance | The gap between what a trader sold and what was actually delivered |
| Installed (monitored) capacity | The maximum power the panels could produce, in MW |
| Load factor | Actual output divided by installed capacity. 0 is nothing, 1 is full power. This is what the model predicts |
| MW and MWh | MW is power at one moment. MWh is energy: 1 MW produced for one hour |
| Benchmark | The simpler forecast we compare ours against |

## Sources

- EPEX SPOT, day-ahead and intraday market rules: https://epexspot.com/de/node/177
- Elia, move of the day-ahead market to 15 minutes (30 September 2025): https://www.eliagroup.eu/press/2025/09/20251001_press-release-sdac
- EPEX SPOT, 15 minute products on the day-ahead market: https://www.epexspot.com/en/news/15-minute-products-live-epex-spot-day-ahead-markets
- Project figures: `01_prepare_data.ipynb` and `analyse_solar_weather.ipynb`
