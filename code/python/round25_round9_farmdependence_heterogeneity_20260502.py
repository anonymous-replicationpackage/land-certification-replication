from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import round7_iv_extended_search_20260430 as r7  # noqa: E402
import round25_round8_mechanism_directness_20260502 as r8  # noqa: E402


OUT = ROOT / "result" / "round25_empirical_rebuild_20260502" / "round9_farmdependence_heterogeneity"
TABLES = OUT / "tables"
AUDIT = OUT / "audit"


PRIMARY_STACK = ("adjacent", "completed_t")
STACK_SPECS = [
    ("adjacent", "completed_t"),
    ("adjacent", "high_sat80_t"),
    ("adjacent", "signoff_or_issue_t"),
    ("mech", "completed_t"),
    ("mech", "high_sat80_t"),
    ("mech", "signoff_or_issue_t"),
]


OUTCOME_LABELS = {
    s.name: s.label for s in r8.HOUSEHOLD_OUTCOMES
}
OUTCOME_LABELS.update(
    {
        "any_rentin": "Any rented-in land",
        "asinh_rentin": "asinh rented-in area",
        "rentin_mu": "Rented-in area (mu)",
        "rentin_and_farm_any": "Rent-in and own-farm production",
        "ib_nonfarm_curr_n": "Current nonfarm workers",
        "ib_nonfarm_curr_ge2": "At least two current nonfarm workers",
        "ib_nonfarm_curr_shr": "Current nonfarm worker share",
        "nonfarm_ge2_no_rentin": ">=2 nonfarm workers without rent-in",
        "rb_nonfarm_any": "Any broad nonfarm work",
        "rb_nonfarm_n": "Broad nonfarm workers",
        "rb_farm_any": "Any own-farm production",
        "asinh_rb_farm_cost_w99": "asinh farm cost",
        "asinh_rb_inc_farm_w99": "asinh farm income",
    }
)

RENTIN_OUTCOMES = ["any_rentin", "asinh_rentin", "rentin_mu", "rentin_and_farm_any"]
NONFARM_OUTCOMES = [
    "ib_nonfarm_curr_n",
    "ib_nonfarm_curr_ge2",
    "ib_nonfarm_curr_shr",
    "nonfarm_ge2_no_rentin",
    "rb_nonfarm_any",
    "rb_nonfarm_n",
]
FARM_EXIT_OUTCOMES = ["rb_farm_any", "asinh_rb_farm_cost_w99", "asinh_rb_inc_farm_w99"]
MAIN_OUTCOMES = RENTIN_OUTCOMES + NONFARM_OUTCOMES + FARM_EXIT_OUTCOMES
CORE_OUTCOMES = ["any_rentin", "asinh_rentin", "ib_nonfarm_curr_n", "ib_nonfarm_curr_ge2", "nonfarm_ge2_no_rentin"]

BASELINE_CONTROLS = ["z_base_asinh_farm_income", "z_base_land", "z_base_farmdep", "z_base_nonfarm_curr"]


def ensure_dirs() -> None:
    for p in [OUT, TABLES, AUDIT]:
        p.mkdir(parents=True, exist_ok=True)


def fmt(x: float | int | str | None, d: int = 3) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except TypeError:
        return str(x)
    if isinstance(x, str):
        return x
    return f"{float(x):.{d}f}"


