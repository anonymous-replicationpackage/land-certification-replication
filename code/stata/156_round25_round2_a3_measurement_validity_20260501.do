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

local OUT "$ROOT/result/round25_empirical_rebuild_20260501/round2_a3_measurement_validity"
cap mkdir "$ROOT/result"
cap mkdir "$ROOT/result/round25_empirical_rebuild_20260501"
cap mkdir "`OUT'"
cap mkdir "`OUT'/tables"
cap mkdir "`OUT'/logs"
cap mkdir "`OUT'/audit"

cap log close _all
log using "`OUT'/logs/156_round25_round2_a3_measurement_validity_20260501.log", replace text

local PANEL   "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_indivbridge_20260416.dta"
local RGPANEL "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_rightsgap_20260415.dta"
local ADMINCY "$ROOT/data/topjournal_rebuild/admin/admin_rollout_countyyear_v2.dta"

tempfile ADMINUSE BASE RGM

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
gen byte started_by_2014_flag = (started_t==1 & year==2014)
bys __cid_id: egen byte county_started_by2014 = max(started_by_2014_flag)
replace county_started_by2014 = 0 if missing(county_started_by2014)
drop started_by_2014_flag

* Binary candidate moderators: 1 always means "higher rights instability / rights gap".
gen byte mod_a3_current = (a3_high_insec==1) if inlist(a3_high_insec, 0, 1)
gen byte mod_a3_any = (a3_any_issue==1) if inlist(a3_any_issue, 0, 1)
gen byte mod_readjust = (base14_rg_readjust==1) if !missing(base14_rg_readjust)
gen byte mod_instab_ge2 = (base14_instab_sum>=2) if !missing(base14_instab_sum)
gen byte mod_instab_ge3 = (base14_instab_sum>=3) if !missing(base14_instab_sum)

gen byte mod_disp_newpop = .
replace mod_disp_newpop = 0 if base14_rg_readjust==0
replace mod_disp_newpop = 0 if base14_rg_readjust==1 & base14_rg_disp_newpop==0
replace mod_disp_newpop = 1 if base14_rg_disp_newpop==1

gen byte mod_disp_women = .
replace mod_disp_women = 0 if base14_rg_readjust==0
replace mod_disp_women = 0 if base14_rg_readjust==1 & base14_rg_disp_women==0
replace mod_disp_women = 1 if base14_rg_disp_women==1

gen byte mod_disp_any = .
replace mod_disp_any = 0 if base14_rg_readjust==0
replace mod_disp_any = 0 if base14_rg_readjust==1 & base14_rg_disp_newpop==0 & base14_rg_disp_women==0
replace mod_disp_any = 1 if base14_rg_disp_newpop==1 | base14_rg_disp_women==1

