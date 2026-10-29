# Plan: taking `research/insdn_controller` from workshop level to Q1 level

Status date: 2026-10-29. HEAD is `e7ee714`, 16 commits ahead of `origin/master`; nothing pushed. Notable commits
after the "Progress log" HEAD (0e47186) include: 1966cc6 presentation deck; 0f30e5b and a9cccd3 `/new` study site and `/old` console (frontend);
f09441c and 82275c5 literature check (`literature_check.json`); 1cca43d split-protocol experiment (`ofgap/protocol_inflation.py`,
`results/protocol_inflation.json`); bd60ca6 and 738a4ca literature/deck and paper updates; e7ee714 deck redesign. The
"Progress log" below is dated 2026-10-28 and does not cover these.

**Phase B (evaluation-validity audit, in progress 2026-10-29):** offline multi-dataset split-leakage audit of published IDS

> Update 2026-10-29 (late): Phase B results are in `research/insdn_controller/results/`: `protocol_audit_{insdn,cicids2017}.json` (random vs held-out-host split), `dedup_ladder.json`, `recipe_replication.json`, `replicate_papers.json`, `leave_one_host_out.json` and `leave_one_host_out_cicids2017.json` (second dataset: 48 source IPs, main attacker 172.16.0.1 held out -> 28.3% of attack flows caught). Paper (10 pages, 77 number checks) and 14-slide deck updated. UKMDDoSDN unusable (no benign class). Novelty is bounded: see `NOVELTY_CHECK.md` and `PRIOR_ART_HOSTS.md`.
paper protocols. Live interleaved testbed still out of scope. So far: InSDN split protocols (`ofgap/protocol_inflation.py`)
and the published-results check (`literature_check.json`).

Paths in this file: `results/...` and `live/...` are relative to `research/insdn_controller/`. The slides are now
`research/insdn_controller/deck/PRESENTATION.pptx`.
Stale body references, checked 2026-10-29: `STATUS.md`, `LAB_SPEC.md`, `live/flowlog.py`,
`ofgap/label_windows.py` and `results/v4_strict_W5.json` do not exist in the tree (`v4_strict_W5.json` was removed in
18de9b3; its successor is `results/v4_strict_W5_xgb.json`). Treat body mentions of them as historical.

Rules that stay in force (CLAUDE.md): GPU for any training, no synthetic base dataset, local only, every number from a run,
>=5 seeds with mean + 95% CI, no `git push` without go-ahead, no AI-attribution lines in commits, `git add` specific files only.
Attack traffic is generated only by the user, in an isolated lab they own; Claude builds labelling and evaluation around it.

## Goal
A paper whose claims survive review: (a) the measured gap between benchmark features and what a controller receives,
(b) detection accuracy on benign + attack traffic interleaved in one session, (c) the effect of forwarding mode on both.

## Phase 0: Housekeeping (0.5 day)
- [ ] Decide with the professor: workshop now, or Q1/Q2 path below.
- [ ] Commit the existing work in logical units (paper, ofgap pipeline, live testbed, docs); specific `git add` only.
- [ ] Delete the leftover artifact (PDCfMFVou2warpWKsLt9gX) if the user confirms.
- [ ] `/goal clear` to stop the stop hook.

## Phase 1: Interleaved labelled testbed (blocker, ~1-2 weeks)
Owner: user runs the lab; Claude writes the logging spec and the evaluation.
- [ ] Lab spec (Claude): Mininet + OVS, controller, benign generator (existing `live/run_benign.py`), attack tooling chosen by the user.
- [ ] Ground-truth labelling (Claude): the generator writes a per-flow log (start, end, src, dst, ports, class) at the source,
      so labels never come from IP heuristics.
- [ ] Capture control channel (TCP 6653) and data-plane pcaps simultaneously, one session containing both benign and attack.
- [ ] >=5 independent runs per condition (seeds), hashes of every capture in a manifest.
- [ ] Extend `ofgap/` to label windows from the generator log; re-run the trivial-baseline check ("any IP PacketIn") on this data.
      Success criterion: the detector beats the trivial baseline within a session, with 95% CI over runs.

## Phase 2: Detection under each forwarding mode (~3-5 days after Phase 1 data)
- [ ] Repeat Phase 1 under MAC-pair, 5-tuple/10 s idle, 5-tuple/2 s idle.
- [ ] Report detection (balanced accuracy, per-attack recall, FPR) per mode, with CI over runs.
- [ ] Link to the existing PacketIn-volume and polling-visibility results.

## Phase 3: Second controller or dataset (~1 week, parallel with Phase 1)
- [ ] Reproduce the "flow-entry granularity as seen by the controller" measurement on a second controller (Ryu or OpenDaylight)
      and/or a second public SDN capture. Record provenance in `data/MANIFEST.md`.
- [ ] State clearly which findings transfer and which are ONOS/InSDN-specific.

