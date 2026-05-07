from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyhdfe
import pyreadstat
import statsmodels.api as sm
from linearmodels.iv import IV2SLS
from scipy import stats

import round6_iv_deep_reassessment_20260430 as r6


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "result" / "round7_iv_extended_search_20260430"
TABLES = OUT / "tables"
AUDIT = OUT / "audit"

PANEL = ROOT / "data" / "topjournal_rebuild" / "clds" / "CLDS_hh_mechanism_panel_with_indivbridge_20260416.dta"
ADMIN = ROOT / "data" / "topjournal_rebuild" / "admin" / "admin_rollout_countyyear_v2.dta"

OUTCOMES = ["any_rentin", "asinh_rentin"]
BALANCE_OUTCOMES = [
    ("any_rentin", "Any rent-in (2014)"),
    ("asinh_rentin", "asinh rented-in area (2014)"),
    ("a3_tenure_insec_z", "Baseline insecurity index"),
    ("ib_nonfarm_curr_n", "Current nonfarm workers"),
    ("land_total_mu", "Household land base"),
    ("asinh_rb_inc_farm", "asinh farm income (2014)"),
]


@dataclass(frozen=True)
class ExtIVSpec:
    name: str
    base_vars: tuple[str, ...]
    component_vars: tuple[str, ...] = ()
    note: str = ""


SPECS = [
    ExtIVSpec("survey_cost_only", ("z_survey_cost",), note="static county survey-cost index"),
    ExtIVSpec("terrain_only", ("z_rugged",), note="terrain ruggedness"),
    ExtIVSpec("distance_only", ("z_dist_capital",), note="distance to provincial capital"),
    ExtIVSpec("workload_only", ("z_workload",), note="administrative workload index"),
    ExtIVSpec("offlate_x_survey_cost", ("iv_offlate_x_survey_cost",), ("official_late_z", "z_survey_cost"), "official schedule x survey cost"),
    ExtIVSpec("offlate_x_rugged", ("iv_offlate_x_rugged",), ("official_late_z", "z_rugged"), "official schedule x ruggedness"),
    ExtIVSpec("offlate_x_distance", ("iv_offlate_x_distance",), ("official_late_z", "z_dist_capital"), "official schedule x distance"),
    ExtIVSpec("offlate_x_workload", ("iv_offlate_x_workload",), ("official_late_z", "z_workload"), "official schedule x workload"),
    ExtIVSpec("offlate_x_area", ("iv_offlate_x_area",), ("official_late_z", "z_log_area"), "official schedule x county area"),
    ExtIVSpec("offlate_x_villages", ("iv_offlate_x_villages",), ("official_late_z", "z_log_villages"), "official schedule x village count"),
    ExtIVSpec("offlate_x_low_capacity", ("iv_offlate_x_low_capacity",), ("official_late_z", "z_low_capacity"), "official schedule x low capacity"),
    ExtIVSpec(
        "offlate_x_cost_lowcap",
        ("iv_offlate_x_survey_cost", "iv_offlate_x_low_capacity"),
        ("official_late_z", "z_survey_cost", "z_low_capacity"),
        "official schedule x survey cost and low capacity",
    ),
    ExtIVSpec("off2016_x_survey_cost", ("iv_off2016_x_survey_cost",), ("official_2016plus", "z_survey_cost"), "official 2016+ x survey cost"),
]


CAPITAL_CITY_CODE = {
    11: 110000,
    12: 120000,
    13: 130100,
    14: 140100,
    15: 150100,
    21: 210100,
    22: 220100,
    23: 230100,
    31: 310000,
    32: 320100,
    33: 330100,
    34: 340100,
    35: 350100,
    36: 360100,
    37: 370100,
    41: 410100,
    42: 420100,
    43: 430100,
    44: 440100,
    45: 450100,
    46: 460100,
    50: 500000,
    51: 510100,
    52: 520100,
    53: 530100,
    54: 540100,
    61: 610100,
    62: 620100,
    63: 630100,
    64: 640100,
    65: 650100,
}


def ensure_dirs() -> None:
    for p in [OUT, TABLES, AUDIT]:
        p.mkdir(parents=True, exist_ok=True)


def data_root() -> Path:
    desktop = Path.home() / "Desktop"
    return next(p for p in desktop.iterdir() if p.is_dir() and p.name.startswith("\u6570\u636e"))


def pref_code_from_county(code: pd.Series) -> pd.Series:
    c = pd.to_numeric(code, errors="coerce")
    prov = np.floor(c / 10000)
    pref = np.floor(c / 100) * 100
    # Municipalities use 110000/120000/310000/500000 as the city code.
    pref = np.where(np.isin(prov, [11, 12, 31, 50]), prov * 10000, pref)
    return pd.Series(pref, index=code.index).astype("Int64")


