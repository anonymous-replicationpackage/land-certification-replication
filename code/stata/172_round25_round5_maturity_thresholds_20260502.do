version 17
clear all
set more off
set linesize 255
set varabbrev off

global ROOT "`c(pwd)'"
do "$ROOT/code/stata/01_globals_and_ado.do"

cap which reghdfe
if _rc ssc install reghdfe, replace

local OUT "$ROOT/result/round25_empirical_rebuild_20260502/round5_maturity_thresholds"
cap mkdir "$ROOT/result"
cap mkdir "$ROOT/result/round25_empirical_rebuild_20260502"
cap mkdir "`OUT'"
cap mkdir "`OUT'/audit"
cap mkdir "`OUT'/tables"
cap mkdir "`OUT'/logs"

cap log close _all
log using "`OUT'/logs/172_round25_round5_maturity_thresholds_20260502.log", replace text

local PANEL "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_indivbridge_20260416.dta"
local ADMIN "$ROOT/data/topjournal_rebuild/admin/admin_rollout_countyyear_v2.dta"

tempfile ADMINUSE MASTER STACK STAGEOUT BINOUT CONTOUT SUPPORT

use "`ADMIN'", clear
keep county_id_num year county_started_t county_signedoff_t county_issued_t county_completed_t ///
    county_sat_t county_completion_rate county_start_year county_signoff_year county_issue_year county_complete_year
rename county_id_num __cid_id

gen byte signoff_or_issue_t = ((county_signedoff_t==1) | (county_issued_t==1)) if !missing(county_signedoff_t) | !missing(county_issued_t)
gen byte signedoff_t = county_signedoff_t if !missing(county_signedoff_t)
gen byte issued_t = county_issued_t if !missing(county_issued_t)
gen byte completed_t = county_completed_t if !missing(county_completed_t)
gen byte high_sat70_t = (county_sat_t>=0.7) if !missing(county_sat_t)
gen byte high_sat80_t = (county_sat_t>=0.8) if !missing(county_sat_t)
gen byte high_sat90_t = (county_sat_t>=0.9) if !missing(county_sat_t)

gen byte maturity_stage = .
replace maturity_stage = 0 if signoff_or_issue_t==0 & completed_t==0 & high_sat80_t==0
replace maturity_stage = 1 if signoff_or_issue_t==1 & completed_t==0 & high_sat80_t==0
replace maturity_stage = 2 if completed_t==1 & high_sat80_t==0
replace maturity_stage = 3 if high_sat80_t==1
label define maturity_stage 0 "No signal" 1 "Signoff/issue only" 2 "Completed below 80%" 3 "High saturation >=80%", replace
label values maturity_stage maturity_stage

gen double stage_index = signoff_or_issue_t + completed_t + high_sat80_t if !missing(signoff_or_issue_t, completed_t, high_sat80_t)
gen byte early_signal_not_complete = (signoff_or_issue_t==1 & completed_t==0) if !missing(signoff_or_issue_t, completed_t)

gen double years_since_complete = 0
replace years_since_complete = year - county_complete_year if !missing(county_complete_year) & year>=county_complete_year
replace years_since_complete = 0 if missing(years_since_complete)
replace years_since_complete = min(years_since_complete, 4)

compress
save `ADMINUSE', replace

* ------------------------------------------------------------
* Master current CLDS mechanism panel
* ------------------------------------------------------------
use "`PANEL'", clear
keep if inlist(year,2014,2016,2018)
merge m:1 __cid_id year using `ADMINUSE', nogen keep(match master)

cap confirm variable s_mech_hh
if !_rc keep if s_mech_hh==1

gen byte instab_high = (a3_high_insec==1) if inlist(a3_high_insec,0,1)
cap drop asinh_land_total
gen double asinh_land_total = asinh(land_total_mu_raw) if !missing(land_total_mu_raw)
cap confirm variable any_abandon
if _rc gen byte any_abandon = (abandon_mu>0) if !missing(abandon_mu)
cap confirm variable asinh_abandon
if _rc gen double asinh_abandon = asinh(abandon_mu) if !missing(abandon_mu)

compress
save `MASTER', replace

