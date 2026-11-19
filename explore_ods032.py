"""
Explore and quality-check Elia dataset ods032
(Photovoltaic power production estimation and forecast on Belgian grid).

Usage:
    python explore_ods032.py ods032_2026.parquet
    python explore_ods032.py ods032_2026.parquet --out figures

Needs: pandas, pyarrow, matplotlib   (pip install pandas pyarrow matplotlib)

It prints a data-quality report to the terminal and saves six figures.
"""
import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------- style
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
BLUE_LIGHT = "#b7d3f6"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 10, "text.color": INK, "axes.labelcolor": INK2,
    "axes.edgecolor": AXIS, "xtick.color": MUTED, "ytick.color": MUTED,
    "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "lines.linewidth": 2, "legend.frameon": False,
})

FORECASTS = {            # column prefix -> label shown on charts
    "mostrecent": "Most recent (intraday)",
    "dayahead11h": "Day-ahead, 11:00",
    "dayahead": "Day-ahead, latest",
    "weekahead": "Week-ahead",
}
REGION_GROUPS = {        # aggregate -> the areas that should add up to it
    "Flanders": ["Antwerp", "East-Flanders", "Flemish-Brabant", "Limburg", "West-Flanders"],
    "Wallonia": ["Hainaut", "Liège", "Luxembourg", "Namur", "Walloon-Brabant"],
    "Belgium": ["Flanders", "Wallonia", "Brussels"],
}
AGGREGATES = list(REGION_GROUPS)


def load(path):
    df = pd.read_parquet(path)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True).dt.tz_convert("Europe/Brussels")
    df = df.sort_values(["region", "datetime"]).reset_index(drop=True)
    # load factor as a 0-1 fraction of monitored capacity, recomputed by us
    df["lf"] = df["measured"] / df["monitoredcapacity"]
    return df


