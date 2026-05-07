from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import round25_round10_fobs_external_validation_20260502 as r10  # noqa: E402
import round25_round10b_fobs_broad_admin_rescue_20260502 as r10b  # noqa: E402


OUT = ROOT / "result" / "round25_empirical_rebuild_20260502" / "round10_fobs_external_validation" / "trend_match_rescue"
TABLES = OUT / "tables"

OUTCOMES = [
    "asinh_operated_area_end",
    "asinh_market_volume_area_zfill",
    "asinh_transfer_in_area_zfill",
    "any_transfer_in_zfill",
]


def ensure_dirs() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)


def first_treat_year(admin: pd.DataFrame, treat: str = "adm_high_t") -> pd.Series:
    pos = admin.loc[pd.to_numeric(admin[treat], errors="coerce").gt(0), ["county_id_num", "year"]].copy()
    return pos.groupby("county_id_num")["year"].min()


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    admin = r10b.read_admin()
    hh = r10b.add_broad_admin(r10.read_household(), admin)
    first_high = first_treat_year(admin, "adm_high_t")
    hh["ever_high"] = pd.to_numeric(hh["county_id_num"], errors="coerce").astype("Int64").isin(first_high.index).astype(float)
    hh["year_c"] = pd.to_numeric(hh["year"], errors="coerce").astype(float) - 2014.0
    return hh, admin


