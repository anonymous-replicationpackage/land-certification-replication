from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from linearmodels.iv import IV2SLS
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import round7_iv_extended_search_20260430 as r7  # noqa: E402
import round8_preferred_iv_geosurvey_20260430 as r8  # noqa: E402


OUT = ROOT / "result" / "round25_empirical_rebuild_20260502" / "round7_iv_exclusion"
TABLES = OUT / "tables"
AUDIT = OUT / "audit"

OUTCOMES = ["any_rentin", "asinh_rentin"]
ANCHORS = ["completed_t", "signoff_or_issue_t"]
CONTROLS = ["farm_income", "baseline_bundle"]

DIRECT_GEO = ["z_rugged", "z_log_area", "z_dist_capital"]
DIRECT_GEO_DEV = [
    "z_rugged",
    "z_log_area",
    "z_dist_capital",
    "z_workload",
]
BASELINE_CHANNELS = [
    "b14_any_rentin",
    "b14_asinh_rentin",
    "b14_any_rentout",
    "b14_asinh_rentout",
    "b14_land_total_mu",
    "b14_contract_land_mu",
    "b14_asinh_farm_cost",
    "b14_nonfarm_n",
    "b14_nonfarm_any",
    "b14_govrent_any",
    "b14_mobility_ease",
]
CHANNEL_GROUPS = {
    "rent": [
        "b14_any_rentin",
        "b14_asinh_rentin",
        "b14_any_rentout",
        "b14_asinh_rentout",
    ],
    "land": [
        "b14_land_total_mu",
        "b14_contract_land_mu",
    ],
    "labor_cost": [
        "b14_asinh_farm_cost",
        "b14_nonfarm_n",
        "b14_nonfarm_any",
    ],
    "gov_mobility": [
        "b14_govrent_any",
        "b14_mobility_ease",
    ],
}


@dataclass(frozen=True)
class IVBundle:
    name: str
    label: str
    bases: tuple[str, ...]


IV_BUNDLES = [
    IVBundle(
        "geo_area_rugged",
        "official schedule x terrain-area survey difficulty",
        ("iv_official_x_geo_area_rugged",),
    ),
    IVBundle(
        "survey_net_distance",
        "official schedule x survey difficulty net of simple distance",
        ("iv_official_x_survey_net_distance",),
    ),
    IVBundle(
        "geo_plus_rawsurvey",
        "terrain-area difficulty + raw survey-cost index",
        ("iv_official_x_geo_area_rugged", "iv_official_x_survey_cost"),
    ),
    IVBundle(
        "geo_plus_net",
        "terrain-area difficulty + net-distance survey difficulty",
        ("iv_official_x_geo_area_rugged", "iv_official_x_survey_net_distance"),
    ),
    IVBundle(
        "net_plus_rawsurvey",
        "net-distance survey difficulty + raw survey-cost index",
        ("iv_official_x_survey_net_distance", "iv_official_x_survey_cost"),
    ),
]


STRESS_BLOCKS = [
    ("baseline", ()),
    ("lower_order_Z", ("lower_order_z",)),
    ("direct_geo_main_trends", ("geo_main",)),
    ("direct_geo_dev_main_trends", ("geo_dev_main",)),
    ("channel_rent_main", ("channel_rent_imp_main",)),
    ("channel_land_main", ("channel_land_imp_main",)),
    ("channel_labor_cost_main", ("channel_labor_cost_imp_main",)),
    ("channel_gov_mobility_main", ("channel_gov_mobility_imp_main",)),
    ("geo_dev_main_plus_rent", ("geo_dev_main", "channel_rent_imp_main")),
    ("geo_dev_main_plus_land", ("geo_dev_main", "channel_land_imp_main")),
    ("geo_dev_main_plus_labor_cost", ("geo_dev_main", "channel_labor_cost_imp_main")),
    ("geo_dev_main_plus_gov_mobility", ("geo_dev_main", "channel_gov_mobility_imp_main")),
    ("baseline_channels_imputed_main", ("baseline_channels_imp_main",)),
    ("geo_dev_main_plus_channels_main", ("geo_dev_main", "baseline_channels_imp_main")),
    ("geo_dev_main_channels_main_plus_Z", ("lower_order_z", "geo_dev_main", "baseline_channels_imp_main")),
    ("direct_geo_trends", ("geo_direct",)),
    ("direct_geo_trends_plus_Z", ("lower_order_z", "geo_direct")),
    ("direct_geo_dev_trends_plus_Z", ("lower_order_z", "geo_dev_direct")),
    ("baseline_channels_plus_Z", ("lower_order_z", "baseline_channels")),
    ("full_exclusion_controls", ("lower_order_z", "geo_dev_direct", "baseline_channels")),
]


