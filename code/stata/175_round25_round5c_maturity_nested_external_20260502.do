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
log using "`OUT'/logs/175_round25_round5c_maturity_nested_external_20260502.log", replace text

local FOBS "$ROOT/data/topjournal_rebuild/fobs/fobs_household_analysis_panel_hybrid_admin_20260415.dta"

tempfile BASE HHRES AGGBASE AGGRES SUPP

use "`FOBS'", clear
capture tostring household_id, replace force
capture destring year county_id_num in_both_segments full_2009_2017_candidate ///
    hybrid_rate_any_t hybrid_rate_mid_t hybrid_rate_high_t hybrid_completion_rate, replace force
keep if !missing(county_id_num, year)
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

gen byte mature_any = (maturity3>=1) if !missing(maturity3)
gen byte mature_mid = (maturity3>=2) if !missing(maturity3)
gen byte mature_high = (maturity3==3) if !missing(maturity3)

gen double completion_rate0 = hybrid_completion_rate
replace completion_rate0 = 0 if maturity3==0 & missing(completion_rate0)
replace completion_rate0 = 0 if maturity3==0 & completion_rate0<0
replace completion_rate0 = . if missing(maturity3)

bys county_id_num: egen first_high_year = min(cond(mature_high==1, year, .))
gen double years_since_high = 0 if !missing(maturity3)
replace years_since_high = year - first_high_year + 1 if !missing(first_high_year) & year>=first_high_year
replace years_since_high = 0 if years_since_high<0 & !missing(years_since_high)
replace years_since_high = min(years_since_high, 3) if !missing(years_since_high)

compress
save `BASE', replace

* Fixed-sample support: after maturity3 is constructed, all thresholds are nested.
postfile PS str12 sample str18 item long rows households counties positive_rows positive_hh positive_counties using `SUPP', replace
foreach sample in full overlap long {
    use `BASE', clear
    local sampif "1==1"
    if "`sample'"=="overlap" local sampif "overlap_household==1"
    if "`sample'"=="long" local sampif "long_household==1"
    keep if `sampif' & !missing(maturity3)
    foreach v in mature_any mature_mid mature_high {
        quietly count
        local rows = r(N)
        cap drop __tagh __tagc __taghp __tagcp
        egen byte __tagh = tag(hh_fe)
        egen byte __tagc = tag(county_id_num)
        quietly count if __tagh==1
        local hh = r(N)
        quietly count if __tagc==1
        local cc = r(N)
        quietly count if `v'==1
        local prow = r(N)
        egen byte __taghp = tag(hh_fe) if `v'==1
        egen byte __tagcp = tag(county_id_num) if `v'==1
        quietly count if __taghp==1
        local phh = r(N)
        quietly count if __tagcp==1
        local pcc = r(N)
        post PS ("`sample'") ("`v'") (`rows') (`hh') (`cc') (`prow') (`phh') (`pcc')
    }
}
postclose PS
use `SUPP', clear
export delimited using "`OUT'/audit/Round5C_A_FOBS_nested_threshold_support.csv", replace

postfile PH str12 sample str24 outcome str24 spec str32 term ///
    double b se p long N households counties using `HHRES', replace

foreach sample in full overlap long {
    local sampif "1==1"
    if "`sample'"=="overlap" local sampif "overlap_household==1"
    if "`sample'"=="long" local sampif "long_household==1"

    foreach y in any_transfer_in_zfill asinh_transfer_in_area_zfill asinh_operated_area_end asinh_farm_income farm_income_share {
        foreach x in mature_any mature_mid mature_high completion_rate0 years_since_high {
            use `BASE', clear
            keep if `sampif' & !missing(`y', maturity3, `x')
            cap noisily reghdfe `y' `x', absorb(hh_fe year) vce(cluster county_id_num)
            if !_rc {
                tempvar es tagh tagc
                gen byte `es' = e(sample)
                egen byte `tagh' = tag(hh_fe) if `es'
                egen byte `tagc' = tag(county_id_num) if `es'
                quietly count if `tagh'==1
                local HH = r(N)
                quietly count if `tagc'==1
                local CC = r(N)
                tempname pp
                scalar `pp' = 2*ttail(e(df_r), abs(_b[`x']/_se[`x']))
                post PH ("`sample'") ("`y'") ("fixed_threshold") ("`x'") (_b[`x']) (_se[`x']) (`pp') (e(N)) (`HH') (`CC')
            }
        }

        use `BASE', clear
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
                if !_rc post PH ("`sample'") ("`y'") ("stage") ("stage`k'_vs0") (r(estimate)) (r(se)) (r(p)) (e(N)) (`HH') (`CC')
            }
            cap quietly lincom 3.maturity3 - 1.maturity3
            if !_rc post PH ("`sample'") ("`y'") ("stage") ("stage3_minus_stage1") (r(estimate)) (r(se)) (r(p)) (e(N)) (`HH') (`CC')
            cap quietly lincom 3.maturity3 - 2.maturity3
            if !_rc post PH ("`sample'") ("`y'") ("stage") ("stage3_minus_stage2") (r(estimate)) (r(se)) (r(p)) (e(N)) (`HH') (`CC')
        }
    }
}
postclose PH
use `HHRES', clear
sort sample outcome spec term
export delimited using "`OUT'/tables/Round5C_B_FOBS_household_fixedsample_maturity.csv", replace

