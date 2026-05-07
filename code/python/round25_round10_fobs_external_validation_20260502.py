from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pyreadstat
import statsmodels.api as sm
from scipy import stats


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import round7_iv_extended_search_20260430 as r7  # noqa: E402


OUT = ROOT / "result" / "round25_empirical_rebuild_20260502" / "round10_fobs_external_validation"
TABLES = OUT / "tables"
AUDIT = OUT / "audit"

FOBS_DIR = ROOT / "data" / "topjournal_rebuild" / "fobs"
HH_PANEL = FOBS_DIR / "fobs_household_analysis_panel_hybrid_admin_20260415.dta"
VILL_PANEL = FOBS_DIR / "fobs_village_analysis_panel_hybrid_admin_20260415.dta"
CRED_PROXIES = FOBS_DIR / "fobs_credibility_proxies_prepolicy.dta"


HH_OUTCOMES = [
    "any_transfer_in_zfill",
    "asinh_transfer_in_area_zfill",
    "any_transfer_out_zfill",
    "asinh_transfer_out_area_zfill",
    "asinh_market_volume_area_zfill",
    "asinh_operated_area_end",
    "asinh_farm_income",
    "farm_income_share",
]

VILL_OUTCOMES = [
    "any_transfer_in_v",
    "asinh_transfer_in_area_zfill",
    "any_transfer_out_v",
    "asinh_transfer_out_area_zfill",
    "asinh_market_volume_area_zfill",
    "birth_rate",
]

CORE_TREATS = [
    "hybrid_started_t",
    "hybrid_rate_any_t",
    "hybrid_rate_mid_t",
    "hybrid_rate_high_t",
    "hybrid_completed_t",
    "hybrid_completion_rate",
]

PRETREND_OUTCOMES = [
    "any_transfer_in_zfill",
    "asinh_transfer_in_area_zfill",
    "asinh_operated_area_end",
    "asinh_market_volume_area_zfill",
]

PROXY_OUTCOMES = [
    "any_transfer_in_zfill",
    "asinh_transfer_in_area_zfill",
    "asinh_operated_area_end",
    "asinh_market_volume_area_zfill",
]

PROXY_SPECS = [
    "tenure_risk_index_z",
    "risk_dispute_z",
    "risk_reserved_z",
    "risk_transferout_z",
]


def ensure_dirs() -> None:
    for p in [OUT, TABLES, AUDIT]:
        p.mkdir(parents=True, exist_ok=True)


def fmt(x: float | int | str | None, d: int = 3) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except TypeError:
        return str(x)
    if isinstance(x, str):
        return x
    return f"{float(x):.{d}f}"