quietly summarize a3_tenure_insec_z if year==2014 & s_mech_hh==1, detail
local a3p75 = r(p75)
gen byte mod_a3_top75 = (a3_tenure_insec_z>`a3p75') if !missing(a3_tenure_insec_z)

quietly summarize base14_broad_z if year==2014 & s_mech_hh==1, detail
local broadp50 = r(p50)
local broadp75 = r(p75)
gen byte mod_broad_high = (base14_broad_z>`broadp50') if !missing(base14_broad_z)
gen byte mod_broad_top75 = (base14_broad_z>`broadp75') if !missing(base14_broad_z)

gen byte mod_absorg_any = (base14_absorg_sum>0) if !missing(base14_absorg_sum)
quietly summarize base14_external_sum if year==2014 & s_mech_hh==1, detail
local extp50 = r(p50)
gen byte mod_external_high = (base14_external_sum>`extp50') if !missing(base14_external_sum)
gen byte mod_pre12_unquiet = (pre12_rg_pretransfer_sum>0) if !missing(pre12_rg_pretransfer_sum)

foreach v in a3_sum base14_instab_sum base14_absorg_sum base14_external_sum pre12_rg_pretransfer_sum {
    cap drop z_`v'
    cap drop __tagz
    egen byte __tagz = tag(__cid_id) if !missing(`v')
    quietly summarize `v' if __tagz==1
    if r(sd)>0 & r(sd)<. gen double z_`v' = (`v' - r(mean))/r(sd) if !missing(`v')
    else gen double z_`v' = . 
    drop __tagz
}

compress
save `BASE', replace

* ------------------------------------------------------------------
* A. Measurement audit: support, equivalence, and correlations
* ------------------------------------------------------------------

tempfile SUPP
postfile PS str32 moderator str80 label long rows households counties villages ///
    double share mean_a3_z mean_asinh_rentin using `SUPP', replace

local MODS "mod_a3_current mod_a3_any mod_readjust mod_instab_ge2 mod_instab_ge3 mod_disp_newpop mod_disp_women mod_disp_any mod_a3_top75 mod_broad_high mod_broad_top75 mod_absorg_any mod_external_high mod_pre12_unquiet"
local mod_a3_current_lab "Current A3 median split"
local mod_a3_any_lab "A3 any issue"
local mod_readjust_lab "Readjustment since 2003"
local mod_instab_ge2_lab "A3 sum >=2"
local mod_instab_ge3_lab "A3 sum >=3"
local mod_disp_newpop_lab "New-population land dispute"
local mod_disp_women_lab "Married-out women dispute"
local mod_disp_any_lab "Any specific dispute"
local mod_a3_top75_lab "A3 top quartile"
local mod_broad_high_lab "Broad rights-gap high"
local mod_broad_top75_lab "Broad rights-gap top quartile"
local mod_absorg_any_lab "Absent-household organization issue"
local mod_external_high_lab "External-intervention high"
local mod_pre12_unquiet_lab "2012 transfer environment unquiet"

foreach M of local MODS {
    use `BASE', clear
    keep if year==2014 & s_mech_hh==1 & !missing(`M')
    quietly count
    local rows = r(N)
    cap drop __tagh __tagc __tagv
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
    quietly summarize a3_tenure_insec_z, meanonly
    local ma3 = r(mean)
    quietly summarize asinh_rentin, meanonly
    local my = r(mean)
    post PS ("`M'") ("``M'_lab'") (`rows') (`hh') (`cc') (`vv') (`share') (`ma3') (`my')
}
postclose PS
use `SUPP', clear
export delimited using "`OUT'/audit/Round2_A1_moderator_baseline_support.csv", replace

preserve
    use `BASE', clear
    keep if year==2014 & s_mech_hh==1
    keep mod_a3_current mod_a3_any mod_readjust mod_instab_ge2 mod_instab_ge3 mod_disp_newpop mod_disp_women mod_disp_any mod_a3_top75 mod_broad_high mod_broad_top75 mod_absorg_any mod_external_high mod_pre12_unquiet ///
         a3_tenure_insec_z a3_sum base14_instab_sum base14_absorg_sum base14_external_sum base14_broad_z pre12_rg_pretransfer_sum
    corr mod_a3_current mod_a3_any mod_readjust mod_instab_ge2 mod_disp_any mod_broad_high mod_absorg_any mod_external_high mod_pre12_unquiet ///
        a3_tenure_insec_z base14_broad_z pre12_rg_pretransfer_sum
    matrix C = r(C)
    clear
    svmat double C, names(col)
    gen str40 rowvar = ""
    local rn : rownames C
    local i = 1
    foreach r of local rn {
        replace rowvar = "`r'" in `i'
        local ++i
    }
    order rowvar
    export delimited using "`OUT'/audit/Round2_A2_moderator_correlation_matrix.csv", replace
restore

preserve
    use `BASE', clear
    keep if year==2014 & s_mech_hh==1
    tempfile CT
    postfile PC str32 rowvar str32 colvar str24 cell long n using `CT', replace
    foreach C in mod_a3_any mod_readjust mod_instab_ge2 mod_disp_any mod_broad_high mod_pre12_unquiet {
        foreach rv in 0 1 {
            foreach cv in 0 1 {
                quietly count if mod_a3_current==`rv' & `C'==`cv'
                post PC ("mod_a3_current") ("`C'") ("`rv'_`cv'") (r(N))
            }
        }
    }
    postclose PC
    use `CT', clear
    export delimited using "`OUT'/audit/Round2_A3_current_a3_crosstabs.csv", replace
restore

* ------------------------------------------------------------------
* B. Stacked DID programs
* ------------------------------------------------------------------

cap program drop __r2_stack_bin
program define __r2_stack_bin
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
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("error") ///
            (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) ("too few nonmissing")
        exit
    }
    quietly summarize `modvar' if !missing(`outcome', `modvar'), meanonly
    if r(min)==r(max) {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("error") ///
            (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) ("no moderator variation")
        exit
    }

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

cap program drop __r2_stack_cont
program define __r2_stack_cont
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
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ///
            (.) (.) (.) (.) (.) (.) ("too few nonmissing")
        exit
    }

    cap noisily reghdfe `outcome' i.treated##i.post##c.`modvar' if !missing(`outcome', `modvar'), ///
        absorb(hid_stack year_stack) vce(cluster __cid_id)
    if _rc {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ///
            (.) (.) (.) (.) (.) (.) ("regression failed")
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

* ------------------------------------------------------------------
* C. Run model contest
* ------------------------------------------------------------------

tempfile BINOUT
postfile PBI str32 restriction str12 sample_scope str24 threshold str20 outcome str32 moderator str28 term ///
    double b se p long N households counties treated_high_hh treated_low_hh treated_high_counties treated_low_counties str60 status ///
    using `BINOUT', replace