* County-year aggregation: checks whether the mature-implementation signal survives
* when household composition is collapsed before estimation.
use `BASE', clear
gen byte ok_any = !missing(any_transfer_in_zfill)
gen byte ok_trarea = !missing(asinh_transfer_in_area_zfill)
gen byte ok_oparea = !missing(asinh_operated_area_end)
gen byte ok_finc = !missing(asinh_farm_income)
gen byte ok_fshare = !missing(farm_income_share)
collapse ///
    (mean) any_transfer_in_zfill asinh_transfer_in_area_zfill asinh_operated_area_end asinh_farm_income farm_income_share ///
    (firstnm) mature_any mature_mid mature_high completion_rate0 years_since_high maturity3 ///
    (sum) n_any=ok_any n_trarea=ok_trarea n_oparea=ok_oparea n_finc=ok_finc n_fshare=ok_fshare, by(county_id_num year)
save `AGGBASE', replace

postfile PA str24 outcome str24 spec str32 term double b se p long N counties using `AGGRES', replace
foreach y in any_transfer_in_zfill asinh_transfer_in_area_zfill asinh_operated_area_end asinh_farm_income farm_income_share {
    local wy n_any
    if "`y'"=="asinh_transfer_in_area_zfill" local wy n_trarea
    if "`y'"=="asinh_operated_area_end" local wy n_oparea
    if "`y'"=="asinh_farm_income" local wy n_finc
    if "`y'"=="farm_income_share" local wy n_fshare
    foreach x in mature_any mature_mid mature_high completion_rate0 years_since_high {
        use `AGGBASE', clear
        keep if !missing(`y', maturity3, `x') & `wy'>0
        cap noisily reghdfe `y' `x' [aw=`wy'], absorb(county_id_num year) vce(cluster county_id_num)
        if !_rc {
            tempvar es tagc
            gen byte `es' = e(sample)
            egen byte `tagc' = tag(county_id_num) if `es'
            quietly count if `tagc'==1
            local CC = r(N)
            tempname pp
            scalar `pp' = 2*ttail(e(df_r), abs(_b[`x']/_se[`x']))
            post PA ("`y'") ("county_agg_aw") ("`x'") (_b[`x']) (_se[`x']) (`pp') (e(N)) (`CC')
        }
    }

    use `AGGBASE', clear
    keep if !missing(`y', maturity3) & `wy'>0
    cap noisily reghdfe `y' ib0.maturity3 [aw=`wy'], absorb(county_id_num year) vce(cluster county_id_num)
    if !_rc {
        tempvar es tagc
        gen byte `es' = e(sample)
        egen byte `tagc' = tag(county_id_num) if `es'
        quietly count if `tagc'==1
        local CC = r(N)
        foreach k in 1 2 3 {
            cap quietly lincom `k'.maturity3
            if !_rc post PA ("`y'") ("county_agg_aw_stage") ("stage`k'_vs0") (r(estimate)) (r(se)) (r(p)) (e(N)) (`CC')
        }
        cap quietly lincom 3.maturity3 - 1.maturity3
        if !_rc post PA ("`y'") ("county_agg_aw_stage") ("stage3_minus_stage1") (r(estimate)) (r(se)) (r(p)) (e(N)) (`CC')
        cap quietly lincom 3.maturity3 - 2.maturity3
        if !_rc post PA ("`y'") ("county_agg_aw_stage") ("stage3_minus_stage2") (r(estimate)) (r(se)) (r(p)) (e(N)) (`CC')
    }
}
postclose PA
use `AGGRES', clear
sort outcome spec term
export delimited using "`OUT'/tables/Round5C_C_FOBS_countyagg_maturity.csv", replace

log close
