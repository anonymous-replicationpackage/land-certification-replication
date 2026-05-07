version 17
clear all
set more off
set linesize 255
set varabbrev off

global ROOT "`c(pwd)'"
do "$ROOT/code/stata/01_globals_and_ado.do"
do "$ROOT/code/stata/60_topjournal_setup.do"

global R4 "$ROOT/result/round25_empirical_rebuild_20260502/round4_parallel_trends_fobs"
cap mkdir "$R4"
cap mkdir "$R4/logs"
cap mkdir "$R4/tables"

cap log close _all
log using "$R4/logs/170_round25_round4b_fobs_conditional_wild_20260502.log", replace text

cap which reghdfe
if _rc {
    di as error "reghdfe not found"
    exit 111
}
cap which boottest
if _rc {
    di as error "boottest not found"
    exit 111
}

tempfile RES

use "$TJFOBS/fobs_household_analysis_panel_hybrid_admin_20260415.dta", clear
capture tostring household_id, replace force
capture destring year county_id_num prov_id hybrid_rate_high_t, replace force

gen byte county_mappable_skel = !missing(county_id_num)
bysort county_id_num: egen first_high_year = min(cond(hybrid_rate_high_t == 1, year, .))
gen byte future_high = inrange(first_high_year, 2016, 2017)
replace future_high = 0 if county_mappable_skel == 1 & missing(future_high)
gen byte high17 = (first_high_year == 2017)
replace high17 = 0 if county_mappable_skel == 1 & missing(high17)

keep if county_mappable_skel == 1 & inrange(year, 2009, 2014)

egen long household_fe = group(household_id)
egen long provyear_fe = group(prov_id year)

gen double transfer_in_area_zfill = transfer_in_area
replace transfer_in_area_zfill = 0 if missing(transfer_in_area_zfill)
gen double asinh_transfer_in_area_zfill = asinh(transfer_in_area_zfill)

gen byte any_transfer_in_zfill = any_transfer_in
replace any_transfer_in_zfill = 0 if missing(any_transfer_in_zfill)

gen double year_c = year - 2009
bysort county_id_num: egen base_tin_any = mean(cond(year == 2009, any_transfer_in_zfill, .))
bysort county_id_num: egen base_tin_asinh = mean(cond(year == 2009, asinh_transfer_in_area_zfill, .))
bysort county_id_num: egen base_oper = mean(cond(year == 2009, asinh_operated_area_end, .))

local controls c.base_tin_any#i.year c.base_tin_asinh#i.year c.base_oper#i.year
local outcomes any_transfer_in_zfill asinh_transfer_in_area_zfill

postfile PW str18 anchor str22 spec str40 outcome ///
    double b se p_cluster p_wild long N households counties treated_counties control_counties reps ///
    str80 status using `RES', replace

foreach anchor in future_high high17 {
    foreach spec in linear_2009_2013 linear_2009_2014 placebo_2013 placebo_2013_14 placebo_2014 {
        tempvar xvar
        gen double `xvar' = .
        local specif "inrange(year, 2009, 2014)"
        if "`spec'" == "linear_2009_2013" {
            replace `xvar' = `anchor' * year_c
            local specif "inrange(year, 2009, 2013)"
        }
        if "`spec'" == "linear_2009_2014" {
            replace `xvar' = `anchor' * year_c
            local specif "inrange(year, 2009, 2014)"
        }
        if "`spec'" == "placebo_2013" {
            replace `xvar' = `anchor' * (year == 2013)
            local specif "inrange(year, 2009, 2013)"
        }
        if "`spec'" == "placebo_2013_14" {
            replace `xvar' = `anchor' * inrange(year, 2013, 2014)
            local specif "inrange(year, 2009, 2014)"
        }
        if "`spec'" == "placebo_2014" {
            replace `xvar' = `anchor' * (year == 2014)
            local specif "inrange(year, 2009, 2014)"
        }

        foreach y of local outcomes {
            capture noisily reghdfe `y' `xvar' `controls' ///
                if `specif' & !missing(`y', `xvar', prov_id, base_tin_any, base_tin_asinh, base_oper), ///
                absorb(household_fe provyear_fe) vce(cluster county_id_num)
            if _rc {
                post PW ("`anchor'") ("`spec'") ("`y'") ///
                    (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) ("reghdfe failed")
                continue
            }
            scalar __b = _b[`xvar']
            scalar __se = _se[`xvar']
            scalar __p = 2 * ttail(e(df_r), abs(__b / __se))
            local __N = e(N)

            quietly egen __tagh = tag(household_fe) if e(sample)
            quietly count if __tagh == 1
            scalar __hh = r(N)
            drop __tagh

            quietly egen __tagc = tag(county_id_num) if e(sample)
            quietly count if __tagc == 1
            scalar __cc = r(N)
            drop __tagc

            quietly egen __tagtc = tag(county_id_num) if e(sample) & `anchor' == 1
            quietly count if __tagtc == 1
            scalar __tc = r(N)
            drop __tagtc

            quietly egen __tagnc = tag(county_id_num) if e(sample) & `anchor' == 0
            quietly count if __tagnc == 1
            scalar __nc = r(N)
            drop __tagnc

            scalar __wildp = .
            scalar __reps = .
            local status "ok"
            capture noisily boottest `xvar', cluster(county_id_num) reps(999) seed(20260502) ///
                weight(webb) nograph quietly
            if !_rc {
                scalar __wildp = r(p)
                scalar __reps = r(reps)
            }
            else local status "boottest failed"

            post PW ("`anchor'") ("`spec'") ("`y'") ///
                (__b) (__se) (__p) (__wildp) (`__N') (__hh) (__cc) (__tc) (__nc) (__reps) ("`status'")
        }
        drop `xvar'
    }
}
postclose PW

use `RES', clear
sort anchor spec outcome
export delimited using "$R4/tables/Round4_N_FOBS_conditional_pretrend_wild.csv", replace

log close
