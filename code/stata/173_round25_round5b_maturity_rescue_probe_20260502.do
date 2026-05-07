version 17
clear all
set more off
set linesize 255
set varabbrev off

global ROOT "`c(pwd)'"
do "$ROOT/code/stata/01_globals_and_ado.do"

local OUT "$ROOT/result/round25_empirical_rebuild_20260502/round5_maturity_thresholds/rescue"
cap mkdir "$ROOT/result"
cap mkdir "$ROOT/result/round25_empirical_rebuild_20260502"
cap mkdir "$ROOT/result/round25_empirical_rebuild_20260502/round5_maturity_thresholds"
cap mkdir "`OUT'"
cap mkdir "`OUT'/audit"
cap mkdir "`OUT'/tables"
cap mkdir "`OUT'/logs"

cap log close _all
log using "`OUT'/logs/173_round25_round5b_maturity_rescue_probe_20260502.log", replace text

local CLDS  "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_indivbridge_20260416.dta"
local ADMIN "$ROOT/data/topjournal_rebuild/admin/admin_rollout_countyyear_v2.dta"
local FOBS  "$ROOT/data/topjournal_rebuild/fobs/fobs_household_analysis_panel_hybrid_admin_20260415.dta"

tempfile ADMINUSE CLDSMASTER FOBSMASTER AUDIT ADMINAUDIT

use "`ADMIN'", clear
rename county_id_num __cid_id
gen byte signoff_or_issue_t = ((county_signedoff_t==1) | (county_issued_t==1)) if !missing(county_signedoff_t) | !missing(county_issued_t)
gen byte completed_t = county_completed_t if !missing(county_completed_t)
foreach x in 50 60 70 80 90 95 99 100 {
    gen byte sat`x'_t = (county_completion_rate>=`x') if !missing(county_completion_rate)
}
gen double comp_rate01 = county_completion_rate/100 if county_completion_rate>1 & !missing(county_completion_rate)
replace comp_rate01 = county_completion_rate if inrange(county_completion_rate, 0, 1)
save `ADMINUSE', replace

postfile PA str20 dataset str24 scope str20 variable str20 category ///
    long rows households counties double mean_rate min_rate max_rate using `AUDIT', replace

* CLDS scopes
use "`CLDS'", clear
keep if inlist(year,2014,2016,2018)
merge m:1 __cid_id year using `ADMINUSE', nogen keep(match master)
gen byte a3_obs = inlist(a3_high_insec,0,1)
save `CLDSMASTER', replace

foreach scope in all_current mech a3obs adjacent {
    use `CLDSMASTER', clear
    if "`scope'"=="mech" {
        cap confirm variable s_mech_hh
        if !_rc keep if s_mech_hh==1
    }
    if "`scope'"=="a3obs" keep if a3_obs==1
    if "`scope'"=="adjacent" keep if timing_adjacent_hh==1

    foreach v in signoff_or_issue_t completed_t sat50_t sat70_t sat80_t sat90_t sat95_t sat99_t sat100_t {
        cap confirm variable `v'
        if _rc continue
        quietly count if !missing(`v')
        local rows = r(N)
        cap drop __tagh __tagc
        egen byte __tagh = tag(hid) if !missing(`v')
        egen byte __tagc = tag(__cid_id) if !missing(`v')
        quietly count if __tagh==1
        local hh = r(N)
        quietly count if __tagc==1
        local cc = r(N)
        quietly summarize comp_rate01 if !missing(`v'), meanonly
        post PA ("CLDS") ("`scope'") ("`v'_obs") ("all") (`rows') (`hh') (`cc') (r(mean)) (r(min)) (r(max))

        quietly count if `v'==1
        local rows = r(N)
        drop __tagh __tagc
        egen byte __tagh = tag(hid) if `v'==1
        egen byte __tagc = tag(__cid_id) if `v'==1
        quietly count if __tagh==1
        local hh = r(N)
        quietly count if __tagc==1
        local cc = r(N)
        quietly summarize comp_rate01 if `v'==1, meanonly
        post PA ("CLDS") ("`scope'") ("`v'_pos") ("all") (`rows') (`hh') (`cc') (r(mean)) (r(min)) (r(max))
    }

    * Distinct support for thresholds
    quietly count if completed_t==1 & sat90_t==0
    post PA ("CLDS") ("`scope'") ("complete_not_sat90") ("rows") (r(N)) (.) (.) (.) (.) (.)
    quietly count if completed_t==1 & sat100_t==0
    post PA ("CLDS") ("`scope'") ("complete_not_sat100") ("rows") (r(N)) (.) (.) (.) (.) (.)
    quietly count if sat90_t==1 & completed_t==0
    post PA ("CLDS") ("`scope'") ("sat90_not_complete") ("rows") (r(N)) (.) (.) (.) (.) (.)
}

* FOBS scopes
use "`FOBS'", clear
capture tostring household_id, replace force
capture destring year county_id_num hybrid_rate_any_t hybrid_rate_mid_t hybrid_rate_high_t hybrid_completion_rate in_both_segments full_2009_2017_candidate, replace force
keep if inrange(year,2009,2017)
gen byte county_mappable = !missing(county_id_num)
gen byte overlap_household = (in_both_segments==1) if !missing(in_both_segments)
gen byte long_household = (full_2009_2017_candidate==1) if !missing(full_2009_2017_candidate)
egen long hh_fe = group(household_id)
save `FOBSMASTER', replace

foreach scope in full overlap long {
    use `FOBSMASTER', clear
    keep if county_mappable==1
    if "`scope'"=="overlap" keep if overlap_household==1
    if "`scope'"=="long" keep if long_household==1

    foreach v in hybrid_rate_any_t hybrid_rate_mid_t hybrid_rate_high_t {
        quietly count if !missing(`v')
        local rows = r(N)
        cap drop __tagh __tagc
        egen byte __tagh = tag(hh_fe) if !missing(`v')
        egen byte __tagc = tag(county_id_num) if !missing(`v')
        quietly count if __tagh==1
        local hh = r(N)
        quietly count if __tagc==1
        local cc = r(N)
        quietly summarize hybrid_completion_rate if !missing(`v'), meanonly
        post PA ("FOBS") ("`scope'") ("`v'_obs") ("all") (`rows') (`hh') (`cc') (r(mean)) (r(min)) (r(max))

        quietly count if `v'==1
        local rows = r(N)
        drop __tagh __tagc
        egen byte __tagh = tag(hh_fe) if `v'==1
        egen byte __tagc = tag(county_id_num) if `v'==1
        quietly count if __tagh==1
        local hh = r(N)
        quietly count if __tagc==1
        local cc = r(N)
        quietly summarize hybrid_completion_rate if `v'==1, meanonly
        post PA ("FOBS") ("`scope'") ("`v'_pos") ("all") (`rows') (`hh') (`cc') (r(mean)) (r(min)) (r(max))
    }
}

postclose PA
use `AUDIT', clear
export delimited using "`OUT'/audit/Round5B_A_maturity_support_multisample.csv", replace

* Admin county-year raw support
use `ADMINUSE', clear
gen one = 1
collapse (sum) rows=one started=county_started_t signaled=signoff_or_issue_t completed=completed_t ///
    sat50=sat50_t sat70=sat70_t sat80=sat80_t sat90=sat90_t sat95=sat95_t sat100=sat100_t ///
    (mean) mean_rate=comp_rate01 (min) min_rate=comp_rate01 (max) max_rate=comp_rate01, by(year)
export delimited using "`OUT'/audit/Round5B_B_admin_countyyear_support.csv", replace

log close
