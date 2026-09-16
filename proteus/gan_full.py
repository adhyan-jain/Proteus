"""Full-scale conditional WGAN-GP (Wasserstein GAN with Gradient Penalty) for minority-class
attack synthesis on the real CICIDS2017 data (Stage 2 of the paper-grade backend scale-up).

Does NOT modify or replace `proteus/gan.py`, the demo's small WGAN-GP -- that stays as-is for
the Streamlit demo.

## GAN-target class selection (a real, citable methodological choice, not an implementation
detail to bury)

CICIDS2017's 25 real label classes are genuinely long-tailed: from BENIGN (1,657,069 rows) down
to `SSH-Patator - Attempted` (8 rows total, ~5-6 in the 70% train split). A class with a
single-digit sample count cannot be meaningfully modeled by a generative network -- there is
nothing to learn a distribution from, and no way to hold out samples to check the generator
against. We therefore define GAN-target classes by two criteria, both required:

1. **Rare**: the class is < `RARE_FRACTION_THRESHOLD` (3%) of the full corpus -- i.e. it is
   actually a class imbalance problem worth augmenting, not just "smaller than BENIGN." This
   mirrors the same 3% threshold the demo (`proteus/pipeline.py::RARE_FRACTION_THRESHOLD`) uses,
   for consistency across scales.
2. **Modelable**: the class has >= `MIN_TRAIN_SAMPLES` (300) rows in the train split -- enough
   for the generator to learn *something* real and for a diversity diagnostic to have a
   meaningful held-out comparison set.

Applying both criteria to the real Stage 1 distribution:
- PortScan (159,023), DoS Hulk (158,469), DDoS (95,123): excluded -- above the 3% rarity
  threshold. These are minority relative to BENIGN but not the imbalance problem GAN
  augmentation targets; the classifier already sees tens of thousands of real examples.
- 9 classes below 300 train rows (`Web Attack - Brute Force`, `DoS GoldenEye - Attempted`,
  `Infiltration`, `Web Attack - XSS`, `Infiltration - Attempted`, `Web Attack - Sql Injection`,
  `FTP-Patator - Attempted`, `Heartbleed`, `SSH-Patator - Attempted`): excluded -- not enough
  data to model or validate against. These remain a real, honest gap; augmenting them would mean
  the generator learning almost entirely from its own random init, which is not augmentation, it's
  fabrication.
- The remaining 12 classes are the actual GAN targets (see `GAN_TARGET_CLASSES` below, resolved
  by name against whatever label encoding a given run produces).
"""
import gc
import json
import logging
import time
from pathlib import Path

import proteus.config  # noqa: F401 -- must import before numpy/torch to cap BLAS/OMP threads

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("proteus.gan_full")

RARE_FRACTION_THRESHOLD = 0.03
MIN_TRAIN_SAMPLES = 300

GAN_TARGET_CLASSES = [
    "DoS Hulk - Attempted", "Web Attack - XSS - Attempted", "Bot",
    "Web Attack - Brute Force - Attempted", "Bot - Attempted",
    "DoS slowloris - Attempted", "DoS Slowhttptest", "SSH-Patator",
    "DoS Slowhttptest - Attempted", "FTP-Patator", "DoS slowloris", "DoS GoldenEye",
]

# After training (see results/gan_full_diagnostics.json, METRICS_HISTORY.md's Stage 3 entry),
# 3 of the 12 GAN_TARGET_CLASSES came back flagged `likely_overdispersed`: the generator had
# not learned their real (sometimes tightly-clustered) distribution and was producing
# statistically implausible, far-more-scattered-than-real synthetic samples for them
# (Bot - Attempted: ~3000x; DoS slowloris - Attempted: ~11x; FTP-Patator: ~3.2x, borderline).
# Decision (made explicitly, not silently): exclude these from admission into any downstream
# augmented training set, mirroring the existing rare-but-not-modelable exclusion pattern below
# -- a class this GAN doesn't yet model faithfully shouldn't have its synthetic output trusted
# just because it cleared the "not literally mode-collapsed" bar. The trained generator and its
# diagnostics are kept (not deleted) as evidence; this can be revisited with a retrain (more
# epochs / different LR / more critic steps) without redoing Stage 1/2.
GAN_ADMIT_CLASSES = [
    c for c in GAN_TARGET_CLASSES
    if c not in ("Bot - Attempted", "DoS slowloris - Attempted", "FTP-Patator")
]

