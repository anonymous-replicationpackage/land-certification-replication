*===============================================================================
* Fig. 4: Event-study coefficients on asinh rented-in area
*-------------------------------------------------------------------------------
* Manuscript : "Land certification, implementation progress, and farmland
*               rental: Evidence from China"
* Target     : China Agricultural Economic Review
* Output     : Fig4.pdf (vector) and Fig4.png (300 dpi)
* Stata 17+
*===============================================================================
*
* WHAT THIS CODE DOES
* -------------------
* Two-panel side-by-side event-study plot, one panel per threshold:
*   Left  panel : Completion         (mature implementation, headline)
*   Right panel : High-saturation    (alternative mature implementation)
*
* In each panel, two series:
*   Lower-instability subgroup  (open circles, solid line, blue)
*   High-instability subgroup   (filled squares, dashed line, red)
*
* x-axis: event time k = -4, -2 (ref.), 0, +2
* y-axis: event-study coefficient on asinh rented-in area
* Reference period k = -2 plotted as a hollow square at y = 0 (no CI bar)
*
* TWO MODES OF USE
* ----------------
* MODE A (recommended): Plot from your own estimated coefficients.
*        Run your event-study regressions, store the coefficients as a
*        small dataset, and the code will plot them.
*
* MODE B: Use the published Table S6 coefficients hard-coded below as a
*        fallback if you only need a placeholder figure.
*
* Choose by setting the local `mode' below to "A" or "B".
*
* SAMPLE
* ------
* The figure uses the MECHANISM sample (3,024 obs, 139 counties).
* Table S6 also reports adjacent-sample numbers; switch the input
* dataset / locals if you want the adjacent version.
*
*===============================================================================

clear all
set more off
version 17

local mode "B"            // Mode B uses Online Appendix Table S6 coefficients

local __root = subinstr("`c(pwd)'", char(92), "/", .)
if regexm("`__root'", "/code/stata$") local __root = regexr("`__root'", "/code/stata$", "")
if trim("$ROOT") == "" global ROOT "`__root'"

global globaldir "$ROOT/outputs/figures"
global outdir    "$globaldir"
cap mkdir "$outdir"
cd       "$globaldir"

cap log close _all
log using "$globaldir/Fig4_stata.log", replace text

*-------------------------------------------------------------------------------
* MODE A. Plot from your own event-study estimation
*-------------------------------------------------------------------------------
*
* Workflow assumed:
*   1. Run your stacked event-study regression for each (threshold x subgroup)
*      combination. The estimating equation is the event-study analog of
*      Eq. (3) in the manuscript, with k in {-4, 0, +2} (omit k = -2):
*
*        reghdfe Y                                                         ///
*            (k_neg4 k_zero k_pos2) (k_neg4_M k_zero_M k_pos2_M)            ///
*            ,  absorb(hh_id stack_year)  cluster(county_id)
*
*      where the second triple is k indicators interacted with the moderator.
*      The coefficients on the first triple recover the lower-instability
*      response; the lower + interaction sums recover the high-instability
*      response.
*
*   2. After each regression, append point estimates and SEs to a results
*      dataset with columns: threshold subgroup k b se
*
*   3. Save as Fig4_coefs.dta (variables threshold subgroup k b se).
*
* Skeleton code below (UNCOMMENT and adapt to your variable names):
*
* /*
* use "$globaldir/your_event_study_panel.dta", clear
*
* tempfile results
* save `results', emptyok
*
* foreach thresh in completion high_sat {
*     foreach grp in lower high {
*         use "$globaldir/your_event_study_panel.dta", clear
*         keep if treatment_type == "`thresh'" & subgroup == "`grp'"
*
*         reghdfe asinh_rentin                                              ///
*             k_neg4 k_zero k_pos2,                                         ///
*             absorb(hh_id stack_year)                                      ///
*             cluster(county_id)
*
*         foreach k in -4 0 2 {
*             local v = cond(`k' == -4, "k_neg4",                           ///
*                       cond(`k' ==  0, "k_zero", "k_pos2"))
*             local b  = _b[`v']
*             local se = _se[`v']
*             post `using_results' ("`thresh'") ("`grp'") (`k') (`b') (`se')
*         }
*     }
* }
* */

