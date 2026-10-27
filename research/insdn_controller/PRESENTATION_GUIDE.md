# Presentation guide: "What does the SDN controller actually see?"

For a 12–15 minute supervisor meeting. Companion files: `DEFENSE.md` (slides + speaker notes + Q&A), `paper/main.pdf`,
`STATUS.md` (what is and is not done). Open the paper PDF next to the slides: reviewers trust a number more when you can
point at its table.

## The 30-second pitch
"SDN intrusion-detection papers say the controller has a global view, but they are scored on flow features computed at the
victim host. InSDN's authors also recorded their ONOS controller's OpenFlow traffic, and nobody seems to have looked at it.
I parsed all 44 captures. The controller never installed or reported a 5-tuple flow entry: only MAC-pair and `eth_type`
entries. It does see a dense PacketIn stream, and models built only from that reach 0.946 balanced accuracy on unseen
captures. But I also found that this number can't be read as attack-detection accuracy, because of how InSDN was recorded.
So the contribution is the measurement, a reproducible pipeline, and a validity analysis that tells the next person
what InSDN can and cannot support."

## The 3 things you want the professor to leave with
1. **A real, checkable measurement:** 0 of 44 captures, 0 of 3,827 FlowMods, ever carry IP or transport match fields.
2. **A reproducible pipeline** with its own error rate reported (12 KB lost of 7.38M messages) and hashes of every capture.
3. **You found the weakness yourself** (trivial rule 0.995; tiny session probes) and say what would fix it. This is what
   makes a supervisor trust the rest.

## Timeline (13 min)
| Min | Slide | Goal |
|---|---|---|
| 0–1 | 1 Question | Frame: benchmark features vs what a controller receives |
| 1–3 | 2–3 Gap + PacketIn stream | Land the measurement; show the table once, don't read it |
| 3–5 | 4 Forwarding case study | Show it as a *design* finding; state the confound before anyone asks |
| 5–6 | 5 Method | One sentence per step; stress "no capture in both train and test" |
| 6–8 | 6–7 Results + generalisation | Say "feasibility", not "detection accuracy" |
| 8–11 | 8 Validity | Spend the most time here. This is your credibility slide |
| 11–12 | 9 Contributions | Read the five items, one line each |
| 12–13 | 10 Questions | Hand over; keep the Q&A table open |

## Order of honesty (say these unprompted, in this order)
1. "The 0.946 is capture-grouped, so it is optimistic. Variants of one scenario can sit on both sides of a fold."
2. "Within sessions, a trivial 'any IP PacketIn' rule scores 0.995 under my strict labels. So I do not claim detection accuracy."
3. "My first Ryu run showed only a 4× PacketIn difference because my learning switch shadowed TCP with ping/ARP entries.
   I fixed the app and reran: per-flow forwarding sends ~10,350 TCP PacketIns per run vs ~12 for MAC-pair, in every paired run.
   One run had 41 failed requests, probably controller overload."
4. "Novelty is narrow: inside InSDN, controller-observable only. LAN-SDN-NIDS (2026) already builds a control-plane dataset."

## Phrases to use / avoid
| Say | Don't say |
|---|---|
| "feasibility", "separates attack captures from benign captures" | "my detector achieves 94.6% accuracy" |
| "as far as my searches show" | "nobody has ever" / "first to" |
| "the controller never installed or reported a 5-tuple entry" | "SDN controllers can't see flows" (it is ONOS-in-InSDN specific) |
| "per-flow forwarding sent ~10,000 TCP PacketIns per run vs ~12 for MAC-pair in this testbed" | "granularity causes a 1000× PacketIn increase in SDN" (one switch, one app) |
| "a visibility study, not a detection study" (for the Ryu testbed) | "I validated this live" |

## Hard questions and what to answer
| Question | Answer (short) |
|---|---|
| "So does it detect attacks?" | Not proven. It separates InSDN's attack captures from benign ones. A trivial rule beats it within sessions under strict labels. Fixing this needs benign and attack traffic interleaved in one session. |
| "Why not just report the 99% from the CSV papers?" | Those use features a controller never receives, so they don't describe a deployable controller-side detector. That gap is the paper. |
| "Logistic regression matches your MLP: what's the model contribution?" | None. The contribution is the measured view, the pipeline and the validity analysis. |
| "Is 10 seeds enough?" | The seeds only vary folds and initialisation on the same 44 captures; the intervals are not over new testbeds. The cluster bootstrap over captures is wider and is in the paper. |
| "Why is the PacketIn-rate baseline so bad?" | Plausibly because benign sessions also generate heavy PacketIn volume, but I can't verify it: the Normal group has no target-side captures. |
| "What would make this a stronger paper?" | A second testbed with attack and benign traffic interleaved, and detection evaluated under each forwarding mode. |
| "Which venue?" | Workshop or conference track as it stands. A journal version needs the interleaved testbed. |

## Before the meeting (checklist)
- [x] Live rerun with the corrected app is done (`results/live_modes_v3.json`); the paper and slides use it.
- [ ] Open `paper/main.pdf` and `DEFENSE.md` side by side; know where Tables cv, family, cross and confound are.
- [ ] Re-read slide 8 twice. It is the one you will be questioned on.
- [ ] Know these numbers cold: 44 captures, 3,827 FlowMods, 0.946, 0.616, 0.995, 6 windows from 2 captures, 10,350 vs 11.6, 151.9 → 36.8.
- [ ] Have `STATUS.md` ready to answer "what is not done".
- [ ] Nothing is committed to git yet; decide with the professor whether `research/` should live in the repo.

## If something goes wrong
- A number is questioned: open `results/<file>.json` named under the slide; every number comes from one.
- You don't know: say "I measured X but not Y; Y is future work." Never improvise a number.
