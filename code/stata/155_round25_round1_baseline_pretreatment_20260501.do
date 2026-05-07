version 17
clear all
set more off
set linesize 255
set varabbrev off

local ROOT = subinstr("`c(pwd)'", char(92), "/", .)
if !fileexists("`ROOT'/dofiles/01_globals_and_ado.do") {
    local ROOT = subinstr("`c(pwd)'", char(92), "/", .)
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

local OUT "$ROOT/result/round25_empirical_rebuild_20260501/round1_baseline_pretreatment"
cap mkdir "$ROOT/result"
cap mkdir "$ROOT/result/round25_empirical_rebuild_20260501"
cap mkdir "`OUT'"
cap mkdir "`OUT'/tables"
cap mkdir "`OUT'/logs"
cap mkdir "`OUT'/audit"

cap log close _all
log using "`OUT'/logs/155_round25_round1_baseline_pretreatment_20260501.log", replace text

local PANEL   "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_indivbridge_20260416.dta"
local RGPANEL "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_rightsgap_20260415.dta"
local ADMINCY "$ROOT/data/topjournal_rebuild/admin/admin_rollout_countyyear_v2.dta"

tempfile ADMINUSE BASE

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

use "`PANEL'", clear
keep if inlist(year, 2014, 2016, 2018)

foreach v in base14_rg_pre_gov_any base14_rg_pre_gov_area base14_rg_pre_gov_fee ///
    base14_rg_pre_dg_any base14_rg_pre_dg_hh base14_rg_pre_dg_share ///
    base14_rg_instab_sum base14_rg_absorg_sum base14_rg_external_sum ///
    base14_rg_pretransfer_sum base14_rg_readjust base14_rg_disp_newpop ///
    base14_rg_disp_women pre12_rg_pre_gov_any pre12_rg_pre_gov_area ///
    pre12_rg_pre_gov_fee pre12_rg_pre_dg_any pre12_rg_pre_dg_hh ///
    pre12_rg_pre_dg_share pre12_rg_pretransfer_sum base14_instab_sum ///
    base14_absorg_sum base14_external_sum base14_broad_nnon ///
    base14_broad_mean base14_broad_z base14_high_broad {
    cap drop `v'
}

preserve
    use "`RGPANEL'", clear
    keep hid year __cid_id base14_rg_pre_gov_any base14_rg_pre_gov_area base14_rg_pre_gov_fee ///
        base14_rg_pre_dg_any base14_rg_pre_dg_hh base14_rg_pre_dg_share ///
        base14_rg_instab_sum base14_rg_absorg_sum base14_rg_external_sum ///
        base14_rg_pretransfer_sum base14_rg_readjust base14_rg_disp_newpop ///
        base14_rg_disp_women pre12_rg_pre_gov_any pre12_rg_pre_gov_area ///
        pre12_rg_pre_gov_fee pre12_rg_pre_dg_any pre12_rg_pre_dg_hh ///
        pre12_rg_pre_dg_share pre12_rg_pretransfer_sum base14_instab_sum ///
        base14_absorg_sum base14_external_sum base14_broad_nnon ///
        base14_broad_mean base14_broad_z base14_high_broad
    duplicates drop hid year __cid_id, force
    tempfile RGM
    save `RGM', replace
restore
merge 1:1 hid year __cid_id using `RGM', keep(master match) nogen

cap drop county_started_t county_signedoff_t county_issued_t county_completed_t county_sat_t county_completion_rate
cap drop signoff_or_issue_t completed_t high_sat80_t started_t
merge m:1 __cid_id year using `ADMINUSE', nogen keep(master match)

gen byte mod_a3_current = (a3_high_insec==1) if inlist(a3_high_insec, 0, 1)
gen byte official2014_prov = inlist(__prov_id, 34, 37, 51)
gen byte admin_start_before2014 = (admin_rollout_start_year<=2013) if !missing(admin_rollout_start_year)
replace admin_start_before2014 = 0 if missing(admin_start_before2014)
gen byte admin_start_by2014 = (admin_rollout_start_year<=2014) if !missing(admin_rollout_start_year)
replace admin_start_by2014 = 0 if missing(admin_start_by2014)
gen byte clean_late_admin = (admin_rollout_start_year>=2015) if !missing(admin_rollout_start_year)
replace clean_late_admin = 0 if missing(clean_late_admin)
gen byte started_by_2014_flag = (started_t==1 & year==2014)
bys __cid_id: egen byte county_started_by2014 = max(started_by_2014_flag)
replace county_started_by2014 = 0 if missing(county_started_by2014)
drop started_by_2014_flag

preserve
    keep if year==2014 & s_mech_hh==1 & !missing(a3_tenure_insec_z, village_id)
    egen byte __tagv = tag(village_id)
    keep if __tagv
    quietly summarize a3_tenure_insec_z, detail
    local p50_all = r(p50)
restore

preserve
    keep if year==2014 & s_mech_hh==1 & official2014_prov==0 & !missing(a3_tenure_insec_z, village_id)
    egen byte __tagv = tag(village_id)
    keep if __tagv
    quietly summarize a3_tenure_insec_z, detail
    local p50_nonoff = r(p50)
restore

preserve
    keep if year==2014 & s_mech_hh==1 & admin_start_by2014==0 & !missing(a3_tenure_insec_z, village_id)
    egen byte __tagv = tag(village_id)
    keep if __tagv
    quietly summarize a3_tenure_insec_z, detail
    local p50_lateadmin = r(p50)
restore

gen byte mod_a3_nonoff_median = (a3_tenure_insec_z > `p50_nonoff') if !missing(a3_tenure_insec_z)
gen byte mod_a3_lateadmin_median = (a3_tenure_insec_z > `p50_lateadmin') if !missing(a3_tenure_insec_z)
gen byte mod_readjust = (base14_rg_readjust==1) if !missing(base14_rg_readjust)
gen byte mod_broad_high = (base14_high_broad==1) if inlist(base14_high_broad, 0, 1)
gen byte mod_pre12_unquiet = (pre12_rg_pretransfer_sum>0) if !missing(pre12_rg_pretransfer_sum)

foreach v in base14_instab_sum base14_absorg_sum base14_external_sum pre12_rg_pretransfer_sum {
    cap drop z_`v'
    cap drop __tagz
    egen byte __tagz = tag(__cid_id) if !missing(`v')
    quietly summarize `v' if __tagz==1
    if r(sd)>0 & r(sd)<. {
        gen double z_`v' = (`v' - r(mean))/r(sd) if !missing(`v')
    }
    else gen double z_`v' = . 
    drop __tagz
}

compress
save `BASE', replace

* ------------------------------------------------------------------
* A. Exposure and moderator audit
* ------------------------------------------------------------------

preserve
    use `BASE', clear
    keep if year==2014 & s_mech_hh==1
    egen byte tag_hh = tag(hid)
    egen byte tag_cid = tag(__cid_id)
    egen byte tag_vil = tag(village_id)
    collapse (count) rows=hid ///
        (sum) households=tag_hh counties=tag_cid villages=tag_vil ///
        (mean) share_a3_high=mod_a3_current share_readjust=mod_readjust ///
               share_broad_high=mod_broad_high share_pre12_unquiet=mod_pre12_unquiet ///
        (min) min_admin_start=admin_rollout_start_year ///
        (max) max_admin_start=admin_rollout_start_year ///
        , by(__prov_id admin_prov_name official2014_prov admin_start_by2014)
    export delimited using "`OUT'/audit/Round1_A1_2014_baseline_exposure_by_province.csv", replace
restore

use `BASE', clear
keep if year==2014 & s_mech_hh==1
egen byte tag_hh = tag(hid)
egen byte tag_cid = tag(__cid_id)
egen byte tag_vil = tag(village_id)
tempfile BASE2014 EXPAUD
save `BASE2014', replace
postfile PEA str36 exposure_group long rows households counties villages ///
    double mean_a3_z share_a3_high share_nonoff_high share_lateadmin_high ///
    double share_readjust share_broad_high share_pre12_unquiet ///
    using `EXPAUD', replace
foreach G in all official2014 nonofficial admin_start_by2014 admin_start_2015plus started_by2014 {
    use `BASE2014', clear
    if "`G'"=="official2014" keep if official2014_prov==1
    if "`G'"=="nonofficial" keep if official2014_prov==0
    if "`G'"=="admin_start_by2014" keep if admin_start_by2014==1
    if "`G'"=="admin_start_2015plus" keep if admin_start_by2014==0
    if "`G'"=="started_by2014" keep if county_started_by2014==1
    quietly count
    local rows = r(N)
    quietly count if tag_hh==1
    local hh = r(N)
    quietly count if tag_cid==1
    local cc = r(N)
    quietly count if tag_vil==1
    local vv = r(N)
    quietly summarize a3_tenure_insec_z, meanonly
    local mz = r(mean)
    quietly summarize mod_a3_current, meanonly
    local sh1 = r(mean)
    quietly summarize mod_a3_nonoff_median, meanonly
    local sh2 = r(mean)
    quietly summarize mod_a3_lateadmin_median, meanonly
    local sh3 = r(mean)
    quietly summarize mod_readjust, meanonly
    local shr = r(mean)
    quietly summarize mod_broad_high, meanonly
    local shb = r(mean)
    quietly summarize mod_pre12_unquiet, meanonly
    local shp = r(mean)
    post PEA ("`G'") (`rows') (`hh') (`cc') (`vv') (`mz') (`sh1') (`sh2') (`sh3') (`shr') (`shb') (`shp')
}
postclose PEA
use `EXPAUD', clear
export delimited using "`OUT'/audit/Round1_A2_moderator_distribution_by_exposure.csv", replace

preserve
    clear
    set obs 3
    gen str32 cutpoint = ""
    gen double value = .
    replace cutpoint = "overall_2014_village_p50" in 1
    replace value = `p50_all' in 1
    replace cutpoint = "nonofficial2014_village_p50" in 2
    replace value = `p50_nonoff' in 2
    replace cutpoint = "admin_start_2015plus_village_p50" in 3
    replace value = `p50_lateadmin' in 3
    export delimited using "`OUT'/audit/Round1_A3_a3_median_cutpoints.csv", replace
restore

* ------------------------------------------------------------------
* B. Binary moderator stacked DID
* ------------------------------------------------------------------

cap program drop __round1_stack_bin
program define __round1_stack_bin
    syntax, BASEFILE(string) POSTH(name) SCOPE(string) RESTRICT(string) THRVAR(name) THRNAME(string) OUTCOME(name) MODVAR(name) MODNAME(string)

    use "`basefile'", clear
    keep if s_mech_hh==1
    if "`scope'"=="adjacent" keep if timing_adjacent_hh==1
    if "`restrict'"=="exclude_official2014" drop if official2014_prov==1
    if "`restrict'"=="exclude_admin_start_by2014" drop if admin_start_by2014==1
    if "`restrict'"=="exclude_admin_start_before2014" drop if admin_start_before2014==1
    if "`restrict'"=="exclude_started_by2014" drop if county_started_by2014==1

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

    cap noisily reghdfe `outcome' i.treated##i.post##i.`modvar' if !missing(`outcome', `modvar'), ///
        absorb(hid_stack year_stack) vce(cluster __cid_id)
    if _rc {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("error") ///
            (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) ("regression failed")
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

    post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("lower_group_DID") ///
        (b_low) (se_low) (p_low) (`NN') (`HH') (`CC') (`THH_hi') (`THH_lo') (`TCC_hi') (`TCC_lo') ("ok")
    post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("high_minus_low_diff") ///
        (b_diff) (se_diff) (p_diff) (`NN') (`HH') (`CC') (`THH_hi') (`THH_lo') (`TCC_hi') (`TCC_lo') ("ok")
    post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("high_group_total") ///
        (b_total) (se_total) (p_total) (`NN') (`HH') (`CC') (`THH_hi') (`THH_lo') (`TCC_hi') (`TCC_lo') ("ok")
end

tempfile BINOUT
postfile PBI str32 restriction str12 sample_scope str24 threshold str20 outcome str32 moderator str28 term ///
    double b se p long N households counties treated_high_hh treated_low_hh treated_high_counties treated_low_counties str60 status ///
    using `BINOUT', replace

local RESTRS "original exclude_official2014 exclude_admin_start_by2014 exclude_admin_start_before2014 exclude_started_by2014"
local SCOPES "mech adjacent"
local THRS "completed_t high_sat80_t signoff_or_issue_t"
local MODS "mod_a3_current mod_a3_nonoff_median mod_a3_lateadmin_median mod_readjust mod_broad_high mod_pre12_unquiet"

foreach RESTR of local RESTRS {
    foreach SCOPE of local SCOPES {
        foreach THR of local THRS {
            local TNAME "`THR'"
            if "`THR'"=="completed_t" local TNAME "Completion"
            if "`THR'"=="high_sat80_t" local TNAME "High-saturation"
            if "`THR'"=="signoff_or_issue_t" local TNAME "Signoff-or-issue"
            foreach Y in any_rentin asinh_rentin {
                foreach M of local MODS {
                    __round1_stack_bin, basefile("`BASE'") posth(PBI) scope("`SCOPE'") restrict("`RESTR'") ///
                        thrvar(`THR') thrname("`TNAME'") outcome(`Y') modvar(`M') modname("`M'")
                }
            }
        }
    }
}
postclose PBI
use `BINOUT', clear
export delimited using "`OUT'/tables/Round1_B_binary_moderator_stacked_did.csv", replace

* ------------------------------------------------------------------
* C. Continuous moderator stacked DID
* ------------------------------------------------------------------

cap program drop __round1_stack_cont
program define __round1_stack_cont
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

    cap noisily reghdfe `outcome' i.treated##i.post##c.`modvar' if !missing(`outcome', `modvar'), ///
        absorb(hid_stack year_stack) vce(cluster __cid_id)
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
    post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ///
        (b_grad) (se_grad) (p_grad) (`NN') (`HH') (`CC') ("ok")
end

tempfile CONTOUT
postfile PCO str32 restriction str12 sample_scope str24 threshold str20 outcome str32 moderator ///
    double b se p long N households counties str60 status using `CONTOUT', replace

local CMODS "a3_tenure_insec_z base14_broad_z z_base14_instab_sum z_base14_absorg_sum z_base14_external_sum z_pre12_rg_pretransfer_sum"
foreach RESTR in original exclude_official2014 exclude_admin_start_by2014 {
    foreach SCOPE in mech adjacent {
        foreach THR in completed_t high_sat80_t {
            local TNAME "`THR'"
            if "`THR'"=="completed_t" local TNAME "Completion"
            if "`THR'"=="high_sat80_t" local TNAME "High-saturation"
            foreach Y in any_rentin asinh_rentin {
                foreach M of local CMODS {
                    __round1_stack_cont, basefile("`BASE'") posth(PCO) scope("`SCOPE'") restrict("`RESTR'") ///
                        thrvar(`THR') thrname("`TNAME'") outcome(`Y') modvar(`M') modname("`M'")
                }
            }
        }
    }
}
postclose PCO
use `CONTOUT', clear
export delimited using "`OUT'/tables/Round1_C_continuous_moderator_stacked_did.csv", replace

log close