def haversine_km(lon1: pd.Series, lat1: pd.Series, lon2: pd.Series, lat2: pd.Series) -> pd.Series:
    lon1 = np.radians(pd.to_numeric(lon1, errors="coerce"))
    lat1 = np.radians(pd.to_numeric(lat1, errors="coerce"))
    lon2 = np.radians(pd.to_numeric(lon2, errors="coerce"))
    lat2 = np.radians(pd.to_numeric(lat2, errors="coerce"))
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def find_external_files() -> dict[str, Path]:
    root = data_root()
    files = {"root": root}
    xlsx = [p for p in root.rglob("*.xlsx") if p.is_file()]
    files["terrain_county"] = next(p for p in xlsx if p.stat().st_size == 204484)
    files["terrain_city"] = next(p for p in xlsx if p.stat().st_size == 38848)
    files["county_db_interp"] = next(p for p in root.iterdir() if p.is_file() and p.stat().st_size == 20105144)
    return files


def standardize(s: pd.Series, sample: pd.Series | None = None) -> pd.Series:
    ref = s if sample is None else s.loc[sample]
    m = ref.mean(skipna=True)
    sd = ref.std(skipna=True)
    if not sd or not np.isfinite(sd):
        return pd.Series(np.nan, index=s.index)
    return (s - m) / sd


