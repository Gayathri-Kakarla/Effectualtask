from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import requests
import tomllib


BASE_URL = "https://api.worldbank.org/v2"

session = requests.Session()
session.headers.update({"User-Agent": "worldbank-macro-project/1.0"})


def load_config(filename: str = "config.toml") -> dict:
    """
    Load the TOML configuration file from the same folder as this script.
    This avoids path problems when the script is run from another directory.
    """
    config_path = Path(__file__).resolve().parent / filename
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def fetch_paginated_json(url: str, params: dict | None = None) -> list:
    """
    Fetch all pages from a World Bank API endpoint and combine the rows.
    The API returns metadata in the first list item and the actual data in the second.
    """
    params = dict(params or {})
    params.setdefault("format", "json")
    params.setdefault("per_page", 20000)

    page = 1
    all_rows = []

    while True:
        params["page"] = page
        response = session.get(url, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, list) or len(payload) < 2:
            break

        metadata, rows = payload[0], payload[1] or []
        all_rows.extend(rows)

        total_pages = int(metadata.get("pages", 1))
        if page >= total_pages:
            break

        page += 1

    return all_rows


def get_country_mapping() -> pd.DataFrame:
    """
    Download the country list from the World Bank API and keep only real countries,
    excluding aggregates such as 'World' or region totals.
    """
    rows = fetch_paginated_json(f"{BASE_URL}/country")
    countries = pd.DataFrame(rows)

    keep_cols = ["id", "iso2Code", "name", "region", "incomeLevel"]
    keep_cols = [col for col in keep_cols if col in countries.columns]
    countries = countries[keep_cols].copy()

    countries["region_name"] = countries["region"].apply(
        lambda x: x.get("value") if isinstance(x, dict) else None
    )

    countries = countries[
        countries["region_name"].notna() & (countries["region_name"] != "Aggregates")
    ].copy()

    countries["name_norm"] = countries["name"].str.casefold()

    return countries[["id", "iso2Code", "name", "name_norm"]].drop_duplicates()


def map_countries(country_names: List[str], country_df: pd.DataFrame) -> Dict[str, str]:
    """
    Map country names from the config file to World Bank ISO-3 country codes.
    A few aliases are added for names that may not match perfectly.
    """
    name_to_code = dict(zip(country_df["name_norm"], country_df["id"]))

    aliases = {
        "united states": "USA",
        "united kingdom": "GBR",
        "turkey": "TUR",
    }

    mapped = {}

    for name in country_names:
        normalized_name = name.casefold()
        code = name_to_code.get(normalized_name) or aliases.get(normalized_name)

        if not code:
            possible_matches = country_df[
                country_df["name_norm"].str.contains(normalized_name, regex=False)
            ]
            if len(possible_matches) == 1:
                code = possible_matches.iloc[0]["id"]

        if not code:
            raise ValueError(f"Could not map country name: {name}")

        mapped[name] = code

    return mapped


def extract_country_code(df: pd.DataFrame) -> pd.Series:
    """
    The indicator endpoint returns both ISO-2 and ISO-3 style fields.
    We want ISO-3 because that matches the country codes used in our mapping.
    """
    if "countryiso3code" in df.columns:
        return df["countryiso3code"]

    return df["country"].apply(
        lambda x: x.get("id") if isinstance(x, dict) else None
    )


def fetch_indicator_data(
    country_codes: List[str],
    indicator_id: str,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """
    Fetch one indicator for multiple countries and return it in long format:
    country_code, year, value
    """
    joined_codes = ";".join(country_codes)
    url = f"{BASE_URL}/country/{joined_codes}/indicator/{indicator_id}"

    rows = fetch_paginated_json(
        url,
        params={"date": f"{start_year}:{end_year}"}
    )

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["country_code", "year", "value"])

    result = pd.DataFrame(
        {
            "country_code": extract_country_code(df),
            "year": pd.to_numeric(df["date"], errors="coerce").astype("Int64"),
            "value": pd.to_numeric(df["value"], errors="coerce"),
        }
    )

    result = result[
        result["year"].between(start_year, end_year, inclusive="both")
    ].copy()

    return result


