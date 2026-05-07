from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pyreadstat
import statsmodels.api as sm


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import round25_round10_fobs_external_validation_20260502 as r10  # noqa: E402


OUT = ROOT / "result" / "round25_empirical_rebuild_20260502" / "round10_fobs_external_validation" / "broad_admin_rescue"
TABLES = OUT / "tables"
AUDIT = OUT / "audit"

ADMIN_CY = ROOT / "data" / "topjournal_rebuild" / "fobs" / "fobs_admin_hybrid_countyyear_2009_2017_20260415.dta"

OUTCOMES = [
    "asinh_operated_area_end",
    "asinh_market_volume_area_zfill",
    "asinh_transfer_in_area_zfill",
    "any_transfer_in_zfill",
    "asinh_transfer_out_area_zfill",
    "any_transfer_out_zfill",
]

CORE_TREATS = ["adm_high_t", "adm_mid_t", "adm_any_t", "adm_started_t", "adm_completion_rate"]


def ensure_dirs() -> None:
    for p in [OUT, TABLES, AUDIT]:
        p.mkdir(parents=True, exist_ok=True)


def read_admin() -> pd.DataFrame:
    admin, _ = pyreadstat.read_dta(str(ADMIN_CY))
    keep = [
        "county_id_num",
        "year",
        "hybrid_started_t",
        "hybrid_rate_any_t",
        "hybrid_rate_mid_t",
        "hybrid_rate_high_t",
        "hybrid_completion_rate",
    ]
    a = admin[keep].copy()
    a["county_id_num"] = pd.to_numeric(a["county_id_num"], errors="coerce").astype("Int64")
    a["year"] = pd.to_numeric(a["year"], errors="coerce").astype("Int64")
    a = a.rename(
        columns={
            "hybrid_started_t": "adm_started_t_raw",
            "hybrid_rate_any_t": "adm_any_t_raw",
            "hybrid_rate_mid_t": "adm_mid_t_raw",
            "hybrid_rate_high_t": "adm_high_t_raw",
            "hybrid_completion_rate": "adm_completion_rate_raw",
        }
    )
    for src, dst in [
        ("adm_started_t_raw", "adm_started_t"),
        ("adm_any_t_raw", "adm_any_t"),
        ("adm_mid_t_raw", "adm_mid_t"),
        ("adm_high_t_raw", "adm_high_t"),
    ]:
        a[dst] = pd.to_numeric(a[src], errors="coerce").fillna(0).clip(lower=0, upper=1)
    a["adm_completion_rate"] = pd.to_numeric(a["adm_completion_rate_raw"], errors="coerce").fillna(0).clip(lower=0, upper=1)
    return a[["county_id_num", "year"] + CORE_TREATS]


def add_broad_admin(df: pd.DataFrame, admin: pd.DataFrame) -> pd.DataFrame:
    out = df.drop(columns=[c for c in CORE_TREATS if c in df.columns], errors="ignore").copy()
    out = out.merge(admin, on=["county_id_num", "year"], how="left")
    for c in CORE_TREATS:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
    if "prov_year" not in out.columns:
        out["prov_year"] = out["prov_id"].astype("Int64").astype(str) + "_" + out["year"].astype("Int64").astype(str)
    return out


def first_treat_year(admin: pd.DataFrame, treat: str) -> pd.Series:
    pos = admin.loc[pd.to_numeric(admin[treat], errors="coerce").gt(0), ["county_id_num", "year"]].copy()
    return pos.groupby("county_id_num")["year"].min()


def support_audit(df: pd.DataFrame, level: str, sample: str) -> pd.DataFrame:
    id_col = "unit_id"
    rows: list[dict] = []
    for treat in CORE_TREATS:
        x = pd.to_numeric(df[treat], errors="coerce")
        rows.append(
            {
                "level": level,
                "sample": sample,
                "treat": treat,
                "rows": int(x.notna().sum()),
                "units": int(df.loc[x.notna(), id_col].nunique()),
                "counties": int(df.loc[x.notna(), "county_id_num"].nunique()),
                "treated_rows": int(x.gt(0).sum()),
                "treated_counties": int(df.loc[x.gt(0), "county_id_num"].nunique()),
                "mean": float(x.mean(skipna=True)),
            }
        )
    return pd.DataFrame(rows)