def section(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# ---------------------------------------------------------------- checks
def quality_report(df):
    section("1. SHAPE AND COVERAGE")
    start, end = df["datetime"].min(), df["datetime"].max()
    print(f"Rows: {len(df):,}   Columns: {df.shape[1] - 1}   Regions: {df['region'].nunique()}")
    print(f"From {start}  to  {end}")
    expected = int((end - start) / pd.Timedelta("15min")) + 1
    per_region = df.groupby("region").size()
    print(f"Expected 15-min steps per region: {expected:,}")
    print(f"Actual steps per region: min {per_region.min():,}, max {per_region.max():,}")
    dups = df.duplicated(["region", "datetime"]).sum()
    print(f"Duplicate (region, datetime) rows: {dups}")
    gaps = 0
    for _, g in df.groupby("region"):
        gaps += (g["datetime"].diff().dropna() != pd.Timedelta("15min")).sum()
    print(f"Breaks in the 15-min sequence (all regions): {gaps}")

    section("2. MISSING AND IMPOSSIBLE VALUES")
    num = df.select_dtypes("number").columns.drop("lf")
    print(f"Missing values in any column: {int(df.isna().sum().sum())}")
    print(f"Negative values in any numeric column: {int((df[num] < 0).sum().sum())}")
    print(f"Measured above monitored capacity: {int((df['measured'] > df['monitoredcapacity']).sum())}")
    print(f"Highest load factor seen: {df['lf'].max():.1%}")
    night = df[df["datetime"].dt.hour.isin([0, 1, 2, 3])]
    print(f"Non-zero output between 00:00 and 04:00: {int((night['measured'] > 0).sum())} rows")
    lf_gap = (df["loadfactor"] / 100 - df["lf"]).abs().max()
    print(f"Largest gap between Elia's load factor and measured/capacity: {lf_gap:.4f}")

    section("3. DO THE REGIONS ADD UP?")
    wide = df.pivot(index="datetime", columns="region", values="measured")
    for total, parts in REGION_GROUPS.items():
        diff = (wide[parts].sum(axis=1) - wide[total]).abs()
        print(f"{total:9s} vs sum of parts: max gap {diff.max():8.3f} MW, "
              f"mean gap {diff.mean():.4f} MW")

    section("4. STUCK OR REPEATED VALUES (daylight only)")
    day = df[df["measured"] > 0].copy()
    same = day.groupby("region")["measured"].transform(lambda s: s.diff().eq(0))
    run = same.groupby((~same).cumsum()).cumsum()
    print(f"Longest run of an identical non-zero value: {int(run.max()) + 1} steps")
    print(f"Share of daylight steps equal to the previous step: {same.mean():.3%}")

    section("5. MONITORED CAPACITY")
    for region in ["Belgium", "Flanders", "Wallonia", "Brussels"]:
        g = df[df["region"] == region]
        changes = g.loc[g["monitoredcapacity"].diff().fillna(0) != 0, ["datetime", "monitoredcapacity"]]
        first, last = g["monitoredcapacity"].iloc[0], g["monitoredcapacity"].iloc[-1]
        when = ", ".join(d.strftime("%d %b") for d in changes["datetime"])
        print(f"{region:9s} {first:9.1f} -> {last:9.1f} MW ({last / first - 1:+.1%}), "
              f"{len(changes)} change(s): {when or 'none'}")

    section("6. ARE THE QUANTILES ORDERED?  (P10 <= forecast <= P90)")
    for pre, label in FORECASTS.items():
        f, lo, hi = df[f"{pre}forecast"], df[f"{pre}confidence10"], df[f"{pre}confidence90"]
        bad = ((lo > f + 1e-6) | (f > hi + 1e-6)).sum()
        print(f"{label:24s} violations: {int(bad):,} ({bad / len(df):.3%})")

    section("7. HOW GOOD ARE ELIA'S OWN FORECASTS?  (Belgium, daylight steps)")
    print(forecast_scores(df, "Belgium").round(2).to_string())
    print("\nnMAE and bias are in % of monitored capacity. For a well calibrated")
    print("P10-P90 band: 10% below, 80% inside, 10% above.")


def forecast_scores(df, region):
    g = df[(df["region"] == region)]
    g = g[(g["measured"] > 0) | (g["dayaheadforecast"] > 0)]
    cap = g["monitoredcapacity"]
    rows = {}
    for pre, label in FORECASTS.items():
        err = g[f"{pre}forecast"] - g["measured"]
        rows[label] = {
            "nMAE %": (err.abs() / cap).mean() * 100,
            "nRMSE %": np.sqrt(((err / cap) ** 2).mean()) * 100,
            "bias %": (err / cap).mean() * 100,
            "below P10 %": (g["measured"] < g[f"{pre}confidence10"]).mean() * 100,
            "inside %": ((g["measured"] >= g[f"{pre}confidence10"])
                         & (g["measured"] <= g[f"{pre}confidence90"])).mean() * 100,
            "above P90 %": (g["measured"] > g[f"{pre}confidence90"]).mean() * 100,
        }
    return pd.DataFrame(rows).T


# ---------------------------------------------------------------- figures
def save(fig, out, name):
    fig.savefig(out / name, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {out / name}")


def fig_daily(df, out):
    be = df[df["region"] == "Belgium"].set_index("datetime")
    daily = be["measured"].resample("D").sum() / 4 / 1000        # MW per 15 min -> GWh
    fig, ax = plt.subplots(figsize=(11, 3.8))
    ax.bar(daily.index, daily.values, width=0.8, color=BLUE, linewidth=0)
    ax.plot(daily.index, daily.rolling(14, center=True).mean(), color=INK, linewidth=1.5,
            label="14-day average")
    ax.legend(loc="upper left")
    ax.set_title("Daily solar generation, Belgium, 2026")
    ax.set_ylabel("GWh per day")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.grid(axis="x", visible=False)
    save(fig, out, "1_daily_generation.png")


def fig_heatmap(df, out):
    be = df[df["region"] == "Belgium"].copy()
    be["date"] = be["datetime"].dt.tz_convert("UTC").dt.date
    be["tod"] = be["datetime"].dt.tz_convert("UTC").dt.hour + be["datetime"].dt.tz_convert("UTC").dt.minute / 60
    grid = be.pivot_table(index="tod", columns="date", values="lf")
    fig, ax = plt.subplots(figsize=(11, 4.2))
    dates = mdates.date2num(pd.to_datetime(grid.columns))
    im = ax.imshow(grid.values * 100, aspect="auto", origin="lower", cmap="Blues",
                   extent=[dates[0], dates[-1] + 1, 0, 24], vmin=0)
    ax.set_ylim(2, 21)
    ax.set_yticks(range(3, 22, 3))
    ax.set_title("Load factor by day and time of day, Belgium, 2026")
    ax.set_ylabel("Hour of day (UTC)")
    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, pad=0.01)
    cb.set_label("% of monitored capacity")
    cb.outline.set_visible(False)
    save(fig, out, "2_load_factor_heatmap.png")


def fig_weeks(df, out):
    be = df[df["region"] == "Belgium"].set_index("datetime")
    daily = be["lf"].resample("D").mean()
    weekly_std = daily.rolling(7).std()
    weekly_mean = daily.rolling(7).mean()
    summer = (daily.index.month >= 5) & (daily.index.month <= 8)
    picks = {
        "A settled week (low day-to-day variation)": weekly_std[summer].idxmin(),
        "A changeable week (high day-to-day variation)": weekly_std[summer].idxmax(),
        "A winter week": weekly_mean[daily.index.month <= 2].dropna().idxmin(),
    }
    fig, axes = plt.subplots(len(picks), 1, figsize=(11, 8.4), sharey=True)
    for ax, (title, end) in zip(axes, picks.items()):
        w = be.loc[end - pd.Timedelta(days=6): end + pd.Timedelta(days=1)]
        ax.fill_between(w.index, w["dayahead11hconfidence10"], w["dayahead11hconfidence90"],
                        color=BLUE_LIGHT, linewidth=0, label="Day-ahead P10 to P90")
        ax.plot(w.index, w["dayahead11hforecast"], color=BLUE, label="Day-ahead forecast (11:00)")
        ax.plot(w.index, w["measured"], color=INK, linewidth=1.5, label="Measured")
        ax.set_title(title, fontsize=10.5)
        ax.set_ylabel("MW")
        ax.xaxis.set_major_locator(mdates.DayLocator(tz=w.index.tz))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d %b", tz=w.index.tz))
        ax.grid(axis="x", visible=False)
    axes[0].legend(loc="upper center", bbox_to_anchor=(0.5, 1.45), ncol=3)
    fig.suptitle("Measured output against Elia's day-ahead forecast, Belgium",
                 x=0.07, ha="left", fontweight="bold", fontsize=12, y=1.0)
    fig.tight_layout()
    save(fig, out, "3_sample_weeks.png")


def fig_forecast_error(df, out):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [1, 1.5]})
    scores = forecast_scores(df, "Belgium")["nMAE %"].iloc[::-1]
    ax1.barh(scores.index, scores.values, color=BLUE, height=0.55)
    for y, v in enumerate(scores.values):
        ax1.text(v + 0.05, y, f"{v:.2f}", va="center", color=INK, fontsize=9)
    ax1.set_title("Error grows with lead time", fontsize=10.5)
    ax1.set_xlabel("Mean absolute error, % of capacity (Belgium, daylight)")
    ax1.grid(axis="y", visible=False)
    ax1.set_xlim(0, scores.max() * 1.2)

    regions = [r for r in sorted(df["region"].unique()) if r not in AGGREGATES]
    by_region = pd.Series({r: forecast_scores(df, r).loc["Day-ahead, 11:00", "nMAE %"]
                           for r in regions + ["Belgium"]}).sort_values()
    colors = [INK2 if r == "Belgium" else BLUE for r in by_region.index]
    ax2.barh(by_region.index, by_region.values, color=colors, height=0.6)
    for y, v in enumerate(by_region.values):
        ax2.text(v + 0.05, y, f"{v:.2f}", va="center", color=INK, fontsize=9)
    ax2.set_title("Small areas are harder than the national total", fontsize=10.5)
    ax2.set_xlabel("Day-ahead (11:00) mean absolute error, % of capacity")
    ax2.grid(axis="y", visible=False)
    ax2.set_xlim(0, by_region.max() * 1.15)
    fig.suptitle("Accuracy of Elia's own forecasts, 2026", x=0.02, ha="left",
                 fontweight="bold", fontsize=12)
    fig.tight_layout()
    save(fig, out, "4_forecast_error.png")


