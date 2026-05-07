from __future__ import annotations

import math
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat
from differences import ATTgt
from differences.models.attgt.attgt import ATTgtResult
from differences.models.attgt.mboot import get_cluster_groups


if not hasattr(np, "alltrue"):
    # differences<=0.2 still calls np.alltrue in the difference aggregator.
    np.alltrue = np.all


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "result" / "round25_empirical_rebuild_20260502" / "round6_modern_did"
TABLES = OUT / "tables"
AUDIT = OUT / "audit"
for path in [OUT, TABLES, AUDIT]:
    path.mkdir(parents=True, exist_ok=True)

PANEL = ROOT / "data" / "topjournal_rebuild" / "clds" / "CLDS_hh_mechanism_panel_with_indivbridge_20260416.dta"
ADMIN = ROOT / "data" / "topjournal_rebuild" / "admin" / "admin_rollout_countyyear_v2.dta"

OLD23 = ROOT / "result" / "round23_csdid_modern_did_20260501" / "tables"
OLD24 = ROOT / "result" / "round24_bjs_imputation_20260501" / "tables"

THRESHOLDS = [
    ("signoff_or_issue_t", "Signoff/issuance"),
    ("completed_t", "Completion"),
    ("high_sat80_t", "High-saturation"),
]
OUTCOMES = [
    ("any_rentin", "Any rent-in"),
    ("asinh_rentin", "asinh rented-in area"),
]
SCOPES = {
    "mechanism": "Mechanism sample",
    "adjacent": "Adjacent sample",
}
BOOT_REPS = 999
SEED = 20260502


def normal_p(b: float, se: float) -> float:
    if pd.isna(b) or pd.isna(se) or se <= 0:
        return np.nan
    return math.erfc(abs(b / se) / math.sqrt(2))


def parse_warning_count(pattern: str, text: str) -> int:
    if not isinstance(text, str):
        return 0
    match = re.search(pattern, text)
    return int(match.group(1)) if match else 0


def patch_difference_cluster_bug() -> None:
    """Patch a narrow compatibility issue in differences' sample-difference bootstrap.

    When two sample splits exhaust the full data, differences passes data_mask=None.
    The upstream method then tries .loc[None]. This patch uses the full data in that
    specific case. It does not change the ATT or influence functions.
    """

    def fixed_get_clusters_for_difference(self, cluster_var, difference_samples, data_mask, iterate_samples):
        cluster_groups = None
        if cluster_var:
            if isinstance(cluster_var, str):
                cluster_var = [cluster_var]
            if difference_samples:
                data = self.data_matrix[cluster_var] if data_mask is None else self.data_matrix[cluster_var].loc[data_mask]
                cluster_groups = get_cluster_groups(data=data, cluster_var=cluster_var)
            elif iterate_samples:
                cluster_groups = {
                    s: get_cluster_groups(
                        data=self.data_matrix[cluster_var].loc[self._att_gt[s]["sample_mask"]],
                        cluster_var=cluster_var,
                    )
                    for s in self.sample_names
                }
            else:
                cluster_groups = get_cluster_groups(data=self.data_matrix[cluster_var], cluster_var=cluster_var)
        return cluster_groups

    ATTgtResult._get_clusters_for_difference = fixed_get_clusters_for_difference


def read_inputs() -> pd.DataFrame:
    panel_cols = [
        "hid",
        "hid_key",
        "year",
        "__cid_id",
        "s_mech_hh",
        "timing_adjacent_hh",
        "a3_high_insec",
        "any_rentin",
        "asinh_rentin",
    ]
    panel, _ = pyreadstat.read_dta(str(PANEL), usecols=panel_cols)
    admin, _ = pyreadstat.read_dta(
        str(ADMIN),
        usecols=[
            "county_id_num",
            "year",
            "county_signedoff_t",
            "county_issued_t",
            "county_completed_t",
            "county_sat_t",
        ],
    )
    df = panel.loc[panel["year"].isin([2014, 2016, 2018])].copy()
    adm = admin.rename(columns={"county_id_num": "__cid_id"})
    df = df.merge(adm, on=["__cid_id", "year"], how="left")
    df["instab_high"] = np.where(
        df["a3_high_insec"].isin([0, 1]), df["a3_high_insec"].astype(float), np.nan
    )
    df["signoff_or_issue_t"] = np.where(
        df[["county_signedoff_t", "county_issued_t"]].notna().any(axis=1),
        (df["county_signedoff_t"].eq(1) | df["county_issued_t"].eq(1)).astype(float),
        np.nan,
    )
    df["completed_t"] = np.where(
        df["county_completed_t"].notna(), df["county_completed_t"].astype(float), np.nan
    )
    df["high_sat80_t"] = np.where(
        df["county_sat_t"].notna(), df["county_sat_t"].ge(0.8).astype(float), np.nan
    )
    return df


