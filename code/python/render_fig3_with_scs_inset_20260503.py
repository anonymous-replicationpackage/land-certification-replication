from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
import pyreadstat
import shapefile


# Prefer the script folder when the renderer is copied into the figure-output
# directory; fall back to the project-root layout used during development.
SCRIPT_DIR = Path(__file__).resolve().parent
if (SCRIPT_DIR / "map_inputs").exists():
    OUTDIR = SCRIPT_DIR
else:
    ROOT = Path.cwd()
    OUTDIR = ROOT / "result" / "fig3_stata_20260503"
MAPDIR = OUTDIR / "map_inputs"

COUNTY_SHP = MAPDIR / "china_county.shp"
TEN_DASH_SHP = MAPDIR / "ten_dash.shp"
CENTROIDS_DTA = MAPDIR / "_centroids.dta"

PDF_OUT = OUTDIR / "Fig3.pdf"
PNG_OUT = OUTDIR / "Fig3.png"


COLORS = {
    1: "#999999",  # Not completed
    2: "#7fbce0",  # 2017-2018
    3: "#1f4e8b",  # 2014-2016
}
LABELS = {
    1: "Not completed by 2018 (n=241)",
    2: "Completed 2017-2018 (n=72)",
    3: "Completed 2014-2016 (n=36)",
}


def shape_parts(shape) -> list[list[tuple[float, float]]]:
    points = shape.points
    parts = list(shape.parts) + [len(points)]
    return [points[parts[i] : parts[i + 1]] for i in range(len(parts) - 1)]


def load_line_segments(shp_path: Path, encoding: str = "gbk") -> list[list[tuple[float, float]]]:
    reader = shapefile.Reader(str(shp_path), encoding=encoding, encodingErrors="replace")
    segments: list[list[tuple[float, float]]] = []
    for shape in reader.shapes():
        for part in shape_parts(shape):
            if len(part) >= 2:
                segments.append(part)
    return segments


def draw_boundaries(ax, segments, color="#d7d7d7", lw=0.25, zorder=1):
    ax.add_collection(LineCollection(segments, colors=color, linewidths=lw, zorder=zorder))


def draw_ten_dash(ax, segments, color="#8f8f8f", lw=1.0, zorder=4):
    ax.add_collection(
        LineCollection(
            segments,
            colors=color,
            linewidths=lw,
            linestyles=(0, (7, 5)),
            capstyle="round",
            zorder=zorder,
        )
    )


def style_map_axis(ax, xlim, ylim):
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)


def main() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    county_segments = load_line_segments(COUNTY_SHP, encoding="utf-8")
    dash_segments = load_line_segments(TEN_DASH_SHP, encoding="gbk")
    centroids, _ = pyreadstat.read_dta(str(CENTROIDS_DTA), apply_value_formats=False)
    centroids = centroids[centroids["cat"].notna()].copy()

    fig = plt.figure(figsize=(9.0, 6.0), facecolor="white")
    ax = fig.add_axes([0.03, 0.16, 0.94, 0.80])
    ax.set_facecolor("white")

    # Main map: keep the mainland-oriented extent; South China Sea is moved to inset.
    draw_boundaries(ax, county_segments, color="#d9d9d9", lw=0.22, zorder=1)
    for cat in [1, 2, 3]:
        df = centroids[centroids["cat"] == cat]
        ax.scatter(
            df["cen_x"],
            df["cen_y"],
            s=16 if cat == 1 else 22,
            c=COLORS[cat],
            edgecolors=COLORS[cat],
            linewidths=0.25,
            zorder=5,
        )
    style_map_axis(ax, (73.0, 135.5), (17.5, 54.5))

    # Conventional South China Sea inset in the lower-right ocean area.
    axins = inset_axes(
        ax,
        width="20%",
        height="31%",
        loc="lower right",
        bbox_to_anchor=(-0.018, 0.02, 1, 1),
        bbox_transform=ax.transAxes,
        borderpad=0,
    )
    axins.set_facecolor("white")
    draw_boundaries(axins, county_segments, color="#dddddd", lw=0.18, zorder=1)
    draw_ten_dash(axins, dash_segments, color="#8f8f8f", lw=1.05, zorder=4)
    style_map_axis(axins, (105.0, 124.5), (2.0, 25.5))
    for spine in axins.spines.values():
        spine.set_visible(True)
        spine.set_color("#bdbdbd")
        spine.set_linewidth(0.45)

    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markerfacecolor=COLORS[cat],
            markeredgecolor=COLORS[cat],
            markersize=4.2,
            label=LABELS[cat],
        )
        for cat in [1, 2, 3]
    ]
    fig.legend(
        handles=handles,
        loc="lower left",
        bbox_to_anchor=(0.055, 0.055),
        frameon=False,
        fontsize=9.5,
        handlelength=0.8,
        handletextpad=0.35,
        borderaxespad=0,
    )
    fig.text(
        0.55,
        0.042,
        "Estimation samples: 139 counties (mechanism), 134 counties (adjacent).",
        ha="center",
        va="center",
        fontsize=8.3,
    )

    fig.savefig(PDF_OUT, bbox_inches="tight", pad_inches=0.02)
    fig.savefig(PNG_OUT, dpi=300, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)

    # Ensure the PNG advertises 300 dpi even after bbox tightening.
    try:
        from PIL import Image

        img = Image.open(PNG_OUT)
        img.save(PNG_OUT, dpi=(300, 300))
    except Exception:
        pass


if __name__ == "__main__":
    main()