def pre_county_features(hh: pd.DataFrame, outcome: str, pre_end: int = 2014) -> pd.DataFrame:
    d = hh.loc[hh["year"].le(pre_end), ["county_id_num", "year", "prov_id", outcome]].replace([np.inf, -np.inf], np.nan).dropna().copy()
    rows: list[dict] = []
    for county, g in d.groupby("county_id_num", dropna=True):
        years = pd.to_numeric(g["year"], errors="coerce").astype(float)
        y = pd.to_numeric(g[outcome], errors="coerce").astype(float)
        if y.notna().sum() < 3 or years.nunique() < 2:
            continue
        x = years - years.mean()
        slope = float(np.dot(x, y - y.mean()) / np.dot(x, x)) if np.dot(x, x) > 0 else 0.0
        rows.append(
            {
                "county_id_num": county,
                f"{outcome}_pre_mean": float(y.mean()),
                f"{outcome}_pre_slope": slope,
                f"{outcome}_pre_2014": float(g.loc[g["year"].eq(2014), outcome].mean()) if g["year"].eq(2014).any() else np.nan,
                f"{outcome}_pre_nyears": int(years.nunique()),
                "prov_id_pre": g["prov_id"].dropna().iloc[0] if g["prov_id"].notna().any() else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    for c in [f"{outcome}_pre_mean", f"{outcome}_pre_slope", f"{outcome}_pre_2014"]:
        out[f"z_{c}"] = r10.standardize(pd.to_numeric(out[c], errors="coerce"))
    return out


def fit_fe_extra(
    data: pd.DataFrame,
    y: str,
    regressors: list[str],
    fe_cols: list[str],
    min_n: int = 80,
    min_clusters: int = 8,
) -> tuple[object, pd.DataFrame, list[str]]:
    cols = [y, "county_id_num"] + fe_cols + regressors
    use = data[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(use) < min_n or use["county_id_num"].nunique() < min_clusters:
        raise ValueError("too few observations")
    res, kept = r10.r7.residualize(use, [y] + regressors, fe_cols)
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
    fit = sm.OLS(res[y].astype(float), res[keep_cols].astype(float)).fit(
        cov_type="cluster",
        cov_kwds={"groups": kept["county_id_num"].astype(int), "use_correction": True},
        use_t=False,
    )
    return fit, kept, keep_cols


def add_province_trends(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    out = df.copy()
    regs: list[str] = []
    provs = sorted(pd.to_numeric(out["prov_id"], errors="coerce").dropna().astype(int).unique().tolist())
    for p in provs[1:]:
        c = f"provtrend_{p}"
        out[c] = np.where(pd.to_numeric(out["prov_id"], errors="coerce").eq(p), out["year_c"], 0.0)
        regs.append(c)
    return out, regs


def run_trend_controls(hh: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for sample in ["full", "overlap", "long"]:
        d_base = hh.loc[r10.sample_filter(hh, sample)].copy()
        for outcome in OUTCOMES:
            feat = pre_county_features(d_base, outcome)
            d0 = d_base.merge(feat[["county_id_num", f"z_{outcome}_pre_mean", f"z_{outcome}_pre_slope"]], on="county_id_num", how="left")
            d0["ever_high_trend"] = d0["ever_high"] * d0["year_c"]
            d0["pre_mean_trend"] = pd.to_numeric(d0[f"z_{outcome}_pre_mean"], errors="coerce") * d0["year_c"]
            d0["pre_slope_trend"] = pd.to_numeric(d0[f"z_{outcome}_pre_slope"], errors="coerce") * d0["year_c"]
            d_prov, prov_regs = add_province_trends(d0)
            specs = {
                "unit_year": (d0, ["unit_id", "year"], ["adm_high_t"]),
                "unit_year_future_high_trend": (d0, ["unit_id", "year"], ["adm_high_t", "ever_high_trend"]),
                "unit_year_pre_outcome_trends": (d0, ["unit_id", "year"], ["adm_high_t", "pre_mean_trend", "pre_slope_trend"]),
                "unit_year_future_and_pre_trends": (
                    d0,
                    ["unit_id", "year"],
                    ["adm_high_t", "ever_high_trend", "pre_mean_trend", "pre_slope_trend"],
                ),
                "unit_year_prov_linear_trends": (d_prov, ["unit_id", "year"], ["adm_high_t"] + prov_regs),
                "unit_provyear": (d0, ["unit_id", "prov_year"], ["adm_high_t"]),
            }
            for spec, (df, fe_cols, regs) in specs.items():
                try:
                    fit, kept, _ = fit_fe_extra(df, outcome, regs, fe_cols, min_n=100, min_clusters=8)
                    b, se, p = r10.lincom(fit, [("adm_high_t", 1.0)])
                    rows.append(
                        {
                            "sample": sample,
                            "outcome": outcome,
                            "spec": spec,
                            "b": b,
                            "se": se,
                            "p": p,
                            "N": int(len(kept)),
                            "units": int(kept["unit_id"].nunique()),
                            "counties": int(kept["county_id_num"].nunique()),
                            "treated_counties": int(kept.loc[pd.to_numeric(kept["adm_high_t"], errors="coerce").gt(0), "county_id_num"].nunique())
                            if "adm_high_t" in kept.columns
                            else np.nan,
                            "status": "ok",
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    rows.append({"sample": sample, "outcome": outcome, "spec": spec, "status": f"error: {exc}"})
    return pd.DataFrame(rows)


def county_year_panel(hh: pd.DataFrame) -> pd.DataFrame:
    agg = {o: "mean" for o in OUTCOMES if o in hh.columns}
    agg.update({"adm_high_t": "max", "adm_mid_t": "max", "adm_any_t": "max", "adm_started_t": "max", "prov_id": "first"})
    cy = (
        hh.loc[hh["county_id_num"].notna()]
        .groupby(["county_id_num", "year"], dropna=True)
        .agg(agg | {"unit_id": "count"})
        .rename(columns={"unit_id": "hh_obs"})
        .reset_index()
    )
    cy["unit_id"] = cy["county_id_num"].astype("Int64").astype(str)
    cy["prov_year"] = cy["prov_id"].astype("Int64").astype(str) + "_" + cy["year"].astype("Int64").astype(str)
    return cy


def choose_matched_controls(cy: pd.DataFrame, outcome: str, first_high: pd.Series, k: int = 5) -> tuple[set[int], pd.DataFrame]:
    feat = pre_county_features(cy.rename(columns={"hh_obs": "_hh_obs"}), outcome)
    high = set(first_high.index.astype(int))
    available = feat.dropna(subset=[f"z_{outcome}_pre_mean", f"z_{outcome}_pre_slope"]).copy()
    available["county_id_num_i"] = pd.to_numeric(available["county_id_num"], errors="coerce").astype(int)
    treated = available[available["county_id_num_i"].isin(high)].copy()
    controls = available[~available["county_id_num_i"].isin(high)].copy()
    selected: set[int] = set(treated["county_id_num_i"].tolist())
    rows: list[dict] = []
    for _, tr in treated.iterrows():
        pool = controls.copy()
        same_prov = pool[pd.to_numeric(pool["prov_id_pre"], errors="coerce").eq(pd.to_numeric(tr["prov_id_pre"], errors="coerce"))]
        if len(same_prov) >= k:
            pool = same_prov
            match_scope = "same_province"
        else:
            match_scope = "national"
        mat = pool[[f"z_{outcome}_pre_mean", f"z_{outcome}_pre_slope", f"z_{outcome}_pre_2014"]].copy()
        tr_vec = tr[[f"z_{outcome}_pre_mean", f"z_{outcome}_pre_slope", f"z_{outcome}_pre_2014"]].astype(float)
        mat = mat.fillna(0.0)
        tr_vec = tr_vec.fillna(0.0)
        pool = pool.assign(dist=np.sqrt(((mat - tr_vec.to_numpy()) ** 2).sum(axis=1)))
        for _, m in pool.sort_values("dist").head(k).iterrows():
            cid = int(m["county_id_num_i"])
            selected.add(cid)
            rows.append(
                {
                    "outcome": outcome,
                    "treated_county": int(tr["county_id_num_i"]),
                    "control_county": cid,
                    "dist": float(m["dist"]),
                    "scope": match_scope,
                }
            )
    return selected, pd.DataFrame(rows)


def run_matched_county_did(cy: pd.DataFrame, admin: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    first_high = first_treat_year(admin, "adm_high_t")
    rows: list[dict] = []
    match_rows: list[pd.DataFrame] = []
    for outcome in OUTCOMES:
        selected, matches = choose_matched_controls(cy, outcome, first_high, k=5)
        match_rows.append(matches)
        d = cy[pd.to_numeric(cy["county_id_num"], errors="coerce").astype(int).isin(selected)].copy()
        for fe_name, fe_cols in {
            "county_year": ["unit_id", "year"],
            "county_provyear": ["unit_id", "prov_year"],
        }.items():
            try:
                fit, kept, _ = fit_fe_extra(d, outcome, ["adm_high_t"], fe_cols, min_n=60, min_clusters=8)
                b, se, p = r10.lincom(fit, [("adm_high_t", 1.0)])
                rows.append(
                    {
                        "outcome": outcome,
                        "spec": fe_name,
                        "b": b,
                        "se": se,
                        "p": p,
                        "N": int(len(kept)),
                        "counties": int(kept["county_id_num"].nunique()),
                        "treated_counties": int(kept.loc[pd.to_numeric(kept["adm_high_t"], errors="coerce").gt(0), "county_id_num"].nunique()),
                        "status": "ok",
                    }
                )
            except Exception as exc:  # noqa: BLE001
                rows.append({"outcome": outcome, "spec": fe_name, "status": f"error: {exc}"})
    return pd.DataFrame(rows), pd.concat(match_rows, ignore_index=True)


def add_event_dummies(df: pd.DataFrame, first_high: pd.Series) -> tuple[pd.DataFrame, list[str], list[str]]:
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
    regs = []
    ordered = list(spec.keys())
    for c, m in spec.items():
        out[c] = np.where(out["ever_high"].eq(1), m.astype(float), 0.0)
        regs.append(c)
    return out, regs, ordered


def run_matched_event(cy: pd.DataFrame, admin: pd.DataFrame) -> pd.DataFrame:
    first_high = first_treat_year(admin, "adm_high_t")
    rows: list[dict] = []
    for outcome in ["asinh_operated_area_end", "asinh_market_volume_area_zfill"]:
        selected, _ = choose_matched_controls(cy, outcome, first_high, k=5)
        d0 = cy[pd.to_numeric(cy["county_id_num"], errors="coerce").astype(int).isin(selected)].copy()
        d, regs, ordered = add_event_dummies(d0, first_high)
        for fe_name, fe_cols in {"county_year": ["unit_id", "year"], "county_provyear": ["unit_id", "prov_year"]}.items():
            try:
                fit, kept, _ = fit_fe_extra(d, outcome, regs, fe_cols, min_n=60, min_clusters=8)
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
    for c in ["b", "se", "p", "dist"]:
        if c in show.columns:
            show[c] = show[c].map(fmt)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, r in show[cols].iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def write_memo(trend: pd.DataFrame, mdid: pd.DataFrame, mevent: pd.DataFrame, matches: pd.DataFrame) -> None:
    op_trend = trend[
        trend["status"].eq("ok")
        & trend["outcome"].eq("asinh_operated_area_end")
        & trend["sample"].isin(["full", "overlap", "long"])
    ].sort_values(["sample", "spec"])
    flow_trend = trend[
        trend["status"].eq("ok")
        & trend["sample"].eq("full")
        & trend["outcome"].isin(["asinh_market_volume_area_zfill", "asinh_transfer_in_area_zfill", "any_transfer_in_zfill"])
        & trend["spec"].isin(["unit_year_future_and_pre_trends", "unit_provyear"])
    ].sort_values(["outcome", "spec"])
    evop = mevent[
        mevent["status"].eq("ok")
        & mevent["outcome"].eq("asinh_operated_area_end")
        & mevent["spec"].eq("county_year")
    ].sort_values("event_term")
    lines = [
        "# Round 10C FOBS trend/matched rescue memo, 2026-05-02",
        "",
        "## Bottom line",
        "",
        "This addendum tests whether the broad-admin operated-area result survives stricter pre-trend handling. "
        "I added future-high linear trends, FOBS pre-outcome mean/slope trends, province linear trends, and matched county controls based on 2009-2014 outcome levels and slopes.",
        "",
        "## Household operated-area with trend controls",
        "",
        md_table(op_trend, ["sample", "spec", "b", "se", "p", "N", "counties", "treated_counties"], 24),
        "",
        "## Household flow outcomes under stronger trend controls",
        "",
        md_table(flow_trend, ["outcome", "spec", "b", "se", "p", "N", "counties", "treated_counties"], 18),
        "",
        "## Matched county DID",
        "",
        md_table(mdid[mdid["status"].eq("ok")].sort_values(["outcome", "spec"]), ["outcome", "spec", "b", "se", "p", "N", "counties", "treated_counties"], 16),
        "",
        "## Matched county event check",
        "",
        md_table(evop, ["event_term", "b", "se", "p", "N", "counties", "treated_counties"], 10),
        "",
        "## Matching support",
        "",
        md_table(matches.groupby("outcome").agg(treated_pairs=("treated_county", "count"), matched_controls=("control_county", "nunique"), mean_dist=("dist", "mean")).reset_index(), ["outcome", "treated_pairs", "matched_controls", "mean_dist"], 8),
        "",
        "## Manuscript implication",
        "",
        "The best FOBS role should be a conservative external validation of operated-area expansion. "
        "The trend-controlled household estimates are the key stress test; matched county models are an auxiliary check because they operate at a very aggregated level and have fewer treated counties.",
    ]
    (OUT / "Round10C_FOBS_TrendMatch_Rescue_Memo_20260502.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    hh, admin = load_data()
    trend = run_trend_controls(hh)
    cy = county_year_panel(hh)
    mdid, matches = run_matched_county_did(cy, admin)
    mevent = run_matched_event(cy, admin)
    trend.to_csv(TABLES / "Round10C_household_trend_controls.csv", index=False, encoding="utf-8-sig")
    mdid.to_csv(TABLES / "Round10C_matched_county_did.csv", index=False, encoding="utf-8-sig")
    mevent.to_csv(TABLES / "Round10C_matched_county_event.csv", index=False, encoding="utf-8-sig")
    matches.to_csv(TABLES / "Round10C_matching_pairs.csv", index=False, encoding="utf-8-sig")
    write_memo(trend, mdid, mevent, matches)
    print(f"Wrote Round 10C outputs to {OUT}")


if __name__ == "__main__":
    main()
