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
if _rc exit 111

local OUT "$ROOT/result/round25_empirical_rebuild_20260501/round2b_deeper_a3_exploration"
cap mkdir "`OUT'/tables"
cap mkdir "`OUT'/audit"
cap mkdir "`OUT'/logs"

cap log close _all
log using "`OUT'/logs/159_round25_round2b_external_county_moderators_20260502.log", replace text

local PANEL   "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_indivbridge_20260416.dta"
local ADMINCY "$ROOT/data/topjournal_rebuild/admin/admin_rollout_countyyear_v2.dta"
local COUNTYCSV "`OUT'/audit/Round2B_external_countydb_2012_covariates.csv"

tempfile COUNTY ADMINUSE BASE

import delimited using "`COUNTYCSV'", clear varnames(1) encoding(UTF-8)
rename county_id_num __cid_id
keep __cid_id county_rural_density county_arable_per_rural county_gdp_pc ///
    county_primary_share county_tertiary_share county_ag_labor_share ///
    county_mech_per_arable county_sow_per_arable county_rural_income
duplicates drop __cid_id, force
save `COUNTY', replace

use "`ADMINCY'", clear
keep county_id_num year county_started_t county_signedoff_t county_issued_t county_completed_t county_sat_t
rename county_id_num __cid_id
gen byte signoff_or_issue_t = ((county_signedoff_t==1) | (county_issued_t==1)) if !missing(county_signedoff_t) | !missing(county_issued_t)
gen byte completed_t = county_completed_t if !missing(county_completed_t)
gen byte high_sat80_t = (county_sat_t>=0.8) if !missing(county_sat_t)
save `ADMINUSE', replace

use "`PANEL'", clear
keep if inlist(year, 2014, 2016, 2018)
merge m:1 __cid_id using `COUNTY', keep(master match) nogen
merge m:1 __cid_id year using `ADMINUSE', keep(master match) nogen

gen byte official2014_prov = inlist(__prov_id, 34, 37, 51)
gen byte admin_start_by2014 = (admin_rollout_start_year<=2014) if !missing(admin_rollout_start_year)
replace admin_start_by2014 = 0 if missing(admin_start_by2014)

egen byte __ctag = tag(__cid_id)
foreach v in county_rural_density county_arable_per_rural county_gdp_pc county_primary_share ///
    county_tertiary_share county_ag_labor_share county_mech_per_arable county_sow_per_arable county_rural_income {
    quietly summarize `v' if __ctag==1 & s_mech_hh==1, detail
    local p50_`v' = r(p50)
    local p25_`v' = r(p25)
    local p75_`v' = r(p75)
    gen double z_`v' = .
    quietly summarize `v' if __ctag==1 & s_mech_hh==1
    if r(sd)>0 & r(sd)<. replace z_`v' = (`v' - r(mean))/r(sd) if !missing(`v')
}
drop __ctag

