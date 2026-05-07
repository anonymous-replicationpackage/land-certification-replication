/********************************************************************
* 63_admin_rebuild_countyyear_v2.do
*
* Rebuild the county-year rollout panel for the top-journal track.
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

quietly do "$ROOT/code/stata/01_globals_and_ado.do"
quietly do "$ROOT/code/stata/60_topjournal_setup.do"

tempname FH
cap file close `FH'
file open `FH' using "$TJLOG/63_admin_rebuild_countyyear_v2.log", write text replace
file write `FH' "Admin county-year rebuild" _n
file write `FH' "Date: `c(current_date)' Time: `c(current_time)'" _n

local ENRICHED "$ROOT/raw data/admin_rollout/admin_rollout_countyyear_enriched_v2.csv"
local FALLBACK "$ROOT/data/admin_rollout/admin_rollout_countyyear_standardized.dta"
local RAWCSV   "$ROOT/raw data/admin_rollout/admin_rollout_countyyear.csv"

if fileexists("`ENRICHED'") {
    import delimited using "`ENRICHED'", clear stringcols(_all) varnames(1)
    file write `FH' "Source used: enriched raw csv" _n
}
else if fileexists("`FALLBACK'") {
    use "`FALLBACK'", clear
    rename admin_county_id county_id_num
    rename admin_year year
    rename admin_rollout_start_year county_start_year
    rename admin_rollout_complete_year county_complete_year
    rename admin_completion_rate county_completion_rate
    capture rename admin_prov_id prov_id
    capture rename admin_county_name county_name
    capture rename admin_prov_name prov_name
    file write `FH' "Source used: fallback standardized dta" _n
}
else if fileexists("`RAWCSV'") {
    import delimited using "`RAWCSV'", clear stringcols(_all) varnames(0)
    drop if v1 == "省份"
    rename v1 prov_name
    rename v2 prov_id
    rename v3 county_name
    rename v4 county_id_num
    rename v5 year
    rename v6 county_start_year
    rename v7 county_complete_year
    rename v8 county_completion_rate
    file write `FH' "Source used: raw csv with positional parsing" _n
}
else {
    file write `FH' "No admin rollout source available." _n
    file close `FH'
    error 601
}

foreach v in county_id_num year county_start_year county_complete_year county_completion_rate prov_id ///
    county_pilot_year county_rollout_start_year county_signoff_year county_issue_year county_review_year ///
    county_pilot_to_signoff_span county_pilot_to_complete_span {
    capture confirm variable `v'
    if !_rc capture destring `v', replace force
}

foreach v in county_pilot_to_signoff_span county_pilot_to_complete_span {
    capture confirm variable `v'
    if _rc gen double `v' = .
}

capture confirm variable county_completion_rate
if !_rc {
    gen double county_sat_t = .
    replace county_sat_t = county_completion_rate/100 if county_completion_rate > 1 & county_completion_rate <= 100
    replace county_sat_t = county_completion_rate if county_completion_rate >= 0 & county_completion_rate <= 1
}
else gen double county_sat_t = .

gen byte county_started_t   = year >= county_start_year if !missing(year, county_start_year)
gen byte county_completed_t = year >= county_complete_year if !missing(year, county_complete_year)
capture gen byte county_signedoff_t = year >= county_signoff_year if !missing(year, county_signoff_year)
capture gen byte county_issued_t    = year >= county_issue_year if !missing(year, county_issue_year)
capture gen byte county_reviewed_t  = year >= county_review_year if !missing(year, county_review_year)
replace county_sat_t = county_completed_t if missing(county_sat_t) & !missing(county_completed_t)
replace county_sat_t = 0 if missing(county_sat_t) & county_started_t == 1
replace county_sat_t = 0 if missing(county_sat_t) & year < county_start_year & !missing(county_start_year)

capture confirm variable county_id
if _rc {
    gen str6 county_id = string(county_id_num, "%06.0f") if !missing(county_id_num)
}
else {
    replace county_id = string(county_id_num, "%06.0f") if missing(county_id) & !missing(county_id_num)
}

keep county_id county_id_num year prov_id county_start_year county_complete_year ///
    county_pilot_year county_rollout_start_year county_signoff_year county_issue_year county_review_year ///
    county_pilot_to_signoff_span county_pilot_to_complete_span ///
    county_completion_rate county_progress_metric_type n_township_impute ///
    county_started_t county_completed_t county_signedoff_t ///
    county_issued_t county_reviewed_t county_sat_t county_name prov_name
duplicates drop county_id_num year, force
sort county_id_num year

save "$TJADMIN/admin_rollout_countyyear_v2.dta", replace

preserve
    collapse (firstnm) county_id prov_id county_name prov_name county_pilot_year county_rollout_start_year ///
        county_start_year county_signoff_year county_issue_year county_review_year county_complete_year ///
        county_pilot_to_signoff_span county_pilot_to_complete_span, by(county_id_num)
    save "$TJADMIN/admin_rollout_county_v2.dta", replace
restore

export delimited using "$TJAUDIT/AdminCoverage_FOBS_v2.csv", replace

quietly count
file write `FH' "County-year rows: " %12.0fc (r(N)) _n
quietly count if !missing(county_start_year)
file write `FH' "Rows with start year: " %12.0fc (r(N)) _n
quietly count if !missing(county_complete_year)
file write `FH' "Rows with complete year: " %12.0fc (r(N)) _n
capture quietly count if !missing(county_signoff_year)
capture file write `FH' "Rows with signoff year: " %12.0fc (r(N)) _n
capture quietly count if !missing(county_issue_year)
capture file write `FH' "Rows with issue year: " %12.0fc (r(N)) _n
capture quietly count if !missing(county_review_year)
capture file write `FH' "Rows with review year: " %12.0fc (r(N)) _n
file close `FH'

di as txt "Wrote $TJADMIN/admin_rollout_countyyear_v2.dta"
