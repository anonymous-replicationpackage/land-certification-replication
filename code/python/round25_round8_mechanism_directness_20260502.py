from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import round7_iv_extended_search_20260430 as r7  # noqa: E402


OUT = ROOT / "result" / "round25_empirical_rebuild_20260502" / "round8_mechanism_directness"
TABLES = OUT / "tables"
AUDIT = OUT / "audit"


@dataclass(frozen=True)
class OutcomeSpec:
    name: str
    label: str
    family: str


HOUSEHOLD_OUTCOMES = [
    OutcomeSpec("any_rentin", "Any rented-in land", "land-reallocation"),
    OutcomeSpec("asinh_rentin", "asinh rented-in area", "land-reallocation"),
    OutcomeSpec("rentin_mu", "Rented-in area (mu)", "land-reallocation"),
    OutcomeSpec("any_abandon", "Any abandoned/idle land", "land-reallocation"),
    OutcomeSpec("asinh_abandon", "asinh abandoned/idle area", "land-reallocation"),
    OutcomeSpec("expand_state", "Rent-in without abandonment", "land-state"),
    OutcomeSpec("idle_state", "Abandonment without rent-in", "land-state"),
    OutcomeSpec("mixed_state", "Rent-in and abandonment both observed", "land-state"),
    OutcomeSpec("expand_minus_idle", "Expand minus idle state", "land-state"),
    OutcomeSpec("signed_asinh_net_rentin_abandon", "signed asinh(rent-in minus abandonment)", "land-state"),
    OutcomeSpec("rb_farm_any", "Any own-farm production", "farm-operation"),
    OutcomeSpec("asinh_rb_farm_cost_w99", "asinh farm cost", "farm-operation"),
    OutcomeSpec("asinh_rb_inc_farm_w99", "asinh farm income", "farm-operation"),
    OutcomeSpec("asinh_rb_farm_partsum_w99", "asinh farm partsum", "farm-operation"),
    OutcomeSpec("rb_farmwork_n", "Farm workers", "farm-operation"),
    OutcomeSpec("rb_farmwork_shr", "Farm-work share", "farm-operation"),
    OutcomeSpec("ib_nonfarm_curr_n", "Current nonfarm workers", "labor"),
    OutcomeSpec("ib_nonfarm_curr_ge2", "At least two nonfarm workers", "labor"),
    OutcomeSpec("ib_nonfarm_curr_shr", "Current nonfarm worker share", "labor"),
    OutcomeSpec("ib_migrant_work_n", "Migrant workers", "labor"),
    OutcomeSpec("ib_migrant_work_any", "Any migrant worker", "labor"),
    OutcomeSpec("rb_nonfarm_any", "Any broad nonfarm work", "labor"),
    OutcomeSpec("rb_nonfarm_n", "Broad nonfarm workers", "labor"),
    OutcomeSpec("rentin_and_nonfarm_any", "Rent-in and any nonfarm work", "co-occurrence"),
    OutcomeSpec("rentin_and_nonfarm_ge2", "Rent-in and >=2 nonfarm workers", "co-occurrence"),
    OutcomeSpec("rentin_and_farm_any", "Rent-in and own-farm production", "co-occurrence"),
    OutcomeSpec("rentin_no_abandon", "Rent-in without abandonment", "co-occurrence"),
    OutcomeSpec("nonfarm_ge2_no_rentin", ">=2 nonfarm workers without rent-in", "co-occurrence"),
]

