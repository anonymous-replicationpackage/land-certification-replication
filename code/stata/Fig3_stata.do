*===============================================================================
* Fig. 3: Geographic distribution of LCP rollout in the analytic sample
* Local figure rendering script
* Output: Fig3.pdf (vector) + Fig3.png (300 dpi)
*===============================================================================

clear all
set more off
version 17

local __root = subinstr("`c(pwd)'", char(92), "/", .)
if regexm("`__root'", "/code/stata$") local __root = regexr("`__root'", "/code/stata$", "")
if trim("$ROOT") == "" global ROOT "`__root'"

global globaldir "$ROOT/outputs/figures"
global mapdir    "$ROOT/data/derived/map_inputs"
global outdir    "$globaldir"
cap mkdir "$outdir"
cd "$globaldir"

cap which spmap
if _rc ssc install spmap, replace
cap which shp2dta
if _rc ssc install shp2dta, replace
cap which palettes
if _rc ssc install palettes, replace
cap which colrspace
if _rc ssc install colrspace, replace

*-------------------------------------------------------------------------------
* 1. Convert county/city/province shapefiles
*-------------------------------------------------------------------------------

foreach layer in county city province dash {
    local src = cond("`layer'" == "county", "china_county", ///
              cond("`layer'" == "city", "china_city", ///
              cond("`layer'" == "province", "china_province", "ten_dash")))
    cap erase "$mapdir/`src'.dta"
    cap erase "$mapdir/`src'_coord.dta"
    shp2dta using "$mapdir/`src'.shp", ///
        database("$mapdir/`src'.dta") ///
        coordinates("$mapdir/`src'_coord.dta") ///
        genid(_id_`layer') replace
}

*-------------------------------------------------------------------------------
* 2. Harmonize shapefile code fields
*-------------------------------------------------------------------------------

use "$mapdir/china_county.dta", clear
cap confirm variable county_code
if _rc {
    cap rename PAC county_code
}
cap confirm string variable county_code
if _rc tostring county_code, replace force
replace county_code = substr("000000" + county_code, length("000000" + county_code) - 5, 6)
save "$mapdir/china_county.dta", replace

use "$mapdir/china_city.dta", clear
cap confirm variable city_code
if _rc {
    cap rename 市代码 city_code
}
cap confirm string variable city_code
if _rc tostring city_code, replace force
replace city_code = substr("000000" + city_code, length("000000" + city_code) - 5, 6)
save "$mapdir/china_city.dta", replace

use "$mapdir/china_province.dta", clear
cap confirm variable prov_code
if _rc {
    cap rename 省代码 prov_code
}
cap confirm string variable prov_code
if _rc tostring prov_code, replace force
replace prov_code = substr("000000" + prov_code, length("000000" + prov_code) - 5, 6)
save "$mapdir/china_province.dta", replace

*-------------------------------------------------------------------------------
* 3. Compute polygon centroids for county, city, and province fallback positions
*-------------------------------------------------------------------------------

use "$mapdir/china_county_coord.dta", clear
drop if _X == . | _Y == .
drop if _ID < 0
collapse (mean) _X _Y, by(_ID)
rename _ID _id_county
merge 1:1 _id_county using "$mapdir/china_county.dta", keepusing(county_code) keep(match) nogen
rename _X cen_x_county
rename _Y cen_y_county
keep county_code cen_x_county cen_y_county
collapse (mean) cen_x_county cen_y_county, by(county_code)
save "$mapdir/_county_centroids.dta", replace

use "$mapdir/china_city_coord.dta", clear
drop if _X == . | _Y == .
drop if _ID < 0
collapse (mean) _X _Y, by(_ID)
rename _ID _id_city
merge 1:1 _id_city using "$mapdir/china_city.dta", keepusing(city_code) keep(match) nogen
rename _X cen_x_city
rename _Y cen_y_city
keep city_code cen_x_city cen_y_city
collapse (mean) cen_x_city cen_y_city, by(city_code)
save "$mapdir/_city_centroids.dta", replace

use "$mapdir/china_province_coord.dta", clear
drop if _X == . | _Y == .
drop if _ID < 0
collapse (mean) _X _Y, by(_ID)
rename _ID _id_province
merge 1:1 _id_province using "$mapdir/china_province.dta", keepusing(prov_code) keep(match) nogen
rename _X cen_x_prov
rename _Y cen_y_prov
keep prov_code cen_x_prov cen_y_prov
collapse (mean) cen_x_prov cen_y_prov, by(prov_code)
save "$mapdir/_province_centroids.dta", replace

*-------------------------------------------------------------------------------
* 4. Build the analytic county dot layer
*    Exact county centroids are used first. CLDS contains many municipal-district
*    aggregate codes absent from the county shapefile; these use city/province
*    fallback centroids with a small deterministic jitter so all 349 counties draw.
*-------------------------------------------------------------------------------

use "$mapdir/county_treatment.dta", clear
cap confirm string variable county_code
if _rc tostring county_code, replace force
replace county_code = substr("000000" + county_code, length("000000" + county_code) - 5, 6)
replace completed_yr = . if completed_yr < 2014 | completed_yr > 2018

merge 1:1 county_code using "$mapdir/_county_centroids.dta", nogen keep(master match)
gen byte geo_match = !missing(cen_x_county)

gen str6 city_code = substr(county_code, 1, 4) + "00"
merge m:1 city_code using "$mapdir/_city_centroids.dta", nogen keep(master match)
gen str6 prov_code = substr(county_code, 1, 2) + "0000"
merge m:1 prov_code using "$mapdir/_province_centroids.dta", nogen keep(master match)

gen cen_x = cen_x_county
gen cen_y = cen_y_county
replace cen_x = cen_x_city if missing(cen_x)
replace cen_y = cen_y_city if missing(cen_y)
replace cen_x = cen_x_prov if missing(cen_x)
replace cen_y = cen_y_prov if missing(cen_y)

gen byte fallback = geo_match == 0
bysort city_code fallback (county_code): gen _j = _n if fallback
replace cen_x = cen_x + (mod(_j - 1, 5) - 2) * 0.08 if fallback & _j < .
replace cen_y = cen_y + (floor((_j - 1) / 5) - 2) * 0.08 if fallback & _j < .

gen byte cat = .
replace cat = 1 if in_analytic == 1 & missing(completed_yr)
replace cat = 2 if in_analytic == 1 & completed_yr > 2016 & completed_yr <= 2018
replace cat = 3 if in_analytic == 1 & completed_yr <= 2016
label define catlbl 1 "Not completed by 2018" 2 "Completed 2017-2018" 3 "Completed 2014-2016"
label values cat catlbl

qui count if cat == 1
local n1 = r(N)
qui count if cat == 2
local n2 = r(N)
qui count if cat == 3
local n3 = r(N)
qui count if !missing(cat)
local nT = r(N)
qui count if fallback == 0 & !missing(cat)
local nexact = r(N)
qui count if fallback == 1 & !missing(cat)
local nfallback = r(N)

di as result "Analytic sample counts: Not completed = `n1'; 2017-2018 = `n2'; 2014-2016 = `n3'; total = `nT'"
di as result "Geographic matching: exact county = `nexact'; city/province fallback = `nfallback'"

label define catlbl 1 "Not completed by 2018 (n=`n1')" ///
                    2 "Completed 2017-2018 (n=`n2')" ///
                    3 "Completed 2014-2016 (n=`n3')", modify

keep county_code completed_yr in_analytic cat cen_x cen_y fallback
save "$mapdir/_centroids.dta", replace

*-------------------------------------------------------------------------------
* 5. Draw the map
*-------------------------------------------------------------------------------

use "$mapdir/china_county.dta", clear

local color_notcomp  "153 153 153"
local color_2017_18  "127 188 224"
local color_2014_16  "31 78 139"

spmap using "$mapdir/china_county_coord.dta", ///
    id(_id_county) ///
    fcolor(gs15) ///
    ocolor(gs13 ..) osize(0.025 ..) ///
    line(data("$mapdir/ten_dash_coord.dta") ///
         color(gs9) size(0.16) pattern(dash) legenda(off)) ///
    point(data("$mapdir/_centroids.dta") xcoord(cen_x) ycoord(cen_y) ///
          by(cat) ///
          fcolor("`color_notcomp'" "`color_2017_18'" "`color_2014_16'") ///
          ocolor("`color_notcomp'" "`color_2017_18'" "`color_2014_16'") ///
          size(0.45 0.65 0.65) ///
          shape(O O O) ///
          legenda(on)) ///
    legend(position(7) ring(0) size(vsmall) symxsize(*0.6) region(lcolor(none) fcolor(none))) ///
    plotregion(margin(zero)) ///
    graphregion(color(white) margin(small)) ///
    note("Estimation samples: 139 counties (mechanism), 134 counties (adjacent).", ///
         size(tiny) position(6)) ///
    name(fig3, replace)

*-------------------------------------------------------------------------------
* 6. Export to PDF and PNG (300 dpi)
*-------------------------------------------------------------------------------

graph export "$outdir/Fig3.pdf", replace
graph export "$outdir/Fig3.png", replace width(2720)

di as result "Done. Figure saved to: $outdir/Fig3.pdf and Fig3.png"

* Final journal layout: Stata has prepared the shapefile conversions and dot
* layer above; the renderer below places the South China Sea / nine-dash line
* in a conventional inset so the main map extent stays compact.
shell python "render_fig3_with_scs_inset_20260503.py"
di as result "Inset-rendered Fig3.pdf and Fig3.png overwritten in: $outdir"

* Keep intermediate .dta files for audit and reproducibility.
