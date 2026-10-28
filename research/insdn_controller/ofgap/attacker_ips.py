"""Write attacker_ips.json: IPs that occur (as source or destination) only in attack-labelled
InSDN CSV flows and never in a Normal-labelled flow. Used only for the sensitivity label variant."""
import glob
import json
from pathlib import Path

import pandas as pd

CSV = str(Path(__file__).resolve().parents[3] / "data/raw/insdn_official/extracted/InSDN_DatasetCSV/*.csv")
df = pd.concat([pd.read_csv(f, usecols=["Src IP", "Dst IP", "Label"]) for f in sorted(glob.glob(CSV))])
nor = df[df.Label == "Normal"]
att = df[df.Label != "Normal"]
normal_ips = set(nor["Src IP"]) | set(nor["Dst IP"])
attack_only = sorted((set(att["Src IP"]) | set(att["Dst IP"])) - normal_ips)
Path(__file__).parent.parent.joinpath("attacker_ips.json").write_text(json.dumps(attack_only))
print(len(attack_only), "attack-only IPs")