AGG_OUTCOMES = [
    OutcomeSpec("any_rentin", "Share renting in", "aggregate-reallocation"),
    OutcomeSpec("asinh_rentin", "Mean asinh rented-in area", "aggregate-reallocation"),
    OutcomeSpec("rentin_mu", "Mean rented-in area", "aggregate-reallocation"),
    OutcomeSpec("any_abandon", "Share abandoning/idling", "aggregate-reallocation"),
    OutcomeSpec("asinh_abandon", "Mean asinh abandoned area", "aggregate-reallocation"),
    OutcomeSpec("expand_state", "Share expand state", "aggregate-reallocation"),
    OutcomeSpec("idle_state", "Share idle state", "aggregate-reallocation"),
    OutcomeSpec("expand_minus_idle", "Expand minus idle balance", "aggregate-reallocation"),
    OutcomeSpec("ib_nonfarm_curr_n", "Mean current nonfarm workers", "aggregate-labor"),
    OutcomeSpec("ib_nonfarm_curr_ge2", "Share with >=2 nonfarm workers", "aggregate-labor"),
    OutcomeSpec("rb_farm_any", "Share with own-farm production", "aggregate-farm"),
    OutcomeSpec("asinh_rb_farm_cost_w99", "Mean asinh farm cost", "aggregate-farm"),
    OutcomeSpec("asinh_rb_inc_farm_w99", "Mean asinh farm income", "aggregate-farm"),
    OutcomeSpec("rentin_and_nonfarm_ge2", "Share rent-in and >=2 nonfarm", "aggregate-cooccurrence"),
    OutcomeSpec("rentin_and_farm_any", "Share rent-in and own-farm", "aggregate-cooccurrence"),
]


def ensure_dirs() -> None:
    for path in [OUT, TABLES, AUDIT]:
        path.mkdir(parents=True, exist_ok=True)


