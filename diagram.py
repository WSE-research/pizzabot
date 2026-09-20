"""Draw the process model of whatever graph is loaded -- on startup, from the graph.

No picture is shipped: the frontend asks the compiled graph for its nodes and
edges and renders them, so the diagram is always the process that is actually
running, for every implementation and after every change to it.

Four ways out, in this order:

1. `dot` (graphviz), when the installation can actually write SVG or PNG
2. the layered SVG renderer below -- no dependency, works offline, always there
3. LangGraph's own `draw_mermaid_png` -- needs mermaid.ink, i.e. the network
4. a text diagram built from the same nodes and edges

Results are cached under `assets/generated/` and keyed by a hash of the
structure, so a changed implementation redraws and an unchanged one does not.
"""

from __future__ import annotations

import hashlib
import html
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from settings import HERE

GENERATED = HERE / "assets" / "generated"

# the shop palette, so the picture belongs to the page it sits on
INK = "#2B211A"
DOUGH = "#FFF8EC"
CRUST = "#E8A33D"
TOMATO = "#C8102E"
BASIL = "#2E7D4F"
SLATE = "#7A6A58"
LINE = "#EADFCB"

START, END = "__start__", "__end__"


# =========================================================================
# structure
# =========================================================================


def structure(graph) -> tuple[list[str], list[tuple[str, str, bool]]]:
    drawn = graph.get_graph()
    nodes = list(drawn.nodes)
    edges = [(edge.source, edge.target, bool(getattr(edge, "conditional", False)))
             for edge in drawn.edges]
    return nodes, edges


def fingerprint(nodes: Iterable[str], edges: Iterable[tuple[str, str, bool]]) -> str:
    payload = "|".join(sorted(nodes)) + "||" + "|".join(
        sorted(f"{source}>{target}:{int(conditional)}"
               for source, target, conditional in edges))
    return hashlib.sha1(payload.encode()).hexdigest()[:10]


def layers(nodes: list[str], edges: list[tuple[str, str, bool]]) -> list[list[str]]:
    """Longest-path layering; edges that would go backwards are ignored."""
    incoming: dict[str, list[str]] = {node: [] for node in nodes}
    for source, target, _ in edges:
        if source != target:
            incoming[target].append(source)

    level = {node: 0 for node in nodes}
    for _ in range(len(nodes)):                 # relax, bounded: no infinite loop
        changed = False
        for node in nodes:
            for parent in incoming[node]:
                if level[node] < level[parent] + 1:
                    level[node] = level[parent] + 1
                    changed = True
        if not changed:
            break
    if END in level:                            # the end node always sits last
        level[END] = max(level.values(), default=0) + 1

    ordered: dict[int, list[str]] = {}
    for node in nodes:
        ordered.setdefault(level[node], []).append(node)
    return [ordered[key] for key in sorted(ordered)]


# =========================================================================
# the renderer that always works
# =========================================================================

BOX_HEIGHT = 34
LAYER_GAP = 74
COLUMN_GAP = 26
PADDING = 18


def _width_of(name: str) -> float:
    return max(74.0, 7.4 * len(name) + 26)


def to_svg(nodes: list[str], edges: list[tuple[str, str, bool]],
           title: str = "") -> str:
    """A layered drawing of the graph -- no graphviz, no network."""
    rows = layers(nodes, edges)
    widths = [sum(_width_of(name) for name in row) + COLUMN_GAP * (len(row) - 1)
              for row in rows]
    canvas_width = max(widths + [240.0]) + 2 * PADDING
    top = PADDING + (22 if title else 0)
    canvas_height = top + len(rows) * LAYER_GAP + PADDING

    place: dict[str, tuple[float, float, float]] = {}      # name -> (x, y, w)
    for index, row in enumerate(rows):
        row_width = sum(_width_of(name) for name in row) + COLUMN_GAP * (len(row) - 1)
        cursor = (canvas_width - row_width) / 2
        for name in row:
            width = _width_of(name)
            place[name] = (cursor, top + index * LAYER_GAP, width)
            cursor += width + COLUMN_GAP

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas_width:.0f} '
        f'{canvas_height:.0f}" width="100%" role="img" '
        f'style="font-family:\'Source Code Pro\',monospace">',
        '<defs>'
        f'<marker id="a" markerWidth="7" markerHeight="7" refX="6" refY="3" '
        f'orient="auto"><path d="M0,0 L6,3 L0,6 z" fill="{SLATE}"/></marker>'
        '</defs>',
    ]
    if title:
        parts.append(f'<text x="{canvas_width / 2:.0f}" y="16" text-anchor="middle" '
                     f'font-size="11" fill="{SLATE}">{html.escape(title)}</text>')

    for source, target, conditional in edges:
        if source not in place or target not in place:
            continue
        sx, sy, sw = place[source]
        tx, ty, tw = place[target]
        x1, y1 = sx + sw / 2, sy + BOX_HEIGHT
        x2, y2 = tx + tw / 2, ty
        dash = ' stroke-dasharray="4 3"' if conditional else ""
        if ty > sy:                                   # forward: a soft curve
            middle = (y1 + y2) / 2
            path = f"M{x1:.1f},{y1:.1f} C{x1:.1f},{middle:.1f} {x2:.1f},{middle:.1f} {x2:.1f},{y2:.1f}"
        elif source == target:                        # self loop
            path = (f"M{x1:.1f},{sy:.1f} C{x1 + 40:.1f},{sy - 26:.1f} "
                    f"{x1 - 40:.1f},{sy - 26:.1f} {x1:.1f},{sy:.1f}")
        else:                                         # backwards: around the side
            side = max(sx + sw, tx + tw) + 26
            path = (f"M{sx + sw:.1f},{sy + BOX_HEIGHT / 2:.1f} C{side:.1f},"
                    f"{sy:.1f} {side:.1f},{ty:.1f} {tx + tw:.1f},{ty + BOX_HEIGHT / 2:.1f}")
        parts.append(f'<path d="{path}" fill="none" stroke="{SLATE}" '
                     f'stroke-width="1.4"{dash} marker-end="url(#a)"/>')

    for name, (x, y, width) in place.items():
        if name in (START, END):
            fill, stroke, label = (BASIL, BASIL, "start") if name == START else (TOMATO, TOMATO, "end")
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{BOX_HEIGHT}" '
                f'rx="{BOX_HEIGHT / 2}" fill="{fill}" stroke="{stroke}"/>'
                f'<text x="{x + width / 2:.1f}" y="{y + 22:.1f}" text-anchor="middle" '
                f'font-size="12" fill="#FFFFFF">{label}</text>')
            continue
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{BOX_HEIGHT}" '
            f'rx="7" fill="{DOUGH}" stroke="{INK}" stroke-width="1.6"/>'
            f'<text x="{x + width / 2:.1f}" y="{y + 22:.1f}" text-anchor="middle" '
            f'font-size="12" fill="{INK}">{html.escape(name)}</text>')

    parts.append("</svg>")
    return "".join(parts)


