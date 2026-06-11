# Replication materials

This repository contains code, derived administrative rollout data, and table/figure outputs for an anonymous manuscript submitted to *China Agricultural Economic Review* on land certification and farmland rental in rural China.

The repository is organized as follows:

- `code/stata/`: Stata do-files used for the main stacked DID, maturity, pretrend, placebo, and external-validation checks.
- `code/python/`: Python scripts used for IV diagnostics, modern-DID checks, FOBS validation, heterogeneity analysis, and map preparation.
- `data/derived/`: public or aggregate derived data that do not contain household- or person-level survey records.
- `data/private_placeholders/`: file manifest for restricted data that must be obtained from the original data providers.
- `outputs/tables/`: CSV outputs used to assemble the manuscript and online appendix tables.
- `outputs/figures/`: figure files used in the submission package.

Restricted microdata from CLDS and FOBS are not redistributed here. Users who have access to the restricted source data can place the required files under the paths listed in `data/private_placeholders/restricted_file_manifest.csv` and run the scripts from the repository root. The derived administrative rollout files supplied in `data/derived/` can be used directly.

The scripts are provided to document the empirical workflow and to support reproduction where data-access agreements permit it.

## Usage terms

The materials in this repository are provided for anonymous peer review and scholarly replication. Code and derived non-restricted materials may be used to inspect, reproduce, and extend the empirical workflow, subject to the access conditions of the original CLDS and FOBS data providers. Restricted household- or person-level microdata are not redistributed in this repository and must be obtained from the original providers.

No warranty is provided. Please cite the published article or repository record if these materials are used after publication.
