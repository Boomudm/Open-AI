"""Plot Qdrant embedding corpus as a 2D similarity map.

Fetches dense vectors from a Qdrant collection, reduces to 2D with t-SNE
(default), UMAP, or PCA, and saves a PNG. Uses matplotlib when installed;
otherwise renders with Pillow.

Usage (repo root):
    .venv/bin/python scripts/plot_embeddings.py
    .venv/bin/python scripts/plot_embeddings.py --method umap --collection spark_docs
    .venv/bin/python scripts/plot_embeddings.py --method tsne --color-by doc_id --limit 500
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

# sklearn before numpy-heavy / OpenMP libs (Jetson TLS workaround).
from sklearn.manifold import TSNE  # noqa: E402

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from qdrant_client import QdrantClient

from spark.core.config import settings

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "output" / "embedding_maps"
SCROLL_BATCH = 256
PCA_PRE_DIM = 50

PALETTE = [
    (59, 130, 246),
    (16, 185, 129),
    (245, 158, 11),
    (239, 68, 68),
    (168, 85, 247),
    (236, 72, 153),
    (20, 184, 166),
    (99, 102, 241),
    (234, 88, 12),
    (34, 197, 94),
    (14, 165, 233),
    (217, 70, 239),
    (250, 204, 21),
    (132, 204, 22),
    (244, 114, 182),
    (56, 189, 248),
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot Qdrant embedding corpus map")
    parser.add_argument("--collection", default=settings.qdrant_collection)
    parser.add_argument("--method", choices=("tsne", "umap", "pca"), default="tsne")
    parser.add_argument("--color-by", choices=("document_type", "doc_id"), default="document_type")
    parser.add_argument("--limit", type=int, default=0, help="0 = all points")
    parser.add_argument("--doc-id", default=None, help="Filter to a single document UUID")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def _fetch_vectors(
    client: QdrantClient,
    collection: str,
    *,
    limit: int,
    doc_id: str | None,
) -> tuple[np.ndarray, list[dict[str, str | int | None]]]:
    vectors: list[list[float]] = []
    meta: list[dict[str, str | int | None]] = []
    offset = None
    cap = limit if limit > 0 else None

    while cap is None or len(vectors) < cap:
        batch_size = SCROLL_BATCH if cap is None else min(SCROLL_BATCH, cap - len(vectors))
        batch, offset = client.scroll(
            collection_name=collection,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if not batch:
            break
        for point in batch:
            payload = point.payload or {}
            if doc_id and str(payload.get("doc_id")) != doc_id:
                continue
            vec = point.vector
            if isinstance(vec, dict):
                vec = vec.get("dense")
            if not vec:
                continue
            vectors.append(vec)
            meta.append(
                {
                    "doc_id": str(payload.get("doc_id") or "?")[:12],
                    "page": payload.get("page"),
                    "title": str(payload.get("title") or payload.get("source_file") or "?")[:48],
                    "document_type": str(payload.get("document_type") or "unknown")[:24],
                }
            )
        if offset is None:
            break

    if not vectors:
        raise SystemExit(f"No vectors found in collection {collection!r}")
    return np.array(vectors, dtype=np.float32), meta


def _pca_reduce(x: np.ndarray, n_components: int) -> np.ndarray:
    x_centered = x - x.mean(axis=0)
    _, _, vt = np.linalg.svd(x_centered, full_matrices=False)
    k = min(n_components, vt.shape[0])
    return x_centered @ vt[:k].T


def _reduce_2d(x: np.ndarray, method: str, seed: int) -> np.ndarray:
    if method == "pca":
        return _pca_reduce(x, 2)

    pre = _pca_reduce(x, min(PCA_PRE_DIM, x.shape[1], x.shape[0] - 1))

    if method == "umap":
        try:
            import umap  # type: ignore[import-untyped]
        except ImportError as exc:
            raise SystemExit(
                "umap-learn is not installed. Run: uv pip install umap-learn --python .venv/bin/python"
            ) from exc
        reducer = umap.UMAP(
            n_components=2,
            n_neighbors=15,
            min_dist=0.1,
            metric="cosine",
            random_state=seed,
        )
        return reducer.fit_transform(pre)

    perplexity = min(30, max(5, (x.shape[0] - 1) // 3))
    return TSNE(
        n_components=2,
        perplexity=perplexity,
        random_state=seed,
        init="pca",
        learning_rate="auto",
        max_iter=1000,
    ).fit_transform(pre)


def _color_key(meta: dict[str, str | int | None], color_by: str) -> str:
    if color_by == "doc_id":
        return str(meta["doc_id"])
    return str(meta["document_type"])


def _render_pillow(
    xy: np.ndarray,
    meta: list[dict[str, str | int | None]],
    *,
    title: str,
    color_by: str,
    out_path: Path,
) -> None:
    keys = [_color_key(m, color_by) for m in meta]
    counts = Counter(keys)
    unique_keys = [k for k, _ in counts.most_common()]
    color_map = {k: PALETTE[i % len(PALETTE)] for i, k in enumerate(unique_keys)}

    w, h = 2000, 1300
    pad, legend_w = 90, 420
    plot_w = w - pad - legend_w - pad
    plot_h = h - 2 * pad

    img = Image.new("RGB", (w, h), (11, 17, 32))
    draw = ImageDraw.Draw(img, "RGBA")

    xs, ys = xy[:, 0], xy[:, 1]
    xmin, xmax = float(xs.min()), float(xs.max())
    ymin, ymax = float(ys.min()), float(ys.max())
    xr = xmax - xmin or 1.0
    yr = ymax - ymin or 1.0

    def to_px(x: float, y: float) -> tuple[float, float]:
        px = pad + (x - xmin) / xr * plot_w
        py = pad + plot_h - (y - ymin) / yr * plot_h
        return px, py

    for gx in range(pad, pad + plot_w, 80):
        draw.line([(gx, pad), (gx, pad + plot_h)], fill=(30, 41, 59, 255))
    for gy in range(pad, pad + plot_h, 80):
        draw.line([(pad, gy), (pad + plot_w, gy)], fill=(30, 41, 59, 255))

    # Draw denser groups on top: sort by group size ascending.
    order = sorted(range(len(meta)), key=lambda i: counts[keys[i]])
    for i in order:
        px, py = to_px(float(xy[i, 0]), float(xy[i, 1]))
        rgb = color_map[keys[i]]
        draw.ellipse((px - 6, py - 6, px + 6, py + 6), fill=(*rgb, 200), outline=(11, 17, 32, 255))

    draw.text((pad, 28), title, fill=(226, 232, 240))
    draw.text((pad, 56), f"{len(meta)} points · color by {color_by}", fill=(148, 163, 184))

    lx = w - legend_w
    draw.rectangle((lx - 12, pad - 10, w - pad, h - pad), fill=(15, 23, 42))
    draw.text((lx, pad), "Legend", fill=(226, 232, 240))
    ly = pad + 28
    max_legend = 18
    for key in unique_keys[:max_legend]:
        c = color_map[key]
        draw.rectangle((lx, ly, lx + 14, ly + 14), fill=c)
        label = f"{key} ({counts[key]})"
        draw.text((lx + 22, ly - 2), label[:36], fill=(203, 213, 225))
        ly += 22
    if len(unique_keys) > max_legend:
        draw.text((lx, ly), f"+ {len(unique_keys) - max_legend} more…", fill=(148, 163, 184))

    by_doc = Counter(str(m["doc_id"]) for m in meta)
    top = ", ".join(f"{d}({n})" for d, n in by_doc.most_common(4))
    draw.text((pad, h - pad + 18), f"Top docs: {top}", fill=(148, 163, 184))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)


def _render_matplotlib(
    xy: np.ndarray,
    meta: list[dict[str, str | int | None]],
    *,
    title: str,
    color_by: str,
    out_path: Path,
) -> None:
    import matplotlib.pyplot as plt

    keys = [_color_key(m, color_by) for m in meta]
    counts = Counter(keys)
    unique_keys = [k for k, _ in counts.most_common()]
    color_map = {k: f"#{PALETTE[i % len(PALETTE)][0]:02x}{PALETTE[i % len(PALETTE)][1]:02x}{PALETTE[i % len(PALETTE)][2]:02x}" for i, k in enumerate(unique_keys)}
    colors = [color_map[k] for k in keys]

    fig, ax = plt.subplots(figsize=(16, 10), facecolor="#0b1120")
    ax.set_facecolor("#0b1120")
    ax.scatter(xy[:, 0], xy[:, 1], c=colors, s=18, alpha=0.75, linewidths=0)
    ax.set_title(title, color="#e2e8f0", fontsize=14, pad=12)
    ax.tick_params(colors="#94a3b8")
    for spine in ax.spines.values():
        spine.set_color("#334155")

    handles = []
    labels = []
    for key in unique_keys[:18]:
        handles.append(plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=color_map[key], markersize=8))
        labels.append(f"{key} ({counts[key]})")
    ax.legend(handles, labels, loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False, labelcolor="#cbd5e1")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> int:
    args = _parse_args()
    client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, timeout=120)

    info = client.get_collection(args.collection)
    total = int(info.points_count or 0)
    print(f"Collection {args.collection}: {total} points in Qdrant")

    x, meta = _fetch_vectors(
        client,
        args.collection,
        limit=args.limit,
        doc_id=args.doc_id,
    )
    print(f"Fetched {len(meta)} vectors ({x.shape[1]} dims)")

    print(f"Reducing to 2D via {args.method.upper()}…")
    xy = _reduce_2d(x, args.method, args.seed)
    print("Reduction done.")

    method_label = {"tsne": "t-SNE", "umap": "UMAP", "pca": "PCA"}[args.method]
    title = f"Embedding map — {args.collection} ({method_label} 2D)"

    out = args.output or (DEFAULT_OUT / f"{args.collection}_{args.method}.png")
    try:
        import matplotlib  # noqa: F401

        _render_matplotlib(xy, meta, title=title, color_by=args.color_by, out_path=out)
        backend = "matplotlib"
    except ImportError:
        _render_pillow(xy, meta, title=title, color_by=args.color_by, out_path=out)
        backend = "pillow"

    print(f"Saved ({backend}): {out}")
    type_counts = Counter(str(m["document_type"]) for m in meta)
    print("Document types:", dict(type_counts.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
