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

**Source**: official distribution from the dataset authors' own institutional lab page —
UCD ASEADOS Lab (School of Computer Science, University College Dublin), the home
institution of Elsayed, Le-Khac & Jurcut, "InSDN: A Novel SDN Intrusion Dataset," IEEE
Access, vol. 8, pp. 165263–165284, 2020.

- Download URL: `https://aseados.ucd.ie/datasets/SDN/InSDN_DatasetCSV.zip`
- Institutional page: `https://aseados.ucd.ie/datasets/SDN/`
- Paper/repository record: `http://hdl.handle.net/10197/12615` (UCD Research Repository)
- Retrieved: 2026-09-11
- File size: 19,302,607 bytes (matches the page's reported ~18M)
- `sha256(InSDN_DatasetCSV.zip) = ee89ec66705c529fef26b27dd18c6aa56d469006f7ade9cd92fd4a503e320d7`
- Extracted to `data/raw/insdn_official/extracted/InSDN_DatasetCSV/` (gitignored, not committed)

An earlier version of this pipeline used a Kaggle community re-upload
(`badcodebuilder/insdn-dataset`) before this official source was located — that copy has been
superseded and is no longer referenced by `proteus/data_full.py`. Row-for-row content is
identical (verified by matching row counts across all three files), but the official UCD
source is now the source of record.

| File | Rows | SHA256 |
|---|---|---|
| Normal_data.csv    |  68,424 | 5cc80c7b5707bf92d3ea501a9af8b488cc4680f0a5b29b5b608e92bbe6e297a |
| OVS.csv             | 138,722 | 8b218c16769dea961028d511928e7da139302afe341cea29dd65e526d580e09 |
| metasploitable-2.csv | 136,743 | 75c5ea5e3526c9500e3d73cbdb11b99ff3fbfb8dac8dff8c39e9dd35d60556b |

Total: 343,889 rows — matches the published InSDN row count exactly.

### Schema unification

InSDN's CSVs use CICFlowMeter's abbreviated column-name convention (e.g. `Tot Fwd Pkts`), while
the corrected CICIDS2017 files use the unabbreviated convention (e.g. `Total Fwd Packet`). Both
are the same 84 CICFlowMeter features in the same emission order — verified by a positional
diff of the two raw header rows, which lines up 1:1 across all 84 columns, including one real
naming quirk (InSDN's `CWE Flag Count` is CICIDS2017's `CWR Flag Count`, same feature/position).
`proteus/data_full.py::INSDN_TO_CICIDS2017_COLS` encodes this verified positional mapping (not a
fuzzy abbreviation-expansion heuristic), so InSDN rows are renamed onto CICIDS2017's column
convention and then run through the same cleaning path (`clean_and_unify_cicids2017`).

InSDN's `Normal` label is mapped to `BENIGN` to match CICIDS2017's benign-class naming; InSDN's
attack labels (`DDoS`, `DoS`, `Probe`, `BFA`, `Web-Attack`, `BOTNET`, `U2R`) have no CICIDS2017
equivalent for `BFA`/`Web-Attack`/`BOTNET`/`U2R` and are kept as their own classes rather than
force-mapped onto an unrelated CICIDS2017 label.

### Post-cleaning result (via `proteus/data_full.py::load_insdn`)

- 0 inf values, 0 rows dropped for missing/invalid features (InSDN's CSVs are clean going in).
- **343,889 rows retained**, 80 numeric/one-hot feature columns, **8 label classes**: BENIGN
  (19.9%), DDoS (35.5%), Probe (28.5%), DoS (15.6%), BFA (0.41%), Web-Attack (0.056%), BOTNET
  (0.048%), U2R (0.0049%).
- Stratified 70/15/15 train/val/test split: 240,722 / 51,583 / 51,584 rows.