def fig_calibration(df, out):
    s = forecast_scores(df, "Belgium")[["below P10 %", "inside %", "above P90 %"]]
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    y = np.arange(len(s))[::-1]
    left = np.zeros(len(s))
    for col, color, label in zip(s.columns, [ORANGE, BLUE, AQUA],
                                 ["Below P10", "Inside the band", "Above P90"]):
        ax.barh(y, s[col], left=left, color=color, height=0.55, edgecolor=SURFACE,
                linewidth=2, label=label)
        for yi, (l, v) in zip(y, zip(left, s[col])):
            if v > 4:
                ax.text(l + v / 2, yi, f"{v:.0f}%", ha="center", va="center", color="white", fontsize=9)
        left += s[col].values
    for x in (10, 90):
        ax.axvline(x, color=INK, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(10, len(s) - 0.42, "ideal 10%", ha="center", fontsize=8.5, color=INK2)
    ax.text(90, len(s) - 0.42, "ideal 90%", ha="center", fontsize=8.5, color=INK2)
    ax.set_yticks(y, s.index)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of daylight steps (Belgium)")
    ax.set_title("Where measured output falls relative to Elia's P10 to P90 band", pad=22)
    ax.grid(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.25), ncol=3)
    save(fig, out, "5_quantile_calibration.png")