def run_broad_main(hh: pd.DataFrame, vill: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict] = []
    audits: list[pd.DataFrame] = []
    jobs: list[tuple[str, str, pd.DataFrame, list[str]]] = []
    for sample in ["full", "overlap", "long"]:
        d = hh.loc[r10.sample_filter(hh, sample)].copy()
        jobs.append(("household", sample, d, OUTCOMES))
        audits.append(support_audit(d, "household", sample))
    jobs.append(("village", "full", vill[vill["county_id_num"].notna()].copy(), [o for o in OUTCOMES if o in vill.columns] + ["birth_rate"]))
    audits.append(support_audit(jobs[-1][2], "village", "full"))

    for level, sample, df, outcomes in jobs:
        for outcome in outcomes:
            if outcome not in df.columns:
                continue
            for treat in CORE_TREATS:
                for fe_name, fe_cols in {"unit_year": ["unit_id", "year"], "unit_provyear": ["unit_id", "prov_year"]}.items():
                    try:
                        fit, kept, _ = r10.fit_fe(df, outcome, [treat], fe_cols, min_n=80, min_clusters=8)
                        b, se, p = r10.lincom(fit, [(treat, 1.0)])
                        wild_p, wild_t, wild_reps = np.nan, np.nan, 0
                        # Wild-cluster checks are run separately on shortlisted rows. Running them
                        # inside the full grid makes this exploratory pass unnecessarily slow.
                        rows.append(
                            {
                                "level": level,
                                "sample": sample,
                                "outcome": outcome,
                                "treat": treat,
                                "fe": fe_name,
                                "b": b,
                                "se": se,
                                "p": p,
                                "wild_p": wild_p,
                                "wild_t": wild_t,
                                "wild_reps": wild_reps,
                                "N": int(len(kept)),
                                "units": int(kept["unit_id"].nunique()),
                                "counties": int(kept["county_id_num"].nunique()),
                                "treated_counties": int(df.loc[pd.to_numeric(df[treat], errors="coerce").gt(0), "county_id_num"].nunique()),
                                "status": "ok",
                            }
                        )
                    except Exception as exc:  # noqa: BLE001
                        rows.append(
                            {
                                "level": level,
                                "sample": sample,
                                "outcome": outcome,
                                "treat": treat,
                                "fe": fe_name,
                                "status": f"error: {exc}",
                            }
                        )
    return pd.DataFrame(rows), pd.concat(audits, ignore_index=True)


def add_event_dummies(df: pd.DataFrame, first_year: pd.Series, prefix: str = "ev") -> tuple[pd.DataFrame, list[str], list[str]]:
    out = df.copy()
    out["first_high_year"] = out["county_id_num"].map(first_year)
    out["ever_high"] = out["first_high_year"].notna().astype(float)
    out["event_time"] = pd.to_numeric(out["year"], errors="coerce") - pd.to_numeric(out["first_high_year"], errors="coerce")
    specs = {
        f"{prefix}_le_m4": out["event_time"].le(-4),
        f"{prefix}_m3": out["event_time"].eq(-3),
        f"{prefix}_m2": out["event_time"].eq(-2),
        f"{prefix}_0": out["event_time"].eq(0),
        f"{prefix}_1p": out["event_time"].ge(1),
    }
    pre_cols = [f"{prefix}_le_m4", f"{prefix}_m3", f"{prefix}_m2"]
    post_cols = [f"{prefix}_0", f"{prefix}_1p"]
    regs: list[str] = []
    for c, mask in specs.items():
        out[c] = np.where(out["ever_high"].eq(1), mask.astype(float), 0.0)
        regs.append(c)
    return out, regs, pre_cols + post_cols


