"""The floor plan, large: an overlay over 90 % of the screen.

A click on the process model in the *Floor plan* tab opens it. The plan is
first fitted into the overlay, whole; a click on it widens it to the overlay's
full width, so every label can be read (scroll for the rest), and another
click fits it back. The x, Esc or a click beside the frame closes it.

Like the tour, the code runs in the page, not in the component's iframe:
Streamlit re-mounts component iframes on every rerun, and a listener whose
code lived in a destroyed iframe stops working. The iframe only makes sure
the code is there. One delegated listener on the document serves every
floor plan the page will ever show -- nothing has to be re-attached after a
rerun draws a new one.

The looks are rules in the frontend's style sheet (`#pz-lightbox`), so the
overlay repaints with the rest of the shop.
"""

from __future__ import annotations

import json

import streamlit.components.v1 as components

# anything inside an element with this class opens the overlay on a click
TRIGGER = ".pz-figure-canvas"

LIGHTBOX_CODE = r"""
(function () {
    if (window.__pzLightbox) return;        // already installed on this page

    const doc = document;
    const ROOT_ID = "pz-lightbox";
    let root = null, stage = null;

    // The copy of an inline SVG shares the page with the original, so its
    // ids (the arrow marker) get a suffix -- otherwise url(#a) would point
    // at the original, which may be hidden in a tab that is not open.
    function renameIds(svg) {
        svg.querySelectorAll("[id]").forEach(function (el) {
            const old = el.id, fresh = old + "-pz-lightbox";
            el.id = fresh;
            svg.querySelectorAll("*").forEach(function (other) {
                Array.from(other.attributes).forEach(function (attr) {
                    if (attr.value.indexOf("#" + old + ")") !== -1) {
                        attr.value = attr.value.split("#" + old + ")")
                                               .join("#" + fresh + ")");
                    }
                });
            });
        });
    }

    function close() {
        if (!root) return;
        root.remove();
        root = stage = null;
        doc.removeEventListener("keydown", onKey, true);
    }

    function onKey(event) {
        if (event.key === "Escape") {
            event.stopPropagation();
            close();
        }
    }

    function toggle() {
        const wide = stage.classList.toggle("wide");
        stage.classList.toggle("fit", !wide);
        stage.scrollTop = 0;
        root.querySelector(".hint").textContent = wide
            ? "full width — scroll for the rest · click the plan to fit it"
            : "fitted to the frame · click the plan to see it at full width";
    }

    function open(canvas) {
        close();
        const picture = canvas.querySelector("svg, img");
        if (!picture) return;
        const copy = picture.cloneNode(true);
        copy.removeAttribute("width");
        copy.removeAttribute("height");
        if (copy.tagName.toLowerCase() === "svg") renameIds(copy);

        root = doc.createElement("div");
        root.id = ROOT_ID;
        root.setAttribute("role", "dialog");
        root.setAttribute("aria-modal", "true");
        root.setAttribute("aria-label", "Floor plan");
        root.innerHTML =
            '<div class="pz-lightbox-frame">' +
            '<div class="pz-lightbox-bar"><b>Floor plan</b>' +
            '<span class="hint"></span>' +
            '<button class="pz-lightbox-close" type="button" ' +
            'title="Close (Esc)" aria-label="Close">×</button></div>' +
            '<div class="pz-lightbox-stage fit"></div></div>';
        stage = root.querySelector(".pz-lightbox-stage");
        stage.appendChild(copy);
        root.querySelector(".hint").textContent =
            "fitted to the frame · click the plan to see it at full width";

        root.addEventListener("click", function (event) {
            if (event.target.closest(".pz-lightbox-close")) { close(); return; }
            if (!event.target.closest(".pz-lightbox-frame")) { close(); return; }
            if (event.target.closest(".pz-lightbox-stage")) toggle();
        });
        doc.addEventListener("keydown", onKey, true);
        doc.body.appendChild(root);
        root.querySelector(".pz-lightbox-close").focus();
    }

    doc.addEventListener("click", function (event) {
        const canvas = event.target.closest && event.target.closest(__TRIGGER__);
        if (canvas && !canvas.closest("#" + ROOT_ID)) open(canvas);
    });

    window.__pzLightbox = { open: open, close: close };
})();
"""

BOOTSTRAP = """
<script>
(function () {
    const win = window.parent;
    if (win.__pzLightbox) return;
    const holder = win.document.createElement("script");
    holder.id = "pz-lightbox-code";
    holder.textContent = __CODE__;
    win.document.head.appendChild(holder);
})();
</script>
"""


def install() -> None:
    """Make sure the page opens the floor plan large when it is clicked."""
    code = LIGHTBOX_CODE.replace("__TRIGGER__", json.dumps(TRIGGER))
    components.html(BOOTSTRAP.replace("__CODE__", json.dumps(code)), height=0)
