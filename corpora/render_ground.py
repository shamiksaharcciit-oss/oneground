#!/usr/bin/env python3
"""
oneground ground view — the hero image
======================================

Draws the arXiv-150k fixture from the tables `export_ground_view.py` produced,
in four variants. Nothing here computes geometry: every position, region, copy
count and category is read from the parquet files, which were themselves
recomputed from the fixture's receipts and asserted against its published
values. This file only chooses ink.

    python corpora/render_ground.py --dir fixtures/arxiv-150k --out docs/img/

What the picture has to be honest about
---------------------------------------
Build 3 measured boundary crispness 0.036 and an ambiguous-query rate of
0.891: under k-means-256 this embedding space has almost no crisp region
boundaries. Closure at epsilon = 0.20 replicates 84.3% of the corpus to the
four-region cap. A tidy Voronoi diagram would be a lie about this corpus, so
the variants are drawn to let overlap read as overlap — low alpha, no region
outlines, no filled cells.

Variants
    A  by top-level arXiv category
    B  by closure copy count          <- default, the crispness story
    C  by region, 256 colours, low alpha
    D  one query, over B at 30%

Each is written as a 2400x1500 PNG and an SVG. The point cloud is rasterised
inside the SVG (150,000 vector circles would make a file no browser enjoys);
text and rings stay vector.

Deterministic: no jitter, no sampling, no random state. Points are drawn in
table order, which is the order the export wrote them.
"""

import argparse
import json
import os
import time

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pyarrow.parquet as pq
from matplotlib.lines import Line2D

# ---------------------------------------------------------------- palette
SLATE = "#1B2432"          # background
INK = "#E8ECF1"            # primary text
INK_DIM = "#8A97A8"        # secondary text
QUIET_BLUE = "#5F7D9E"     # copies = 1
OCHRE = "#C99A3B"          # copies = 4
CORAL = "#E2725B"          # true neighbours, variant D
WIDTH, HEIGHT, DPI = 2400, 1500, 100
# Point ink. 150k points over this extent are mostly non-overlapping, so
# alpha does more work than size: at 0.45 the ochre read as near-background
# and variant B failed to show the thing it exists to show.
# Tuned by rendering and looking (tasks/scratch/005-tune-ink.py), not guessed.
# The brief suggests ~1-2 px; at that size the ochre read as background and
# variant B failed to show the one thing it exists to show, so points are
# drawn a little larger. s=5.0 is ~3.1 px diameter at dpi 100.
PT_SIZE = 5.0
PT_ALPHA = 0.85
PT_ALPHA_LOW = 0.50    # variant C, where overlap must read as overlap
THUMB_W, THUMB_H = 800, 500

# copies 1..4: quiet blue -> ochre, two mixed steps between
COPIES_COLORS = {
    1: QUIET_BLUE,     # quiet blue
    2: "#77808A",      # blue-grey
    3: "#A08A67",      # warm grey, leaning to ochre
    4: OCHRE,
}

# muted, distinguishable; 12 named + everything else grey
CATEGORY_COLORS = [
    ("cs",        "#6E9BC5"),
    ("math",      "#C98C6B"),
    ("cond-mat",  "#7FB08A"),
    ("astro-ph",  "#B98BC0"),
    ("physics",   "#D4B36A"),
    ("hep-ph",    "#7BA7A0"),
    ("quant-ph",  "#C77E8E"),
    ("hep-th",    "#8E9BD4"),
    ("gr-qc",     "#A8B472"),
    ("eess",      "#6FA9B8"),
    ("stat",      "#CE9F86"),
    ("q-bio",     "#8FBF9F"),
]
OTHER_COLOR = "#4E5A6B"


