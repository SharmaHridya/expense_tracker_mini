"""Expense Analyzer

Cleans a messy personal-expense CSV, summarises where the money goes,
flags 
budget overruns and saves a chart.

Usage:
    python expense_analyzer.py sample_expenses.csv --out output
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # render to file, no display needed
import matplotlib.pyplot as plt
import pandas as pd

# Monthly budget per category (in rupees). Edit these to suit yourself.
BUDGETS = {
    "Food": 4500,
    "Transport": 700,
    "Shopping": 2000,
    "Entertainment": 600,
    "Education": 800,
    "Bills": 500,
}

# Each category keeps the same colour in every chart (fixed order, validated palette).
CATEGORY_COLORS = {
    "Food": "#2a78d6",
    "Transport": "#eb6834",
    "Shopping": "#1baf7a",
    "Entertainment": "#eda100",
    "Education": "#e87ba4",
    "Bills": "#008300",
    "Uncategorized": "#898781",
}

INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"


def load_and_clean(path: Path) -> tuple[pd.DataFrame, dict]:
    """Read the CSV and fix the usual mess. Returns (clean_df, cleaning_log)."""
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip().str.lower()
    log = {"rows read": len(df)}

    # Parse types; bad values become NaT/NaN and are dropped
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    before = len(df)
    df = df.dropna(subset=["date", "amount"])
    log["invalid rows dropped"] = before - len(df)

    # Normalise text columns ("education" and "Education" are the same category)
    df["category"] = df["category"].fillna("").str.strip().str.title()
    log["missing categories"] = int((df["category"] == "").sum())
    df["category"] = df["category"].replace("", "Uncategorized")
    df["payment_mode"] = df["payment_mode"].str.strip().str.upper()
    df["description"] = df["description"].str.strip()

    # Same day + item + amount twice is most likely a double entry
    before = len(df)
    df = df.drop_duplicates()
    log["duplicates dropped"] = before - len(df)

    # Negative amounts are refunds: kept, so they reduce net spend
    log["refunds kept"] = int((df["amount"] < 0).sum())

    df["month"] = df["date"].dt.to_period("M") #dt._to_period("M") is used to convert the date to a monthly period, which is then used to group the data by month
    return df.sort_values("date").reset_index(drop=True), log


def budget_overruns(df: pd.DataFrame) -> pd.DataFrame:
    """Month/category combinations where spending went past the budget."""
    spend = df.groupby(["month", "category"], as_index=False)["amount"].sum()
    spend["budget"] = spend["category"].map(BUDGETS)
    spend["over_by"] = spend["amount"] - spend["budget"]
    return spend[spend["over_by"] > 0].sort_values("over_by", ascending=False)


def category_by_month(df: pd.DataFrame) -> pd.DataFrame:
    """Rows = categories, columns = months."""
    table = df.pivot_table(
        index="category", columns="month", values="amount", aggfunc="sum", fill_value=0
    )
    order = [c for c in CATEGORY_COLORS if c in table.index]
    return table.loc[order]


def style_axes(ax):
    """Quiet chart chrome: light grid, no top/right spines."""
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_SECONDARY, length=0)
    ax.title.set_color(INK)


def make_chart(table: pd.DataFrame, out_file: Path):
    months = [str(m.strftime("%b %Y")) for m in table.columns]
    totals = table.sum(axis=1).sort_values()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2), facecolor=SURFACE)

    # Left: monthly spend, stacked by category
    bottom = pd.Series(0.0, index=table.columns)
    for category, row in table.iterrows():
        ax1.bar(
            months, row.values, bottom=bottom.values, label=category,
            color=CATEGORY_COLORS[category], width=0.5,
            edgecolor=SURFACE, linewidth=2,  # surface-coloured gap between segments
        )
        bottom += row
    ax1.set_title("Monthly spend by category", loc="left", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Amount (INR)", color=INK_SECONDARY)
    ax1.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax1.set_axisbelow(True)
    ax1.legend(
        frameon=False, fontsize=9, labelcolor=INK_SECONDARY, ncol=4,
        loc="upper center", bbox_to_anchor=(0.5, -0.08),  # below the plot, clear of the bars
    )
    style_axes(ax1)

    # Right: total per category, one hue, value labelled at the bar end
    ax2.barh(totals.index, totals.values, color="#2a78d6", height=0.55)
    for y, value in enumerate(totals.values):
        ax2.text(value + totals.max() * 0.015, y, f"{value:,.0f}",
                 va="center", fontsize=9, color=INK_SECONDARY)
    ax2.set_title("Total spend by category", loc="left", fontsize=12, fontweight="bold")
    ax2.set_xlim(0, totals.max() * 1.15)
    ax2.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax2.set_axisbelow(True)
    style_axes(ax2)

    fig.tight_layout()
    fig.savefig(out_file, dpi=150, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Analyse a personal expense CSV.")
    parser.add_argument("csv", type=Path, help="path to the expenses CSV")
    parser.add_argument("--out", type=Path, default=Path("output"), help="output folder")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    df, log = load_and_clean(args.csv)
    total = df["amount"].sum()
    days = (df["date"].max() - df["date"].min()).days + 1

    print("== Cleaning ==")
    for key, value in log.items():
        print(f"{key:<22}{value}")

    print("\n== Overview ==")
    print(f"Net spend            {total:,.0f}")
    print(f"Average per day      {total / days:,.0f}  (over {days} days)")

    print("\n== Monthly total ==")
    monthly = df.groupby("month")["amount"].sum()
    monthly.index = monthly.index.astype(str)
    print(monthly.to_string())

    table = category_by_month(df)
    shown = table.copy()
    shown.columns = shown.columns.astype(str)
    print("\n== Category x month ==")
    print(shown.to_string())

    print("\n== Payment mode share (%) ==")
    share = df.groupby("payment_mode")["amount"].sum().sort_values(ascending=False)
    print((share / total * 100).round(1).to_string())

    print("\n== Top 5 expenses ==")
    top = df.nlargest(5, "amount").assign(date=lambda d: d["date"].dt.strftime("%d %b"))
    print(top[["date", "description", "category", "amount"]].to_string(index=False))

    print("\n== Budget overruns ==")
    over = budget_overruns(df)
    if over.empty:
        print("None - all categories within budget.")
    else:
        over = over.assign(month=over["month"].astype(str))
        print(over.to_string(index=False))

    # Save outputs
    df.assign(month=df["month"].astype(str)).to_csv(args.out / "cleaned_expenses.csv", index=False)
    shown.to_csv(args.out / "category_by_month.csv")
    make_chart(table, args.out / "spending_report.png")
    print(f"\nSaved cleaned data, summary and chart to {args.out}/")


if __name__ == "__main__":
    main()
