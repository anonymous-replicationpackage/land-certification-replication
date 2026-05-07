/********************************************************************
* 161_round25_round3_parallel_trends_placebo_20260502.do
*
* Round 3: exhaustive-ish pretrend / placebo exploration for the
* implementation-maturity land-rental results.
*
* Outputs:
*   result/round25_empirical_rebuild_20260502/round3_parallel_trends/
*     audit/Round3_A_preperiod_support.csv
*     tables/Round3_B_preperiod_placebo_did.csv
*     tables/Round3_C_prechange_balance.csv
*     tables/Round3_D_mainpanel_event_leads.csv
*     Round3_ParallelTrends_Memo_20260502.md
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
cap which eventstudyinteract
if _rc ssc install eventstudyinteract, replace

local OUTROOT "$ROOT/result/round25_empirical_rebuild_20260502/round3_parallel_trends"
cap mkdir "$ROOT/result"
cap mkdir "$ROOT/result/round25_empirical_rebuild_20260502"
cap mkdir "`OUTROOT'"
cap mkdir "`OUTROOT'/audit"
cap mkdir "`OUTROOT'/tables"
cap mkdir "`OUTROOT'/logs"
cap log close _all
log using "`OUTROOT'/logs/161_round25_round3_parallel_trends_placebo_20260502.log", replace text

local P12    "$ROOT/data/admin_rollout/CLDS_hh_mechanism_panel_2012_2018_with_admin_rollout.dta"
local P14    "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_indivbridge_20260416.dta"
local ADMIN  "$ROOT/data/topjournal_rebuild/admin/admin_rollout_countyyear_v2.dta"

foreach f in "`P12'" "`P14'" "`ADMIN'" {
    cap confirm file "`f'"
    if _rc {
        di as error "Missing required input: `f'"
        exit 459
    }
}

tempfile BASE14 BASE12 ADMINUSE

preserve
    use "`ADMIN'", clear
    keep county_id_num year county_signedoff_t county_issued_t county_completed_t county_sat_t county_completion_rate
    rename county_id_num __cid_id
    save `ADMINUSE', replace
restore

* ------------------------------------------------------------------
* 1) Build 2012-2018 auxiliary preperiod panel with common anchors
* ------------------------------------------------------------------
use "`P12'", clear
keep if inlist(year,2012,2014,2016,2018)

foreach v in hid year __cid_id __prov_id any_rentin asinh_rentin any_abandon asinh_abandon ///
             admin_started_by_t admin_completed_by_t admin_rollout_start_year admin_sat_detail_t {
    cap confirm variable `v'
    if _rc {
        di as error "P12 panel missing required variable: `v'"
        exit 459
    }
}

cap drop asinh_land_total
gen double asinh_land_total = asinh(land_total_mu_raw) if !missing(land_total_mu_raw)

gen byte started_t    = admin_started_by_t if !missing(admin_started_by_t)
gen byte completed_t  = admin_completed_by_t if !missing(admin_completed_by_t)
gen byte high_sat80_t = (admin_sat_detail_t>=0.8) if !missing(admin_sat_detail_t)

bys __cid_id: egen min_admin_start = min(admin_rollout_start_year)
gen byte official2014prov = inlist(__prov_id, 34, 37, 51)
gen byte admin_start_by2014 = (min_admin_start<=2014) if !missing(min_admin_start)
replace admin_start_by2014 = 0 if missing(admin_start_by2014)

egen long provyear = group(__prov_id year)

foreach THR in started_t completed_t high_sat80_t {
    bys __cid_id: egen first_`THR' = min(cond(`THR'==1, year, .))
    gen byte never_`THR' = missing(first_`THR')
}

compress
save `BASE12', replace

* ------------------------------------------------------------------
* 2) Helpers for placebo samples
* ------------------------------------------------------------------
cap program drop __r3_build_sample
program define __r3_build_sample
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
        gen int target_cohort = 2016
        gen byte control = 0
        if "`ctrlset'"=="never_only"       replace control = (`never'==1)
        if "`ctrlset'"=="never_plus_next"  replace control = (`never'==1 | `first'==2018)
        if "`ctrlset'"=="next_only"        replace control = (`first'==2018)
    }
    else if "`window'"=="w12_14_c2018" {
        keep if inlist(year,2012,2014)
        gen byte treated = (`first'==2018)
        gen byte post = (year==2014)
        gen int target_cohort = 2018
        gen byte control = (`never'==1)
    }
    else if "`window'"=="w14_16_c2018" {
        keep if inlist(year,2014,2016)
        gen byte treated = (`first'==2018)
        gen byte post = (year==2016)
        gen int target_cohort = 2018
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

cap program drop __r3_post_support
program define __r3_post_support
    version 17
    syntax , HANDLE(name) THR(string) WINDOW(string) CTRLSET(string) RESTRICT(string)

    tempvar taghh tagcl tagthh tagtcl tagchh tagccl
    quietly count
    local rows = r(N)
    quietly egen byte `taghh' = tag(hid)
    quietly count if `taghh'==1
    local hh = r(N)
    quietly egen byte `tagcl' = tag(__cid_id)
    quietly count if `tagcl'==1
    local cl = r(N)

    quietly egen byte `tagthh' = tag(hid) if treated==1
    quietly count if `tagthh'==1
    local thh = r(N)
    quietly egen byte `tagtcl' = tag(__cid_id) if treated==1
    quietly count if `tagtcl'==1
    local tcl = r(N)
    quietly egen byte `tagchh' = tag(hid) if control==1
    quietly count if `tagchh'==1
    local chh = r(N)
    quietly egen byte `tagccl' = tag(__cid_id) if control==1
    quietly count if `tagccl'==1
    local ccl = r(N)

    quietly count if treated==1 & post==0
    local tpre = r(N)
    quietly count if treated==1 & post==1
    local tpost = r(N)
    quietly count if control==1 & post==0
    local cpre = r(N)
    quietly count if control==1 & post==1
    local cpost = r(N)

    post `handle' ("`thr'") ("`window'") ("`ctrlset'") ("`restrict'") ///
        (`rows') (`hh') (`cl') (`thh') (`tcl') (`chh') (`ccl') (`tpre') (`tpost') (`cpre') (`cpost')
end

cap program drop __r3_est_did
program define __r3_est_did
    version 17
    syntax , HANDLE(name) THR(string) WINDOW(string) CTRLSET(string) RESTRICT(string) OUTCOME(name) FESPEC(string)

    if "`fespec'"=="hh_year" local ABS "hid year"
    else if "`fespec'"=="hh_provyear" local ABS "hid provyear"
    else {
        di as error "Unknown FE spec: `fespec'"
        exit 198
    }

    cap noisily reghdfe `outcome' i.treated##i.post if !missing(`outcome'), absorb(`ABS') vce(cluster __cid_id)
    if _rc {
        post `handle' ("`thr'") ("`window'") ("`ctrlset'") ("`restrict'") ("`outcome'") ("`fespec'") ///
            (.) (.) (.) (.) (.) (.) (.) (.) (.) (.) (.)
        exit
    }

    tempvar es taghh tagcl tagthh tagtcl tagchh tagccl
    gen byte `es' = e(sample)
    quietly summarize `outcome' if `es', meanonly
    local meandv = r(mean)
    quietly egen byte `taghh' = tag(hid) if `es'
    quietly count if `taghh'==1
    local hh = r(N)
    quietly egen byte `tagcl' = tag(__cid_id) if `es'
    quietly count if `tagcl'==1
    local cl = r(N)
    quietly egen byte `tagthh' = tag(hid) if `es' & treated==1
    quietly count if `tagthh'==1
    local thh = r(N)
    quietly egen byte `tagtcl' = tag(__cid_id) if `es' & treated==1
    quietly count if `tagtcl'==1
    local tcl = r(N)
    quietly egen byte `tagchh' = tag(hid) if `es' & control==1
    quietly count if `tagchh'==1
    local chh = r(N)
    quietly egen byte `tagccl' = tag(__cid_id) if `es' & control==1
    quietly count if `tagccl'==1
    local ccl = r(N)

    tempname b se p
    scalar `b' = .
    scalar `se' = .
    scalar `p' = .
    cap scalar `b' = _b[1.treated#1.post]
    cap scalar `se' = _se[1.treated#1.post]
    cap scalar `p' = 2*ttail(e(df_r), abs(`b'/`se'))

    post `handle' ("`thr'") ("`window'") ("`ctrlset'") ("`restrict'") ("`outcome'") ("`fespec'") ///
        (`b') (`se') (`p') (e(N)) (`hh') (`cl') (`meandv') (`thh') (`tcl') (`chh') (`ccl')
end

cap program drop __r3_prechange
program define __r3_prechange
    version 17
    syntax , HANDLE(name) THR(string) WINDOW(string) CTRLSET(string) RESTRICT(string) OUTCOME(name)

    local preyr = .
    local postyr = .
    if inlist("`window'", "w12_14_c2016", "w12_14_c2018") {
        local preyr 2012
        local postyr 2014
    }
    else if "`window'"=="w14_16_c2018" {
        local preyr 2014
        local postyr 2016
    }

    tempvar ypre ypost tag basegrp
    bys hid: egen double `ypre' = max(cond(year==`preyr', `outcome', .))
    bys hid: egen double `ypost' = max(cond(year==`postyr', `outcome', .))
    egen byte `tag' = tag(hid)
    keep if `tag'==1 & !missing(`ypre', `ypost')
    gen double dy = `ypost' - `ypre'

    quietly summarize `ypre' if treated==1, meanonly
    local mtpre = r(mean)
    quietly summarize `ypost' if treated==1, meanonly
    local mtpost = r(mean)
    quietly summarize dy if treated==1, meanonly
    local mtdy = r(mean)
    quietly count if treated==1
    local nthh = r(N)

    quietly summarize `ypre' if control==1, meanonly
    local mcpre = r(mean)
    quietly summarize `ypost' if control==1, meanonly
    local mcpost = r(mean)
    quietly summarize dy if control==1, meanonly
    local mcdy = r(mean)
    quietly count if control==1
    local nchh = r(N)

    cap noisily regress dy treated, vce(cluster __cid_id)
    tempname b se p
    scalar `b' = .
    scalar `se' = .
    scalar `p' = .
    if !_rc {
        cap scalar `b' = _b[treated]
        cap scalar `se' = _se[treated]
        cap scalar `p' = 2*ttail(e(df_r), abs(`b'/`se'))
    }

    post `handle' ("`thr'") ("`window'") ("`ctrlset'") ("`restrict'") ("`outcome'") ///
        (`mtpre') (`mtpost') (`mtdy') (`mcpre') (`mcpost') (`mcdy') (`b') (`se') (`p') (`nthh') (`nchh')
end

* ------------------------------------------------------------------
* 3) Run auxiliary pre-period placebo DID and prechange balance
* ------------------------------------------------------------------
tempname PSUP PDID PCHG
tempfile FSUP FDID FCHG

postfile `PSUP' str16 threshold str14 window str18 ctrlset str24 restriction ///
    long rows households counties treated_hh treated_counties control_hh control_counties ///
    long treated_pre_rows treated_post_rows control_pre_rows control_post_rows using "`FSUP'", replace

postfile `PDID' str16 threshold str14 window str18 ctrlset str24 restriction str18 outcome str12 fespec ///
    double b se p long N households clusters double meandv long treated_hh treated_counties control_hh control_counties using "`FDID'", replace

postfile `PCHG' str16 threshold str14 window str18 ctrlset str24 restriction str18 outcome ///
    double treated_pre treated_post treated_change control_pre control_post control_change diff_change se p ///
    long treated_hh control_hh using "`FCHG'", replace

local thresholds started_t completed_t high_sat80_t
local outcomes any_rentin asinh_rentin any_abandon asinh_abandon asinh_land_total
local restrictions full drop_official2014prov drop_adminstart2014

foreach THR of local thresholds {
    foreach R of local restrictions {
        foreach W in w12_14_c2016 w12_14_c2018 w14_16_c2018 {
            local ctrls never_only
            if "`W'"=="w12_14_c2016" local ctrls never_only never_plus_next next_only
            foreach C of local ctrls {
                use `BASE12', clear
                quietly __r3_build_sample, thr(`THR') window("`W'") ctrlset("`C'") restrict("`R'")
                quietly count
                if r(N)==0 continue
                quietly __r3_post_support, handle(`PSUP') thr("`THR'") window("`W'") ctrlset("`C'") restrict("`R'")

                foreach Y of local outcomes {
                    cap confirm variable `Y'
                    if _rc continue
                    foreach FE in hh_year hh_provyear {
                        preserve
                            quietly __r3_est_did, handle(`PDID') thr("`THR'") window("`W'") ctrlset("`C'") restrict("`R'") outcome(`Y') fespec("`FE'")
                        restore
                    }
                    preserve
                        quietly __r3_prechange, handle(`PCHG') thr("`THR'") window("`W'") ctrlset("`C'") restrict("`R'") outcome(`Y')
                    restore
                }
            }
        }
    }
}

postclose `PSUP'
postclose `PDID'
postclose `PCHG'

use "`FSUP'", clear
sort threshold window ctrlset restriction
export delimited using "`OUTROOT'/audit/Round3_A_preperiod_support.csv", replace

use "`FDID'", clear
sort threshold window ctrlset restriction outcome fespec
export delimited using "`OUTROOT'/tables/Round3_B_preperiod_placebo_did.csv", replace

use "`FCHG'", clear
sort threshold window ctrlset restriction outcome
export delimited using "`OUTROOT'/tables/Round3_C_prechange_balance.csv", replace

* ------------------------------------------------------------------
* 4) Main-panel event-lead audit for land-rental outcomes
* ------------------------------------------------------------------
use "`P14'", clear
keep if inlist(year,2014,2016,2018)
cap confirm variable s_mech_hh
if _rc gen byte s_mech_hh = 1
merge m:1 __cid_id year using `ADMINUSE', nogen keep(match master)

gen byte signoff_or_issue_t = ((county_signedoff_t==1) | (county_issued_t==1)) if !missing(county_signedoff_t) | !missing(county_issued_t)
gen byte completed_t = county_completed_t if !missing(county_completed_t)
gen byte high_sat80_t = (county_sat_t>=0.8) if !missing(county_sat_t)
cap drop asinh_land_total
gen double asinh_land_total = asinh(land_total_mu_raw) if !missing(land_total_mu_raw)

compress
save `BASE14', replace

tempname PES
tempfile FES
postfile `PES' str12 scope str16 threshold str18 outcome str8 event ///
    double b se p long N households clusters double meandv long cohort2016_hh cohort2018_hh never_hh using "`FES'", replace

foreach SCOPE in mech adjacent {
    foreach THR in signoff_or_issue_t completed_t high_sat80_t {
        use `BASE14', clear
        if "`SCOPE'"=="mech" keep if s_mech_hh==1
        if "`SCOPE'"=="adjacent" keep if timing_adjacent_hh==1

        bys __cid_id: egen first_thr = min(cond(`THR'==1, year, .))
        gen byte never_thr = missing(first_thr)
        keep if never_thr==1 | inlist(first_thr,2016,2018)

        gen reltime = year - first_thr if !missing(first_thr)
        cap drop rt_m4 rt_0 rt_p2
        gen byte rt_m4 = (reltime==-4) if !missing(reltime)
        gen byte rt_0  = (reltime==0)  if !missing(reltime)
        gen byte rt_p2 = (reltime==2)  if !missing(reltime)

        foreach Y in any_rentin asinh_rentin any_abandon asinh_abandon asinh_land_total {
            cap confirm variable `Y'
            if _rc continue
            cap noisily eventstudyinteract `Y' rt_m4 rt_0 rt_p2 if !missing(`Y'), ///
                absorb(hid year) cohort(first_thr) control_cohort(never_thr) vce(cluster __cid_id)
            if _rc {
                post `PES' ("`SCOPE'") ("`THR'") ("`Y'") ("failed") ///
                    (.) (.) (.) (.) (.) (.) (.) (.) (.) (.)
                continue
            }

            tempvar es taghh tagcl tag16 tag18 tagnv
            gen byte `es' = e(sample)
            quietly summarize `Y' if `es', meanonly
            local meandv = r(mean)
            quietly egen byte `taghh' = tag(hid) if `es'
            quietly count if `taghh'==1
            local hh = r(N)
            quietly egen byte `tagcl' = tag(__cid_id) if `es'
            quietly count if `tagcl'==1
            local cl = r(N)
            quietly egen byte `tag16' = tag(hid) if `es' & first_thr==2016
            quietly count if `tag16'==1
            local hh16 = r(N)
            quietly egen byte `tag18' = tag(hid) if `es' & first_thr==2018
            quietly count if `tag18'==1
            local hh18 = r(N)
            quietly egen byte `tagnv' = tag(hid) if `es' & never_thr==1
            quietly count if `tagnv'==1
            local hhnv = r(N)

            matrix B = e(b_iw)
            matrix V = e(V_iw)
            mata: st_matrix("R3SE__", sqrt(diagonal(st_matrix("V"))))
            matrix R3SE__ = R3SE__'
            matrix colnames B = rt_m4 rt_0 rt_p2
            matrix colnames R3SE__ = rt_m4 rt_0 rt_p2

            foreach EV in rt_m4 rt_0 rt_p2 {
                tempname bb ss pp
                scalar `bb' = B[1, "`EV'"]
                scalar `ss' = R3SE__[1, "`EV'"]
                scalar `pp' = 2*normal(-abs(`bb'/`ss'))
                post `PES' ("`SCOPE'") ("`THR'") ("`Y'") ("`EV'") ///
                    (`bb') (`ss') (`pp') (e(N)) (`hh') (`cl') (`meandv') (`hh16') (`hh18') (`hhnv')
            }
        }
    }
}

postclose `PES'

use "`FES'", clear
sort scope threshold outcome event
export delimited using "`OUTROOT'/tables/Round3_D_mainpanel_event_leads.csv", replace

* ------------------------------------------------------------------
* 5) Minimal machine-readable memo shell. Interpretive memo is updated
*    after inspecting outputs.
* ------------------------------------------------------------------
tempname FH
cap file close `FH'
file open `FH' using "`OUTROOT'/Round3_ParallelTrends_Memo_20260502.md", write text replace
file write `FH' "# Round 3 memo shell: parallel trends / pre-support" _n _n
file write `FH' "Generated: `c(current_date)' `c(current_time)'" _n _n
file write `FH' "Inputs:" _n
file write `FH' "- `P12'" _n
file write `FH' "- `P14'" _n
file write `FH' "- `ADMIN'" _n _n
file write `FH' "Outputs:" _n
file write `FH' "- audit/Round3_A_preperiod_support.csv" _n
file write `FH' "- tables/Round3_B_preperiod_placebo_did.csv" _n
file write `FH' "- tables/Round3_C_prechange_balance.csv" _n
file write `FH' "- tables/Round3_D_mainpanel_event_leads.csv" _n
file close `FH'

log close
exit 0