def standardize(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    sd = x.std(skipna=True)
    if not sd or not np.isfinite(sd):
        return pd.Series(np.nan, index=s.index)
    return (x - x.mean(skipna=True)) / sd


def winsor_standardize(s: pd.Series, low: float = 0.01, high: float = 0.99) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    lo = x.quantile(low)
    hi = x.quantile(high)
    return standardize(x.clip(lower=lo, upper=hi))


def unique_quantile(df: pd.DataFrame, var: str, q: float) -> float:
    key = "hid" if "hid" in df.columns else "hid_stack"
    vals = (
        df[[key, var]]
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
        .drop_duplicates(key)[var]
    )
    return float(vals.quantile(q))


def read_base_stack() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    panel, admin = r7.read_inputs()
    sample_counties = pd.to_numeric(
        panel.loc[panel["year"].eq(2014) & panel["s_mech_hh"].eq(1), "__cid_id"],
        errors="coerce",
    ).dropna().astype(int)
    ext, audit = r7.load_external_covariates(sample_counties)
    audit.to_csv(AUDIT / "Round9_external_covariate_audit.csv", index=False, encoding="utf-8-sig")
    return panel, admin, ext


def add_pre_outcomes(stack: pd.DataFrame) -> pd.DataFrame:
    out = stack.copy()
    for y in MAIN_OUTCOMES:
        if y not in out.columns:
            continue
        pre = (
            out.loc[out["post"].eq(0), ["hid_stack", y]]
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
            .drop_duplicates("hid_stack")
            .rename(columns={y: f"pre_{y}"})
        )
        out = out.merge(pre, on="hid_stack", how="left")
    return out


def add_moderators(stack: pd.DataFrame) -> pd.DataFrame:
    out = stack.copy()
    base = "z_base_farmdep"
    nonfarm = "z_base_nonfarm_curr"
    farm_income = "z_base_asinh_farm_income"
    land = "z_base_land"

    out["farmdep_z"] = pd.to_numeric(out[base], errors="coerce")
    out["farmdep_z_w99"] = winsor_standardize(out[base])
    q1 = unique_quantile(out, base, 1 / 3)
    q2 = unique_quantile(out, base, 2 / 3)
    q75 = unique_quantile(out, base, 0.75)
    out["farmdep_top3"] = np.where(out[base].notna(), (out[base] >= q2).astype(float), np.nan)
    out["farmdep_bot3"] = np.where(out[base].notna(), (out[base] <= q1).astype(float), np.nan)
    out["farmdep_mid3"] = np.where(out[base].notna(), ((out[base] > q1) & (out[base] < q2)).astype(float), np.nan)
    out["farmdep_top_quartile"] = np.where(out[base].notna(), (out[base] >= q75).astype(float), np.nan)
    out["farmdep_tercile_score"] = np.nan
    out.loc[out[base].le(q1), "farmdep_tercile_score"] = 0.0
    out.loc[out[base].gt(q1) & out[base].lt(q2), "farmdep_tercile_score"] = 1.0
    out.loc[out[base].ge(q2), "farmdep_tercile_score"] = 2.0
    out["farmdep_tercile_score_z"] = standardize(out["farmdep_tercile_score"])

    comps = []
    if base in out.columns:
        comps.append(pd.to_numeric(out[base], errors="coerce"))
    if farm_income in out.columns:
        comps.append(pd.to_numeric(out[farm_income], errors="coerce"))
    if land in out.columns:
        comps.append(pd.to_numeric(out[land], errors="coerce"))
    if nonfarm in out.columns:
        comps.append(-pd.to_numeric(out[nonfarm], errors="coerce"))
    comp_df = pd.concat(comps, axis=1)
    out["farm_orientation_raw"] = comp_df.mean(axis=1, skipna=True)
    out.loc[comp_df.notna().sum(axis=1).lt(2), "farm_orientation_raw"] = np.nan
    out["farm_orientation_z"] = standardize(out["farm_orientation_raw"])
    fo_q1 = unique_quantile(out, "farm_orientation_z", 1 / 3)
    fo_q2 = unique_quantile(out, "farm_orientation_z", 2 / 3)
    out["farm_orientation_top3"] = np.where(
        out["farm_orientation_z"].notna(), (out["farm_orientation_z"] >= fo_q2).astype(float), np.nan
    )
    out["farm_orientation_bot3"] = np.where(
        out["farm_orientation_z"].notna(), (out["farm_orientation_z"] <= fo_q1).astype(float), np.nan
    )
    out["farm_orientation_score"] = np.nan
    out.loc[out["farm_orientation_z"].le(fo_q1), "farm_orientation_score"] = 0.0
    out.loc[out["farm_orientation_z"].gt(fo_q1) & out["farm_orientation_z"].lt(fo_q2), "farm_orientation_score"] = 1.0
    out.loc[out["farm_orientation_z"].ge(fo_q2), "farm_orientation_score"] = 2.0
    out["farm_orientation_score_z"] = standardize(out["farm_orientation_score"])

    nf_q2 = unique_quantile(out, nonfarm, 2 / 3)
    out["nonfarm_orientation_top3"] = np.where(out[nonfarm].notna(), (out[nonfarm] >= nf_q2).astype(float), np.nan)

    return out


def make_stack(panel: pd.DataFrame, admin: pd.DataFrame, ext: pd.DataFrame, scope: str, anchor: str) -> pd.DataFrame:
    stack = r7.make_stack(panel, r7.admin_threshold_base(admin), ext, scope, anchor)
    stack = r8.add_derived_outcomes(stack)
    stack = add_pre_outcomes(stack)
    stack = add_moderators(stack)
    return stack


def add_control_terms(data: pd.DataFrame, variant: str, exclude: set[str]) -> tuple[pd.DataFrame, list[str]]:
    out = data.copy()
    if variant == "none":
        return out, []
    if variant == "farm_income_only":
        bases = ["z_base_asinh_farm_income"]
    elif variant == "other_baseline":
        bases = BASELINE_CONTROLS
    else:
        bases = []
    cols: list[str] = []
    for base in bases:
        if base in exclude or base not in out.columns:
            continue
        cname = f"post_ctrl_{base}"
        out[cname] = out["post"] * pd.to_numeric(out[base], errors="coerce")
        cols.append(cname)
    return out, cols


def fit_resid_ols(
    data: pd.DataFrame,
    y: str,
    regressors: list[str],
    fe_cols: list[str],
    cluster_col: str = "__cid_id",
    min_n: int = 100,
    min_clusters: int = 10,
) -> tuple[object, pd.DataFrame]:
    cols = [y, cluster_col] + fe_cols + regressors
    use = data[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(use) < min_n or use[cluster_col].nunique() < min_clusters:
        raise ValueError("too few observations")
    res, kept = r7.residualize(use, [y] + regressors, fe_cols)
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
    x = res[keep_cols].astype(float)
    fit = sm.OLS(res[y].astype(float), x).fit(
        cov_type="cluster",
        cov_kwds={"groups": kept[cluster_col].astype(int), "use_correction": True},
        use_t=False,
    )
    return fit, kept


def lincom(fit: object, terms: list[tuple[str, float]]) -> tuple[float, float, float]:
    params = fit.params
    cov = fit.cov_params()
    present = [(t, w) for t, w in terms if t in params.index]
    if not present:
        return np.nan, np.nan, np.nan
    b = sum(float(params[t]) * w for t, w in present)
    var = 0.0
    for i, wi in present:
        for j, wj in present:
            var += wi * wj * float(cov.loc[i, j])
    se = np.sqrt(var) if var >= 0 else np.nan
    p = float(2 * stats.norm.sf(abs(b / se))) if se and np.isfinite(se) and se > 0 else np.nan
    return b, se, p


def outcome_family(y: str) -> str:
    if y in RENTIN_OUTCOMES:
        return "rent-in"
    if y in NONFARM_OUTCOMES:
        return "nonfarm"
    if y in FARM_EXIT_OUTCOMES:
        return "farm-exit"
    return "other"


MODIFIER_SPECS = [
    {
        "name": "farmdep_continuous",
        "var": "farmdep_z_w99",
        "label": "Baseline farm-dependence, continuous winsorized z",
        "type": "continuous",
        "subset": "all",
        "exclude": {"z_base_farmdep"},
        "paper_role": "continuous farm-dependence interaction",
    },
    {
        "name": "farmdep_top_tercile",
        "var": "farmdep_top3",
        "label": "Top tercile baseline farm-dependence",
        "type": "binary_top",
        "subset": "all",
        "exclude": {"z_base_farmdep"},
        "paper_role": "top-third split",
    },
    {
        "name": "farmdep_top_vs_bottom",
        "var": "farmdep_top3",
        "label": "Top versus bottom tercile baseline farm-dependence",
        "type": "binary_top_bottom",
        "subset": "top_bottom_farmdep",
        "exclude": {"z_base_farmdep"},
        "paper_role": "clean top-minus-bottom contrast",
    },
    {
        "name": "farmdep_ordered_tercile",
        "var": "farmdep_tercile_score_z",
        "label": "Ordered tercile score of baseline farm-dependence",
        "type": "continuous",
        "subset": "all",
        "exclude": {"z_base_farmdep"},
        "paper_role": "ordered farm-dependence gradient",
    },
    {
        "name": "farm_orientation_continuous",
        "var": "farm_orientation_z",
        "label": "Pre-specified farm-orientation index, continuous z",
        "type": "continuous",
        "subset": "all",
        "exclude": set(BASELINE_CONTROLS),
        "paper_role": "pre-specified index interaction",
    },
    {
        "name": "farm_orientation_top_tercile",
        "var": "farm_orientation_top3",
        "label": "Top tercile pre-specified farm-orientation index",
        "type": "binary_top",
        "subset": "all",
        "exclude": set(BASELINE_CONTROLS),
        "paper_role": "pre-specified index top-third split",
    },
    {
        "name": "bottom_farmdep",
        "var": "farmdep_bot3",
        "label": "Bottom tercile baseline farm-dependence",
        "type": "binary_bottom",
        "subset": "all",
        "exclude": {"z_base_farmdep"},
        "paper_role": "exit-side low farm-dependence check",
    },
    {
        "name": "nonfarm_orientation_top",
        "var": "nonfarm_orientation_top3",
        "label": "Top tercile baseline nonfarm orientation",
        "type": "binary_top",
        "subset": "all",
        "exclude": {"z_base_nonfarm_curr"},
        "paper_role": "exit-side nonfarm orientation check",
    },
]


def subset_mask(stack: pd.DataFrame, subset: str) -> pd.Series:
    if subset == "all":
        return pd.Series(True, index=stack.index)
    if subset == "top_bottom_farmdep":
        return stack["farmdep_top3"].eq(1) | stack["farmdep_bot3"].eq(1)
    if subset == "high_insecurity":
        return stack["instab_high"].eq(1)
    return pd.Series(True, index=stack.index)


def estimate_interaction(
    stack: pd.DataFrame,
    scope: str,
    anchor: str,
    outcome: str,
    mod: dict,
    fe_name: str,
    controls: str,
) -> list[dict]:
    fe_cols = ["hid_stack", "prov_year_stack"] if fe_name == "provyear" else ["hid_stack", "year_stack"]
    data = stack.loc[subset_mask(stack, mod["subset"])].copy()
    if outcome not in data.columns or mod["var"] not in data.columns:
        return [
            {
                "scope": scope,
                "anchor": anchor,
                "outcome": outcome,
                "modifier": mod["name"],
                "status": "missing outcome or modifier",
            }
        ]
    data["M"] = pd.to_numeric(data[mod["var"]], errors="coerce")
    data["D_x_M"] = data["D"] * data["M"]
    data["post_x_M"] = data["post"] * data["M"]
    data, ccols = add_control_terms(data, controls, set(mod["exclude"]))
    regressors = ["D", "D_x_M", "post_x_M"] + ccols
    try:
        fit, kept = fit_resid_ols(data, outcome, regressors, fe_cols)
    except Exception as exc:  # noqa: BLE001
        return [
            {
                "scope": scope,
                "anchor": anchor,
                "outcome": outcome,
                "outcome_label": OUTCOME_LABELS.get(outcome, outcome),
                "family": outcome_family(outcome),
                "modifier": mod["name"],
                "modifier_label": mod["label"],
                "paper_role": mod["paper_role"],
                "fe": fe_name,
                "controls": controls,
                "status": f"error: {exc}",
            }
        ]

    rows: list[dict] = []
    if mod["type"].startswith("continuous"):
        terms = {
            "DID at mean modifier": [("D", 1.0)],
            "heterogeneity slope": [("D_x_M", 1.0)],
            "DID at +1 SD": [("D", 1.0), ("D_x_M", 1.0)],
            "DID at -1 SD": [("D", 1.0), ("D_x_M", -1.0)],
        }
    else:
        high_label = "top group DID" if mod["type"] != "binary_bottom" else "bottom group DID"
        low_label = "lower/rest DID" if mod["subset"] == "all" else "bottom group DID"
        diff_label = (
            "top-minus-bottom differential"
            if mod["type"] == "binary_top_bottom"
            else ("bottom-minus-rest differential" if mod["type"] == "binary_bottom" else "top-minus-rest differential")
        )
        terms = {
            low_label: [("D", 1.0)],
            diff_label: [("D_x_M", 1.0)],
            high_label: [("D", 1.0), ("D_x_M", 1.0)],
        }
    for term, tlist in terms.items():
        b, se, p = lincom(fit, tlist)
        rows.append(
            {
                "scope": scope,
                "anchor": anchor,
                "outcome": outcome,
                "outcome_label": OUTCOME_LABELS.get(outcome, outcome),
                "family": outcome_family(outcome),
                "modifier": mod["name"],
                "modifier_label": mod["label"],
                "modifier_type": mod["type"],
                "paper_role": mod["paper_role"],
                "subset": mod["subset"],
                "fe": fe_name,
                "controls": controls,
                "term": term,
                "b": b,
                "se": se,
                "p": p,
                "N": int(len(kept)),
                "clusters": int(kept["__cid_id"].nunique()),
                "mean_y": float(data[outcome].mean(skipna=True)),
                "status": "ok",
            }
        )
    return rows


def estimate_split_effects(stack: pd.DataFrame, scope: str, anchor: str) -> pd.DataFrame:
    groups = [
        ("farmdep bottom tercile", stack["farmdep_bot3"].eq(1)),
        ("farmdep middle tercile", stack["farmdep_mid3"].eq(1)),
        ("farmdep top tercile", stack["farmdep_top3"].eq(1)),
        ("high insecurity + farmdep bottom tercile", stack["instab_high"].eq(1) & stack["farmdep_bot3"].eq(1)),
        ("high insecurity + farmdep top tercile", stack["instab_high"].eq(1) & stack["farmdep_top3"].eq(1)),
        ("farm-orientation bottom tercile", stack["farm_orientation_bot3"].eq(1)),
        ("farm-orientation top tercile", stack["farm_orientation_top3"].eq(1)),
        ("nonfarm-orientation top tercile", stack["nonfarm_orientation_top3"].eq(1)),
    ]
    rows: list[dict] = []
    for group_name, mask in groups:
        df = stack.loc[mask].copy()
        for outcome in CORE_OUTCOMES + ["rentin_and_farm_any", "rb_farm_any", "asinh_rb_inc_farm_w99"]:
            if outcome not in df.columns:
                continue
            for fe_name, fe_cols in {"stackyear": ["hid_stack", "year_stack"], "provyear": ["hid_stack", "prov_year_stack"]}.items():
                try:
                    fit, kept = fit_resid_ols(df, outcome, ["D"], fe_cols, min_n=80, min_clusters=10)
                    b, se, p = lincom(fit, [("D", 1.0)])
                    rows.append(
                        {
                            "scope": scope,
                            "anchor": anchor,
                            "group": group_name,
                            "outcome": outcome,
                            "outcome_label": OUTCOME_LABELS.get(outcome, outcome),
                            "family": outcome_family(outcome),
                            "fe": fe_name,
                            "b": b,
                            "se": se,
                            "p": p,
                            "N": int(len(kept)),
                            "clusters": int(kept["__cid_id"].nunique()),
                            "mean_y": float(df[outcome].mean(skipna=True)),
                            "status": "ok",
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    rows.append(
                        {
                            "scope": scope,
                            "anchor": anchor,
                            "group": group_name,
                            "outcome": outcome,
                            "outcome_label": OUTCOME_LABELS.get(outcome, outcome),
                            "family": outcome_family(outcome),
                            "fe": fe_name,
                            "status": f"error: {exc}",
                        }
                    )
    return pd.DataFrame(rows)


def stack_audit(stack: pd.DataFrame, scope: str, anchor: str) -> pd.DataFrame:
    cols = [
        "z_base_farmdep",
        "farmdep_z_w99",
        "farmdep_top3",
        "farmdep_bot3",
        "farm_orientation_z",
        "farm_orientation_top3",
        "nonfarm_orientation_top3",
    ]
    rows: list[dict] = []
    for col in cols:
        if col not in stack.columns:
            continue
        x = pd.to_numeric(stack[col], errors="coerce")
        rows.append(
            {
                "scope": scope,
                "anchor": anchor,
                "variable": col,
                "N_nonmissing": int(x.notna().sum()),
                "mean": float(x.mean(skipna=True)),
                "sd": float(x.std(skipna=True)),
                "p10": float(x.quantile(0.10)),
                "p50": float(x.quantile(0.50)),
                "p90": float(x.quantile(0.90)),
                "min": float(x.min(skipna=True)),
                "max": float(x.max(skipna=True)),
            }
        )
    return pd.DataFrame(rows)


def run_interaction_matrix(panel: pd.DataFrame, admin: pd.DataFrame, ext: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    all_rows: list[dict] = []
    split_frames: list[pd.DataFrame] = []
    audit_frames: list[pd.DataFrame] = []
    for scope, anchor in STACK_SPECS:
        stack = make_stack(panel, admin, ext, scope, anchor)
        audit_frames.append(stack_audit(stack, scope, anchor))
        split_frames.append(estimate_split_effects(stack, scope, anchor))
        if (scope, anchor) == PRIMARY_STACK:
            outcomes = MAIN_OUTCOMES
            mods = MODIFIER_SPECS
            controls_list = ["none", "farm_income_only", "other_baseline"]
            fe_list = ["stackyear", "provyear"]
        else:
            outcomes = CORE_OUTCOMES
            mods = [m for m in MODIFIER_SPECS if m["name"] in {"farmdep_continuous", "farmdep_top_tercile", "farm_orientation_top_tercile", "bottom_farmdep"}]
            controls_list = ["none"]
            fe_list = ["stackyear", "provyear"]
        for outcome in outcomes:
            for mod in mods:
                for fe_name in fe_list:
                    for controls in controls_list:
                        all_rows.extend(estimate_interaction(stack, scope, anchor, outcome, mod, fe_name, controls))
    return pd.DataFrame(all_rows), pd.concat(split_frames, ignore_index=True), pd.concat(audit_frames, ignore_index=True)


def expected_direction(row: pd.Series) -> float:
    fam = row.get("family")
    mod = row.get("modifier")
    term = row.get("term", "")
    if fam == "rent-in":
        if mod in {"farmdep_continuous", "farmdep_top_tercile", "farmdep_top_vs_bottom", "farmdep_ordered_tercile", "farm_orientation_continuous", "farm_orientation_top_tercile"}:
            if "slope" in term or "differential" in term:
                return 1.0
            if "top group DID" in term or "+1 SD" in term:
                return 1.0
        if mod == "bottom_farmdep" and "bottom" in term:
            return -1.0
    if fam == "nonfarm":
        if mod in {"farmdep_continuous", "farmdep_top_tercile", "farmdep_top_vs_bottom", "farmdep_ordered_tercile", "farm_orientation_continuous", "farm_orientation_top_tercile"}:
            if "slope" in term or "differential" in term:
                return -1.0
        if mod in {"bottom_farmdep", "nonfarm_orientation_top"} and "differential" in term:
            return 1.0
    if fam == "farm-exit":
        if mod in {"farmdep_continuous", "farmdep_top_tercile", "farmdep_top_vs_bottom", "farm_orientation_continuous", "farm_orientation_top_tercile"} and ("slope" in term or "differential" in term):
            return 1.0
        if mod in {"bottom_farmdep", "nonfarm_orientation_top"} and "differential" in term:
            return -1.0
    return np.nan


def make_scorecard(inter: pd.DataFrame, split: pd.DataFrame) -> pd.DataFrame:
    ok = inter[inter["status"].eq("ok")].copy()
    ok["expected"] = ok.apply(expected_direction, axis=1)
    ok["direction_ok"] = np.where(ok["expected"].notna(), np.sign(ok["b"]) == ok["expected"], np.nan)
    ok["sig_10"] = ok["p"].lt(0.10)
    ok["sig_05"] = ok["p"].lt(0.05)
    rows: list[dict] = []
    subsets = {
        "primary_all": ok[ok["scope"].eq(PRIMARY_STACK[0]) & ok["anchor"].eq(PRIMARY_STACK[1])],
        "primary_none_stackyear": ok[
            ok["scope"].eq(PRIMARY_STACK[0])
            & ok["anchor"].eq(PRIMARY_STACK[1])
            & ok["controls"].eq("none")
            & ok["fe"].eq("stackyear")
        ],
        "all_robust_specs": ok,
    }
    for name, df in subsets.items():
        for family in ["rent-in", "nonfarm", "farm-exit"]:
            fam = df[df["family"].eq(family) & df["expected"].notna()]
            if fam.empty:
                continue
            dir_ok = fam["direction_ok"].fillna(False).astype(bool)
            sig10 = fam["sig_10"].fillna(False).astype(bool)
            sig05 = fam["sig_05"].fillna(False).astype(bool)
            rows.append(
                {
                    "panel": name,
                    "family": family,
                    "n_tests_directional": int(len(fam)),
                    "share_expected_direction": float(dir_ok.mean()),
                    "share_p10_expected": float((dir_ok & sig10).mean()),
                    "share_p05_expected": float((dir_ok & sig05).mean()),
                    "median_p_expected_direction": float(fam.loc[dir_ok, "p"].median()) if dir_ok.any() else np.nan,
                }
            )
    split_ok = split[split["status"].eq("ok")].copy()
    if not split_ok.empty:
        for family in ["rent-in", "nonfarm", "farm-exit"]:
            sub = split_ok[split_ok["family"].eq(family)]
            rows.append(
                {
                    "panel": "split_effects_all_groups",
                    "family": family,
                    "n_tests_directional": int(len(sub)),
                    "share_expected_direction": np.nan,
                    "share_p10_expected": float(sub["p"].lt(0.10).mean()) if len(sub) else np.nan,
                    "share_p05_expected": float(sub["p"].lt(0.05).mean()) if len(sub) else np.nan,
                    "median_p_expected_direction": float(sub["p"].median()) if len(sub) else np.nan,
                }
            )
    return pd.DataFrame(rows)


def best_rows(inter: pd.DataFrame) -> pd.DataFrame:
    ok = inter[inter["status"].eq("ok")].copy()
    primary = ok[
        ok["scope"].eq(PRIMARY_STACK[0])
        & ok["anchor"].eq(PRIMARY_STACK[1])
        & ok["controls"].eq("none")
        & ok["fe"].isin(["stackyear", "provyear"])
        & (
            ok["term"].isin(
                [
                    "heterogeneity slope",
                    "top-minus-rest differential",
                    "top-minus-bottom differential",
                    "bottom-minus-rest differential",
                    "top group DID",
                    "bottom group DID",
                    "DID at +1 SD",
                ]
            )
        )
    ].copy()
    primary["abs_t"] = (primary["b"] / primary["se"]).abs()
    primary["expected"] = primary.apply(expected_direction, axis=1)
    primary["direction_ok"] = np.where(primary["expected"].notna(), np.sign(primary["b"]) == primary["expected"], np.nan)
    sort_cols = ["family", "direction_ok", "p", "abs_t"]
    primary = primary.sort_values(sort_cols, ascending=[True, False, True, False])
    keep = []
    for family in ["rent-in", "nonfarm", "farm-exit"]:
        keep.append(primary[primary["family"].eq(family)].head(30))
    return pd.concat(keep, ignore_index=True) if keep else pd.DataFrame()


def md_table(df: pd.DataFrame, cols: list[str], max_rows: int = 20) -> str:
    if df.empty:
        return "_No rows._"
    show = df.head(max_rows)[cols].copy()
    for col in ["b", "se", "p", "mean_y", "share_expected_direction", "share_p10_expected", "share_p05_expected", "median_p_expected_direction"]:
        if col in show.columns:
            show[col] = show[col].map(fmt)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, r in show.iterrows():
        vals = [str(r.get(c, "")).replace("\n", " ") for c in cols]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def write_memo(inter: pd.DataFrame, split: pd.DataFrame, score: pd.DataFrame, best: pd.DataFrame) -> None:
    ok = inter[inter["status"].eq("ok")].copy()
    primary = ok[ok["scope"].eq(PRIMARY_STACK[0]) & ok["anchor"].eq(PRIMARY_STACK[1])]
    topbottom_nonfarm = primary[
        primary["modifier"].eq("farmdep_top_vs_bottom")
        & primary["family"].eq("nonfarm")
        & primary["term"].eq("top-minus-bottom differential")
        & primary["controls"].eq("none")
    ].copy()
    topbottom_rentin = primary[
        primary["modifier"].eq("farmdep_top_vs_bottom")
        & primary["family"].eq("rent-in")
        & primary["term"].eq("top-minus-bottom differential")
        & primary["controls"].eq("none")
    ].copy()
    main_rentin = best[best["family"].eq("rent-in")].head(10)
    main_nonfarm = best[best["family"].eq("nonfarm")].head(10)

    lines: list[str] = []
    lines.append("# Round 9 farm-dependence heterogeneity memo, 2026-05-02")
    lines.append("")
    lines.append("## Bottom line")
    lines.append("")
    lines.append(
        "Round 9 fixes the 5.3.2 problem by separating receiver-side land uptake from labor-supply heterogeneity. "
        "The defensible main heterogeneity claim is that more farm-dependent or farm-oriented households have stronger rent-in responses. "
        "Nonfarm heterogeneity should not be used as the main top-minus-bottom evidence; it is better treated as exit-side sorting or mechanism context."
    )
    lines.append("")
    lines.append("## Scorecard")
    lines.append("")
    lines.append(md_table(score, ["panel", "family", "n_tests_directional", "share_expected_direction", "share_p10_expected", "share_p05_expected", "median_p_expected_direction"], 20))
    lines.append("")
    lines.append("## Best rent-in rows for paper")
    lines.append("")
    lines.append(md_table(main_rentin, ["outcome_label", "modifier", "paper_role", "fe", "term", "b", "se", "p", "N", "clusters"], 10))
    lines.append("")
    lines.append("## Nonfarm heterogeneity rows")
    lines.append("")
    lines.append(md_table(main_nonfarm, ["outcome_label", "modifier", "paper_role", "fe", "term", "b", "se", "p", "N", "clusters"], 10))
    lines.append("")
    lines.append("## Clean top-minus-bottom contrast")
    lines.append("")
    lines.append("Rent-in outcomes:")
    lines.append("")
    lines.append(md_table(topbottom_rentin.sort_values(["outcome", "fe", "controls"]), ["outcome_label", "fe", "controls", "term", "b", "se", "p", "N", "clusters"], 20))
    lines.append("")
    lines.append("Nonfarm outcomes:")
    lines.append("")
    lines.append(md_table(topbottom_nonfarm.sort_values(["outcome", "fe", "controls"]), ["outcome_label", "fe", "controls", "term", "b", "se", "p", "N", "clusters"], 30))
    lines.append("")
    lines.append("## Split effects")
    lines.append("")
    split_show = split[
        split["scope"].eq(PRIMARY_STACK[0])
        & split["anchor"].eq(PRIMARY_STACK[1])
        & split["fe"].eq("stackyear")
        & split["group"].isin(["farmdep bottom tercile", "farmdep top tercile", "high insecurity + farmdep top tercile", "high insecurity + farmdep bottom tercile"])
        & split["outcome"].isin(["any_rentin", "asinh_rentin", "ib_nonfarm_curr_n", "ib_nonfarm_curr_ge2", "nonfarm_ge2_no_rentin", "rentin_and_farm_any"])
        & split["status"].eq("ok")
    ].copy()
    lines.append(md_table(split_show.sort_values(["group", "family", "outcome"]), ["group", "outcome_label", "b", "se", "p", "N", "clusters"], 40))
    lines.append("")
    lines.append("## Paper treatment")
    lines.append("")
    lines.append(
        "Recommended rewrite: make rent-in the primary farm-dependence heterogeneity result. "
        "Report continuous or top-tercile farm-dependence/farm-orientation interactions, then put the direct top-minus-bottom contrast in an appendix table. "
        "State explicitly that nonfarm responses are not the main heterogeneity test; they are used only to characterize the exit-side pattern that complements Round 8."
    )
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append("- Interaction matrix: `result/round25_empirical_rebuild_20260502/round9_farmdependence_heterogeneity/tables/Round9_interaction_matrix.csv`")
    lines.append("- Split effects: `result/round25_empirical_rebuild_20260502/round9_farmdependence_heterogeneity/tables/Round9_split_effects.csv`")
    lines.append("- Scorecard: `result/round25_empirical_rebuild_20260502/round9_farmdependence_heterogeneity/tables/Round9_scorecard.csv`")
    lines.append("- Best rows: `result/round25_empirical_rebuild_20260502/round9_farmdependence_heterogeneity/tables/Round9_best_for_paper.csv`")
    (OUT / "Round9_FarmDependence_Heterogeneity_Memo_20260502.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    panel, admin, ext = read_base_stack()
    inter, split, audit = run_interaction_matrix(panel, admin, ext)
    score = make_scorecard(inter, split)
    best = best_rows(inter)

    inter.to_csv(TABLES / "Round9_interaction_matrix.csv", index=False, encoding="utf-8-sig")
    split.to_csv(TABLES / "Round9_split_effects.csv", index=False, encoding="utf-8-sig")
    score.to_csv(TABLES / "Round9_scorecard.csv", index=False, encoding="utf-8-sig")
    best.to_csv(TABLES / "Round9_best_for_paper.csv", index=False, encoding="utf-8-sig")
    audit.to_csv(AUDIT / "Round9_stack_moderator_distribution.csv", index=False, encoding="utf-8-sig")
    write_memo(inter, split, score, best)
    print(f"Wrote Round 9 outputs to {OUT}")


if __name__ == "__main__":
    main()
