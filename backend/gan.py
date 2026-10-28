"""Small conditional WGAN-GP for minority-class attack synthesis."""
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

LATENT_DIM = 16
HIDDEN = 96


class Generator(nn.Module):
    def __init__(self, n_features, n_classes):
        super().__init__()
        self.n_classes = n_classes
        self.net = nn.Sequential(
            nn.Linear(LATENT_DIM + n_classes, HIDDEN), nn.ReLU(),
            nn.Linear(HIDDEN, HIDDEN), nn.ReLU(),
            nn.Linear(HIDDEN, n_features),
        )

    def forward(self, z, class_onehot):
        return self.net(torch.cat([z, class_onehot], dim=1))


class Critic(nn.Module):
    def __init__(self, n_features, n_classes):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features + n_classes, HIDDEN), nn.LeakyReLU(0.2),
            nn.Linear(HIDDEN, HIDDEN), nn.LeakyReLU(0.2),
            nn.Linear(HIDDEN, 1),
        )

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
    gp = ((grads.norm(2, dim=1) - 1) ** 2).mean()
    return gp


class WGANGP:
    def __init__(self, n_features, class_labels, feature_mean, feature_std, device="cpu"):
        """class_labels: the set of minority-class integer labels this GAN is trained on."""
        self.device = torch.device(device)
        self.n_features = n_features
        self.class_labels = list(class_labels)
        self.n_classes = len(self.class_labels)
        self.label_to_idx = {c: i for i, c in enumerate(self.class_labels)}
        self.feature_mean = feature_mean
        self.feature_std = np.where(feature_std == 0, 1.0, feature_std)

        self.G = Generator(n_features, self.n_classes).to(self.device)
        self.D = Critic(n_features, self.n_classes).to(self.device)
        self.opt_G = optim.Adam(self.G.parameters(), lr=2e-4, betas=(0.5, 0.9))
        self.opt_D = optim.Adam(self.D.parameters(), lr=2e-4, betas=(0.5, 0.9))
        self.loss_log = []  # list of {step, g_loss, d_loss}
        self._step = 0

    def _normalize(self, X):
        return (X - self.feature_mean) / self.feature_std

    def _denormalize(self, X):
        return X * self.feature_std + self.feature_mean

    def train(self, X, y, n_steps=300, batch_size=32, n_critic=3, log_every=1):
        X_norm = self._normalize(X)
        idx_by_class = {c: np.where(y == c)[0] for c in self.class_labels}
        for c, idxs in idx_by_class.items():
            if len(idxs) == 0:
                raise ValueError(f"no samples for class {c}")

        for step in range(n_steps):
            d_loss_val = None
            for _ in range(n_critic):
                batch_labels = np.random.choice(self.class_labels, size=batch_size)
                batch_idx_local = [self.label_to_idx[c] for c in batch_labels]
                real_rows = np.stack([
                    X_norm[np.random.choice(idx_by_class[c])] for c in batch_labels])
                real = torch.tensor(real_rows, dtype=torch.float32, device=self.device)
                cls_oh = _onehot(torch.tensor(batch_idx_local, device=self.device),
                                  self.n_classes, self.device)

                z = torch.randn(batch_size, LATENT_DIM, device=self.device)
                fake = self.G(z, cls_oh).detach()

                self.opt_D.zero_grad()
                d_real = self.D(real, cls_oh).mean()
                d_fake = self.D(fake, cls_oh).mean()
                gp = gradient_penalty(self.D, real, fake, cls_oh, self.device)
                d_loss = d_fake - d_real + 10.0 * gp
                d_loss.backward()
                self.opt_D.step()
                d_loss_val = d_loss.item()

            z = torch.randn(batch_size, LATENT_DIM, device=self.device)
            batch_labels = np.random.choice(self.class_labels, size=batch_size)
            batch_idx_local = [self.label_to_idx[c] for c in batch_labels]
            cls_oh = _onehot(torch.tensor(batch_idx_local, device=self.device),
                              self.n_classes, self.device)
            self.opt_G.zero_grad()
            fake = self.G(z, cls_oh)
            g_loss = -self.D(fake, cls_oh).mean()
            g_loss.backward()
            self.opt_G.step()

            self._step += 1
            if step % log_every == 0:
                self.loss_log.append({"step": self._step, "g_loss": g_loss.item(),
                                       "d_loss": d_loss_val})
        return self.loss_log[-1] if self.loss_log else None

    def retrain(self, X_recent, y_recent, extra_steps=30, batch_size=16):
        """Resume training (not from scratch) on a recent data window."""
        return self.train(X_recent, y_recent, n_steps=extra_steps, batch_size=batch_size,
                           n_critic=2)

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
