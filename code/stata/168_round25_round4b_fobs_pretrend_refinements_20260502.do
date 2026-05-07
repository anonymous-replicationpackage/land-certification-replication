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
cap mkdir "$R4/audit"
cap mkdir "$R4/tables"

cap log close _all
log using "$R4/logs/168_round25_round4b_fobs_pretrend_refinements_20260502.log", replace text

tempfile BASE RES

use "$TJFOBS/fobs_household_analysis_panel_hybrid_admin_20260415.dta", clear
capture tostring household_id, replace force
capture destring year county_id_num prov_id in_both_segments full_2009_2015 ///
    hybrid_rate_high_t hybrid_completed_t hybrid_completion_rate, replace force

gen byte county_mappable_skel = !missing(county_id_num)
egen long household_fe = group(household_id)

bysort county_id_num: egen first_high_year = min(cond(hybrid_rate_high_t == 1, year, .))
bysort county_id_num: egen first_completed_year = min(cond(hybrid_completed_t == 1, year, .))

gen byte future_high = inrange(first_high_year, 2016, 2017) if county_mappable_skel == 1
replace future_high = 0 if county_mappable_skel == 1 & missing(future_high)
gen byte high17 = (first_high_year == 2017) if county_mappable_skel == 1
replace high17 = 0 if county_mappable_skel == 1 & missing(high17)
gen byte high16 = (first_high_year == 2016) if county_mappable_skel == 1
replace high16 = 0 if county_mappable_skel == 1 & missing(high16)

gen byte future_completed = inrange(first_completed_year, 2016, 2017) if county_mappable_skel == 1
replace future_completed = 0 if county_mappable_skel == 1 & missing(future_completed)
gen byte completed17 = (first_completed_year == 2017) if county_mappable_skel == 1
replace completed17 = 0 if county_mappable_skel == 1 & missing(completed17)

gen double transfer_in_area_zfill = transfer_in_area
replace transfer_in_area_zfill = 0 if county_mappable_skel == 1 & missing(transfer_in_area_zfill)
gen double asinh_transfer_in_area_zfill = asinh(transfer_in_area_zfill)

gen byte any_transfer_in_zfill = any_transfer_in
replace any_transfer_in_zfill = 0 if county_mappable_skel == 1 & missing(any_transfer_in_zfill)

gen double transfer_out_area_zfill = transfer_out_area
replace transfer_out_area_zfill = 0 if county_mappable_skel == 1 & missing(transfer_out_area_zfill)
gen double asinh_transfer_out_area_zfill = asinh(transfer_out_area_zfill)
gen byte any_transfer_out_zfill = any_transfer_out
replace any_transfer_out_zfill = 0 if county_mappable_skel == 1 & missing(any_transfer_out_zfill)

gen double year_c = year - 2009

bysort county_id_num: egen base_tin_any = mean(cond(year == 2009, any_transfer_in_zfill, .))
bysort county_id_num: egen base_tin_asinh = mean(cond(year == 2009, asinh_transfer_in_area_zfill, .))
bysort county_id_num: egen base_oper = mean(cond(year == 2009, asinh_operated_area_end, .))

egen byte tag_cy_pre14 = tag(county_id_num year) if county_mappable_skel == 1 & inrange(year, 2009, 2014)
bysort county_id_num: egen n_pre14_years = total(tag_cy_pre14)
gen byte county_bal_pre14 = (n_pre14_years == 6) if county_mappable_skel == 1

preserve
    keep if county_mappable_skel == 1
    egen tagc = tag(county_id_num)
    keep if tagc == 1
    collapse (sum) counties=tagc future_high high16 high17 future_completed completed17, by(prov_id)
    sort prov_id
    export delimited using "$R4/audit/Round4_L_FOBS_treated_counties_by_province.csv", replace
restore

compress
save `BASE', replace

local outcomes ///
    any_transfer_in_zfill ///
    asinh_transfer_in_area_zfill ///
    asinh_operated_area_end ///
    asinh_farm_income ///
    asinh_household_income_total

postfile PR str18 anchor str16 sample str22 spec str22 model str40 outcome ///
    double b se p long N households counties treated_counties control_counties ///
    str80 status using `RES', replace

foreach anchor in future_high high17 high16 future_completed completed17 {
    foreach sample in full countybal {
        local sampif "county_mappable_skel == 1 & !missing(`anchor')"
        if "`sample'" == "countybal" local sampif "`sampif' & county_bal_pre14 == 1"

        foreach spec in linear_2009_2013 linear_2009_2014 placebo_2013 placebo_2014 placebo_2013_14 {
            local specif "inrange(year, 2009, 2014)"
            tempvar xvar
            gen double `xvar' = .
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
            if "`spec'" == "placebo_2014" {
                replace `xvar' = `anchor' * (year == 2014)
                local specif "inrange(year, 2009, 2014)"
            }
            if "`spec'" == "placebo_2013_14" {
                replace `xvar' = `anchor' * inrange(year, 2013, 2014)
                local specif "inrange(year, 2009, 2014)"
            }

            foreach model in yearfe provyear baseyear prov_baseyear {
                local fepart "i.year"
                local modelif ""
                if "`model'" == "provyear" {
                    local fepart "i.prov_id#i.year"
                }
                if "`model'" == "baseyear" {
                    local fepart "i.year c.base_tin_any#i.year c.base_tin_asinh#i.year c.base_oper#i.year"
                    local modelif "& !missing(base_tin_any, base_tin_asinh, base_oper)"
                }
                if "`model'" == "prov_baseyear" {
                    local fepart "i.prov_id#i.year c.base_tin_any#i.year c.base_tin_asinh#i.year c.base_oper#i.year"
                    local modelif "& !missing(base_tin_any, base_tin_asinh, base_oper)"
                }

                foreach y of local outcomes {
                    capture quietly areg `y' `xvar' `fepart' ///
                        if `sampif' & `specif' & !missing(`y', `xvar', prov_id) `modelif', ///
                        absorb(household_fe) vce(cluster county_id_num)
                    if _rc {
                        post PR ("`anchor'") ("`sample'") ("`spec'") ("`model'") ("`y'") ///
                            (.) (.) (.) (.) (.) (.) (.) (.) ("areg failed")
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

                    post PR ("`anchor'") ("`sample'") ("`spec'") ("`model'") ("`y'") ///
                        (__b) (__se) (__p) (`__N') (__hh) (__cc) (__tc) (__nc) ("ok")
                }
            }
            drop `xvar'
        }
    }
}
postclose PR

use `RES', clear
sort anchor sample spec model outcome
export delimited using "$R4/tables/Round4_L_FOBS_pretrend_refinements.csv", replace

log close