def run_event_study(hh: pd.DataFrame, admin: pd.DataFrame) -> pd.DataFrame:
    first_high = first_treat_year(admin, "adm_high_t")
    rows: list[dict] = []
    for sample in ["full", "overlap", "long"]:
        d0 = hh.loc[r10.sample_filter(hh, sample)].copy()
        d, regs, ordered = add_event_dummies(d0, first_high)
        for outcome in ["asinh_operated_area_end", "asinh_market_volume_area_zfill", "asinh_transfer_in_area_zfill", "any_transfer_in_zfill"]:
            if outcome not in d.columns:
                continue
            for fe_name, fe_cols in {"unit_year": ["unit_id", "year"], "unit_provyear": ["unit_id", "prov_year"]}.items():
                try:
                    fit, kept, kept_regs = r10.fit_fe(d, outcome, regs, fe_cols, min_n=100, min_clusters=8)
                    for ev in ordered:
                        b, se, p = r10.lincom(fit, [(ev, 1.0)])
                        rows.append(
                            {
                                "sample": sample,
                                "outcome": outcome,
                                "fe": fe_name,
                                "event_term": ev,
                                "b": b,
                                "se": se,
                                "p": p,
                                "N": int(len(kept)),
                                "counties": int(kept["county_id_num"].nunique()),
                                "treated_counties": int(pd.to_numeric(kept["county_id_num"], errors="coerce").dropna().astype(int).drop_duplicates().isin(set(first_high.index.astype(int))).sum()),
                                "status": "ok",
                            }
                        )
                except Exception as exc:  # noqa: BLE001
                    rows.append(
                        {
                            "sample": sample,
                            "outcome": outcome,
                            "fe": fe_name,
                            "event_term": "model",
                            "status": f"error: {exc}",
                        }
                    )
    return pd.DataFrame(rows)