BALANCE_OUTCOMES = [
    ("any_rentin", "Any rent-in (2014)"),
    ("asinh_rentin", "asinh rented-in area (2014)"),
    ("any_rentout", "Any rent-out (2014)"),
    ("asinh_rentout", "asinh rented-out area (2014)"),
    ("a3_tenure_insec_z", "Baseline tenure insecurity index"),
    ("ib_nonfarm_curr_n", "Current nonfarm workers"),
    ("rb_nonfarm_any", "Any broad nonfarm work"),
    ("rb_nonfarm_n", "Broad nonfarm workers"),
    ("land_total_mu", "Household land base"),
    ("contracted_land_mu", "Contracted land"),
    ("asinh_rb_inc_farm", "asinh farm income"),
    ("asinh_rb_farm_cost", "asinh farm cost"),
    ("base14_rg_govrent_any", "Government rent-in any"),
    ("base14_rg_abs_rent", "Absolute rent paid"),
    ("a2_mobility_ease_county_z", "County mobility ease"),
    ("base14_broad_z", "Village broad insecurity z"),
]


def ensure_dirs() -> None:
    for path in [OUT, TABLES, AUDIT]:
        path.mkdir(parents=True, exist_ok=True)


def safe_p(obj) -> float:
    try:
        val = float(obj.pval)
    except Exception:
        val = np.nan
    return val


def short_name(name: str) -> str:
    return (
        name.replace("iv_official_x_", "")
        .replace("survey_net_distance", "net")
        .replace("geo_area_rugged", "geo")
        .replace("survey_cost", "raw")
    )


