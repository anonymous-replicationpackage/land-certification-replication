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

local OUT "$ROOT/result/round25_empirical_rebuild_20260501/round2b_deeper_a3_exploration"
cap mkdir "$ROOT/result"
cap mkdir "$ROOT/result/round25_empirical_rebuild_20260501"
cap mkdir "`OUT'"
cap mkdir "`OUT'/audit"
cap mkdir "`OUT'/logs"

cap log close _all
log using "`OUT'/logs/157_round25_round2b_probe_labels_20260502.log", replace text

local PANEL   "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_indivbridge_20260416.dta"
local RGPANEL "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_rightsgap_20260415.dta"

di as txt "=== RGPANEL DESCRIBE RIGHTS-GAP VARIABLES ==="
use "`RGPANEL'", clear
describe base14_rg_* base14_* pre12_rg_*
codebook base14_rg_readjust base14_rg_disp_newpop base14_rg_disp_women ///
    base14_rg_readj_reason base14_rg_readj_method base14_rg_noreadj_reason ///
    base14_rg_abs_idle base14_rg_abs_proxy base14_rg_abs_rent base14_rg_abs_share ///
    base14_rg_req_any base14_rg_govrent_any base14_rg_daigeng_any base14_rg_transfer_kin ///
    base14_instab_sum base14_absorg_sum base14_external_sum base14_broad_z pre12_rg_pretransfer_sum, compact

foreach v in base14_rg_readj_reason base14_rg_readj_method base14_rg_noreadj_reason {
    di as txt "=== label for `v' ==="
    local L : value label `v'
    di as txt "value label: `L'"
    if "`L'" != "" label list `L'
    tab `v', missing
}

di as txt "=== RAW COMMUNITY 2014 VALUE LABELS FOR C15/C16 ==="
cap use "$ROOT/raw data/community2014.dta", clear
if _rc {
    cap use "$ROOT/data/comm2014_fixed.dta", clear
}
if !_rc {
    describe C15 C15_1 C15_2 C15_3 C15_4 C16 C17_1 C17_2 C17_3 C18 C22 C23 C23_0
    foreach v in C15 C15_1 C15_2 C15_3 C15_4 C16 C18 C22 C23 C23_0 {
        di as txt "=== raw label for `v' ==="
        local L : value label `v'
        di as txt "value label: `L'"
        if "`L'" != "" label list `L'
        tab `v', missing
    }
}

di as txt "=== PANEL ALL VARIABLES OF INTEREST ==="
use "`PANEL'", clear
describe

preserve
    clear
    set obs 0
    gen str80 name = ""
    gen str244 label = ""
    gen str20 storage = ""
    tempfile dict
    save `dict', replace
restore

ds
local allvars `r(varlist)'
foreach v of local allvars {
    local vl : variable label `v'
    local ty : type `v'
    preserve
        use `dict', clear
        set obs `=_N+1'
        replace name = "`v'" in L
        replace label = "`vl'" in L
        replace storage = "`ty'" in L
        save `dict', replace
    restore
}
use `dict', clear
gen str244 hit = lower(name + " " + label)
keep if strpos(hit,"land") | strpos(hit,"rent") | strpos(hit,"farm") | strpos(hit,"agri") | ///
    strpos(hit,"cert") | strpos(hit,"迁") | strpos(hit,"农") | strpos(hit,"地") | ///
    strpos(hit,"labor") | strpos(hit,"work") | strpos(hit,"income") | strpos(hit,"area") | ///
    strpos(hit,"流转") | strpos(hit,"确权") | strpos(hit,"耕") | strpos(hit,"adjust") | ///
    strpos(hit,"birth") | strpos(hit,"child")
drop hit
export delimited using "`OUT'/audit/Round2B_A0_panel_variable_dictionary_hits.csv", replace

log close