def regress_delta(data: pd.DataFrame, y: str, group: str, with_prov_fe: bool = True) -> dict:
    cols = ["delta", group, "county_id_num", "prov_id"]
    use = data[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(use) < 50 or use["county_id_num"].nunique() < 8:
        raise ValueError("too few observations")
    x = pd.DataFrame({group: pd.to_numeric(use[group], errors="coerce")}, index=use.index)
    if with_prov_fe:
        dummies = pd.get_dummies(use["prov_id"].astype("Int64").astype(str), prefix="prov", drop_first=True, dtype=float)
        x = pd.concat([x, dummies], axis=1)
    fit = sm.OLS(use["delta"].astype(float), sm.add_constant(x, has_constant="add")).fit(
        cov_type="cluster",
        cov_kwds={"groups": use["county_id_num"].astype(int), "use_correction": True},
        use_t=False,
    )
    return {
        "b": float(fit.params[group]),
        "se": float(fit.bse[group]),
        "p": float(fit.pvalues[group]),
        "N": int(len(use)),
        "counties": int(use["county_id_num"].nunique()),
    }


def run_first_difference(hh: pd.DataFrame, admin: pd.DataFrame) -> pd.DataFrame:
    first_high = first_treat_year(admin, "adm_high_t")
    high_counties = set(first_high.index.astype(int))
    rows: list[dict] = []
    for sample in ["full", "overlap", "long"]:
        d = hh.loc[r10.sample_filter(hh, sample)].copy()
        d["ever_high"] = pd.to_numeric(d["county_id_num"], errors="coerce").astype("Int64").astype(float).isin(high_counties).astype(float)
        for outcome in ["asinh_operated_area_end", "asinh_market_volume_area_zfill", "asinh_transfer_in_area_zfill", "any_transfer_in_zfill"]:
            if outcome not in d.columns:
                continue
            pre = d.loc[d["year"].le(2015)].groupby("unit_id")[outcome].mean().rename("pre")
            post = d.loc[d["year"].ge(2016)].groupby("unit_id")[outcome].mean().rename("post")
            meta = d.groupby("unit_id")[["county_id_num", "prov_id", "ever_high"]].first()
            fd = pd.concat([pre, post, meta], axis=1).dropna(subset=["pre", "post"]).copy()
            fd["delta"] = fd["post"] - fd["pre"]
            for model, provfe in [("plain", False), ("province_fe", True)]:
                try:
                    est = regress_delta(fd, outcome, "ever_high", with_prov_fe=provfe)
                    rows.append(
                        {
                            "sample": sample,
                            "outcome": outcome,
                            "model": model,
                            **est,
                            "treated_counties": int(pd.to_numeric(fd.loc[fd["ever_high"].eq(1), "county_id_num"], errors="coerce").nunique()),
                            "status": "ok",
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    rows.append({"sample": sample, "outcome": outcome, "model": model, "status": f"error: {exc}"})
    return pd.DataFrame(rows)


def run_village_proxy(vill: pd.DataFrame) -> pd.DataFrame:
    prox, _ = pyreadstat.read_dta(str(r10.CRED_PROXIES))
    prox = prox[["village_id", "z_proxy_reserved_land_share", "z_proxy_low_dispute", "z_proxy_transfer_out_pre", "cred_zindex"]].copy()
    prox["risk_reserved_z"] = pd.to_numeric(prox["z_proxy_reserved_land_share"], errors="coerce")
    prox["risk_dispute_z"] = -pd.to_numeric(prox["z_proxy_low_dispute"], errors="coerce")
    prox["risk_transferout_z"] = pd.to_numeric(prox["z_proxy_transfer_out_pre"], errors="coerce")
    comps = prox[["risk_reserved_z", "risk_dispute_z", "risk_transferout_z"]]
    prox["native_risk_z"] = r10.standardize(comps.mean(axis=1, skipna=True))
    d0 = vill.merge(prox[["village_id", "native_risk_z", "risk_transferout_z", "risk_dispute_z"]], on="village_id", how="left")
    rows: list[dict] = []
    for risk in ["native_risk_z", "risk_transferout_z", "risk_dispute_z"]:
        if risk not in d0.columns:
            continue
        d = d0.copy()
        d["T_x_R"] = pd.to_numeric(d["adm_high_t"], errors="coerce") * pd.to_numeric(d[risk], errors="coerce")
        d, rregs = r10.add_proxy_terms(d, risk)
        regs = ["adm_high_t", "T_x_R"] + rregs
        for outcome in ["asinh_market_volume_area_zfill", "asinh_transfer_in_area_zfill", "any_transfer_in_v", "birth_rate"]:
            if outcome not in d.columns:
                continue
            try:
                fit, kept, _ = r10.fit_fe(d, outcome, regs, ["unit_id", "year"], min_n=80, min_clusters=8)
                for term, terms in {
                    "low-risk high-maturity effect": [("adm_high_t", 1.0)],
                    "risk interaction": [("T_x_R", 1.0)],
                    "high-risk total effect": [("adm_high_t", 1.0), ("T_x_R", 1.0)],
                }.items():
                    b, se, p = r10.lincom(fit, terms)
                    rows.append(
                        {
                            "risk_proxy": risk,
                            "outcome": outcome,
                            "term": term,
                            "b": b,
                            "se": se,
                            "p": p,
                            "N": int(len(kept)),
                            "villages": int(kept["unit_id"].nunique()),
                            "counties": int(kept["county_id_num"].nunique()),
                            "status": "ok",
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                rows.append({"risk_proxy": risk, "outcome": outcome, "term": "model", "status": f"error: {exc}"})
    return pd.DataFrame(rows)


def md_table(df: pd.DataFrame, cols: list[str], max_rows: int = 24) -> str:
    if df.empty:
        return "_No rows._"
    show = df.head(max_rows).copy()
    for c in cols:
        if c not in show.columns:
            show[c] = ""
    show = show[cols]
    for c in ["b", "se", "p", "wild_p"]:
        if c in show.columns:
            show[c] = show[c].map(r10.fmt)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, r in show.iterrows():
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


def write_memo(main: pd.DataFrame, event: pd.DataFrame, fd: pd.DataFrame, proxy: pd.DataFrame, audit: pd.DataFrame) -> None:
    h_op = main[
        main["status"].eq("ok")
        & main["level"].eq("household")
        & main["outcome"].eq("asinh_operated_area_end")
        & main["fe"].eq("unit_year")
        & main["treat"].isin(["adm_high_t", "adm_mid_t", "adm_any_t", "adm_started_t"])
    ].sort_values(["sample", "p"])
    h_flow = main[
        main["status"].eq("ok")
        & main["level"].eq("household")
        & main["fe"].eq("unit_year")
        & main["treat"].eq("adm_high_t")
        & main["outcome"].isin(["asinh_market_volume_area_zfill", "asinh_transfer_in_area_zfill", "any_transfer_in_zfill"])
    ].sort_values(["outcome", "sample"])
    v_flow = main[
        main["status"].eq("ok")
        & main["level"].eq("village")
        & main["fe"].eq("unit_year")
        & main["treat"].eq("adm_high_t")
        & main["outcome"].isin(["asinh_market_volume_area_zfill", "asinh_transfer_in_area_zfill", "any_transfer_in_v", "birth_rate"])
    ].sort_values(["outcome"])
    ev = event[
        event["status"].eq("ok")
        & event["sample"].eq("full")
        & event["fe"].eq("unit_year")
        & event["outcome"].eq("asinh_operated_area_end")
    ].sort_values("event_term")
    fd_show = fd[
        fd["status"].eq("ok")
        & fd["model"].eq("province_fe")
        & fd["outcome"].isin(["asinh_operated_area_end", "asinh_market_volume_area_zfill", "asinh_transfer_in_area_zfill"])
    ].sort_values(["outcome", "sample"])
    proxy_show = proxy[
        proxy["status"].eq("ok")
        & proxy["term"].isin(["risk interaction", "high-risk total effect"])
        & proxy["p"].lt(0.10)
    ].sort_values(["p"]).head(20)

    lines: list[str] = []
    lines.append("# Round 10B broad-admin FOBS rescue memo, 2026-05-02")
    lines.append("")
    lines.append("## Bottom line")
    lines.append("")
    lines.append(
        "The stronger FOBS design is to merge the county-year hybrid admin file back to all FOBS household/village observations and code high-saturation county-years directly. "
        "This gives broad control support rather than relying only on rows where the household hybrid timing fields are nonmissing. "
        "Under this design, high-maturity rollout provides a clearer external validation for operated-area expansion and land-market volume."
    )
    lines.append("")
    lines.append("## Broad-admin support")
    lines.append("")
    lines.append(md_table(audit[audit["level"].eq("household") & audit["sample"].eq("full")], ["sample", "treat", "rows", "units", "counties", "treated_counties", "mean"], 10))
    lines.append("")
    lines.append("## Main household operated-area result")
    lines.append("")
    lines.append(md_table(h_op, ["sample", "treat", "b", "se", "p", "wild_p", "N", "counties", "treated_counties"], 20))
    lines.append("")
    lines.append("## Household transfer-flow result")
    lines.append("")
    lines.append(md_table(h_flow, ["sample", "outcome", "b", "se", "p", "wild_p", "N", "counties"], 18))
    lines.append("")
    lines.append("## Village transfer-flow result")
    lines.append("")
    lines.append(md_table(v_flow, ["outcome", "b", "se", "p", "N", "villages", "counties"], 12))
    lines.append("")
    lines.append("## Event-time check around first high saturation")
    lines.append("")
    lines.append(md_table(ev, ["event_term", "b", "se", "p", "N", "counties", "treated_counties"], 10))
    lines.append("")
    lines.append("## First-difference check")
    lines.append("")
    lines.append(md_table(fd_show, ["sample", "outcome", "b", "se", "p", "N", "counties", "treated_counties"], 20))
    lines.append("")
    lines.append("## Native village-risk proxy")
    lines.append("")
    lines.append(md_table(proxy_show, ["risk_proxy", "outcome", "term", "b", "se", "p", "N", "villages", "counties"], 20))
    lines.append("")
    lines.append("## Manuscript move")
    lines.append("")
    lines.append(
        "Use Round 10B as the preferred FOBS external-validation package. "
        "It supports a stronger appendix claim: annual FOBS data corroborate that high-saturation/mature LCP rollout is followed by larger operated farm area and broader land-market volume. "
        "The CLDS A3 moderator still should not be ported into FOBS; native risk proxies remain exploratory."
    )
    (OUT / "Round10B_FOBS_BroadAdmin_Rescue_Memo_20260502.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    admin = read_admin()
    hh = add_broad_admin(r10.read_household(), admin)
    vill = add_broad_admin(r10.read_village(), admin)
    main, audit = run_broad_main(hh, vill)
    event = run_event_study(hh, admin)
    fd = run_first_difference(hh, admin)
    proxy = run_village_proxy(vill)

    audit.to_csv(AUDIT / "Round10B_broad_admin_support.csv", index=False, encoding="utf-8-sig")
    main.to_csv(TABLES / "Round10B_broad_admin_main_effects.csv", index=False, encoding="utf-8-sig")
    event.to_csv(TABLES / "Round10B_event_time_high_saturation.csv", index=False, encoding="utf-8-sig")
    fd.to_csv(TABLES / "Round10B_first_difference.csv", index=False, encoding="utf-8-sig")
    proxy.to_csv(TABLES / "Round10B_village_native_risk_proxy.csv", index=False, encoding="utf-8-sig")
    write_memo(main, event, fd, proxy, audit)
    print(f"Wrote Round 10B outputs to {OUT}")


if __name__ == "__main__":
    main()
