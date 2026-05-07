version 17
clear all
set more off
set linesize 255
set varabbrev off

global ROOT "`c(pwd)'"
do "$ROOT/code/stata/01_globals_and_ado.do"

cap which reghdfe
if _rc ssc install reghdfe, replace

local OUT "$ROOT/result/round25_empirical_rebuild_20260502/round5_maturity_thresholds/rescue"
cap mkdir "`OUT'"
cap mkdir "`OUT'/tables"
cap mkdir "`OUT'/audit"
cap mkdir "`OUT'/logs"

cap log close _all
log using "`OUT'/logs/174_round25_round5b_maturity_gradient_external_20260502.log", replace text

local CLDS  "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_indivbridge_20260416.dta"
local ADMIN "$ROOT/data/topjournal_rebuild/admin/admin_rollout_countyyear_v2.dta"
local FOBS  "$ROOT/data/topjournal_rebuild/fobs/fobs_household_analysis_panel_hybrid_admin_20260415.dta"

tempfile ADMINUSE CLDSMASTER FOBSMASTER FOBSRES CLDSRES CLDSSAT

* ------------------------------------------------------------
* CLDS: finer raw county_sat_t thresholds, not completion_rate
* ------------------------------------------------------------
use "`ADMIN'", clear
rename county_id_num __cid_id
keep __cid_id year county_signedoff_t county_issued_t county_completed_t county_sat_t county_completion_rate
gen byte completed_t = county_completed_t if !missing(county_completed_t)
foreach x in 50 70 80 85 90 95 98 99 {
    gen byte satraw`x'_t = (county_sat_t>=`x'/100) if !missing(county_sat_t)
}
save `ADMINUSE', replace

use "`CLDS'", clear
keep if inlist(year,2014,2016,2018)
merge m:1 __cid_id year using `ADMINUSE', nogen keep(match master)
cap confirm variable s_mech_hh
if !_rc keep if s_mech_hh==1
gen byte instab_high = (a3_high_insec==1) if inlist(a3_high_insec,0,1)
cap drop asinh_land_total
gen double asinh_land_total = asinh(land_total_mu_raw) if !missing(land_total_mu_raw)
save `CLDSMASTER', replace

preserve
    use `CLDSMASTER', clear
    keep if !missing(instab_high)
    postfile PS str20 variable long obs_rows pos_rows pos_hh pos_counties double mean_sat min_sat max_sat using `CLDSSAT', replace
    foreach v in completed_t satraw50_t satraw70_t satraw80_t satraw85_t satraw90_t satraw95_t satraw98_t satraw99_t {
        quietly count if !missing(`v')
        local obs = r(N)
        quietly count if `v'==1
        local pos = r(N)
        cap drop __tagh __tagc
        egen byte __tagh = tag(hid) if `v'==1
        egen byte __tagc = tag(__cid_id) if `v'==1
        quietly count if __tagh==1
        local hh = r(N)
        quietly count if __tagc==1
        local cc = r(N)
        quietly summarize county_sat_t if `v'==1, meanonly
        post PS ("`v'") (`obs') (`pos') (`hh') (`cc') (r(mean)) (r(min)) (r(max))
    }
    postclose PS
    use `CLDSSAT', clear
    export delimited using "`OUT'/audit/Round5B_C_CLDS_raw_saturation_threshold_support.csv", replace
restore