def fig_scatter(df, out):
    be = df[(df["region"] == "Belgium") & (df["measured"] > 0)]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), sharex=True, sharey=True)
    top = max(be["measured"].max(), be["dayahead11hforecast"].max()) * 1.03
    for ax, pre in zip(axes, ["dayahead11h", "mostrecent"]):
        ax.scatter(be[f"{pre}forecast"], be["measured"], s=3, color=BLUE, alpha=0.12, linewidths=0)
        ax.plot([0, top], [0, top], color=INK, linewidth=1)
        ax.set_title(FORECASTS[pre], fontsize=10.5)
        ax.set_xlabel("Forecast, MW")
        ax.set_xlim(0, top), ax.set_ylim(0, top)
        ax.set_aspect("equal")
    axes[0].set_ylabel("Measured, MW")
    axes[0].text(top * 0.60, top * 0.66, "perfect forecast", rotation=45, color=INK2,
                 fontsize=8.5, ha="center", va="center")
    fig.suptitle("Forecast against outcome, Belgium, daylight steps", x=0.06, ha="left",
                 fontweight="bold", fontsize=12)
    fig.tight_layout()
    save(fig, out, "6_forecast_vs_measured.png")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("parquet", help="path to the ods032 parquet file")
    p.add_argument("--out", default=None, help="folder for figures (default: 'figures' next to the data)")
    args = p.parse_args()

    out = Path(args.out) if args.out else Path(args.parquet).resolve().parent / "figures"
    out.mkdir(parents=True, exist_ok=True)

    df = load(args.parquet)
    quality_report(df)
    section("FIGURES")
    for fig in (fig_daily, fig_heatmap, fig_weeks, fig_forecast_error, fig_calibration, fig_scatter):
        fig(df, out)


if __name__ == "__main__":
    main()
