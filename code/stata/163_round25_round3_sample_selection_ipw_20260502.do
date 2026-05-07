/********************************************************************
* 163_round25_round3_sample_selection_ipw_20260502.do
*
* Round 3 in the 10-round plan:
* sample contraction and selection into the preferred stacked DID.
********************************************************************/

version 17
set more off
set linesize 255
set varabbrev off

local __needroot 0
cap confirm global ROOT
if _rc local __needroot 1
else {
    local __groot = subinstr("$ROOT", char(92), "/", .)
    if !fileexists("`__groot'/dofiles/01_globals_and_ado.do") local __needroot 1
}
if `__needroot' {
    local __pwd  = subinstr("`c(pwd)'", char(92), "/", .)
    local __this = subinstr("`c(filename)'", char(92), "/", .)
    local __starts "`__pwd'"
    if "`__this'" != "" {
        local __dir = regexr("`__this'", "/[^/]*$", "")
        local __starts "`__starts' `__dir'"
    }
    local __root ""
    foreach s of local __starts {
        local try = subinstr("`s'", char(92), "/", .)
        if regexm("`try'", "/(dofiles|data|result|results|output|diagnostics)(/|$)") {
            local try = regexr("`try'", "/(dofiles|data|result|results|output|diagnostics)(/.*)?$", "")
        }
        forvalues up = 0/8 {
            if fileexists("`try'/dofiles/01_globals_and_ado.do") {
                local __root "`try'"
                continue, break
            }
            local parent = regexr("`try'", "/[^/]+$", "")
            if ("`parent'"=="" | "`parent'"=="`try'") continue, break
            local try "`parent'"
        }
        if "`__root'" != "" continue, break
    }
    if "`__root'" == "" local __root "`__pwd'"
    global ROOT "`__root'"
}

cap confirm file "$ROOT/code/stata/01_globals_and_ado.do"
if !_rc quietly do "$ROOT/code/stata/01_globals_and_ado.do"
else {
    cap confirm global DATA
    if _rc global DATA "$ROOT/data"
    cap confirm global OUT
    if _rc global OUT "$ROOT/result"
}

cap which reghdfe
if _rc ssc install reghdfe, replace

local OUTROOT "$ROOT/result/round25_empirical_rebuild_20260502/round3_sample_selection"
cap mkdir "$ROOT/result"
cap mkdir "$ROOT/result/round25_empirical_rebuild_20260502"
cap mkdir "`OUTROOT'"
cap mkdir "`OUTROOT'/audit"
cap mkdir "`OUTROOT'/tables"
cap mkdir "`OUTROOT'/logs"
cap log close _all
log using "`OUTROOT'/logs/163_round25_round3_sample_selection_ipw_20260502.log", replace text

local REG    "$ROOT/data/admin_rollout/CLDS_sample_registry_with_admin_rollout.dta"
local PANEL  "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_indivbridge_20260416.dta"
local ADMIN  "$ROOT/data/topjournal_rebuild/admin/admin_rollout_countyyear_v2.dta"

foreach f in "`REG'" "`PANEL'" "`ADMIN'" {
    cap confirm file "`f'"
    if _rc {
        di as error "Missing required file: `f'"
        exit 459
    }
}

tempfile ADMINUSE MASTER STACK RETAIN BASE14 WEIGHTS

preserve
    use "`ADMIN'", clear
    keep county_id_num year county_signedoff_t county_issued_t county_completed_t county_sat_t county_completion_rate
    rename county_id_num __cid_id
    save `ADMINUSE', replace
restore

cap program drop __r3s_count_post
program define __r3s_count_post
    version 17
    syntax , HANDLE(name) ORDER(integer) STEP(string) SOURCE(string) NOTE(string)

    tempvar taghh tagcl
    quietly count
    local rows = r(N)
    cap confirm variable hid
    if !_rc {
        quietly egen byte `taghh' = tag(hid) if !missing(hid)
        quietly count if `taghh'==1
        local hh = r(N)
    }
    else local hh = .
    cap confirm variable __cid_id
    if !_rc {
        quietly egen byte `tagcl' = tag(__cid_id) if !missing(__cid_id)
        quietly count if `tagcl'==1
        local cc = r(N)
    }
    else local cc = .
    post `handle' (`order') ("`step'") ("`source'") (`rows') (`hh') (`cc') ("`note'")
end