def build_main_dataset(config: dict) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Build the main wide-format dataset required in the assignment:
    one row per country and indicator, with one column per year.
    """
    country_names = config["countries"]["list"]
    series = config["series"]
    start_year = int(config["time"]["start_year"])
    end_year = int(config["time"]["end_year"])

    country_df = get_country_mapping()
    country_map = map_countries(country_names, country_df)
    reverse_country_map = {code: name for name, code in country_map.items()}

    final_rows = []
    full_years = list(range(start_year, end_year + 1))

    for indicator_key, indicator_id in series.items():
        long_df = fetch_indicator_data(
            country_codes=list(country_map.values()),
            indicator_id=indicator_id,
            start_year=start_year,
            end_year=end_year,
        )

        if long_df.empty:
            wide_df = pd.DataFrame(index=list(country_map.values()))
        else:
            wide_df = long_df.pivot_table(
                index="country_code",
                columns="year",
                values="value",
                aggfunc="first",
            )

        # Reindex so every configured country and year always appears in the output.
        wide_df = wide_df.reindex(index=list(country_map.values()), columns=full_years)
        wide_df.index.name = "country_code"
        wide_df = wide_df.reset_index()

        wide_df.insert(0, "country", wide_df["country_code"].map(reverse_country_map))
        wide_df.insert(1, "indicator", indicator_key)
        wide_df = wide_df.drop(columns="country_code")

        wide_df.columns = [
            f"year_{col}" if isinstance(col, int) else col
            for col in wide_df.columns
        ]

        final_rows.append(wide_df)

    main_dataset = pd.concat(final_rows, ignore_index=True)
    return main_dataset, country_map


def cagr(start_value: float, end_value: float, periods: int) -> float:
    """
    Compute compound annual growth rate.
    Return NaN if the inputs are missing or invalid.
    """
    if periods <= 0:
        return np.nan

    if pd.isna(start_value) or pd.isna(end_value):
        return np.nan

    if start_value <= 0 or end_value <= 0:
        return np.nan

    return (end_value / start_value) ** (1 / periods) - 1


def build_summary(main_df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Build the compact summary table requested in the assignment.
    It includes value-added shares and CAGR measures for each country.
    """
    start_year = int(config["time"]["start_year"])
    end_year = int(config["time"]["end_year"])
    periods = end_year - start_year

    year_columns = [col for col in main_df.columns if col.startswith("year_")]

    long_df = main_df.melt(
        id_vars=["country", "indicator"],
        value_vars=year_columns,
        var_name="year",
        value_name="value",
    )

    long_df["year"] = long_df["year"].str.replace("year_", "", regex=False).astype(int)

    wide_df = long_df.pivot_table(
        index=["country", "year"],
        columns="indicator",
        values="value",
        aggfunc="first",
    ).reset_index()

    required_cols = [
        "industry_value_added_usd_const",
        "manufacturing_value_added_usd_const",
        "gdp_usd_real",
    ]

    for col in required_cols:
        if col not in wide_df.columns:
            wide_df[col] = np.nan

    wide_df["industry_share"] = (
        wide_df["industry_value_added_usd_const"] / wide_df["gdp_usd_real"]
    )
    wide_df["manufacturing_share"] = (
        wide_df["manufacturing_value_added_usd_const"] / wide_df["gdp_usd_real"]
    )

    summary_rows = []

    for country, group in wide_df.groupby("country"):
        group = group.sort_values("year")

        start_row = group[group["year"] == start_year]
        end_row = group[group["year"] == end_year]

        summary_rows.append(
            {
                "country": country,
                "industry_share_2000": start_row["industry_share"].iloc[0] if not start_row.empty else np.nan,
                "industry_share_2025": end_row["industry_share"].iloc[0] if not end_row.empty else np.nan,
                "manufacturing_share_2000": start_row["manufacturing_share"].iloc[0] if not start_row.empty else np.nan,
                "manufacturing_share_2025": end_row["manufacturing_share"].iloc[0] if not end_row.empty else np.nan,
                "industry_cagr": cagr(
                    start_row["industry_value_added_usd_const"].iloc[0] if not start_row.empty else np.nan,
                    end_row["industry_value_added_usd_const"].iloc[0] if not end_row.empty else np.nan,
                    periods,
                ),
                "manufacturing_cagr": cagr(
                    start_row["manufacturing_value_added_usd_const"].iloc[0] if not start_row.empty else np.nan,
                    end_row["manufacturing_value_added_usd_const"].iloc[0] if not end_row.empty else np.nan,
                    periods,
                ),
                "gdp_cagr": cagr(
                    start_row["gdp_usd_real"].iloc[0] if not start_row.empty else np.nan,
                    end_row["gdp_usd_real"].iloc[0] if not end_row.empty else np.nan,
                    periods,
                ),
            }
        )

    summary_df = pd.DataFrame(summary_rows)

    if summary_df.empty:
        return pd.DataFrame(
            columns=[
                "country",
                "industry_share_2000",
                "industry_share_2025",
                "manufacturing_share_2000",
                "manufacturing_share_2025",
                "industry_cagr",
                "manufacturing_cagr",
                "gdp_cagr",
            ]
        )

    return summary_df.sort_values("country").reset_index(drop=True)


def main() -> None:
    config = load_config()

    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(exist_ok=True)

    main_df, country_map = build_main_dataset(config)
    summary_df = build_summary(main_df, config)

    main_df.to_csv(output_dir / "worldbank_main_dataset.csv", index=False)
    summary_df.to_csv(output_dir / "worldbank_structural_change_summary.csv", index=False)

    mapping_df = pd.DataFrame(
        {
            "country": list(country_map.keys()),
            "country_code": list(country_map.values()),
        }
    )
    mapping_df.to_csv(output_dir / "country_mapping.csv", index=False)


if __name__ == "__main__":
    main()