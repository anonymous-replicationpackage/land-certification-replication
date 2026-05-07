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
cap mkdir "`OUT'/logs"

cap log close _all
log using "`OUT'/logs/176_round25_round5d_fobs_maturity_pretrend_placebo_20260502.log", replace text

local FOBS "$ROOT/data/topjournal_rebuild/fobs/fobs_household_analysis_panel_hybrid_admin_20260415.dta"

tempfile BASE PREOUT EVOUT

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
gen byte mature_high = (maturity3==3) if !missing(maturity3)
gen byte mature_mid = (maturity3>=2) if !missing(maturity3)

bys county_id_num: egen has_maturity = max(!missing(maturity3))
bys county_id_num: egen first_high_year = min(cond(mature_high==1, year, .))
bys county_id_num: egen first_mid_year = min(cond(mature_mid==1, year, .))
bys county_id_num: egen ever_high = max(mature_high)
bys county_id_num: egen ever_mid = max(mature_mid)
replace ever_high = 0 if missing(ever_high)
replace ever_mid = 0 if missing(ever_mid)
gen double year_idx = year - 2009
gen double trend_ever_high = year_idx*ever_high
gen double trend_ever_mid = year_idx*ever_mid

gen double rel_high = year - first_high_year if !missing(first_high_year)
gen byte lead2p_high = (rel_high<=-2) if !missing(mature_high)
gen byte event0_high = (rel_high==0) if !missing(mature_high)
gen byte lag1_high = (rel_high==1) if !missing(mature_high)
gen byte lag2p_high = (rel_high>=2) if !missing(mature_high)
foreach v in lead2p_high event0_high lag1_high lag2p_high {
    replace `v' = 0 if missing(`v') & !missing(maturity3)
}

compress
save `BASE', replace

postfile PP str12 sample str24 outcome str12 future_group ///
    double b_pretrend se_pretrend p_pretrend long N households counties using `PREOUT', replace

foreach sample in full overlap long {
    local sampif "1==1"
    if "`sample'"=="overlap" local sampif "overlap_household==1"
    if "`sample'"=="long" local sampif "long_household==1"

    foreach y in asinh_operated_area_end asinh_farm_income any_transfer_in_zfill asinh_transfer_in_area_zfill {
        foreach g in ever_high ever_mid {
            use `BASE', clear
            local tg trend_`g'
            keep if `sampif' & has_maturity==1 & year<=2014 & !missing(`y', maturity3, `g', `tg')
            cap noisily reghdfe `y' `tg', absorb(hh_fe year) vce(cluster county_id_num)
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
                scalar `pp' = 2*ttail(e(df_r), abs(_b[`tg']/_se[`tg']))
                post PP ("`sample'") ("`y'") ("`g'") ///
                    (_b[`tg']) (_se[`tg']) (`pp') (e(N)) (`HH') (`CC')
            }
        }
    }
}
postclose PP
use `PREOUT', clear
sort sample outcome future_group
export delimited using "`OUT'/tables/Round5D_A_FOBS_future_maturity_pretrends.csv", replace

postfile PE str12 sample str24 outcome str24 term double b se p long N households counties using `EVOUT', replace
foreach sample in full overlap long {
    local sampif "1==1"
    if "`sample'"=="overlap" local sampif "overlap_household==1"
    if "`sample'"=="long" local sampif "long_household==1"
    foreach y in asinh_operated_area_end asinh_farm_income {
        use `BASE', clear
        keep if `sampif' & !missing(`y', maturity3)
        cap noisily reghdfe `y' lead2p_high event0_high lag1_high lag2p_high, absorb(hh_fe year) vce(cluster county_id_num)
        if !_rc {
            tempvar es tagh tagc
            gen byte `es' = e(sample)
            egen byte `tagh' = tag(hh_fe) if `es'
            egen byte `tagc' = tag(county_id_num) if `es'
            quietly count if `tagh'==1
            local HH = r(N)
            quietly count if `tagc'==1
            local CC = r(N)
            foreach x in lead2p_high event0_high lag1_high lag2p_high {
                tempname pp
                scalar `pp' = 2*ttail(e(df_r), abs(_b[`x']/_se[`x']))
                post PE ("`sample'") ("`y'") ("`x'") (_b[`x']) (_se[`x']) (`pp') (e(N)) (`HH') (`CC')
            }
        }
    }
}
postclose PE
use `EVOUT', clear
sort sample outcome term
export delimited using "`OUT'/tables/Round5D_B_FOBS_high_event_probe.csv", replace

log close
