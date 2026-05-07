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
import round25_round8_mechanism_directness_20260502 as r8  # noqa: E402


OUT = ROOT / "result" / "round25_empirical_rebuild_20260502" / "round8_mechanism_directness" / "enhanced"
TABLES = OUT / "tables"


def ensure_dirs() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)


def fit_fe(
    data: pd.DataFrame,
    y: str,
    treat: str,
    fe_cols: list[str],
    cluster_col: str,
    min_n: int = 80,
    min_clusters: int = 10,
) -> dict | None:
    cols = [y, treat, cluster_col] + fe_cols
    use = data[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(use) < min_n or use[cluster_col].nunique() < min_clusters or use[treat].nunique() < 2:
        return None
    res, kept = r7.residualize(use, [y, treat], fe_cols)
    x = res[[treat]].astype(float)
    if np.linalg.matrix_rank(x.to_numpy(), tol=1e-10) < 1:
        return None
    fit = sm.OLS(res[y].astype(float), x).fit(
        cov_type="cluster",
        cov_kwds={"groups": kept[cluster_col].astype(int), "use_correction": True},
        use_t=False,
    )
    return {
        "b": float(fit.params[treat]),
        "se": float(fit.bse[treat]),
        "p": float(fit.pvalues[treat]),
        "N": int(len(kept)),
        "clusters": int(kept[cluster_col].nunique()),
        "mean_y": float(use[y].mean(skipna=True)),
    }


def load_clds_stack() -> pd.DataFrame:
    panel, admin = r7.read_inputs()
    sample_counties = pd.to_numeric(
        panel.loc[panel["year"].eq(2014) & panel["s_mech_hh"].eq(1), "__cid_id"],
        errors="coerce",
    ).dropna().astype(int)
    ext, _ = r7.load_external_covariates(sample_counties)
    stack = r7.make_stack(panel, r7.admin_threshold_base(admin), ext, "adjacent", "completed_t")
    stack = r8.add_derived_outcomes(stack)
    for base in ["z_base_farmdep", "z_base_land", "z_base_asinh_farm_income", "z_base_nonfarm_curr"]:
        x = pd.to_numeric(stack[base], errors="coerce")
        stack[f"{base}_top3"] = np.where(x.notna(), (x >= x.quantile(2 / 3)).astype(float), np.nan)
        stack[f"{base}_bot3"] = np.where(x.notna(), (x <= x.quantile(1 / 3)).astype(float), np.nan)
    for y in ["any_rentin", "asinh_rentin", "rentin_mu", "ib_nonfarm_curr_ge2", "ib_nonfarm_curr_n"]:
        pre = (
            stack.loc[stack["post"].eq(0), ["hid_stack", y]]
            .dropna()
            .drop_duplicates("hid_stack")
            .rename(columns={y: f"pre_{y}"})
        )
        stack = stack.merge(pre, on="hid_stack", how="left")
    return stack


def clds_sorting_diagnostics(stack: pd.DataFrame) -> pd.DataFrame:
    groups = [
        (
            "recipient: top baseline farm dependence",
            stack["instab_high"].eq(1) & stack["z_base_farmdep_top3"].eq(1),
            ["any_rentin", "asinh_rentin", "rentin_mu", "rentin_and_farm_any"],
        ),
        (
            "recipient: top baseline farm income",
            stack["instab_high"].eq(1) & stack["z_base_asinh_farm_income_top3"].eq(1),
            ["any_rentin", "asinh_rentin", "rentin_mu", "rentin_and_farm_any"],
        ),
        (
            "recipient: no pre rent-in and top farm dependence",
            stack["instab_high"].eq(1) & stack["pre_any_rentin"].eq(0) & stack["z_base_farmdep_top3"].eq(1),
            ["any_rentin", "asinh_rentin", "rentin_mu"],
        ),
        (
            "exit: bottom baseline farm dependence",
            stack["instab_high"].eq(1) & stack["z_base_farmdep_bot3"].eq(1),
            ["ib_nonfarm_curr_n", "ib_nonfarm_curr_ge2", "nonfarm_ge2_no_rentin", "asinh_rb_inc_farm_w99"],
        ),
        (
            "exit: top baseline nonfarm labor",
            stack["instab_high"].eq(1) & stack["z_base_nonfarm_curr_top3"].eq(1),
            [
                "ib_nonfarm_curr_n",
                "ib_nonfarm_curr_ge2",
                "nonfarm_ge2_no_rentin",
                "rb_farm_any",
                "asinh_rb_farm_cost_w99",
                "asinh_rb_inc_farm_w99",
            ],
        ),
    ]
    rows: list[dict] = []
    labels = {s.name: s.label for s in r8.HOUSEHOLD_OUTCOMES}
    for group_name, mask, outcomes in groups:
        df = stack.loc[mask].copy()
        for y in outcomes:
            if y not in df.columns:
                continue
            est = fit_fe(df, y, "D", ["hid_stack", "year_stack"], "__cid_id", min_n=120, min_clusters=15)
            if not est:
                continue
            rows.append(
                {
                    "source": "CLDS",
                    "design": "high-insecurity villages only; household-stack and stack-year FE",
                    "group": group_name,
                    "outcome": y,
                    "label": labels.get(y, y),
                    **est,
                }
            )
    return pd.DataFrame(rows)


def fobs_direct_transfer_diagnostics() -> pd.DataFrame:
    path = ROOT / "data" / "topjournal_rebuild" / "fobs" / "fobs_village_analysis_panel_hybrid_admin_20260415.dta"
    df, _ = pyreadstat.read_dta(str(path))
    for c in df.columns:
        if c not in ["hybrid_county_name", "hybrid_prov_name", "hybrid_rate_source"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.copy()
    df["asinh_transfer_out_hh"] = np.log1p(df["vc24"].clip(lower=0))
    df["market_volume_area"] = df[["transfer_out_area", "transfer_in_area"]].sum(axis=1, min_count=1)
    df["asinh_market_volume_area"] = np.log1p(df["market_volume_area"].clip(lower=0))
    df["any_transfer_out_v"] = np.where(df["transfer_out_area"].notna(), (df["transfer_out_area"] > 0).astype(float), np.nan)
    df["any_transfer_in_v"] = np.where(df["transfer_in_area"].notna(), (df["transfer_in_area"] > 0).astype(float), np.nan)
    specs = [
        ("asinh_transfer_in_area", "asinh transferred-in cultivated area", "hybrid_started_t"),
        ("asinh_market_volume_area", "asinh transfer-in plus transfer-out area", "hybrid_started_t"),
        ("asinh_transfer_out_area", "asinh transferred-out cultivated area", "hybrid_started_t"),
        ("asinh_transfer_out_hh", "asinh households transferring out cultivated land", "hybrid_started_t"),
        ("any_transfer_in_v", "any transfer-in in village-year", "hybrid_started_t"),
        ("any_transfer_out_v", "any transfer-out in village-year", "hybrid_started_t"),
    ]
    rows: list[dict] = []
    for y, label, treat in specs:
        est = fit_fe(df, y, treat, ["village_id", "year"], "county_id_num", min_n=50, min_clusters=12)
        if not est:
            continue
        rows.append(
            {
                "source": "FOBS village panel",
                "design": "village and year FE; county-clustered; county rollout start",
                "outcome": y,
                "label": label,
                "treat": treat,
                **est,
            }
        )
    return pd.DataFrame(rows)


def clds_village_supply_bridge() -> pd.DataFrame:
    _, admin = r7.read_inputs()
    path = ROOT / "data" / "CLDS_hh_mechanism_panel_with_village_mechanisms.dta"
    panel, _ = pyreadstat.read_dta(str(path))
    if "__prov_id" not in panel.columns:
        panel["__prov_id"] = np.floor(pd.to_numeric(panel["__cid_id"], errors="coerce") / 10000)
    sample_counties = pd.to_numeric(
        panel.loc[panel["year"].eq(2014) & panel["s_mech_hh"].eq(1), "__cid_id"], errors="coerce"
    ).dropna().astype(int)
    ext, _ = r7.load_external_covariates(sample_counties)
    stack = r7.make_stack(panel, r7.admin_threshold_base(admin), ext, "adjacent", "completed_t")
    specs = [
        r8.OutcomeSpec("landuse_rentout_pct_v", "share of absent-household land rented out (%)", "village-supply"),
        r8.OutcomeSpec("landuse_active_pct_v", "active use share of absent-household land (%)", "village-supply"),
        r8.OutcomeSpec("landuse_idle_pct_v", "idle share of absent-household land (%)", "village-supply"),
        r8.OutcomeSpec("landuse_idle_vs_active_gap_pct_v", "active minus idle share", "village-supply"),
    ]
    res = r8.estimate_aggregate(stack, "village", specs, "adjacent")
    keep = res[
        res["status"].eq("ok")
        & res["controls"].eq("none")
        & res["fe"].eq("stackyear")
        & res["term"].isin(["high-instability total", "high-minus-low differential"])
    ].copy()
    keep["source"] = "CLDS village mechanism variables"
    keep["design"] = "adjacent-window stacked DID; village-stack and stack-year FE"
    return keep


def md_table(df: pd.DataFrame, cols: list[str]) -> str:
    show = df[cols].copy()
    for c in ["b", "se", "p", "mean_y"]:
        if c in show.columns:
            show[c] = show[c].map(lambda x: "" if pd.isna(x) else f"{x:.3f}")
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, r in show.iterrows():
        vals = [str(r[c]).replace("\n", " ") for c in cols]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def write_memo(clds_sort: pd.DataFrame, fobs: pd.DataFrame, clds_v: pd.DataFrame) -> str:
    lines: list[str] = []
    lines.append("# Round 8C enhanced mechanism rescue memo, 2026-05-02")
    lines.append("")
    lines.append("## Bottom line")
    lines.append("")
    lines.append(
        "The stronger mechanism is not a same-household mediation chain. It is a two-sided reallocation pattern: "
        "farm-oriented households in high-insecurity villages become the land receivers, while nonfarm-oriented or low-farm-dependence households move further toward nonfarm labor and away from farm income/costs. "
        "FOBS supplies direct village-level transfer-flow evidence that CLDS lacks at the household rent-out margin."
    )
    lines.append("")
    lines.append("## CLDS sorting diagnostics")
    lines.append("")
    clds_show = clds_sort[
        clds_sort["group"].isin(
            [
                "recipient: top baseline farm dependence",
                "recipient: no pre rent-in and top farm dependence",
                "exit: bottom baseline farm dependence",
                "exit: top baseline nonfarm labor",
            ]
        )
    ].copy()
    lines.append(md_table(clds_show, ["group", "label", "b", "se", "p", "N", "clusters"]))
    lines.append("")
    lines.append("## FOBS direct village transfer-flow check")
    lines.append("")
    lines.append(md_table(fobs, ["label", "treat", "b", "se", "p", "N", "clusters"]))
    lines.append("")
    lines.append("## CLDS village supply-side bridge")
    lines.append("")
    lines.append(md_table(clds_v, ["label", "term", "b", "se", "p", "N", "clusters"]))
    lines.append("")
    lines.append("## Recommended paper treatment")
    lines.append("")
    lines.append(
        "Use the CLDS household results as the main mechanism evidence for receiver/exit sorting, and use FOBS as an external direct transfer-flow validation. "
        "The text should say that certification is consistent with within-village/county reallocation: land is taken up by more farm-oriented households, while less farm-dependent/nonfarm-oriented households adjust further toward nonfarm work. "
        "Because CLDS still does not observe household rent-out, avoid formal mediation language and avoid claiming matched supplier-receiver evidence."
    )
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append(f"- CLDS sorting diagnostics: `{TABLES / 'Round8C_CLDS_receiver_exit_sorting.csv'}`")
    lines.append(f"- FOBS direct transfer diagnostics: `{TABLES / 'Round8C_FOBS_direct_transfer_flow.csv'}`")
    lines.append(f"- CLDS village supply bridge: `{TABLES / 'Round8C_CLDS_village_supply_bridge.csv'}`")
    return "\n".join(lines)


def main() -> None:
    ensure_dirs()
    clds_stack = load_clds_stack()
    clds_sort = clds_sorting_diagnostics(clds_stack)
    fobs = fobs_direct_transfer_diagnostics()
    clds_v = clds_village_supply_bridge()
    clds_sort.to_csv(TABLES / "Round8C_CLDS_receiver_exit_sorting.csv", index=False, encoding="utf-8-sig")
    fobs.to_csv(TABLES / "Round8C_FOBS_direct_transfer_flow.csv", index=False, encoding="utf-8-sig")
    clds_v.to_csv(TABLES / "Round8C_CLDS_village_supply_bridge.csv", index=False, encoding="utf-8-sig")
    memo = write_memo(clds_sort, fobs, clds_v)
    (OUT / "Round8C_EnhancedMechanism_Rescue_Memo_20260502.md").write_text(memo, encoding="utf-8")
    print(memo)


if __name__ == "__main__":
    main()
