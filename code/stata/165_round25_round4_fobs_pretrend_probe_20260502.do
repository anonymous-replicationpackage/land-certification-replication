version 17
clear all
set more off
set linesize 255
set varabbrev off

global ROOT "`c(pwd)'"
do "$ROOT/code/stata/01_globals_and_ado.do"
do "$ROOT/code/stata/60_topjournal_setup.do"

global R4 "$ROOT/result/round25_empirical_rebuild_20260502/round4_parallel_trends_fobs"
cap mkdir "$ROOT/result/round25_empirical_rebuild_20260502"
cap mkdir "$R4"
cap mkdir "$R4/logs"
cap mkdir "$R4/audit"
cap mkdir "$R4/tables"

cap log close _all
log using "$R4/logs/165_round25_round4_fobs_pretrend_probe_20260502.log", replace text

use "$TJFOBS/fobs_household_analysis_panel_hybrid_admin_20260415.dta", clear
capture tostring household_id, replace force
capture destring year county_id_num in_both_segments full_2009_2017_candidate ///
    hybrid_completion_rate hybrid_rate_any_t hybrid_rate_mid_t hybrid_rate_high_t, replace force

di as txt "=== VARIABLE INVENTORY ==="
describe, simple
ds
local allvars "`r(varlist)'"

preserve
    clear
    set obs 1
    gen strL vars = ""
    replace vars = "`allvars'"
    export delimited using "$R4/audit/Round4_A_FOBS_variable_inventory.csv", replace
restore

di as txt "=== YEAR SUPPORT ==="
tab year, missing

preserve
    keep if !missing(year)
    gen one = 1
    collapse (sum) rows=one ///
        (sum) rate_any_rows=hybrid_rate_any_t rate_mid_rows=hybrid_rate_mid_t rate_high_rows=hybrid_rate_high_t ///
        (mean) mean_completion_rate=hybrid_completion_rate, by(year)
    export delimited using "$R4/audit/Round4_B_FOBS_year_support.csv", replace
restore

di as txt "=== COUNTY SUPPORT BY YEAR ==="
preserve
    keep if !missing(year, county_id_num)
    egen tag_county_year = tag(county_id_num year)
    collapse (sum) counties=tag_county_year, by(year)
    export delimited using "$R4/audit/Round4_C_FOBS_county_support_by_year.csv", replace
restore

di as txt "=== ADMIN THRESHOLD TIMING SUPPORT ==="
preserve
    keep if !missing(county_id_num)
    collapse (max) any=hybrid_rate_any_t mid=hybrid_rate_mid_t high=hybrid_rate_high_t ///
        (mean) completion_rate=hybrid_completion_rate, by(county_id_num year)
    bysort county_id_num (year): egen first_any_year = min(cond(any==1, year, .))
    bysort county_id_num (year): egen first_mid_year = min(cond(mid==1, year, .))
    bysort county_id_num (year): egen first_high_year = min(cond(high==1, year, .))
    bysort county_id_num (year): egen ever_any = max(any)
    bysort county_id_num (year): egen ever_mid = max(mid)
    bysort county_id_num (year): egen ever_high = max(high)
    bysort county_id_num (year): egen completion_max = max(completion_rate)
    bysort county_id_num (year): keep if _n == 1
    keep county_id_num first_any_year first_mid_year first_high_year ever_any ever_mid ever_high completion_max
    duplicates drop
    export delimited using "$R4/audit/Round4_D_FOBS_county_threshold_timing.csv", replace
restore

di as txt "=== CANDIDATE OUTCOME SUMMARIES ==="
local candidates ///
    asinh_operated_area_end operated_area_end ///
    asinh_farm_income farm_income ///
    asinh_household_income_total household_income_total ///
    farm_income_share ///
    asinh_local_wage_income local_wage_income local_wage_share ///
    asinh_migrant_wage_income migrant_wage_income migrant_wage_share ///
    transfer_in_area transfer_in_area_mu asinh_transfer_in_area ///
    transfer_out_area transfer_out_area_mu asinh_transfer_out_area ///
    idle_labor migrant_labor idle_labor_share migrant_labor_share

tempfile avail
postfile PA str40 variable byte exists double nonmissing mean sd min max using `avail', replace
foreach v of local candidates {
    capture confirm variable `v'
    if _rc {
        post PA ("`v'") (0) (.) (.) (.) (.) (.)
    }
    else {
        quietly summarize `v'
        post PA ("`v'") (1) (r(N)) (r(mean)) (r(sd)) (r(min)) (r(max))
    }
}
postclose PA
use `avail', clear
export delimited using "$R4/audit/Round4_E_FOBS_candidate_outcome_availability.csv", replace

log close