* ------------------------------------------------------------
* A. Support and threshold overlap
* ------------------------------------------------------------
postfile PS str30 block str30 item str30 category long rows households counties using `SUPPORT', replace

foreach v in signoff_or_issue_t completed_t high_sat70_t high_sat80_t high_sat90_t {
    use `MASTER', clear
    keep if !missing(instab_high, `v')
    quietly count
    local rows = r(N)
    cap drop __tagh __tagc
    egen byte __tagh = tag(hid)
    egen byte __tagc = tag(__cid_id)
    quietly count if __tagh==1
    local hh = r(N)
    quietly count if __tagc==1
    local cc = r(N)
    post PS ("threshold_support") ("`v'_observed") ("all") (`rows') (`hh') (`cc')
    quietly count if `v'==1
    local rows = r(N)
    drop __tagh __tagc
    egen byte __tagh = tag(hid) if `v'==1
    egen byte __tagc = tag(__cid_id) if `v'==1
    quietly count if __tagh==1
    local hh = r(N)
    quietly count if __tagc==1
    local cc = r(N)
    post PS ("threshold_support") ("`v'_positive") ("all") (`rows') (`hh') (`cc')
}

use `MASTER', clear
keep if !missing(instab_high, maturity_stage)
levelsof maturity_stage, local(stages)
foreach s of local stages {
    quietly count if maturity_stage==`s'
    local rows = r(N)
    cap drop __tagh __tagc
    egen byte __tagh = tag(hid) if maturity_stage==`s'
    egen byte __tagc = tag(__cid_id) if maturity_stage==`s'
    quietly count if __tagh==1
    local hh = r(N)
    quietly count if __tagc==1
    local cc = r(N)
    post PS ("stage_support") ("maturity_stage") ("`s'") (`rows') (`hh') (`cc')
}

use `MASTER', clear
keep if !missing(completed_t, high_sat80_t)
gen byte comp_high_same = (completed_t==high_sat80_t)
quietly count if comp_high_same==1
post PS ("threshold_overlap") ("completed_eq_high80") ("rows") (r(N)) (.) (.)
quietly count
post PS ("threshold_overlap") ("completed_high80_total") ("rows") (r(N)) (.) (.)
quietly count if completed_t==1 & high_sat80_t==0
post PS ("threshold_overlap") ("completed_only_not_high80") ("rows") (r(N)) (.) (.)
quietly count if completed_t==0 & high_sat80_t==1
post PS ("threshold_overlap") ("high80_without_completed") ("rows") (r(N)) (.) (.)

postclose PS
use `SUPPORT', clear
export delimited using "`OUT'/audit/Round5_A_maturity_support_overlap.csv", replace

preserve
    use `MASTER', clear
    keep if !missing(completed_t, high_sat80_t, signoff_or_issue_t, maturity_stage)
    collapse (count) rows=hid (mean) mean_sat=county_sat_t mean_completion=county_completion_rate, by(year signoff_or_issue_t completed_t high_sat80_t maturity_stage)
    export delimited using "`OUT'/audit/Round5_B_stage_counts_by_year.csv", replace
restore