local BINMODS "mod_a3_current mod_a3_any mod_readjust mod_instab_ge2 mod_instab_ge3 mod_disp_newpop mod_disp_women mod_disp_any mod_a3_top75 mod_broad_high mod_broad_top75 mod_absorg_any mod_external_high mod_pre12_unquiet"
foreach RESTR in original exclude_official2014 exclude_admin_start_by2014 {
    foreach SCOPE in mech adjacent {
        foreach THR in completed_t high_sat80_t signoff_or_issue_t {
            local TNAME "`THR'"
            if "`THR'"=="completed_t" local TNAME "Completion"
            if "`THR'"=="high_sat80_t" local TNAME "High-saturation"
            if "`THR'"=="signoff_or_issue_t" local TNAME "Signoff-or-issue"
            foreach Y in any_rentin asinh_rentin {
                foreach M of local BINMODS {
                    __r2_stack_bin, basefile("`BASE'") posth(PBI) scope("`SCOPE'") restrict("`RESTR'") ///
                        thrvar(`THR') thrname("`TNAME'") outcome(`Y') modvar(`M') modname("`M'")
                }
            }
        }
    }
}
postclose PBI
use `BINOUT', clear
export delimited using "`OUT'/tables/Round2_B_binary_moderator_contest.csv", replace

tempfile CONTOUT
postfile PCO str32 restriction str12 sample_scope str24 threshold str20 outcome str32 moderator ///
    double b se p long N households counties str60 status using `CONTOUT', replace

local CONTMODS "a3_tenure_insec_z z_a3_sum z_base14_instab_sum z_base14_absorg_sum z_base14_external_sum base14_broad_z z_pre12_rg_pretransfer_sum"
foreach RESTR in original exclude_official2014 exclude_admin_start_by2014 {
    foreach SCOPE in mech adjacent {
        foreach THR in completed_t high_sat80_t signoff_or_issue_t {
            local TNAME "`THR'"
            if "`THR'"=="completed_t" local TNAME "Completion"
            if "`THR'"=="high_sat80_t" local TNAME "High-saturation"
            if "`THR'"=="signoff_or_issue_t" local TNAME "Signoff-or-issue"
            foreach Y in any_rentin asinh_rentin {
                foreach M of local CONTMODS {
                    __r2_stack_cont, basefile("`BASE'") posth(PCO) scope("`SCOPE'") restrict("`RESTR'") ///
                        thrvar(`THR') thrname("`TNAME'") outcome(`Y') modvar(`M') modname("`M'")
                }
            }
        }
    }
}
postclose PCO
use `CONTOUT', clear
export delimited using "`OUT'/tables/Round2_C_continuous_moderator_contest.csv", replace

* ------------------------------------------------------------------
* D. Exploratory household-FE certificate interaction contest.
* This is not the preferred causal design; it only checks whether
* very narrow moderators fail because of stacked-DID support.
* ------------------------------------------------------------------