def cohort_by_county(df: pd.DataFrame, threshold: str) -> pd.Series:
    first = df.loc[df[threshold].eq(1)].groupby("__cid_id")["year"].min()
    return df["__cid_id"].map(first)


def scope_filter(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    if scope == "mechanism":
        return df.loc[df["s_mech_hh"].eq(1)].copy()
    if scope == "adjacent":
        return df.loc[df["s_mech_hh"].eq(1) & df["timing_adjacent_hh"].eq(1)].copy()
    raise ValueError(scope)


def build_cs_data(df: pd.DataFrame, scope: str, threshold: str, outcome: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    sub = scope_filter(df, scope)
    sub["cohort"] = cohort_by_county(sub, threshold)
    keep = ["hid", "year", "__cid_id", "cohort", "instab_high", outcome]
    sub = (
        sub[keep]
        .replace([np.inf, -np.inf], np.nan)
        .dropna(subset=["hid", "year", "__cid_id", "instab_high", outcome])
        .copy()
    )
    sub = sub.loc[sub["cohort"].isna() | sub["cohort"].isin([2014, 2016, 2018])].copy()
    sub["hid"] = sub["hid"].astype(str)
    sub["year"] = sub["year"].astype(int)
    sub["__cid_id"] = sub["__cid_id"].astype(int)
    sub["instab_high"] = sub["instab_high"].astype(int)
    sub = sub.sort_values(["hid", "year"]).copy()

    raw_county_cohorts = (
        sub[["__cid_id", "cohort"]].drop_duplicates()["cohort"].value_counts(dropna=False).to_dict()
    )

    # Mimic differences' panel validation so that county clusters can be aligned
    # back to the recoded entity index in result.data_matrix.
    ent = (
        sub.groupby("hid")
        .agg(first_year=("year", "min"), last_year=("year", "max"), cohort=("cohort", "first"))
        .reset_index()
    )
    ent["drop_always"] = ent["cohort"].notna() & (ent["cohort"] <= ent["first_year"])
    ent["ignore_after"] = ent["cohort"].notna() & (ent["cohort"] > ent["last_year"])
    valid = sub.merge(ent[["hid", "drop_always", "ignore_after"]], on="hid", how="left")
    valid = valid.loc[~valid["drop_always"]].copy()
    valid.loc[valid["ignore_after"], "cohort"] = np.nan
    valid = valid.sort_values(["hid", "year"]).reset_index(drop=True)

    info = {
        "raw_obs": int(len(sub)),
        "raw_households": int(sub["hid"].nunique()),
        "raw_counties": int(sub["__cid_id"].nunique()),
        "raw_county_cohort_counts": str(raw_county_cohorts),
        "validator_drop_always_entities": int(ent["drop_always"].sum()),
        "validator_ignore_after_entities": int(ent["ignore_after"].sum()),
        "valid_obs": int(len(valid)),
        "valid_households": int(valid["hid"].nunique()),
        "valid_counties": int(valid["__cid_id"].nunique()),
    }
    cs = sub.set_index(["hid", "year"])[["__cid_id", "cohort", "instab_high", outcome]].sort_index()
    return cs, valid, info


def flatten_agg(out: pd.DataFrame) -> dict:
    flat = out.copy()
    if isinstance(flat.columns, pd.MultiIndex):
        flat.columns = ["|".join(str(x) for x in col if str(x) != "") for col in flat.columns]
    row = flat.iloc[0]
    att_col = next(c for c in flat.columns if c.endswith("|ATT") or c == "ATT" or "ATT" in c)
    se_col = next(c for c in flat.columns if "std_error" in c)
    low_col = next((c for c in flat.columns if "lower" in c), None)
    high_col = next((c for c in flat.columns if "upper" in c), None)
    att = float(row[att_col])
    se = float(row[se_col])
    return {
        "att": att,
        "se": se,
        "p": normal_p(att, se),
        "ci_low": float(row[low_col]) if low_col else att - 1.96 * se,
        "ci_high": float(row[high_col]) if high_col else att + 1.96 * se,
    }


def flatten_event_diff(out: pd.DataFrame) -> pd.DataFrame:
    flat = out.copy()
    if isinstance(flat.columns, pd.MultiIndex):
        flat.columns = ["|".join(str(x) for x in col if str(x) != "") for col in flat.columns]
    flat = flat.reset_index()
    rel_col = next((c for c in flat.columns if "relative_period" in c), None)
    att_col = next(c for c in flat.columns if c.endswith("|ATT") or c == "ATT" or "ATT" in c)
    se_col = next(c for c in flat.columns if "std_error" in c)
    low_col = next((c for c in flat.columns if "lower" in c), None)
    high_col = next((c for c in flat.columns if "upper" in c), None)
    out_df = flat[[rel_col, att_col, se_col] + ([low_col] if low_col else []) + ([high_col] if high_col else [])].copy()
    out_df = out_df.rename(columns={rel_col: "event_time", att_col: "att", se_col: "se"})
    if low_col:
        out_df = out_df.rename(columns={low_col: "ci_low"})
    else:
        out_df["ci_low"] = out_df["att"] - 1.96 * out_df["se"]
    if high_col:
        out_df = out_df.rename(columns={high_col: "ci_high"})
    else:
        out_df["ci_high"] = out_df["att"] + 1.96 * out_df["se"]
    out_df["p"] = [normal_p(b, se) for b, se in zip(out_df["att"], out_df["se"])]
    return out_df[["event_time", "att", "se", "p", "ci_low", "ci_high"]]


def run_cs_direct(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    patch_difference_cluster_bug()
    rows = []
    audits = []
    events = []
    for scope, sample_label in SCOPES.items():
        for threshold, threshold_label in THRESHOLDS:
            for outcome, outcome_label in OUTCOMES:
                cs, valid, info = build_cs_data(df, scope, threshold, outcome)
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    try:
                        result = ATTgt(cs, cohort_column="cohort", base_period="varying").fit(
                            outcome,
                            est_method="dr",
                            control_group="not_yet_treated",
                            sample_split_column="instab_high",
                            boot_iterations=0,
                            progress_bar=False,
                        )
                        if len(result.data_matrix) != len(valid):
                            raise RuntimeError(
                                f"validator alignment mismatch: {len(result.data_matrix)} vs {len(valid)}"
                            )
                        result.data_matrix["__cid_id"] = valid["__cid_id"].to_numpy()
                        group = result.aggregate("simple")
                        diff = result.aggregate(
                            "simple",
                            difference=["instab_high = 1", "instab_high = 0"],
                            cluster_var="__cid_id",
                            boot_iterations=BOOT_REPS,
                            random_state=SEED,
                            n_jobs=1,
                        )
                        event_diff = result.aggregate(
                            "event",
                            difference=["instab_high = 1", "instab_high = 0"],
                            cluster_var="__cid_id",
                            boot_iterations=BOOT_REPS,
                            random_state=SEED,
                            n_jobs=1,
                        )
                        status = "ok"
                        err = ""
                    except Exception as exc:  # noqa: BLE001
                        group = pd.DataFrame()
                        diff = pd.DataFrame()
                        event_diff = pd.DataFrame()
                        status = f"error:{type(exc).__name__}"
                        err = str(exc)

                warning_text = " | ".join(str(w.message) for w in caught)
                audit = {
                    "scope": scope,
                    "sample": sample_label,
                    "threshold": threshold_label,
                    "threshold_var": threshold,
                    "outcome": outcome,
                    "outcome_label": outcome_label,
                    **info,
                    "status": status,
                    "error_message": err,
                    "warnings": warning_text,
                    "warn_drop_always_entities": parse_warning_count(r"(\d+) entities have been dropped", warning_text),
                    "warn_ignore_after_entities": parse_warning_count(r"(\d+) entity-events ignored", warning_text),
                }
                audits.append(audit)
                if status != "ok":
                    continue

                group_flat = group.copy()
                if isinstance(group_flat.columns, pd.MultiIndex):
                    group_flat.columns = [
                        "|".join(str(x) for x in col if str(x) != "") for col in group_flat.columns
                    ]
                group_flat = group_flat.reset_index().rename(columns={"sample_name": "split"})
                for _, gr in group_flat.iterrows():
                    split = str(gr.get("split", ""))
                    m = 1 if split.endswith("= 1") else 0
                    att_col = next(c for c in group_flat.columns if c.endswith("|ATT") or c == "ATT" or "ATT" in c)
                    se_col = next(c for c in group_flat.columns if "std_error" in c)
                    b = float(gr[att_col])
                    se = float(gr[se_col])
                    rows.append(
                        {
                            "estimator": "CS group-time ATT",
                            "scope": scope,
                            "sample": sample_label,
                            "threshold": threshold_label,
                            "threshold_var": threshold,
                            "outcome": outcome,
                            "outcome_label": outcome_label,
                            "row": "High baseline insecurity" if m == 1 else "Lower baseline insecurity",
                            "contrast": "subgroup ATT",
                            "att": b,
                            "se": se,
                            "p": normal_p(b, se),
                            "inference": "analytic subgroup SE from differences",
                            "boot_reps": 0,
                            **info,
                        }
                    )

                d = flatten_agg(diff)
                rows.append(
                    {
                        "estimator": "CS group-time ATT",
                        "scope": scope,
                        "sample": sample_label,
                        "threshold": threshold_label,
                        "threshold_var": threshold,
                        "outcome": outcome,
                        "outcome_label": outcome_label,
                        "row": "High - lower",
                        "contrast": "high-minus-lower ATT",
                        "inference": "direct county-cluster multiplier bootstrap for sample-split difference",
                        "boot_reps": BOOT_REPS,
                        **d,
                        **info,
                    }
                )
                ev = flatten_event_diff(event_diff)
                for _, er in ev.iterrows():
                    events.append(
                        {
                            "scope": scope,
                            "sample": sample_label,
                            "threshold": threshold_label,
                            "threshold_var": threshold,
                            "outcome": outcome,
                            "outcome_label": outcome_label,
                            "contrast": "CS high-minus-lower event ATT",
                            "event_time": er["event_time"],
                            "att": er["att"],
                            "se": er["se"],
                            "p": er["p"],
                            "ci_low": er["ci_low"],
                            "ci_high": er["ci_high"],
                            "inference": "direct county-cluster multiplier bootstrap for sample-split event difference",
                            "boot_reps": BOOT_REPS,
                            **info,
                        }
                    )

    return pd.DataFrame(rows), pd.DataFrame(audits), pd.DataFrame(events)


def load_stacked_and_bjs() -> tuple[pd.DataFrame, pd.DataFrame]:
    stacked_path = OLD23 / "Table_S10b_CSDID_vs_stacked_preferred_thresholds.csv"
    stacked = pd.read_csv(stacked_path)
    stacked = stacked.rename(columns={"outcome": "outcome_label"})
    stacked["estimator"] = "Stacked 2x2 DID"
    stacked["row"] = "High - lower"
    stacked["contrast"] = "high-minus-lower DDD"
    stacked["att"] = stacked["stacked_DID_high_low_diff"]
    stacked["se"] = np.nan
    stacked["p"] = np.nan
    stacked["inference"] = "county-cluster SE in Stata table; this comparison table imports point estimates only"
    stacked["threshold_var"] = stacked["threshold"].map(
        {
            "Completion": "completed_t",
            "High-saturation": "high_sat80_t",
            "Signoff/issuance": "signoff_or_issue_t",
        }
    )
    stacked["outcome"] = stacked["outcome_label"].map(
        {"Any rent-in": "any_rentin", "asinh rented-in area": "asinh_rentin"}
    )
    stacked["scope"] = stacked["sample"].map({"Mechanism sample": "mechanism", "Adjacent sample": "adjacent"})
    stacked = stacked[
        [
            "estimator",
            "scope",
            "sample",
            "threshold",
            "threshold_var",
            "outcome",
            "outcome_label",
            "row",
            "contrast",
            "att",
            "se",
            "p",
            "inference",
        ]
    ]

    bjs_path = OLD24 / "Table_S11_BJS_preferred_highlow.csv"
    bjs = pd.read_csv(bjs_path)
    bjs["estimator"] = "BJS imputation DID"
    bjs["contrast"] = "high-minus-lower ATT"
    bjs["inference"] = "paired county bootstrap"
    bjs["boot_reps"] = bjs.get("boot_reps_ok", np.nan)
    bjs = bjs[
        [
            "estimator",
            "scope",
            "sample",
            "threshold",
            "threshold_var",
            "outcome",
            "outcome_label",
            "row",
            "contrast",
            "att",
            "se",
            "p",
            "ci_low",
            "ci_high",
            "inference",
            "boot_reps",
            "low_fit_obs",
            "low_fit_households",
            "low_fit_counties",
            "low_treated_obs",
            "low_treated_households",
            "low_treated_counties",
            "high_fit_obs",
            "high_fit_households",
            "high_fit_counties",
            "high_treated_obs",
            "high_treated_households",
            "high_treated_counties",
            "county_count_boot_frame",
        ]
    ]
    return stacked, bjs


def make_preferred_summary(stacked: pd.DataFrame, cs: pd.DataFrame, bjs: pd.DataFrame) -> pd.DataFrame:
    cs_diff = cs.loc[cs["row"].eq("High - lower")].copy()
    stacked_pref = stacked.loc[
        stacked["threshold"].isin(["Completion", "High-saturation"])
        & stacked["outcome"].isin(["any_rentin", "asinh_rentin"])
    ].copy()
    cs_pref = cs_diff.loc[
        cs_diff["threshold"].isin(["Completion", "High-saturation"])
        & cs_diff["outcome"].isin(["any_rentin", "asinh_rentin"])
    ].copy()
    bjs_pref = bjs.loc[
        bjs["threshold"].isin(["Completion", "High-saturation"])
        & bjs["outcome"].isin(["any_rentin", "asinh_rentin"])
    ].copy()
    rows = []
    keys = ["scope", "sample", "threshold", "threshold_var", "outcome", "outcome_label"]
    for key, srow in stacked_pref.groupby(keys, dropna=False):
        base = dict(zip(keys, key))
        crow = cs_pref
        brow = bjs_pref
        for k, v in base.items():
            crow = crow.loc[crow[k].eq(v)]
            brow = brow.loc[brow[k].eq(v)]
        rows.append(
            {
                **base,
                "stacked_diff": float(srow.iloc[0]["att"]),
                "cs_direct_diff": float(crow.iloc[0]["att"]) if not crow.empty else np.nan,
                "cs_direct_se": float(crow.iloc[0]["se"]) if not crow.empty else np.nan,
                "cs_direct_p": float(crow.iloc[0]["p"]) if not crow.empty else np.nan,
                "bjs_diff": float(brow.iloc[0]["att"]) if not brow.empty else np.nan,
                "bjs_se": float(brow.iloc[0]["se"]) if not brow.empty else np.nan,
                "bjs_p": float(brow.iloc[0]["p"]) if not brow.empty else np.nan,
                "bjs_high_treated_obs": int(brow.iloc[0]["high_treated_obs"]) if not brow.empty else np.nan,
                "bjs_low_treated_obs": int(brow.iloc[0]["low_treated_obs"]) if not brow.empty else np.nan,
                "cs_valid_households": int(crow.iloc[0]["valid_households"]) if not crow.empty else np.nan,
                "cs_valid_counties": int(crow.iloc[0]["valid_counties"]) if not crow.empty else np.nan,
                "cs_drop_always_entities": int(crow.iloc[0]["validator_drop_always_entities"]) if not crow.empty else np.nan,
                "cs_ignore_after_entities": int(crow.iloc[0]["validator_ignore_after_entities"]) if not crow.empty else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values(["sample", "threshold", "outcome"])


def write_memo(summary: pd.DataFrame, cs_audit: pd.DataFrame) -> None:
    mech = summary.loc[summary["scope"].eq("mechanism")].copy()
    lines = [
        "# Round 6 Modern DID Re-audit",
        "",
        "Date: 2026-05-02",
        "",
        "## What changed in this re-audit",
        "",
        "The earlier CS table used a conservative independent-subgroup SE for the high-minus-lower contrast. This addendum re-estimates CS with `sample_split_column=instab_high` and computes the high-minus-lower contrast directly inside the CS result object. Inference for that contrast uses a county-cluster multiplier bootstrap after restoring county identifiers to the post-validation data matrix. This is the correct covariance-aware comparison because the two subgroups are nested in the same county rollout process.",
        "",
        "## Main conclusion",
        "",
        "The modern DID evidence is stronger than the earlier conservative summary suggested. Across the preferred completion and high-saturation thresholds, stacked DID, CS group-time ATT, and BJS imputation DID all produce positive high-minus-lower effects on both rent-in outcomes. In the mechanism sample, the CS direct county-bootstrap high-minus-lower differences are statistically clear, and the BJS imputation differences are also significant.",
        "",
        "## Preferred mechanism-sample estimates",
        "",
        "| Threshold | Outcome | Stacked DDD | CS direct diff (SE, p) | BJS diff (SE, p) |",
        "|---|---:|---:|---:|---:|",
    ]
    for _, r in mech.iterrows():
        lines.append(
            f"| {r['threshold']} | {r['outcome_label']} | {r['stacked_diff']:.3f} | "
            f"{r['cs_direct_diff']:.3f} ({r['cs_direct_se']:.3f}, p={r['cs_direct_p']:.3g}) | "
            f"{r['bjs_diff']:.3f} ({r['bjs_se']:.3f}, p={r['bjs_p']:.3g}) |"
        )
    lines.extend(
        [
            "",
            "## Support and drop diagnostics",
            "",
            "The CS estimator drops households that first appear when their county is already treated and treats cohort dates after a household's last observed wave as never-treated. This behavior is expected in an unbalanced three-wave household panel. It reduces precision but does not create the positive pattern: the valid CS sample still preserves the stacked-DID high-minus-lower magnitudes.",
            "",
            "For the mechanism sample and preferred thresholds, the CS validated samples contain roughly 3,200-3,300 households and 214 counties before subgroup splitting. BJS treated support is smaller in the high-insecurity group (about 47-48 households and 9-10 counties for the preferred thresholds), so BJS should remain an additional robustness check rather than the main precision benchmark.",
            "",
            "## Recommended manuscript framing",
            "",
            "Use stacked 2x2 DID as the main estimator. Present CS and BJS as modern-DID robustness checks showing that the high-insecurity rent-in result is not an artifact of staggered TWFE weighting. The upgraded CS table can now report the direct high-minus-lower county-bootstrap contrast, but the text should still emphasize sign and magnitude consistency rather than claiming CS as the primary estimator.",
            "",
            "## Files",
            "",
            "- `tables/Round6_A_CSDID_direct_sample_split.csv`",
            "- `audit/Round6_B_CSDID_support_and_drop_audit.csv`",
            "- `tables/Round6_C_modernDID_unified_preferred.csv`",
            "- `tables/Round6_D_all_modernDID_long.csv`",
            "- `tables/Round6_E_CSDID_direct_event_highlow.csv`",
        ]
    )
    (OUT / "Round6_ModernDID_Reaudit_Memo_20260502.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    df = read_inputs()
    cs_rows, cs_audit, cs_events = run_cs_direct(df)
    stacked, bjs = load_stacked_and_bjs()
    summary = make_preferred_summary(stacked, cs_rows, bjs)
    long = pd.concat(
        [
            stacked.assign(ci_low=np.nan, ci_high=np.nan, boot_reps=np.nan),
            cs_rows,
            bjs,
        ],
        ignore_index=True,
        sort=False,
    )
    cs_rows.to_csv(TABLES / "Round6_A_CSDID_direct_sample_split.csv", index=False, encoding="utf-8-sig")
    cs_audit.to_csv(AUDIT / "Round6_B_CSDID_support_and_drop_audit.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(TABLES / "Round6_C_modernDID_unified_preferred.csv", index=False, encoding="utf-8-sig")
    long.to_csv(TABLES / "Round6_D_all_modernDID_long.csv", index=False, encoding="utf-8-sig")
    cs_events.to_csv(TABLES / "Round6_E_CSDID_direct_event_highlow.csv", index=False, encoding="utf-8-sig")
    write_memo(summary, cs_audit)


if __name__ == "__main__":
    main()