def to_text(nodes, edges) -> str:
    """The same structure as text -- the last fallback."""
    outgoing: dict[str, list[tuple[str, bool]]] = {}
    for source, target, conditional in edges:
        outgoing.setdefault(source, []).append((target, conditional))
    lines = []
    for node in nodes:
        for index, (target, conditional) in enumerate(sorted(outgoing.get(node, []))):
            arrow = "?-->" if conditional else " -->"
            head = f"{node:>20s}" if index == 0 else " " * 20
            lines.append(f"{head} {arrow} {target}")
    return "\n".join(lines) or "(no edges)"


# =========================================================================
# graphviz, when it is actually usable
# =========================================================================


def to_dot(nodes, edges, title: str = "") -> str:
    lines = ["digraph process {",
             '  bgcolor="transparent";',
             "  rankdir=TB;",
             f'  node [fontname="Helvetica", fontsize=11, shape=box, style="rounded,filled",'
             f' color="{INK}", fillcolor="{DOUGH}", penwidth=1.6, margin="0.16,0.08"];',
             f'  edge [fontname="Helvetica", fontsize=9, color="{SLATE}", penwidth=1.3];']
    if title:
        lines.append(f'  labelloc="t"; label="{title}"; fontname="Helvetica"; fontsize=10;')
    for node in nodes:
        if node == START:
            lines.append(f'  "{node}" [label="start", shape=circle, width=0.35,'
                         f' fillcolor="{BASIL}", fontcolor="#FFFFFF", penwidth=0];')
        elif node == END:
            lines.append(f'  "{node}" [label="end", shape=doublecircle, width=0.3,'
                         f' fillcolor="{TOMATO}", fontcolor="#FFFFFF", penwidth=0];')
    for source, target, conditional in edges:
        style = ' [style=dashed, label="?"]' if conditional else ""
        lines.append(f'  "{source}" -> "{target}"{style};')
    lines.append("}")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def graphviz_format() -> Optional[str]:
    """Which format this graphviz can write -- often none, when it is half-installed."""
    if not shutil.which("dot"):
        return None
    for candidate in ("svg", "png"):
        try:
            done = subprocess.run(["dot", f"-T{candidate}"], input=b"digraph{a->b}",
                                  capture_output=True, timeout=10)
        except (subprocess.SubprocessError, OSError):
            return None
        if done.returncode == 0 and done.stdout:
            return candidate
    return None


# =========================================================================
# the entry point
# =========================================================================


def render(graph, key: str, title: str = "") -> tuple[str, str]:
    """("svg", markup) | ("png", path) | ("text", diagram), generated now."""
    nodes, edges = structure(graph)
    digest = fingerprint(nodes, edges)
    GENERATED.mkdir(parents=True, exist_ok=True)
    svg_file = GENERATED / f"{key}-{digest}.svg"
    png_file = GENERATED / f"{key}-{digest}.png"

    if svg_file.is_file():
        return "svg", svg_file.read_text()
    if png_file.is_file():
        return "png", str(png_file)

    usable = graphviz_format()
    if usable:
        try:
            done = subprocess.run(["dot", f"-T{usable}", "-Gdpi=140"],
                                  input=to_dot(nodes, edges, title).encode(),
                                  capture_output=True, check=True, timeout=20)
            if usable == "svg":
                svg_file.write_bytes(done.stdout)
                return "svg", done.stdout.decode()
            png_file.write_bytes(done.stdout)
            return "png", str(png_file)
        except (subprocess.SubprocessError, OSError):
            pass

    try:                                        # our own layout: always available
        # no title inside the picture: the pane already carries it, and a long
        # one would widen (or clip) the drawing
        markup = to_svg(nodes, edges)
        svg_file.write_text(markup)
        return "svg", markup
    except Exception:
        pass

    try:                                        # needs the network (mermaid.ink)
        png_file.write_bytes(graph.get_graph().draw_mermaid_png())
        return "png", str(png_file)
    except Exception:
        return "text", to_text(nodes, edges)


def mermaid(graph) -> str:
    """The mermaid source of the loaded graph -- handy to paste into the slides."""
    try:
        return graph.get_graph().draw_mermaid()
    except Exception:
        nodes, edges = structure(graph)
        return to_text(nodes, edges)
