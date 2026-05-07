/********************************************************************
 * 60_topjournal_setup.do - Directory tree for the analysis rebuild
 ********************************************************************/
version 17
set more off
set linesize 255
set varabbrev off

if trim("$ROOT") == "" {
    local __root = subinstr("`c(pwd)'", char(92), "/", .)
    if regexm("`__root'", "/code/stata$") local __root = regexr("`__root'", "/code/stata$", "")
    global ROOT "`__root'"
}
quietly do "$ROOT/code/stata/01_globals_and_ado.do"

global TJDATA   "$ROOT/data/topjournal_rebuild"
global TJOUT    "$ROOT/result/topjournal_rebuild"
global TJADMIN  "$TJDATA/admin"
global TJFOBS   "$TJDATA/fobs"
global TJCLDS   "$TJDATA/clds"
global TJCFPS   "$TJDATA/cfps"
global TJCHIP   "$TJDATA/chip"
global TJTAB    "$TJOUT/tables"
global TJFIG    "$TJOUT/figures"
global TJAUDIT  "$TJOUT/audit"
global TJLOG    "$TJOUT/logs"

if trim("$RESTRICTED_DATA_ROOT") == "" global RESTRICTED_DATA_ROOT "$ROOT/data/raw_private"
global LIBROOT  "$RESTRICTED_DATA_ROOT"
global FOBSROOT "$LIBROOT/fobs"
global CFPSROOT "$LIBROOT/cfps"

foreach d in "$TJDATA" "$TJOUT" "$TJADMIN" "$TJFOBS" "$TJCLDS" "$TJCFPS" "$TJCHIP" "$TJTAB" "$TJFIG" "$TJAUDIT" "$TJLOG" {
    cap mkdir "`d'"
}

di as txt ">> 60_topjournal_setup.do ready. TJDATA=$TJDATA | TJOUT=$TJOUT"
