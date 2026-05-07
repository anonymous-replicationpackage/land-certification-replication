version 17
clear all
set more off
set linesize 255
set varabbrev off

local ROOT = subinstr("`c(pwd)'", char(92), "/", .)
if !fileexists("`ROOT'/dofiles/01_globals_and_ado.do") {
    while !fileexists("`ROOT'/dofiles/01_globals_and_ado.do") & "`ROOT'" != "" {
        local ROOT = regexr("`ROOT'", "/[^/]+$", "")
    }
}
global ROOT "`ROOT'"
do "$ROOT/code/stata/01_globals_and_ado.do"

cap which reghdfe
if _rc {
    di as error "reghdfe is required but was not found."
    exit 111
}

local OUT "$ROOT/result/round25_empirical_rebuild_20260501/round2b_deeper_a3_exploration"
cap mkdir "$ROOT/result"
cap mkdir "$ROOT/result/round25_empirical_rebuild_20260501"
cap mkdir "`OUT'"
cap mkdir "`OUT'/tables"
cap mkdir "`OUT'/audit"
cap mkdir "`OUT'/logs"

cap log close _all
log using "`OUT'/logs/158_round25_round2b_deeper_a3_exploration_20260502.log", replace text

local PANEL   "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_indivbridge_20260416.dta"
local RGPANEL "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_rightsgap_20260415.dta"
local ADMINCY "$ROOT/data/topjournal_rebuild/admin/admin_rollout_countyyear_v2.dta"

tempfile ADMINUSE RGM BASE

use "`ADMINCY'", clear
keep county_id_num year county_started_t county_signedoff_t county_issued_t county_completed_t county_sat_t county_completion_rate
rename county_id_num __cid_id
gen byte signoff_or_issue_t = ((county_signedoff_t==1) | (county_issued_t==1)) ///
    if !missing(county_signedoff_t) | !missing(county_issued_t)
gen byte completed_t = county_completed_t if !missing(county_completed_t)
gen byte high_sat80_t = (county_sat_t>=0.8) if !missing(county_sat_t)
gen byte started_t = county_started_t if !missing(county_started_t)
compress
save `ADMINUSE', replace

use "`RGPANEL'", clear
keep hid year __cid_id ///
    base14_rg_readjust base14_rg_disp_newpop base14_rg_disp_women ///
    base14_rg_readj_reason base14_rg_readj_method base14_rg_noreadj_reason ///
    base14_rg_abs_idle base14_rg_abs_proxy base14_rg_abs_rent base14_rg_abs_share ///
    base14_rg_req_any base14_rg_govrent_any base14_rg_daigeng_any base14_rg_transfer_kin ///
    base14_rg_govrent_area base14_rg_govrent_fee base14_rg_daigeng_area ///
    base14_instab_sum base14_absorg_sum base14_external_sum ///
    base14_broad_mean base14_broad_z base14_high_broad ///
    pre12_rg_pre_gov_any pre12_rg_pre_dg_any pre12_rg_pretransfer_sum
duplicates drop hid year __cid_id, force
save `RGM', replace

use "`PANEL'", clear
keep if inlist(year, 2014, 2016, 2018)
merge 1:1 hid year __cid_id using `RGM', keep(master match) nogen
merge m:1 __cid_id year using `ADMINUSE', keep(master match) nogen

gen byte official2014_prov = inlist(__prov_id, 34, 37, 51)
gen byte admin_start_by2014 = (admin_rollout_start_year<=2014) if !missing(admin_rollout_start_year)
replace admin_start_by2014 = 0 if missing(admin_start_by2014)

* Household baseline land exposure. These are frozen at 2014.
bys hid: egen double base_contract_land = max(cond(year==2014, contracted_land_mu, .))
bys hid: egen double base_total_land = max(cond(year==2014, land_total_mu, .))
gen double base_land_mu = base_contract_land
replace base_land_mu = base_total_land if missing(base_land_mu)

quietly summarize base_land_mu if year==2014 & s_mech_hh==1 & base_land_mu>0, detail
local landp25 = r(p25)
local landp50 = r(p50)
local landp75 = r(p75)

