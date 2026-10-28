# -*- coding: utf-8 -*-
"""U4: reentrenar Kronos como sus autores (finetune/), en un solo proceso, con el S&P 500 en vez del CSI 300.

Los bucles son copia de `finetune/train_tokenizer.py` y `finetune/train_predictor.py` sin la parte distribuida (en
Windows no hay NCCL): mismos optimizadores, programadores, recortes, pérdidas y elección del mejor modelo por la pérdida
de validación. Su `QlibDataset` se usa tal cual, con la configuración inyectada. Diferencias declaradas: un proceso
(no 2 cargadores) y un punto de control por época para poder reanudar.

    python -m tiresias.reentrenar preparar --velas <dir con velas_*.csv y simbolos.json> --salida <dir>
    python -m tiresias.reentrenar tokenizador --dir <dir> --dispositivo cuda
    python -m tiresias.reentrenar predictor --dir <dir> --dispositivo cuda
    python -m tiresias.reentrenar medir --dir <dir> --dispositivo cuda        (segundos por lote, para el presupuesto)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import pickle
import sys
import time
import types

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

from tiresias import modelo as M

REPO = pathlib.Path(__file__).resolve().parent.parent
ENTRENA = ("2011-01-01", "2022-12-31")              # como sus autores
VALIDA = ("2022-09-01", "2024-06-30")               # ídem, con su solape; nada posterior al fin del preentrenamiento
COLS = ["open", "high", "low", "close", "vol", "amt"]


class Config:
    """Lo que leen su QlibDataset y sus bucles (finetune/config.py), con nuestros datos."""

    def __init__(self, dataset_path: str, epocas: int = 30, lote: int = 50, acumulacion: int = 1):
        self.dataset_path = dataset_path
        self.lookback_window, self.predict_window, self.max_context = 90, 10, 512
        self.feature_list = COLS
        self.time_feature_list = ["minute", "hour", "weekday", "day", "month"]
        self.clip, self.epochs, self.log_interval = 5.0, epocas, 100
        self.batch_size, self.accumulation_steps = lote, acumulacion
        self.n_train_iter, self.n_val_iter = 2000 * 50, 400 * 50        # muestras por época: las suyas, sea cual sea el lote
        self.tokenizer_learning_rate, self.predictor_learning_rate = 2e-4, 4e-5
        self.adam_beta1, self.adam_beta2, self.adam_weight_decay = 0.9, 0.95, 0.1
        self.seed = 100


def _dataset(cfg: Config, tipo: str):
    """Su QlibDataset, con nuestra configuración en el `from config import Config` que hace."""
    sys.modules["config"] = types.SimpleNamespace(Config=lambda: cfg)       # type: ignore[assignment]
    sys.path.insert(0, str(REPO / "finetune"))
    import dataset as D                                                     # noqa: E402  (su finetune/dataset.py)
    return D.QlibDataset(tipo)


# ── datos ────────────────────────────────────────────────────────────────
def preparar(velas: pathlib.Path, salida: pathlib.Path) -> dict:
    """train_data.pkl y val_data.pkl en su formato: {símbolo: DataFrame con índice «datetime» y COLS}. Nada después del
    2024-06-30."""
    info = json.loads((velas / "simbolos.json").read_text(encoding="utf-8"))
    out = {"train": {}, "val": {}}
    for s in info["simbolos"]:
        v = pd.read_csv(velas / f"velas_{s}.csv", index_col=0, parse_dates=True, float_precision="round_trip")
        df = pd.DataFrame({"open": v["open"], "high": v["high"], "low": v["low"], "close": v["close"],
                           "vol": v["volume"].fillna(0.0)}, index=v.index)
        df["amt"] = df["vol"] * df[["open", "high", "low", "close"]].mean(axis=1)    # como KronosPredictor
        df.index.name = "datetime"
        df = df.dropna()
        for nombre, (a, b) in (("train", ENTRENA), ("val", VALIDA)):
            trozo = df.loc[a:b]
            if len(trozo) >= 101:
                out[nombre][s] = trozo
    salida.mkdir(parents=True, exist_ok=True)
    for nombre in out:
        with open(salida / f"{nombre}_data.pkl", "wb") as f:
            pickle.dump(out[nombre], f)
    ult = max(d.index.max() for d in out["val"].values())
    if ult > pd.Timestamp(VALIDA[1]):
        raise SystemExit(f"⛔ hay datos posteriores al fin del preentrenamiento: {ult}")
    r = {"valores_train": len(out["train"]), "valores_val": len(out["val"]), "ultima_fecha": str(ult.date())}
    (salida / "preparacion.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    return r


# ── los bucles, copia de los suyos ───────────────────────────────────────
def _cargadores(cfg: Config):
    from torch.utils.data import DataLoader
    tr, va = _dataset(cfg, "train"), _dataset(cfg, "val")
    return (DataLoader(tr, batch_size=cfg.batch_size, shuffle=False, num_workers=0, pin_memory=True, drop_last=True),
            DataLoader(va, batch_size=cfg.batch_size, shuffle=False, num_workers=0, pin_memory=True), tr, va)


def _reanudar(ruta: pathlib.Path, modelo, opt, sch, epocas: int) -> tuple:
    if not ruta.exists():
        return 0, float("inf"), []
    e = torch.load(ruta, map_location="cpu", weights_only=False)
    if e["epocas"] != epocas:            # OneCycle fija los pasos totales al crearse: no se reanuda con otro plan
        raise SystemExit(f"⛔ el punto de control es de {e['epocas']} épocas y se piden {epocas}")
    modelo.load_state_dict(e["modelo"])
    opt.load_state_dict(e["opt"])
    sch.load_state_dict(e["sch"])
    return e["epoca"] + 1, e["mejor"], e["historial"]


def tokenizador(cfg: Config, dispositivo: str, salida: pathlib.Path, max_lotes: int | None = None,
                hasta: int | None = None) -> dict:
    tok, _ = M.cargar("small", dispositivo)
    tl, vl, tr, va = _cargadores(cfg)
    opt = torch.optim.AdamW(tok.parameters(), lr=cfg.tokenizer_learning_rate, weight_decay=cfg.adam_weight_decay)
    sch = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.tokenizer_learning_rate, steps_per_epoch=len(tl),
                                              epochs=cfg.epochs, pct_start=0.03, div_factor=10)
    pc = salida / "tokenizador_ultimo.pt"
    ini, mejor, hist = _reanudar(pc, tok, opt, sch, cfg.epochs)
    for ep in range(ini, hasta or cfg.epochs):
        t0 = time.time()
        tok.train()
        tr.set_epoch_seed(ep * 10000)
        va.set_epoch_seed(0)
        perdidas = []
        for i, (x, _) in enumerate(tl):
            x = x.to(dispositivo, non_blocking=True)
            total = 0.0
            for j in range(cfg.accumulation_steps):
                b = x[j * (x.shape[0] // cfg.accumulation_steps):(j + 1) * (x.shape[0] // cfg.accumulation_steps)]
                zs, bsq, _, _ = tok(b)
                z_pre, z = zs
                loss = (F.mse_loss(z_pre, b) + F.mse_loss(z, b) + bsq) / 2
                (loss / cfg.accumulation_steps).backward()
                total += loss.item()
            torch.nn.utils.clip_grad_norm_(tok.parameters(), max_norm=2.0)
            opt.step()
            sch.step()
            opt.zero_grad()
            perdidas.append(total / cfg.accumulation_steps)
            if max_lotes and i + 1 >= max_lotes:
                break
        tok.eval()
        suma, n = 0.0, 0
        with torch.no_grad():
            for k, (x, _) in enumerate(vl):
                x = x.to(dispositivo, non_blocking=True)
                zs, _, _, _ = tok(x)
                suma += F.mse_loss(zs[1], x).item() * x.size(0)
                n += x.size(0)
                if max_lotes and k + 1 >= max_lotes:
                    break
        val = suma / n
        if val < mejor:
            mejor = val
            tok.save_pretrained(str(salida / "tokenizador_mejor"))
        hist.append({"epoca": ep + 1, "train": float(np.mean(perdidas)), "val": val, "segundos": time.time() - t0})
        torch.save({"modelo": tok.state_dict(), "opt": opt.state_dict(), "sch": sch.state_dict(), "epoca": ep,
                    "mejor": mejor, "historial": hist, "epocas": cfg.epochs}, pc)
        print(f"tokenizador época {ep + 1}/{cfg.epochs}: train {hist[-1]['train']:.4f} val {val:.4f} "
              f"(mejor {mejor:.4f}) en {hist[-1]['segundos']:.0f} s", flush=True)
    return {"mejor_val": mejor, "historial": hist}


def predictor(cfg: Config, dispositivo: str, salida: pathlib.Path, max_lotes: int | None = None,
              hasta: int | None = None) -> dict:
    from model import Kronos, KronosTokenizer
    tok = KronosTokenizer.from_pretrained(str(salida / "tokenizador_mejor")).eval().to(dispositivo)
    repo, rev = M.MODELOS["small"]
    mod = Kronos.from_pretrained(repo, revision=rev).to(dispositivo)
    tl, vl, tr, va = _cargadores(cfg)
    opt = torch.optim.AdamW(mod.parameters(), lr=cfg.predictor_learning_rate, betas=(cfg.adam_beta1, cfg.adam_beta2),
                            weight_decay=cfg.adam_weight_decay)
    sch = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.predictor_learning_rate, steps_per_epoch=len(tl),
                                              epochs=cfg.epochs, pct_start=0.03, div_factor=10)
    pc = salida / "predictor_ultimo.pt"
    ini, mejor, hist = _reanudar(pc, mod, opt, sch, cfg.epochs)
    for ep in range(ini, hasta or cfg.epochs):
        t0 = time.time()
        mod.train()
        tr.set_epoch_seed(ep * 10000)
        va.set_epoch_seed(0)
        perdidas = []
        for i, (x, xs) in enumerate(tl):
            x, xs = x.to(dispositivo, non_blocking=True), xs.to(dispositivo, non_blocking=True)
            with torch.no_grad():
                s0, s1 = tok.encode(x, half=True)
            logits = mod(s0[:, :-1], s1[:, :-1], xs[:, :-1, :])
            loss, _, _ = mod.head.compute_loss(logits[0], logits[1], s0[:, 1:], s1[:, 1:])
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(mod.parameters(), max_norm=3.0)
            opt.step()
            sch.step()
            perdidas.append(loss.item())
            if max_lotes and i + 1 >= max_lotes:
                break
        mod.eval()
        suma, n = 0.0, 0
        with torch.no_grad():
            for k, (x, xs) in enumerate(vl):
                x, xs = x.to(dispositivo, non_blocking=True), xs.to(dispositivo, non_blocking=True)
                s0, s1 = tok.encode(x, half=True)
                logits = mod(s0[:, :-1], s1[:, :-1], xs[:, :-1, :])
                suma += mod.head.compute_loss(logits[0], logits[1], s0[:, 1:], s1[:, 1:])[0].item()
                n += 1
                if max_lotes and k + 1 >= max_lotes:
                    break
        val = suma / n
        if val < mejor:
            mejor = val
            mod.save_pretrained(str(salida / "predictor_mejor"))
        hist.append({"epoca": ep + 1, "train": float(np.mean(perdidas)), "val": val, "segundos": time.time() - t0})
        torch.save({"modelo": mod.state_dict(), "opt": opt.state_dict(), "sch": sch.state_dict(), "epoca": ep,
                    "mejor": mejor, "historial": hist, "epocas": cfg.epochs}, pc)
        print(f"predictor época {ep + 1}/{cfg.epochs}: train {hist[-1]['train']:.4f} val {val:.4f} "
              f"(mejor {mejor:.4f}) en {hist[-1]['segundos']:.0f} s", flush=True)
    return {"mejor_val": mejor, "historial": hist}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("orden", choices=["preparar", "tokenizador", "predictor", "medir"])
    ap.add_argument("--velas")
    ap.add_argument("--dir", "--salida", dest="dir", required=True)
    ap.add_argument("--dispositivo", default="cuda")
    ap.add_argument("--epocas", type=int, default=30)
    ap.add_argument("--lote", type=int, default=50)
    ap.add_argument("--acumulacion", type=int, default=1)
    a = ap.parse_args(argv)
    d = pathlib.Path(a.dir).expanduser()
    if a.orden == "preparar":
        print(preparar(pathlib.Path(a.velas).expanduser(), d))
        return 0
    torch.manual_seed(100)
    cfg = Config(str(d), a.epocas, a.lote, a.acumulacion)
    if a.orden == "medir":
        import shutil
        cfg.epochs = 1
        sub = d / "medida"
        shutil.rmtree(sub, ignore_errors=True)                  # sin punto de control viejo: si no, «reanuda» y no mide
        sub.mkdir()
        for nombre, f in (("tokenizador", tokenizador), ("predictor", predictor)):
            seg = f(cfg, a.dispositivo, sub, max_lotes=20)["historial"][-1]["segundos"] / 40
            print(f"{nombre}: {seg:.3f} s por lote (media de 20 de entrenamiento y 20 de validación, sin cargas) · "
                  f"30 épocas de 2.000 + 400 lotes ≈ {seg * 2400 * 30 / 3600:.1f} h", flush=True)
        return 0
    r = (tokenizador if a.orden == "tokenizador" else predictor)(cfg, a.dispositivo, d)
    (d / f"{a.orden}.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
