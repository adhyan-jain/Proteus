# Data Manifest — Stage 1 (CICIDS2017)

## Source

**Corrected CICIDS2017, WTMC-2021 variant** (Engelen et al., "Troubleshooting an Intrusion
Detection Dataset: the CICIDS2017 Case Study"). This corrected version relabels/reconstructs
a significant fraction of flows from the original 2017 CICIDS release to fix labeling and
flow-construction errors identified by the authors.

- Download URL: `https://intrusion-detection.distrinet-research.be/WTMC2021/Dataset/dataset.zip`
- Project page: `https://intrusion-detection.distrinet-research.be/WTMC2021/tools_datasets.html`
- Retrieved: 2026-09-10
- Server-reported `Content-Length`: 333,841,436 bytes (confirmed on download)
- **No vendor-provided checksum exists on the source page.** The SHA256 below is what we
  computed ourselves on download — it is a record for our own reproducibility, not a
  verification against a published hash (none was published to verify against).

```
sha256(data/raw/dataset.zip) = 4d535da19795d85376ae1397d161329e3b06fc47d9a5a68cd9be2cd7ecee0f2a
```

## Extracted files (`data/raw/cicids2017/`, gitignored — not committed)

| File | Size (bytes) | Rows (incl. header) | SHA256 |
|---|---|---|---|
| Monday-WorkingHours.csv    | 208,244,807 | 371,750 | 580bc5b3a48ccaa9b61d6936bb88adb00a6a069a02c974e946bd324bc09971bc |
| Tuesday-WorkingHours.csv   | 178,453,210 | 322,004 | 59d60eff01526b511fa575a08a9a0e241674276adf1aa07471c947f7d733e19a |
| Wednesday-WorkingHours.csv | 291,529,516 | 496,780 | 820446eb19713031827a1893871e30fb9da4c3b21ad5cd15d9a2ef6686a37583 |
| Thursday-WorkingHours.csv  | 187,707,525 | 362,369 | 3db32a8e9a4da80aa15fd0bbf69733c8de8c6e6147fe279770eec1be6c263d65 |
| Friday-WorkingHours.csv    | 282,607,319 | 547,916 | 8bf5a79222d2a553b75fe1ee81cc3ddff89b87befaef52e62368fdb2e3a79def |

Total: 2,100,814 data rows (2,100,819 lines incl. 5 headers) across 5 daily CSVs, 84 columns
each (83 CICFlowMeter features + `Label`).

## Post-cleaning result (via `proteus/data_full.py::load_data_full`)

- 984 individual `inf` values (CICFlowMeter rate-feature artifact on near-zero-duration
  flows) replaced with NaN.
- 793 / 2,100,814 rows (0.038%) dropped for having >=1 NaN/inf feature after that
  replacement — not a silent drop, logged at load time.
- **2,100,021 rows retained**, 80 numeric/one-hot feature columns, **25 label classes**
  (CICIDS2017's real per-attack-variant taxonomy, including WTMC-2021's `<Attack> -
  Attempted` subclasses, kept separate rather than collapsed — see docstring in
  `clean_and_unify_cicids2017`/`_clean_label`).
- Class distribution ranges from BENIGN (78.9%, 1,657,069 rows) down to
  `SSH-Patator - Attempted` (8 rows). Full table is logged by
  `proteus/data_full.py::class_distribution_report` on every run.
- Stratified 70/15/15 train/val/test split: 1,470,014 / 315,003 / 315,004 rows.

## InSDN

Not yet acquired for this stage — see `proteus/data_full.py::load_insdn()` (raises
`NotImplementedError` with the reason). No official non-Kaggle mirror was found; acquisition
is blocked on Kaggle API credentials, tracked as a follow-up.
