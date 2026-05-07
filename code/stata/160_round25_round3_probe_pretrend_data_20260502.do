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

local OUT "$ROOT/result/round25_empirical_rebuild_20260502/round3_parallel_trends"
cap mkdir "$ROOT/result"
cap mkdir "$ROOT/result/round25_empirical_rebuild_20260502"
cap mkdir "`OUT'"
cap mkdir "`OUT'/audit"
cap mkdir "`OUT'/logs"

cap log close _all
log using "`OUT'/logs/160_round25_round3_probe_pretrend_data_20260502.log", replace text

local P12 "$ROOT/data/admin_rollout/CLDS_hh_mechanism_panel_2012_2018_with_admin_rollout.dta"
local P14 "$ROOT/data/topjournal_rebuild/clds/CLDS_hh_mechanism_panel_with_indivbridge_20260416.dta"

foreach P in P12 P14 {
    di as txt "=== DATASET ``P'' ==="
    use "``P''", clear
    describe, short
    describe, fullnames
    local inspect_vars hid pid year __cid_id village_id s_mech_hh timing_adjacent_hh first_treat never_treat Cert_h ///
        any_rentin asinh_rentin rentin_mu any_rentout asinh_rentout rentout_mu ///
        any_abandon asinh_abandon abandon_mu land_total_mu contracted_land_mu ///
        admin_rollout_start_year admin_completion_year
    foreach v of local inspect_vars {
        cap describe `v', fullnames
        if _rc di as error "MISSING VARIABLE: `v'"
    }
    tab year, missing
    foreach y in any_rentin asinh_rentin rentin_mu any_rentout asinh_rentout rentout_mu any_abandon asinh_abandon abandon_mu land_total_mu contracted_land_mu {
        cap confirm variable `y'
        if !_rc {
            di as txt "=== outcome support: `y' ==="
            tab year if !missing(`y'), missing
            quietly summarize `y' if !missing(`y')
            di as result "N=" r(N) " mean=" r(mean) " sd=" r(sd)
        }
    }
    foreach s in s_mech_hh timing_adjacent_hh s_event s_event_adjattack {
        cap confirm variable `s'
        if !_rc {
            di as txt "=== sample marker: `s' ==="
            tab year `s', missing
        }
    }
}

log close