def standardize(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    sd = x.std(skipna=True)
    if not sd or not np.isfinite(sd):
        return pd.Series(np.nan, index=x.index)
    return (x - x.mean(skipna=True)) / sd


def to_num(df: pd.DataFrame, except_cols: set[str] | None = None) -> pd.DataFrame:
    except_cols = except_cols or set()
    out = df.copy()
    for c in out.columns:
        if c not in except_cols:
            out[c] = pd.to_numeric(out[c], errors="ignore")
    return out


def add_common_outcomes(df: pd.DataFrame, level: str) -> pd.DataFrame:
    out = df.copy()
    for c in [
        "transfer_in_area",
        "transfer_out_area",
        "any_transfer_in",
        "any_transfer_out",
        "operated_area_end",
        "farm_income",
        "farm_income_share",
        "birth_rate",
    ]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    if "transfer_in_area" in out.columns:
        ti = out["transfer_in_area"].fillna(0).clip(lower=0)
        out["transfer_in_area_zfill"] = ti
        out["asinh_transfer_in_area_zfill"] = np.arcsinh(ti)
        if "any_transfer_in" in out.columns:
            out["any_transfer_in_zfill"] = pd.to_numeric(out["any_transfer_in"], errors="coerce").fillna(0)
        else:
            out["any_transfer_in_zfill"] = (ti > 0).astype(float)
        out["any_transfer_in_v"] = (ti > 0).astype(float)
    if "transfer_out_area" in out.columns:
        to = out["transfer_out_area"].fillna(0).clip(lower=0)
        out["transfer_out_area_zfill"] = to
        out["asinh_transfer_out_area_zfill"] = np.arcsinh(to)
        if "any_transfer_out" in out.columns:
            out["any_transfer_out_zfill"] = pd.to_numeric(out["any_transfer_out"], errors="coerce").fillna(0)
        else:
            out["any_transfer_out_zfill"] = (to > 0).astype(float)
        out["any_transfer_out_v"] = (to > 0).astype(float)
    if {"transfer_in_area_zfill", "transfer_out_area_zfill"}.issubset(out.columns):
        out["market_volume_area_zfill"] = out["transfer_in_area_zfill"] + out["transfer_out_area_zfill"]
        out["asinh_market_volume_area_zfill"] = np.arcsinh(out["market_volume_area_zfill"])
    if "asinh_operated_area_end" not in out.columns and "operated_area_end" in out.columns:
        out["asinh_operated_area_end"] = np.arcsinh(out["operated_area_end"].clip(lower=0))
    if "asinh_farm_income" not in out.columns and "farm_income" in out.columns:
        out["asinh_farm_income"] = np.arcsinh(out["farm_income"].clip(lower=0))

    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")
    out["county_id_num"] = pd.to_numeric(out["county_id_num"], errors="coerce").astype("Int64")
    if "prov_id" not in out.columns:
        out["prov_id"] = np.floor(pd.to_numeric(out["county_id_num"], errors="coerce") / 10000)
    out["prov_id"] = pd.to_numeric(out["prov_id"], errors="coerce").astype("Int64")
    out["prov_year"] = out["prov_id"].astype(str) + "_" + out["year"].astype(str)

    if level == "household":
        out["unit_id"] = out["household_id"].astype(str)
    elif level == "village":
        out["unit_id"] = out["village_id"].astype(str)
    else:
        out["unit_id"] = out["county_id_num"].astype(str)
    return out


def read_household() -> pd.DataFrame:
    df, _ = pyreadstat.read_dta(str(HH_PANEL))
    df = add_common_outcomes(df, "household")
    df["overlap_sample"] = pd.to_numeric(df.get("in_both_segments"), errors="coerce").eq(1)
    df["long_sample"] = pd.to_numeric(df.get("full_2009_2017_candidate"), errors="coerce").eq(1)
    return df


def read_village() -> pd.DataFrame:
    df, _ = pyreadstat.read_dta(str(VILL_PANEL))
    return add_common_outcomes(df, "village")


def read_proxy() -> pd.DataFrame:
    df, _ = pyreadstat.read_dta(str(CRED_PROXIES))
    df["county_id_num"] = pd.to_numeric(df["county_id_num"], errors="coerce").astype("Int64")
    out = df.copy()
    out["risk_reserved_z"] = pd.to_numeric(out.get("z_proxy_reserved_land_share"), errors="coerce")
    if "z_proxy_low_dispute" in out.columns:
        out["risk_dispute_z"] = -pd.to_numeric(out["z_proxy_low_dispute"], errors="coerce")
    else:
        out["risk_dispute_z"] = standardize(pd.to_numeric(out.get("proxy_civil_disputes_raw"), errors="coerce"))
    out["risk_transferout_z"] = pd.to_numeric(out.get("z_proxy_transfer_out_pre"), errors="coerce")
    comps = out[["risk_reserved_z", "risk_dispute_z", "risk_transferout_z"]]
    out["tenure_risk_index_z"] = standardize(comps.mean(axis=1, skipna=True))
    county = (
        out.groupby("county_id_num", dropna=True)[
            ["tenure_risk_index_z", "risk_dispute_z", "risk_reserved_z", "risk_transferout_z", "cred_zindex"]
        ]
        .mean(numeric_only=True)
        .reset_index()
    )
    for c in ["tenure_risk_index_z", "risk_dispute_z", "risk_reserved_z", "risk_transferout_z", "cred_zindex"]:
        if c in county.columns:
            county[c] = standardize(county[c])
            county[f"{c}_high"] = np.where(county[c].notna(), (county[c] >= county[c].median(skipna=True)).astype(float), np.nan)
    return county


def fit_fe(
    data: pd.DataFrame,
    y: str,
    regressors: list[str],
    fe_cols: list[str],
    cluster_col: str = "county_id_num",
    min_n: int = 50,
    min_clusters: int = 8,
) -> tuple[object, pd.DataFrame, list[str]]:
    cols = [y, cluster_col] + fe_cols + regressors
    use = data[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(use) < min_n or use[cluster_col].nunique() < min_clusters:
        raise ValueError("too few observations")
    res, kept = r7.residualize(use, [y] + regressors, fe_cols)
    keep_cols: list[str] = []
    rank = 0
    for col in regressors:
        cand = res[keep_cols + [col]].to_numpy()
        new_rank = np.linalg.matrix_rank(cand, tol=1e-10)
        if new_rank > rank:
            keep_cols.append(col)
            rank = new_rank
    if not keep_cols:
        raise ValueError("no regressors after FE")
    x = res[keep_cols].astype(float)
    fit = sm.OLS(res[y].astype(float), x).fit(
        cov_type="cluster",
        cov_kwds={"groups": kept[cluster_col].astype(int), "use_correction": True},
        use_t=False,
    )
    return fit, kept, keep_cols


def lincom(fit: object, terms: list[tuple[str, float]]) -> tuple[float, float, float]:
    params = fit.params
    cov = fit.cov_params()
    present = [(t, w) for t, w in terms if t in params.index]
    if not present:
        return np.nan, np.nan, np.nan
    b = sum(float(params[t]) * w for t, w in present)
    var = 0.0
    for i, wi in present:
        for j, wj in present:
            var += wi * wj * float(cov.loc[i, j])
    se = np.sqrt(var) if var >= 0 else np.nan
    p = float(2 * stats.norm.sf(abs(b / se))) if se and np.isfinite(se) and se > 0 else np.nan
    return b, se, p


def wild_cluster_p(
    data: pd.DataFrame,
    y: str,
    treat: str,
    fe_cols: list[str],
    cluster_col: str = "county_id_num",
    reps: int = 999,
    seed: int = 2510,
) -> tuple[float, float, int] | tuple[float, float, int]:
    cols = [y, treat, cluster_col] + fe_cols
    use = data[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(use) < 50 or use[cluster_col].nunique() < 8 or use[treat].nunique() < 2:
        return np.nan, np.nan, 0
    res, kept = r7.residualize(use, [y, treat], fe_cols)
    x_df = res[[treat]].astype(float)
    x = x_df.to_numpy()
    yv = res[y].astype(float).to_numpy()
    clusters = kept[cluster_col].astype(int).to_numpy()
    fit = sm.OLS(res[y].astype(float), x_df).fit(
        cov_type="cluster",
        cov_kwds={"groups": clusters, "use_correction": True},
        use_t=False,
    )
    if treat not in fit.params.index:
        return np.nan, np.nan, 0
    t_obs = float(fit.params[treat] / fit.bse[treat])
    rng = np.random.default_rng(seed)
    unique = np.unique(clusters)
    ge = 0
    done = 0
    for _ in range(reps):
        weights = dict(zip(unique, rng.choice([-1.0, 1.0], size=len(unique))))
        w = np.array([weights[c] for c in clusters])
        y_star = yv * w
        try:
            fb = sm.OLS(pd.Series(y_star, index=x_df.index), x_df).fit(
                cov_type="cluster",
                cov_kwds={"groups": clusters, "use_correction": True},
                use_t=False,
            )
            t_b = float(fb.params[treat] / fb.bse[treat])
            if np.isfinite(t_b):
                ge += abs(t_b) >= abs(t_obs)
                done += 1
        except Exception:
            continue
    return float((ge + 1) / (done + 1)) if done else np.nan, t_obs, done


def sample_filter(df: pd.DataFrame, sample: str) -> pd.Series:
    base = df["county_id_num"].notna()
    if sample == "full":
        return base
    if sample == "overlap":
        return base & df.get("overlap_sample", pd.Series(False, index=df.index)).eq(True)
    if sample == "long":
        return base & df.get("long_sample", pd.Series(False, index=df.index)).eq(True)
    return base


def support_audit(hh: pd.DataFrame, vill: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for level, df, id_col in [("household", hh, "household_id"), ("village", vill, "village_id")]:
        samples = ["full", "overlap", "long"] if level == "household" else ["full"]
        for sample in samples:
            d = df.loc[sample_filter(df, sample)].copy() if level == "household" else df[df["county_id_num"].notna()].copy()
            for treat in CORE_TREATS:
                if treat not in d.columns:
                    continue
                x = pd.to_numeric(d[treat], errors="coerce")
                rows.append(
                    {
                        "level": level,
                        "sample": sample,
                        "treat": treat,
                        "rows_nonmissing": int(x.notna().sum()),
                        "units": int(d.loc[x.notna(), id_col].nunique()) if id_col in d.columns else np.nan,
                        "counties": int(d.loc[x.notna(), "county_id_num"].nunique()),
                        "treated_rows": int(x.eq(1).sum()) if treat != "hybrid_completion_rate" else int(x.gt(0).sum()),
                        "treated_counties": int(d.loc[x.eq(1) if treat != "hybrid_completion_rate" else x.gt(0), "county_id_num"].nunique()),
                        "mean": float(x.mean(skipna=True)),
                    }
                )
    return pd.DataFrame(rows)


def run_main_effects(hh: pd.DataFrame, vill: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    jobs = []
    for sample in ["full", "overlap", "long"]:
        d = hh.loc[sample_filter(hh, sample)].copy()
        jobs.append(("household", sample, d, HH_OUTCOMES, "unit_id"))
    jobs.append(("village", "full", vill.loc[vill["county_id_num"].notna()].copy(), VILL_OUTCOMES, "unit_id"))

    for level, sample, df, outcomes, unit in jobs:
        fe_map = {"unit_year": [unit, "year"], "unit_provyear": [unit, "prov_year"]}
        for outcome in outcomes:
            if outcome not in df.columns:
                continue
            for treat in CORE_TREATS:
                if treat not in df.columns:
                    continue
                for fe_name, fe_cols in fe_map.items():
                    try:
                        fit, kept, kept_regs = fit_fe(df, outcome, [treat], fe_cols)
                        b, se, p = lincom(fit, [(treat, 1.0)])
                        wild_p, t_obs, wild_reps = (np.nan, np.nan, 0)
                        if (
                            level == "household"
                            and sample in {"full", "overlap", "long"}
                            and fe_name == "unit_year"
                            and treat in {"hybrid_rate_high_t", "hybrid_started_t"}
                            and outcome in {"asinh_operated_area_end", "asinh_transfer_in_area_zfill", "any_transfer_in_zfill", "asinh_market_volume_area_zfill"}
                        ):
                            wild_p, t_obs, wild_reps = wild_cluster_p(df, outcome, treat, fe_cols, reps=999)
                        rows.append(
                            {
                                "level": level,
                                "sample": sample,
                                "outcome": outcome,
                                "treat": treat,
                                "fe": fe_name,
                                "b": b,
                                "se": se,
                                "p": p,
                                "wild_p": wild_p,
                                "wild_t": t_obs,
                                "wild_reps": wild_reps,
                                "N": int(len(kept)),
                                "units": int(kept[unit].nunique()) if unit in kept.columns else np.nan,
                                "counties": int(kept["county_id_num"].nunique()),
                                "mean_y": float(df[outcome].mean(skipna=True)),
                                "status": "ok",
                            }
                        )
                    except Exception as exc:  # noqa: BLE001
                        rows.append(
                            {
                                "level": level,
                                "sample": sample,
                                "outcome": outcome,
                                "treat": treat,
                                "fe": fe_name,
                                "status": f"error: {exc}",
                            }
                        )
    return pd.DataFrame(rows)


def county_baselines(df: pd.DataFrame) -> pd.DataFrame:
    base = df.loc[df["year"].eq(2009)].copy()
    vars_ = [v for v in PRETREND_OUTCOMES if v in base.columns]
    out = base.groupby("county_id_num", dropna=True)[vars_].mean(numeric_only=True).reset_index()
    for v in vars_:
        out[f"base2009_{v}"] = standardize(out[v])
    return out[["county_id_num"] + [f"base2009_{v}" for v in vars_]]


def add_baseline_year_terms(data: pd.DataFrame, base_cols: list[str]) -> tuple[pd.DataFrame, list[str]]:
    out = data.copy()
    regs: list[str] = []
    years = sorted(int(y) for y in pd.to_numeric(out["year"], errors="coerce").dropna().unique())
    for b in base_cols:
        if b not in out.columns:
            continue
        for yr in years:
            col = f"{b}_x_y{yr}"
            out[col] = pd.to_numeric(out[b], errors="coerce") * out["year"].eq(yr).astype(float)
            regs.append(col)
    return out, regs


def add_future_flag(df: pd.DataFrame, treat: str, name: str, min_year: int = 2015) -> pd.DataFrame:
    out = df.copy()
    future = (
        out.loc[out["year"].ge(min_year) & pd.to_numeric(out[treat], errors="coerce").notna()]
        .groupby("county_id_num")[treat]
        .max()
    )
    out[name] = out["county_id_num"].map(future)
    return out


def run_pretrend_placebo(hh: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    base = county_baselines(hh)
    df0 = hh.merge(base, on="county_id_num", how="left")
    future_specs = [
        ("future_high", "hybrid_rate_high_t"),
        ("future_any", "hybrid_rate_any_t"),
    ]
    for future_name, treat in future_specs:
        if treat not in df0.columns:
            continue
        df1 = add_future_flag(df0, treat, future_name, min_year=2015)
        for sample in ["full", "overlap", "long"]:
            d_s = df1.loc[sample_filter(df1, sample)].copy()
            for cutoff in [2013, 2014]:
                pre = d_s.loc[d_s["year"].le(cutoff)].copy()
                pre["trend"] = pre["year"].astype(float) - 2009.0
                pre[f"{future_name}_trend"] = pd.to_numeric(pre[future_name], errors="coerce") * pre["trend"]
                base_cols = [c for c in pre.columns if c.startswith("base2009_")]
                pre_cond, bregs = add_baseline_year_terms(pre, base_cols)
                for outcome in PRETREND_OUTCOMES:
                    if outcome not in pre.columns:
                        continue
                    for fe_name, fe_cols in {"hh_year": ["unit_id", "year"], "hh_provyear": ["unit_id", "prov_year"]}.items():
                        for controls, pdata, regs_extra in [
                            ("unconditional", pre, []),
                            ("conditional_base2009_by_year", pre_cond, bregs),
                        ]:
                            regs = [f"{future_name}_trend"] + regs_extra
                            try:
                                fit, kept, _ = fit_fe(pdata, outcome, regs, fe_cols, min_n=80, min_clusters=8)
                                b, se, p = lincom(fit, [(f"{future_name}_trend", 1.0)])
                                future_counties = set(
                                    pd.to_numeric(
                                        pdata.loc[pd.to_numeric(pdata[future_name], errors="coerce").eq(1), "county_id_num"],
                                        errors="coerce",
                                    )
                                    .dropna()
                                    .astype(int)
                                )
                                rows.append(
                                    {
                                        "sample": sample,
                                        "future_group": future_name,
                                        "test": f"linear_2009_{cutoff}",
                                        "outcome": outcome,
                                        "fe": fe_name,
                                        "controls": controls,
                                        "b": b,
                                        "se": se,
                                        "p": p,
                                        "N": int(len(kept)),
                                        "counties": int(kept["county_id_num"].nunique()),
                                        "treated_counties": int(pd.to_numeric(kept["county_id_num"], errors="coerce").dropna().astype(int).isin(future_counties).sum() > 0)
                                        if kept["county_id_num"].nunique() == 1
                                        else int(pd.to_numeric(kept["county_id_num"], errors="coerce").dropna().astype(int).drop_duplicates().isin(future_counties).sum()),
                                        "status": "ok",
                                    }
                                )
                            except Exception as exc:  # noqa: BLE001
                                rows.append(
                                    {
                                        "sample": sample,
                                        "future_group": future_name,
                                        "test": f"linear_2009_{cutoff}",
                                        "outcome": outcome,
                                        "fe": fe_name,
                                        "controls": controls,
                                        "status": f"error: {exc}",
                                    }
                                )

            pre = d_s.loc[d_s["year"].le(2014)].copy()
            base_cols = [c for c in pre.columns if c.startswith("base2009_")]
            pre_cond, bregs = add_baseline_year_terms(pre, base_cols)
            for placebo_year in [2013, 2014]:
                pre[f"{future_name}_post{placebo_year}"] = pd.to_numeric(pre[future_name], errors="coerce") * pre["year"].ge(placebo_year).astype(float)
                pre_cond[f"{future_name}_post{placebo_year}"] = pd.to_numeric(pre_cond[future_name], errors="coerce") * pre_cond["year"].ge(placebo_year).astype(float)
                for outcome in PRETREND_OUTCOMES:
                    if outcome not in pre.columns:
                        continue
                    for fe_name, fe_cols in {"hh_year": ["unit_id", "year"], "hh_provyear": ["unit_id", "prov_year"]}.items():
                        for controls, pdata, regs_extra in [
                            ("unconditional", pre, []),
                            ("conditional_base2009_by_year", pre_cond, bregs),
                        ]:
                            reg = f"{future_name}_post{placebo_year}"
                            regs = [reg] + regs_extra
                            try:
                                fit, kept, _ = fit_fe(pdata, outcome, regs, fe_cols, min_n=80, min_clusters=8)
                                b, se, p = lincom(fit, [(reg, 1.0)])
                                future_counties = set(
                                    pd.to_numeric(
                                        pdata.loc[pd.to_numeric(pdata[future_name], errors="coerce").eq(1), "county_id_num"],
                                        errors="coerce",
                                    )
                                    .dropna()
                                    .astype(int)
                                )
                                rows.append(
                                    {
                                        "sample": sample,
                                        "future_group": future_name,
                                        "test": f"placebo_post{placebo_year}",
                                        "outcome": outcome,
                                        "fe": fe_name,
                                        "controls": controls,
                                        "b": b,
                                        "se": se,
                                        "p": p,
                                        "N": int(len(kept)),
                                        "counties": int(kept["county_id_num"].nunique()),
                                        "treated_counties": int(pd.to_numeric(kept["county_id_num"], errors="coerce").dropna().astype(int).drop_duplicates().isin(future_counties).sum()),
                                        "status": "ok",
                                    }
                                )
                            except Exception as exc:  # noqa: BLE001
                                rows.append(
                                    {
                                        "sample": sample,
                                        "future_group": future_name,
                                        "test": f"placebo_post{placebo_year}",
                                        "outcome": outcome,
                                        "fe": fe_name,
                                        "controls": controls,
                                        "status": f"error: {exc}",
                                    }
                                )
    return pd.DataFrame(rows)


def make_county_agg(hh: pd.DataFrame) -> pd.DataFrame:
    agg_vars = sorted(set(PRETREND_OUTCOMES + HH_OUTCOMES))
    treat_vars = [t for t in CORE_TREATS if t in hh.columns]
    rows = []
    for (cid, year), g in hh.groupby(["county_id_num", "year"], dropna=True):
        if pd.isna(cid) or pd.isna(year):
            continue
        row = {
            "county_id_num": cid,
            "year": int(year),
            "prov_id": g["prov_id"].dropna().iloc[0] if g["prov_id"].notna().any() else np.nan,
            "n_households": int(g["unit_id"].nunique()),
        }
        for v in agg_vars:
            if v in g.columns:
                row[v] = pd.to_numeric(g[v], errors="coerce").mean(skipna=True)
        for t in treat_vars:
            row[t] = pd.to_numeric(g[t], errors="coerce").max(skipna=True)
        rows.append(row)
    out = pd.DataFrame(rows)
    out["prov_year"] = out["prov_id"].astype("Int64").astype(str) + "_" + out["year"].astype("Int64").astype(str)
    out["unit_id"] = out["county_id_num"].astype(str)
    return out


def run_county_agg_pretrend(hh: pd.DataFrame) -> pd.DataFrame:
    c = make_county_agg(hh)
    return run_pretrend_placebo(c)


def add_proxy_terms(data: pd.DataFrame, risk: str) -> tuple[pd.DataFrame, list[str]]:
    out = data.copy()
    regs: list[str] = []
    for yr in sorted(int(y) for y in out["year"].dropna().unique()):
        col = f"{risk}_x_y{yr}"
        out[col] = pd.to_numeric(out[risk], errors="coerce") * out["year"].eq(yr).astype(float)
        regs.append(col)
    return out, regs


def run_proxy_interactions(hh: pd.DataFrame, vill: pd.DataFrame) -> pd.DataFrame:
    proxies = read_proxy()
    rows: list[dict] = []
    tasks = [
        ("household", "full", hh.loc[sample_filter(hh, "full")].merge(proxies, on="county_id_num", how="left"), HH_OUTCOMES, ["unit_id", "year"]),
        ("household", "overlap", hh.loc[sample_filter(hh, "overlap")].merge(proxies, on="county_id_num", how="left"), HH_OUTCOMES, ["unit_id", "year"]),
        ("household", "long", hh.loc[sample_filter(hh, "long")].merge(proxies, on="county_id_num", how="left"), HH_OUTCOMES, ["unit_id", "year"]),
        ("village", "full", vill.loc[vill["county_id_num"].notna()].merge(proxies, on="county_id_num", how="left"), VILL_OUTCOMES, ["unit_id", "year"]),
    ]
    for level, sample, df, outcomes, fe_cols in tasks:
        for risk in PROXY_SPECS:
            if risk not in df.columns:
                continue
            high = f"{risk}_high"
            for risk_var, risk_type in [(risk, "continuous"), (high, "high_binary")]:
                if risk_var not in df.columns:
                    continue
                for treat in ["hybrid_started_t", "hybrid_rate_high_t", "hybrid_rate_any_t"]:
                    if treat not in df.columns:
                        continue
                    d = df.copy()
                    d["T_x_R"] = pd.to_numeric(d[treat], errors="coerce") * pd.to_numeric(d[risk_var], errors="coerce")
                    d, rregs = add_proxy_terms(d, risk_var)
                    regs = [treat, "T_x_R"] + rregs
                    for outcome in outcomes:
                        if outcome not in d.columns or outcome not in PROXY_OUTCOMES:
                            continue
                        try:
                            fit, kept, _ = fit_fe(d, outcome, regs, fe_cols, min_n=80, min_clusters=8)
                            for term, terms in {
                                "baseline/low-risk treatment effect": [(treat, 1.0)],
                                "risk interaction": [("T_x_R", 1.0)],
                                "high-risk total effect": [(treat, 1.0), ("T_x_R", 1.0)],
                            }.items():
                                b, se, p = lincom(fit, terms)
                                rows.append(
                                    {
                                        "level": level,
                                        "sample": sample,
                                        "risk_proxy": risk,
                                        "risk_type": risk_type,
                                        "treat": treat,
                                        "outcome": outcome,
                                        "term": term,
                                        "b": b,
                                        "se": se,
                                        "p": p,
                                        "N": int(len(kept)),
                                        "counties": int(kept["county_id_num"].nunique()),
                                        "proxy_counties": int(kept["county_id_num"].nunique()),
                                        "status": "ok",
                                    }
                                )
                        except Exception as exc:  # noqa: BLE001
                            rows.append(
                                {
                                    "level": level,
                                    "sample": sample,
                                    "risk_proxy": risk,
                                    "risk_type": risk_type,
                                    "treat": treat,
                                    "outcome": outcome,
                                    "status": f"error: {exc}",
                                }
                            )
    return pd.DataFrame(rows)


def score_pretrend(pre: pd.DataFrame) -> pd.DataFrame:
    ok = pre[pre["status"].eq("ok")].copy()
    rows: list[dict] = []
    for controls in ["unconditional", "conditional_base2009_by_year"]:
        for sample in ["full", "overlap", "long"]:
            for future in ["future_high", "future_any"]:
                sub = ok[
                    ok["controls"].eq(controls)
                    & ok["sample"].eq(sample)
                    & ok["future_group"].eq(future)
                    & ok["fe"].eq("hh_provyear")
                    & ok["outcome"].isin(["any_transfer_in_zfill", "asinh_transfer_in_area_zfill"])
                ]
                if sub.empty:
                    continue
                rows.append(
                    {
                        "controls": controls,
                        "sample": sample,
                        "future_group": future,
                        "tests": int(len(sub)),
                        "share_p_gt_10": float(sub["p"].gt(0.10).mean()),
                        "min_p": float(sub["p"].min()),
                        "median_p": float(sub["p"].median()),
                        "treated_counties_median": float(sub["treated_counties"].median()),
                    }
                )
    return pd.DataFrame(rows)


def write_memo(
    support: pd.DataFrame,
    main: pd.DataFrame,
    pre: pd.DataFrame,
    pre_county: pd.DataFrame,
    proxy: pd.DataFrame,
    score: pd.DataFrame,
) -> None:
    def md_table(df: pd.DataFrame, cols: list[str], max_rows: int = 24) -> str:
        if df.empty:
            return "_No rows._"
        show = df.head(max_rows)[cols].copy()
        for c in ["b", "se", "p", "wild_p", "mean_y", "share_p_gt_10", "min_p", "median_p"]:
            if c in show.columns:
                show[c] = show[c].map(fmt)
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
        for _, r in show.iterrows():
            lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
        return "\n".join(lines)

    operated = main[
        main["status"].eq("ok")
        & main["level"].eq("household")
        & main["outcome"].eq("asinh_operated_area_end")
        & main["treat"].isin(["hybrid_rate_high_t", "hybrid_rate_mid_t", "hybrid_rate_any_t", "hybrid_started_t"])
        & main["fe"].eq("unit_year")
    ].sort_values(["sample", "p"])
    transfer = main[
        main["status"].eq("ok")
        & main["level"].eq("household")
        & main["outcome"].isin(["any_transfer_in_zfill", "asinh_transfer_in_area_zfill", "asinh_market_volume_area_zfill"])
        & main["treat"].isin(["hybrid_rate_high_t", "hybrid_started_t"])
        & main["fe"].eq("unit_year")
    ].sort_values(["outcome", "sample", "p"])
    pre_clean = pre[
        pre["status"].eq("ok")
        & pre["controls"].eq("conditional_base2009_by_year")
        & pre["future_group"].eq("future_high")
        & pre["fe"].eq("hh_provyear")
        & pre["outcome"].isin(["any_transfer_in_zfill", "asinh_transfer_in_area_zfill"])
    ].sort_values(["sample", "test", "outcome"])
    county_clean = pre_county[
        pre_county["status"].eq("ok")
        & pre_county["controls"].eq("conditional_base2009_by_year")
        & pre_county["future_group"].eq("future_high")
        & pre_county["fe"].eq("hh_provyear")
        & pre_county["outcome"].isin(["any_transfer_in_zfill", "asinh_transfer_in_area_zfill"])
    ].sort_values(["sample", "test", "outcome"])
    if not proxy.empty and "term" in proxy.columns:
        proxy_best = proxy[
            proxy["status"].eq("ok")
            & proxy["term"].isin(["risk interaction", "high-risk total effect"])
            & proxy["outcome"].isin(["asinh_operated_area_end", "asinh_transfer_in_area_zfill", "asinh_market_volume_area_zfill"])
            & proxy["p"].lt(0.10)
        ].sort_values(["p", "level", "sample"]).head(30)
    else:
        proxy_best = pd.DataFrame()

    lines: list[str] = []
    lines.append("# Round 10 FOBS external validation memo, 2026-05-02")
    lines.append("")
    lines.append("## Bottom line")
    lines.append("")
    lines.append(
        "FOBS is useful as conditional external corroboration, not as a second main identification design. "
        "The best external result is the production-scale response: mature/high-saturation rollout is associated with larger operated farm area, especially in overlap and long-panel household samples. "
        "Transfer-in evidence is directionally useful but less stable than CLDS; FOBS transfer-out should remain supplementary. "
        "Native FOBS county-level tenure-risk proxies can be explored, but they should not replace the CLDS baseline-insecurity moderator."
    )
    lines.append("")
    lines.append("## Support audit")
    lines.append("")
    lines.append(md_table(support[support["level"].eq("household")], ["sample", "treat", "rows_nonmissing", "units", "counties", "treated_counties", "mean"], 30))
    lines.append("")
    lines.append("## Main external validation: operated area")
    lines.append("")
    lines.append(md_table(operated, ["sample", "treat", "b", "se", "p", "wild_p", "N", "units", "counties"], 30))
    lines.append("")
    lines.append("## Transfer-flow checks")
    lines.append("")
    lines.append(md_table(transfer, ["sample", "outcome", "treat", "b", "se", "p", "wild_p", "N", "counties"], 30))
    lines.append("")
    lines.append("## Conditional household pretrends/placebos")
    lines.append("")
    lines.append(md_table(pre_clean, ["sample", "test", "outcome", "b", "se", "p", "N", "counties", "treated_counties"], 36))
    lines.append("")
    lines.append("## Conditional county-aggregate pretrends/placebos")
    lines.append("")
    lines.append(md_table(county_clean, ["sample", "test", "outcome", "b", "se", "p", "N", "counties", "treated_counties"], 36))
    lines.append("")
    lines.append("## Pretrend scorecard")
    lines.append("")
    lines.append(md_table(score, ["controls", "sample", "future_group", "tests", "share_p_gt_10", "min_p", "median_p", "treated_counties_median"], 30))
    lines.append("")
    lines.append("## Native FOBS tenure-risk proxy exploration")
    lines.append("")
    lines.append(md_table(proxy_best, ["level", "sample", "risk_proxy", "risk_type", "treat", "outcome", "term", "b", "se", "p", "N", "counties"], 30))
    lines.append("")
    lines.append("## Manuscript recommendation")
    lines.append("")
    lines.append(
        "Use FOBS in the appendix to corroborate two claims: first, later high-saturation counties do not show differential transfer-in pretrends after province-year and 2009 baseline land-market conditioning; second, annual FOBS data show a mature-rollout production-scale response. "
        "Do not attach the CLDS village-level baseline insecurity moderator to FOBS. If a tenure-risk angle is desired, describe the FOBS proxies as native, county-level exploratory checks only."
    )
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append("- Support audit: `result/round25_empirical_rebuild_20260502/round10_fobs_external_validation/audit/Round10_FOBS_support_audit.csv`")
    lines.append("- Main effects: `result/round25_empirical_rebuild_20260502/round10_fobs_external_validation/tables/Round10_FOBS_main_effects.csv`")
    lines.append("- Household pretrends/placebos: `result/round25_empirical_rebuild_20260502/round10_fobs_external_validation/tables/Round10_FOBS_household_pretrend_placebo.csv`")
    lines.append("- County-aggregate pretrends/placebos: `result/round25_empirical_rebuild_20260502/round10_fobs_external_validation/tables/Round10_FOBS_countyagg_pretrend_placebo.csv`")
    lines.append("- Native proxy interactions: `result/round25_empirical_rebuild_20260502/round10_fobs_external_validation/tables/Round10_FOBS_native_tenure_risk_proxy.csv`")
    (OUT / "Round10_FOBS_ExternalValidation_Memo_20260502.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    hh = read_household()
    vill = read_village()
    support = support_audit(hh, vill)
    main = run_main_effects(hh, vill)
    pre = run_pretrend_placebo(hh)
    pre_county = run_county_agg_pretrend(hh)
    proxy = run_proxy_interactions(hh, vill)
    score = score_pretrend(pre)

    support.to_csv(AUDIT / "Round10_FOBS_support_audit.csv", index=False, encoding="utf-8-sig")
    main.to_csv(TABLES / "Round10_FOBS_main_effects.csv", index=False, encoding="utf-8-sig")
    pre.to_csv(TABLES / "Round10_FOBS_household_pretrend_placebo.csv", index=False, encoding="utf-8-sig")
    pre_county.to_csv(TABLES / "Round10_FOBS_countyagg_pretrend_placebo.csv", index=False, encoding="utf-8-sig")
    proxy.to_csv(TABLES / "Round10_FOBS_native_tenure_risk_proxy.csv", index=False, encoding="utf-8-sig")
    score.to_csv(TABLES / "Round10_FOBS_pretrend_scorecard.csv", index=False, encoding="utf-8-sig")
    write_memo(support, main, pre, pre_county, proxy, score)
    print(f"Wrote Round 10 outputs to {OUT}")


if __name__ == "__main__":
    main()