CHECKPOINT_DIR = Path(__file__).parent.parent / "checkpoints" / "gan_full"
RESULTS_DIR = Path(__file__).parent.parent / "results"

LATENT_DIM = 32
GEN_HIDDEN = [256, 256, 128]
CRITIC_HIDDEN = [256, 256, 128]

MAX_EPOCHS = 80
BATCH_SIZE = 64
N_CRITIC = 5
GRAD_PENALTY_WEIGHT = 10.0
PLATEAU_WINDOW = 8
PLATEAU_STD_THRESHOLD = 0.05  # rolling std of mean generator loss below this -> converged


class Generator(nn.Module):
    def __init__(self, n_features, n_classes):
        super().__init__()
        dims = [LATENT_DIM + n_classes] + GEN_HIDDEN
        layers = []
        for i in range(len(dims) - 1):
            layers += [nn.Linear(dims[i], dims[i + 1]), nn.LeakyReLU(0.2)]
        layers.append(nn.Linear(dims[-1], n_features))
        self.net = nn.Sequential(*layers)

    def forward(self, z, class_onehot):
        return self.net(torch.cat([z, class_onehot], dim=1))


class Critic(nn.Module):
    """No batch norm: batch norm's cross-sample dependence conflicts with the gradient-penalty
    term's per-sample gradient assumption (standard WGAN-GP guidance). Layer norm instead,
    which normalizes per-sample and doesn't have this issue."""

    def __init__(self, n_features, n_classes):
        super().__init__()
        dims = [n_features + n_classes] + CRITIC_HIDDEN
        layers = []
        for i in range(len(dims) - 1):
            layers += [nn.Linear(dims[i], dims[i + 1]), nn.LayerNorm(dims[i + 1]),
                       nn.LeakyReLU(0.2)]
        layers.append(nn.Linear(dims[-1], 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x, class_onehot):
        return self.net(torch.cat([x, class_onehot], dim=1))


def _onehot(labels, n_classes, device):
    return torch.eye(n_classes, device=device)[labels]


def gradient_penalty(critic, real, fake, class_onehot, device):
    alpha = torch.rand(real.size(0), 1, device=device)
    interp = (alpha * real + (1 - alpha) * fake).requires_grad_(True)
    scores = critic(interp, class_onehot)
    grads = torch.autograd.grad(
        outputs=scores, inputs=interp, grad_outputs=torch.ones_like(scores),
        create_graph=True, retain_graph=True)[0]
    return ((grads.norm(2, dim=1) - 1) ** 2).mean()


def mean_pairwise_distance(X, max_n=200, seed=0):
    """Diversity diagnostic: mean pairwise Euclidean distance within a sample set. A generator
    that has mode-collapsed produces near-identical samples -> near-zero pairwise distance."""
    rng = np.random.default_rng(seed)
    if len(X) > max_n:
        idx = rng.choice(len(X), max_n, replace=False)
        X = X[idx]
    if len(X) < 2:
        return float("nan")
    diffs = X[:, None, :] - X[None, :, :]
    dists = np.sqrt((diffs ** 2).sum(axis=-1))
    iu = np.triu_indices(len(X), k=1)
    return float(dists[iu].mean())


class WGANGPFull:
    def __init__(self, n_features, class_labels, feature_mean, feature_std, device=None):
        if device is None:
            if not torch.cuda.is_available():
                raise RuntimeError(
                    "CUDA is not available -- refusing to silently train on CPU. This repo's "
                    "absolute rule (see CLAUDE.md) is GPU-only training. Check "
                    "`torch.cuda.is_available()` and fix the torch install "
                    "(uv pip install --python .venv/bin/python torch "
                    "--extra-index-url https://download.pytorch.org/whl/cu128) if it reports "
                    "False on a machine that has a GPU (nvidia-smi should confirm one). Pass "
                    "device='cpu' explicitly only for local unit testing on a GPU-less machine.")
            device = "cuda"
        self.device = torch.device(device)
        self.n_features = n_features
        self.class_labels = list(class_labels)
        self.n_classes = len(self.class_labels)
        self.label_to_idx = {c: i for i, c in enumerate(self.class_labels)}
        self.feature_mean = feature_mean
        self.feature_std = np.where(feature_std == 0, 1.0, feature_std)

        self.G = Generator(n_features, self.n_classes).to(self.device)
        self.D = Critic(n_features, self.n_classes).to(self.device)
        self.opt_G = optim.Adam(self.G.parameters(), lr=1e-4, betas=(0.5, 0.9))
        self.opt_D = optim.Adam(self.D.parameters(), lr=1e-4, betas=(0.5, 0.9))
        self.loss_log = []  # [{epoch, step, g_loss, d_loss}]
        self._step = 0

    def _normalize(self, X):
        return (X - self.feature_mean) / self.feature_std

    def _denormalize(self, X):
        return X * self.feature_std + self.feature_mean

    def train_one_epoch(self, X_norm, y, epoch, idx_by_class, steps_per_epoch):
        g_losses, d_losses = [], []
        available_classes = [c for c in self.class_labels if c in idx_by_class and len(idx_by_class[c]) > 0]
        if not available_classes:
            return 0.0, 0.0
        for _ in range(steps_per_epoch):
            d_loss_val = None
            for _ in range(N_CRITIC):
                batch_labels = np.random.choice(available_classes, size=BATCH_SIZE)
                batch_idx_local = [self.label_to_idx[c] for c in batch_labels]
                real_rows = np.stack([
                    X_norm[np.random.choice(idx_by_class[c])] for c in batch_labels])
                real = torch.tensor(real_rows, dtype=torch.float32, device=self.device)
                cls_oh = _onehot(torch.tensor(batch_idx_local, device=self.device),
                                  self.n_classes, self.device)

                z = torch.randn(BATCH_SIZE, LATENT_DIM, device=self.device)
                fake = self.G(z, cls_oh).detach()

                self.opt_D.zero_grad()
                d_real = self.D(real, cls_oh).mean()
                d_fake = self.D(fake, cls_oh).mean()
                gp = gradient_penalty(self.D, real, fake, cls_oh, self.device)
                d_loss = d_fake - d_real + GRAD_PENALTY_WEIGHT * gp
                d_loss.backward()
                self.opt_D.step()
                d_loss_val = d_loss.item()

            z = torch.randn(BATCH_SIZE, LATENT_DIM, device=self.device)
            batch_labels = np.random.choice(available_classes, size=BATCH_SIZE)
            batch_idx_local = [self.label_to_idx[c] for c in batch_labels]
            cls_oh = _onehot(torch.tensor(batch_idx_local, device=self.device),
                              self.n_classes, self.device)
            self.opt_G.zero_grad()
            fake = self.G(z, cls_oh)
            g_loss = -self.D(fake, cls_oh).mean()
            g_loss.backward()
            self.opt_G.step()

            self._step += 1
            g_losses.append(g_loss.item())
            d_losses.append(d_loss_val)
            self.loss_log.append({"epoch": epoch, "step": self._step,
                                   "g_loss": g_loss.item(), "d_loss": d_loss_val})
        return float(np.mean(g_losses)), float(np.mean(d_losses))

    def generate_synthetic_batch(self, class_label, n_samples):
        self.G.eval()
        with torch.no_grad():
            z = torch.randn(n_samples, LATENT_DIM, device=self.device)
            idx = self.label_to_idx[class_label]
            cls_oh = _onehot(torch.full((n_samples,), idx, device=self.device),
                              self.n_classes, self.device)
            fake = self.G(z, cls_oh).cpu().numpy()
        self.G.train()
        return self._denormalize(fake)

    def save_checkpoint(self, epoch, path):
        torch.save({
            "epoch": epoch, "generator": self.G.state_dict(), "critic": self.D.state_dict(),
            "opt_g": self.opt_G.state_dict(), "opt_d": self.opt_D.state_dict(),
            "class_labels": self.class_labels, "feature_mean": self.feature_mean,
            "feature_std": self.feature_std,
        }, path)


def run_stage2(max_epochs=MAX_EPOCHS):
    t_start = time.time()
    from proteus.data_full import load_data_full
    log.info("Loading full CICIDS2017 data (Stage 1)...")
    d = load_data_full()
    X_train, y_train = d["X_train"], d["y_train"]
    X_val, y_val = d["X_val"], d["y_val"]
    class_names = d["class_names"]
    name_to_idx = {c: i for i, c in enumerate(class_names)}

    target_idx = [name_to_idx[c] for c in GAN_TARGET_CLASSES if c in name_to_idx]
    missing = [c for c in GAN_TARGET_CLASSES if c not in name_to_idx]
    if missing:
        log.warning(f"GAN_TARGET_CLASSES not found in this run's label set (skipped): {missing}")

    train_counts = {class_names[i]: int((y_train == i).sum()) for i in target_idx}
    log.info(f"GAN target classes (train-split counts): {train_counts}")

    mask = np.isin(y_train, target_idx)
    X_target = X_train[mask].astype(np.float32)
    y_target = y_train[mask]
    val_mask = np.isin(y_val, target_idx)
    X_val_target = X_val[val_mask].astype(np.float32)
    y_val_target = y_val[val_mask]

    feature_mean = X_target.mean(axis=0)
    feature_std = X_target.std(axis=0)
    n_features = X_target.shape[1]

    # Free the full 1.47M-row arrays -- only the ~21k target-class rows are needed from here on.
    del X_train, y_train, X_val, y_val, d
    gc.collect()
    log.info(f"Freed full training arrays; training set for GAN: {len(X_target):,} rows "
             f"across {len(target_idx)} classes")

    gan = WGANGPFull(n_features, target_idx, feature_mean, feature_std)
    gan.class_names_by_idx = class_names  # for reporting only

    idx_by_class = {c: np.where(y_target == c)[0] for c in target_idx}
    X_norm = gan._normalize(X_target)
    steps_per_epoch = max(50, len(X_target) // BATCH_SIZE)
    log.info(f"steps_per_epoch={steps_per_epoch}  n_critic={N_CRITIC}  batch_size={BATCH_SIZE}")

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    epoch_g_losses = []
    stopped_reason = None
    epoch = 0
    for epoch in range(1, max_epochs + 1):
        t0 = time.time()
        g_mean, d_mean = gan.train_one_epoch(X_norm, y_target, epoch, idx_by_class,
                                              steps_per_epoch)
        dt = time.time() - t0
        epoch_g_losses.append(g_mean)
        log.info(f"epoch {epoch:3d}/{max_epochs}  g_loss={g_mean:8.4f}  d_loss={d_mean:8.4f}  "
                 f"({dt:.1f}s)")

        gan.save_checkpoint(epoch, CHECKPOINT_DIR / f"epoch_{epoch}.pt")
        # Keep only the 3 most recent checkpoints on disk to bound disk usage.
        ckpts = sorted(CHECKPOINT_DIR.glob("epoch_*.pt"),
                        key=lambda p: int(p.stem.split("_")[1]))
        for old in ckpts[:-3]:
            old.unlink()

        if epoch >= PLATEAU_WINDOW:
            recent = epoch_g_losses[-PLATEAU_WINDOW:]
            if float(np.std(recent)) < PLATEAU_STD_THRESHOLD:
                stopped_reason = (f"generator loss plateaued: std over last {PLATEAU_WINDOW} "
                                   f"epochs = {np.std(recent):.4f} < {PLATEAU_STD_THRESHOLD}")
                log.info(f"Stopping early at epoch {epoch}: {stopped_reason}")
                break
    else:
        stopped_reason = f"reached max_epochs={max_epochs} without loss plateau"

    # ---- mode-collapse / diversity diagnostics on the final generator ----
    diagnostics = {}
    for c in target_idx:
        cname = class_names[c]
        real_val = X_val_target[y_val_target == c]
        n_sample = min(200, max(2, len(real_val)))
        synth = gan.generate_synthetic_batch(c, n_samples=n_sample)
        real_div = mean_pairwise_distance(real_val) if len(real_val) >= 2 else float("nan")
        synth_div = mean_pairwise_distance(synth)
        ratio = synth_div / real_div if real_div and not np.isnan(real_div) and real_div > 0 \
            else float("nan")
        # Mode collapse (ratio << 1, generator producing near-identical samples) is the
        # classic failure mode this diagnostic was built to catch. But the opposite failure --
        # the generator producing samples far MORE scattered than the real distribution, i.e.
        # not learning the real (possibly tightly-clustered) distribution at all and instead
        # emitting near-random output in feature space -- is just as real a quality problem and
        # was going undetected: a class could show ratio=2900 (wildly over-dispersed, clearly
        # not modeling the real distribution) and this diagnostic would report nothing wrong.
        # 3.0 is the symmetric counterpart to the 0.3 mode-collapse threshold (roughly 1/0.3).
        likely_mode_collapse = bool(not np.isnan(ratio) and ratio < 0.3)
        likely_overdispersed = bool(not np.isnan(ratio) and ratio > 3.0)
        diagnostics[cname] = {
            "n_val_real": int(len(real_val)), "n_synth_checked": int(n_sample),
            "real_diversity_mean_pairwise_dist": real_div,
            "synth_diversity_mean_pairwise_dist": synth_div,
            "synth_to_real_diversity_ratio": ratio,
            "likely_mode_collapse": likely_mode_collapse,
            "likely_overdispersed": likely_overdispersed,
        }
        flag = ("  <-- POSSIBLE MODE COLLAPSE" if likely_mode_collapse else
                "  <-- OVER-DISPERSED (not modeling real distribution)" if likely_overdispersed
                else "")
        log.info(f"  diversity[{cname}]: real={real_div:.3f} synth={synth_div:.3f} "
                 f"ratio={ratio:.3f}{flag}")

    summary = {
        "epochs_run": epoch,
        "max_epochs": max_epochs,
        "stopped_reason": stopped_reason,
        "wall_clock_seconds": time.time() - t_start,
        "steps_per_epoch": steps_per_epoch,
        "gan_target_classes": [class_names[i] for i in target_idx],
        "train_counts_per_target_class": train_counts,
        "final_epoch_g_loss": epoch_g_losses[-1] if epoch_g_losses else None,
        "final_epoch_g_loss_window_std": float(np.std(epoch_g_losses[-PLATEAU_WINDOW:]))
            if len(epoch_g_losses) >= PLATEAU_WINDOW else None,
        "diversity_diagnostics": diagnostics,
    }
    with open(RESULTS_DIR / "gan_full_diagnostics.json", "w") as f:
        json.dump(summary, f, indent=2)
    with open(RESULTS_DIR / "gan_full_loss_log.json", "w") as f:
        json.dump(gan.loss_log, f)

    log.info(f"\nDone. epochs_run={epoch} wall_clock={summary['wall_clock_seconds']:.1f}s "
              f"stopped_reason={stopped_reason!r}")
    return summary


if __name__ == "__main__":
    run_stage2()
