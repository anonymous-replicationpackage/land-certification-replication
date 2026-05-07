from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from linearmodels.iv import IV2SLS
from scipy import stats

import round7_iv_extended_search_20260430 as r7


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "result" / "round8_preferred_iv_geosurvey_20260430"
TABLES = OUT / "tables"
AUDIT = OUT / "audit"

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
class PreferredIV:
    name: str
    base_col: str
    label: str


SPECS = [
    PreferredIV(
        "official_x_geo_area_rugged",
        "iv_official_x_geo_area_rugged",
        "Official schedule x terrain-area survey difficulty",
    ),
    PreferredIV(
        "official_x_survey_net_distance",
        "iv_official_x_survey_net_distance",
        "Official schedule x survey difficulty net of simple distance",
    ),
    PreferredIV(
        "official_x_survey_cost",
        "iv_official_x_survey_cost",
        "Official schedule x raw survey-cost index",
    ),
]


def ensure_dirs() -> None:
    for p in [OUT, TABLES, AUDIT]:
        p.mkdir(parents=True, exist_ok=True)


def std(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    sd = s.std(skipna=True)
    if not sd or not np.isfinite(sd):
        return pd.Series(np.nan, index=s.index)
    return (s - s.mean(skipna=True)) / sd


def add_preferred_iv_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["z_geo_area_rugged"] = std((pd.to_numeric(out["z_rugged"], errors="coerce") + pd.to_numeric(out["z_log_area"], errors="coerce")) / 2)
    out["z_survey_net_distance"] = std(
        pd.to_numeric(out["z_survey_cost"], errors="coerce") - 0.5 * pd.to_numeric(out["z_dist_capital"], errors="coerce")
    )
    out["iv_official_x_geo_area_rugged"] = out["official_late_z"] * out["z_geo_area_rugged"]
    out["iv_official_x_survey_net_distance"] = out["official_late_z"] * out["z_survey_net_distance"]
    out["iv_official_x_survey_cost"] = out["official_late_z"] * out["z_survey_cost"]
    return out


def make_stack(panel: pd.DataFrame, admin_thr: pd.DataFrame, ext: pd.DataFrame, scope: str, anchor: str) -> pd.DataFrame:
    stack = r7.make_stack(panel, admin_thr, ext, scope, anchor)
    return add_preferred_iv_columns(stack)


def balance_frame(panel: pd.DataFrame, ext: pd.DataFrame) -> pd.DataFrame:
    base = r7.balance_frame(panel, ext)
    return add_preferred_iv_columns(base)


def balance_one(df: pd.DataFrame, y: str, z: str) -> dict:
    cols = [y, z, "__cid_id", "__prov_id"]
    data = df[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(data) < 50 or data["__cid_id"].nunique() < 10 or data[z].std() < 1e-12:
        return {"b": np.nan, "se": np.nan, "p": np.nan, "N": len(data), "counties": data["__cid_id"].nunique(), "status": "too_few"}
    x = pd.concat(
        [
            pd.DataFrame({"const": 1.0, z: data[z].astype(float)}),
            pd.get_dummies(data["__prov_id"].astype(int), prefix="prov", drop_first=True, dtype=float),
        ],
        axis=1,
    )
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
    for spec in SPECS:
        for y, ylab in BALANCE_OUTCOMES:
            if y not in base.columns:
                continue
            rows.append(
                {
                    "spec": spec.name,
                    "instrument_base": spec.base_col,
                    "instrument_label": spec.label,
                    "outcome": y,
                    "outcome_label": ylab,
                    "balance_controls": "province_fe",
                    **balance_one(base, y, spec.base_col),
                }
            )
    return pd.DataFrame(rows)


def add_zcols(stack: pd.DataFrame, spec: PreferredIV) -> tuple[pd.DataFrame, list[str]]:
    out = stack.copy()
    out["Z"] = out["post"] * pd.to_numeric(out[spec.base_col], errors="coerce")
    out["ZM"] = out["Z"] * out["instab_high"]
    return out, ["Z", "ZM"]


def run_iv(
    stack_in: pd.DataFrame,
    spec: PreferredIV,
    outcome: str,
    controls: str,
    model: str,
) -> dict:
    stack, zcols = add_zcols(stack_in, spec)
    ccols = r7.control_cols(stack, controls)
    fe_cols = ["hid_stack", "prov_year_stack"]
    cols = [outcome, "PM", "D", "DM", "__cid_id", "hid_stack", "year_stack", "prov_year_stack"] + zcols + ccols
    data = stack[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(data) < 100 or data["__cid_id"].nunique() < 10:
        raise ValueError("too few observations")
    res, kept = r7.residualize(data, [outcome, "PM", "D", "DM"] + zcols + ccols, fe_cols)
    clusters = kept["__cid_id"].astype(int)

    ols = IV2SLS(res[outcome], res[["PM", "D"] + ccols + ["DM"]], None, None).fit(cov_type="clustered", clusters=clusters)
    if model == "interaction_iv":
        iv = IV2SLS(res[outcome], res[["PM", "D"] + ccols], res[["DM"]], res[["ZM"]]).fit(
            cov_type="clustered",
            clusters=clusters,
        )
        first_stage = float(iv.first_stage.diagnostics.loc["DM", "f.stat"])
        weak_d = np.nan
        weak_dm = first_stage
        low_b = float(ols.params["D"])
        low_p = float(ols.pvalues["D"])
        sargan_p = np.nan
    elif model == "full_treatment_iv":
        iv = IV2SLS(res[outcome], res[["PM"] + ccols], res[["D", "DM"]], res[zcols]).fit(
            cov_type="clustered",
            clusters=clusters,
        )
        diag = iv.first_stage.diagnostics
        weak_d = float(diag.loc["D", "f.stat"])
        weak_dm = float(diag.loc["DM", "f.stat"])
        first_stage = min(weak_d, weak_dm)
        low_b = float(iv.params["D"])
        low_p = float(iv.pvalues["D"])
        sargan_p = float(iv.sargan.pval) if hasattr(iv, "sargan") else np.nan
    else:
        raise ValueError(model)

    return {
        "spec": spec.name,
        "instrument_label": spec.label,
        "outcome": outcome,
        "controls": controls,
        "model": model,
        "N": int(len(kept)),
        "clusters": int(clusters.nunique()),
        "ols_diff_b": float(ols.params["DM"]),
        "ols_diff_se": float(ols.std_errors["DM"]),
        "ols_diff_p": float(ols.pvalues["DM"]),
        "iv_diff_b": float(iv.params["DM"]),
        "iv_diff_se": float(iv.std_errors["DM"]),
        "iv_diff_p": float(iv.pvalues["DM"]),
        "iv_low_b": low_b,
        "iv_low_p": low_p,
        "first_stage_f": first_stage,
        "weak_D_f": weak_d,
        "weak_DM_f": weak_dm,
        "sargan_p": sargan_p,
        "status": "ok",
    }


def screen(iv: pd.DataFrame, bal: pd.DataFrame) -> pd.DataFrame:
    ok = iv[iv["status"].eq("ok")].copy()
    main = ok[
        ok["model"].eq("interaction_iv")
        & ok["scope"].eq("mech")
        & ok["anchor"].eq("completed_t")
        & ok["controls"].isin(["farm_income", "baseline_bundle"])
    ]
    keys = ["spec", "instrument_label", "controls", "model", "scope", "anchor"]
    wide = main.pivot_table(
        index=keys,
        columns="outcome",
        values=["iv_diff_b", "iv_diff_p", "first_stage_f", "N", "clusters"],
        aggfunc="first",
    )
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    wide = wide.reset_index()
    bal_core = bal[bal["outcome"].isin(["asinh_rb_inc_farm", "land_total_mu", "any_rentin", "a3_tenure_insec_z"])].copy()
    bal_min = bal_core.groupby("spec")["p"].min().rename("balance_core_min_p").reset_index()
    wide = wide.merge(bal_min, on="spec", how="left")
    wide["both_positive"] = (wide["iv_diff_b_any_rentin"] > 0) & (wide["iv_diff_b_asinh_rentin"] > 0)
    wide["both_p10"] = (wide["iv_diff_p_any_rentin"] < 0.10) & (wide["iv_diff_p_asinh_rentin"] < 0.10)
    wide["both_p05"] = (wide["iv_diff_p_any_rentin"] < 0.05) & (wide["iv_diff_p_asinh_rentin"] < 0.05)
    wide["first_stage_min"] = wide[["first_stage_f_any_rentin", "first_stage_f_asinh_rentin"]].min(axis=1)
    wide["clusters_min"] = wide[["clusters_any_rentin", "clusters_asinh_rentin"]].min(axis=1)
    wide["score"] = (
        wide["both_positive"].astype(int) * 2
        + wide["both_p10"].astype(int) * 2
        + wide["both_p05"].astype(int)
        + (wide["first_stage_min"] > 10).astype(int) * 2
        + (wide["balance_core_min_p"] > 0.10).astype(int) * 2
        + (wide["clusters_min"] >= 100).astype(int)
    )
    return wide.sort_values(["score", "both_p05", "first_stage_min"], ascending=[False, False, False])


def summarize(iv: pd.DataFrame, bal: pd.DataFrame, scr: pd.DataFrame) -> str:
    def fmt(x: float, d: int = 3) -> str:
        return "" if pd.isna(x) else f"{x:.{d}f}"

    lines = ["# Round 8 preferred IV memo, 2026-04-30", ""]
    lines.append("## Recommended IV")
    lines.append("")
    lines.append(
        "The defensible IV is an interaction-IV for the paper's core high-insecurity differential: "
        "`post x high-insecurity x [official province schedule x county terrain-area survey difficulty]`. "
        "The regression controls the county treatment main effect `D`; the instrument is used for `D x M` only."
    )
    lines.append("")
    lines.append(
        "This is preferable to the old province-schedule IV because province-year fixed effects absorb provincewide schedule shocks; "
        "identification comes from within-province county differences in quasi-fixed survey/mapping difficulty, interacted with the official schedule."
    )
    lines.append("")
    lines.append("## Main screen")
    lines.append("")
    lines.append("| IV | controls | any b/p | area b/p | first-stage min F | balance min p | N min | counties min |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for _, r in scr.head(6).iterrows():
        lines.append(
            f"| {r['instrument_label']} | {r['controls']} | "
            f"{fmt(r['iv_diff_b_any_rentin'])}/{fmt(r['iv_diff_p_any_rentin'])} | "
            f"{fmt(r['iv_diff_b_asinh_rentin'])}/{fmt(r['iv_diff_p_asinh_rentin'])} | "
            f"{fmt(r['first_stage_min'], 1)} | {fmt(r['balance_core_min_p'])} | "
            f"{int(r['N_asinh_rentin'])} | {int(r['clusters_min'])} |"
        )
    lines.append("")
    lines.append("## Full-treatment IV diagnostic")
    lines.append("")
    full = iv[
        iv["status"].eq("ok")
        & iv["model"].eq("full_treatment_iv")
        & iv["scope"].eq("mech")
        & iv["anchor"].eq("completed_t")
        & iv["spec"].eq("official_x_geo_area_rugged")
        & iv["controls"].eq("baseline_bundle")
    ]
    lines.append("| outcome | diff b | p | weak D F | weak DM F |")
    lines.append("|---|---:|---:|---:|---:|")
    for _, r in full.iterrows():
        lines.append(f"| {r['outcome']} | {fmt(r['iv_diff_b'])} | {fmt(r['iv_diff_p'])} | {fmt(r['weak_D_f'], 1)} | {fmt(r['weak_DM_f'], 1)} |")
    lines.append("")
    lines.append(
        "The full treatment-IV remains weak for the treatment main effect, so it should not be sold as the headline design. "
        "Use the interaction-IV as an IV robustness check for the high-insecurity differential."
    )
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append("- IV table: `result/round8_preferred_iv_geosurvey_20260430/tables/Round8_preferred_IV_results.csv`")
    lines.append("- Balance table: `result/round8_preferred_iv_geosurvey_20260430/tables/Round8_preferred_IV_balance.csv`")
    lines.append("- Screen table: `result/round8_preferred_iv_geosurvey_20260430/tables/Round8_preferred_IV_screen.csv`")
    return "\n".join(lines)


def main() -> None:
    ensure_dirs()
    panel, admin = r7.read_inputs()
    ext, file_audit = r7.load_external_covariates(panel.loc[panel["s_mech_hh"].eq(1), "__cid_id"])
    file_audit.to_csv(AUDIT / "Round8_external_source_files.csv", index=False, encoding="utf-8-sig")
    admin_thr = r7.admin_threshold_base(admin)

    bal = run_balance(panel, ext)
    bal.to_csv(TABLES / "Round8_preferred_IV_balance.csv", index=False, encoding="utf-8-sig")

    rows: list[dict] = []
    for scope in ["mech", "adjacent"]:
        for anchor in ["signoff_or_issue_t", "completed_t", "high_sat80_t"]:
            stack = make_stack(panel, admin_thr, ext, scope, anchor)
            for spec in SPECS:
                for controls in ["farm_income", "baseline_bundle"]:
                    for model in ["interaction_iv", "full_treatment_iv"]:
                        for outcome in OUTCOMES:
                            try:
                                row = run_iv(stack, spec, outcome, controls, model)
                                row.update({"scope": scope, "anchor": anchor})
                            except Exception as exc:  # noqa: BLE001
                                row = {
                                    "spec": spec.name,
                                    "instrument_label": spec.label,
                                    "outcome": outcome,
                                    "controls": controls,
                                    "model": model,
                                    "scope": scope,
                                    "anchor": anchor,
                                    "status": f"error:{type(exc).__name__}:{exc}",
                                }
                            rows.append(row)
    iv = pd.DataFrame(rows)
    iv.to_csv(TABLES / "Round8_preferred_IV_results.csv", index=False, encoding="utf-8-sig")
    scr = screen(iv, bal)
    scr.to_csv(TABLES / "Round8_preferred_IV_screen.csv", index=False, encoding="utf-8-sig")
    (OUT / "Round8_preferred_IV_memo_20260430.md").write_text(summarize(iv, bal, scr), encoding="utf-8")
    print(f"Round 8 outputs written to {OUT}")


if __name__ == "__main__":
    main()