tempfile FEOUT
postfile PFE str12 sample_scope str20 outcome str32 moderator str28 term ///
    double b se p long N households counties cert_high_hh cert_low_hh cert_high_counties cert_low_counties str60 status ///
    using `FEOUT', replace

foreach SCOPE in mech adjacent {
    foreach Y in any_rentin asinh_rentin {
        foreach M of local BINMODS {
            use `BASE', clear
            keep if s_mech_hh==1 & inlist(year, 2014, 2016, 2018)
            if "`SCOPE'"=="adjacent" keep if timing_adjacent_hh==1
            quietly count if !missing(`Y', Cert_h, `M')
            if r(N)<50 {
                post PFE ("`SCOPE'") ("`Y'") ("`M'") ("error") (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) ("too few nonmissing")
                continue
            }
            quietly summarize `M' if !missing(`Y', Cert_h, `M'), meanonly
            if r(min)==r(max) {
                post PFE ("`SCOPE'") ("`Y'") ("`M'") ("error") (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) ("no moderator variation")
                continue
            }
            cap noisily reghdfe `Y' i.Cert_h##i.`M' if !missing(`Y', Cert_h, `M'), absorb(hid cidyear) vce(cluster __cid_id)
            if _rc {
                post PFE ("`SCOPE'") ("`Y'") ("`M'") ("error") (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) ("regression failed")
                continue
            }

            tempvar ES THH TCC THH1 THH0 TCC1 TCC0
            gen byte `ES' = e(sample)
            egen byte `THH' = tag(hid) if `ES'
            quietly count if `THH'==1
            local HH = r(N)
            egen byte `TCC' = tag(__cid_id) if `ES'
            quietly count if `TCC'==1
            local CC = r(N)
            egen byte `THH1' = tag(hid) if `ES' & Cert_h==1 & `M'==1
            quietly count if `THH1'==1
            local CHH_hi = r(N)
            egen byte `THH0' = tag(hid) if `ES' & Cert_h==1 & `M'==0
            quietly count if `THH0'==1
            local CHH_lo = r(N)
            egen byte `TCC1' = tag(__cid_id) if `ES' & Cert_h==1 & `M'==1
            quietly count if `TCC1'==1
            local CCC_hi = r(N)
            egen byte `TCC0' = tag(__cid_id) if `ES' & Cert_h==1 & `M'==0
            quietly count if `TCC0'==1
            local CCC_lo = r(N)
            local NN = e(N)

            scalar b_base = .
            scalar se_base = .
            scalar p_base = .
            cap scalar b_base = _b[1.Cert_h]
            cap scalar se_base = _se[1.Cert_h]
            if se_base<. & se_base>0 scalar p_base = 2*ttail(e(df_r), abs(b_base/se_base))

            scalar b_diff = .
            scalar se_diff = .
            scalar p_diff = .
            cap scalar b_diff = _b[1.Cert_h#1.`M']
            cap scalar se_diff = _se[1.Cert_h#1.`M']
            cap test 1.Cert_h#1.`M' = 0
            if !_rc scalar p_diff = r(p)

            scalar b_total = .
            scalar se_total = .
            scalar p_total = .
            cap lincom 1.Cert_h + 1.Cert_h#1.`M'
            if !_rc {
                scalar b_total = r(estimate)
                scalar se_total = r(se)
                scalar p_total = r(p)
            }

            post PFE ("`SCOPE'") ("`Y'") ("`M'") ("lower_group_FE") ///
                (b_base) (se_base) (p_base) (`NN') (`HH') (`CC') (`CHH_hi') (`CHH_lo') (`CCC_hi') (`CCC_lo') ("ok")
            post PFE ("`SCOPE'") ("`Y'") ("`M'") ("high_minus_low_diff") ///
                (b_diff) (se_diff) (p_diff) (`NN') (`HH') (`CC') (`CHH_hi') (`CHH_lo') (`CCC_hi') (`CCC_lo') ("ok")
            post PFE ("`SCOPE'") ("`Y'") ("`M'") ("high_group_total") ///
                (b_total) (se_total) (p_total) (`NN') (`HH') (`CC') (`CHH_hi') (`CHH_lo') (`CCC_hi') (`CCC_lo') ("ok")
        }
    }
}
postclose PFE
use `FEOUT', clear
export delimited using "`OUT'/tables/Round2_D_panel_fe_interaction_contest.csv", replace

log close
