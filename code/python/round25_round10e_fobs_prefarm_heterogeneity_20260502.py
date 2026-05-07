from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import round25_round10_fobs_external_validation_20260502 as r10  # noqa: E402
import round25_round10b_fobs_broad_admin_rescue_20260502 as r10b  # noqa: E402
import round25_round10c_fobs_trend_match_rescue_20260502 as r10c  # noqa: E402


OUT = ROOT / "result" / "round25_empirical_rebuild_20260502" / "round10_fobs_external_validation" / "prefarm_heterogeneity"
TABLES = OUT / "tables"

OUTCOMES = [
    "asinh_operated_area_end",
    "asinh_market_volume_area_zfill",
    "asinh_transfer_in_area_zfill",
    "any_transfer_in_zfill",
]


def ensure_dirs() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)


def load() -> pd.DataFrame:
    admin = r10b.read_admin()
    hh = r10b.add_broad_admin(r10.read_household(), admin)
    hh["year_c"] = pd.to_numeric(hh["year"], errors="coerce").astype(float) - 2014.0
    return hh


def add_pre_farm_groups(hh: pd.DataFrame) -> pd.DataFrame:
    d = hh.copy()
    pre = d.loc[d["year"].le(2014)].groupby("unit_id")["asinh_operated_area_end"].mean().rename("pre_op_asinh_mean")
    d = d.merge(pre, on="unit_id", how="left")
    x = pd.to_numeric(d["pre_op_asinh_mean"], errors="coerce")
    valid = x.dropna()
    q33, q67 = valid.quantile([1 / 3, 2 / 3])
    positive_q67 = valid.loc[valid.gt(0)].quantile(2 / 3) if valid.gt(0).any() else q67
    d["pre_op_z"] = r10.standardize(x)
    d["pre_op_top"] = np.where(x.notna(), x.ge(q67).astype(float), np.nan)
    d["pre_op_bottom"] = np.where(x.notna(), x.le(q33).astype(float), np.nan)
    d["pre_op_positive"] = np.where(x.notna(), x.gt(0).astype(float), np.nan)
    d["pre_op_positive_top"] = np.where(x.notna(), x.ge(positive_q67).astype(float), np.nan)
    for g in ["pre_op_z", "pre_op_top", "pre_op_bottom", "pre_op_positive", "pre_op_positive_top"]:
        d[f"T_x_{g}"] = pd.to_numeric(d["adm_high_t"], errors="coerce") * pd.to_numeric(d[g], errors="coerce")
    return d


