"""Paper-style comparison tables (booktabs look) as one PNG: published rPPG models vs our rppg1 PhysFormer.
Best value per column (within a comparable group) is bold; our rows are shaded.

    python -m bench.tables_figure          (from rppg1/)  -> runs/comparison_tables.png
"""
import json
import os
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from bench.preprocess import ROOT  # noqa: E402

RES = os.path.join(ROOT, "runs", "results")
OUT = os.path.join(ROOT, "runs", "comparison_tables.png")
SHADE = "#e8eef7"


def ours(name):
    m = json.load(open(os.path.join(RES, name + ".json")))["metrics"]
    return m["MAE"], m["RMSE"], m["MAPE"], m["Pearson"], 100 * m["within_5bpm"]


def draw(ax, title, caption, header, groups, better, fmt="{:.2f}", first=(0.30, 0.16)):
    """groups: list of (group label or None, rows); a row is (name, train, values..., is_ours).
    better: per value column 'min', 'max' or None. Best is found within each group."""
    ax.axis("off")
    ncol = len(header)
    widths = list(first) + [(1 - sum(first)) / (ncol - 2)] * (ncol - 2)
    xs = [sum(widths[:i]) for i in range(ncol)]
    nrows = sum(len(r) + (1 if g else 0) for g, r in groups) + 1
    h = 1.0 / (nrows + 0.6)
    y = 1.0

    def rule(yy, lw):
        ax.plot([0, 1], [yy, yy], color="black", lw=lw, transform=ax.transAxes, clip_on=False)

    ax.text(0, 1.0 + 0.9 * h, title, transform=ax.transAxes, fontsize=11.5, fontweight="bold", va="bottom")
    rule(y, 1.4)
    y -= h
    for i, c in enumerate(header):
        ax.text(xs[i] + (0.005 if i < 2 else widths[i] / 2), y + h / 2, c, transform=ax.transAxes, fontsize=9.5,
                fontweight="bold", va="center", ha="left" if i < 2 else "center")
    rule(y, 0.8)
    for g, rows in groups:
        if g:
            y -= h
            ax.text(0.005, y + h / 2, g, transform=ax.transAxes, fontsize=9, style="italic", va="center",
                    color="#333333")
        best = {}
        for j, b in enumerate(better):
            vals = [r[2 + j] for r in rows if isinstance(r[2 + j], (int, float))]
            if b and vals:
                best[j] = min(vals) if b == "min" else max(vals)
        for r in rows:
            y -= h
            if r[-1]:
                ax.add_patch(plt.Rectangle((0, y), 1, h, transform=ax.transAxes, color=SHADE, zorder=0, lw=0))
            ax.text(0.005, y + h / 2, r[0], transform=ax.transAxes, fontsize=9.5, va="center",
                    fontweight="bold" if r[-1] else "normal")
            ax.text(xs[1] + 0.005, y + h / 2, r[1], transform=ax.transAxes, fontsize=9.5, va="center")
            for j, v in enumerate(r[2:-1]):
                isnum = isinstance(v, (int, float))
                txt = ("{:.0f}" if "%" in header[2 + j] else fmt).format(v) if isnum else v
                bold = isnum and j in best and abs(v - best[j]) < 1e-9
                ax.text(xs[2 + j] + widths[2 + j] / 2, y + h / 2, txt, transform=ax.transAxes, fontsize=9.5,
                        va="center", ha="center", fontweight="bold" if bold else "normal",
                        color="black" if isnum else "#777777")
        if g is not None and (g, rows) != groups[-1]:
            rule(y, 0.5)
    rule(y, 1.4)
    caption = "\n".join(textwrap.fill(c, 125) for c in caption.split("\n"))
    ax.text(0, y - 0.35 * h, caption, transform=ax.transAxes, fontsize=8.3, va="top", color="#333333", wrap=True)