def signed_asinh(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    return np.sign(x) * np.log1p(np.abs(x))


def safe_binary(a: pd.Series) -> pd.Series:
    x = pd.to_numeric(a, errors="coerce")
    return np.where(x.notna(), (x > 0).astype(float), np.nan)


def read_stack(scope: str = "mech", anchor: str = "completed_t") -> tuple[pd.DataFrame, pd.DataFrame]:
    panel, admin = r7.read_inputs()
    sample_counties = pd.to_numeric(
        panel.loc[panel["year"].eq(2014) & panel["s_mech_hh"].eq(1), "__cid_id"],
        errors="coerce",
    ).dropna().astype(int)
    ext, audit = r7.load_external_covariates(sample_counties)
    audit.to_csv(AUDIT / "Round8_external_files.csv", index=False, encoding="utf-8-sig")
    stack = r7.make_stack(panel, r7.admin_threshold_base(admin), ext, scope, anchor)
    stack = add_derived_outcomes(stack)
    return panel, stack


def add_derived_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["rentin_mu", "abandon_mu"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "any_rentin" not in out.columns and "rentin_mu" in out.columns:
        out["any_rentin"] = safe_binary(out["rentin_mu"])
    if "any_abandon" not in out.columns and "abandon_mu" in out.columns:
        out["any_abandon"] = safe_binary(out["abandon_mu"])
    if "rentin_mu" in out.columns and "abandon_mu" in out.columns:
        out["net_rentin_abandon_mu"] = out["rentin_mu"] - out["abandon_mu"]
        out["signed_asinh_net_rentin_abandon"] = signed_asinh(out["net_rentin_abandon_mu"])
    if {"any_rentin", "any_abandon"}.issubset(out.columns):
        r = pd.to_numeric(out["any_rentin"], errors="coerce")
        a = pd.to_numeric(out["any_abandon"], errors="coerce")
        ok = r.notna() & a.notna()
        out["expand_state"] = np.where(ok, ((r == 1) & (a == 0)).astype(float), np.nan)
        out["idle_state"] = np.where(ok, ((r == 0) & (a == 1)).astype(float), np.nan)
        out["mixed_state"] = np.where(ok, ((r == 1) & (a == 1)).astype(float), np.nan)
        out["expand_minus_idle"] = out["expand_state"] - out["idle_state"]
        out["rentin_no_abandon"] = out["expand_state"]
    if {"any_rentin", "ib_nonfarm_curr_n"}.issubset(out.columns):
        nf_any = safe_binary(out["ib_nonfarm_curr_n"])
        out["rentin_and_nonfarm_any"] = np.where(
            out["any_rentin"].notna() & pd.Series(nf_any, index=out.index).notna(),
            ((out["any_rentin"] == 1) & (nf_any == 1)).astype(float),
            np.nan,
        )
    if {"any_rentin", "ib_nonfarm_curr_ge2"}.issubset(out.columns):
        out["rentin_and_nonfarm_ge2"] = np.where(
            out["any_rentin"].notna() & out["ib_nonfarm_curr_ge2"].notna(),
            ((out["any_rentin"] == 1) & (out["ib_nonfarm_curr_ge2"] == 1)).astype(float),
            np.nan,
        )
        out["nonfarm_ge2_no_rentin"] = np.where(
            out["any_rentin"].notna() & out["ib_nonfarm_curr_ge2"].notna(),
            ((out["any_rentin"] == 0) & (out["ib_nonfarm_curr_ge2"] == 1)).astype(float),
            np.nan,
        )
    if {"any_rentin", "rb_farm_any"}.issubset(out.columns):
        out["rentin_and_farm_any"] = np.where(
            out["any_rentin"].notna() & out["rb_farm_any"].notna(),
            ((out["any_rentin"] == 1) & (out["rb_farm_any"] == 1)).astype(float),
            np.nan,
        )
    return out


def fit_resid_ols(
    data: pd.DataFrame,
    y: str,
    regressors: list[str],
    fe_cols: list[str],
    cluster_col: str = "__cid_id",
) -> tuple[object, pd.DataFrame, pd.DataFrame]:
    cols = [y, cluster_col] + fe_cols + regressors
    use = data[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(use) < 100 or use[cluster_col].nunique() < 10:
        raise ValueError("too few observations")
    res, kept = r7.residualize(use, [y] + regressors, fe_cols)
    x = res[regressors].astype(float)
    if np.linalg.matrix_rank(x.to_numpy(), tol=1e-10) < x.shape[1]:
        # Keep columns that add rank in order.
        keep_cols: list[str] = []
        rank = 0
        for col in regressors:
            cand = res[keep_cols + [col]].to_numpy()
            new_rank = np.linalg.matrix_rank(cand, tol=1e-10)
            if new_rank > rank:
                keep_cols.append(col)
                rank = new_rank
        regressors = keep_cols
        x = res[regressors].astype(float)
    clusters = kept[cluster_col].astype(int)
    fit = sm.OLS(res[y].astype(float), x).fit(
        cov_type="cluster",
        cov_kwds={"groups": clusters, "use_correction": True},
        use_t=False,
    )
    return fit, kept, res


def lincom(fit, terms: list[str]) -> tuple[float, float, float]:
    params = fit.params
    cov = fit.cov_params()
    b = sum(float(params[t]) for t in terms if t in params.index)
    var = 0.0
    present = [t for t in terms if t in params.index]
    for i in present:
        for j in present:
            var += float(cov.loc[i, j])
    se = np.sqrt(var) if var >= 0 else np.nan
    p = float(2 * stats.norm.sf(abs(b / se))) if se and np.isfinite(se) and se > 0 else np.nan
    return b, se, p


def control_cols(stack: pd.DataFrame, variant: str = "baseline_bundle") -> list[str]:
    return r7.control_cols(stack, variant)


def estimate_household(stack: pd.DataFrame, outcome_specs: list[OutcomeSpec], sample_scope: str) -> pd.DataFrame:
    rows: list[dict] = []
    fe_variants = {
        "stackyear": ["hid_stack", "year_stack"],
        "provyear": ["hid_stack", "prov_year_stack"],
    }
    for spec in outcome_specs:
        if spec.name not in stack.columns:
            rows.append({"sample_scope": sample_scope, "level": "household", "outcome": spec.name, "status": "missing"})
            continue
        for controls in ["none", "farm_income", "baseline_bundle"]:
            for fe_name, fe_cols in fe_variants.items():
                st = stack.copy()
                ccols = control_cols(st, controls)
                regressors = ["PM", "D", "DM"] + ccols
                try:
                    fit, kept, _ = fit_resid_ols(st, spec.name, regressors, fe_cols)
                    for term, terms in {
                        "low-instability DID": ["D"],
                        "high-minus-low differential": ["DM"],
                        "high-instability total": ["D", "DM"],
                    }.items():
                        b, se, p = lincom(fit, terms)
                        rows.append(
                            {
                                "level": "household",
                                "sample_scope": sample_scope,
                                "fe": fe_name,
                                "family": spec.family,
                                "outcome": spec.name,
                                "label": spec.label,
                                "controls": controls,
                                "term": term,
                                "b": b,
                                "se": se,
                                "p": p,
                                "N": int(len(kept)),
                                "clusters": int(kept["__cid_id"].nunique()),
                                "mean_y": float(st[spec.name].mean(skipna=True)),
                                "status": "ok",
                            }
                        )
                except Exception as exc:
                    rows.append(
                        {
                            "level": "household",
                            "sample_scope": sample_scope,
                            "fe": fe_name,
                            "family": spec.family,
                            "outcome": spec.name,
                            "label": spec.label,
                            "controls": controls,
                            "status": f"error: {exc}",
                        }
                    )
    return pd.DataFrame(rows)


def aggregate_stack(stack: pd.DataFrame, level: str, outcome_specs: list[OutcomeSpec]) -> pd.DataFrame:
    group_base = "village_id" if level == "village" else "__cid_id"
    df = stack.copy()
    if group_base not in df.columns:
        raise ValueError(f"missing {group_base}")
    df[f"{level}_stack"] = df[group_base].astype(str) + "_" + df["winflag"].astype(int).astype(str)
    keep_outcomes = [s.name for s in outcome_specs if s.name in df.columns]
    ccols = control_cols(df, "baseline_bundle")
    agg_dict = {c: "mean" for c in keep_outcomes + ["D", "DM", "PM"] + ccols}
    agg_dict.update({"__cid_id": "first", "prov_year_stack": "first", "hid": "count"})
    out = (
        df.groupby([f"{level}_stack", "year_stack"], dropna=False)
        .agg(agg_dict)
        .reset_index()
        .rename(columns={"hid": "hh_count"})
    )
    return out


def estimate_aggregate(stack: pd.DataFrame, level: str, outcome_specs: list[OutcomeSpec], sample_scope: str) -> pd.DataFrame:
    agg = aggregate_stack(stack, level, outcome_specs)
    rows: list[dict] = []
    fe_col = f"{level}_stack"
    fe_variants = {
        "stackyear": [fe_col, "year_stack"],
        "provyear": [fe_col, "prov_year_stack"],
    }
    for spec in outcome_specs:
        if spec.name not in agg.columns:
            rows.append({"sample_scope": sample_scope, "level": level, "outcome": spec.name, "status": "missing"})
            continue
        for controls in ["none", "baseline_bundle"]:
            ccols = [c for c in agg.columns if c.startswith("post_z_base")] if controls == "baseline_bundle" else []
            for fe_name, fe_cols in fe_variants.items():
                regressors = ["PM", "D", "DM"] + ccols
                try:
                    fit, kept, _ = fit_resid_ols(agg, spec.name, regressors, fe_cols)
                    for term, terms in {
                        "low-instability DID": ["D"],
                        "high-minus-low differential": ["DM"],
                        "high-instability total": ["D", "DM"],
                    }.items():
                        b, se, p = lincom(fit, terms)
                        rows.append(
                            {
                                "level": level,
                                "sample_scope": sample_scope,
                                "fe": fe_name,
                                "family": spec.family,
                                "outcome": spec.name,
                                "label": spec.label,
                                "controls": controls,
                                "term": term,
                                "b": b,
                                "se": se,
                                "p": p,
                                "N": int(len(kept)),
                                "clusters": int(kept["__cid_id"].nunique()),
                                "mean_y": float(agg[spec.name].mean(skipna=True)),
                                "status": "ok",
                            }
                        )
                except Exception as exc:
                    rows.append(
                        {
                            "level": level,
                            "sample_scope": sample_scope,
                            "fe": fe_name,
                            "family": spec.family,
                            "outcome": spec.name,
                            "label": spec.label,
                            "controls": controls,
                            "status": f"error: {exc}",
                        }
                    )
    return pd.DataFrame(rows)


def rentout_audit(panel: pd.DataFrame, stack: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    vars_to_check = [
        "rentout_mu",
        "any_rentout",
        "asinh_rentout",
        "rentin_mu",
        "any_rentin",
        "asinh_rentin",
        "abandon_mu",
        "any_abandon",
        "asinh_abandon",
    ]
    for source, df in [("panel", panel), ("stack", stack)]:
        for col in vars_to_check:
            if col not in df.columns:
                rows.append({"source": source, "variable": col, "status": "missing"})
                continue
            x = pd.to_numeric(df[col], errors="coerce")
            rows.append(
                {
                    "source": source,
                    "variable": col,
                    "nonmissing": int(x.notna().sum()),
                    "positive": int((x > 0).sum()),
                    "mean": float(x.mean(skipna=True)) if x.notna().any() else np.nan,
                    "status": "ok",
                }
            )
    return pd.DataFrame(rows)


def compact_tables(hh: pd.DataFrame, village: pd.DataFrame, county: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    focus = [
        "any_rentin",
        "asinh_rentin",
        "any_abandon",
        "asinh_abandon",
        "expand_state",
        "idle_state",
        "expand_minus_idle",
        "signed_asinh_net_rentin_abandon",
        "rb_farm_any",
        "asinh_rb_farm_cost_w99",
        "asinh_rb_inc_farm_w99",
        "ib_nonfarm_curr_n",
        "ib_nonfarm_curr_ge2",
        "rentin_and_nonfarm_ge2",
        "rentin_and_farm_any",
    ]
    hh_focus = hh[
        hh["status"].eq("ok")
        & hh["term"].isin(["high-minus-low differential", "high-instability total"])
        & hh["outcome"].isin(focus)
    ].copy()
    agg = pd.concat([village, county], ignore_index=True)
    agg_focus = agg[
        agg["status"].eq("ok")
        & agg["term"].isin(["high-minus-low differential", "high-instability total"])
        & agg["outcome"].isin(focus)
    ].copy()
    return hh_focus, agg_focus


def summarize(hh_focus: pd.DataFrame, agg_focus: pd.DataFrame, audit: pd.DataFrame) -> str:
    def spec_slice(
        df: pd.DataFrame,
        *,
        scope: str = "adjacent",
        controls: str = "none",
        fe: str = "stackyear",
        term: str = "high-instability total",
    ) -> pd.DataFrame:
        return df[
            df["sample_scope"].eq(scope)
            & df["controls"].eq(controls)
            & df["fe"].eq(fe)
            & df["term"].eq(term)
        ].copy()

    def cell(r: pd.Series) -> str:
        return f"{r['b']:.3f} ({r['se']:.3f}), p={r['p']:.3f}"

    def get_cell(df: pd.DataFrame, outcome: str) -> str:
        row = df[df["outcome"].eq(outcome)]
        if row.empty:
            return ""
        return cell(row.iloc[0])

    lines: list[str] = []
    lines.append("# Round 8 mechanism directness memo, 2026-05-02")
    lines.append("")
    lines.append("## What the data can and cannot show")
    lines.append("")
    rentout = audit[(audit["variable"].isin(["rentout_mu", "any_rentout", "asinh_rentout"])) & audit["source"].eq("panel")]
    if not rentout.empty:
        nonmiss = int(rentout["nonmissing"].fillna(0).max())
        lines.append(
            f"The current CLDS extracts contain no usable direct household rent-out measure: maximum nonmissing rent-out observations = {nonmiss}. "
            "The mechanism claim therefore cannot be a matched within-village supplier-to-receiver mediation test."
        )
    lines.append("")
    lines.append("## Main household mechanism pattern")
    lines.append("")
    lines.append(
        "Preferred mechanism display uses the adjacent-window stacked DID with household-stack and stack-year fixed effects. "
        "This is the same identifying window as the main stacked estimates, while heavier controls are treated as pressure tests."
    )
    lines.append("")
    show = spec_slice(hh_focus, scope="adjacent", controls="none", fe="stackyear", term="high-instability total")
    key_order = [
        "any_rentin",
        "asinh_rentin",
        "rentin_mu",
        "expand_state",
        "idle_state",
        "expand_minus_idle",
        "rb_farm_any",
        "asinh_rb_farm_cost_w99",
        "asinh_rb_inc_farm_w99",
        "ib_nonfarm_curr_n",
        "ib_nonfarm_curr_ge2",
        "rentin_and_nonfarm_ge2",
        "rentin_and_farm_any",
    ]
    show["order"] = show["outcome"].map({v: i for i, v in enumerate(key_order)})
    show = show.sort_values(["order", "outcome"])
    lines.append("| outcome | b | se | p |")
    lines.append("|---|---:|---:|---:|")
    for _, r in show.iterrows():
        lines.append(f"| {r['label']} | {r['b']:.3f} | {r['se']:.3f} | {r['p']:.3f} |")
    lines.append("")
    lines.append("## Pressure tests")
    lines.append("")
    lines.append(
        "The rent-in margin remains positive when adding baseline interactions under stack-year FE; "
        "province-year FE mainly reduces the high-instability total because the lower-instability component turns negative, "
        "but the high-minus-low rent-in differential remains positive and marginal."
    )
    lines.append("")
    pressure_outcomes = [
        "any_rentin",
        "asinh_rentin",
        "ib_nonfarm_curr_n",
        "ib_nonfarm_curr_ge2",
        "rb_farm_any",
        "asinh_rb_farm_cost_w99",
    ]
    main = spec_slice(hh_focus, scope="adjacent", controls="none", fe="stackyear", term="high-instability total")
    bundle_stack = spec_slice(hh_focus, scope="adjacent", controls="baseline_bundle", fe="stackyear", term="high-instability total")
    bundle_prov = spec_slice(hh_focus, scope="adjacent", controls="baseline_bundle", fe="provyear", term="high-instability total")
    diff_bundle_stack = spec_slice(
        hh_focus, scope="adjacent", controls="baseline_bundle", fe="stackyear", term="high-minus-low differential"
    )
    lines.append("| outcome | main total | baseline-bundle stack-year total | baseline-bundle province-year total | baseline-bundle stack-year diff |")
    lines.append("|---|---:|---:|---:|---:|")
    label_map = hh_focus.drop_duplicates("outcome").set_index("outcome")["label"].to_dict()
    for outcome in pressure_outcomes:
        lines.append(
            f"| {label_map.get(outcome, outcome)} | "
            f"{get_cell(main, outcome)} | "
            f"{get_cell(bundle_stack, outcome)} | "
            f"{get_cell(bundle_prov, outcome)} | "
            f"{get_cell(diff_bundle_stack, outcome)} |"
        )
    lines.append("")
    lines.append("## Aggregate bridge")
    lines.append("")
    agg_show = spec_slice(agg_focus, scope="adjacent", controls="none", fe="stackyear", term="high-instability total")
    agg_show = agg_show[agg_show["outcome"].isin(["any_rentin", "asinh_rentin", "expand_minus_idle", "ib_nonfarm_curr_n"])].copy()
    lines.append(
        "Village and county aggregate rows are a bridge against pure household-composition interpretations, "
        "but not an independent supplier-receiver match; in the current extract the usable village and county units largely coincide."
    )
    lines.append("")
    lines.append("| level | outcome | b | se | p |")
    lines.append("|---|---|---:|---:|---:|")
    for _, r in agg_show.sort_values(["level", "outcome"]).iterrows():
        lines.append(f"| {r['level']} | {r['label']} | {r['b']:.3f} | {r['se']:.3f} | {r['p']:.3f} |")
    lines.append("")
    lines.append("## Recommended interpretation")
    lines.append("")
    lines.append(
        "The defensible wording is co-occurrence and reallocation-consistency rather than formal mediation: "
        "certification is associated with stronger rent-in among high-insecurity villages in the adjacent-window stacked design, "
        "accompanied by lower own-farm production/costs and higher nonfarm labor engagement. "
        "Because rent-out is unobserved, the paper should avoid 'mediation' language and state that the evidence is consistent with within-village/county reallocation."
    )
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append(f"- Household mechanisms: `{TABLES / 'Round8_household_mechanism_results.csv'}`")
    lines.append(f"- Village aggregate bridge: `{TABLES / 'Round8_village_aggregate_results.csv'}`")
    lines.append(f"- County aggregate bridge: `{TABLES / 'Round8_county_aggregate_results.csv'}`")
    lines.append(f"- Rent-out audit: `{TABLES / 'Round8_rentout_observability_audit.csv'}`")
    return "\n".join(lines)


def main() -> None:
    ensure_dirs()
    panel = None
    stacks: dict[str, pd.DataFrame] = {}
    for scope in ["mech", "adjacent"]:
        panel_i, stack_i = read_stack(scope, "completed_t")
        panel = panel_i
        stacks[scope] = stack_i

    audit = rentout_audit(panel, stacks["mech"])
    audit.to_csv(TABLES / "Round8_rentout_observability_audit.csv", index=False, encoding="utf-8-sig")

    hh = pd.concat(
        [estimate_household(stack, HOUSEHOLD_OUTCOMES, scope) for scope, stack in stacks.items()],
        ignore_index=True,
    )
    hh.to_csv(TABLES / "Round8_household_mechanism_results.csv", index=False, encoding="utf-8-sig")

    village = pd.concat(
        [estimate_aggregate(stack, "village", AGG_OUTCOMES, scope) for scope, stack in stacks.items()],
        ignore_index=True,
    )
    village.to_csv(TABLES / "Round8_village_aggregate_results.csv", index=False, encoding="utf-8-sig")

    county = pd.concat(
        [estimate_aggregate(stack, "county", AGG_OUTCOMES, scope) for scope, stack in stacks.items()],
        ignore_index=True,
    )
    county.to_csv(TABLES / "Round8_county_aggregate_results.csv", index=False, encoding="utf-8-sig")

    hh_focus, agg_focus = compact_tables(hh, village, county)
    hh_focus.to_csv(TABLES / "Round8_household_mechanism_focus.csv", index=False, encoding="utf-8-sig")
    agg_focus.to_csv(TABLES / "Round8_aggregate_mechanism_focus.csv", index=False, encoding="utf-8-sig")
    selected = hh_focus[
        hh_focus["sample_scope"].eq("adjacent")
        & hh_focus["outcome"].isin(
            [
                "any_rentin",
                "asinh_rentin",
                "ib_nonfarm_curr_n",
                "ib_nonfarm_curr_ge2",
                "rb_farm_any",
                "asinh_rb_farm_cost_w99",
                "asinh_rb_inc_farm_w99",
            ]
        )
        & (
            (hh_focus["controls"].eq("none") & hh_focus["fe"].eq("stackyear"))
            | (hh_focus["controls"].eq("baseline_bundle") & hh_focus["fe"].isin(["stackyear", "provyear"]))
        )
    ].copy()
    selected.to_csv(TABLES / "Round8_mechanism_selected_for_paper.csv", index=False, encoding="utf-8-sig")

    memo = summarize(hh_focus, agg_focus, audit)
    (OUT / "Round8_Mechanism_Directness_Memo_20260502.md").write_text(memo, encoding="utf-8")
    print(memo)


if __name__ == "__main__":
    main()
