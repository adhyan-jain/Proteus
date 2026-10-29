# Prior art: InSDN host/IP structure, host-held-out evaluation, identifier leakage

Search date 2026-10-29. Time-boxed web search (about 6 queries, 2 fetches). Search snippets were produced by the search tool; only the dataset README was fetched and read in full. Negative results mean "not found in this limited search", not "does not exist".

## Verdicts

- (a) Host/IP structure of InSDN (distinct source IPs, spoofed or single-flow sources, few real attacker hosts): NOT FOUND in searches. The only primary description says one Kali attacker VM, four Mininet hosts, and attacks "from both outside and inside"; it gives no IP counts and does not mention spoofing.
- (b) Leave-one-host-out or held-out-attacker-host evaluation on InSDN or other SDN IDS datasets: NOT FOUND in searches.
- (c) Statement that InSDN random-split results are inflated by identifier/host leakage: NOT FOUND for InSDN specifically. Adjacent (non-InSDN, or only generic) statements exist, listed below.

## Hits

1. InSDN dataset README (Elsayed et al., UCD ASEADOS). https://aseados.ucd-cs.ie/datasets/SDN/README.txt (redirected from aseados.ucd.ie). READ FULL TEXT via fetch tool (summarised by the tool, not raw).
   - (a) Partial: Kali Linux VM is "the attacker server"; four Mininet virtual hosts; Metasploitable 2 target; attacks "from both outside and inside the SDN network"; hosts h1/h2 generate malicious traffic. Source IP assignment and spoofing are NOT described.
   - Labeling: "we used some features information such as Source IP and Destination IP" (so IPs informed labels, which is relevant to leakage but is not itself a leakage claim).
   - (b), (c): nothing.
2. Elsayed, Le-Khac, Jurcut, "InSDN: A Novel SDN Intrusion Dataset", IEEE Access 2020, DOI 10.1109/ACCESS.2020.3022633. https://researchrepository.ucd.ie/handle/10197/12615 . SNIPPET ONLY (full paper not read). Nothing found on (a)/(b)/(c). A secondary snippet says the feature set (83 features) includes IP addresses as categorical fields.
3. ICIT 2026 reproduction paper (CNN-LSTM/Transformer IDS on InSDN), https://muhammadsalman1205.vercel.app/research-paper-icit2026.pdf . SNIPPET ONLY; PDF fetch returned unreadable binary. Per snippet: criticises single-split near-perfect accuracy, feature dropping and class merging with synthetic upsampling; reports about 81.6% average accuracy. Not about host/IP leakage per snippet. (c) adjacent only (single-split inflation, not identifier leakage). Unverified.
4. "Individual Packet Features are a Risk to Model Generalisation in ML-Based Intrusion Detection", arXiv 2406.07578. SNIPPET ONLY. Not InSDN. Says identifying features (frame number/time, eth src/dst, src/dst IP) are used in a studied work and that removing them is insufficient without session-based segregation, so session characteristics leak across train/test. Generic (c)-adjacent for IDS, not SDN/InSDN.
5. "Towards a Privacy-preserving Deep Learning-based NIDS in Data Distribution Services", arXiv 2106.06765. SNIPPET ONLY. Not InSDN. CNNs reportedly rely heavily on IP address as a feature. Generic shortcut evidence.
6. Søgaard et al., "We Need to Talk About Random Splits", EACL 2021, arXiv 2005.00636. SNIPPET ONLY. NLP; general claim that random splits are overly optimistic. Not InSDN.
7. Emergent Mind InSDN summary and Shamra Academia review (aggregators). SNIPPET ONLY. Note a conflict: aggregator claims 16 classes (1 normal + 15 attack) are not confirmed by primary sources; sample counts 361,317 total (68,424 normal, 292,893 attack) unverified. Do not cite without checking the original paper.
8. A 2024 InSDN SHAP feature-selection study (title/URL not captured). SNIPPET ONLY; not checked for whether IP features dominate.

## Queries run
- InSDN dataset attacker hosts source IP leakage
- InSDN leave-one-host-out OR "grouped split" OR "data leakage" SDN intrusion detection dataset
- InSDN dataset Elsayed 2020 Kali Metasploitable attackers description
- InSDN random split inflated accuracy host overlap spoofed source IP DDoS critique SDN IDS datasets generalization
- "InSDN" "source IP" removed features data leakage identifier IP address shortcut intrusion detection

## Not searched (time limit)
Google Scholar, IEEE Xplore, ScienceDirect, MDPI, PMC directly; full text of the Elsayed paper; Sci. Rep. 2026 and ETASR/IIETA InSDN papers that surfaced in results (unread). A deeper pass on those could still turn up a prior statement.

## Full-text check (2026-10-29)
Method: PDFs saved via WebFetch and converted with pdftotext, then grepped for IP/host/attacker/spoof/session/disjoint/split/InSDN and read in context.

1. Flood, Engelen, Aspinall, Desmet, "Bad Design Smells in Benchmark NIDS Datasets", EuroS&P 2024. FULL TEXT READ (pdftotext, ~16.6k words; InSDN not covered by the paper: zero hits for "InSDN"/"SDN" outside a reference title).
   - (a) InSDN host/IP structure: no such statement found in full text (InSDN absent). The only host-count statement is about CICIDS: "CIC 17 comprises 14 hosts and CIC 18 comprises of 500 hosts."
   - (b) leave-one-host / held-out-attacker evaluation: no such statement found in full text. Nearest: "standard, randomised train/test splits result in data leakage." (homogeneous traffic, failed attacks); and "this is often equivalent to training and evaluating models on flows from the same attack, a form of data leakage." Their remedy is train/test from different runs of a generation process, not host-disjoint splits.
   - Also: "Labelling flows via IPs and timestamps is challenging." (labelling, not evaluation).
2. Salman et al., ICIT 2026 InSDN re-evaluation (Malik, Salman, Ahmed, Maryam). FULL TEXT READ (pdftotext, ~5.1k words). It uses stratified 5-fold CV; no mention of IP addresses, hosts, attackers, spoofing, or group/host/session-disjoint splits. (a) none; (b) none. Closest: criticism of single splits ("single train-test splits"), not host-level.
3. Elsayed et al. 2020, InSDN, IEEE Access. COULD NOT READ (IEEE Xplore page returned empty; earlier note's description from snippets stands). Verdict unverified; cannot claim absence.
4. Engelen et al. 2021, "Troubleshooting an Intrusion Detection Dataset: the CICIDS2017 Case Study". COULD NOT READ (arXiv id not located in time; a guessed id returned an unrelated paper, discarded). Verdict unverified. It concerns CICIDS2017 only, not InSDN.

Net: among the two papers actually read in full, neither states InSDN's source-IP/host structure nor a leave-one-host-out evaluation. Elsayed 2020 (open-access PDF) and Engelen 2021 still need a full-text read before the novelty claim is made unhedged.