def main():
    pf_mcd, pf_ubfc = ours("MCD_MCD"), ours("MCD_UBFC")
    pos_m, chr_m, pos_u, chr_u = (ours(n) for n in
                                  ("POS_mcd_IriunWebcam", "CHROM_mcd_IriunWebcam", "POS_ubfc", "CHROM_ubfc"))
    pf_mp, pos_p, chr_p = ours("MCD_MPSC"), ours("POS_mpsc"), ours("CHROM_mpsc")
    p4_m, p4_u, p4_p = ours("CVPR_P4_e30_MCD"), ours("CVPR_P4_e30_MCD_UBFC"), ours("CVPR_P4_e30_MCD_MPSC")
    d12 = [ours(f"CVPR_P4_d12_e30_MCD{s}") for s in ("", "_UBFC", "_MPSC")]
    aug = [ours(f"CVPR_P4_d12_e30_aug_MCD{s}") for s in ("", "_UBFC", "_MPSC")]
    p_d12 = json.load(open(os.path.join(RES, "CVPR_P4_d12_e30_MCD.json")))["info"]["params"] / 1e6
    # same 40 held-out MCD test videos as PhysFormer (computed from per-video results)
    pos_m40, chr_m40 = 15.67, 15.72

    lad = [("phase1_physformer", "core, tube 2×4×4"), ("phase2_physics", "+ZAS/ASF/GTCN"),
           ("phase3_dualstream", "+STMap/DCEB/SAFD"), ("phase4_frequency", "+FreqPhys")]
    cv = {p: (ours(f"CVPR_{p}_MCD"), ours(f"CVPR_{p}_MCD_UBFC"), ours(f"CVPR_{p}_MCD_MPSC")) for p, _ in lad}
    params = {p: json.load(open(os.path.join(RES, f"CVPR_{p}_MCD.json")))["info"]["params"] / 1e6 for p, _ in lad}

    tables = []

    def table(*args, **kw):
        tables.append((args, kw))

    table("Table 1. Our results (rPPG-Toolbox protocol: whole-video FFT heart rate, bpm)",
         "MCD test = 20 held-out subjects (40 videos, Iriun webcam), subject-disjoint from training. "
         "UBFC = all 42 videos, never seen in training. MPSC = 9 phone videos of 7 subjects, never seen in training; "
         "reference = Empatica E4 wrist BVP, hand-synchronised; HR peak search skips the codec artefact at fps/15 "
         "(119.9 bpm) for every method.\nPOS/CHROM on MCD are on the same 40 test videos. "
         "Bold = best per column within each test set.",
         ["Method", "Train set", "MAE ↓", "RMSE ↓", "MAPE ↓", "ρ ↑", "≤5 bpm % ↑"],
         [("Test: MCD-rPPG (held-out subjects)",
           [("POS", "—", pos_m40, 19.91, "–", 0.32, 28.0, False),
            ("CHROM", "—", chr_m40, 19.17, "–", 0.43, 25.0, False),
            ("PhysFormer (rppg1, ours)", "MCD-rPPG", *pf_mcd, True),
            ("CVPR Lab P4, 30 ep (ours)", "MCD-rPPG", *p4_m, True),
            ("CVPR Lab P4-12 +flip (ours)", "MCD-rPPG", *aug[0], True)]),
          ("Test: UBFC-rPPG (cross-dataset)",
           [("POS", "—", *pos_u, False), ("CHROM", "—", *chr_u, False),
            ("PhysFormer (rppg1, ours)", "MCD-rPPG", *pf_ubfc, True),
            ("CVPR Lab P4, 30 ep (ours)", "MCD-rPPG", *p4_u, True),
            ("CVPR Lab P4-12 +flip (ours)", "MCD-rPPG", *aug[1], True)]),
          ("Test: MPSC-rPPG (cross-dataset, phone camera)",
           [("POS", "—", *pos_p, False), ("CHROM", "—", *chr_p, False),
            ("PhysFormer (rppg1, ours)", "MCD-rPPG", *pf_mp, True),
            ("CVPR Lab P4, 30 ep (ours)", "MCD-rPPG", *p4_p, True),
            ("CVPR Lab P4-12 +flip (ours)", "MCD-rPPG", *aug[2], True)])],
         ["min", "min", "min", "max", "max"])

    table("Table 2. CVPR Lab ablation ladder (trained on MCD-rPPG; HR MAE / RMSE / ρ)",
         "Same protocol as Table 1: 64 train / 16 valid / 20 held-out MCD subjects; UBFC never seen. Each phase adds "
         "the listed modules to the previous one (phases 2–4: 4 transformer blocks; phase 1: 12). Stem TDC off "
         "(input is already DiffNormalized; with it on, phase 2 scored MCD 11.13). MAE / RMSE lower is better, "
         "ρ higher is better; bold = best per column. P2 = ZAS + ASF + physics GTCN; P3 = + STMap branch, DCEB, "
         "SAFD decoder; P4 = + FreqPhys PBF/PSM/ASS and cross-domain fusion. P1–P4 trained 10 epochs; the last three rows = P4 "
         "trained 30 epochs (best validation epoch 29); then the same with 12 transformer blocks, without and with random "
         "horizontal-flip augmentation.",
         ["Model", "Params", "MCD", "RMSE", "ρ", "UBFC", "RMSE", "ρ", "MPSC", "RMSE", "ρ"],
         [(None, [("PhysFormer (rppg1)", "7.70 M", *(t[k] for t in (pf_mcd, pf_ubfc, pf_mp) for k in (0, 1, 3)),
                   False)]
           + [(f"P{i + 1} {d}", f"{params[p]:.2f} M", *(t[k] for t in cv[p] for k in (0, 1, 3)), True)
              for i, (p, d) in enumerate(lad)]
           + [("P4 +FreqPhys, 30 ep", f"{params['phase4_frequency']:.2f} M",
               *(t[k] for t in (p4_m, p4_u, p4_p) for k in (0, 1, 3)), True),
              ("P4, 12 blocks, 30 ep", f"{p_d12:.2f} M", *(t[k] for t in d12 for k in (0, 1, 3)), True),
              ("P4, 12 bl. +flip, 30 ep", f"{p_d12:.2f} M", *(t[k] for t in aug for k in (0, 1, 3)), True)])],
         ["min", "min", "max"] * 3, first=(0.255, 0.085))

    table("Table 3. Models trained on MCD-rPPG (HR MAE, bpm)",
         "Published rows: Egorov et al., MCD-rPPG paper (arXiv 2508.17924), Table 3 – HR per 10-s window, all frontal "
         "cameras, full training split.\nOur rows: toolbox protocol, Iriun webcam only, 64 training subjects. "
         "The two protocols are not directly comparable (see POS on UBFC: 1.17 vs 4.22); bold = best within group.",
         ["Method", "Train set", "MCD-rPPG", "UBFC-rPPG"],
         [("Published (MCD-rPPG paper protocol)",
           [("POS", "—", 3.80, 1.17, False), ("OMIT", "—", 4.78, 1.95, False),
            ("PhysFormer", "MCD-rPPG", 4.08, 1.27, False), ("RhythmFormer", "MCD-rPPG", 2.82, 2.39, False),
            ("iBVPNet", "MCD-rPPG", 4.83, 4.69, False), ("SCNN (MCD authors)", "MCD-rPPG", 4.86, 4.13, False)]),
          ("Ours (rPPG-Toolbox protocol)",
           [("POS", "—", pos_m40, pos_u[0], False), ("CHROM", "—", chr_m40, chr_u[0], False),
            ("PhysFormer (rppg1, ours)", "MCD-rPPG", pf_mcd[0], pf_ubfc[0], True)]
           + [(f"CVPR Lab {p.split('_')[0]} (ours)", "MCD-rPPG", cv[p][0][0], cv[p][1][0], True) for p, _ in lad]
           + [("CVPR Lab P4, 30 ep (ours)", "MCD-rPPG", p4_m[0], p4_u[0], True),
              ("CVPR Lab P4-12 +flip (ours)", "MCD-rPPG", aug[0][0], aug[1][0], True)])],
         ["min", "min"])

    table("Table 4. Cross-dataset: trained on UBFC-rPPG, tested on PURE (HR MAE, bpm)",
         "Source: Zou et al., RhythmFormer (arXiv 2402.12788), Table 3; PhysFormer 12.92 matches rPPG-Toolbox "
         "(Liu et al., NeurIPS 2023).\nOur row is pending the full PURE dataset.",
         ["Method", "Train set", "PURE MAE ↓"],
         [(None, [("Face2PPG (OMIT)", "—", 4.66, False), ("DeepPhys", "UBFC", 5.54, False),
                  ("PhysNet", "UBFC", 8.06, False), ("TS-CAN", "UBFC", 3.69, False),
                  ("PhysFormer", "UBFC", 12.92, False), ("EfficientPhys", "UBFC", 5.47, False),
                  ("Spiking-PhysFormer", "UBFC", 3.83, False), ("RhythmFormer", "UBFC", 0.97, False),
                  ("PhysFormer (rppg1, ours)", "UBFC", "pending", True)])],
         ["min"])

    table("Table 5. Intra-dataset results (HR MAE, bpm)",
         "Source: Zou et al., RhythmMamba (AAAI 2025, arXiv 2404.06483), Table 1. Train and test on the same dataset. "
         "Our intra-dataset result is on MCD-rPPG (Table 1).",
         ["Method", "Type", "PURE", "UBFC", "VIPL-HR", "MMPD"],
         [(None, [("HR-CNN", "CNN", 1.84, 4.90, "–", "–", False), ("DeepPhys", "CNN", 0.83, 6.27, 11.00, 22.27, False),
                  ("PhysNet", "3D-CNN", 2.10, 2.95, 10.80, 4.80, False),
                  ("TS-CAN", "CNN", 2.48, 1.70, "–", 9.71, False),
                  ("Dual-GAN", "GAN", 0.82, 0.44, 4.93, "–", False),
                  ("EfficientPhys", "CNN", "–", 1.14, "–", 13.47, False),
                  ("PhysFormer", "Transformer", 1.10, 0.50, 4.97, 11.99, False),
                  ("PhysFormer++", "Transformer", "–", "–", 4.88, "–", False),
                  ("Contrast-Phys+", "3D-CNN", 0.48, 0.21, "–", "–", False),
                  ("RhythmFormer", "Transformer", 0.27, 0.50, "–", 3.07, False),
                  ("RhythmMamba", "Mamba", 0.23, 0.50, 4.30, 3.16, False)])],
         ["min", "min", "min", "min"])

    table("Table 6. PhysFormer vs PhysFormer++ (Yu et al., IJCV 2023)",
         "Intra-dataset VIPL-HR (MAE / RMSE / ρ) and MAHNOB-HCI. Datasets not available to us.",
         ["Method", "Venue", "VIPL MAE ↓", "VIPL RMSE ↓", "VIPL ρ ↑", "MAHNOB RMSE ↓"],
         [(None, [("PhysFormer", "CVPR 2022", 4.97, 7.79, 0.78, 3.97, False),
                  ("PhysFormer++", "IJCV 2023", 4.88, 7.62, 0.80, 3.88, False)])],
         ["min", "min", "max", "min"])

    ratios = [17, 11.5, 15, 9.5, 12.5, 4.5]
    fig, axes = plt.subplots(6, 1, figsize=(10, 31), gridspec_kw={"height_ratios": ratios, "hspace": 0.42})
    fig.patch.set_facecolor("white")
    for ax, (args, kw) in zip(axes, tables):
        draw(ax, *args, **kw)
    fig.savefig(OUT, dpi=170, bbox_inches="tight", pad_inches=0.35)
    # the full figure is too tall to read once a chat viewer scales it down: also a vector PDF, and each table drawn
    # on its own page (same width, so captions wrap the same way)
    fig.savefig(OUT.replace(".png", ".pdf"), bbox_inches="tight", pad_inches=0.35)
    plt.close(fig)
    for i, (r, (args, kw)) in enumerate(zip(ratios, tables), 1):
        f, ax = plt.subplots(figsize=(10, r * 31 / sum(ratios) * 0.95))
        f.patch.set_facecolor("white")
        draw(ax, *args, **kw)
        f.savefig(OUT.replace(".png", f"_table{i}.png"), dpi=220, bbox_inches="tight", pad_inches=0.3)
        plt.close(f)
    print(OUT)


if __name__ == "__main__":
    main()