if "`mode'" == "A" {
    use "$globaldir/Fig4_coefs.dta", clear
    cap confirm variable threshold
    if _rc {
        di as error ///
        "Fig4_coefs.dta must contain: threshold subgroup k b se"
        exit 198
    }
}

*-------------------------------------------------------------------------------
* MODE B. Use the published Table S6 coefficients (mechanism sample)
*-------------------------------------------------------------------------------

if "`mode'" == "B" {
    clear
    input str20 threshold str10 subgroup k b se
        "Completion"     "Lower"  -4  0.039  0.085
        "Completion"     "Lower"  -2  0.000  0.000
        "Completion"     "Lower"   0  0.314  0.111
        "Completion"     "Lower"   2  0.420  0.144
        "Completion"     "High"   -4  0.224  0.137
        "Completion"     "High"   -2  0.000  0.000
        "Completion"     "High"    0  0.498  0.149
        "Completion"     "High"    2  0.621  0.180
        "High-saturation" "Lower" -4  0.037  0.084
        "High-saturation" "Lower" -2  0.000  0.000
        "High-saturation" "Lower"  0  0.302  0.108
        "High-saturation" "Lower"  2  0.412  0.141
        "High-saturation" "High"  -4  0.219  0.135
        "High-saturation" "High"  -2  0.000  0.000
        "High-saturation" "High"   0  0.490  0.146
        "High-saturation" "High"   2  0.613  0.177
    end
}

*-------------------------------------------------------------------------------
* 1. Compute 95% CI bounds; the reference period (k = -2) gets no CI
*-------------------------------------------------------------------------------

gen lo = b - 1.96 * se
gen hi = b + 1.96 * se
replace lo = . if k == -2
replace hi = . if k == -2

* Small horizontal jitter so the two series do not overlap exactly at k
gen kj = k + cond(subgroup == "Lower", -0.10, 0.10)

*-------------------------------------------------------------------------------
* 2. Build the plot
*-------------------------------------------------------------------------------

* Color choices: blue for Lower-instability, red for High-instability
* Hex equivalents:  Lower #1F77B4   High #D62728
* Stata 17+ supports inline RGB; we use these:
local cLower "0 78 156"     // dark blue
local cHigh  "164 41 41"    // dark red

* Marker for reference period (k = -2): hollow square at y = 0
* Plot data: separate the reference period as its own scatter for "ref. point" appearance.

* Convenience: encode threshold for paneling
encode threshold, gen(thr_id)
label define thrlbl 1 "Completion" 2 "High-saturation"
label values thr_id thrlbl

* Threshold-crossing indicator at k = 0 (vertical dotted line)
* — drawn via xline()

