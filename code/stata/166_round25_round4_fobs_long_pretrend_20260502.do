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
log using "$R4/logs/166_round25_round4_fobs_long_pretrend_20260502.log", replace text

cap which boottest
local has_boottest = (_rc == 0)

tempfile BASE HHRES CAGG

use "$TJFOBS/fobs_household_analysis_panel_hybrid_admin_20260415.dta", clear
capture tostring household_id, replace force
capture destring year county_id_num in_both_segments full_2009_2015 full_2009_2017_candidate ///
    hybrid_rate_high_t hybrid_completion_rate, replace force

gen byte county_mappable_skel = !missing(county_id_num)
gen byte overlap_household = (in_both_segments == 1) if !missing(in_both_segments)
gen byte full_0915 = (full_2009_2015 == 1) if !missing(full_2009_2015)
egen long household_fe = group(household_id)

bysort county_id_num: egen first_high_year = min(cond(hybrid_rate_high_t == 1, year, .))
gen byte future_high = inrange(first_high_year, 2016, 2017) if county_mappable_skel == 1
replace future_high = 0 if county_mappable_skel == 1 & missing(future_high)

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
gen double future_high_slope = future_high * year_c
gen byte pseudo_2013 = (year == 2013) if !missing(year)
gen byte pseudo_2014 = (year == 2014) if !missing(year)
gen byte pseudo_2013_14 = inrange(year, 2013, 2014) if !missing(year)
gen double future_high_pseudo2013 = future_high * pseudo_2013
gen double future_high_pseudo2014 = future_high * pseudo_2014
gen double future_high_pseudo1314 = future_high * pseudo_2013_14

egen byte tag_cy_pre14 = tag(county_id_num year) if county_mappable_skel == 1 & inrange(year, 2009, 2014)
bysort county_id_num: egen n_pre14_years = total(tag_cy_pre14)
gen byte county_bal_pre14 = (n_pre14_years == 6) if county_mappable_skel == 1

compress
save `BASE', replace

preserve
    keep if county_mappable_skel == 1 & inrange(year, 2009, 2014)
    gen one = 1
    collapse (sum) rows=one ///
        (sum) future_high_rows=future_high ///
        (max) future_high_county=future_high ///
        (mean) mean_any_transfer_in=any_transfer_in_zfill ///
        (mean) mean_asinh_transfer_in=asinh_transfer_in_area_zfill, by(year)
    export delimited using "$R4/audit/Round4_F_FOBS_preperiod_year_support.csv", replace
restore

preserve
    keep if county_mappable_skel == 1 & inrange(year, 2009, 2014)
    egen tagc = tag(county_id_num)
    collapse (sum) counties=tagc (sum) future_high_counties=future_high, by(year)
    export delimited using "$R4/audit/Round4_G_FOBS_preperiod_county_support.csv", replace
restore

local outcomes ///
    any_transfer_in_zfill ///
    asinh_transfer_in_area_zfill ///
    any_transfer_in ///
    asinh_transfer_in_area ///
    any_transfer_out_zfill ///
    asinh_transfer_out_area_zfill ///
    asinh_operated_area_end ///
    asinh_farm_income ///
    asinh_household_income_total ///
    asinh_local_wage_income ///
    asinh_migrant_wage_income

postfile HH str18 sample str24 spec str40 outcome ///
    double b se p wild_p long N households counties future_high_counties control_counties reps ///
    str80 status using `HHRES', replace