cap program drop __r3s_build_stack
program define __r3s_build_stack
    version 17
    syntax , THR(name) SCOPE(string)

    if "`scope'"=="mech" {
        cap confirm variable s_mech_hh
        if !_rc keep if s_mech_hh==1
    }
    if "`scope'"=="adjacent" keep if timing_adjacent_hh==1

    bys __cid_id: egen first_thr = min(cond(`thr'==1, year, .))
    gen byte never_thr = missing(first_thr)
    keep if never_thr==1 | inlist(first_thr,2016,2018)

    preserve
        keep if inlist(year,2014,2016) & (first_thr==2016 | first_thr==2018 | never_thr==1)
        gen byte treated = (first_thr==2016)
        gen byte post = (year==2016)
        gen int cohort = 2016
        gen byte winflag = 0
        tempfile W16
        save `W16', replace
    restore

    keep if inlist(year,2016,2018) & (first_thr==2018 | never_thr==1)
    gen byte treated = (first_thr==2018)
    gen byte post = (year==2018)
    gen int cohort = 2018
    gen byte winflag = 1
    append using `W16'

    gen long hid_stack = hid + 10000000*winflag
    gen long year_stack = year + 10000*winflag
end

cap program drop __r3s_stats
program define __r3s_stats, rclass
    version 17
    syntax , YVAR(name)
    tempvar es taghh tagcl
    gen byte `es' = e(sample)
    quietly summarize `yvar' if `es', meanonly
    return scalar meandv = r(mean)
    quietly egen byte `taghh' = tag(hid_stack) if `es'
    quietly count if `taghh'==1
    return scalar hhstack = r(N)
    quietly egen byte `tagcl' = tag(__cid_id) if `es'
    quietly count if `tagcl'==1
    return scalar clusters = r(N)
end

cap program drop __r3s_run_did
program define __r3s_run_did
    version 17
    syntax , HANDLE(name) SCOPE(string) THRESHOLD(string) OUTCOME(name) WSPEC(string)

    local WOPT ""
    if "`wspec'"=="ipw2014" local WOPT "[aw=w_ipw2014]"
    if "`wspec'"=="ipw2014_simple" local WOPT "[aw=w_ipw2014_simple]"
    if "`wspec'"=="overlap2014" local WOPT "[aw=w_overlap2014]"
    if "`wspec'"=="county_bal" local WOPT "[aw=w_county_bal]"
    if "`wspec'"=="ipw_x_county" local WOPT "[aw=w_ipw_x_county]"
    if "`wspec'"=="ipw_simple_x_county" local WOPT "[aw=w_ipw_simple_x_county]"
    if "`wspec'"=="overlap_x_county" local WOPT "[aw=w_overlap_x_county]"

    if "`wspec'"!="unweighted" {
        local wvar = subinstr("`WOPT'", "[aw=", "", .)
        local wvar = subinstr("`wvar'", "]", "", .)
        quietly count if !missing(`outcome', instab_high, `wvar') & `wvar'>0
        if r(N)==0 {
            post `handle' ("`scope'") ("`threshold'") ("`outcome'") ("`wspec'") ///
                (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) (.)
            exit
        }
    }

    cap noisily reghdfe `outcome' i.treated##i.post##i.instab_high `WOPT' ///
        if !missing(`outcome', instab_high), absorb(hid_stack year_stack) vce(cluster __cid_id)
    if _rc {
        post `handle' ("`scope'") ("`threshold'") ("`outcome'") ("`wspec'") ///
            (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) (.)
        exit
    }
    quietly __r3s_stats, yvar(`outcome')
    local N = e(N)
    local HH = r(hhstack)
    local CL = r(clusters)
    local MEAN = r(meandv)

    tempname pbase pdiff btot setot ptot
    scalar `pbase' = 2*ttail(e(df_r), abs(_b[1.treated#1.post]/_se[1.treated#1.post]))
    scalar `pdiff' = 2*ttail(e(df_r), abs(_b[1.treated#1.post#1.instab_high]/_se[1.treated#1.post#1.instab_high]))
    quietly lincom 1.treated#1.post + 1.treated#1.post#1.instab_high
    scalar `btot' = r(estimate)
    scalar `setot' = r(se)
    scalar `ptot' = r(p)

    post `handle' ("`scope'") ("`threshold'") ("`outcome'") ("`wspec'") ///
        (_b[1.treated#1.post]) (_se[1.treated#1.post]) (`pbase') ///
        (_b[1.treated#1.post#1.instab_high]) (_se[1.treated#1.post#1.instab_high]) (`pdiff') ///
        (`btot') (`setot') (`ptot') (`N') (`HH') (`CL') (`MEAN')
end

* ------------------------------------------------------------------
* 1) Build master panel with preferred thresholds
* ------------------------------------------------------------------
use "`PANEL'", clear
keep if inlist(year,2014,2016,2018)
merge m:1 __cid_id year using `ADMINUSE', nogen keep(match master)

gen byte instab_high = (a3_high_insec==1) if inlist(a3_high_insec,0,1)
gen byte signoff_or_issue_t = ((county_signedoff_t==1) | (county_issued_t==1)) if !missing(county_signedoff_t) | !missing(county_issued_t)
gen byte completed_t = county_completed_t if !missing(county_completed_t)
gen byte high_sat80_t = (county_sat_t>=0.8) if !missing(county_sat_t)
cap drop asinh_land_total
gen double asinh_land_total = asinh(land_total_mu_raw) if !missing(land_total_mu_raw)

bys __cid_id: egen first_completed = min(cond(completed_t==1, year, .))
gen byte never_completed = missing(first_completed)
bys __cid_id: egen min_admin_start = min(admin_rollout_start_year)
gen byte official2014prov = inlist(__prov_id, 34, 37, 51)
gen byte admin_start_by2014 = (min_admin_start<=2014) if !missing(min_admin_start)
replace admin_start_by2014 = 0 if missing(admin_start_by2014)

compress
save `MASTER', replace

* ------------------------------------------------------------------
* 2) Sample funnel
* ------------------------------------------------------------------
tempname PF
tempfile FFUN
postfile `PF' int order str90 step str18 source long hh_year households counties str160 note using "`FFUN'", replace

use "`REG'", clear
keep if s_wave==1
quietly __r3s_count_post, handle(`PF') order(1) step("CLDS 2014/2016/2018 registry wave rows") source("registry") note("s_wave==1")
keep if s_land==1
quietly __r3s_count_post, handle(`PF') order(2) step("Land/rural-eligible registry rows") source("registry") note("s_land==1 within wave rows")
keep if s_mech_hh==1
quietly __r3s_count_post, handle(`PF') order(3) step("Timing/main-variable eligible registry rows") source("registry") note("s_mech_hh==1 within land-eligible rows")

use `MASTER', clear
quietly __r3s_count_post, handle(`PF') order(4) step("Current mechanism panel rows") source("panel") note("topjournal household mechanism panel")
preserve
    keep if year==2014
    quietly __r3s_count_post, handle(`PF') order(5) step("Current panel households observed in 2014") source("panel") note("baseline row available")
restore
preserve
    keep if timing_adjacent_hh==1
    quietly __r3s_count_post, handle(`PF') order(6) step("Adjacent-switch validation panel rows") source("panel") note("timing_adjacent_hh==1")
restore

foreach SCOPE in mech adjacent {
    foreach THR in completed_t high_sat80_t signoff_or_issue_t {
        use `MASTER', clear
        quietly __r3s_build_stack, thr(`THR') scope("`SCOPE'")
        quietly __r3s_count_post, handle(`PF') order(10) step("Raw stacked rows: `SCOPE' x `THR'") source("stack") note("before outcome/A3/singleton restrictions")
        keep if instab_high<.
        quietly __r3s_count_post, handle(`PF') order(11) step("A3 moderator nonmissing: `SCOPE' x `THR'") source("stack") note("instab_high nonmissing")
        foreach Y in any_rentin asinh_rentin {
            preserve
                keep if !missing(`Y', instab_high)
                quietly __r3s_count_post, handle(`PF') order(12) step("Outcome nonmissing: `SCOPE' x `THR' x `Y'") source("stack") note("before reghdfe singleton drop")
                cap noisily reghdfe `Y' i.treated##i.post##i.instab_high, absorb(hid_stack year_stack) vce(cluster __cid_id)
                if !_rc {
                    keep if e(sample)
                    quietly __r3s_count_post, handle(`PF') order(13) step("Estimation sample: `SCOPE' x `THR' x `Y'") source("stack") note("after reghdfe singleton drop")
                }
            restore
        }
    }
}
postclose `PF'

use "`FFUN'", clear
sort order step
export delimited using "`OUTROOT'/audit/Round3_A_sample_funnel.csv", replace

* ------------------------------------------------------------------
* 3) Preferred retained-household marker: mechanism x completed_t
* ------------------------------------------------------------------
use `MASTER', clear
quietly __r3s_build_stack, thr(completed_t) scope("mech")
save `STACK', replace

foreach Y in any_rentin asinh_rentin {
    use `STACK', clear
    reghdfe `Y' i.treated##i.post##i.instab_high if !missing(`Y', instab_high), absorb(hid_stack year_stack) vce(cluster __cid_id)
    keep if e(sample)
    keep hid
    duplicates drop
    gen byte retained_`Y' = 1
    tempfile R_`Y'
    save `R_`Y'', replace
}

use `R_any_rentin', clear
merge 1:1 hid using `R_asinh_rentin', nogen
replace retained_any_rentin = 0 if missing(retained_any_rentin)
replace retained_asinh_rentin = 0 if missing(retained_asinh_rentin)
save `RETAIN', replace

* ------------------------------------------------------------------
* 4) Baseline 2014 retained-vs-dropped comparison
* ------------------------------------------------------------------
use `MASTER', clear
keep if year==2014
merge m:1 hid using `RETAIN', nogen keep(master match)
replace retained_any_rentin = 0 if missing(retained_any_rentin)
replace retained_asinh_rentin = 0 if missing(retained_asinh_rentin)

gen byte risk_completed = (never_completed==1 | inlist(first_completed,2016,2018))
gen byte cohort2016_completed = (first_completed==2016)
gen byte cohort2018_completed = (first_completed==2018)
gen byte never_completed_base = (never_completed==1)
gen double land_mu_base = land_total_mu_raw
cap confirm variable land_total_mu_clean
if !_rc replace land_mu_base = land_total_mu_clean if !missing(land_total_mu_clean)
cap confirm variable base14_rg_readadjust
if _rc gen byte base14_rg_readadjust = .

keep hid __cid_id __prov_id retained_any_rentin retained_asinh_rentin ///
    risk_completed cohort2016_completed cohort2018_completed never_completed_base ///
    any_rentin asinh_rentin any_abandon asinh_abandon asinh_land_total land_mu_base ///
    Cert_h instab_high base14_rg_readadjust official2014prov admin_start_by2014

save `BASE14', replace

tempname PBAL
tempfile FBAL
postfile `PBAL' str18 retained_marker str24 universe str32 variable ///
    long n_ret n_drop double mean_ret mean_drop diff se p using "`FBAL'", replace

foreach RET in retained_any_rentin retained_asinh_rentin {
    foreach UNIV in all2014 riskset2014 {
        use `BASE14', clear
        if "`UNIV'"=="riskset2014" keep if risk_completed==1
        foreach V in any_rentin asinh_rentin any_abandon asinh_abandon asinh_land_total land_mu_base ///
                    Cert_h instab_high base14_rg_readadjust official2014prov admin_start_by2014 ///
                    cohort2016_completed cohort2018_completed never_completed_base {
            cap confirm variable `V'
            if _rc continue
            quietly count if `RET'==1 & !missing(`V')
            local nr = r(N)
            quietly count if `RET'==0 & !missing(`V')
            local nd = r(N)
            quietly summarize `V' if `RET'==1, meanonly
            local mr = r(mean)
            quietly summarize `V' if `RET'==0, meanonly
            local md = r(mean)
            cap noisily regress `V' `RET', vce(cluster __cid_id)
            if !_rc {
                local b = _b[`RET']
                local se = _se[`RET']
                local p = 2*ttail(e(df_r), abs(`b'/`se'))
            }
            else {
                local b = .
                local se = .
                local p = .
            }
            post `PBAL' ("`RET'") ("`UNIV'") ("`V'") (`nr') (`nd') (`mr') (`md') (`b') (`se') (`p')
        }
    }
}
postclose `PBAL'

use "`FBAL'", clear
sort retained_marker universe variable
export delimited using "`OUTROOT'/tables/Round3_B_retained_vs_dropped_2014.csv", replace

* ------------------------------------------------------------------
* 5) Entry probability model and 2014 IPW
* ------------------------------------------------------------------
use `BASE14', clear
keep if risk_completed==1
gen byte retained = retained_any_rentin

foreach V in any_rentin asinh_rentin any_abandon asinh_abandon asinh_land_total land_mu_base Cert_h instab_high official2014prov admin_start_by2014 {
    cap confirm variable `V'
    if _rc continue
    quietly summarize `V', meanonly
    replace `V' = r(mean) if missing(`V')
}

cap noisily logit retained c.asinh_rentin c.any_rentin c.asinh_abandon c.any_abandon ///
    c.asinh_land_total c.land_mu_base c.Cert_h c.instab_high ///
    c.official2014prov c.admin_start_by2014 i.__prov_id, vce(cluster __cid_id)
if _rc {
    di as error "Province-FE logit failed; retrying parsimonious logit."
    logit retained c.asinh_rentin c.any_rentin c.asinh_abandon c.any_abandon ///
        c.asinh_land_total c.land_mu_base c.Cert_h c.instab_high ///
        c.official2014prov c.admin_start_by2014, vce(cluster __cid_id)
}
predict double phat2014 if e(sample), pr
cap noisily logit retained c.asinh_rentin c.any_rentin c.asinh_abandon c.any_abandon ///
    c.asinh_land_total c.land_mu_base c.Cert_h c.instab_high ///
    c.official2014prov c.admin_start_by2014, vce(cluster __cid_id)
if !_rc predict double phat2014_simple if e(sample), pr
else gen double phat2014_simple = phat2014

gen double w_ipw2014_raw = 1/phat2014 if retained==1 & phat2014>0
_pctile w_ipw2014_raw if retained==1, percentiles(1 99)
gen double w_ipw2014 = w_ipw2014_raw
replace w_ipw2014 = r(r1) if w_ipw2014<r(r1) & retained==1
replace w_ipw2014 = r(r2) if w_ipw2014>r(r2) & retained==1
quietly summarize w_ipw2014 if retained==1, meanonly
replace w_ipw2014 = w_ipw2014/r(mean) if retained==1

gen double w_ipw2014_simple_raw = 1/phat2014_simple if retained==1 & phat2014_simple>0
_pctile w_ipw2014_simple_raw if retained==1, percentiles(1 99)
gen double w_ipw2014_simple = w_ipw2014_simple_raw
replace w_ipw2014_simple = r(r1) if w_ipw2014_simple<r(r1) & retained==1
replace w_ipw2014_simple = r(r2) if w_ipw2014_simple>r(r2) & retained==1
quietly summarize w_ipw2014_simple if retained==1, meanonly
replace w_ipw2014_simple = w_ipw2014_simple/r(mean) if retained==1

gen double w_overlap2014 = 1 - phat2014 if retained==1 & phat2014<.
quietly summarize w_overlap2014 if retained==1, meanonly
replace w_overlap2014 = w_overlap2014/r(mean) if retained==1

tempname PENTRY
tempfile FENTRY
postfile `PENTRY' str30 statistic double value using "`FENTRY'", replace
quietly count
post `PENTRY' ("riskset_2014_rows") (r(N))
quietly count if retained==1
post `PENTRY' ("retained_rows") (r(N))
quietly summarize phat2014 if e(sample), meanonly
post `PENTRY' ("phat_mean") (r(mean))
post `PENTRY' ("phat_min") (r(min))
post `PENTRY' ("phat_max") (r(max))
quietly summarize phat2014_simple if e(sample), meanonly
post `PENTRY' ("phat_simple_mean") (r(mean))
post `PENTRY' ("phat_simple_min") (r(min))
post `PENTRY' ("phat_simple_max") (r(max))
quietly summarize w_ipw2014_raw if retained==1, meanonly
post `PENTRY' ("raw_ipw_mean_retained") (r(mean))
post `PENTRY' ("raw_ipw_min_retained") (r(min))
post `PENTRY' ("raw_ipw_max_retained") (r(max))
quietly summarize w_ipw2014_simple_raw if retained==1, meanonly
post `PENTRY' ("raw_ipw_simple_mean_retained") (r(mean))
post `PENTRY' ("raw_ipw_simple_min_retained") (r(min))
post `PENTRY' ("raw_ipw_simple_max_retained") (r(max))
quietly summarize w_ipw2014 if retained==1, meanonly
post `PENTRY' ("trimmed_ipw_mean_retained") (r(mean))
post `PENTRY' ("trimmed_ipw_min_retained") (r(min))
post `PENTRY' ("trimmed_ipw_max_retained") (r(max))
quietly summarize w_ipw2014_simple if retained==1, meanonly
post `PENTRY' ("trimmed_ipw_simple_mean_retained") (r(mean))
post `PENTRY' ("trimmed_ipw_simple_min_retained") (r(min))
post `PENTRY' ("trimmed_ipw_simple_max_retained") (r(max))
quietly summarize w_overlap2014 if retained==1, meanonly
post `PENTRY' ("overlap_weight_mean_retained") (r(mean))
post `PENTRY' ("overlap_weight_min_retained") (r(min))
post `PENTRY' ("overlap_weight_max_retained") (r(max))
postclose `PENTRY'

preserve
    use "`FENTRY'", clear
    export delimited using "`OUTROOT'/audit/Round3_C_entry_model_ipw_diagnostics.csv", replace
restore

keep hid phat2014 phat2014_simple w_ipw2014 w_ipw2014_simple w_overlap2014
keep if !missing(w_ipw2014)
duplicates drop
save `WEIGHTS', replace

* ------------------------------------------------------------------
* 6) Weighted stacked DID robustness
* ------------------------------------------------------------------
tempname PW
tempfile FW
postfile `PW' str12 sample_scope str20 threshold str18 outcome str18 weight_spec ///
    double lower_b lower_se lower_p diff_b diff_se diff_p high_total_b high_total_se high_total_p ///
    long N households clusters double meandv using "`FW'", replace

foreach SCOPE in mech adjacent {
    foreach THR in completed_t high_sat80_t {
        use `MASTER', clear
        quietly __r3s_build_stack, thr(`THR') scope("`SCOPE'")
        merge m:1 hid using `WEIGHTS', nogen
        foreach Y in any_rentin asinh_rentin {
            preserve
                keep if !missing(`Y', instab_high)
                bys __cid_id: egen double __n_county = count(`Y')
                quietly summarize __n_county if __n_county>0, meanonly
                gen double w_county_bal = r(mean)/__n_county if __n_county>0
                quietly summarize w_county_bal if !missing(w_county_bal), meanonly
                replace w_county_bal = w_county_bal/r(mean) if !missing(w_county_bal)
                gen double w_ipw_x_county = w_ipw2014*w_county_bal if !missing(w_ipw2014, w_county_bal)
                quietly summarize w_ipw_x_county if !missing(w_ipw_x_county), meanonly
                replace w_ipw_x_county = w_ipw_x_county/r(mean) if !missing(w_ipw_x_county)
                gen double w_ipw_simple_x_county = w_ipw2014_simple*w_county_bal if !missing(w_ipw2014_simple, w_county_bal)
                quietly summarize w_ipw_simple_x_county if !missing(w_ipw_simple_x_county), meanonly
                replace w_ipw_simple_x_county = w_ipw_simple_x_county/r(mean) if !missing(w_ipw_simple_x_county)
                gen double w_overlap_x_county = w_overlap2014*w_county_bal if !missing(w_overlap2014, w_county_bal)
                quietly summarize w_overlap_x_county if !missing(w_overlap_x_county), meanonly
                replace w_overlap_x_county = w_overlap_x_county/r(mean) if !missing(w_overlap_x_county)
                foreach W in unweighted ipw2014 ipw2014_simple overlap2014 county_bal ipw_x_county ipw_simple_x_county overlap_x_county {
                    quietly __r3s_run_did, handle(`PW') scope("`SCOPE'") threshold("`THR'") outcome(`Y') wspec("`W'")
                }
            restore
        }
    }
}
postclose `PW'

use "`FW'", clear
sort sample_scope threshold outcome weight_spec
export delimited using "`OUTROOT'/tables/Round3_D_weighted_stacked_did.csv", replace

* ------------------------------------------------------------------
* 7) Memo shell
* ------------------------------------------------------------------
tempname FH
cap file close `FH'
file open `FH' using "`OUTROOT'/Round3_SampleSelection_Memo_20260502.md", write text replace
file write `FH' "# Round 3 memo shell: sample contraction and selection" _n _n
file write `FH' "Generated: `c(current_date)' `c(current_time)'" _n _n
file write `FH' "Outputs:" _n
file write `FH' "- audit/Round3_A_sample_funnel.csv" _n
file write `FH' "- tables/Round3_B_retained_vs_dropped_2014.csv" _n
file write `FH' "- audit/Round3_C_entry_model_ipw_diagnostics.csv" _n
file write `FH' "- tables/Round3_D_weighted_stacked_did.csv" _n
file close `FH'

log close
exit 0