cap program drop __r5b_build_stack
program define __r5b_build_stack
    version 17
    syntax , THR(name)
    bys __cid_id: egen first_thr = min(cond(`thr'==1, year, .))
    gen byte never_thr = missing(first_thr)
    keep if never_thr==1 | inlist(first_thr,2016,2018)
    preserve
        keep if inlist(year,2014,2016) & (first_thr==2016 | first_thr==2018 | never_thr==1)
        gen byte treated = (first_thr==2016)
        gen byte post = (year==2016)
        gen byte winflag = 0
        tempfile W16
        save `W16', replace
    restore
    keep if inlist(year,2016,2018) & (first_thr==2018 | never_thr==1)
    gen byte treated = (first_thr==2018)
    gen byte post = (year==2018)
    gen byte winflag = 1
    append using `W16'
    gen long hid_stack = hid + 10000000*winflag
    gen long year_stack = year + 10000*winflag
end

postfile PC str20 threshold str24 outcome ///
    double b_low se_low p_low b_diff se_diff p_diff b_high se_high p_high ///
    long N households clusters using `CLDSRES', replace

foreach thr in completed_t satraw50_t satraw80_t satraw90_t satraw95_t {
    foreach y in any_rentin asinh_rentin asinh_land_total {
        use `CLDSMASTER', clear
        keep if !missing(instab_high)
        quietly count if `thr'==1 & instab_high==1
        if r(N)==0 continue
        quietly count if `thr'==1 & instab_high==0
        if r(N)==0 continue
        __r5b_build_stack, thr(`thr')
        cap noisily reghdfe `y' i.treated##i.post##i.instab_high if !missing(`y', instab_high), absorb(hid_stack year_stack) vce(cluster __cid_id)
        if _rc continue
        tempvar es tagh tagc
        gen byte `es' = e(sample)
        egen byte `tagh' = tag(hid_stack) if `es'
        egen byte `tagc' = tag(__cid_id) if `es'
        quietly count if `tagh'==1
        local HH = r(N)
        quietly count if `tagc'==1
        local CC = r(N)
        tempname pbase pdiff btot setot ptot
        scalar `pbase' = 2*ttail(e(df_r), abs(_b[1.treated#1.post]/_se[1.treated#1.post]))
        scalar `pdiff' = 2*ttail(e(df_r), abs(_b[1.treated#1.post#1.instab_high]/_se[1.treated#1.post#1.instab_high]))
        quietly lincom 1.treated#1.post + 1.treated#1.post#1.instab_high
        scalar `btot' = r(estimate)
        scalar `setot' = r(se)
        scalar `ptot' = r(p)
        post PC ("`thr'") ("`y'") ///
            (_b[1.treated#1.post]) (_se[1.treated#1.post]) (`pbase') ///
            (_b[1.treated#1.post#1.instab_high]) (_se[1.treated#1.post#1.instab_high]) (`pdiff') ///
            (`btot') (`setot') (`ptot') (e(N)) (`HH') (`CC')
    }
}
postclose PC
use `CLDSRES', clear
export delimited using "`OUT'/tables/Round5B_D_CLDS_raw_saturation_threshold_DDD.csv", replace

* ------------------------------------------------------------
* FOBS: any/mid/high maturity gradient on external outcomes
* ------------------------------------------------------------
use "`FOBS'", clear
capture tostring household_id, replace force
capture destring year county_id_num in_both_segments full_2009_2017_candidate ///
    hybrid_rate_any_t hybrid_rate_mid_t hybrid_rate_high_t hybrid_completion_rate, replace force
gen byte county_mappable = !missing(county_id_num)
keep if county_mappable==1
egen long hh_fe = group(household_id)
gen byte overlap_household = (in_both_segments==1) if !missing(in_both_segments)
gen byte long_household = (full_2009_2017_candidate==1) if !missing(full_2009_2017_candidate)

gen double transfer_in_area_zfill = transfer_in_area
replace transfer_in_area_zfill = 0 if missing(transfer_in_area_zfill)
gen double asinh_transfer_in_area_zfill = asinh(transfer_in_area_zfill)
gen byte any_transfer_in_zfill = any_transfer_in
replace any_transfer_in_zfill = 0 if missing(any_transfer_in_zfill)

gen byte maturity3 = .
replace maturity3 = 0 if hybrid_rate_any_t==0
replace maturity3 = 1 if hybrid_rate_any_t==1 & hybrid_rate_mid_t==0
replace maturity3 = 2 if hybrid_rate_mid_t==1 & hybrid_rate_high_t==0
replace maturity3 = 3 if hybrid_rate_high_t==1

save `FOBSMASTER', replace

postfile PF str12 sample str24 outcome str20 spec str32 term ///
    double b se p long N households counties treated_counties using `FOBSRES', replace

foreach sample in full overlap long {
    local sampif "county_mappable==1"
    if "`sample'"=="overlap" local sampif "`sampif' & overlap_household==1"
    if "`sample'"=="long" local sampif "`sampif' & long_household==1"

    foreach y in any_transfer_in_zfill asinh_transfer_in_area_zfill asinh_operated_area_end asinh_farm_income farm_income_share {
        use `FOBSMASTER', clear
        keep if `sampif' & !missing(`y')
        * Separate thresholds
        foreach thr in hybrid_rate_any_t hybrid_rate_mid_t hybrid_rate_high_t {
            cap noisily reghdfe `y' `thr', absorb(hh_fe year) vce(cluster county_id_num)
            if !_rc {
                tempvar es tagh tagc tagt
                gen byte `es' = e(sample)
                egen byte `tagh' = tag(hh_fe) if `es'
                egen byte `tagc' = tag(county_id_num) if `es'
                egen byte `tagt' = tag(county_id_num) if `es' & `thr'==1
                quietly count if `tagh'==1
                local HH = r(N)
                quietly count if `tagc'==1
                local CC = r(N)
                quietly count if `tagt'==1
                local TC = r(N)
                tempname pp
                scalar `pp' = 2*ttail(e(df_r), abs(_b[`thr']/_se[`thr']))
                post PF ("`sample'") ("`y'") ("threshold") ("`thr'") (_b[`thr']) (_se[`thr']) (`pp') (e(N)) (`HH') (`CC') (`TC')
            }
        }

        use `FOBSMASTER', clear
        keep if `sampif' & !missing(`y', maturity3)
        cap noisily reghdfe `y' ib0.maturity3, absorb(hh_fe year) vce(cluster county_id_num)
        if !_rc {
            tempvar es tagh tagc
            gen byte `es' = e(sample)
            egen byte `tagh' = tag(hh_fe) if `es'
            egen byte `tagc' = tag(county_id_num) if `es'
            quietly count if `tagh'==1
            local HH = r(N)
            quietly count if `tagc'==1
            local CC = r(N)
            foreach k in 1 2 3 {
                cap quietly lincom `k'.maturity3
                if !_rc post PF ("`sample'") ("`y'") ("stage") ("stage`k'_vs0") (r(estimate)) (r(se)) (r(p)) (e(N)) (`HH') (`CC') (.)
            }
            cap quietly lincom 3.maturity3 - 2.maturity3
            if !_rc post PF ("`sample'") ("`y'") ("stage") ("stage3_minus_stage2") (r(estimate)) (r(se)) (r(p)) (e(N)) (`HH') (`CC') (.)
            cap quietly lincom 3.maturity3 - 1.maturity3
            if !_rc post PF ("`sample'") ("`y'") ("stage") ("stage3_minus_stage1") (r(estimate)) (r(se)) (r(p)) (e(N)) (`HH') (`CC') (.)
        }
    }
}
postclose PF
use `FOBSRES', clear
sort sample outcome spec term
export delimited using "`OUT'/tables/Round5B_E_FOBS_maturity_gradient.csv", replace

log close
