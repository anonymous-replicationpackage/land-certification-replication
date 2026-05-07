/********************************************************************
 * 01_globals_and_ado.do - Paths, ADO, and graph settings
 ********************************************************************/
version 17
set more off

local __root = subinstr("`c(pwd)'", char(92), "/", .)
if regexm("`__root'", "/code/stata$") local __root = regexr("`__root'", "/code/stata$", "")
if trim("$ROOT") == "" global ROOT "`__root'"

global DATA "$ROOT/data"
global OUT  "$ROOT/result"
global RAW  "$ROOT/raw data"

if trim("$raw") == ""  global raw  "$RAW"
if trim("$temp") == "" global temp "$DATA"
if trim("$out") == ""  global out  "$OUT"

cap mkdir "$DATA"
cap mkdir "$OUT"
cap mkdir "$RAW"
cap mkdir "$ROOT/ado/plus"
cap mkdir "$ROOT/ado/personal"
sysdir set PLUS     "$ROOT/ado/plus"
sysdir set PERSONAL "$ROOT/ado/personal"
adopath ++ "$ROOT/ado/plus"
adopath ++ "$ROOT/ado/personal"

cap set scheme s2mono
graph set window fontface "Arial"

di as txt ">> 01_globals_and_ado.do ready. ROOT=$ROOT | DATA=$DATA"
