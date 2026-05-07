/********************************************************************
* 164_round25_round3_a3_observability_selection_20260502.do
*
* Round 3 add-on: A3 missingness / observability selection.
*
* Purpose:
*   The biggest sample-contraction point is nonmissing A3 moderator
*   support. This module probes whether high-instability results are
*   driven by selection into A3-observed villages/households.
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

local OUTROOT "$ROOT/result/round25_empirical_rebuild_20260502/round3_sample_selection/a3_observability"
cap mkdir "$ROOT/result"
cap mkdir "$ROOT/result/round25_empirical_rebuild_20260502"
cap mkdir "$ROOT/result/round25_empirical_rebuild_20260502/round3_sample_selection"
cap mkdir "`OUTROOT'"
cap mkdir "`OUTROOT'/audit"
cap mkdir "`OUTROOT'/tables"
cap mkdir "`OUTROOT'/logs"
cap log close _all
log using "`OUTROOT'/logs/164_round25_round3_a3_observability_selection_20260502.log", replace text

local PANEL "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_indivbridge_20260416.dta"
local ADMIN "$ROOT/data/topjournal_rebuild/admin/admin_rollout_countyyear_v2.dta"
foreach f in "`PANEL'" "`ADMIN'" {
    cap confirm file "`f'"
    if _rc {
        di as error "Missing required file: `f'"
        exit 459
    }
}

tempfile ADMINUSE MASTER STACK BASE14 A3W

preserve
    use "`ADMIN'", clear
    keep county_id_num year county_signedoff_t county_issued_t county_completed_t county_sat_t county_completion_rate
    rename county_id_num __cid_id
    save `ADMINUSE', replace
restore

* ------------------------------------------------------------------
* Helpers
* ------------------------------------------------------------------
cap program drop __r3a_build_stack
program define __r3a_build_stack
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

cap program drop __r3a_est_binary
program define __r3a_est_binary
    version 17
    syntax , HANDLE(name) SCOPE(string) THRESHOLD(string) OUTCOME(name) MOD(name) SPEC(string) [WVAR(name)]

    local WOPT ""
    if "`wvar'"!="" local WOPT "[aw=`wvar']"

    cap noisily reghdfe `outcome' i.treated##i.post##i.`mod' `WOPT' ///
        if !missing(`outcome', `mod'), absorb(hid_stack year_stack) vce(cluster __cid_id)
    if _rc {
        post `handle' ("`scope'") ("`threshold'") ("`outcome'") ("`spec'") ///
            (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) (.)
        exit
    }

    tempvar es taghh tagcl
    gen byte `es' = e(sample)
    quietly egen byte `taghh' = tag(hid_stack) if `es'
    quietly count if `taghh'==1
    local HH = r(N)
    quietly egen byte `tagcl' = tag(__cid_id) if `es'
    quietly count if `tagcl'==1
    local CL = r(N)
    quietly summarize `outcome' if `es', meanonly
    local MEAN = r(mean)

    tempname pbase pdiff btot setot ptot
    scalar `pbase' = 2*ttail(e(df_r), abs(_b[1.treated#1.post]/_se[1.treated#1.post]))
    scalar `pdiff' = 2*ttail(e(df_r), abs(_b[1.treated#1.post#1.`mod']/_se[1.treated#1.post#1.`mod']))
    quietly lincom 1.treated#1.post + 1.treated#1.post#1.`mod'
    scalar `btot' = r(estimate)
    scalar `setot' = r(se)
    scalar `ptot' = r(p)

    post `handle' ("`scope'") ("`threshold'") ("`outcome'") ("`spec'") ///
        (_b[1.treated#1.post]) (_se[1.treated#1.post]) (`pbase') ///
        (_b[1.treated#1.post#1.`mod']) (_se[1.treated#1.post#1.`mod']) (`pdiff') ///
        (`btot') (`setot') (`ptot') (e(N)) (`HH') (`CL') (`MEAN')
end

cap program drop __r3a_post_group_effect
program define __r3a_post_group_effect
    version 17
    syntax , HANDLE(name) SCOPE(string) THRESHOLD(string) OUTCOME(name) TERM(string) LABEL(string)

    cap quietly lincom `term'
    if _rc {
        post `handle' ("`scope'") ("`threshold'") ("`outcome'") ("`label'") (.) (.) (.) (.) (.) (.) (.) (.) (.)
        exit
    }
    post `handle' ("`scope'") ("`threshold'") ("`outcome'") ("`label'") ///
        (r(estimate)) (r(se)) (r(p)) (e(N)) (${R3A_HH}) (${R3A_CL}) (${R3A_NLOW}) (${R3A_NHIGH}) (${R3A_NMISS})
end

* ------------------------------------------------------------------
* 1) Master panel
* ------------------------------------------------------------------
use "`PANEL'", clear
keep if inlist(year,2014,2016,2018)
merge m:1 __cid_id year using `ADMINUSE', nogen keep(match master)

gen byte a3_obs = inlist(a3_high_insec,0,1)
gen byte instab_high = a3_high_insec if a3_obs==1
gen byte a3_grp = .
replace a3_grp = 0 if a3_obs==1 & instab_high==0
replace a3_grp = 1 if a3_obs==1 & instab_high==1
replace a3_grp = 2 if a3_obs==0
label define a3grp 0 "A3 lower" 1 "A3 high" 2 "A3 missing", replace
label values a3_grp a3grp

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
* 2) A3 observability support
* ------------------------------------------------------------------
tempname PSUP
tempfile FSUP
postfile `PSUP' str12 sample_scope str20 threshold str18 stage ///
    long rows households counties low_hh high_hh missing_hh low_counties high_counties missing_counties using "`FSUP'", replace

foreach SCOPE in mech adjacent {
    foreach THR in completed_t high_sat80_t {
        use `MASTER', clear
        quietly __r3a_build_stack, thr(`THR') scope("`SCOPE'")
        foreach ST in raw outcome_any outcome_asinh estim_any estim_asinh {
            preserve
                if "`ST'"=="outcome_any" keep if !missing(any_rentin)
                if "`ST'"=="outcome_asinh" keep if !missing(asinh_rentin)
                if "`ST'"=="estim_any" {
                    cap noisily reghdfe any_rentin i.treated##i.post##i.instab_high if !missing(any_rentin, instab_high), absorb(hid_stack year_stack) vce(cluster __cid_id)
                    if _rc restore, preserve
                    else keep if e(sample)
                }
                if "`ST'"=="estim_asinh" {
                    cap noisily reghdfe asinh_rentin i.treated##i.post##i.instab_high if !missing(asinh_rentin, instab_high), absorb(hid_stack year_stack) vce(cluster __cid_id)
                    if _rc restore, preserve
                    else keep if e(sample)
                }
                tempvar taghh tagcl taglh taghhg tagmh taglc taghc tagmc
                quietly count
                local rows = r(N)
                quietly egen byte `taghh' = tag(hid)
                quietly count if `taghh'==1
                local hh = r(N)
                quietly egen byte `tagcl' = tag(__cid_id)
                quietly count if `tagcl'==1
                local cc = r(N)
                quietly egen byte `taglh' = tag(hid) if a3_grp==0
                quietly count if `taglh'==1
                local lhh = r(N)
                quietly egen byte `taghhg' = tag(hid) if a3_grp==1
                quietly count if `taghhg'==1
                local hhh = r(N)
                quietly egen byte `tagmh' = tag(hid) if a3_grp==2
                quietly count if `tagmh'==1
                local mhh = r(N)
                quietly egen byte `taglc' = tag(__cid_id) if a3_grp==0
                quietly count if `taglc'==1
                local lcc = r(N)
                quietly egen byte `taghc' = tag(__cid_id) if a3_grp==1
                quietly count if `taghc'==1
                local hcc = r(N)
                quietly egen byte `tagmc' = tag(__cid_id) if a3_grp==2
                quietly count if `tagmc'==1
                local mcc = r(N)
                post `PSUP' ("`SCOPE'") ("`THR'") ("`ST'") (`rows') (`hh') (`cc') (`lhh') (`hhh') (`mhh') (`lcc') (`hcc') (`mcc')
            restore
        }
    }
}
postclose `PSUP'

use "`FSUP'", clear
sort sample_scope threshold stage
export delimited using "`OUTROOT'/audit/Round3E_A3_observability_support.csv", replace

* ------------------------------------------------------------------
* 3) A3-observed selection model at 2014 baseline
* ------------------------------------------------------------------
use `MASTER', clear
keep if year==2014
gen byte risk_completed = (never_completed==1 | inlist(first_completed,2016,2018))
keep if risk_completed==1
gen double land_mu_base = land_total_mu_raw
cap confirm variable land_total_mu_clean
if !_rc replace land_mu_base = land_total_mu_clean if !missing(land_total_mu_clean)

foreach V in any_rentin asinh_rentin any_abandon asinh_abandon asinh_land_total land_mu_base Cert_h official2014prov admin_start_by2014 {
    cap confirm variable `V'
    if _rc continue
    quietly summarize `V', meanonly
    replace `V' = r(mean) if missing(`V')
}

cap noisily logit a3_obs c.asinh_rentin c.any_rentin c.asinh_abandon c.any_abandon ///
    c.asinh_land_total c.land_mu_base c.Cert_h c.official2014prov c.admin_start_by2014 ///
    i.__prov_id, vce(cluster __cid_id)
if !_rc predict double phat_a3_prov if e(sample), pr
else gen double phat_a3_prov = .

cap noisily logit a3_obs c.asinh_rentin c.any_rentin c.asinh_abandon c.any_abandon ///
    c.asinh_land_total c.land_mu_base c.Cert_h c.official2014prov c.admin_start_by2014, ///
    vce(cluster __cid_id)
if !_rc predict double phat_a3_simple if e(sample), pr
else gen double phat_a3_simple = phat_a3_prov

gen double w_a3_ipw_prov_raw = 1/phat_a3_prov if a3_obs==1 & phat_a3_prov>0
gen double w_a3_ipw_simple_raw = 1/phat_a3_simple if a3_obs==1 & phat_a3_simple>0

foreach W in w_a3_ipw_prov w_a3_ipw_simple {
    local RAW "`W'_raw"
    _pctile `RAW' if a3_obs==1, percentiles(1 99)
    gen double `W' = `RAW'
    replace `W' = r(r1) if `W'<r(r1) & a3_obs==1
    replace `W' = r(r2) if `W'>r(r2) & a3_obs==1
    quietly summarize `W' if a3_obs==1, meanonly
    replace `W' = `W'/r(mean) if a3_obs==1
}
gen double w_a3_overlap = 1 - phat_a3_simple if a3_obs==1 & phat_a3_simple<.
quietly summarize w_a3_overlap if a3_obs==1, meanonly
replace w_a3_overlap = w_a3_overlap/r(mean) if a3_obs==1

tempname PDIAG
tempfile FDIAG
postfile `PDIAG' str34 statistic double value using "`FDIAG'", replace
quietly count
post `PDIAG' ("baseline2014_risk_rows") (r(N))
quietly count if a3_obs==1
post `PDIAG' ("a3_observed_rows") (r(N))
quietly count if a3_obs==0
post `PDIAG' ("a3_missing_rows") (r(N))
foreach V in phat_a3_prov phat_a3_simple w_a3_ipw_prov_raw w_a3_ipw_simple_raw w_a3_ipw_prov w_a3_ipw_simple w_a3_overlap {
    quietly summarize `V' if (`V'<. & (strpos("`V'","w_")==0 | a3_obs==1)), meanonly
    post `PDIAG' ("`V'_mean") (r(mean))
    post `PDIAG' ("`V'_min") (r(min))
    post `PDIAG' ("`V'_max") (r(max))
}
postclose `PDIAG'
preserve
    use "`FDIAG'", clear
    export delimited using "`OUTROOT'/audit/Round3F_A3_selection_ipw_diagnostics.csv", replace
restore

keep hid phat_a3_prov phat_a3_simple w_a3_ipw_prov w_a3_ipw_simple w_a3_overlap
keep if !missing(w_a3_ipw_simple)
duplicates drop
save `A3W', replace

* ------------------------------------------------------------------
* 4) A3-observed IPW stacked DID
* ------------------------------------------------------------------
tempname PA3W
tempfile FA3W
postfile `PA3W' str12 sample_scope str20 threshold str18 outcome str18 weight_spec ///
    double lower_b lower_se lower_p diff_b diff_se diff_p high_total_b high_total_se high_total_p ///
    long N households clusters double meandv using "`FA3W'", replace

foreach SCOPE in mech adjacent {
    foreach THR in completed_t high_sat80_t {
        use `MASTER', clear
        quietly __r3a_build_stack, thr(`THR') scope("`SCOPE'")
        merge m:1 hid using `A3W', nogen
        foreach Y in any_rentin asinh_rentin {
            preserve
                keep if !missing(`Y', instab_high)
                bys __cid_id: egen double __n_county = count(`Y')
                quietly summarize __n_county if __n_county>0, meanonly
                gen double w_county_bal = r(mean)/__n_county if __n_county>0
                quietly summarize w_county_bal if !missing(w_county_bal), meanonly
                replace w_county_bal = w_county_bal/r(mean) if !missing(w_county_bal)
                gen double w_a3_simple_x_county = w_a3_ipw_simple*w_county_bal if !missing(w_a3_ipw_simple, w_county_bal)
                quietly summarize w_a3_simple_x_county if !missing(w_a3_simple_x_county), meanonly
                replace w_a3_simple_x_county = w_a3_simple_x_county/r(mean) if !missing(w_a3_simple_x_county)
                gen byte mod_a3 = instab_high
                foreach SPEC in unweighted a3_ipw_prov a3_ipw_simple a3_overlap county_bal a3_simple_x_county {
                    local WV ""
                    if "`SPEC'"=="a3_ipw_prov" local WV "w_a3_ipw_prov"
                    if "`SPEC'"=="a3_ipw_simple" local WV "w_a3_ipw_simple"
                    if "`SPEC'"=="a3_overlap" local WV "w_a3_overlap"
                    if "`SPEC'"=="county_bal" local WV "w_county_bal"
                    if "`SPEC'"=="a3_simple_x_county" local WV "w_a3_simple_x_county"
                    quietly __r3a_est_binary, handle(`PA3W') scope("`SCOPE'") threshold("`THR'") outcome(`Y') mod(mod_a3) spec("`SPEC'") wvar(`WV')
                }
            restore
        }
    }
}
postclose `PA3W'
use "`FA3W'", clear
sort sample_scope threshold outcome weight_spec
export delimited using "`OUTROOT'/tables/Round3G_A3_observed_ipw_stacked_did.csv", replace

* ------------------------------------------------------------------
* 5) A3 missing as a third group
* ------------------------------------------------------------------
tempname PGRP
tempfile FGRP
postfile `PGRP' str12 sample_scope str20 threshold str18 outcome str24 term ///
    double b se p long N households clusters n_low n_high n_missing using "`FGRP'", replace

foreach SCOPE in mech adjacent {
    foreach THR in completed_t high_sat80_t {
        use `MASTER', clear
        quietly __r3a_build_stack, thr(`THR') scope("`SCOPE'")
        foreach Y in any_rentin asinh_rentin {
            cap noisily reghdfe `Y' i.treated##i.post##ib0.a3_grp if !missing(`Y', a3_grp), ///
                absorb(hid_stack year_stack) vce(cluster __cid_id)
            if _rc continue

            tempvar es taghh tagcl tagl tagh tagm
            gen byte `es' = e(sample)
            quietly egen byte `taghh' = tag(hid_stack) if `es'
            quietly count if `taghh'==1
            global R3A_HH = r(N)
            quietly egen byte `tagcl' = tag(__cid_id) if `es'
            quietly count if `tagcl'==1
            global R3A_CL = r(N)
            quietly egen byte `tagl' = tag(hid_stack) if `es' & a3_grp==0
            quietly count if `tagl'==1
            global R3A_NLOW = r(N)
            quietly egen byte `tagh' = tag(hid_stack) if `es' & a3_grp==1
            quietly count if `tagh'==1
            global R3A_NHIGH = r(N)
            quietly egen byte `tagm' = tag(hid_stack) if `es' & a3_grp==2
            quietly count if `tagm'==1
            global R3A_NMISS = r(N)

            quietly __r3a_post_group_effect, handle(`PGRP') scope("`SCOPE'") threshold("`THR'") outcome(`Y') term("1.treated#1.post") label("low_total")
            quietly __r3a_post_group_effect, handle(`PGRP') scope("`SCOPE'") threshold("`THR'") outcome(`Y') term("1.treated#1.post + 1.treated#1.post#1.a3_grp") label("high_total")
            quietly __r3a_post_group_effect, handle(`PGRP') scope("`SCOPE'") threshold("`THR'") outcome(`Y') term("1.treated#1.post + 1.treated#1.post#2.a3_grp") label("missing_total")
            quietly __r3a_post_group_effect, handle(`PGRP') scope("`SCOPE'") threshold("`THR'") outcome(`Y') term("1.treated#1.post#1.a3_grp") label("high_minus_low")
            quietly __r3a_post_group_effect, handle(`PGRP') scope("`SCOPE'") threshold("`THR'") outcome(`Y') term("1.treated#1.post#2.a3_grp") label("missing_minus_low")
            quietly __r3a_post_group_effect, handle(`PGRP') scope("`SCOPE'") threshold("`THR'") outcome(`Y') term("1.treated#1.post#1.a3_grp - 1.treated#1.post#2.a3_grp") label("high_minus_missing")
        }
    }
}
postclose `PGRP'
use "`FGRP'", clear
sort sample_scope threshold outcome term
export delimited using "`OUTROOT'/tables/Round3H_A3_missing_thirdgroup_stacked_did.csv", replace

* ------------------------------------------------------------------
* 6) Missing-as-low/high recodes and tipping summary
* ------------------------------------------------------------------
tempname PREC PTIP
tempfile FREC FTIP
postfile `PREC' str12 sample_scope str20 threshold str18 outcome str20 recode ///
    double lower_b lower_se lower_p diff_b diff_se diff_p high_total_b high_total_se high_total_p ///
    long N households clusters double meandv using "`FREC'", replace
postfile `PTIP' str12 sample_scope str20 threshold str18 outcome ///
    double low_total high_total missing_total n_low n_high n_missing min_diff max_diff q_at_min q_at_zero using "`FTIP'", replace

foreach SCOPE in mech adjacent {
    foreach THR in completed_t high_sat80_t {
        use `MASTER', clear
        quietly __r3a_build_stack, thr(`THR') scope("`SCOPE'")
        gen byte a3_missing_low = (a3_grp==1) if inlist(a3_grp,0,1,2)
        replace a3_missing_low = 0 if a3_grp==2
        gen byte a3_missing_high = (a3_grp==1 | a3_grp==2) if inlist(a3_grp,0,1,2)
        gen byte a3_obs_only = instab_high if a3_obs==1
        foreach Y in any_rentin asinh_rentin {
            foreach R in a3_obs_only a3_missing_low a3_missing_high {
                quietly __r3a_est_binary, handle(`PREC') scope("`SCOPE'") threshold("`THR'") outcome(`Y') mod(`R') spec("`R'")
            }

            preserve
                keep if !missing(`Y', a3_grp)
                cap noisily reghdfe `Y' i.treated##i.post##ib0.a3_grp, absorb(hid_stack year_stack) vce(cluster __cid_id)
                if !_rc {
                    tempvar es tagl tagh tagm
                    gen byte `es' = e(sample)
                    tempname bL bH bM
                    cap quietly lincom 1.treated#1.post
                    scalar `bL' = cond(_rc, ., r(estimate))
                    cap quietly lincom 1.treated#1.post + 1.treated#1.post#1.a3_grp
                    scalar `bH' = cond(_rc, ., r(estimate))
                    cap quietly lincom 1.treated#1.post + 1.treated#1.post#2.a3_grp
                    scalar `bM' = cond(_rc, ., r(estimate))
                    quietly egen byte `tagl' = tag(hid_stack) if `es' & a3_grp==0
                    quietly count if `tagl'==1
                    local nL = r(N)
                    quietly egen byte `tagh' = tag(hid_stack) if `es' & a3_grp==1
                    quietly count if `tagh'==1
                    local nH = r(N)
                    quietly egen byte `tagm' = tag(hid_stack) if `es' & a3_grp==2
                    quietly count if `tagm'==1
                    local nM = r(N)
                    local mind = .
                    local maxd = .
                    local qmin = .
                    local qzero = .
                    forvalues qi = 0/100 {
                        local q = `qi'/100
                        scalar __high = (`nH'*`bH' + `q'*`nM'*`bM')/(`nH' + `q'*`nM')
                        scalar __low  = (`nL'*`bL' + (1-`q')*`nM'*`bM')/(`nL' + (1-`q')*`nM')
                        scalar __diff = __high - __low
                        if missing(`mind') | __diff < `mind' {
                            local mind = __diff
                            local qmin = `q'
                        }
                        if missing(`maxd') | __diff > `maxd' local maxd = __diff
                        if missing(`qzero') & __diff<=0 local qzero = `q'
                    }
                    post `PTIP' ("`SCOPE'") ("`THR'") ("`Y'") ///
                        (`bL') (`bH') (`bM') (`nL') (`nH') (`nM') (`mind') (`maxd') (`qmin') (`qzero')
                }
            restore
        }
    }
}
postclose `PREC'
postclose `PTIP'

use "`FREC'", clear
sort sample_scope threshold outcome recode
export delimited using "`OUTROOT'/tables/Round3I_A3_missing_recode_bounds.csv", replace

use "`FTIP'", clear
sort sample_scope threshold outcome
export delimited using "`OUTROOT'/tables/Round3J_A3_tipping_summary.csv", replace

* ------------------------------------------------------------------
* 7) Memo shell
* ------------------------------------------------------------------
tempname FH
cap file close `FH'
file open `FH' using "`OUTROOT'/Round3_A3Observability_Memo_20260502.md", write text replace
file write `FH' "# Round 3 add-on memo shell: A3 observability / missingness" _n _n
file write `FH' "Generated: `c(current_date)' `c(current_time)'" _n _n
file write `FH' "Outputs:" _n
file write `FH' "- audit/Round3E_A3_observability_support.csv" _n
file write `FH' "- audit/Round3F_A3_selection_ipw_diagnostics.csv" _n
file write `FH' "- tables/Round3G_A3_observed_ipw_stacked_did.csv" _n
file write `FH' "- tables/Round3H_A3_missing_thirdgroup_stacked_did.csv" _n
file write `FH' "- tables/Round3I_A3_missing_recode_bounds.csv" _n
file write `FH' "- tables/Round3J_A3_tipping_summary.csv" _n
file close `FH'

log close
exit 0