twoway                                                                          ///
    /* Lower-instability series — solid line, open circle, with CI bars */     ///
    (rcap hi lo kj if subgroup == "Lower" & k != -2,                            ///
        lcolor("`cLower'") lwidth(medthin)                                      ///
        msize(small))                                                           ///
    (connected b kj if subgroup == "Lower" & k != -2,                           ///
        lcolor("`cLower'") lpattern(solid) lwidth(medthick)                     ///
        msymbol(Oh) mcolor("`cLower'") msize(medlarge) sort)                    ///
    /* Lower-instability reference at k = -2 (hollow square at 0) */            ///
    (scatter b kj if subgroup == "Lower" & k == -2,                             ///
        msymbol(Sh) mcolor("`cLower'") msize(medium))                           ///
    /* High-instability series — dashed line, filled square, with CI bars */   ///
    (rcap hi lo kj if subgroup == "High" & k != -2,                             ///
        lcolor("`cHigh'") lwidth(medthin)                                       ///
        msize(small))                                                           ///
    (connected b kj if subgroup == "High" & k != -2,                            ///
        lcolor("`cHigh'") lpattern(dash) lwidth(medthick)                       ///
        msymbol(S) mcolor("`cHigh'") msize(medium) sort)                        ///
    /* High-instability reference at k = -2 (hollow square at 0) */             ///
    (scatter b kj if subgroup == "High" & k == -2,                              ///
        msymbol(Sh) mcolor("`cHigh'") msize(medium)),                           ///
    by(thr_id, note("") graphregion(color(white))                               ///
        cols(2) iscale(0.82))                                                   ///
    legend(position(6) ring(1) rows(1) size(small)                               ///
           region(lcolor(none) fcolor(none))                                    ///
           order(2 "Lower-instability" 5 "High-instability"))                  ///
    xline(0, lpattern(dot) lcolor(gs10) lwidth(thin))                           ///
    yline(0, lcolor(gs10) lwidth(vthin))                                        ///
    xtitle("Event time k (years from threshold crossing)", size(small))         ///
    ytitle("Event-study coefficient (asinh rented-in area)", size(small))       ///
    xlabel(-4 "{&minus}4" -2 `" "{&minus}2" "(ref.)" "' 0 "0" 2 "+2",           ///
           grid labsize(small))                                                 ///
    ylabel(-0.2(0.2)1.0, angle(horizontal) format(%4.1f) labsize(small))        ///
    plotregion(margin(small))                                                   ///
    graphregion(color(white) margin(small))                                     ///
    xsize(7.8) ysize(4.8)                                                       ///
    name(fig4, replace)

*-------------------------------------------------------------------------------
* 3. Export
*-------------------------------------------------------------------------------

graph export "$outdir/Fig4.pdf", replace
graph export "$outdir/Fig4.png", replace width(2720)

di as result "Done. Figure saved to: $outdir/Fig4.pdf and Fig4.png"

log close

*===============================================================================
* TROUBLESHOOTING
*===============================================================================
* Q1. "Two series overlap exactly at the same x"
*     -> The horizontal jitter `kj' offsets each series by 0.10 from the
*        nominal k value. If you want no jitter, set `kj' = `k' directly.
*
* Q2. "Reference square (k = -2) shows two markers, one per series"
*     -> By design, both series have a hollow square at k = -2, slightly
*        offset, indicating the reference period for each subgroup. To
*        collapse to a single shared reference marker, replace the
*        two scatter calls for k == -2 with one centered marker at k = -2.
*
* Q3. "x-axis labels look truncated when -4 is shown as plain hyphen"
*     -> The minus sign in xlabel uses the Unicode minus (&minus;) for
*        typographic correctness. If your Stata version does not render
*        that glyph, replace `"{&minus}4"' with `"-4"' (plain hyphen).
*
* Q4. "Confidence intervals are too narrow / too wide compared to R5"
*     -> Make sure you are using the correct sample. Table S6 reports
*        mechanism-sample numbers; adjacent-sample SEs are slightly larger.
*        See Table S6 in the supplementary materials for both versions.
*
* Q5. "Legend overlaps the high-saturation panel"
*     -> Move the legend with `position(11)` (top-left) or `position(5)`
*        (top-right). The default `position(2) ring(0)' places it inside
*        the right-hand (high-saturation) panel.
*
* Q6. "I want to switch to the adjacent sample"
*     -> Replace the MODE B input block with the adjacent-sample numbers:
*
*        Adjacent sample, Table S6:
*        Completion       Lower    -4   0.043  0.089
*        Completion       Lower     0   0.298  0.117
*        Completion       Lower     2   0.402  0.151
*        Completion       High     -4   0.198  0.142
*        Completion       High      0   0.451  0.156
*        Completion       High      2   0.572  0.188
*        High-saturation  Lower    -4   0.040  0.088
*        High-saturation  Lower     0   0.286  0.114
*        High-saturation  Lower     2   0.394  0.148
*        High-saturation  High     -4   0.193  0.140
*        High-saturation  High      0   0.443  0.153
*        High-saturation  High      2   0.564  0.185
*
*===============================================================================
* End of file.