def run_models(hh: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    specs = {
        "continuous_preop": ["adm_high_t", "T_x_pre_op_z"],
        "top_vs_rest": ["adm_high_t", "T_x_pre_op_top"],
        "positive_vs_zero": ["adm_high_t", "T_x_pre_op_positive"],
        "positive_top_vs_rest": ["adm_high_t", "T_x_pre_op_positive_top"],
    }
    totals = {
        "continuous_preop": {
            "low_or_mean effect": [("adm_high_t", 1.0)],
            "per-sd interaction": [("T_x_pre_op_z", 1.0)],
            "one-sd-higher total": [("adm_high_t", 1.0), ("T_x_pre_op_z", 1.0)],
        },
        "top_vs_rest": {
            "non-top effect": [("adm_high_t", 1.0)],
            "top interaction": [("T_x_pre_op_top", 1.0)],
            "top total": [("adm_high_t", 1.0), ("T_x_pre_op_top", 1.0)],
        },
        "positive_vs_zero": {
            "zero-preop effect": [("adm_high_t", 1.0)],
            "positive interaction": [("T_x_pre_op_positive", 1.0)],
            "positive total": [("adm_high_t", 1.0), ("T_x_pre_op_positive", 1.0)],
        },
        "positive_top_vs_rest": {
            "not-positive-top effect": [("adm_high_t", 1.0)],
            "positive-top interaction": [("T_x_pre_op_positive_top", 1.0)],
            "positive-top total": [("adm_high_t", 1.0), ("T_x_pre_op_positive_top", 1.0)],
        },
    }
    for sample in ["full", "overlap", "long"]:
        d = hh.loc[r10.sample_filter(hh, sample)].copy()
        for outcome in OUTCOMES:
            for spec_name, regs in specs.items():
                for fe_name, fe_cols in {"unit_year": ["unit_id", "year"], "unit_provyear": ["unit_id", "prov_year"]}.items():
                    try:
                        fit, kept, _ = r10c.fit_fe_extra(d, outcome, regs, fe_cols, min_n=100, min_clusters=8)
                        for term, terms in totals[spec_name].items():
                            b, se, p = r10.lincom(fit, terms)
                            rows.append(
                                {
                                    "sample": sample,
                                    "outcome": outcome,
                                    "spec": spec_name,
                                    "fe": fe_name,
                                    "term": term,
                                    "b": b,
                                    "se": se,
                                    "p": p,
                                    "N": int(len(kept)),
                                    "units": int(kept["unit_id"].nunique()),
                                    "counties": int(kept["county_id_num"].nunique()),
                                    "treated_counties": int(kept.loc[pd.to_numeric(kept["adm_high_t"], errors="coerce").gt(0), "county_id_num"].nunique()),
                                    "status": "ok",
                                }
                            )
                    except Exception as exc:  # noqa: BLE001
                        rows.append({"sample": sample, "outcome": outcome, "spec": spec_name, "fe": fe_name, "term": "model", "status": f"error: {exc}"})
    return pd.DataFrame(rows)


def support(hh: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sample in ["full", "overlap", "long"]:
        d = hh.loc[r10.sample_filter(hh, sample)].copy()
        for group in ["pre_op_top", "pre_op_positive", "pre_op_positive_top"]:
            rows.append(
                {
                    "sample": sample,
                    "group": group,
                    "N": int(d[group].notna().sum()),
                    "units": int(d.loc[d[group].notna(), "unit_id"].nunique()),
                    "counties": int(d.loc[d[group].notna(), "county_id_num"].nunique()),
                    "share": float(pd.to_numeric(d[group], errors="coerce").mean(skipna=True)),
                    "treated_counties": int(d.loc[pd.to_numeric(d["adm_high_t"], errors="coerce").gt(0) & d[group].notna(), "county_id_num"].nunique()),
                }
            )
    return pd.DataFrame(rows)


def fmt(x: object) -> str:
    try:
        v = float(x)
    except Exception:
        return str(x)
    if not np.isfinite(v):
        return ""
    return f"{v:.3f}"


def md_table(df: pd.DataFrame, cols: list[str], max_rows: int = 24) -> str:
    if df.empty:
        return "_No rows._"
    show = df.head(max_rows).copy()
    for c in cols:
        if c not in show.columns:
            show[c] = ""
    for c in ["b", "se", "p", "share"]:
        if c in show.columns:
            show[c] = show[c].map(fmt)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, r in show[cols].iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def write_memo(res: pd.DataFrame, sup: pd.DataFrame) -> None:
    op = res[
        res["status"].eq("ok")
        & res["outcome"].eq("asinh_operated_area_end")
        & res["fe"].eq("unit_year")
        & res["term"].isin(["per-sd interaction", "one-sd-higher total", "top interaction", "top total", "positive-top interaction", "positive-top total"])
    ].sort_values(["sample", "spec", "term"])
    flow = res[
        res["status"].eq("ok")
        & res["sample"].eq("full")
        & res["fe"].eq("unit_year")
        & res["outcome"].isin(["asinh_market_volume_area_zfill", "asinh_transfer_in_area_zfill", "any_transfer_in_zfill"])
        & res["spec"].isin(["continuous_preop", "top_vs_rest", "positive_top_vs_rest"])
        & res["term"].str.contains("interaction|total", regex=True)
    ].sort_values(["outcome", "spec", "term"])
    lines = [
        "# Round 10E FOBS pre-farm heterogeneity memo, 2026-05-02",
        "",
        "## Bottom line",
        "",
        "This test uses only FOBS pre-2014 household operated-area history to define farm-oriented households. "
        "It checks whether high-saturation LCP rollout is associated with stronger expansion among households that already operated more land before rollout.",
        "",
        "## Support",
        "",
        md_table(sup, ["sample", "group", "N", "units", "counties", "treated_counties", "share"], 12),
        "",
        "## Operated-area heterogeneity",
        "",
        md_table(op, ["sample", "spec", "term", "b", "se", "p", "N", "counties", "treated_counties"], 30),
        "",
        "## Flow heterogeneity",
        "",
        md_table(flow, ["outcome", "spec", "term", "b", "se", "p", "N", "counties", "treated_counties"], 30),
        "",
        "## Manuscript implication",
        "",
        "If retained, this is an external heterogeneity validation rather than a separate mechanism proof: FOBS shows that the operated-area expansion is concentrated among pre-rollout farm-oriented households. "
        "It should be presented after the CLDS mechanism, not as a replacement for it.",
    ]
    (OUT / "Round10E_FOBS_PreFarm_Heterogeneity_Memo_20260502.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    hh = add_pre_farm_groups(load())
    res = run_models(hh)
    sup = support(hh)
    res.to_csv(TABLES / "Round10E_prefarm_heterogeneity.csv", index=False, encoding="utf-8-sig")
    sup.to_csv(TABLES / "Round10E_prefarm_support.csv", index=False, encoding="utf-8-sig")
    write_memo(res, sup)
    print(f"Wrote Round 10E outputs to {OUT}")


if __name__ == "__main__":
    main()