gen byte mod_land_pressure_density = (county_rural_density>`p50_county_rural_density') if !missing(county_rural_density)
gen byte mod_land_pressure_arable = (county_arable_per_rural<`p50_county_arable_per_rural') if !missing(county_arable_per_rural)
gen byte mod_land_scarce_p25 = (county_arable_per_rural<`p25_county_arable_per_rural') if !missing(county_arable_per_rural)
gen byte mod_ag_depend_high = (county_primary_share>`p50_county_primary_share') if !missing(county_primary_share)
gen byte mod_aglabor_high = (county_ag_labor_share>`p50_county_ag_labor_share') if !missing(county_ag_labor_share)
gen byte mod_gdp_low = (county_gdp_pc<`p50_county_gdp_pc') if !missing(county_gdp_pc)
gen byte mod_tertiary_low = (county_tertiary_share<`p50_county_tertiary_share') if !missing(county_tertiary_share)
gen byte mod_mech_low = (county_mech_per_arable<`p50_county_mech_per_arable') if !missing(county_mech_per_arable)

compress
save `BASE', replace

local BINMODS "mod_land_pressure_density mod_land_pressure_arable mod_land_scarce_p25 mod_ag_depend_high mod_aglabor_high mod_gdp_low mod_tertiary_low mod_mech_low"
local mod_land_pressure_density_lab "county_rural_density_high"
local mod_land_pressure_arable_lab "county_arable_per_rural_low"
local mod_land_scarce_p25_lab "county_arable_per_rural_bottom25"
local mod_ag_depend_high_lab "county_primary_share_high"
local mod_aglabor_high_lab "county_ag_labor_share_high"
local mod_gdp_low_lab "county_gdp_pc_low"
local mod_tertiary_low_lab "county_tertiary_share_low"
local mod_mech_low_lab "county_mechanization_low"

local CONTMODS "z_county_rural_density z_county_arable_per_rural z_county_gdp_pc z_county_primary_share z_county_tertiary_share z_county_ag_labor_share z_county_mech_per_arable z_county_sow_per_arable z_county_rural_income"
local z_county_rural_density_lab "z_county_rural_density"
local z_county_arable_per_rural_lab "z_county_arable_per_rural"
local z_county_gdp_pc_lab "z_county_gdp_pc"
local z_county_primary_share_lab "z_county_primary_share"
local z_county_tertiary_share_lab "z_county_tertiary_share"
local z_county_ag_labor_share_lab "z_county_ag_labor_share"
local z_county_mech_per_arable_lab "z_county_mechanization"
local z_county_sow_per_arable_lab "z_county_sowing_intensity"
local z_county_rural_income_lab "z_county_rural_income"

tempfile SUPP
postfile PS str40 moderator str60 label long rows households counties double share using `SUPP', replace
foreach M of local BINMODS {
    use `BASE', clear
    keep if year==2014 & s_mech_hh==1 & !missing(`M')
    egen byte __tagh = tag(hid)
    egen byte __tagc = tag(__cid_id)
    quietly count
    local rows = r(N)
    quietly count if __tagh==1
    local hh = r(N)
    quietly count if __tagc==1
    local cc = r(N)
    quietly summarize `M', meanonly
    post PS ("`M'") ("``M'_lab'") (`rows') (`hh') (`cc') (r(mean))
}
postclose PS
use `SUPP', clear
export delimited using "`OUT'/audit/Round2B_E_external_county_moderator_support.csv", replace

cap program drop __x_stack_bin
program define __x_stack_bin
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
        keep if inlist(year,2014,2016) & (first_thr==2016 | first_thr==2018 | never_thr==1)
        gen byte treated=(first_thr==2016)
        gen byte post=(year==2016)
        gen byte winflag=0
        save `W16', replace
    restore
    preserve
        keep if inlist(year,2016,2018) & (first_thr==2018 | never_thr==1)
        gen byte treated=(first_thr==2018)
        gen byte post=(year==2018)
        gen byte winflag=1
        save `W18', replace
    restore
    use `W16', clear
    append using `W18'
    egen long hid_stack=group(winflag hid)
    egen long year_stack=group(winflag year)
    quietly count if !missing(`outcome', `modvar')
    if r(N)<50 {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("error") (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) ("too few")
        exit
    }
    cap noisily reghdfe `outcome' i.treated##i.post##i.`modvar' if !missing(`outcome', `modvar'), absorb(hid_stack year_stack) vce(cluster __cid_id)
    if _rc {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("error") (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) ("failed")
        exit
    }
    tempvar ES THH TCC THH1 THH0 TCC1 TCC0
    gen byte `ES'=e(sample)
    egen byte `THH'=tag(hid) if `ES'
    quietly count if `THH'==1
    local HH=r(N)
    egen byte `TCC'=tag(__cid_id) if `ES'
    quietly count if `TCC'==1
    local CC=r(N)
    egen byte `THH1'=tag(hid) if `ES' & treated==1 & `modvar'==1
    quietly count if `THH1'==1
    local THH_hi=r(N)
    egen byte `THH0'=tag(hid) if `ES' & treated==1 & `modvar'==0
    quietly count if `THH0'==1
    local THH_lo=r(N)
    egen byte `TCC1'=tag(__cid_id) if `ES' & treated==1 & `modvar'==1
    quietly count if `TCC1'==1
    local TCC_hi=r(N)
    egen byte `TCC0'=tag(__cid_id) if `ES' & treated==1 & `modvar'==0
    quietly count if `TCC0'==1
    local TCC_lo=r(N)
    local NN=e(N)
    scalar b_low=.
    scalar se_low=.
    scalar p_low=.
    cap scalar b_low=_b[1.treated#1.post]
    cap scalar se_low=_se[1.treated#1.post]
    if se_low<. & se_low>0 scalar p_low=2*ttail(e(df_r),abs(b_low/se_low))
    scalar b_diff=.
    scalar se_diff=.
    scalar p_diff=.
    cap scalar b_diff=_b[1.treated#1.post#1.`modvar']
    cap scalar se_diff=_se[1.treated#1.post#1.`modvar']
    cap test 1.treated#1.post#1.`modvar'=0
    if !_rc scalar p_diff=r(p)
    scalar b_total=.
    scalar se_total=.
    scalar p_total=.
    cap lincom 1.treated#1.post + 1.treated#1.post#1.`modvar'
    if !_rc {
        scalar b_total=r(estimate)
        scalar se_total=r(se)
        scalar p_total=r(p)
    }
    post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("lower_group_DID") (b_low) (se_low) (p_low) (`NN') (`HH') (`CC') (`THH_hi') (`THH_lo') (`TCC_hi') (`TCC_lo') ("ok")
    post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("high_minus_low_diff") (b_diff) (se_diff) (p_diff) (`NN') (`HH') (`CC') (`THH_hi') (`THH_lo') (`TCC_hi') (`TCC_lo') ("ok")
    post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") ("high_group_total") (b_total) (se_total) (p_total) (`NN') (`HH') (`CC') (`THH_hi') (`THH_lo') (`TCC_hi') (`TCC_lo') ("ok")
end

cap program drop __x_stack_cont
program define __x_stack_cont
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
        keep if inlist(year,2014,2016) & (first_thr==2016 | first_thr==2018 | never_thr==1)
        gen byte treated=(first_thr==2016)
        gen byte post=(year==2016)
        gen byte winflag=0
        save `W16', replace
    restore
    preserve
        keep if inlist(year,2016,2018) & (first_thr==2018 | never_thr==1)
        gen byte treated=(first_thr==2018)
        gen byte post=(year==2018)
        gen byte winflag=1
        save `W18', replace
    restore
    use `W16', clear
    append using `W18'
    egen long hid_stack=group(winflag hid)
    egen long year_stack=group(winflag year)
    quietly count if !missing(`outcome', `modvar')
    if r(N)<50 {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") (.) (.) (.) (.) (.) (.) ("too few")
        exit
    }
    cap noisily reghdfe `outcome' i.treated##i.post##c.`modvar' if !missing(`outcome', `modvar'), absorb(hid_stack year_stack) vce(cluster __cid_id)
    if _rc {
        post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") (.) (.) (.) (.) (.) (.) ("failed")
        exit
    }
    tempvar ES THH TCC
    gen byte `ES'=e(sample)
    egen byte `THH'=tag(hid) if `ES'
    quietly count if `THH'==1
    local HH=r(N)
    egen byte `TCC'=tag(__cid_id) if `ES'
    quietly count if `TCC'==1
    local CC=r(N)
    scalar b=.
    scalar se=.
    scalar p=.
    cap scalar b=_b[1.treated#1.post#c.`modvar']
    cap scalar se=_se[1.treated#1.post#c.`modvar']
    cap test 1.treated#1.post#c.`modvar'=0
    if !_rc scalar p=r(p)
    post `posth' ("`restrict'") ("`scope'") ("`thrname'") ("`outcome'") ("`modname'") (b) (se) (p) (e(N)) (`HH') (`CC') ("ok")
end

tempfile BINOUT
postfile PBI str32 restriction str12 sample_scope str24 threshold str20 outcome str60 moderator str28 term ///
    double b se p long N households counties treated_high_hh treated_low_hh treated_high_counties treated_low_counties str60 status using `BINOUT', replace

foreach RESTR in original exclude_official2014 exclude_admin_start_by2014 {
    foreach SCOPE in mech adjacent {
        foreach THR in completed_t high_sat80_t {
            local TNAME "`THR'"
            if "`THR'"=="completed_t" local TNAME "Completion"
            if "`THR'"=="high_sat80_t" local TNAME "High-saturation"
            foreach Y in any_rentin asinh_rentin {
                foreach M of local BINMODS {
                    __x_stack_bin, basefile("`BASE'") posth(PBI) scope("`SCOPE'") restrict("`RESTR'") thrvar(`THR') thrname("`TNAME'") outcome(`Y') modvar(`M') modname("``M'_lab'")
                }
            }
        }
    }
}
postclose PBI
use `BINOUT', clear
export delimited using "`OUT'/tables/Round2B_E_external_county_binary.csv", replace

tempfile CONTOUT
postfile PCO str32 restriction str12 sample_scope str24 threshold str20 outcome str60 moderator ///
    double b se p long N households counties str60 status using `CONTOUT', replace

foreach RESTR in original exclude_official2014 exclude_admin_start_by2014 {
    foreach SCOPE in mech adjacent {
        foreach THR in completed_t high_sat80_t {
            local TNAME "`THR'"
            if "`THR'"=="completed_t" local TNAME "Completion"
            if "`THR'"=="high_sat80_t" local TNAME "High-saturation"
            foreach Y in any_rentin asinh_rentin {
                foreach M of local CONTMODS {
                    __x_stack_cont, basefile("`BASE'") posth(PCO) scope("`SCOPE'") restrict("`RESTR'") thrvar(`THR') thrname("`TNAME'") outcome(`Y') modvar(`M') modname("``M'_lab'")
                }
            }
        }
    }
}
postclose PCO
use `CONTOUT', clear
export delimited using "`OUT'/tables/Round2B_F_external_county_continuous.csv", replace

log close