def fig_axes(w=WIDTH, h=HEIGHT):
    """A figure that is nothing but image: no axes, ticks, margins or title."""
    fig = plt.figure(figsize=(w / DPI, h / DPI), dpi=DPI, facecolor=SLATE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(SLATE)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_axis_off()
    return fig, ax


def frame(ax, x, y, pad=0.02):
    """Fixed limits, shared by every variant so they overlay exactly."""
    dx, dy = x.max() - x.min(), y.max() - y.min()
    ax.set_xlim(x.min() - pad * dx, x.max() + pad * dx)
    ax.set_ylim(y.min() - pad * dy, y.max() + pad * dy)


def scrim(ax, height=0.20):
    """A soft darkening of the bottom strip so text stays legible over points.

    Not chart chrome: it carries no scale or category, it only stops the
    caption fighting the cloud. Ramped rather than a hard band so there is no
    edge line across the image.
    """
    ramp = np.linspace(1.0, 0.0, 256) ** 1.6
    rgba = np.zeros((256, 1, 4))
    rgba[:, 0, :3] = np.array([0x1B, 0x24, 0x32]) / 255.0
    rgba[:, 0, 3] = ramp * 0.88
    ax.imshow(rgba, extent=(0, 1, 0, height), transform=ax.transAxes,
              aspect="auto", zorder=4, interpolation="bilinear",
              origin="lower")


def caption(ax, lines, color=INK, dim=INK_DIM, x=0.018, y=0.030, size=21):
    """Bottom-left caption. First line primary, the rest dim."""
    for i, line in enumerate(reversed(lines)):
        ax.text(x, y + i * 0.030, line, transform=ax.transAxes,
                color=color if i == len(lines) - 1 else dim,
                fontsize=size if i == len(lines) - 1 else size - 4,
                family="DejaVu Sans", va="bottom", ha="left", zorder=6)


def save(fig, out, name):
    """PNG then SVG. Most of a variant's wall clock is here, not in the draw."""
    png = os.path.join(out, f"{name}.png")
    svg = os.path.join(out, f"{name}.svg")
    fig.savefig(png, facecolor=SLATE, dpi=DPI)
    fig.savefig(svg, facecolor=SLATE)
    plt.close(fig)
    return png, svg


# ------------------------------------------------------------------ A
def variant_a(base, cents, out, times):
    t0 = time.time()
    x, y = base["x"], base["y"]
    cats = base["top_level_category"]

    named = {n: c for n, c in CATEGORY_COLORS}
    colors = np.array([named.get(c, OTHER_COLOR) for c in cats], dtype=object)

    fig, ax = fig_axes()
    frame(ax, x, y)
    ax.scatter(x, y, s=PT_SIZE, c=list(colors), alpha=PT_ALPHA, linewidths=0,
               marker=".", rasterized=True)
    # centroids as small white rings
    ax.scatter(cents["x"], cents["y"], s=46, facecolors="none",
               edgecolors="#FFFFFF", linewidths=0.9, alpha=0.55)

    # key, bottom-left: 3 columns x 5 rows, clear of the caption below it
    counts = {}
    for c in cats:
        counts[c] = counts.get(c, 0) + 1
    n = len(cats)
    entries = [(label, color, counts.get(label, 0)) for label, color in CATEGORY_COLORS]
    entries.append(("25 others", OTHER_COLOR,
                    sum(v for k, v in counts.items() if k not in named)))

    scrim(ax, height=0.245)
    for i, (label, color, count) in enumerate(entries):
        col, row = divmod(i, 5)
        px = 0.018 + col * 0.108
        py = 0.196 - row * 0.025
        ax.plot([px], [py], marker="o", markersize=7, color=color,
                transform=ax.transAxes, linestyle="none", zorder=6)
        ax.text(px + 0.013, py, f"{label}  {count / n:.1%}",
                transform=ax.transAxes, color=INK_DIM, fontsize=15,
                family="DejaVu Sans", va="center", ha="left", zorder=6)

    caption(ax, ["arXiv-150k · 150,000 abstracts, bge-base-en-v1.5",
                 "coloured by top-level arXiv category"])
    save(fig, out, "ground_a_category")
    times["A"] = time.time() - t0
    return "A"


# ------------------------------------------------------------------ B
def variant_b(base, cents, out, times, name="ground_b_copies",
              w=WIDTH, h=HEIGHT, with_caption=True):
    t0 = time.time()
    x, y, copies = base["x"], base["y"], base["copies"]
    colors = [COPIES_COLORS[int(c)] for c in copies]

    fig, ax = fig_axes(w, h)
    frame(ax, x, y)
    ax.scatter(x, y, s=PT_SIZE * (w / WIDTH), c=colors, alpha=PT_ALPHA,
               linewidths=0, marker=".", rasterized=True)

    if with_caption:
        scrim(ax)
        share = {k: float((copies == k).mean()) for k in (1, 2, 3, 4)}
        for i, k in enumerate((1, 2, 3, 4)):
            px = 0.018 + i * 0.105
            ax.plot([px], [0.118], marker="o", markersize=8,
                    color=COPIES_COLORS[k], transform=ax.transAxes,
                    linestyle="none", zorder=6)
            ax.text(px + 0.014, 0.118,
                    f"{k}x  {share[k]:.1%}",
                    transform=ax.transAxes, color=INK_DIM, fontsize=15,
                    family="DejaVu Sans", va="center", ha="left", zorder=6)
        caption(ax, [
            "84% of vectors sit within ε of four regions. "
            "There is no boundary to shard on.",
            "crispness 0.036  ·  ambiguity 0.891  ·  storage 3.7×",
        ])
    save(fig, out, name)
    times[name] = time.time() - t0
    return "B"


# ------------------------------------------------------------------ C
def variant_c(base, cents, out, times):
    t0 = time.time()
    x, y, region = base["x"], base["y"], base["region"]

    # 256 colours, cyclic, so neighbouring region ids do not read as a ramp
    cyc = matplotlib.colormaps["hsv"]
    lut = np.array([cyc((i * 97 % 256) / 256.0) for i in range(256)])
    lut[:, :3] = 0.55 * lut[:, :3] + 0.45 * np.array([0.42, 0.47, 0.55])  # mute

    fig, ax = fig_axes()
    frame(ax, x, y)
    ax.scatter(x, y, s=PT_SIZE, c=lut[region], alpha=PT_ALPHA_LOW,
               linewidths=0, marker=".", rasterized=True)

    scrim(ax)
    order = np.argsort(-cents["size"])[:8]
    for i in order:
        ax.plot([cents["x"][i]], [cents["y"][i]], marker="o", markersize=5,
                markerfacecolor="none", markeredgecolor="#FFFFFF",
                markeredgewidth=1.1, linestyle="none")
        ax.text(cents["x"][i], cents["y"][i] + 0.10,
                f"{int(cents['size'][i]):,}", color=INK, fontsize=16,
                family="DejaVu Sans", ha="center", va="bottom")

    caption(ax, [
        "256 k-means regions, one colour each, drawn at low opacity.",
        "The colours do not separate: regions overlap through the whole space. "
        "Labels are the eight largest regions by membership.",
    ])
    save(fig, out, "ground_c_region")
    times["C"] = time.time() - t0
    return "C"


# ------------------------------------------------------------------ D
def variant_d(base, cents, queries, gt, out, times):
    t0 = time.time()
    x, y, copies = base["x"], base["y"], base["copies"]
    region = base["region"]

    # The worst-recall ambiguous query. 91 of them tie at recall 0, so the
    # tie is broken deterministically on the tightest d2/d1 ratio: the most
    # ambiguous of the worst, not an arbitrary one.
    amb = queries["ambiguous"]
    rec = queries["recall10_one_region"]
    cand = np.where(amb)[0]
    worst_recall = rec[cand].min()
    tied = cand[rec[cand] == worst_recall]
    qi = int(tied[np.argmin(queries["ratio"][tied])])

    q_region = int(queries["region"][qi])
    nbrs = gt[qi, :10]
    nbr_regions = region[nbrs]
    outside = int((nbr_regions != q_region).sum())

    fig, ax = fig_axes()
    frame(ax, x, y)
    # variant B as background at 30%
    ax.scatter(x, y, s=PT_SIZE, c=[COPIES_COLORS[int(c)] for c in copies],
               alpha=0.30 * PT_ALPHA, linewidths=0, marker=".", rasterized=True)

    # the routed region's centroid, and the regions the true neighbours are in
    ax.scatter([cents["x"][q_region]], [cents["y"][q_region]], s=340,
               facecolors="none", edgecolors="#FFFFFF", linewidths=2.0)
    ax.text(cents["x"][q_region], cents["y"][q_region] - 0.22,
            f"routed region {q_region}  ({int(cents['size'][q_region]):,} vectors)",
            color=INK, fontsize=16, family="DejaVu Sans",
            ha="center", va="top")

    for r in sorted(set(nbr_regions.tolist()) - {q_region}):
        ax.scatter([cents["x"][r]], [cents["y"][r]], s=170, facecolors="none",
                   edgecolors=CORAL, linewidths=1.4, alpha=0.85)

    # the ten true neighbours
    ax.scatter(x[nbrs], y[nbrs], s=70, c=CORAL, marker="D", linewidths=0,
               alpha=0.95, zorder=5)
    # the query itself
    ax.scatter([queries["x"][qi]], [queries["y"][qi]], s=190, c=INK,
               marker="*", linewidths=0, zorder=6)
    ax.text(queries["x"][qi], queries["y"][qi] + 0.16, "query",
            color=INK, fontsize=16, family="DejaVu Sans",
            ha="center", va="bottom")

    scrim(ax)
    caption(ax, [
        (f"One ambiguous query: all 10 of its true neighbours fall outside "
         f"the region it routes to." if outside == 10 else
         f"One ambiguous query: {outside} of its 10 true neighbours fall "
         f"outside the region it routes to."),
        f"d2/d1 = {float(queries['ratio'][qi]):.3f}  ·  "
        f"recall@10 at one-region routing = {float(rec[qi]):.1f}  ·  "
        f"true neighbours in {len(set(nbr_regions.tolist()))} regions",
    ])
    save(fig, out, "ground_d_query")
    times["D"] = time.time() - t0
    return dict(query_index=qi, routed_region=q_region, outside=outside,
                ratio=float(queries["ratio"][qi]), recall=float(rec[qi]),
                n_regions=len(set(nbr_regions.tolist())))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    t_all = time.time()
    b = pq.read_table(os.path.join(args.dir, "ground_view_base.parquet")).to_pydict()
    c = pq.read_table(os.path.join(args.dir, "ground_view_centroids.parquet")).to_pydict()
    q = pq.read_table(os.path.join(args.dir, "ground_view_queries.parquet")).to_pydict()
    gt = np.load(os.path.join(args.dir, "ground_truth.npy"))

    base = {k: np.asarray(v) for k, v in b.items() if k != "top_level_category"}
    base["top_level_category"] = b["top_level_category"]
    cents = {k: np.asarray(v) for k, v in c.items()}
    queries = {k: np.asarray(v) for k, v in q.items()}
    load = time.time() - t_all
    print(f"loaded {len(base['x']):,} base, {len(queries['x']):,} queries, "
          f"{len(cents['x'])} centroids in {load:.1f}s", flush=True)

    times = {}
    variant_a(base, cents, args.out, times)
    print(f"  A by category   {times['A']:.1f}s", flush=True)
    variant_b(base, cents, args.out, times)
    print(f"  B by copies     {times['ground_b_copies']:.1f}s   (default)", flush=True)
    variant_c(base, cents, args.out, times)
    print(f"  C by region     {times['C']:.1f}s", flush=True)
    d = variant_d(base, cents, queries, gt, args.out, times)
    print(f"  D one query     {times['D']:.1f}s", flush=True)

    # thumbnail of the default variant
    t = time.time()
    variant_b(base, cents, args.out, times, name="ground_thumbnail",
              w=THUMB_W, h=THUMB_H, with_caption=False)
    thumb_png = os.path.join(args.out, "ground_thumbnail.png")
    os.remove(os.path.join(args.out, "ground_thumbnail.svg"))   # thumbnail is PNG only
    print(f"  thumbnail       {time.time() - t:.1f}s  -> {thumb_png}", flush=True)

    print(f"\nvariant D query: index {d['query_index']}, routed region "
          f"{d['routed_region']}, {d['outside']}/10 neighbours outside it, "
          f"neighbours spread over {d['n_regions']} regions")
    print(f"total {time.time() - t_all:.1f}s")
    print(json.dumps({"default": "ground_b_copies", **d}))


if __name__ == "__main__":
    main()
