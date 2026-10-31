# Cover Letter to the Editor-in-Chief

**To:**  
Prof. Sushil Jajodia, Editor-in-Chief  
*Computers & Security* (Elsevier)  

**Date:** October 31, 2026  

**Subject:** Submission of Original Research Article: *"Evaluation Validity in Software-Defined Network Intrusion Detection: An Empirical Audit of Controller Observability and Address Generalization on InSDN"*

---

Dear Prof. Jajodia and Members of the Editorial Board,

We are pleased to submit our original research manuscript entitled **"Evaluation Validity in Software-Defined Network Intrusion Detection: An Empirical Audit of Controller Observability and Address Generalization on InSDN"** for consideration for publication as a regular research article in *Computers & Security*.

### Background & Motivation
In recent years, software-defined networking (SDN) intrusion detection has emerged as a major focus of applied machine learning research. A large body of literature—including numerous articles published between 2020 and 2026—evaluates neural networks, tree ensembles, and deep learning architectures against benchmark datasets such as InSDN, routinely reporting near-perfect detection scores exceeding $99.9\%$ accuracy and F1-score. 

In this work, we present an empirical audit of the InSDN benchmark and its surrounding research literature. We examine two fundamental assumptions underpinning this domain:
1. **The Control-Plane Observability Assumption:** That SDN controllers naturally observe the rich per-connection flow features extracted offline from end-host network captures.
2. **The Address Generalization Assumption:** That high classification accuracy reflects genuine discrimination of attack behavior rather than memorization of static network addresses and duplicate flow vectors.

### Key Contributions & Empirical Findings
Through a dual-path audit combining complete OpenFlow control-channel decoding, controlled live switch experiments, and rigorous re-evaluations across multiple splitting protocols, our findings include:

1. **Control-Plane Blindness in Standard Deployments:** By decoding all 3,827 FlowMod messages across the 44 raw InSDN ONOS controller captures, we show that ONOS installs strictly reactive MAC-pair forwarding rules (`in_port|eth_dst|eth_src`). Once installed, the controller receives zero transport-layer PacketIns for ongoing TCP connections. Software reconstruction reveals that controller PacketIns capture only 1.7% of the flows and 38% of the packets present in target host traces.
2. **The Observability--Scalability Tradeoff:** Through controlled forwarding experiments across single-switch and 3-switch topologies on a live OpenFlow/Ryu testbed, we demonstrate that configuring switches to emit per-connection 5-tuple flow statistics causes a **$1,000\times$ surge in PacketIn control traffic** and severe flow-table bloat ($153.1$ entries per reply), confirming that the granular visibility assumed by host-derived flow CSVs cannot be sustained in production SDN control planes.
3. **Pervasive Address Memorization & Benchmark Leakage:** Auditing 12 published benchmark papers (spanning 2020–2026), we find that $100\%$ employ random flow-level splits, $48.7\%$ of test records are exact duplicates of training records, and trivial classifiers relying solely on IP addresses and ports achieve $\ge 99.99\%$ balanced accuracy.
4. **Generalization Collapse on Genuine Endpoints:** When evaluated under source-IP-disjoint splitting (Leave-One-Source-IP-Group-Out, LOSGO), performance collapses from $0.9998$ to $0.907 \pm 0.085$, with worst-case seeds plunging to $0.66$. When isolating genuine, non-spoofed hosts from automated DDoS spoofing headers, Balanced Accuracy drops to $0.8417 \pm 0.1114$ and Macro-F1 collapses to $0.6503 \pm 0.2005$.
5. **Exact Hypergeometric & Sample-Weighting Analysis:** We derive the exact hypergeometric partition probabilities governing scikit-learn's integer ceiling rounding rule ($k = \lceil 0.3 \times 122,868 \rceil = 36,861$), proving why standard 10-seed evaluations exhibit extreme bimodal variance ($r = -0.7713$ with test row share). We evaluate source-address sample weighting via paired per-seed testing, demonstrating that square-root attenuation acts as a variance-moderating tail hedge rather than an unconditional performance boost.

### Methodological Rigor & Reproducibility
Our manuscript adheres to the highest standards of open science and empirical reproducibility:
- **Zero Hallucination / Complete Data Provenance:** Every table, figure, and numerical claim in the 17-page manuscript maps directly to committed raw captures, feature datasets, and machine-readable JSON artifacts.
- **Continuous Automated Verification:** We provide an automated verification suite (`verify_numbers.py`) that executes 149 programmatic assertions against the compiled manuscript, confirming exact mathematical agreement (Exit code 0).
- **Public Reproducibility Package:** All code, decoding tools, experiment runners, and analysis scripts are fully packaged and automated via a single shell script (`reproduce.sh`).

### Author Affirmations & Declarations
- This manuscript represents original work and has not been published previously, nor is it under consideration for publication elsewhere in whole or in part.
- All authors have reviewed and approved the final manuscript and agree with its submission to *Computers & Security*.
- The authors declare that there are no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.
- The research makes constructive methodological recommendations for benchmark construction and ethical security evaluation without proprietary encumbrances.

We believe this paper provides a timely, essential course-correction for the SDN intrusion detection community and will be of immense interest to the readers of *Computers & Security*.

Thank you very much for your time and consideration of our work.

Sincerely,

**Dr. Arivoli A.** (Corresponding Author)  
Associate Professor, School of Computer Science and Engineering  
Vellore Institute of Technology, Vellore 632014, Tamil Nadu, India  
Email: arivoli.a@vit.ac.in  

*On behalf of the authors:*  
Adhyan Jain, Atharva Sheersh Pandey, Kshitij Manikshete, and Dr. Arivoli A.  
*Proteus Research Project*  
Repository: `https://github.com/adhyan-jain/Proteus/tree/journal-paper/research/insdn_controller`
