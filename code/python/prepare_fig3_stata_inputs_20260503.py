from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pyreadstat


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "outputs" / "figures" / "fig3_stata_work"
OUT = WORK / "output"

SRC_GEO = ROOT / "result" / "round10_submission_assets_20260428" / "geo_work_alt"
SRC_REGISTRY = ROOT / "data" / "admin_rollout" / "CLDS_sample_registry_with_admin_rollout.dta"


def copy_shape(src_stem: str, dst_stem: str) -> None:
    for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
        src = SRC_GEO / f"{src_stem}{ext}"
        if src.exists():
            shutil.copy2(src, WORK / f"{dst_stem}{ext}")


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    copy_shape("county", "china_county")
    copy_shape("city", "china_city")
    copy_shape("province", "china_province")

    df, _ = pyreadstat.read_dta(str(SRC_REGISTRY), apply_value_formats=False)
    df = df[df["__cid_id"].notna()].copy()
    df["county_code"] = (
        df["__cid_id"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    )
    county = (
        df.groupby("county_code", as_index=False)
        .agg(completed_yr=("admin_rollout_complete_year", "first"))
        .sort_values("county_code")
    )
    county["completed_yr"] = pd.to_numeric(county["completed_yr"], errors="coerce")
    county.loc[
        (county["completed_yr"] < 2014) | (county["completed_yr"] > 2018),
        "completed_yr",
    ] = pd.NA
    county["in_analytic"] = 1
    county["sample_tag"] = pd.NA
    county = county[["county_code", "completed_yr", "in_analytic", "sample_tag"]]
    pyreadstat.write_dta(county, str(WORK / "county_treatment.dta"))

    summary = county.assign(
        cat=pd.cut(
            county["completed_yr"],
            bins=[2013, 2016, 2018],
            labels=["2014-2016", "2017-2018"],
        )
    )
    counts = {
        "analytic_counties": int(len(county)),
        "not_completed_by_2018": int(county["completed_yr"].isna().sum()),
        "completed_2017_2018": int(county["completed_yr"].between(2017, 2018).sum()),
        "completed_2014_2016": int(county["completed_yr"].between(2014, 2016).sum()),
    }
    (WORK / "county_treatment_counts.txt").write_text(
        "\n".join(f"{k}: {v}" for k, v in counts.items()) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