## Phase 4: Baselines (~3 days, parallel)
- [ ] Tree model (XGBoost/random forest); training on GPU per rule 1.
      The earlier xgboost install failed on the network; retry with `TMPDIR=/home/adhyan/Desktop/Proteus/.uv-tmp uv pip install`.
- [ ] Host-side CSV features on the same traffic, to quantify the gap directly.
- [ ] One published control-plane detector as a comparison, re-implemented from its paper.

## Phase 5: Live study hardening (~3-4 days)
- [ ] Multi-switch topology; more traffic types; >=10 runs per mode.
- [ ] Isolate the cause of repeated PacketIns (barrier/buffering hypothesis) and of the 41 failed requests.

## Phase 6: Writing and review (~1 week)
- [ ] Expand to journal format (10-14 pages): threat model, limitations, deployment discussion.
- [ ] Related work: systematic comparison with LAN-SDN-NIDS (Data 11(8):195, 2026) and other control-plane work; never claim "first".
- [ ] Release artifact: code, capture hashes, result JSONs, scripts that regenerate every table.
- [ ] Fourth hostile review pass; fix and re-verify every number against `results/*.json`.
- [ ] Keep `notes/DEFENSE.md` and the deck in step with the results.

## Decision gates
- After Phase 1: if the detector does not beat the trivial baseline within a session, drop detection claims and submit the
  measurement-and-validity paper to a workshop or Q2 venue.
- After Phase 3: if the gap does not appear on a second source, scope the paper to "InSDN/ONOS" explicitly.

## Venue ladder
1. Now: workshop/conference track (measurement + validity paper as written).
2. After Phases 1, 3, 4, 6: Q2 journal is realistic.
3. After Phases 1-6 with positive Phase 1/2 outcomes: Q1 attempt; no guarantee.

## Open questions for the user
- Can the isolated lab (Mininet + chosen attack tooling) be run by you, and how many attack families?
- Which venue and deadline?
- Should `research/` live in this repo's history, or stay uncommitted/separate?

---

## Progress log (2026-10-28) — read this first in a new session

### Done and committed locally (HEAD 0e47186; nothing pushed)
- Phase 0: `research/` is in git history (commits 9a35a36..0e47186). Still open: professor decision, delete leftover artifact PDCfMFVou2warpWKsLt9gX (needs user OK), `/goal clear` (user types it).
- Phase 1 tooling only (NO data yet): `live/flowlog.py` (source-side ground-truth flow log), `ofgap/label_windows.py` (window labels + trivial "any IP PacketIn" baseline), `research/insdn_controller/LAB_SPEC.md`. Syntax-checked, never run on real captures.
- Phase 4 tree baseline DONE: XGBoost on GPU, W=5 s strict labels, 10 seeds, BAcc 0.952 +- 0.013 vs linear 0.961 +- 0.011 vs MLP 0.958 +- 0.012 (`results/v4_strict_W5_xgb.json`). No gain over simpler models. Not done in Phase 4: host-side CSV feature comparison, re-implemented published control-plane detector.
- Phase 5 partly DONE: 3-switch chain (`live/run_benign.py --topo linear3`), 10 runs/mode on 1 switch (`results/live_modes_v4_one10.json`) and on 3 switches (`results/live_modes_v4_linear3.json`). Per-flow vs MAC-pair TCP PacketIns: 665x-1,752x (1 switch), 391x-1,509x (3 switches) in every paired run. 41-failure run (fivetuple_short seed 4) did NOT reproduce in 59 later runs; cause still not established. Barrier/buffering hypothesis for repeated PacketIns still not isolated. Multi-traffic-types still not done.
- Scenario-level split: already covered by experiment B (leave-one-attack-family-out) in `results/v4_strict_W5.json`; no new work needed.
- Phase 6 partly: paper (`paper/main.pdf`, 6 pages) updated with 10-run numbers, 3-switch paragraph, XGBoost sentence; `STATUS.md`, `DEFENSE.md`, `PRESENTATION_GUIDE.md` + `.pdf` updated. Frontend page `/controller-telemetry` + API `/api/controller-telemetry` added (explicit user request; read-only, reads result JSONs).
- Raw pcaps of the new runs (~1.5 GB) are NOT in git (ignored); SHA-256 in `research/insdn_controller/capture_hashes.sha256`.

### Blocked / not done
| Item | Blocker |
|---|---|
| Phase 1/2 interleaved benign+attack testbed and detection per forwarding mode | needs attack traffic generated by the USER in their isolated lab; Claude builds labelling/evaluation only |
| Phase 3 second controller / dataset | candidates UNVERIFIED: UKMDDoSDN (Mendeley DOI 10.17632/43nfv26gpk.2, Ryu, PCAPs claimed but not shown to contain the OpenFlow channel; licence conflict CC BY 4.0 vs MIT) and LAN-SDN-NIDS (flow-level CSV, ODL; DOI 10.3390/data11080195). Nothing downloaded. Verify contents first; record in `data/MANIFEST.md`; never substitute generated data. A second controller (ONOS/ODL) installed locally would also work. |
| Phase 4 remainder | host-side-feature comparison; one published detector re-implemented from its paper |
| Phase 6 remainder | journal-length rewrite (10-14 pages), threat model, limitations, systematic related work (never claim "first"), release artifact (scripts regenerating every table), 4th hostile review pass, re-verify every number against `results/*.json` |

