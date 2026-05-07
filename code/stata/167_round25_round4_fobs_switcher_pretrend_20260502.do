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
cap mkdir "$R4/audit"

cap log close _all
log using "$R4/logs/167_round25_round4_fobs_switcher_pretrend_20260502.log", replace text

tempfile BASE OUT

use "$TJFOBS/fobs_household_analysis_panel_hybrid_admin_20260415.dta", clear
capture tostring household_id, replace force
capture destring year county_id_num in_both_segments full_2009_2015 ///
    hybrid_rate_high_t, replace force

gen byte county_mappable_skel = !missing(county_id_num)
egen long household_fe = group(household_id)

bysort county_id_num: egen first_high_year = min(cond(hybrid_rate_high_t == 1, year, .))
gen byte never_high = missing(first_high_year) if county_mappable_skel == 1
gen byte high16 = (first_high_year == 2016) if county_mappable_skel == 1
gen byte high17 = (first_high_year == 2017) if county_mappable_skel == 1

gen double transfer_in_area_zfill = transfer_in_area
replace transfer_in_area_zfill = 0 if county_mappable_skel == 1 & missing(transfer_in_area_zfill)
gen double asinh_transfer_in_area_zfill = asinh(transfer_in_area_zfill)

gen byte any_transfer_in_zfill = any_transfer_in
replace any_transfer_in_zfill = 0 if county_mappable_skel == 1 & missing(any_transfer_in_zfill)

gen double year_c = year - 2009

egen byte tag_cy_pre14 = tag(county_id_num year) if county_mappable_skel == 1 & inrange(year, 2009, 2014)
bysort county_id_num: egen n_pre14_years = total(tag_cy_pre14)
gen byte county_bal_pre14 = (n_pre14_years == 6) if county_mappable_skel == 1

preserve
    keep if county_mappable_skel == 1
    egen tagc = tag(county_id_num)
    keep if tagc == 1
    collapse (sum) counties=tagc high16 high17 never_high, by(first_high_year)
    export delimited using "$R4/audit/Round4_J_FOBS_high_switcher_counties.csv", replace
restore

save `BASE', replace

local outcomes ///
    any_transfer_in_zfill ///
    asinh_transfer_in_area_zfill ///
    asinh_operated_area_end ///
    asinh_farm_income ///
    asinh_household_income_total

postfile PO str18 group str14 sample str22 spec str40 outcome ///
    double b se p long N households counties treated_counties control_counties ///
    str80 status using `OUT', replace

foreach group in high17_vs_never high16_vs_never high17_vs_not17 {
    local gsample "county_mappable_skel == 1"
    local treat "high17"
    if "`group'" == "high17_vs_never" {
        local gsample "`gsample' & (high17 == 1 | never_high == 1)"
        local treat "high17"
    }
    if "`group'" == "high16_vs_never" {
        local gsample "`gsample' & (high16 == 1 | never_high == 1)"
        local treat "high16"
    }
    if "`group'" == "high17_vs_not17" {
        local gsample "`gsample' & !missing(high17)"
        local treat "high17"
    }

    foreach sample in full countybal {
        local sampif "`gsample'"
        if "`sample'" == "countybal" local sampif "`sampif' & county_bal_pre14 == 1"

        foreach spec in linear_2009_2013 linear_2009_2014 placebo_2013 placebo_2014 placebo_2013_14 {
            local specif "inrange(year, 2009, 2014)"
            tempvar xvar
            gen double `xvar' = .
            if "`spec'" == "linear_2009_2013" {
                replace `xvar' = `treat' * year_c
                local specif "inrange(year, 2009, 2013)"
            }
            if "`spec'" == "linear_2009_2014" {
                replace `xvar' = `treat' * year_c
                local specif "inrange(year, 2009, 2014)"
            }
            if "`spec'" == "placebo_2013" {
                replace `xvar' = `treat' * (year == 2013)
                local specif "inrange(year, 2009, 2013)"
            }
            if "`spec'" == "placebo_2014" {
                replace `xvar' = `treat' * (year == 2014)
                local specif "inrange(year, 2009, 2014)"
            }
            if "`spec'" == "placebo_2013_14" {
                replace `xvar' = `treat' * inrange(year, 2013, 2014)
                local specif "inrange(year, 2009, 2014)"
            }

            foreach y of local outcomes {
                preserve
                    keep if `sampif' & `specif' & !missing(`y', `xvar')
                    capture noisily quietly areg `y' `xvar' i.year, absorb(household_fe) vce(cluster county_id_num)
                    if _rc {
                        post PO ("`group'") ("`sample'") ("`spec'") ("`y'") ///
                            (.) (.) (.) (.) (.) (.) (.) (.) ("areg failed")
                        restore
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

                    quietly egen __tagtc = tag(county_id_num) if e(sample) & `treat' == 1
                    quietly count if __tagtc == 1
                    scalar __tc = r(N)
                    drop __tagtc

                    quietly egen __tagnc = tag(county_id_num) if e(sample) & `treat' == 0
                    quietly count if __tagnc == 1
                    scalar __nc = r(N)
                    drop __tagnc

                    post PO ("`group'") ("`sample'") ("`spec'") ("`y'") ///
                        (__b) (__se) (__p) (`__N') (__hh) (__cc) (__tc) (__nc) ("ok")
                restore
            }
            drop `xvar'
        }
    }
}
postclose PO

use `OUT', clear
sort group sample spec outcome
export delimited using "$R4/tables/Round4_K_FOBS_switcher_pretrends.csv", replace

log close
