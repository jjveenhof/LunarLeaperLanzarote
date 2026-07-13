"""Shared figure export for the thesis (ASCII only).

save_figure(fig, name, folder, ...) writes TWO things from one figure:
  * the THESIS copy, with every title hidden, straight into
    thesis-overleaf/<folder>/  -- a vector PDF (any imshow/pcolormesh inside it is
    auto-rasterized so it stays compact AND the axes/text stay crisp), or a raster
    PNG at `dpi` when vector=False.
  * optionally a titled PNG into `browse_dir`, so the results tree keeps the title
    as context when you browse it.

All text is rendered in Computer Modern (the LaTeX body font) so figures match the
thesis -- applied on `import plot_utils` and re-asserted at save time (see
set_thesis_style / _apply_thesis_font). This uses matplotlib's bundled cm fonts via
mathtext, NOT usetex, so there is no LaTeX call at plot time.

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

  * tight=True (default) -- crop to the drawn content (bbox_inches="tight"). Do NOT
    use this on a figure that is pre-sized for equal aspect (fig.set_size_inches +
    subplots_adjust chosen so an aspect="equal" box exactly fills the canvas): the
    tight pass re-fits the equal-aspect box on a resized canvas and the page height
    diverges (seen: an 18-foot-tall terrain PDF). Pass tight=False for those -- it
    saves the figure's own layout verbatim (like a plain savefig), matching the PNG.
    The reserved title margin then shows as a little whitespace, which is harmless.

FIGURE-SIZING RULE (text size, on top of the font fix above): matplotlib text is set in
ABSOLUTE points, but \includegraphics[width=L]{...} scales the WHOLE figure -- text
included -- by L / W, where W is the figsize width in inches. So:

    on-page text size (pt) = matplotlib fontsize (pt) x (L / W)

Author a figure at W=14 and place it at L=6 and every label shrinks to 0.43x -- that is
the "why is the text tiny" bug, and it has nothing to do with dpi or fontsize alone.
THE RULE: author each figure at roughly the width it will occupy on the page.
  1. This thesis's \linewidth = 6.1 in (single-column A4, normal margins). If a figure
     is placed at 0.8\linewidth, L = 0.8 x 6.1 = 4.9 in.
  2. Set figsize WIDTH W ~= L (height is whatever aspect you want -- only the width
     ratio drives text scaling).
  3. Fine-tune: W < L makes text bigger, W > L makes it smaller. Our full-\linewidth GPR
     radargrams use W = 5.3 in -> 6.1/5.3 = 1.15x native -- a deliberate slight enlargement.
  4. NEVER author at 12-15 in and lean on \includegraphics to shrink -- that is exactly
     what makes text 2-2.5x too small.
  5. Dense multi-panel figures need a minimum width per panel for their labels; if W~=L
     makes labels collide, split the figure or accept smaller text (appendix-OK) rather
     than forcing it.

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
import matplotlib as mpl
from matplotlib.text import Text
from matplotlib.image import AxesImage
from matplotlib.collections import QuadMesh

# git-bridge Overleaf clone (outside OneDrive). The thesis \includegraphics paths
# resolve relative to this root, so writing here means no manual copy step.
THESIS = Path(r"C:\Users\jj_ve\thesis-overleaf")

_TITLE_MODES = ("auto", "all", "suptitle", "keep")

# Computer Modern (the LaTeX body font) via matplotlib's BUNDLED cm fonts + mathtext,
# NOT usetex -- no LaTeX process at plot time, so it stays fast and dependency-free and
# keeps the project's "mathtext default" rule. Regular text renders in cmr10; math (the
# r"$\Delta\rho$" / r"$\mu$Gal" labels) renders in the cm math fonts, matching the thesis.
_THESIS_RC = {
    "font.family": "serif",
    "font.serif": ["cmr10", "STIX Two Text", "DejaVu Serif"],
    "mathtext.fontset": "cm",
    "axes.formatter.use_mathtext": True,   # tick offset/exponent text via mathtext too
    # cmr10 has no U+2212 minus glyph; without this, minus signs render as boxes and
    # matplotlib spams a warning on every save. Mathtext still draws proper minus signs.
    "axes.unicode_minus": False,
}


def set_thesis_style():
    """Switch matplotlib to the thesis font (Computer Modern via mathtext, no usetex).
    Applied automatically on `import plot_utils`; call it explicitly at the top of a
    script only if that script builds figures BEFORE importing this module."""
    mpl.rcParams.update(_THESIS_RC)


set_thesis_style()  # apply on import (covers scripts that import before plotting)


def _apply_thesis_font(fig):
    """Re-assert the thesis font at save time. Font is captured when a Text artist is
    CREATED, so axis labels/titles built before set_thesis_style ran keep their old
    font; restyle every existing Text here so late-import scripts still come out right.
    Tick labels are (re)created at draw and pick up the rcParams directly."""
    set_thesis_style()
    for t in fig.findobj(Text):
        t.set_family("serif")


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
                tight=True, browse_dir=None, browse_dpi=150):
    """Write the title-free thesis figure into thesis-overleaf/<folder>/<name>.<ext>
    and, if browse_dir is given, a titled <name>_titled.png beside your results.

    `titles` in {"auto","all","suptitle","keep"} -- see module docstring.
    `tight` -- crop to content; set False for figures pre-sized for equal aspect
    (see module docstring). Both saves honour it.
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

    _apply_thesis_font(fig)  # Computer Modern, regardless of import order
    bbox = "tight" if tight else None
    titles = _title_artists(fig, titles)
    prev = [(a, a.get_visible()) for a in titles]
    for a, _ in prev:
        a.set_visible(False)
    thesis_path = out_dir / "{}.{}".format(name, ext)
    fig.savefig(thesis_path, dpi=dpi, bbox_inches=bbox)
    for a, vis in prev:
        a.set_visible(vis)

    browse_path = None
    if browse_dir is not None:
        bdir = Path(browse_dir)
        bdir.mkdir(parents=True, exist_ok=True)
        browse_path = bdir / "{}_titled.png".format(name)
        fig.savefig(browse_path, dpi=browse_dpi, bbox_inches=bbox)

    return thesis_path, browse_path