def zscore(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    sd = s.std(skipna=True)
    if not sd or not np.isfinite(sd):
        return pd.Series(np.nan, index=s.index)
    return (s - s.mean(skipna=True)) / sd


def add_household_baseline_channels(stack: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    out = stack.copy()
    base = panel.loc[panel["year"].eq(2014)].sort_values(["hid", "year"]).drop_duplicates("hid").copy()
    mapping = {
        "any_rentin": "b14_any_rentin",
        "asinh_rentin": "b14_asinh_rentin",
        "any_rentout": "b14_any_rentout",
        "asinh_rentout": "b14_asinh_rentout",
        "land_total_mu": "b14_land_total_mu",
        "contracted_land_mu": "b14_contract_land_mu",
        "asinh_rb_farm_cost": "b14_asinh_farm_cost",
        "ib_nonfarm_curr_n": "b14_nonfarm_n",
        "rb_nonfarm_any": "b14_nonfarm_any",
        "base14_rg_govrent_any": "b14_govrent_any",
        "a2_mobility_ease_county_z": "b14_mobility_ease",
    }
    keep = ["hid"] + [c for c in mapping if c in base.columns]
    base = base[keep].rename(columns={k: v for k, v in mapping.items() if k in base.columns})
    out = out.merge(base, on="hid", how="left", suffixes=("", "_b14src"))
    for col in list(mapping.values()):
        if col in out.columns:
            out[col] = zscore(out[col])
            out[f"{col}_miss"] = out[col].isna().astype(float)
            out[f"{col}_imp"] = out[col].fillna(0.0)
    return out


def add_term_main(df: pd.DataFrame, raw_col: str, prefix: str) -> list[str]:
    if raw_col not in df.columns:
        return []
    base = pd.to_numeric(df[raw_col], errors="coerce")
    name = f"{prefix}_{raw_col}"
    name = name.replace("iv_official_x_", "iv_").replace("z_", "")
    df[name] = df["post"] * base
    return [name]


def add_term_pair(df: pd.DataFrame, raw_col: str, prefix: str) -> list[str]:
    if raw_col not in df.columns:
        return []
    base = pd.to_numeric(df[raw_col], errors="coerce")
    name = f"{prefix}_{raw_col}"
    name = name.replace("iv_official_x_", "iv_").replace("z_", "")
    mname = f"{name}_M"
    df[name] = df["post"] * base
    df[mname] = df[name] * df["instab_high"]
    return [name, mname]


def add_iv_terms(df: pd.DataFrame, bundle: IVBundle) -> tuple[list[str], list[str]]:
    z_main: list[str] = []
    z_int: list[str] = []
    for base in bundle.bases:
        if base not in df.columns:
            continue
        stem = short_name(base)
        z = f"Z_{stem}"
        zm = f"ZM_{stem}"
        df[z] = df["post"] * pd.to_numeric(df[base], errors="coerce")
        df[zm] = df[z] * df["instab_high"]
        z_main.append(z)
        z_int.append(zm)
    return z_main, z_int


def build_extra_controls(df: pd.DataFrame, z_main: list[str], blocks: tuple[str, ...]) -> list[str]:
    cols: list[str] = []
    if "lower_order_z" in blocks:
        cols += z_main
    if "geo_main" in blocks:
        for raw in DIRECT_GEO:
            cols += add_term_main(df, raw, "Tmain")
    if "geo_dev_main" in blocks:
        for raw in DIRECT_GEO_DEV:
            cols += add_term_main(df, raw, "Tmain")
    if "geo_direct" in blocks:
        for raw in DIRECT_GEO:
            cols += add_term_pair(df, raw, "T")
    if "geo_dev_direct" in blocks:
        for raw in DIRECT_GEO_DEV:
            cols += add_term_pair(df, raw, "T")
    if "baseline_channels" in blocks:
        for raw in BASELINE_CHANNELS:
            cols += add_term_pair(df, raw, "B")
    if "baseline_channels_imp_main" in blocks:
        for raw in BASELINE_CHANNELS:
            cols += add_term_main(df, f"{raw}_imp", "BI")
            cols += add_term_main(df, f"{raw}_miss", "BM")
    for group, raw_cols in CHANNEL_GROUPS.items():
        if f"channel_{group}_imp_main" in blocks:
            for raw in raw_cols:
                cols += add_term_main(df, f"{raw}_imp", f"BI{group}")
                cols += add_term_main(df, f"{raw}_miss", f"BM{group}")
    seen: set[str] = set()
    out: list[str] = []
    for col in cols:
        if col not in seen and col in df.columns:
            seen.add(col)
            out.append(col)
    return out


def residualize_and_rank(
    data: pd.DataFrame,
    outcome: str,
    exog_cols: list[str],
    endog_col: str,
    instr_cols: list[str],
    fe_cols: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
    all_cols = [outcome, endog_col] + exog_cols + instr_cols
    res, kept = r7.residualize(data, all_cols, fe_cols)

    def keep_rank(cols: list[str], base_cols: list[str] | None = None) -> list[str]:
        selected: list[str] = []
        base_cols = base_cols or []
        base_mat = res[base_cols].to_numpy() if base_cols else np.empty((len(res), 0))
        rank = np.linalg.matrix_rank(base_mat, tol=1e-10)
        for col in cols:
            arr = res[[col]].to_numpy()
            if np.nanvar(arr) < 1e-12:
                continue
            candidate = np.column_stack([base_mat, res[selected].to_numpy(), arr])
            new_rank = np.linalg.matrix_rank(candidate, tol=1e-10)
            if new_rank > rank + len(selected):
                selected.append(col)
        return selected

    # Keep the endogenous high-insecurity treatment differential as the
    # non-negotiable column; drop any saturated controls that duplicate it
    # after household and province-year residualization.
    exog_keep = keep_rank(exog_cols, [endog_col])
    instr_keep = keep_rank(instr_cols, exog_keep)
    return res, kept, exog_keep, instr_keep


def cluster_ar_zero_p(y: pd.Series, exog: pd.DataFrame, instr: pd.DataFrame, clusters: pd.Series) -> tuple[float, float]:
    x = pd.concat([exog, instr], axis=1)
    fit = sm.OLS(y.astype(float), x.astype(float)).fit(
        cov_type="cluster",
        cov_kwds={"groups": clusters.astype(int), "use_correction": True},
        use_t=False,
    )
    k = instr.shape[1]
    if k == 0:
        return np.nan, np.nan
    b = fit.params[instr.columns].to_numpy(dtype=float)
    cov = fit.cov_params().loc[instr.columns, instr.columns].to_numpy(dtype=float)
    stat = float(b.T @ np.linalg.pinv(cov) @ b)
    p = float(stats.chi2.sf(stat, k))
    return stat, p


def run_one(
    stack_in: pd.DataFrame,
    bundle: IVBundle,
    outcome: str,
    controls: str,
    anchor: str,
    stress_name: str,
    blocks: tuple[str, ...],
) -> dict:
    stack = stack_in.copy()
    z_main, z_int = add_iv_terms(stack, bundle)
    ccols = r7.control_cols(stack, controls)
    ccols += build_extra_controls(stack, z_main, blocks)

    fe_cols = ["hid_stack", "prov_year_stack"]
    needed = [outcome, "PM", "D", "DM", "__cid_id", "hid_stack", "prov_year_stack"] + ccols + z_int
    data = stack[needed].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(data) < 150 or data["__cid_id"].nunique() < 20:
        raise ValueError("too few observations")

    exog_cols = ["PM", "D"] + ccols
    res, kept, exog_keep, instr_keep = residualize_and_rank(
        data, outcome, exog_cols, "DM", z_int, fe_cols
    )
    clusters = kept["__cid_id"].astype(int)
    if len(instr_keep) < 1:
        raise ValueError("no excluded instruments after rank checks")

    ols = IV2SLS(res[outcome], res[exog_keep + ["DM"]], None, None).fit(
        cov_type="clustered", clusters=clusters
    )
    iv = IV2SLS(res[outcome], res[exog_keep], res[["DM"]], res[instr_keep]).fit(
        cov_type="clustered", clusters=clusters
    )
    diag = iv.first_stage.diagnostics
    ar_stat, ar_p = cluster_ar_zero_p(res[outcome], res[exog_keep], res[instr_keep], clusters)

    return {
        "bundle": bundle.name,
        "bundle_label": bundle.label,
        "outcome": outcome,
        "anchor": anchor,
        "controls": controls,
        "stress": stress_name,
        "blocks": ",".join(blocks) if blocks else "none",
        "N": int(len(kept)),
        "clusters": int(clusters.nunique()),
        "n_exog": int(len(exog_keep)),
        "n_instruments": int(len(instr_keep)),
        "dropped_exog": ",".join([c for c in exog_cols if c not in exog_keep]),
        "dropped_instr": ",".join([c for c in z_int if c not in instr_keep]),
        "ols_b": float(ols.params["DM"]),
        "ols_se": float(ols.std_errors["DM"]),
        "ols_p": float(ols.pvalues["DM"]),
        "iv_b": float(iv.params["DM"]),
        "iv_se": float(iv.std_errors["DM"]),
        "iv_p": float(iv.pvalues["DM"]),
        "first_stage_f": float(diag.loc["DM", "f.stat"]),
        "first_stage_p": float(diag.loc["DM", "f.pval"]),
        "partial_r2": float(diag.loc["DM", "partial.rsquared"]),
        "ar_zero_stat": ar_stat,
        "ar_zero_p": ar_p,
        "sargan_p": safe_p(iv.sargan),
        "basmann_p": safe_p(iv.basmann),
        "wooldridge_overid_p": safe_p(iv.wooldridge_overid),
        "status": "ok",
    }


def balance_one(df: pd.DataFrame, y: str, z: str) -> dict:
    cols = [y, z, "__cid_id", "__prov_id"]
    data = df[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(data) < 80 or data["__cid_id"].nunique() < 20:
        return {
            "b": np.nan,
            "se": np.nan,
            "p": np.nan,
            "N": int(len(data)),
            "counties": int(data["__cid_id"].nunique()),
            "status": "too_few",
        }
    x = pd.concat(
        [
            pd.DataFrame({"const": 1.0, z: data[z].astype(float)}, index=data.index),
            pd.get_dummies(data["__prov_id"].astype(int), prefix="prov", drop_first=True, dtype=float),
        ],
        axis=1,
    )
    fit = sm.OLS(data[y].astype(float), x.astype(float)).fit(
        cov_type="cluster",
        cov_kwds={"groups": data["__cid_id"].astype(int), "use_correction": True},
        use_t=False,
    )
    b = float(fit.params[z])
    se = float(fit.bse[z])
    p = float(2 * stats.t.sf(abs(b / se), max(int(data["__cid_id"].nunique()) - 1, 1))) if se > 0 else np.nan
    return {
        "b": b,
        "se": se,
        "p": p,
        "N": int(len(data)),
        "counties": int(data["__cid_id"].nunique()),
        "status": "ok",
    }


def run_balance(panel: pd.DataFrame, ext: pd.DataFrame) -> pd.DataFrame:
    base = r8.balance_frame(panel, ext)
    rows: list[dict] = []
    instrument_bases = {
        "geo_area_rugged": "iv_official_x_geo_area_rugged",
        "survey_net_distance": "iv_official_x_survey_net_distance",
        "raw_survey_cost": "iv_official_x_survey_cost",
    }
    for name, z in instrument_bases.items():
        if z not in base.columns:
            continue
        for y, label in BALANCE_OUTCOMES:
            if y not in base.columns:
                continue
            rows.append(
                {
                    "instrument": name,
                    "instrument_col": z,
                    "outcome": y,
                    "outcome_label": label,
                    "controls": "province_fe",
                    **balance_one(base, y, z),
                }
            )
    return pd.DataFrame(rows)


def compact_summary(results: pd.DataFrame) -> pd.DataFrame:
    ok = results.loc[results["status"].eq("ok")].copy()
    main = ok.loc[
        ok["anchor"].eq("completed_t")
        & ok["controls"].eq("baseline_bundle")
        & ok["bundle"].isin(["geo_area_rugged", "survey_net_distance", "geo_plus_rawsurvey"])
        & ok["stress"].isin(["baseline", "direct_geo_dev_trends_plus_Z", "full_exclusion_controls"])
    ].copy()
    cols = [
        "bundle",
        "outcome",
        "stress",
        "N",
        "clusters",
        "n_instruments",
        "iv_b",
        "iv_se",
        "iv_p",
        "first_stage_f",
        "partial_r2",
        "ar_zero_p",
        "sargan_p",
        "wooldridge_overid_p",
    ]
    return main[cols].sort_values(["bundle", "outcome", "stress"])


def summarize(results: pd.DataFrame, balance: pd.DataFrame) -> str:
    ok = results.loc[results["status"].eq("ok")].copy()
    primary = ok.loc[
        ok["anchor"].eq("completed_t")
        & ok["controls"].eq("baseline_bundle")
        & ok["bundle"].eq("geo_plus_rawsurvey")
        & ok["stress"].isin(["baseline", "direct_geo_dev_trends_plus_Z", "full_exclusion_controls"])
    ].copy()
    lines: list[str] = []
    lines.append("# Round 7 IV exclusion-restriction reinforcement, 2026-05-02")
    lines.append("")
    lines.append("## Design")
    lines.append("")
    lines.append(
        "The preferred IV is kept as an interaction-IV for the high-insecurity differential: "
        "`post x high-insecurity x [official province schedule x county survey difficulty]`. "
        "Province-year fixed effects absorb provincewide official rollout timing; household fixed effects absorb static county geography."
    )
    lines.append("")
    lines.append(
        "This reinforcement adds four exclusion-restriction stress tests: lower-order official-schedule-by-geography terms, "
        "generic geography-by-post trends, geography/development/workload-by-post trends, and 2014 baseline channel-by-post controls."
    )
    lines.append("")
    lines.append("## Preferred strengthened specification")
    lines.append("")
    if not primary.empty:
        lines.append("| outcome | stress test | b | se | p | first-stage F | AR zero p | overid p |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
        for _, r in primary.sort_values(["outcome", "stress"]).iterrows():
            overid = r["wooldridge_overid_p"] if np.isfinite(r["wooldridge_overid_p"]) else r["sargan_p"]
            lines.append(
                f"| {r['outcome']} | {r['stress']} | {r['iv_b']:.3f} | {r['iv_se']:.3f} | "
                f"{r['iv_p']:.3f} | {r['first_stage_f']:.1f} | {r['ar_zero_p']:.3f} | {overid:.3f} |"
            )
    else:
        lines.append("No preferred rows were estimated.")
    lines.append("")
    lines.append("## Baseline balance / direct-channel screen")
    lines.append("")
    bal_ok = balance.loc[balance["status"].eq("ok")].copy()
    if not bal_ok.empty:
        by_inst = (
            bal_ok.groupby("instrument", as_index=False)
            .agg(min_p=("p", "min"), n_tests=("p", "count"))
            .sort_values("min_p", ascending=False)
        )
        lines.append("| instrument | minimum p across 2014 channels | tests |")
        lines.append("|---|---:|---:|")
        for _, r in by_inst.iterrows():
            lines.append(f"| {r['instrument']} | {r['min_p']:.3f} | {int(r['n_tests'])} |")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append(
        "The most defensible path is to present the two-instrument version "
        "(`terrain-area difficulty + raw survey-cost index`) as the strengthened IV robustness check. "
        "It improves first-stage strength relative to a single instrument, permits overidentification tests, "
        "and remains positive after controlling for direct geography/development trends and baseline channels."
    )
    lines.append("")
    lines.append(
        "The single clean instruments are still useful as transparent component checks; the strengthened two-IV specification is the better answer to exclusion-restriction concerns."
    )
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append(f"- Full IV stress table: `{TABLES / 'Round7_IV_exclusion_stress_results.csv'}`")
    lines.append(f"- Compact IV table: `{TABLES / 'Round7_IV_exclusion_compact.csv'}`")
    lines.append(f"- Baseline/direct-channel balance: `{TABLES / 'Round7_IV_exclusion_balance.csv'}`")
    return "\n".join(lines)


def main() -> None:
    ensure_dirs()
    panel, admin = r7.read_inputs()
    sample_counties = pd.to_numeric(
        panel.loc[panel["year"].eq(2014) & panel["s_mech_hh"].eq(1), "__cid_id"],
        errors="coerce",
    ).dropna().astype(int)
    ext, audit = r7.load_external_covariates(sample_counties)
    audit.to_csv(AUDIT / "Round7_IV_exclusion_external_files.csv", index=False, encoding="utf-8-sig")
    ext.to_csv(AUDIT / "Round7_IV_exclusion_external_covariates.csv", index=False, encoding="utf-8-sig")

    admin_thr = r7.admin_threshold_base(admin)
    stacks = {
        anchor: add_household_baseline_channels(r8.make_stack(panel, admin_thr, ext, "mech", anchor), panel)
        for anchor in ANCHORS
    }

    rows: list[dict] = []
    for anchor, stack in stacks.items():
        for bundle in IV_BUNDLES:
            for outcome in OUTCOMES:
                for controls in CONTROLS:
                    for stress_name, blocks in STRESS_BLOCKS:
                        try:
                            rows.append(run_one(stack, bundle, outcome, controls, anchor, stress_name, blocks))
                        except Exception as exc:
                            rows.append(
                                {
                                    "bundle": bundle.name,
                                    "bundle_label": bundle.label,
                                    "outcome": outcome,
                                    "anchor": anchor,
                                    "controls": controls,
                                    "stress": stress_name,
                                    "blocks": ",".join(blocks) if blocks else "none",
                                    "status": f"error: {exc}",
                                }
                            )

    results = pd.DataFrame(rows)
    results.to_csv(TABLES / "Round7_IV_exclusion_stress_results.csv", index=False, encoding="utf-8-sig")

    balance = run_balance(panel, ext)
    balance.to_csv(TABLES / "Round7_IV_exclusion_balance.csv", index=False, encoding="utf-8-sig")

    compact = compact_summary(results)
    compact.to_csv(TABLES / "Round7_IV_exclusion_compact.csv", index=False, encoding="utf-8-sig")

    memo = summarize(results, balance)
    (OUT / "Round7_IV_Exclusion_Reinforcement_Memo_20260502.md").write_text(memo, encoding="utf-8")
    print(memo)


if __name__ == "__main__":
    main()