def load_external_covariates(sample_counties: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    files = find_external_files()

    tc_raw = pd.read_excel(files["terrain_county"], sheet_name=0)
    terrain_county = pd.DataFrame(
        {
            "county_id": pd.to_numeric(tc_raw.iloc[:, 0], errors="coerce"),
            "county_name_ext": tc_raw.iloc[:, 2],
            "province_name_ext": tc_raw.iloc[:, 3],
            "lon": pd.to_numeric(tc_raw.iloc[:, 5], errors="coerce"),
            "lat": pd.to_numeric(tc_raw.iloc[:, 6], errors="coerce"),
            "rugged": pd.to_numeric(tc_raw.iloc[:, 7], errors="coerce"),
        }
    ).dropna(subset=["county_id"])
    terrain_county["county_id"] = terrain_county["county_id"].astype(int)
    terrain_county["prov_id"] = np.floor(terrain_county["county_id"] / 10000).astype(int)
    terrain_county["pref_code"] = pref_code_from_county(terrain_county["county_id"])

    tcity_raw = pd.read_excel(files["terrain_city"], sheet_name=0)
    terrain_city = pd.DataFrame(
        {
            "pref_code": pd.to_numeric(tcity_raw.iloc[:, 0], errors="coerce"),
            "city_name_ext": tcity_raw.iloc[:, 2],
            "province_name_ext": tcity_raw.iloc[:, 3],
            "city_lon": pd.to_numeric(tcity_raw.iloc[:, 5], errors="coerce"),
            "city_lat": pd.to_numeric(tcity_raw.iloc[:, 6], errors="coerce"),
            "city_rugged": pd.to_numeric(tcity_raw.iloc[:, 7], errors="coerce"),
        }
    ).dropna(subset=["pref_code"])
    terrain_city["pref_code"] = terrain_city["pref_code"].astype(int)
    terrain_city["prov_id"] = np.floor(terrain_city["pref_code"] / 10000).astype(int)

    cap = terrain_city[terrain_city["pref_code"].isin(CAPITAL_CITY_CODE.values())][
        ["pref_code", "city_lon", "city_lat"]
    ].rename(columns={"pref_code": "capital_code", "city_lon": "capital_lon", "city_lat": "capital_lat"})
    cap["prov_id"] = cap["capital_code"].map({v: k for k, v in CAPITAL_CITY_CODE.items()})
    terrain_county = terrain_county.merge(cap[["prov_id", "capital_lon", "capital_lat"]], on="prov_id", how="left")
    terrain_county["dist_capital_km"] = haversine_km(
        terrain_county["lon"], terrain_county["lat"], terrain_county["capital_lon"], terrain_county["capital_lat"]
    )
    terrain_city = terrain_city.merge(cap[["prov_id", "capital_lon", "capital_lat"]], on="prov_id", how="left")
    terrain_city["dist_capital_km"] = haversine_km(
        terrain_city["city_lon"], terrain_city["city_lat"], terrain_city["capital_lon"], terrain_city["capital_lat"]
    )

    db = pd.read_excel(files["county_db_interp"], sheet_name=0, usecols=list(range(80)))
    db13 = db[db.iloc[:, 0].eq(2013)].copy()
    cov = pd.DataFrame(
        {
            "county_id": pd.to_numeric(db13.iloc[:, 4], errors="coerce"),
            "area_km2": pd.to_numeric(db13.iloc[:, 5], errors="coerce"),
            "townships": pd.to_numeric(db13.iloc[:, 6], errors="coerce"),
            "villages": pd.to_numeric(db13.iloc[:, 10], errors="coerce"),
            "rural_pop_10k": pd.to_numeric(db13.iloc[:, 14], errors="coerce"),
            "ag_workers": pd.to_numeric(db13.iloc[:, 19], errors="coerce"),
            "ag_mach_power": pd.to_numeric(db13.iloc[:, 22], errors="coerce"),
            "broadband": pd.to_numeric(db13.iloc[:, 25], errors="coerce"),
            "gdp_10k": pd.to_numeric(db13.iloc[:, 26], errors="coerce"),
            "primary_gdp_10k": pd.to_numeric(db13.iloc[:, 27], errors="coerce"),
            "gdp_pc": pd.to_numeric(db13.iloc[:, 33], errors="coerce"),
            "fiscal_rev_10k": pd.to_numeric(db13.iloc[:, 37], errors="coerce"),
            "crop_area_kha": pd.to_numeric(db13.iloc[:, 44], errors="coerce"),
            "arable_land_ha": pd.to_numeric(db13.iloc[:, 45], errors="coerce"),
        }
    ).dropna(subset=["county_id"])
    cov["county_id"] = cov["county_id"].astype(int)
    cov["prov_id"] = np.floor(cov["county_id"] / 10000).astype(int)
    cov["pref_code"] = pref_code_from_county(cov["county_id"])

    direct = terrain_county.merge(cov.drop(columns=["prov_id", "pref_code"]), on="county_id", how="outer")
    direct["prov_id"] = np.floor(direct["county_id"] / 10000).astype(int)
    direct["pref_code"] = pref_code_from_county(direct["county_id"])

    numeric_cols = [
        "rugged",
        "lon",
        "lat",
        "dist_capital_km",
        "area_km2",
        "townships",
        "villages",
        "rural_pop_10k",
        "ag_workers",
        "ag_mach_power",
        "broadband",
        "gdp_10k",
        "primary_gdp_10k",
        "gdp_pc",
        "fiscal_rev_10k",
        "crop_area_kha",
        "arable_land_ha",
    ]
    pref = direct.groupby("pref_code", dropna=True)[numeric_cols].mean(numeric_only=True).reset_index()
    pref["prov_id"] = np.floor(pref["pref_code"] / 10000).astype(int)
    pref = pref.merge(
        terrain_city[["pref_code", "city_rugged", "city_lon", "city_lat", "dist_capital_km"]].rename(
            columns={
                "city_rugged": "pref_city_rugged",
                "city_lon": "pref_city_lon",
                "city_lat": "pref_city_lat",
                "dist_capital_km": "pref_dist_capital_km",
            }
        ),
        on="pref_code",
        how="outer",
    )
    pref["rugged"] = pref["rugged"].combine_first(pref["pref_city_rugged"])
    pref["lon"] = pref["lon"].combine_first(pref["pref_city_lon"])
    pref["lat"] = pref["lat"].combine_first(pref["pref_city_lat"])
    pref["dist_capital_km"] = pref["dist_capital_km"].combine_first(pref["pref_dist_capital_km"])
    pref = pref[["pref_code", "prov_id"] + numeric_cols]

    prov = direct.groupby("prov_id", dropna=True)[numeric_cols].mean(numeric_only=True).reset_index()

    sample = pd.DataFrame({"county_id": pd.to_numeric(sample_counties, errors="coerce").dropna().astype(int).unique()})
    sample["prov_id"] = np.floor(sample["county_id"] / 10000).astype(int)
    sample["pref_code"] = pref_code_from_county(sample["county_id"])
    out = sample.merge(direct[["county_id"] + numeric_cols], on="county_id", how="left", suffixes=("", "_direct"))
    out["match_level"] = np.where(out["rugged"].notna() | out["area_km2"].notna(), "county", "")
    out = out.merge(pref.add_suffix("_pref"), left_on="pref_code", right_on="pref_code_pref", how="left")
    out = out.merge(prov.add_suffix("_prov"), left_on="prov_id", right_on="prov_id_prov", how="left")

    for col in numeric_cols:
        out[col] = out[col].combine_first(out.get(f"{col}_pref")).combine_first(out.get(f"{col}_prov"))
    out.loc[out["match_level"].eq("") & (out["rugged_pref"].notna() | out["area_km2_pref"].notna()), "match_level"] = "prefecture"
    out.loc[out["match_level"].eq("") & (out["rugged_prov"].notna() | out["area_km2_prov"].notna()), "match_level"] = "province"
    out.loc[out["match_level"].eq(""), "match_level"] = "unmatched"

    # Construct interpretable cost/capacity measures.
    out["log_area"] = np.log1p(out["area_km2"])
    out["log_townships"] = np.log1p(out["townships"])
    out["log_villages"] = np.log1p(out["villages"])
    out["log_rural_pop"] = np.log1p(out["rural_pop_10k"])
    out["log_gdp_pc"] = np.log1p(out["gdp_pc"])
    out["log_fiscal_pc"] = np.log1p(out["fiscal_rev_10k"] / out["rural_pop_10k"])
    out["log_broadband_pc"] = np.log1p(out["broadband"] / out["rural_pop_10k"])

    sample_mask = out["county_id"].isin(sample["county_id"])
    for col in [
        "rugged",
        "dist_capital_km",
        "log_area",
        "log_townships",
        "log_villages",
        "log_rural_pop",
        "log_gdp_pc",
        "log_fiscal_pc",
        "log_broadband_pc",
    ]:
        out[f"z_{col.replace('_km', '').replace('dist_capital', 'dist_capital')}"] = standardize(out[col], sample_mask)

    out["z_survey_cost"] = pd.concat(
        [out["z_rugged"], out["z_dist_capital"], out["z_log_area"]], axis=1
    ).mean(axis=1, skipna=True)
    out["z_workload"] = pd.concat(
        [out["z_log_townships"], out["z_log_villages"], out["z_log_rural_pop"]], axis=1
    ).mean(axis=1, skipna=True)
    out["z_low_capacity"] = pd.concat(
        [-out["z_log_gdp_pc"], -out["z_log_fiscal_pc"], -out["z_log_broadband_pc"]], axis=1
    ).mean(axis=1, skipna=True)
    out["z_cost_workload"] = pd.concat([out["z_survey_cost"], out["z_workload"]], axis=1).mean(axis=1, skipna=True)

    keep = [
        "county_id",
        "prov_id",
        "pref_code",
        "match_level",
        "rugged",
        "dist_capital_km",
        "area_km2",
        "townships",
        "villages",
        "rural_pop_10k",
        "gdp_pc",
        "fiscal_rev_10k",
        "broadband",
        "z_rugged",
        "z_dist_capital",
        "z_log_area",
        "z_log_townships",
        "z_log_villages",
        "z_survey_cost",
        "z_workload",
        "z_low_capacity",
        "z_cost_workload",
    ]
    audit = pd.DataFrame(
        [
            {"file_role": role, "path": str(path)}
            for role, path in files.items()
            if role != "root"
        ]
    )
    return out[keep], audit


def read_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    panel, _ = pyreadstat.read_dta(str(PANEL))
    admin, _ = pyreadstat.read_dta(str(ADMIN))
    if "__cid_id" not in panel.columns and "county_id_num" in panel.columns:
        panel = panel.rename(columns={"county_id_num": "__cid_id"})
    if "__prov_id" not in panel.columns:
        panel["__prov_id"] = np.floor(pd.to_numeric(panel["__cid_id"], errors="coerce") / 10000)
    admin = admin.rename(columns={"county_id_num": "__cid_id", "prov_id": "__prov_id"})
    return panel, admin


def admin_threshold_base(admin: pd.DataFrame) -> pd.DataFrame:
    keep = [
        "__cid_id",
        "__prov_id",
        "year",
        "county_signedoff_t",
        "county_issued_t",
        "county_completed_t",
        "county_sat_t",
    ]
    out = admin[[c for c in keep if c in admin.columns]].drop_duplicates().copy()
    out = r6.add_thresholds(out)
    return out


def make_stack(panel: pd.DataFrame, admin_thr: pd.DataFrame, ext: pd.DataFrame, scope: str, anchor: str) -> pd.DataFrame:
    df = panel.loc[panel["year"].isin([2014, 2016, 2018])].copy()
    df = df.loc[df["s_mech_hh"].eq(1)].copy()
    if scope == "adjacent":
        df = df.loc[df["timing_adjacent_hh"].eq(1)].copy()
    df["__cid_id"] = pd.to_numeric(df["__cid_id"], errors="coerce").astype("Int64")
    if "__prov_id" not in df.columns:
        df["__prov_id"] = np.floor(pd.to_numeric(df["__cid_id"], errors="coerce") / 10000)
    thr_cols = [
        "__cid_id",
        "year",
        "county_signedoff_t",
        "county_issued_t",
        "county_completed_t",
        "county_sat_t",
        "signoff_or_issue_t",
        "completed_t",
        "high_sat80_t",
        "sat_cont",
    ]
    df = df.merge(admin_thr[[c for c in thr_cols if c in admin_thr.columns]], on=["__cid_id", "year"], how="left")
    df = df.merge(ext.rename(columns={"county_id": "__cid_id"}), on="__cid_id", how="left", suffixes=("", "_ext"))
    df = r6.add_official_schedule(df)
    df = r6.add_baseline_vars(df)
    df["instab_high"] = np.where(df["a3_high_insec"].isin([0, 1]), df["a3_high_insec"], np.nan)
    df["region"] = df["__prov_id"].map(r6.region_code)

    for x in ["survey_cost", "rugged", "dist_capital", "workload", "log_area", "log_villages", "low_capacity"]:
        zname = f"z_{x}"
        if zname in df.columns:
            df[f"iv_offlate_x_{x}"] = df["official_late_z"] * df[zname]
            df[f"iv_off2016_x_{x}"] = df["official_2016plus"] * df[zname]

    first = df.loc[df[anchor].eq(1)].groupby("__cid_id")["year"].min()
    df["first_thr"] = df["__cid_id"].map(first)
    df["never_thr"] = df["first_thr"].isna()
    df = df.loc[df["never_thr"] | df["first_thr"].isin([2016, 2018])].copy()

    w16 = df.loc[
        df["year"].isin([2014, 2016]) & (df["first_thr"].eq(2016) | df["first_thr"].eq(2018) | df["never_thr"])
    ].copy()
    w16["treated"] = w16["first_thr"].eq(2016).astype(float)
    w16["post"] = w16["year"].eq(2016).astype(float)
    w16["winflag"] = 0

    w18 = df.loc[df["year"].isin([2016, 2018]) & (df["first_thr"].eq(2018) | df["never_thr"])].copy()
    w18["treated"] = w18["first_thr"].eq(2018).astype(float)
    w18["post"] = w18["year"].eq(2018).astype(float)
    w18["winflag"] = 1

    stack = pd.concat([w16, w18], ignore_index=True, sort=False)
    stack["D"] = stack["treated"] * stack["post"]
    stack["DM"] = stack["D"] * stack["instab_high"]
    stack["PM"] = stack["post"] * stack["instab_high"]
    stack["hid_stack"] = stack["hid"] + 10_000_000 * stack["winflag"]
    stack["year_stack"] = stack["year"] + 10_000 * stack["winflag"]
    stack["prov_year_stack"] = stack["__prov_id"].astype("Int64").astype(str) + "_" + stack["year_stack"].astype("Int64").astype(str)
    return stack


def add_post_terms(stack: pd.DataFrame, names: list[str], prefix: str) -> list[str]:
    cols: list[str] = []
    for name in names:
        if name not in stack.columns:
            continue
        col = f"{prefix}_{name}"
        col_m = f"{col}_M"
        stack[col] = stack["post"] * pd.to_numeric(stack[name], errors="coerce")
        stack[col_m] = stack[col] * stack["instab_high"]
        cols.extend([col, col_m])
    return cols


def control_cols(stack: pd.DataFrame, variant: str) -> list[str]:
    if variant == "none":
        return []
    mapping = {
        "farm_income": ["z_base_asinh_farm_income"],
        "baseline_bundle": ["z_base_asinh_farm_income", "z_base_land", "z_base_farmdep", "z_base_nonfarm_curr"],
    }
    cols: list[str] = []
    for base in mapping.get(variant, []):
        if base not in stack.columns:
            continue
        col = f"post_{base}"
        col_m = f"{col}_M"
        stack[col] = stack["post"] * stack[base]
        stack[col_m] = stack[col] * stack["instab_high"]
        cols.extend([col, col_m])
    return cols


def residualize(data: pd.DataFrame, cols: list[str], fe_cols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    ids = data[fe_cols].astype("category").apply(lambda s: s.cat.codes).to_numpy()
    alg = pyhdfe.create(ids, drop_singletons=True)
    keep = np.ones(len(data), dtype=bool)
    if alg.singleton_indices is not None:
        keep = ~alg.singleton_indices
    resid = alg.residualize(data[cols].astype(float).to_numpy())
    return pd.DataFrame(resid, columns=cols, index=data.index[keep]), data.loc[keep].copy()


def scalar_f(model, param: str) -> float:
    if param not in model.params:
        return np.nan
    var = float(model.cov.loc[param, param])
    beta = float(model.params[param])
    return (beta * beta) / var if var > 0 else np.nan


def run_iv(
    stack_in: pd.DataFrame,
    spec: ExtIVSpec,
    outcome: str,
    controls: str,
    fe_variant: str,
    component_controls: bool,
) -> dict:
    stack = stack_in.copy()
    zcols = add_post_terms(stack, list(spec.base_vars), "Z")
    ccols = control_cols(stack, controls)
    if component_controls and spec.component_vars:
        ccols += add_post_terms(stack, list(spec.component_vars), "C")

    fe_cols = ["hid_stack", "prov_year_stack"] if fe_variant == "provyear" else ["hid_stack", "year_stack"]
    cols = [outcome, "PM", "D", "DM", "__cid_id", "hid_stack", "year_stack", "prov_year_stack"] + zcols + ccols
    data = stack[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(data) < 100 or data["__cid_id"].nunique() < 10:
        raise ValueError("too few observations")
    if data[zcols].var().min() < 1e-12:
        raise ValueError("zero-variance instruments before FE")

    res, kept = residualize(data, [outcome, "PM", "D", "DM"] + zcols + ccols, fe_cols)
    clusters = kept["__cid_id"].astype(int)
    if len(kept) < 100 or clusters.nunique() < 10:
        raise ValueError("too few observations after FE")
    if res[zcols].var().min() < 1e-12:
        raise ValueError("zero-variance instruments after FE")

    exog_cols = ["PM"] + ccols
    ols = IV2SLS(res[outcome], res[exog_cols + ["D", "DM"]], None, None).fit(cov_type="clustered", clusters=clusters)
    iv = IV2SLS(res[outcome], res[exog_cols], res[["D", "DM"]], res[zcols]).fit(cov_type="clustered", clusters=clusters)
    fs = IV2SLS(res["D"], pd.concat([res[exog_cols], res[zcols]], axis=1), None, None).fit(cov_type="clustered", clusters=clusters)
    diag = iv.first_stage.diagnostics

    return {
        "spec": spec.name,
        "outcome": outcome,
        "controls": controls,
        "fe": fe_variant,
        "component_controls": int(component_controls),
        "N": int(len(kept)),
        "clusters": int(clusters.nunique()),
        "zcols": ",".join(zcols),
        "exog_extra": ",".join(ccols),
        "ols_diff_b": float(ols.params["DM"]),
        "ols_diff_se": float(ols.std_errors["DM"]),
        "ols_diff_p": float(ols.pvalues["DM"]),
        "iv_diff_b": float(iv.params["DM"]),
        "iv_diff_se": float(iv.std_errors["DM"]),
        "iv_diff_p": float(iv.pvalues["DM"]),
        "iv_low_b": float(iv.params["D"]),
        "iv_low_se": float(iv.std_errors["D"]),
        "iv_low_p": float(iv.pvalues["D"]),
        "weak_D_f": float(diag.loc["D", "f.stat"]) if "D" in diag.index else np.nan,
        "weak_DM_f": float(diag.loc["DM", "f.stat"]) if "DM" in diag.index else np.nan,
        "fs_D_Z1_b": float(fs.params[zcols[0]]) if zcols and zcols[0] in fs.params else np.nan,
        "fs_D_Z1_F": scalar_f(fs, zcols[0]) if zcols else np.nan,
        "sargan_p": float(iv.sargan.pval) if hasattr(iv, "sargan") else np.nan,
        "status": "ok",
    }


def balance_frame(panel: pd.DataFrame, ext: pd.DataFrame) -> pd.DataFrame:
    base = panel.loc[panel["year"].eq(2014) & panel["s_mech_hh"].eq(1)].copy()
    base = base.sort_values(["hid", "year"]).drop_duplicates("hid")
    base["__cid_id"] = pd.to_numeric(base["__cid_id"], errors="coerce").astype("Int64")
    base = base.merge(ext.rename(columns={"county_id": "__cid_id"}), on="__cid_id", how="left")
    base = r6.add_official_schedule(r6.add_baseline_vars(base))
    base["region"] = base["__prov_id"].map(r6.region_code)
    for x in ["survey_cost", "rugged", "dist_capital", "workload", "log_area", "log_villages", "low_capacity"]:
        zname = f"z_{x}"
        if zname in base.columns:
            base[f"iv_offlate_x_{x}"] = base["official_late_z"] * base[zname]
            base[f"iv_off2016_x_{x}"] = base["official_2016plus"] * base[zname]
    if "asinh_rb_inc_farm" not in base.columns and "base_asinh_farm_income" in base.columns:
        base["asinh_rb_inc_farm"] = base["base_asinh_farm_income"]
    return base


def balance_one(df: pd.DataFrame, y: str, z: str, controls: str) -> dict:
    cols = [y, z, "__cid_id", "__prov_id", "region"]
    data = df[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(data) < 50 or data["__cid_id"].nunique() < 10 or data[z].std() < 1e-12:
        return {"b": np.nan, "se": np.nan, "p": np.nan, "N": len(data), "counties": data["__cid_id"].nunique(), "status": "too_few"}
    x = pd.DataFrame({"const": 1.0, z: data[z].astype(float)})
    if controls == "region_fe":
        x = pd.concat([x, pd.get_dummies(data["region"], prefix="region", drop_first=True, dtype=float)], axis=1)
    elif controls == "province_fe":
        x = pd.concat([x, pd.get_dummies(data["__prov_id"].astype(int), prefix="prov", drop_first=True, dtype=float)], axis=1)
    res = sm.OLS(data[y].astype(float), x.astype(float)).fit(
        cov_type="cluster",
        cov_kwds={"groups": data["__cid_id"].astype(int), "use_correction": True},
        use_t=False,
    )
    b = float(res.params[z])
    se = float(res.bse[z])
    p = float(2 * stats.t.sf(abs(b / se), max(int(data["__cid_id"].nunique()) - 1, 1))) if se > 0 else np.nan
    return {"b": b, "se": se, "p": p, "N": int(len(data)), "counties": int(data["__cid_id"].nunique()), "status": "ok"}


def run_balance(panel: pd.DataFrame, ext: pd.DataFrame) -> pd.DataFrame:
    base = balance_frame(panel, ext)
    rows: list[dict] = []
    balance_zs = sorted({v for spec in SPECS for v in spec.base_vars})
    for z in balance_zs:
        if z not in base.columns:
            continue
        for y, ylab in BALANCE_OUTCOMES:
            if y not in base.columns:
                continue
            for controls in ["none", "region_fe", "province_fe"]:
                fr = balance_one(base, y, z, controls)
                rows.append(
                    {
                        "instrument_base": z,
                        "outcome": y,
                        "outcome_label": ylab,
                        "balance_controls": controls,
                        **fr,
                    }
                )
    return pd.DataFrame(rows)


def screen_candidates(iv: pd.DataFrame, bal: pd.DataFrame) -> pd.DataFrame:
    ok = iv[iv["status"].eq("ok")].copy()
    main = ok[
        (ok["scope"].eq("mech"))
        & (ok["anchor"].eq("completed_t"))
        & (ok["controls"].isin(["none", "farm_income", "baseline_bundle"]))
    ].copy()
    # Pair the two outcomes for each specification/variant.
    keys = ["spec", "controls", "fe", "component_controls"]
    wide = main.pivot_table(
        index=keys,
        columns="outcome",
        values=["iv_diff_b", "iv_diff_p", "weak_D_f", "weak_DM_f", "N", "clusters"],
        aggfunc="first",
    )
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    wide = wide.reset_index()
    wide["both_positive"] = (wide["iv_diff_b_any_rentin"] > 0) & (wide["iv_diff_b_asinh_rentin"] > 0)
    wide["both_p10"] = (wide["iv_diff_p_any_rentin"] < 0.10) & (wide["iv_diff_p_asinh_rentin"] < 0.10)
    wide["both_p05"] = (wide["iv_diff_p_any_rentin"] < 0.05) & (wide["iv_diff_p_asinh_rentin"] < 0.05)
    wide["weak_min"] = wide[["weak_D_f_any_rentin", "weak_DM_f_any_rentin", "weak_D_f_asinh_rentin", "weak_DM_f_asinh_rentin"]].min(axis=1)
    wide["clusters_min"] = wide[["clusters_any_rentin", "clusters_asinh_rentin"]].min(axis=1)

    farm_bal = bal[
        (bal["outcome"].eq("asinh_rb_inc_farm"))
        & (bal["balance_controls"].eq("province_fe"))
    ][["instrument_base", "p", "b"]].rename(columns={"p": "farm_income_balance_p_provfe", "b": "farm_income_balance_b_provfe"})
    spec_base = pd.DataFrame(
        [{"spec": spec.name, "instrument_base": spec.base_vars[0], "note": spec.note} for spec in SPECS]
    )
    wide = wide.merge(spec_base, on="spec", how="left").merge(farm_bal, on="instrument_base", how="left")
    wide["score"] = (
        wide["both_positive"].astype(int) * 2
        + wide["both_p10"].astype(int) * 2
        + wide["both_p05"].astype(int)
        + (wide["weak_min"] > 10).astype(int)
        + (wide["clusters_min"] >= 80).astype(int)
        + (wide["farm_income_balance_p_provfe"] > 0.10).fillna(False).astype(int)
    )
    return wide.sort_values(["score", "both_p05", "weak_min", "clusters_min"], ascending=[False, False, False, False])


def summarize(screen: pd.DataFrame, iv: pd.DataFrame, bal: pd.DataFrame, ext: pd.DataFrame) -> str:
    def fmt(x: float, d: int = 3) -> str:
        return "" if pd.isna(x) else f"{x:.{d}f}"

    lines = ["# Round 7 extended IV search memo, 2026-04-30", ""]
    lines.append("## Design space")
    lines.append("")
    lines.append("This round combines the official provincewide rollout schedule with external county/prefecture geography and administrative-cost variables. Direct county-code matches are supplemented by prefecture and province aggregates to avoid losing old-code CLDS counties.")
    lines.append("")
    lines.append("External match levels among CLDS mechanism counties:")
    lines.append("")
    lines.append("| match level | county count |")
    lines.append("|---|---:|")
    for level, n in ext["match_level"].value_counts().items():
        lines.append(f"| {level} | {int(n)} |")
    lines.append("")
    lines.append("## Best candidates by screening score")
    lines.append("")
    cols = [
        "spec",
        "controls",
        "fe",
        "component_controls",
        "iv_diff_b_any_rentin",
        "iv_diff_p_any_rentin",
        "iv_diff_b_asinh_rentin",
        "iv_diff_p_asinh_rentin",
        "weak_min",
        "clusters_min",
        "farm_income_balance_p_provfe",
        "score",
    ]
    lines.append("| spec | controls | FE | comp | any b/p | area b/p | min weak F | clusters | farm-inc bal p | score |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for _, r in screen.head(20)[cols].iterrows():
        lines.append(
            f"| {r['spec']} | {r['controls']} | {r['fe']} | {int(r['component_controls'])} | "
            f"{fmt(r['iv_diff_b_any_rentin'])}/{fmt(r['iv_diff_p_any_rentin'])} | "
            f"{fmt(r['iv_diff_b_asinh_rentin'])}/{fmt(r['iv_diff_p_asinh_rentin'])} | "
            f"{fmt(r['weak_min'], 1)} | {fmt(r['clusters_min'], 0)} | "
            f"{fmt(r['farm_income_balance_p_provfe'])} | {int(r['score'])} |"
        )
    lines.append("")
    lines.append("## Interpretation rule")
    lines.append("")
    lines.append("A candidate is suitable for main-text IV only if it is positive for both outcomes, has at least p<0.10 for both outcomes in the preferred control specification, has first-stage diagnostics comfortably above 10 for both endogenous variables, uses broad county support, and does not reproduce the farm-income balance problem under province fixed effects.")
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append("- Script: `scripts/round7_iv_extended_search_20260430.py`")
    lines.append("- IV scan: `result/round7_iv_extended_search_20260430/tables/Round7_IV_extended_scan.csv`")
    lines.append("- Balance scan: `result/round7_iv_extended_search_20260430/tables/Round7_IV_extended_balance.csv`")
    lines.append("- Candidate screen: `result/round7_iv_extended_search_20260430/tables/Round7_IV_candidate_screen.csv`")
    lines.append("- External covariate audit: `result/round7_iv_extended_search_20260430/audit/Round7_external_covariate_audit.csv`")
    return "\n".join(lines)


def main() -> None:
    ensure_dirs()
    panel, admin = read_inputs()
    sample_counties = panel.loc[panel["s_mech_hh"].eq(1), "__cid_id"]
    ext, file_audit = load_external_covariates(sample_counties)
    file_audit.to_csv(AUDIT / "Round7_external_source_files.csv", index=False, encoding="utf-8-sig")
    ext.to_csv(AUDIT / "Round7_external_covariate_audit.csv", index=False, encoding="utf-8-sig")
    admin_thr = admin_threshold_base(admin)

    balance = run_balance(panel, ext)
    balance.to_csv(TABLES / "Round7_IV_extended_balance.csv", index=False, encoding="utf-8-sig")

    rows: list[dict] = []
    for scope in ["mech", "adjacent"]:
        for anchor in ["completed_t", "high_sat80_t"]:
            stack = make_stack(panel, admin_thr, ext, scope, anchor)
            for spec in SPECS:
                component_options = [False, True] if spec.component_vars else [False]
                for outcome in OUTCOMES:
                    for controls in ["none", "farm_income", "baseline_bundle"]:
                        for fe_variant in ["year", "provyear"]:
                            for comp in component_options:
                                try:
                                    row = run_iv(stack, spec, outcome, controls, fe_variant, comp)
                                    row.update({"scope": scope, "anchor": anchor, "note": spec.note})
                                except Exception as exc:  # noqa: BLE001
                                    row = {
                                        "spec": spec.name,
                                        "outcome": outcome,
                                        "controls": controls,
                                        "fe": fe_variant,
                                        "component_controls": int(comp),
                                        "scope": scope,
                                        "anchor": anchor,
                                        "note": spec.note,
                                        "status": f"error:{type(exc).__name__}:{exc}",
                                    }
                                rows.append(row)
    iv = pd.DataFrame(rows)
    iv.to_csv(TABLES / "Round7_IV_extended_scan.csv", index=False, encoding="utf-8-sig")
    screen = screen_candidates(iv, balance)
    screen.to_csv(TABLES / "Round7_IV_candidate_screen.csv", index=False, encoding="utf-8-sig")
    (OUT / "Round7_IV_extended_search_memo_20260430.md").write_text(summarize(screen, iv, balance, ext), encoding="utf-8")
    print(f"Round 7 outputs written to {OUT}")


if __name__ == "__main__":
    main()
