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


OUT = ROOT / "result" / "round25_empirical_rebuild_20260502" / "round10_fobs_external_validation" / "household_matched_rescue"
TABLES = OUT / "tables"

OUTCOMES = [
    "asinh_operated_area_end",
    "asinh_market_volume_area_zfill",
    "asinh_transfer_in_area_zfill",
    "any_transfer_in_zfill",
]


def ensure_dirs() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    admin = r10b.read_admin()
    hh = r10b.add_broad_admin(r10.read_household(), admin)
    first_high = r10c.first_treat_year(admin, "adm_high_t")
    hh["ever_high"] = pd.to_numeric(hh["county_id_num"], errors="coerce").astype("Int64").isin(first_high.index).astype(float)
    hh["year_c"] = pd.to_numeric(hh["year"], errors="coerce").astype(float) - 2014.0
    cy = r10c.county_year_panel(hh)
    return hh, admin, cy


def add_outcome_trends(d_base: pd.DataFrame, outcome: str) -> pd.DataFrame:
    feat = r10c.pre_county_features(d_base, outcome)
    d = d_base.merge(feat[["county_id_num", f"z_{outcome}_pre_mean", f"z_{outcome}_pre_slope"]], on="county_id_num", how="left")
    d["pre_mean_trend"] = pd.to_numeric(d[f"z_{outcome}_pre_mean"], errors="coerce") * d["year_c"]
    d["pre_slope_trend"] = pd.to_numeric(d[f"z_{outcome}_pre_slope"], errors="coerce") * d["year_c"]
    d["ever_high_trend"] = d["ever_high"] * d["year_c"]
    return d