foreach sample in full countybal long0915 overlap {
    local sampif "county_mappable_skel == 1 & !missing(future_high)"
    if "`sample'" == "countybal" local sampif "`sampif' & county_bal_pre14 == 1"
    if "`sample'" == "long0915"  local sampif "`sampif' & full_0915 == 1"
    if "`sample'" == "overlap"   local sampif "`sampif' & overlap_household == 1"

    foreach spec in linear_2009_2013 linear_2009_2014 placebo_2013 placebo_2014 placebo_2013_14 {
        local specif "inrange(year, 2009, 2014)"
        local xvar "future_high_slope"
        if "`spec'" == "linear_2009_2013" local specif "inrange(year, 2009, 2013)"
        if "`spec'" == "linear_2009_2014" local specif "inrange(year, 2009, 2014)"
        if "`spec'" == "placebo_2013" {
            local specif "inrange(year, 2009, 2013)"
            local xvar "future_high_pseudo2013"
        }
        if "`spec'" == "placebo_2014" {
            local specif "inrange(year, 2009, 2014)"
            local xvar "future_high_pseudo2014"
        }
        if "`spec'" == "placebo_2013_14" {
            local specif "inrange(year, 2009, 2014)"
            local xvar "future_high_pseudo1314"
        }

        foreach y of local outcomes {
            use `BASE', clear
            capture confirm variable `y'
            if _rc {
                post HH ("`sample'") ("`spec'") ("`y'") ///
                    (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) ("missing outcome")
                continue
            }

            capture noisily areg `y' `xvar' i.year if `sampif' & `specif' & !missing(`y', `xvar'), ///
                absorb(household_fe) vce(cluster county_id_num)
            if _rc {
                post HH ("`sample'") ("`spec'") ("`y'") ///
                    (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) ("areg failed")
                continue
            }

            scalar __b  = _b[`xvar']
            scalar __se = _se[`xvar']
            scalar __p  = 2 * ttail(e(df_r), abs(__b / __se))
            local __N = e(N)

            quietly egen __tagh = tag(household_fe) if e(sample)
            quietly count if __tagh == 1
            scalar __hh = r(N)
            drop __tagh

            quietly egen __tagc = tag(county_id_num) if e(sample)
            quietly count if __tagc == 1
            scalar __cc = r(N)
            drop __tagc

            quietly egen __tagtc = tag(county_id_num) if e(sample) & future_high == 1
            quietly count if __tagtc == 1
            scalar __tc = r(N)
            drop __tagtc

            quietly egen __tagnc = tag(county_id_num) if e(sample) & future_high == 0
            quietly count if __tagnc == 1
            scalar __nc = r(N)
            drop __tagnc

            scalar __wildp = .
            scalar __reps = .
            local stat "ok"
            if `has_boottest' {
                capture noisily boottest `xvar', cluster(county_id_num) reps(999) seed(20260502) ///
                    weight(webb) nograph quietly
                if !_rc {
                    scalar __wildp = r(p)
                    scalar __reps = r(reps)
                }
                else local stat "boottest failed"
            }
            else local stat "boottest unavailable"

            post HH ("`sample'") ("`spec'") ("`y'") ///
                (__b) (__se) (__p) (__wildp) (`__N') (__hh) (__cc) (__tc) (__nc) (__reps) ("`stat'")
        }
    }
}
postclose HH

use `HHRES', clear
sort sample spec outcome
export delimited using "$R4/tables/Round4_H_FOBS_household_long_pretrends.csv", replace

postfile CA str18 sample str24 spec str40 outcome ///
    double b se p long N counties future_high_counties control_counties ///
    str80 status using `CAGG', replace

foreach sample in full countybal {
    local sampif "county_mappable_skel == 1 & !missing(future_high)"
    if "`sample'" == "countybal" local sampif "`sampif' & county_bal_pre14 == 1"

    foreach spec in linear_2009_2013 linear_2009_2014 placebo_2013 placebo_2014 placebo_2013_14 {
        local specif "inrange(year, 2009, 2014)"
        local xvar "future_high_slope"
        if "`spec'" == "linear_2009_2013" local specif "inrange(year, 2009, 2013)"
        if "`spec'" == "linear_2009_2014" local specif "inrange(year, 2009, 2014)"
        if "`spec'" == "placebo_2013" {
            local specif "inrange(year, 2009, 2013)"
            local xvar "future_high_pseudo2013"
        }
        if "`spec'" == "placebo_2014" {
            local specif "inrange(year, 2009, 2014)"
            local xvar "future_high_pseudo2014"
        }
        if "`spec'" == "placebo_2013_14" {
            local specif "inrange(year, 2009, 2014)"
            local xvar "future_high_pseudo1314"
        }

        foreach y of local outcomes {
            use `BASE', clear
            capture confirm variable `y'
            if _rc {
                post CA ("`sample'") ("`spec'") ("`y'") ///
                    (.) (.) (.) (.) (.) (.) (.) ("missing outcome")
                continue
            }

            keep if `sampif' & `specif' & !missing(`y', `xvar')
            if _N == 0 {
                post CA ("`sample'") ("`spec'") ("`y'") ///
                    (.) (.) (.) (.) (.) (.) (.) ("empty sample")
                continue
            }
            collapse (mean) `y' `xvar' future_high (count) rows=`y', by(county_id_num year)

            capture noisily areg `y' `xvar' i.year [aw=rows], absorb(county_id_num) vce(cluster county_id_num)
            if _rc {
                post CA ("`sample'") ("`spec'") ("`y'") ///
                    (.) (.) (.) (.) (.) (.) (.) ("county areg failed")
                continue
            }

            scalar __b  = _b[`xvar']
            scalar __se = _se[`xvar']
            scalar __p  = 2 * ttail(e(df_r), abs(__b / __se))
            local __N = e(N)

            quietly egen __tagc = tag(county_id_num) if e(sample)
            quietly count if __tagc == 1
            scalar __cc = r(N)
            drop __tagc

            quietly egen __tagtc = tag(county_id_num) if e(sample) & future_high == 1
            quietly count if __tagtc == 1
            scalar __tc = r(N)
            drop __tagtc

            quietly egen __tagnc = tag(county_id_num) if e(sample) & future_high == 0
            quietly count if __tagnc == 1
            scalar __nc = r(N)
            drop __tagnc

            post CA ("`sample'") ("`spec'") ("`y'") ///
                (__b) (__se) (__p) (`__N') (__cc) (__tc) (__nc) ("ok")
        }
    }
}
postclose CA

use `CAGG', clear
sort sample spec outcome
export delimited using "$R4/tables/Round4_I_FOBS_countyagg_long_pretrends.csv", replace

log close
