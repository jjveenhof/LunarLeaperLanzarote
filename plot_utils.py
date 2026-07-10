"""Shared figure export for the thesis (ASCII only).

save_figure(fig, name, folder, ...) writes TWO things from one figure:
  * the THESIS copy, with every title hidden, straight into
    thesis-overleaf/<folder>/  -- a vector PDF (any imshow/pcolormesh inside it is
    auto-rasterized so it stays compact AND the axes/text stay crisp), or a raster
    PNG at `dpi` when vector=False.
  * optionally a titled PNG into `browse_dir`, so the results tree keeps the title
    as context when you browse it.

Choose the format by what the figure is MADE OF, not by habit:
  * lines / markers / text only (decay fits, detrend, inversion sections,
    schematics)                       -> vector=True   (PDF)
  * dense per-pixel data on its own
    (photos, 3D stills, satellite maps) -> vector=False  (PNG, dpi>=300)
  * a raster image WITH vector overlays
    (radargrams with picks/labels)     -> vector=True   (image auto-rasterized in PDF)

The title toggle is free because these scripts save with bbox_inches="tight":
hidden title artists drop out of the tight bounding box, so the thesis figure
crops clean with no leftover band.

Which titles get hidden is set by `titles=`:
  * "auto" (default) -- hide the figure suptitle always; hide axes titles ONLY when
    the figure has a single data panel. So a lone plot loses its (caption-like) title,
    while a multi-panel figure keeps its per-panel labels ("Line 3", "L5 S0", ...) and
    loses only an overarching suptitle. Colorbar axes do not count as panels.
  * "all"      -- hide every title (single- and multi-panel). Use when LaTeX will
                  relabel the panels itself (subcaptions / (a),(b) letters).
  * "suptitle" -- hide only the figure suptitle.
  * "keep"     -- hide nothing.
"""
from pathlib import Path
from matplotlib.image import AxesImage
from matplotlib.collections import QuadMesh

# git-bridge Overleaf clone (outside OneDrive). The thesis \includegraphics paths
# resolve relative to this root, so writing here means no manual copy step.
THESIS = Path(r"C:\Users\jj_ve\thesis-overleaf")

_TITLE_MODES = ("auto", "all", "suptitle", "keep")


def _data_axes(fig):
    """Panel axes, excluding colorbar axes (matplotlib labels them '<colorbar>')."""
    return [ax for ax in fig.axes if ax.get_label() != "<colorbar>"]


def _title_artists(fig, mode):
    """Title Text artists to hide for `mode`. matplotlib keeps center/left/right
    titles separately (loc='left'/'right' live in _left_title / _right_title)."""
    if mode == "keep":
        return []
    arts = []
    supt = getattr(fig, "_suptitle", None)
    if supt is not None:
        arts.append(supt)
    if mode == "suptitle":
        return arts
    if mode == "auto" and len(_data_axes(fig)) != 1:
        return arts                      # multi-panel: keep panel labels
    for ax in fig.axes:                  # "all", or "auto" with a single panel
        for a in (ax.title, getattr(ax, "_left_title", None),
                  getattr(ax, "_right_title", None)):
            if a is not None:
                arts.append(a)
    return arts


def save_figure(fig, name, folder, vector=True, dpi=300, titles="auto",
                browse_dir=None, browse_dpi=150):
    """Write the title-free thesis figure into thesis-overleaf/<folder>/<name>.<ext>
    and, if browse_dir is given, a titled <name>_titled.png beside your results.

    `titles` in {"auto","all","suptitle","keep"} -- see module docstring.
    Returns (thesis_path, browse_path); browse_path is None when browse_dir is None.
    """
    if titles not in _TITLE_MODES:
        raise ValueError("titles must be one of {}".format(_TITLE_MODES))
    out_dir = THESIS / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = "pdf" if vector else "png"

    if vector:  # keep heavy raster artists compact + sharp inside the vector PDF
        for ax in fig.axes:
            for art in ax.get_children():
                if isinstance(art, (AxesImage, QuadMesh)):
                    art.set_rasterized(True)

    titles = _title_artists(fig, titles)
    prev = [(a, a.get_visible()) for a in titles]
    for a, _ in prev:
        a.set_visible(False)
    thesis_path = out_dir / "{}.{}".format(name, ext)
    fig.savefig(thesis_path, dpi=dpi, bbox_inches="tight")
    for a, vis in prev:
        a.set_visible(vis)

    browse_path = None
    if browse_dir is not None:
        bdir = Path(browse_dir)
        bdir.mkdir(parents=True, exist_ok=True)
        browse_path = bdir / "{}_titled.png".format(name)
        fig.savefig(browse_path, dpi=browse_dpi, bbox_inches="tight")

    return thesis_path, browse_path