def run_household_matched(hh: pd.DataFrame, admin: pd.DataFrame, cy: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    first_high = r10c.first_treat_year(admin, "adm_high_t")
    rows: list[dict] = []
    match_rows: list[pd.DataFrame] = []
    for outcome in OUTCOMES:
        selected, matches = r10c.choose_matched_controls(cy, outcome, first_high, k=5)
        matches["matched_counties_total"] = len(selected)
        match_rows.append(matches)
        for sample in ["full", "overlap", "long"]:
            d_base = hh.loc[
                r10.sample_filter(hh, sample)
                & pd.to_numeric(hh["county_id_num"], errors="coerce").astype("Int64").isin(selected)
            ].copy()
            d = add_outcome_trends(d_base, outcome)
            d_prov, prov_regs = r10c.add_province_trends(d)
            specs = {
                "matched_unit_year": (d, ["unit_id", "year"], ["adm_high_t"]),
                "matched_pre_outcome_trends": (d, ["unit_id", "year"], ["adm_high_t", "pre_mean_trend", "pre_slope_trend"]),
                "matched_future_and_pre_trends": (d, ["unit_id", "year"], ["adm_high_t", "ever_high_trend", "pre_mean_trend", "pre_slope_trend"]),
                "matched_prov_linear_trends": (d_prov, ["unit_id", "year"], ["adm_high_t"] + prov_regs),
                "matched_unit_provyear": (d, ["unit_id", "prov_year"], ["adm_high_t"]),
            }
            for spec, (df, fe_cols, regs) in specs.items():
                try:
                    fit, kept, _ = r10c.fit_fe_extra(df, outcome, regs, fe_cols, min_n=100, min_clusters=8)
                    b, se, p = r10.lincom(fit, [("adm_high_t", 1.0)])
                    rows.append(
                        {
                            "outcome": outcome,
                            "sample": sample,
                            "spec": spec,
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
                    rows.append({"outcome": outcome, "sample": sample, "spec": spec, "status": f"error: {exc}"})
    return pd.DataFrame(rows), pd.concat(match_rows, ignore_index=True)


def add_event(df: pd.DataFrame, first_high: pd.Series) -> tuple[pd.DataFrame, list[str], list[str]]:
    out = df.copy()
    out["first_high_year"] = out["county_id_num"].map(first_high)
    out["ever_high"] = out["first_high_year"].notna().astype(float)
    out["event_time"] = pd.to_numeric(out["year"], errors="coerce") - pd.to_numeric(out["first_high_year"], errors="coerce")
    spec = {
        "ev_le_m4": out["event_time"].le(-4),
        "ev_m3": out["event_time"].eq(-3),
        "ev_m2": out["event_time"].eq(-2),
        "ev_0": out["event_time"].eq(0),
        "ev_1p": out["event_time"].ge(1),
    }
    regs: list[str] = []
    for c, m in spec.items():
        out[c] = np.where(out["ever_high"].eq(1), m.astype(float), 0.0)
        regs.append(c)
    return out, regs, list(spec.keys())


def run_household_matched_event(hh: pd.DataFrame, admin: pd.DataFrame, cy: pd.DataFrame) -> pd.DataFrame:
    first_high = r10c.first_treat_year(admin, "adm_high_t")
    rows: list[dict] = []
    for outcome in ["asinh_operated_area_end", "asinh_market_volume_area_zfill"]:
        selected, _ = r10c.choose_matched_controls(cy, outcome, first_high, k=5)
        d0 = hh.loc[
            r10.sample_filter(hh, "full")
            & pd.to_numeric(hh["county_id_num"], errors="coerce").astype("Int64").isin(selected)
        ].copy()
        d, regs, ordered = add_event(d0, first_high)
        for fe_name, fe_cols in {"matched_unit_year": ["unit_id", "year"], "matched_unit_provyear": ["unit_id", "prov_year"]}.items():
            try:
                fit, kept, _ = r10c.fit_fe_extra(d, outcome, regs, fe_cols, min_n=100, min_clusters=8)
                for ev in ordered:
                    b, se, p = r10.lincom(fit, [(ev, 1.0)])
                    rows.append(
                        {
                            "outcome": outcome,
                            "spec": fe_name,
                            "event_term": ev,
                            "b": b,
                            "se": se,
                            "p": p,
                            "N": int(len(kept)),
                            "counties": int(kept["county_id_num"].nunique()),
                            "treated_counties": int(kept.loc[kept["ever_high"].eq(1), "county_id_num"].nunique()),
                            "status": "ok",
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                rows.append({"outcome": outcome, "spec": fe_name, "event_term": "model", "status": f"error: {exc}"})
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
    for c in ["b", "se", "p"]:
        if c in show.columns:
            show[c] = show[c].map(fmt)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, r in show[cols].iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def write_memo(main: pd.DataFrame, event: pd.DataFrame, matches: pd.DataFrame) -> None:
    op = main[
        main["status"].eq("ok")
        & main["outcome"].eq("asinh_operated_area_end")
    ].sort_values(["sample", "spec"])
    flow = main[
        main["status"].eq("ok")
        & main["sample"].eq("full")
        & main["outcome"].isin(["asinh_market_volume_area_zfill", "asinh_transfer_in_area_zfill", "any_transfer_in_zfill"])
        & main["spec"].isin(["matched_unit_year", "matched_pre_outcome_trends", "matched_unit_provyear"])
    ].sort_values(["outcome", "spec"])
    evop = event[
        event["status"].eq("ok")
        & event["outcome"].eq("asinh_operated_area_end")
        & event["spec"].eq("matched_unit_year")
    ].sort_values("event_term")
    support = matches.groupby("outcome").agg(
        treated_pairs=("treated_county", "count"),
        controls=("control_county", "nunique"),
        matched_counties_total=("matched_counties_total", "max"),
    ).reset_index()
    lines = [
        "# Round 10D household matched FOBS memo, 2026-05-02",
        "",
        "## Bottom line",
        "",
        "Matching counties on FOBS pre-2009-2014 levels/slopes and then estimating at the household-year level preserves more information than county-year aggregation. "
        "This is the preferred robustness check if we want a stricter comparator set without abandoning household fixed effects.",
        "",
        "## Operated area",
        "",
        md_table(op, ["sample", "spec", "b", "se", "p", "N", "counties", "treated_counties"], 24),
        "",
        "## Flow outcomes",
        "",
        md_table(flow, ["outcome", "spec", "b", "se", "p", "N", "counties", "treated_counties"], 18),
        "",
        "## Event check",
        "",
        md_table(evop, ["event_term", "b", "se", "p", "N", "counties", "treated_counties"], 10),
        "",
        "## Match support",
        "",
        md_table(support, ["outcome", "treated_pairs", "controls", "matched_counties_total"], 8),
    ]
    (OUT / "Round10D_FOBS_HouseholdMatched_Memo_20260502.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    hh, admin, cy = load()
    main_res, matches = run_household_matched(hh, admin, cy)
    event = run_household_matched_event(hh, admin, cy)
    main_res.to_csv(TABLES / "Round10D_household_matched_main.csv", index=False, encoding="utf-8-sig")
    event.to_csv(TABLES / "Round10D_household_matched_event.csv", index=False, encoding="utf-8-sig")
    matches.to_csv(TABLES / "Round10D_household_matching_pairs.csv", index=False, encoding="utf-8-sig")
    write_memo(main_res, event, matches)
    print(f"Wrote Round 10D outputs to {OUT}")


if __name__ == "__main__":
    main()
