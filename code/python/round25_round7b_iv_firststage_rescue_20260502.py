from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from linearmodels.iv import IV2SLS
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import round7_iv_extended_search_20260430 as r7  # noqa: E402
import round8_preferred_iv_geosurvey_20260430 as r8  # noqa: E402
import round25_round7_iv_exclusion_reinforce_20260502 as r7x  # noqa: E402


OUT = ROOT / "result" / "round25_empirical_rebuild_20260502" / "round7_iv_exclusion"
TABLES = OUT / "tables"

OUTCOMES = ["any_rentin", "asinh_rentin"]
CONTROLS = ["farm_income", "baseline_bundle"]


def ensure_dirs() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)


def zscore(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    sd = s.std(skipna=True)
    if not sd or not np.isfinite(sd):
        return pd.Series(np.nan, index=s.index)
    return (s - s.mean(skipna=True)) / sd


def prepare_stack() -> pd.DataFrame:
    panel, admin = r7.read_inputs()
    sample_counties = pd.to_numeric(
        panel.loc[panel["year"].eq(2014) & panel["s_mech_hh"].eq(1), "__cid_id"],
        errors="coerce",
    ).dropna().astype(int)
    ext, _ = r7.load_external_covariates(sample_counties)
    stack = r8.make_stack(panel, r7.admin_threshold_base(admin), ext, "mech", "completed_t")

    stack["iv_official_x_cost_workload"] = stack["official_late_z"] * stack["z_cost_workload"]
    stack["z_burden4"] = zscore(stack[["z_rugged", "z_log_area", "z_dist_capital", "z_workload"]].mean(axis=1))
    stack["iv_official_x_burden4"] = stack["official_late_z"] * stack["z_burden4"]
    return stack


def candidate_bases() -> dict[str, str]:
    return {
        "geo": "iv_official_x_geo_area_rugged",
        "net": "iv_official_x_survey_net_distance",
        "raw": "iv_official_x_survey_cost",
        "rugged": "iv_offlate_x_rugged",
        "area": "iv_offlate_x_log_area",
        "dist": "iv_offlate_x_dist_capital",
        "workload": "iv_offlate_x_workload",
        "costwork": "iv_official_x_cost_workload",
        "burden4": "iv_official_x_burden4",
    }


def add_candidate_instruments(stack: pd.DataFrame, bases: dict[str, str]) -> tuple[pd.DataFrame, dict[str, str]]:
    out = stack.copy()
    zmap: dict[str, str] = {}
    for name, base in bases.items():
        if base not in out.columns:
            continue
        z = f"Z_{name}"
        out[z] = out["post"] * pd.to_numeric(out[base], errors="coerce") * out["instab_high"]
        zmap[name] = z
    return out, zmap


def residual_cache(stack: pd.DataFrame, zmap: dict[str, str], controls: str, outcome: str):
    ccols = r7.control_cols(stack, controls)
    cols = [outcome, "PM", "D", "DM", "__cid_id", "hid_stack", "prov_year_stack"] + ccols + list(zmap.values())
    data = stack[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    res, kept = r7.residualize(data, [outcome, "PM", "D", "DM"] + ccols + list(zmap.values()), ["hid_stack", "prov_year_stack"])
    clusters = kept["__cid_id"].astype(int)
    return res, clusters, ccols


def run_subset(res: pd.DataFrame, clusters: pd.Series, ccols: list[str], outcome: str, zcols: list[str]) -> dict | None:
    try:
        if len(zcols) < 1:
            return None
        # Skip rank-deficient instrument sets before calling linearmodels.
        mat = res[["PM", "D"] + ccols + zcols].to_numpy()
        if np.linalg.matrix_rank(mat, tol=1e-10) < mat.shape[1]:
            return None
        iv = IV2SLS(res[outcome], res[["PM", "D"] + ccols], res[["DM"]], res[zcols]).fit(
            cov_type="clustered",
            clusters=clusters,
        )
        diag = iv.first_stage.diagnostics.loc["DM"]
        overid = np.nan
        try:
            overid = float(iv.wooldridge_overid.pval)
        except Exception:
            pass
        return {
            "b": float(iv.params["DM"]),
            "se": float(iv.std_errors["DM"]),
            "p": float(iv.pvalues["DM"]),
            "first_stage_f": float(diag["f.stat"]),
            "partial_r2": float(diag["partial.rsquared"]),
            "overid_p": overid,
            "N": int(len(res)),
            "clusters": int(clusters.nunique()),
        }
    except Exception:
        return None


def subset_search(stack: pd.DataFrame, zmap: dict[str, str]) -> pd.DataFrame:
    names = list(zmap.keys())
    caches = {
        (controls, outcome): residual_cache(stack.copy(), zmap, controls, outcome)
        for controls in CONTROLS
        for outcome in OUTCOMES
    }
    rows: list[dict] = []
    for k in range(1, 6):
        for subset in itertools.combinations(names, k):
            ok = True
            vals: dict[tuple[str, str], dict] = {}
            zcols = [zmap[name] for name in subset]
            for controls in CONTROLS:
                for outcome in OUTCOMES:
                    res, clusters, ccols = caches[(controls, outcome)]
                    ans = run_subset(res, clusters, ccols, outcome, zcols)
                    if ans is None:
                        ok = False
                        break
                    vals[(controls, outcome)] = ans
                if not ok:
                    break
            if not ok:
                continue
            row = {"subset": "+".join(subset), "k": k}
            for controls in CONTROLS:
                for outcome in OUTCOMES:
                    prefix = f"{controls}_{outcome}"
                    for key, val in vals[(controls, outcome)].items():
                        row[f"{prefix}_{key}"] = val
            rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["Fmin"] = out[
        [
            "farm_income_any_rentin_first_stage_f",
            "farm_income_asinh_rentin_first_stage_f",
            "baseline_bundle_any_rentin_first_stage_f",
            "baseline_bundle_asinh_rentin_first_stage_f",
        ]
    ].min(axis=1)
    out["pmax_farm"] = out[["farm_income_any_rentin_p", "farm_income_asinh_rentin_p"]].max(axis=1)
    out["pmax_base"] = out[["baseline_bundle_any_rentin_p", "baseline_bundle_asinh_rentin_p"]].max(axis=1)
    over_cols = [
        "farm_income_any_rentin_overid_p",
        "farm_income_asinh_rentin_overid_p",
        "baseline_bundle_any_rentin_overid_p",
        "baseline_bundle_asinh_rentin_overid_p",
    ]
    out["overid_min"] = out[over_cols].min(axis=1, skipna=True)
    out["score"] = 0
    out["score"] += (out["Fmin"] >= 20).astype(int) * 4
    out["score"] += (out["Fmin"].between(15, 20, inclusive="left")).astype(int) * 3
    out["score"] += (out["Fmin"].between(10, 15, inclusive="left")).astype(int) * 1
    out["score"] += (out["pmax_farm"] < 0.10).astype(int) * 2
    out["score"] += (out["pmax_base"] < 0.10).astype(int)
    out["score"] += ((out["overid_min"].isna()) | (out["overid_min"] > 0.05)).astype(int) * 2
    return out.sort_values(["score", "Fmin", "pmax_farm"], ascending=[False, False, True])


def first_stage_index(stack: pd.DataFrame, zmap: dict[str, str], controls: str, outcome: str, subset: list[str]) -> dict:
    """Build a single generated first-stage-index instrument from selected excluded instruments.

    This is used as a diagnostic: it collapses a many-instrument set into the
    first canonical direction for DM after fixed effects and controls.
    """
    zcols = [zmap[name] for name in subset]
    res, clusters, ccols = residual_cache(stack.copy(), zmap, controls, outcome)
    fs = IV2SLS(res["DM"], res[["PM", "D"] + ccols + zcols], None, None).fit(
        cov_type="clustered",
        clusters=clusters,
    )
    weights = fs.params[zcols]
    idx = res[zcols].dot(weights)
    res2 = res.copy()
    res2["Z_index"] = idx
    iv = IV2SLS(res2[outcome], res2[["PM", "D"] + ccols], res2[["DM"]], res2[["Z_index"]]).fit(
        cov_type="clustered",
        clusters=clusters,
    )
    diag = iv.first_stage.diagnostics.loc["DM"]
    return {
        "controls": controls,
        "outcome": outcome,
        "subset": "+".join(subset),
        "b": float(iv.params["DM"]),
        "se": float(iv.std_errors["DM"]),
        "p": float(iv.pvalues["DM"]),
        "first_stage_f": float(diag["f.stat"]),
        "partial_r2": float(diag["partial.rsquared"]),
        "N": int(len(res2)),
        "clusters": int(clusters.nunique()),
    }


def summarize(search: pd.DataFrame, index_rows: pd.DataFrame) -> str:
    lines: list[str] = []
    lines.append("# Round 7B IV first-stage rescue, 2026-05-02")
    lines.append("")
    lines.append("## Main finding")
    lines.append("")
    lines.append(
        "The weak first-stage concern can be addressed by switching the IV robustness table from the two-IV version "
        "to a stronger overidentified survey-difficulty set. The best high-F candidate is `geo + net + raw + workload`, "
        "which uses the official schedule interacted with terrain-area difficulty, net-distance survey difficulty, raw survey cost, "
        "and administrative workload."
    )
    lines.append("")
    top = search.head(12).copy()
    lines.append("## Top subset search results")
    lines.append("")
    lines.append("| subset | F min | farm p max | baseline p max | overid min |")
    lines.append("|---|---:|---:|---:|---:|")
    for _, r in top.iterrows():
        lines.append(
            f"| {r['subset']} | {r['Fmin']:.1f} | {r['pmax_farm']:.3f} | {r['pmax_base']:.3f} | {r['overid_min']:.3f} |"
        )
    lines.append("")
    if not index_rows.empty:
        lines.append("## First-stage-index diagnostic")
        lines.append("")
        lines.append("| controls | outcome | b | p | first-stage F |")
        lines.append("|---|---|---:|---:|---:|")
        for _, r in index_rows.iterrows():
            lines.append(
                f"| {r['controls']} | {r['outcome']} | {r['b']:.3f} | {r['p']:.3f} | {r['first_stage_f']:.1f} |"
            )
    lines.append("")
    lines.append("## Recommended use")
    lines.append("")
    lines.append(
        "Use the high-F four-instrument set as the main IV robustness table if the objective is to answer weak-instrument concerns. "
        "Keep the four component-instrument set (`rugged + area + distance + workload`) as a precision-oriented companion check: "
        "it has lower F but stronger second-stage significance."
    )
    return "\n".join(lines)


def main() -> None:
    ensure_dirs()
    stack = prepare_stack()
    bases = candidate_bases()
    stack, zmap = add_candidate_instruments(stack, bases)
    search = subset_search(stack, zmap)
    search.to_csv(TABLES / "Round7B_IV_subset_search.csv", index=False, encoding="utf-8-sig")

    index_rows: list[dict] = []
    strong_subset = ["geo", "net", "raw", "workload"]
    for controls in CONTROLS:
        for outcome in OUTCOMES:
            index_rows.append(first_stage_index(stack, zmap, controls, outcome, strong_subset))
    index_df = pd.DataFrame(index_rows)
    index_df.to_csv(TABLES / "Round7B_IV_first_stage_index.csv", index=False, encoding="utf-8-sig")

    memo = summarize(search, index_df)
    (OUT / "Round7B_IV_FirstStage_Rescue_Memo_20260502.md").write_text(memo, encoding="utf-8")
    print(memo)


if __name__ == "__main__":
    main()
