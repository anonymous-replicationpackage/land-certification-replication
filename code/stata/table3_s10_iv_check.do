version 18
clear all
set more off

local __root = subinstr("`c(pwd)'", char(92), "/", .)
if regexm("`__root'", "/code/stata$") local __root = regexr("`__root'", "/code/stata$", "")
if trim("$ROOT") == "" global ROOT "`__root'"
cd "$ROOT"
capture log close
log using "result/iv_consistency_check_20260507/table3_s10_iv_check.log", replace text

display as text "=== Table 3 IV-DID source: single composite IV, mechanism sample, completion ==="
import delimited using "result/round8_preferred_iv_geosurvey_20260430/tables/Round8_preferred_IV_table_for_paper.csv", clear varnames(1)
keep if anchor == "completed_t" & spec == "official_x_geo_area_rugged" & controls == "baseline_bundle"
list anchor instrument controls any_b any_se any_p any_first_stage_f any_n any_counties area_b area_se area_p area_first_stage_f area_n area_counties, noobs abbreviate(24)

display as text "=== Online Appendix Table S10 source: clean three-IV IV-GMM baseline ==="
import delimited using "result/round25_empirical_rebuild_20260502/round7_iv_exclusion/tables/Round7B_highF_GMM_table.csv", clear varnames(1)
keep if set == "clean_three_iv" & estimator == "IVGMM" & controls == "baseline_bundle" & stress == "baseline"
list set estimator controls stress outcome n clusters b se p first_stage_f overid_p, noobs abbreviate(24)

log close