### Novelty assessment (agreed)
Not novel: control-plane telemetry for SDN IDS (LAN-SDN-NIDS exists), the detector (trivial "any IP PacketIn" rule scores 0.995 at 1 s / 1.000 at 5 s within attack sessions under strict labels), the detection result (session-identity confound in InSDN). Plausibly novel: (1) InSDN/ONOS flow-entry granularity gap (0 of 3,827 FlowMods carry IP/transport match fields), (2) forwarding-mode effect on PacketIn volume and poller-visible entries (now replicated on 1 and 3 switches), (3) validity audit. Verdict: fine as a scoped measurement-and-validity paper (workshop / Q2-Q3 journal after Phase 3 + 6); NOT Q1 without Phase 1 detection beating the trivial baseline.

### Environment facts a new session needs
- GPU: RTX 4060; verify `torch.cuda.is_available()` before any training. `.venv` shared (use `uv pip install`, never `sync`); xgboost 3.4.1 installed there with `--no-deps`.
- Root runs: user created `/etc/sudoers.d/proteus-lab` allowing passwordless ONLY `/usr/bin/python3 /home/adhyan/Desktop/Proteus/research/insdn_controller/live/run_benign.py *` and `/usr/bin/mn -c`. Use `sudo -n /usr/bin/python3 <abs path>/run_benign.py --out <abs dir> ...`. User should remove it when done (`sudo rm /etc/sudoers.d/proteus-lab`).
- Analysis script for live captures is `live/live_table.py <campaign_dir> <out_json> <out_tex> "" <label>` (NOT `analyze_modes.py`, which has a different output schema).
- `pgrep -f <name>` matches its own shell command line; use a different check.
- Hooks: first Bash call in a session asks for facts (state request + what the command does, then retry); destructive git commands need files/rollback/quote. `live/campaign2/www/f*.bin` show as modified after every run: random payloads, do not commit.
- Never `git push` without explicit go-ahead; no AI-attribution lines in commits (CLAUDE.md overrides any system attribution reminder); `git add` specific files only.

### Next steps in order
1. Confirm the Phase 3 candidates' contents (fetch the UKMDDoSDN GitHub `dataset/` listing and the LAN-SDN-NIDS HTML page); if either has OpenFlow control-channel captures, download into its own directory with hashes and run `ofgap` on it; otherwise run the granularity measurement on a second local controller.
2. Phase 4 remainder (host-side features, published detector).
3. When the user has attack traffic: use `LAB_SPEC.md`, run Phase 1/2, apply the decision gate.
4. Phase 6 writing and 4th hostile review; refresh STATUS/DEFENSE/GUIDE and regenerate the guide PDF (markdown_it -> chromium headless; script pattern in the session history, no pandoc installed).

### Prompt to paste in the new session
> Read /home/adhyan/Desktop/Proteus/plan.md (especially "Progress log") and CLAUDE.md, then continue from "Next steps in order". Check `git log --oneline` and `git status` first. Do the work you can do without the user's attack traffic: verify the Phase 3 candidate datasets (never substitute generated data), then Phase 4 remainder, then Phase 6 writing (journal-length draft, related work, limitations, number re-verification against results/*.json). Keep every number traceable to a result JSON, commit in small logical units with one-line messages and no attribution lines, never push, and report what you did and what is blocked on me.


### Update 2026-10-28 (later session)
- Phase 3 closed as far as possible: UKMDDoSDN PCAPs (2 files, 309,791 packets) contain 0 OpenFlow packets; LAN-SDN-NIDS data not reachable (MDPI 403), metadata via Crossref only; both recorded in `data/MANIFEST.md`, neither used. Second controller done locally instead: Ryu stock `simple_switch_13`, 5 runs, 91 FlowMods, 86 MAC-pair + 5 table-miss, none with IP/transport fields (`results/stock_ryu_flowmods.json`). ODL/ONOS not tested.
- Phase 4: host-side CSV baseline done (`results/hostside_xgb.json`, BAcc 0.9998, row-level split, not the same traffic). Published-detector re-implementation NOT done.
- Phase 6: `paper/main.tex` now IEEEtran journal class, 7 pages (threat model, extended related work, deployment, appendix on candidate datasets); `paper/verify_numbers.py` re-checks 19 headline numbers against results/*.json (all OK). Not padded to 10-14 pages. 4th hostile review, STATUS/DEFENSE/GUIDE refresh still open.