gen byte mod_landpoor = (base_land_mu<=`landp25') if !missing(base_land_mu)
gen byte mod_landbelowmed = (base_land_mu<=`landp50') if !missing(base_land_mu)
gen byte mod_landrich = (base_land_mu>=`landp75') if !missing(base_land_mu)
gen byte mod_baseland_zero = (base_land_mu<=0) if !missing(base_land_mu)

* Fine-grained C15/C16 recodes. Codes from 2014 community questionnaire:
* C15_1: 1 expropriation; 2 population change; 3 second-round contracting; 99 other.
* C15_2: 1 reserved collective land; 2 partial/small adjustment; 3 complete reshuffle; 99 other.
* C16: 1 policy forbids adjustment; 2 villagers do not need it; 99 other.
gen byte mod_readjust = (base14_rg_readjust==1) if !missing(base14_rg_readjust)

gen byte mod_readj_pop = (base14_rg_readj_reason==2) if !missing(base14_rg_readjust)
replace mod_readj_pop = 0 if base14_rg_readjust==0

gen byte mod_readj_exprop = (base14_rg_readj_reason==1) if !missing(base14_rg_readjust)
replace mod_readj_exprop = 0 if base14_rg_readjust==0

gen byte mod_readj_secondround = (base14_rg_readj_reason==3) if !missing(base14_rg_readjust)
replace mod_readj_secondround = 0 if base14_rg_readjust==0

gen byte mod_method_reserved = (base14_rg_readj_method==1) if !missing(base14_rg_readjust)
replace mod_method_reserved = 0 if base14_rg_readjust==0

gen byte mod_method_small = (base14_rg_readj_method==2) if !missing(base14_rg_readjust)
replace mod_method_small = 0 if base14_rg_readjust==0

gen byte mod_method_full = (base14_rg_readj_method==3) if !missing(base14_rg_readjust)
replace mod_method_full = 0 if base14_rg_readjust==0

gen byte mod_policy_noadj = (base14_rg_readjust==0 & base14_rg_noreadj_reason==1) if !missing(base14_rg_readjust)
gen byte mod_nodemand_noadj = (base14_rg_readjust==0 & base14_rg_noreadj_reason==2) if !missing(base14_rg_readjust)

gen byte mod_pop_dispute = 0 if !missing(base14_rg_readjust)
replace mod_pop_dispute = 1 if base14_rg_disp_newpop==1 | base14_rg_disp_women==1

gen byte mod_internal_pressure = 0 if !missing(base14_rg_readjust)
replace mod_internal_pressure = 1 if base14_rg_readj_reason==2 | base14_rg_disp_newpop==1 | base14_rg_disp_women==1

gen byte mod_intrusive_realloc = 0 if !missing(base14_rg_readjust)
replace mod_intrusive_realloc = 1 if base14_rg_readj_method==2 | base14_rg_readj_method==3

gen byte mod_highintrusion_core = 0 if !missing(base14_rg_readjust)
replace mod_highintrusion_core = 1 if base14_rg_readj_method==3 | base14_rg_disp_newpop==1 | base14_rg_disp_women==1

gen byte mod_rule_constrained = mod_policy_noadj
gen byte mod_no_adjust_any = (base14_rg_readjust==0) if !missing(base14_rg_readjust)

* Village land-market and absentee-land environment.
gen byte mod_absentee_idle = (base14_rg_abs_idle==1) if !missing(base14_rg_abs_idle)
gen byte mod_absentee_proxy = (base14_rg_abs_proxy==1) if !missing(base14_rg_abs_proxy)
gen byte mod_absentee_rent = (base14_rg_abs_rent==1) if !missing(base14_rg_abs_rent)
gen byte mod_govrent = (base14_rg_govrent_any==1) if !missing(base14_rg_govrent_any)
gen byte mod_daigeng = (base14_rg_daigeng_any==1) if !missing(base14_rg_daigeng_any)
gen byte mod_kin_transfer = (base14_rg_transfer_kin==1) if !missing(base14_rg_transfer_kin)

egen byte __market_n = rownonmiss(base14_rg_abs_rent base14_rg_govrent_any base14_rg_daigeng_any base14_rg_transfer_kin)
egen byte __market_any = rowmax(base14_rg_abs_rent base14_rg_govrent_any base14_rg_daigeng_any base14_rg_transfer_kin)
gen byte mod_market_active = __market_any if __market_n>0
drop __market_n __market_any

* Combined village condition x household land exposure. Names are kept short for Stata.
gen byte mod_rj_landpoor = (mod_readjust==1 & mod_landpoor==1) if !missing(mod_readjust, mod_landpoor)
gen byte mod_rj_landmed = (mod_readjust==1 & mod_landbelowmed==1) if !missing(mod_readjust, mod_landbelowmed)
gen byte mod_rjpop_landpoor = (mod_readj_pop==1 & mod_landpoor==1) if !missing(mod_readj_pop, mod_landpoor)
gen byte mod_rjpop_landmed = (mod_readj_pop==1 & mod_landbelowmed==1) if !missing(mod_readj_pop, mod_landbelowmed)
gen byte mod_intrn_landpoor = (mod_internal_pressure==1 & mod_landpoor==1) if !missing(mod_internal_pressure, mod_landpoor)
gen byte mod_intrn_landmed = (mod_internal_pressure==1 & mod_landbelowmed==1) if !missing(mod_internal_pressure, mod_landbelowmed)
gen byte mod_intrsv_landpoor = (mod_intrusive_realloc==1 & mod_landpoor==1) if !missing(mod_intrusive_realloc, mod_landpoor)
gen byte mod_intrsv_landmed = (mod_intrusive_realloc==1 & mod_landbelowmed==1) if !missing(mod_intrusive_realloc, mod_landbelowmed)
gen byte mod_polnoadj_landpoor = (mod_policy_noadj==1 & mod_landpoor==1) if !missing(mod_policy_noadj, mod_landpoor)
gen byte mod_polnoadj_landmed = (mod_policy_noadj==1 & mod_landbelowmed==1) if !missing(mod_policy_noadj, mod_landbelowmed)
gen byte mod_mkt_landpoor = (mod_market_active==1 & mod_landpoor==1) if !missing(mod_market_active, mod_landpoor)
gen byte mod_mkt_landmed = (mod_market_active==1 & mod_landbelowmed==1) if !missing(mod_market_active, mod_landbelowmed)

* Continuous risk/credibility scores.
gen double risk_demographic = 0 if !missing(base14_rg_readjust)
replace risk_demographic = risk_demographic + 1 if base14_rg_readj_reason==2
replace risk_demographic = risk_demographic + 1 if base14_rg_disp_newpop==1
replace risk_demographic = risk_demographic + 1 if base14_rg_disp_women==1

gen double risk_intrusion = 0 if !missing(base14_rg_readjust)
replace risk_intrusion = 0.5 if base14_rg_readj_method==1
replace risk_intrusion = 1.0 if base14_rg_readj_method==2
replace risk_intrusion = 2.0 if base14_rg_readj_method==3
replace risk_intrusion = risk_intrusion + 0.5 if base14_rg_disp_newpop==1
replace risk_intrusion = risk_intrusion + 0.5 if base14_rg_disp_women==1

gen double tenure_credibility = . 
replace tenure_credibility = 2.0 if base14_rg_readjust==0 & base14_rg_noreadj_reason==1
replace tenure_credibility = 1.5 if base14_rg_readjust==0 & base14_rg_noreadj_reason==2
replace tenure_credibility = 1.0 if base14_rg_readjust==0 & base14_rg_noreadj_reason==99
replace tenure_credibility = 1.0 if base14_rg_readj_method==1
replace tenure_credibility = 0.5 if base14_rg_readj_method==2 | base14_rg_readj_reason==3
replace tenure_credibility = 0.0 if base14_rg_readj_method==3 | base14_rg_readj_reason==2 | base14_rg_disp_newpop==1 | base14_rg_disp_women==1

egen double market_env_sum = rowtotal(base14_rg_abs_rent base14_rg_govrent_any base14_rg_daigeng_any base14_rg_transfer_kin)
egen byte market_env_nonmiss = rownonmiss(base14_rg_abs_rent base14_rg_govrent_any base14_rg_daigeng_any base14_rg_transfer_kin)
replace market_env_sum = . if market_env_nonmiss==0
drop market_env_nonmiss

foreach v in risk_demographic risk_intrusion tenure_credibility market_env_sum base_land_mu {
    cap drop z_`v'
    quietly summarize `v' if year==2014 & s_mech_hh==1
    if r(sd)>0 & r(sd)<. gen double z_`v' = (`v' - r(mean))/r(sd) if !missing(`v')
    else gen double z_`v' = .
}

compress
save `BASE', replace

* ------------------------------------------------------------------
* A. Baseline and stacked support audit
* ------------------------------------------------------------------

local BINMODS "mod_readjust mod_readj_pop mod_readj_exprop mod_readj_secondround mod_method_reserved mod_method_small mod_method_full mod_policy_noadj mod_nodemand_noadj mod_pop_dispute mod_internal_pressure mod_intrusive_realloc mod_highintrusion_core mod_rule_constrained mod_no_adjust_any mod_absentee_idle mod_absentee_proxy mod_absentee_rent mod_govrent mod_daigeng mod_kin_transfer mod_market_active mod_landpoor mod_landbelowmed mod_landrich mod_baseland_zero mod_rj_landpoor mod_rjpop_landpoor mod_intrn_landpoor mod_intrsv_landpoor mod_polnoadj_landpoor mod_mkt_landpoor mod_rj_landmed mod_rjpop_landmed mod_intrn_landmed mod_intrsv_landmed mod_polnoadj_landmed mod_mkt_landmed"

local mod_readjust_lab "readjust_any"
local mod_readj_pop_lab "readjust_population_reason"
local mod_readj_exprop_lab "readjust_expropriation_reason"
local mod_readj_secondround_lab "readjust_secondround_reason"
local mod_method_reserved_lab "method_reserved_land"
local mod_method_small_lab "method_small_adjustment"
local mod_method_full_lab "method_full_reshuffle"
local mod_policy_noadj_lab "no_adjust_policy_forbids"
local mod_nodemand_noadj_lab "no_adjust_no_demand"
local mod_pop_dispute_lab "population_or_women_dispute"
local mod_internal_pressure_lab "internal_demographic_pressure"
local mod_intrusive_realloc_lab "small_or_full_reallocation"
local mod_highintrusion_core_lab "full_or_dispute_core"
local mod_rule_constrained_lab "rule_constrained_no_adjust"
local mod_no_adjust_any_lab "no_adjust_any"
local mod_absentee_idle_lab "absentee_land_idle"
local mod_absentee_proxy_lab "absentee_land_proxy"
local mod_absentee_rent_lab "absentee_land_rented"
local mod_govrent_lab "village_rent_to_orgs"
local mod_daigeng_lab "village_daigeng"
local mod_kin_transfer_lab "kin_transfer_present"
local mod_market_active_lab "baseline_land_market_active"
local mod_landpoor_lab "household_land_poor_p25"
local mod_landbelowmed_lab "household_land_below_median"
local mod_landrich_lab "household_land_rich_p75"
local mod_baseland_zero_lab "household_zero_land"
local mod_rj_landpoor_lab "readjust_x_landpoor"
local mod_rjpop_landpoor_lab "pop_readjust_x_landpoor"
local mod_intrn_landpoor_lab "internal_pressure_x_landpoor"
local mod_intrsv_landpoor_lab "intrusive_realloc_x_landpoor"
local mod_polnoadj_landpoor_lab "policy_noadj_x_landpoor"
local mod_mkt_landpoor_lab "market_active_x_landpoor"
local mod_rj_landmed_lab "readjust_x_landbelowmed"
local mod_rjpop_landmed_lab "pop_readjust_x_landbelowmed"
local mod_intrn_landmed_lab "internal_pressure_x_landbelowmed"
local mod_intrsv_landmed_lab "intrusive_realloc_x_landbelowmed"
local mod_polnoadj_landmed_lab "policy_noadj_x_landbelowmed"
local mod_mkt_landmed_lab "market_active_x_landbelowmed"

tempfile SUPP
postfile PS str40 moderator str60 label long rows households counties villages double share using `SUPP', replace
foreach M of local BINMODS {
    use `BASE', clear
    keep if year==2014 & s_mech_hh==1 & !missing(`M')
    quietly count
    local rows = r(N)
    egen byte __tagh = tag(hid)
    egen byte __tagc = tag(__cid_id)
    egen byte __tagv = tag(village_id)
    quietly count if __tagh==1
    local hh = r(N)
    quietly count if __tagc==1
    local cc = r(N)
    quietly count if __tagv==1
    local vv = r(N)
    quietly summarize `M', meanonly
    local share = r(mean)
    post PS ("`M'") ("``M'_lab'") (`rows') (`hh') (`cc') (`vv') (`share')
}
postclose PS
use `SUPP', clear
export delimited using "`OUT'/audit/Round2B_A1_new_moderator_baseline_support.csv", replace

* ------------------------------------------------------------------
* B. Stacked DID programs
* ------------------------------------------------------------------

cap program drop __r2b_stack_bin
program define __r2b_stack_bin
    syntax, BASEFILE(string) POSTH(name) SCOPE(string) RESTRICT(string) THRVAR(name) THRNAME(string) OUTCOME(name) MODVAR(name) MODNAME(string)

    use "`basefile'", clear
    keep if s_mech_hh==1
    if "`scope'"=="adjacent" keep if timing_adjacent_hh==1
    if "`restrict'"=="exclude_official2014" drop if official2014_prov==1
    if "`restrict'"=="exclude_admin_start_by2014" drop if admin_start_by2014==1

    bys __cid_id: egen first_thr = min(cond(`thrvar'==1, year, .))
    gen byte never_thr = missing(first_thr)
    keep if never_thr==1 | inlist(first_thr, 2016, 2018)

    tempfile W16 W18
    preserve
        keep if inlist(year, 2014, 2016) & (first_thr==2016 | first_thr==2018 | never_thr==1)
        gen byte treated = (first_thr==2016)
        gen byte post = (year==2016)
        gen byte winflag = 0
        save `W16', replace
    restore
    preserve
        keep if inlist(year, 2016, 2018) & (first_thr==2018 | never_thr==1)
        gen byte treated = (first_thr==2018)
        gen byte post = (year==2018)
        gen byte winflag = 1
        save `W18', replace
    restore

    use `W16', clear
    append using `W18'
    egen long hid_stack = group(winflag hid)
    egen long year_stack = group(winflag year)

    quietly count if !missing(`outcome', `modvar')
    if r(N)<50 {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("error") (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) ("too few nonmissing")
        exit
    }
    quietly summarize `modvar' if !missing(`outcome', `modvar'), meanonly
    if r(min)==r(max) {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("error") (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) ("no moderator variation")
        exit
    }

    cap noisily reghdfe `outcome' i.treated##i.post##i.`modvar' if !missing(`outcome', `modvar'), absorb(hid_stack year_stack) vce(cluster __cid_id)
    if _rc {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("error") (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) ("regression failed")
        exit
    }

    tempvar ES THH TCC THH1 THH0 TCC1 TCC0
    gen byte `ES' = e(sample)
    egen byte `THH' = tag(hid) if `ES'
    quietly count if `THH'==1
    local HH = r(N)
    egen byte `TCC' = tag(__cid_id) if `ES'
    quietly count if `TCC'==1
    local CC = r(N)
    egen byte `THH1' = tag(hid) if `ES' & treated==1 & `modvar'==1
    quietly count if `THH1'==1
    local THH_hi = r(N)
    egen byte `THH0' = tag(hid) if `ES' & treated==1 & `modvar'==0
    quietly count if `THH0'==1
    local THH_lo = r(N)
    egen byte `TCC1' = tag(__cid_id) if `ES' & treated==1 & `modvar'==1
    quietly count if `TCC1'==1
    local TCC_hi = r(N)
    egen byte `TCC0' = tag(__cid_id) if `ES' & treated==1 & `modvar'==0
    quietly count if `TCC0'==1
    local TCC_lo = r(N)
    local NN = e(N)

    scalar b_low = .
    scalar se_low = .
    scalar p_low = .
    cap scalar b_low = _b[1.treated#1.post]
    cap scalar se_low = _se[1.treated#1.post]
    if se_low<. & se_low>0 scalar p_low = 2*ttail(e(df_r), abs(b_low/se_low))

    scalar b_diff = .
    scalar se_diff = .
    scalar p_diff = .
    cap scalar b_diff = _b[1.treated#1.post#1.`modvar']
    cap scalar se_diff = _se[1.treated#1.post#1.`modvar']
    cap test 1.treated#1.post#1.`modvar' = 0
    if !_rc scalar p_diff = r(p)

    scalar b_total = .
    scalar se_total = .
    scalar p_total = .
    cap lincom 1.treated#1.post + 1.treated#1.post#1.`modvar'
    if !_rc {
        scalar b_total = r(estimate)
        scalar se_total = r(se)
        scalar p_total = r(p)
    }

    post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("lower_group_DID") (b_low) (se_low) (p_low) (`NN') (`HH') (`CC') (`THH_hi') (`THH_lo') (`TCC_hi') (`TCC_lo') ("ok")
    post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("high_minus_low_diff") (b_diff) (se_diff) (p_diff) (`NN') (`HH') (`CC') (`THH_hi') (`THH_lo') (`TCC_hi') (`TCC_lo') ("ok")
    post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("high_group_total") (b_total) (se_total) (p_total) (`NN') (`HH') (`CC') (`THH_hi') (`THH_lo') (`TCC_hi') (`TCC_lo') ("ok")
end

cap program drop __r2b_stack_group
program define __r2b_stack_group
    syntax, BASEFILE(string) POSTH(name) SCOPE(string) RESTRICT(string) THRVAR(name) THRNAME(string) OUTCOME(name) GROUPVAR(name) GROUPNAME(string)

    use "`basefile'", clear
    keep if s_mech_hh==1 & `groupvar'==1
    if "`scope'"=="adjacent" keep if timing_adjacent_hh==1
    if "`restrict'"=="exclude_official2014" drop if official2014_prov==1
    if "`restrict'"=="exclude_admin_start_by2014" drop if admin_start_by2014==1

    bys __cid_id: egen first_thr = min(cond(`thrvar'==1, year, .))
    gen byte never_thr = missing(first_thr)
    keep if never_thr==1 | inlist(first_thr, 2016, 2018)

    tempfile W16 W18
    preserve
        keep if inlist(year, 2014, 2016) & (first_thr==2016 | first_thr==2018 | never_thr==1)
        gen byte treated = (first_thr==2016)
        gen byte post = (year==2016)
        gen byte winflag = 0
        save `W16', replace
    restore
    preserve
        keep if inlist(year, 2016, 2018) & (first_thr==2018 | never_thr==1)
        gen byte treated = (first_thr==2018)
        gen byte post = (year==2018)
        gen byte winflag = 1
        save `W18', replace
    restore

    use `W16', clear
    append using `W18'
    egen long hid_stack = group(winflag hid)
    egen long year_stack = group(winflag year)

    quietly count if !missing(`outcome')
    if r(N)<50 {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`groupname'") (.) (.) (.) (.) (.) (.) (.) (.) ("too few nonmissing")
        exit
    }
    quietly summarize treated if !missing(`outcome'), meanonly
    if r(min)==r(max) {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`groupname'") (.) (.) (.) (.) (.) (.) (.) (.) ("no treated variation")
        exit
    }

    cap noisily reghdfe `outcome' i.treated##i.post if !missing(`outcome'), absorb(hid_stack year_stack) vce(cluster __cid_id)
    if _rc {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`groupname'") (.) (.) (.) (.) (.) (.) (.) (.) ("regression failed")
        exit
    }

    tempvar ES THH TCC THHT TCCT
    gen byte `ES' = e(sample)
    egen byte `THH' = tag(hid) if `ES'
    quietly count if `THH'==1
    local HH = r(N)
    egen byte `TCC' = tag(__cid_id) if `ES'
    quietly count if `TCC'==1
    local CC = r(N)
    egen byte `THHT' = tag(hid) if `ES' & treated==1
    quietly count if `THHT'==1
    local THH = r(N)
    egen byte `TCCT' = tag(__cid_id) if `ES' & treated==1
    quietly count if `TCCT'==1
    local TCC = r(N)
    local NN = e(N)

    scalar b = .
    scalar se = .
    scalar p = .
    cap scalar b = _b[1.treated#1.post]
    cap scalar se = _se[1.treated#1.post]
    if se<. & se>0 scalar p = 2*ttail(e(df_r), abs(b/se))
    post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`groupname'") (b) (se) (p) (`NN') (`HH') (`CC') (`THH') (`TCC') ("ok")
end

cap program drop __r2b_stack_cont
program define __r2b_stack_cont
    syntax, BASEFILE(string) POSTH(name) SCOPE(string) RESTRICT(string) THRVAR(name) THRNAME(string) OUTCOME(name) MODVAR(name) MODNAME(string)

    use "`basefile'", clear
    keep if s_mech_hh==1
    if "`scope'"=="adjacent" keep if timing_adjacent_hh==1
    if "`restrict'"=="exclude_official2014" drop if official2014_prov==1
    if "`restrict'"=="exclude_admin_start_by2014" drop if admin_start_by2014==1

    bys __cid_id: egen first_thr = min(cond(`thrvar'==1, year, .))
    gen byte never_thr = missing(first_thr)
    keep if never_thr==1 | inlist(first_thr, 2016, 2018)

    tempfile W16 W18
    preserve
        keep if inlist(year, 2014, 2016) & (first_thr==2016 | first_thr==2018 | never_thr==1)
        gen byte treated = (first_thr==2016)
        gen byte post = (year==2016)
        gen byte winflag = 0
        save `W16', replace
    restore
    preserve
        keep if inlist(year, 2016, 2018) & (first_thr==2018 | never_thr==1)
        gen byte treated = (first_thr==2018)
        gen byte post = (year==2018)
        gen byte winflag = 1
        save `W18', replace
    restore

    use `W16', clear
    append using `W18'
    egen long hid_stack = group(winflag hid)
    egen long year_stack = group(winflag year)

    quietly count if !missing(`outcome', `modvar')
    if r(N)<50 {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") (.) (.) (.) (.) (.) (.) ("too few nonmissing")
        exit
    }

    cap noisily reghdfe `outcome' i.treated##i.post##c.`modvar' if !missing(`outcome', `modvar'), absorb(hid_stack year_stack) vce(cluster __cid_id)
    if _rc {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") (.) (.) (.) (.) (.) (.) ("regression failed")
        exit
    }

    tempvar ES THH TCC
    gen byte `ES' = e(sample)
    egen byte `THH' = tag(hid) if `ES'
    quietly count if `THH'==1
    local HH = r(N)
    egen byte `TCC' = tag(__cid_id) if `ES'
    quietly count if `TCC'==1
    local CC = r(N)
    local NN = e(N)
    scalar b_grad = .
    scalar se_grad = .
    scalar p_grad = .
    cap scalar b_grad = _b[1.treated#1.post#c.`modvar']
    cap scalar se_grad = _se[1.treated#1.post#c.`modvar']
    cap test 1.treated#1.post#c.`modvar' = 0
    if !_rc scalar p_grad = r(p)
    post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") (b_grad) (se_grad) (p_grad) (`NN') (`HH') (`CC') ("ok")
end

* ------------------------------------------------------------------
* C. Run expanded model contest
* ------------------------------------------------------------------

tempfile BINOUT
postfile PBI str32 restriction str12 sample_scope str24 threshold str20 outcome str60 moderator str28 term ///
    double b se p long N households counties treated_high_hh treated_low_hh treated_high_counties treated_low_counties str60 status ///
    using `BINOUT', replace

foreach RESTR in original exclude_official2014 exclude_admin_start_by2014 {
    foreach SCOPE in mech adjacent {
        foreach THR in completed_t high_sat80_t signoff_or_issue_t {
            local TNAME "`THR'"
            if "`THR'"=="completed_t" local TNAME "Completion"
            if "`THR'"=="high_sat80_t" local TNAME "High-saturation"
            if "`THR'"=="signoff_or_issue_t" local TNAME "Signoff-or-issue"
            foreach Y in any_rentin asinh_rentin {
                foreach M of local BINMODS {
                    __r2b_stack_bin, basefile("`BASE'") posth(PBI) scope("`SCOPE'") restrict("`RESTR'") ///
                        thrvar(`THR') thrname("`TNAME'") outcome(`Y') modvar(`M') modname("``M'_lab'")
                }
            }
        }
    }
}
postclose PBI
use `BINOUT', clear
export delimited using "`OUT'/tables/Round2B_B_binary_interaction_expanded.csv", replace

tempfile GRPOUT
postfile PGR str32 restriction str12 sample_scope str24 threshold str20 outcome str60 group ///
    double b se p long N households counties treated_hh treated_counties str60 status using `GRPOUT', replace

local GROUPS "mod_readjust mod_readj_pop mod_readj_exprop mod_method_reserved mod_method_small mod_method_full mod_policy_noadj mod_nodemand_noadj mod_internal_pressure mod_intrusive_realloc mod_highintrusion_core mod_no_adjust_any mod_market_active mod_landpoor mod_landbelowmed mod_rj_landpoor mod_rjpop_landpoor mod_intrn_landpoor mod_polnoadj_landpoor mod_mkt_landpoor"
foreach RESTR in original exclude_official2014 exclude_admin_start_by2014 {
    foreach SCOPE in mech adjacent {
        foreach THR in completed_t high_sat80_t signoff_or_issue_t {
            local TNAME "`THR'"
            if "`THR'"=="completed_t" local TNAME "Completion"
            if "`THR'"=="high_sat80_t" local TNAME "High-saturation"
            if "`THR'"=="signoff_or_issue_t" local TNAME "Signoff-or-issue"
            foreach Y in any_rentin asinh_rentin {
                foreach G of local GROUPS {
                    __r2b_stack_group, basefile("`BASE'") posth(PGR) scope("`SCOPE'") restrict("`RESTR'") ///
                        thrvar(`THR') thrname("`TNAME'") outcome(`Y') groupvar(`G') groupname("``G'_lab'")
                }
            }
        }
    }
}
postclose PGR
use `GRPOUT', clear
export delimited using "`OUT'/tables/Round2B_C_group_specific_did.csv", replace

tempfile CONTOUT
postfile PCO str32 restriction str12 sample_scope str24 threshold str20 outcome str60 moderator ///
    double b se p long N households counties str60 status using `CONTOUT', replace

local CONTMODS "z_risk_demographic z_risk_intrusion z_tenure_credibility z_market_env_sum z_base_land_mu a3_tenure_insec_z base14_broad_z"
local z_risk_demographic_lab "z_demographic_pressure"
local z_risk_intrusion_lab "z_reallocation_intrusion"
local z_tenure_credibility_lab "z_tenure_credibility"
local z_market_env_sum_lab "z_market_environment"
local z_base_land_mu_lab "z_baseline_land"
local a3_tenure_insec_z_lab "z_current_A3"
local base14_broad_z_lab "z_broad_rightsgap"

foreach RESTR in original exclude_official2014 exclude_admin_start_by2014 {
    foreach SCOPE in mech adjacent {
        foreach THR in completed_t high_sat80_t signoff_or_issue_t {
            local TNAME "`THR'"
            if "`THR'"=="completed_t" local TNAME "Completion"
            if "`THR'"=="high_sat80_t" local TNAME "High-saturation"
            if "`THR'"=="signoff_or_issue_t" local TNAME "Signoff-or-issue"
            foreach Y in any_rentin asinh_rentin {
                foreach M of local CONTMODS {
                    __r2b_stack_cont, basefile("`BASE'") posth(PCO) scope("`SCOPE'") restrict("`RESTR'") ///
                        thrvar(`THR') thrname("`TNAME'") outcome(`Y') modvar(`M') modname("``M'_lab'")
                }
            }
        }
    }
}
postclose PCO
use `CONTOUT', clear
export delimited using "`OUT'/tables/Round2B_D_continuous_scores_expanded.csv", replace

log close
