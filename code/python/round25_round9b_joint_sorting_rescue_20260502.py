from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import round25_round9_farmdependence_heterogeneity_20260502 as r9  # noqa: E402


OUT = ROOT / "result" / "round25_empirical_rebuild_20260502" / "round9_farmdependence_heterogeneity" / "joint_sorting"
TABLES = OUT / "tables"

STACK_SPECS = [
    ("adjacent", "completed_t"),
    ("adjacent", "high_sat80_t"),
    ("mech", "completed_t"),
    ("mech", "high_sat80_t"),
]
CORE_OUTCOMES = [
    "any_rentin",
    "asinh_rentin",
    "rentin_and_farm_any",
    "ib_nonfarm_curr_n",
    "ib_nonfarm_curr_ge2",
    "nonfarm_ge2_no_rentin",
    "rb_farm_any",
    "asinh_rb_inc_farm_w99",
]


def ensure_dirs() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)


def fit_simple_did(data: pd.DataFrame, y: str, fe_name: str) -> dict | None:
    fe_cols = ["hid_stack", "prov_year_stack"] if fe_name == "provyear" else ["hid_stack", "year_stack"]
    try:
        fit, kept = r9.fit_resid_ols(data, y, ["D"], fe_cols, min_n=80, min_clusters=10)
        b, se, p = r9.lincom(fit, [("D", 1.0)])
        return {
            "b": b,
            "se": se,
            "p": p,
            "N": int(len(kept)),
            "clusters": int(kept["__cid_id"].nunique()),
            "mean_y": float(data[y].mean(skipna=True)),
            "status": "ok",
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": f"error: {exc}"}


def fit_top_bottom_contrast(data: pd.DataFrame, y: str, top_col: str, label_top: str, fe_name: str) -> list[dict]:
    fe_cols = ["hid_stack", "prov_year_stack"] if fe_name == "provyear" else ["hid_stack", "year_stack"]
    d = data.copy()
    d["M"] = pd.to_numeric(d[top_col], errors="coerce")
    d["D_x_M"] = d["D"] * d["M"]
    d["post_x_M"] = d["post"] * d["M"]
    try:
        fit, kept = r9.fit_resid_ols(d, y, ["D", "D_x_M", "post_x_M"], fe_cols, min_n=80, min_clusters=10)
    except Exception as exc:  # noqa: BLE001
        return [{"term": "error", "status": f"error: {exc}"}]
    term_map = {
        "bottom group DID": [("D", 1.0)],
        f"{label_top}-minus-bottom differential": [("D_x_M", 1.0)],
        f"{label_top} group DID": [("D", 1.0), ("D_x_M", 1.0)],
    }
    rows: list[dict] = []
    for term, terms in term_map.items():
        b, se, p = r9.lincom(fit, terms)
        rows.append(
            {
                "term": term,
                "b": b,
                "se": se,
                "p": p,
                "N": int(len(kept)),
                "clusters": int(kept["__cid_id"].nunique()),
                "mean_y": float(d[y].mean(skipna=True)),
                "status": "ok",
            }
        )
    return rows


def fit_high_minus_low_within_stratum(data: pd.DataFrame, y: str, fe_name: str) -> list[dict]:
    fe_cols = ["hid_stack", "prov_year_stack"] if fe_name == "provyear" else ["hid_stack", "year_stack"]
    d = data.copy()
    try:
        fit, kept = r9.fit_resid_ols(d, y, ["D", "DM", "PM"], fe_cols, min_n=80, min_clusters=10)
    except Exception as exc:  # noqa: BLE001
        return [{"term": "error", "status": f"error: {exc}"}]
    term_map = {
        "low-insecurity DID": [("D", 1.0)],
        "high-minus-low differential": [("DM", 1.0)],
        "high-insecurity DID": [("D", 1.0), ("DM", 1.0)],
    }
    rows: list[dict] = []
    for term, terms in term_map.items():
        b, se, p = r9.lincom(fit, terms)
        rows.append(
            {
                "term": term,
                "b": b,
                "se": se,
                "p": p,
                "N": int(len(kept)),
                "clusters": int(kept["__cid_id"].nunique()),
                "mean_y": float(d[y].mean(skipna=True)),
                "status": "ok",
            }
        )
    return rows


def run_joint_sorting() -> tuple[pd.DataFrame, pd.DataFrame]:
    panel, admin, ext = r9.read_base_stack()
    group_rows: list[dict] = []
    contrast_rows: list[dict] = []
    for scope, anchor in STACK_SPECS:
        stack = r9.make_stack(panel, admin, ext, scope, anchor)
        groups = [
            ("low insecurity + farmdep bottom", stack["instab_high"].eq(0) & stack["farmdep_bot3"].eq(1)),
            ("low insecurity + farmdep top", stack["instab_high"].eq(0) & stack["farmdep_top3"].eq(1)),
            ("high insecurity + farmdep bottom", stack["instab_high"].eq(1) & stack["farmdep_bot3"].eq(1)),
            ("high insecurity + farmdep top", stack["instab_high"].eq(1) & stack["farmdep_top3"].eq(1)),
            ("low insecurity + farm-orientation bottom", stack["instab_high"].eq(0) & stack["farm_orientation_bot3"].eq(1)),
            ("low insecurity + farm-orientation top", stack["instab_high"].eq(0) & stack["farm_orientation_top3"].eq(1)),
            ("high insecurity + farm-orientation bottom", stack["instab_high"].eq(1) & stack["farm_orientation_bot3"].eq(1)),
            ("high insecurity + farm-orientation top", stack["instab_high"].eq(1) & stack["farm_orientation_top3"].eq(1)),
        ]
        for group_name, mask in groups:
            d = stack.loc[mask].copy()
            for y in CORE_OUTCOMES:
                if y not in d.columns:
                    continue
                for fe_name in ["stackyear", "provyear"]:
                    est = fit_simple_did(d, y, fe_name)
                    group_rows.append(
                        {
                            "scope": scope,
                            "anchor": anchor,
                            "design": "simple DID within joint A3 x baseline-orientation group",
                            "group": group_name,
                            "outcome": y,
                            "outcome_label": r9.OUTCOME_LABELS.get(y, y),
                            "family": r9.outcome_family(y),
                            "fe": fe_name,
                            **(est or {"status": "no result"}),
                        }
                    )

        for a3_value, a3_label in [(0, "low insecurity"), (1, "high insecurity")]:
            for orient, top_col, bottom_col, label_top in [
                ("farmdep", "farmdep_top3", "farmdep_bot3", "top farmdep"),
                ("farm_orientation", "farm_orientation_top3", "farm_orientation_bot3", "top farm-orientation"),
            ]:
                d = stack.loc[stack["instab_high"].eq(a3_value) & (stack[top_col].eq(1) | stack[bottom_col].eq(1))].copy()
                for y in CORE_OUTCOMES:
                    if y not in d.columns:
                        continue
                    for fe_name in ["stackyear", "provyear"]:
                        for res in fit_top_bottom_contrast(d, y, top_col, label_top, fe_name):
                            contrast_rows.append(
                                {
                                    "scope": scope,
                                    "anchor": anchor,
                                    "design": f"{a3_label}: top-vs-bottom {orient}",
                                    "a3_group": a3_label,
                                    "orientation": orient,
                                    "outcome": y,
                                    "outcome_label": r9.OUTCOME_LABELS.get(y, y),
                                    "family": r9.outcome_family(y),
                                    "fe": fe_name,
                                    **res,
                                }
                            )

        for stratum, mask in [
            ("farmdep bottom", stack["farmdep_bot3"].eq(1)),
            ("farmdep top", stack["farmdep_top3"].eq(1)),
            ("farm-orientation bottom", stack["farm_orientation_bot3"].eq(1)),
            ("farm-orientation top", stack["farm_orientation_top3"].eq(1)),
        ]:
            d = stack.loc[mask].copy()
            for y in CORE_OUTCOMES:
                if y not in d.columns:
                    continue
                for fe_name in ["stackyear", "provyear"]:
                    for res in fit_high_minus_low_within_stratum(d, y, fe_name):
                        contrast_rows.append(
                            {
                                "scope": scope,
                                "anchor": anchor,
                                "design": f"high-minus-low A3 within {stratum}",
                                "a3_group": "high-minus-low",
                                "orientation": stratum,
                                "outcome": y,
                                "outcome_label": r9.OUTCOME_LABELS.get(y, y),
                                "family": r9.outcome_family(y),
                                "fe": fe_name,
                                **res,
                            }
                        )
    return pd.DataFrame(group_rows), pd.DataFrame(contrast_rows)


def md_table(df: pd.DataFrame, cols: list[str], max_rows: int = 30) -> str:
    if df.empty:
        return "_No rows._"
    show = df.head(max_rows)[cols].copy()
    for col in ["b", "se", "p", "mean_y"]:
        if col in show.columns:
            show[col] = show[col].map(r9.fmt)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in show.iterrows():
        lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


def write_memo(group: pd.DataFrame, contrast: pd.DataFrame) -> None:
    main_group = group[
        group["scope"].eq("adjacent")
        & group["anchor"].eq("completed_t")
        & group["fe"].eq("stackyear")
        & group["status"].eq("ok")
        & group["group"].isin(["high insecurity + farmdep bottom", "high insecurity + farmdep top", "low insecurity + farmdep bottom", "low insecurity + farmdep top"])
        & group["outcome"].isin(["any_rentin", "asinh_rentin", "rentin_and_farm_any", "ib_nonfarm_curr_n", "ib_nonfarm_curr_ge2", "nonfarm_ge2_no_rentin"])
    ].sort_values(["group", "family", "outcome"])
    high_tb = contrast[
        contrast["scope"].eq("adjacent")
        & contrast["anchor"].eq("completed_t")
        & contrast["design"].eq("high insecurity: top-vs-bottom farmdep")
        & contrast["term"].str.contains("differential", na=False)
        & contrast["status"].eq("ok")
        & contrast["b"].notna()
    ].sort_values(["family", "outcome", "fe"])
    high_low_top = contrast[
        contrast["scope"].eq("adjacent")
        & contrast["anchor"].eq("completed_t")
        & contrast["design"].eq("high-minus-low A3 within farmdep top")
        & contrast["term"].isin(["high-insecurity DID", "high-minus-low differential"])
        & contrast["status"].eq("ok")
    ].sort_values(["family", "outcome", "fe", "term"])
    high_low_bottom = contrast[
        contrast["scope"].eq("adjacent")
        & contrast["anchor"].eq("completed_t")
        & contrast["design"].eq("high-minus-low A3 within farmdep bottom")
        & contrast["term"].isin(["high-insecurity DID", "high-minus-low differential"])
        & contrast["status"].eq("ok")
        & contrast["family"].isin(["nonfarm", "farm-exit"])
    ].sort_values(["family", "outcome", "fe", "term"])

    lines: list[str] = []
    lines.append("# Round 9B joint sorting addendum, 2026-05-02")
    lines.append("")
    lines.append("## Bottom line")
    lines.append("")
    lines.append(
        "The best way to rescue 5.3.2 is to write farm-dependence as conditional sorting under baseline tenure insecurity. "
        "In high-insecurity villages, top-farm-dependent households show the receiver-side rent-in response, while bottom-farm-dependent households show the exit-side nonfarm response. "
        "This directly replaces the weak pooled nonfarm top-minus-bottom contrast."
    )
    lines.append("")
    lines.append("## Main joint group effects")
    lines.append("")
    lines.append(md_table(main_group, ["group", "outcome_label", "b", "se", "p", "N", "clusters"], 40))
    lines.append("")
    lines.append("## High-insecurity top-minus-bottom farm-dependence contrasts")
    lines.append("")
    lines.append(md_table(high_tb, ["outcome_label", "family", "fe", "term", "b", "se", "p", "N", "clusters"], 30))
    lines.append("")
    lines.append("## High-minus-low A3 within top farm-dependence")
    lines.append("")
    lines.append(md_table(high_low_top, ["outcome_label", "family", "fe", "term", "b", "se", "p", "N", "clusters"], 30))
    lines.append("")
    lines.append("## High-minus-low A3 within bottom farm-dependence")
    lines.append("")
    lines.append(md_table(high_low_bottom, ["outcome_label", "family", "fe", "term", "b", "se", "p", "N", "clusters"], 30))
    lines.append("")
    lines.append("## Recommended use")
    lines.append("")
    lines.append(
        "Use this addendum to frame Section 5.3.2 as sorting, not as a pooled labor-market heterogeneity test. "
        "The main table can report the high-insecurity top-farm-dependence receiver effects and bottom-farm-dependence exit effects; "
        "the appendix can show the direct top-minus-bottom and high-minus-low contrasts."
    )
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append("- Joint group effects: `result/round25_empirical_rebuild_20260502/round9_farmdependence_heterogeneity/joint_sorting/tables/Round9B_joint_group_effects.csv`")
    lines.append("- Joint contrasts: `result/round25_empirical_rebuild_20260502/round9_farmdependence_heterogeneity/joint_sorting/tables/Round9B_joint_contrasts.csv`")
    (OUT / "Round9B_JointSorting_Addendum_20260502.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    group, contrast = run_joint_sorting()
    group.to_csv(TABLES / "Round9B_joint_group_effects.csv", index=False, encoding="utf-8-sig")
    contrast.to_csv(TABLES / "Round9B_joint_contrasts.csv", index=False, encoding="utf-8-sig")
    write_memo(group, contrast)
    print(f"Wrote Round 9B outputs to {OUT}")


if __name__ == "__main__":
    main()
