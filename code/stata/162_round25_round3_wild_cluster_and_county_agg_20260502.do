/********************************************************************
* 162_round25_round3_wild_cluster_and_county_agg_20260502.do
*
* Round 3 add-on: key placebo checks with wild cluster bootstrap and
* county-level aggregation, motivated by very few treated counties in
* some 2012-2014 auxiliary-placebo restrictions.
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
cap which boottest
if _rc ssc install boottest, replace

local OUTROOT "$ROOT/result/round25_empirical_rebuild_20260502/round3_parallel_trends"
cap mkdir "`OUTROOT'"
cap mkdir "`OUTROOT'/tables"
cap mkdir "`OUTROOT'/logs"
cap log close _all
log using "`OUTROOT'/logs/162_round25_round3_wild_cluster_and_county_agg_20260502.log", replace text

local P12 "$ROOT/data/admin_rollout/CLDS_hh_mechanism_panel_2012_2018_with_admin_rollout.dta"
cap confirm file "`P12'"
if _rc exit 459

tempfile BASE
use "`P12'", clear
keep if inlist(year,2012,2014,2016,2018)

gen double asinh_land_total = asinh(land_total_mu_raw) if !missing(land_total_mu_raw)
gen byte completed_t  = admin_completed_by_t if !missing(admin_completed_by_t)
gen byte high_sat80_t = (admin_sat_detail_t>=0.8) if !missing(admin_sat_detail_t)

bys __cid_id: egen min_admin_start = min(admin_rollout_start_year)
gen byte official2014prov = inlist(__prov_id, 34, 37, 51)
gen byte admin_start_by2014 = (min_admin_start<=2014) if !missing(min_admin_start)
replace admin_start_by2014 = 0 if missing(admin_start_by2014)
egen long provyear = group(__prov_id year)

foreach THR in completed_t high_sat80_t {
    bys __cid_id: egen first_`THR' = min(cond(`THR'==1, year, .))
    gen byte never_`THR' = missing(first_`THR')
}

compress
save `BASE', replace

cap program drop __r3b_build_sample
program define __r3b_build_sample
    version 17
    syntax , THR(name) WINDOW(string) CTRLSET(string) RESTRICT(string)

    if "`restrict'"=="drop_official2014prov" drop if official2014prov==1
    if "`restrict'"=="drop_adminstart2014" drop if admin_start_by2014==1

    local first first_`thr'
    local never never_`thr'

    if "`window'"=="w12_14_c2016" {
        keep if inlist(year,2012,2014)
        gen byte treated = (`first'==2016)
        gen byte post = (year==2014)
        gen byte control = 0
        if "`ctrlset'"=="never_only"       replace control = (`never'==1)
        if "`ctrlset'"=="never_plus_next"  replace control = (`never'==1 | `first'==2018)
        if "`ctrlset'"=="next_only"        replace control = (`first'==2018)
    }
    else if "`window'"=="w14_16_c2018" {
        keep if inlist(year,2014,2016)
        gen byte treated = (`first'==2018)
        gen byte post = (year==2016)
        gen byte control = (`never'==1)
    }
    else {
        di as error "Unknown window: `window'"
        exit 198
    }
    keep if treated==1 | control==1
    drop if missing(hid, year, __cid_id)
    gen byte placebo_did = treated*post
end

cap program drop __r3b_key_stats
program define __r3b_key_stats, rclass
    version 17
    syntax , OUTCOME(name)
    tempvar es taghh tagcl tagthh tagtcl tagchh tagccl
    gen byte `es' = e(sample)
    quietly summarize `outcome' if `es', meanonly
    return scalar meandv = r(mean)
    quietly egen byte `taghh' = tag(hid) if `es'
    quietly count if `taghh'==1
    return scalar hh = r(N)
    quietly egen byte `tagcl' = tag(__cid_id) if `es'
    quietly count if `tagcl'==1
    return scalar cl = r(N)
    quietly egen byte `tagthh' = tag(hid) if `es' & treated==1
    quietly count if `tagthh'==1
    return scalar thh = r(N)
    quietly egen byte `tagtcl' = tag(__cid_id) if `es' & treated==1
    quietly count if `tagtcl'==1
    return scalar tcl = r(N)
    quietly egen byte `tagchh' = tag(hid) if `es' & control==1
    quietly count if `tagchh'==1
    return scalar chh = r(N)
    quietly egen byte `tagccl' = tag(__cid_id) if `es' & control==1
    quietly count if `tagccl'==1
    return scalar ccl = r(N)
end

tempname PWILD PAGG
tempfile FWILD FAGG

postfile `PWILD' str16 threshold str14 window str18 ctrlset str24 restriction str18 outcome str12 fespec ///
    double b se p_cluster p_wild long N households clusters treated_hh treated_counties control_hh control_counties using "`FWILD'", replace

postfile `PAGG' str16 threshold str14 window str18 ctrlset str24 restriction str18 outcome ///
    double b se p long N counties treated_counties control_counties using "`FAGG'", replace

foreach THR in completed_t high_sat80_t {
    foreach R in full drop_official2014prov drop_adminstart2014 {
        foreach W in w12_14_c2016 w14_16_c2018 {
            local ctrls never_only
            if "`W'"=="w12_14_c2016" local ctrls never_only never_plus_next next_only
            foreach C of local ctrls {
                foreach Y in any_rentin asinh_rentin {
                    foreach FE in hh_year hh_provyear {
                        use `BASE', clear
                        quietly __r3b_build_sample, thr(`THR') window("`W'") ctrlset("`C'") restrict("`R'")
                        if "`FE'"=="hh_year" local XFE "i.year"
                        if "`FE'"=="hh_provyear" local XFE "i.provyear"
                        cap noisily areg `Y' i.treated##i.post `XFE' if !missing(`Y'), absorb(hid) vce(cluster __cid_id)
                        if _rc continue
                        quietly __r3b_key_stats, outcome(`Y')
                        local __N   = e(N)
                        local __HH  = r(hh)
                        local __CL  = r(cl)
                        local __THH = r(thh)
                        local __TCL = r(tcl)
                        local __CHH = r(chh)
                        local __CCL = r(ccl)
                        tempname b se pc pw
                        scalar `b' = _b[1.treated#1.post]
                        scalar `se' = _se[1.treated#1.post]
                        scalar `pc' = 2*ttail(e(df_r), abs(`b'/`se'))
                        scalar `pw' = .
                        cap noisily boottest 1.treated#1.post, cluster(__cid_id) reps(999) seed(20260502) nograph
                        if !_rc cap scalar `pw' = r(p)
                        post `PWILD' ("`THR'") ("`W'") ("`C'") ("`R'") ("`Y'") ("`FE'") ///
                            (`b') (`se') (`pc') (`pw') (`__N') (`__HH') (`__CL') (`__THH') (`__TCL') (`__CHH') (`__CCL')
                    }

                    use `BASE', clear
                    quietly __r3b_build_sample, thr(`THR') window("`W'") ctrlset("`C'") restrict("`R'")
                    keep if !missing(`Y')
                    collapse (mean) y=`Y' treated post control (count) n=`Y', by(__cid_id year)
                    gen byte placebo_did = treated*post
                    cap noisily reghdfe y i.treated##i.post [aw=n], absorb(__cid_id year) vce(cluster __cid_id)
                    if _rc continue
                    tempvar tagt tagc
                    egen byte `tagt' = tag(__cid_id) if e(sample) & treated==1
                    quietly count if `tagt'==1
                    local tcl = r(N)
                    egen byte `tagc' = tag(__cid_id) if e(sample) & control==1
                    quietly count if `tagc'==1
                    local ccl = r(N)
                    tempname b2 se2 p2
                    scalar `b2' = _b[1.treated#1.post]
                    scalar `se2' = _se[1.treated#1.post]
                    scalar `p2' = 2*ttail(e(df_r), abs(`b2'/`se2'))
                    post `PAGG' ("`THR'") ("`W'") ("`C'") ("`R'") ("`Y'") ///
                        (`b2') (`se2') (`p2') (e(N)) (e(N_clust)) (`tcl') (`ccl')
                }
            }
        }
    }
}

postclose `PWILD'
postclose `PAGG'

use "`FWILD'", clear
sort threshold window ctrlset restriction outcome fespec
export delimited using "`OUTROOT'/tables/Round3_E_key_wild_cluster_placebo.csv", replace

use "`FAGG'", clear
sort threshold window ctrlset restriction outcome
export delimited using "`OUTROOT'/tables/Round3_F_county_aggregate_placebo.csv", replace

log close
exit 0