* ------------------------------------------------------------
* Helpers
* ------------------------------------------------------------
cap program drop __r5_build_stack
program define __r5_build_stack
    version 17
    syntax , THR(name) [DROPEARLY]

    bys __cid_id: egen first_thr = min(cond(`thr'==1, year, .))
    gen byte never_thr = missing(first_thr)
    keep if never_thr==1 | inlist(first_thr,2016,2018)

    preserve
        keep if inlist(year,2014,2016) & (first_thr==2016 | first_thr==2018 | never_thr==1)
        gen byte treated = (first_thr==2016)
        gen byte post = (year==2016)
        gen int cohort = 2016
        gen byte winflag = 0
        tempfile W16
        save `W16', replace
    restore

    keep if inlist(year,2016,2018) & (first_thr==2018 | never_thr==1)
    gen byte treated = (first_thr==2018)
    gen byte post = (year==2018)
    gen int cohort = 2018
    gen byte winflag = 1
    append using `W16'

    if "`dropearly'" != "" {
        drop if treated==0 & early_signal_not_complete==1
    }

    gen long hid_stack = hid + 10000000*winflag
    gen long year_stack = year + 10000*winflag
end

cap program drop __r5_stack_stats
program define __r5_stack_stats, rclass
    version 17
    syntax , YVAR(name)
    tempvar es tagh tagc
    gen byte `es' = e(sample)
    quietly summarize `yvar' if `es', meanonly
    return scalar meandv = r(mean)
    quietly egen byte `tagh' = tag(hid_stack) if `es'
    quietly count if `tagh'==1
    return scalar hh = r(N)
    quietly egen byte `tagc' = tag(__cid_id) if `es'
    quietly count if `tagc'==1
    return scalar cc = r(N)
end

cap program drop __r5_post_stack
program define __r5_post_stack
    version 17
    syntax , HANDLE(name) THRESHOLD(string) OUTCOME(name) SPEC(string)

    cap noisily reghdfe `outcome' i.treated##i.post##i.instab_high ///
        if !missing(`outcome', instab_high), absorb(hid_stack year_stack) vce(cluster __cid_id)
    if _rc {
        post `handle' ("`threshold'") ("`outcome'") ("`spec'") ///
            (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) (. )
        exit
    }
    quietly __r5_stack_stats, yvar(`outcome')
    local N = e(N)
    local HH = r(hh)
    local CC = r(cc)
    local MDV = r(meandv)
    tempname pbase pdiff btot setot ptot
    scalar `pbase' = 2*ttail(e(df_r), abs(_b[1.treated#1.post]/_se[1.treated#1.post]))
    scalar `pdiff' = 2*ttail(e(df_r), abs(_b[1.treated#1.post#1.instab_high]/_se[1.treated#1.post#1.instab_high]))
    quietly lincom 1.treated#1.post + 1.treated#1.post#1.instab_high
    scalar `btot' = r(estimate)
    scalar `setot' = r(se)
    scalar `ptot' = r(p)
    post `handle' ("`threshold'") ("`outcome'") ("`spec'") ///
        (_b[1.treated#1.post]) (_se[1.treated#1.post]) (`pbase') ///
        (_b[1.treated#1.post#1.instab_high]) (_se[1.treated#1.post#1.instab_high]) (`pdiff') ///
        (`btot') (`setot') (`ptot') (`N') (`HH') (`CC') (`MDV')
end

postfile PB str24 threshold str24 outcome str30 spec ///
    double b_low se_low p_low b_diff se_diff p_diff b_high se_high p_high ///
    long N households clusters double meandv using `BINOUT', replace

foreach thr in signoff_or_issue_t completed_t high_sat70_t high_sat80_t high_sat90_t {
    foreach y in any_rentin asinh_rentin asinh_land_total {
        use `MASTER', clear
        keep if !missing(instab_high)
        quietly count if `thr'==1 & instab_high==1
        if r(N)==0 continue
        quietly count if `thr'==1 & instab_high==0
        if r(N)==0 continue
        __r5_build_stack, thr(`thr')
        quietly __r5_post_stack, handle(PB) threshold("`thr'") outcome(`y') spec("stacked")
    }
}

foreach y in any_rentin asinh_rentin asinh_land_total {
    use `MASTER', clear
    keep if !missing(instab_high)
    __r5_build_stack, thr(completed_t) dropearly
    quietly __r5_post_stack, handle(PB) threshold("completed_t") outcome(`y') spec("drop_early_signal_controls")
}

postclose PB
use `BINOUT', clear
sort outcome threshold spec
export delimited using "`OUT'/tables/Round5_C_binary_threshold_stacked_DDD.csv", replace

* ------------------------------------------------------------
* C. Continuous and stage-index panel FE
* ------------------------------------------------------------
postfile PC str30 measure str24 outcome str24 spec ///
    double b_low se_low p_low b_diff se_diff p_diff b_high se_high p_high ///
    long N households clusters double meandv using `CONTOUT', replace

foreach m in county_sat_t county_completion_rate years_since_complete stage_index {
    foreach y in any_rentin asinh_rentin asinh_land_total {
        use `MASTER', clear
        keep if !missing(instab_high, `m', `y')
        cap noisily reghdfe `y' c.`m'##i.instab_high, absorb(hid year) vce(cluster __cid_id)
        if _rc continue
        tempvar es tagh tagc
        gen byte `es' = e(sample)
        egen byte `tagh' = tag(hid) if `es'
        egen byte `tagc' = tag(__cid_id) if `es'
        quietly count if `tagh'==1
        local HH = r(N)
        quietly count if `tagc'==1
        local CC = r(N)
        quietly summarize `y' if `es', meanonly
        local MDV = r(mean)
        tempname pbase pdiff btot setot ptot
        scalar `pbase' = 2*ttail(e(df_r), abs(_b[c.`m']/_se[c.`m']))
        scalar `pdiff' = 2*ttail(e(df_r), abs(_b[1.instab_high#c.`m']/_se[1.instab_high#c.`m']))
        quietly lincom c.`m' + 1.instab_high#c.`m'
        scalar `btot' = r(estimate)
        scalar `setot' = r(se)
        scalar `ptot' = r(p)
        post PC ("`m'") ("`y'") ("FE_year") ///
            (_b[c.`m']) (_se[c.`m']) (`pbase') ///
            (_b[1.instab_high#c.`m']) (_se[1.instab_high#c.`m']) (`pdiff') ///
            (`btot') (`setot') (`ptot') (e(N)) (`HH') (`CC') (`MDV')

        cap noisily reghdfe `y' c.`m'##i.instab_high c.year#i.__prov_id, absorb(hid year) vce(cluster __cid_id)
        if !_rc {
            drop `es' `tagh' `tagc'
            gen byte `es' = e(sample)
            egen byte `tagh' = tag(hid) if `es'
            egen byte `tagc' = tag(__cid_id) if `es'
            quietly count if `tagh'==1
            local HH = r(N)
            quietly count if `tagc'==1
            local CC = r(N)
            quietly summarize `y' if `es', meanonly
            local MDV = r(mean)
            scalar `pbase' = 2*ttail(e(df_r), abs(_b[c.`m']/_se[c.`m']))
            scalar `pdiff' = 2*ttail(e(df_r), abs(_b[1.instab_high#c.`m']/_se[1.instab_high#c.`m']))
            quietly lincom c.`m' + 1.instab_high#c.`m'
            scalar `btot' = r(estimate)
            scalar `setot' = r(se)
            scalar `ptot' = r(p)
            post PC ("`m'") ("`y'") ("FE_year_provtrend") ///
                (_b[c.`m']) (_se[c.`m']) (`pbase') ///
                (_b[1.instab_high#c.`m']) (_se[1.instab_high#c.`m']) (`pdiff') ///
                (`btot') (`setot') (`ptot') (e(N)) (`HH') (`CC') (`MDV')
        }
    }
}
postclose PC
use `CONTOUT', clear
sort outcome measure spec
export delimited using "`OUT'/tables/Round5_D_continuous_maturity_panelFE.csv", replace

* ------------------------------------------------------------
* D. Stage dummy panel FE, including explicit high-vs-completed tests
* ------------------------------------------------------------
postfile PS2 str24 outcome str24 spec str32 contrast ///
    double b se p long N households clusters double meandv using `STAGEOUT', replace

foreach y in any_rentin asinh_rentin asinh_land_total {
    foreach spec in FE_year FE_year_provtrend {
        use `MASTER', clear
        keep if !missing(instab_high, maturity_stage, `y')
        local extra ""
        if "`spec'"=="FE_year_provtrend" local extra "c.year#i.__prov_id"
        cap noisily reghdfe `y' ib0.maturity_stage##i.instab_high `extra', absorb(hid year) vce(cluster __cid_id)
        if _rc continue
        tempvar es tagh tagc
        gen byte `es' = e(sample)
        egen byte `tagh' = tag(hid) if `es'
        egen byte `tagc' = tag(__cid_id) if `es'
        quietly count if `tagh'==1
        local HH = r(N)
        quietly count if `tagc'==1
        local CC = r(N)
        quietly summarize `y' if `es', meanonly
        local MDV = r(mean)

        foreach s in 1 2 3 {
            cap quietly lincom `s'.maturity_stage
            if !_rc post PS2 ("`y'") ("`spec'") ("lower_stage`s'_vs0") (r(estimate)) (r(se)) (r(p)) (e(N)) (`HH') (`CC') (`MDV')
            cap quietly lincom `s'.maturity_stage + `s'.maturity_stage#1.instab_high
            if !_rc post PS2 ("`y'") ("`spec'") ("high_stage`s'_vs0") (r(estimate)) (r(se)) (r(p)) (e(N)) (`HH') (`CC') (`MDV')
            cap quietly lincom `s'.maturity_stage#1.instab_high
            if !_rc post PS2 ("`y'") ("`spec'") ("DDD_stage`s'_minus_lower") (r(estimate)) (r(se)) (r(p)) (e(N)) (`HH') (`CC') (`MDV')
        }
        cap quietly lincom (3.maturity_stage + 3.maturity_stage#1.instab_high) - (2.maturity_stage + 2.maturity_stage#1.instab_high)
        if !_rc post PS2 ("`y'") ("`spec'") ("high_stage3_minus_stage2") (r(estimate)) (r(se)) (r(p)) (e(N)) (`HH') (`CC') (`MDV')
        cap quietly lincom 3.maturity_stage#1.instab_high - 2.maturity_stage#1.instab_high
        if !_rc post PS2 ("`y'") ("`spec'") ("DDD_stage3_minus_stage2") (r(estimate)) (r(se)) (r(p)) (e(N)) (`HH') (`CC') (`MDV')
    }
}
postclose PS2
use `STAGEOUT', clear
sort outcome spec contrast
export delimited using "`OUT'/tables/Round5_E_stage_dummy_panelFE.csv", replace

log close
