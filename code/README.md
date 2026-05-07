# Code

Run Stata scripts from the repository root unless a script states otherwise. The helper file `code/stata/01_globals_and_ado.do` defines project-relative paths.

Several Python scripts require `pandas`, `numpy`, `statsmodels`, `scipy`, `pyreadstat`, `linearmodels`, and `differences`. Stata scripts require Stata 17 or later; some regressions require `reghdfe` and `boottest`.

Scripts that depend on restricted CLDS or FOBS microdata will run only after those data have been obtained from the original providers and placed in the expected local folder structure.
