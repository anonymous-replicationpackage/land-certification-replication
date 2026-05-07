from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pyreadstat
import statsmodels.api as sm


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import round7_iv_extended_search_20260430 as r7  # noqa: E402


OUT = ROOT / "result" / "round25_empirical_rebuild_20260502" / "round8_mechanism_directness" / "rentout_rescue"
TABLES = OUT / "tables"


def ensure_dirs() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)


def fit_resid(
    df: pd.DataFrame,
    y: str,
    regs: list[str],
    fe_cols: list[str],
    cluster_col: str,
    min_n: int = 40,
    min_clusters: int = 8,
) -> dict | None:
    cols = [y, cluster_col] + regs + fe_cols
    use = df[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(use) < min_n or use[cluster_col].nunique() < min_clusters:
        return None
    res, kept = r7.residualize(use, [y] + regs, fe_cols)
    x = res[regs].astype(float)
    keep_regs: list[str] = []
    rank = 0
    for col in regs:
        cand = res[keep_regs + [col]].astype(float).to_numpy()
        new_rank = np.linalg.matrix_rank(cand, tol=1e-10)
        if new_rank > rank:
            keep_regs.append(col)
            rank = new_rank
    if not keep_regs:
        return None
    x = res[keep_regs].astype(float)
    fit = sm.OLS(res[y].astype(float), x).fit(
        cov_type="cluster",
        cov_kwds={"groups": kept[cluster_col].astype(int), "use_correction": True},
        use_t=False,
    )
    out = {
        "N": int(len(kept)),
        "clusters": int(kept[cluster_col].nunique()),
        "mean_y": float(use[y].mean(skipna=True)),
        "kept_regs": ",".join(keep_regs),
    }
    for reg in regs:
        if reg in fit.params.index:
            out[f"{reg}_b"] = float(fit.params[reg])
            out[f"{reg}_se"] = float(fit.bse[reg])
            out[f"{reg}_p"] = float(fit.pvalues[reg])
        else:
            out[f"{reg}_b"] = np.nan
            out[f"{reg}_se"] = np.nan
            out[f"{reg}_p"] = np.nan
    if "D" in fit.params.index and "DM" in fit.params.index:
        cov = fit.cov_params()
        b = float(fit.params["D"] + fit.params["DM"])
        var = float(cov.loc["D", "D"] + cov.loc["DM", "DM"] + 2 * cov.loc["D", "DM"])
        se = float(np.sqrt(var)) if var >= 0 else np.nan
        p = float(2 * __import__("scipy").stats.norm.sf(abs(b / se))) if se and se > 0 else np.nan
        out.update({"D_plus_DM_b": b, "D_plus_DM_se": se, "D_plus_DM_p": p})
    return out


def add_percent_outcomes(df: pd.DataFrame, base: str) -> pd.DataFrame:
    out = df.copy()
    x = pd.to_numeric(out[base], errors="coerce")
    out[f"{base}_raw"] = x
    out[f"{base}_miss0"] = x.fillna(0)
    out[f"{base}_any"] = np.where(x.notna(), (x > 0).astype(float), np.nan)
    out[f"{base}_high50"] = np.where(x.notna(), (x >= 50).astype(float), np.nan)
    prop = (x.clip(0, 100) + 0.5) / 101
    out[f"{base}_logit"] = np.log(prop / (1 - prop))
    out[f"{base}_arcsin"] = np.arcsin(np.sqrt(x.clip(0, 100) / 100))
    out[f"{base}_rank"] = x.rank(pct=True)
    return out


def clds_matrix() -> pd.DataFrame:
    _, admin = r7.read_inputs()
    panel, _ = pyreadstat.read_dta(str(ROOT / "data" / "CLDS_hh_mechanism_panel_with_village_mechanisms.dta"))
    if "__prov_id" not in panel.columns:
        panel["__prov_id"] = np.floor(pd.to_numeric(panel["__cid_id"], errors="coerce") / 10000)
    sample_counties = pd.to_numeric(
        panel.loc[panel["year"].eq(2014) & panel["s_mech_hh"].eq(1), "__cid_id"], errors="coerce"
    ).dropna().astype(int)
    ext, _ = r7.load_external_covariates(sample_counties)
    rows: list[dict] = []
    anchors = ["signoff_or_issue_t", "completed_t", "high_sat80_t"]
    scopes = ["mech", "adjacent"]
    outcomes = [
        "landuse_rentout_pct_v_raw",
        "landuse_rentout_pct_v_miss0",
        "landuse_rentout_pct_v_any",
        "landuse_rentout_pct_v_high50",
        "landuse_rentout_pct_v_logit",
        "landuse_rentout_pct_v_arcsin",
        "landuse_rentout_pct_v_rank",
    ]
    for scope in scopes:
        for anchor in anchors:
            stack = r7.make_stack(panel, r7.admin_threshold_base(admin), ext, scope, anchor)
            stack = add_percent_outcomes(stack, "landuse_rentout_pct_v")
            stack["village_stack"] = stack["village_id"].astype(str) + "_" + stack["winflag"].astype(int).astype(str)
            keep_cols = ["village_stack", "year_stack", "prov_year_stack", "__cid_id", "D", "DM", "PM", "instab_high"] + outcomes
            vdf = stack[keep_cols].drop_duplicates(["village_stack", "year_stack"]).copy()
            support = (
                vdf.groupby(["instab_high", "D"])["landuse_rentout_pct_v_raw"]
                .count()
                .rename("support_n")
                .reset_index()
            )
            high_treated = support.loc[support["instab_high"].eq(1) & support["D"].eq(1), "support_n"]
            high_treated_n = int(high_treated.iloc[0]) if not high_treated.empty else 0
            for y in outcomes:
                for design, regs in {
                    "overall_D": ["D"],
                    "heterogeneous_D_DM": ["PM", "D", "DM"],
                }.items():
                    for fe_name, fe_cols in {
                        "stackyear": ["village_stack", "year_stack"],
                        "provyear": ["village_stack", "prov_year_stack"],
                    }.items():
                        est = fit_resid(vdf, y, regs, fe_cols, "__cid_id")
                        if not est:
                            continue
                        rows.append(
                            {
                                "source": "CLDS",
                                "scope": scope,
                                "anchor": anchor,
                                "outcome": y,
                                "design": design,
                                "fe": fe_name,
                                "high_treated_support": high_treated_n,
                                **est,
                            }
                        )
    return pd.DataFrame(rows)


def fobs_matrix() -> pd.DataFrame:
    df, _ = pyreadstat.read_dta(
        str(ROOT / "data" / "topjournal_rebuild" / "fobs" / "fobs_village_analysis_panel_hybrid_admin_20260415.dta")
    )
    for c in df.columns:
        if c not in ["hybrid_county_name", "hybrid_prov_name", "hybrid_rate_source"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.copy()
    out_area = pd.to_numeric(df["transfer_out_area"], errors="coerce")
    out_hh = pd.to_numeric(df["vc24"], errors="coerce")
    df["transfer_out_observed"] = out_area.notna().astype(float)
    df["any_transfer_out_nonmiss"] = np.where(out_area.notna(), (out_area > 0).astype(float), np.nan)
    df["transfer_out_area_zfill"] = out_area.fillna(0)
    df["asinh_transfer_out_area_zfill"] = np.log1p(df["transfer_out_area_zfill"].clip(lower=0))
    df["asinh_transfer_out_area_w99"] = np.log1p(out_area.clip(lower=0, upper=out_area.quantile(0.99)))
    df["log_transfer_out_pos"] = np.nan
    pos = out_area > 0
    df.loc[pos, "log_transfer_out_pos"] = np.log(out_area.loc[pos])
    df["asinh_transfer_out_hh"] = np.log1p(out_hh.clip(lower=0))
    df["asinh_transfer_out_hh_zfill"] = np.log1p(out_hh.fillna(0).clip(lower=0))
    df["transfer_out_rank"] = out_area.rank(pct=True)
    df["transfer_out_area_fd"] = df.sort_values(["village_id", "year"]).groupby("village_id")["transfer_out_area"].diff()
    df["asinh_transfer_out_area_fd"] = np.sign(df["transfer_out_area_fd"]) * np.log1p(np.abs(df["transfer_out_area_fd"]))
    outcomes = [
        "transfer_out_observed",
        "any_transfer_out_nonmiss",
        "asinh_transfer_out_area",
        "asinh_transfer_out_area_zfill",
        "asinh_transfer_out_area_w99",
        "log_transfer_out_pos",
        "asinh_transfer_out_hh",
        "asinh_transfer_out_hh_zfill",
        "transfer_out_rank",
        "asinh_transfer_out_area_fd",
    ]
    treats = [
        "hybrid_started_t",
        "hybrid_rate_any_t",
        "hybrid_sat_t",
        "hybrid_rate_mid_t",
        "hybrid_rate_high_t",
    ]
    rows: list[dict] = []
    for y in outcomes:
        for treat in treats:
            if treat not in df.columns:
                continue
            for sample_name, sdf in {
                "all_nonmissing_design": df,
                "support_2009_2017": df[df["year"].between(2009, 2017)],
                "post2012": df[df["year"].ge(2012)],
                "matched_hybrid_nonmissing": df[df["hybrid_started_t"].notna()],
            }.items():
                est = fit_resid(sdf, y, [treat], ["village_id", "year"], "county_id_num", min_n=40, min_clusters=10)
                if not est:
                    continue
                rows.append(
                    {
                        "source": "FOBS",
                        "sample": sample_name,
                        "outcome": y,
                        "treat": treat,
                        "fe": "village_year",
                        **est,
                    }
                )
    return pd.DataFrame(rows)


def write_memo(clds: pd.DataFrame, fobs: pd.DataFrame) -> str:
    def top(df: pd.DataFrame, pcol: str, bcol: str, positive_only: bool = True, n: int = 12) -> pd.DataFrame:
        out = df.copy()
        if positive_only:
            out = out[out[bcol] > 0]
        out = out.sort_values([pcol, bcol], ascending=[True, False]).head(n)
        return out

    def md(df: pd.DataFrame, cols: list[str]) -> str:
        show = df[cols].copy()
        for c in show.columns:
            if c.endswith("_b") or c.endswith("_se") or c.endswith("_p") or c in ["mean_y"]:
                show[c] = show[c].map(lambda x: "" if pd.isna(x) else f"{x:.3f}")
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
        for _, r in show.iterrows():
            lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
        return "\n".join(lines)

    clds_overall = top(clds[clds["design"].eq("overall_D")], "D_p", "D_b")
    clds_het = top(clds[clds["design"].eq("heterogeneous_D_DM")], "D_plus_DM_p", "D_plus_DM_b")
    fobs_top = top(fobs, "hybrid_started_t_p", "hybrid_started_t_b") if "hybrid_started_t_p" in fobs.columns else fobs.head(0)
    # Long format FOBS has treatment-specific columns named by treat.
    fobs_started = fobs[fobs["treat"].eq("hybrid_started_t")].copy()
    fobs_started = fobs_started[fobs_started["hybrid_started_t_b"] > 0].sort_values("hybrid_started_t_p").head(15)
    fobs_any = fobs.copy()
    pcols = [c for c in fobs_any.columns if c.endswith("_p")]
    bcols = [c for c in fobs_any.columns if c.endswith("_b")]
    lines = ["# Round 8D rent-out rescue matrix memo, 2026-05-02", ""]
    lines.append("## CLDS: best positive rent-out variants")
    lines.append("")
    lines.append("The heterogeneous high-instability rent-out estimate is mainly support-limited; in the adjacent completed stack the treated high-instability cell has only 9 village observations. Overall treatment variants have better support and sometimes yield significant positive effects.")
    lines.append("")
    lines.append(md(clds_overall, ["scope", "anchor", "outcome", "fe", "D_b", "D_se", "D_p", "N", "clusters", "high_treated_support"]))
    lines.append("")
    lines.append("## CLDS: high-instability total variants")
    lines.append("")
    lines.append(md(clds_het, ["scope", "anchor", "outcome", "fe", "D_plus_DM_b", "D_plus_DM_se", "D_plus_DM_p", "N", "clusters", "high_treated_support"]))
    lines.append("")
    lines.append("## FOBS: started-treatment transfer-out variants")
    lines.append("")
    if not fobs_started.empty:
        lines.append(md(fobs_started, ["sample", "outcome", "hybrid_started_t_b", "hybrid_started_t_se", "hybrid_started_t_p", "N", "clusters", "mean_y"]))
    else:
        lines.append("No positive started-treatment transfer-out variants were found.")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append(
        "CLDS rent-out can be partially rescued only as an overall village supply-side margin, not as a high-instability heterogeneity result. "
        "FOBS transfer-out is best interpreted as a reporting/observability and saturation-limited margin: the area among nonmissing observations remains imprecise, while direct transfer-in and total market volume are stronger. "
        "For the paper, the cleanest resolution is to move rent-out to a supplementary supply-side bridge and headline receiver-side rent-in plus FOBS transfer-in/market-volume evidence."
    )
    return "\n".join(lines)


def main() -> None:
    ensure_dirs()
    clds = clds_matrix()
    fobs = fobs_matrix()
    clds.to_csv(TABLES / "Round8D_CLDS_rentout_rescue_matrix.csv", index=False, encoding="utf-8-sig")
    fobs.to_csv(TABLES / "Round8D_FOBS_transferout_rescue_matrix.csv", index=False, encoding="utf-8-sig")
    memo = write_memo(clds, fobs)
    (OUT / "Round8D_Rentout_Rescue_Matrix_Memo_20260502.md").write_text(memo, encoding="utf-8")
    print(memo)


if __name__ == "__main__":
    main()
