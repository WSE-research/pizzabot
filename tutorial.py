"""The guided tour through the shop.

It runs in the page itself: a veil over the app, a hole around the element the
step talks about, and a card with the explanation. Every step addresses an
element by the id the frontend gives it (`pz-...`), so the tour needs no
knowledge of Streamlit's own markup.

* first visit (no cookie `pizzabot_tutorial`) -> the tour starts by itself,
  after the shop front has been set up (`shopfront.welcome()`)
* `Skip` (or Esc) stops it and remembers that, so it does not come back
* the `Tutorial` button beside `New order` starts it again at any time

The steps are data; add one by adding a dictionary below.
"""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

COOKIE = "pizzabot_tutorial"

STEPS = [
    {
        "target": "#pz-button-rename",
        "title": "Your sign",
        "text": "This is a pizza bot built as a LangGraph process, and this "
                "is your pizzeria. Click the sign whenever you want to change "
                "the name; the line under it names the implementation that is "
                "currently behind the counter.",
    },
    {
        "target": "#pz-widget-implementation",
        "title": "Which bot answers",
        "text": "Switch between the registered implementations — the demo, "
                "Exercise 3 with rules, Exercise 3 LLM-backed. The frontend "
                "itself never changes: it reads the process out of whichever "
                "graph is loaded.",
    },
    {
        "target": "#pz-status",
        "title": "What the shop is doing",
        "text": "The green chip shows the step the order is in. The second "
                "chip says whether the AI-backed steps are answered by the "
                "model or, without an endpoint, by their rule twins.",
    },
    {
        "target": "#pz-transcript",
        "title": "The conversation",
        "text": "What you say and what the bot answers. New messages arrive "
                "one after another, half a second apart.",
    },
    {
        "target": "#pz-examples",
        "title": "Things you can say",
        "text": "Inputs that are known to work with this implementation, "
                "filtered by the step the order is in. One click sends them — "
                "hover to read what each one demonstrates.",
    },
    {
        "target": "#pz-input",
        "title": "Or type your own",
        "text": "Anything you type here goes through the same graph. Try an "
                "unknown pizza or an address outside the delivery area to see "
                "how the process refuses.",
    },
    {
        "target": "#pz-kitchen-tabs",
        "title": "In the kitchen",
        "text": "The five tabs show what the process did with your last "
                "sentence: the ticket of nodes that ran, a card per node, the "
                "state after the turn, the generated process model, and a "
                "description in words.",
    },
    {
        "target": "#pz-toggle-kitchen-view",
        "title": "Kitchen view",
        "text": "Turn the right-hand pane off when you only want the "
                "conversation — in front of an audience, for instance.",
    },
    {
        "target": "#pz-button-new-order",
        "title": "Start over",
        "text": "Clears the conversation and the state of the graph. The "
                "selected implementation stays as it is.",
    },
    {
        "target": "#pz-button-tutorial",
        "title": "And back to here",
        "text": "This button brings the tour back whenever you want it.",
    },
    {
        "target": "#pz-button-style",
        "title": "How the shop looks",
        "text": "Five styles, each with its own colours, type and icons — "
                "pick one in the overlay and the whole shop repaints, this "
                "tour included. Enjoy your pizza!",
    },
]

# The tour itself. The code is injected into the *page* (not into the
# component's iframe): Streamlit re-mounts component iframes on every rerun,
# and a tour whose buttons live in a destroyed iframe stops responding. The
# iframe below therefore only carries the steps over and presses "start".
TOUR_CODE = r"""
(function () {
    if (window.__pzTour) return;            // already installed on this page

    const doc = document;
    const STYLE_ID = "pz-tour-style";
    const ROOT_ID = "pz-tour";
    let steps = [], index = 0, root = null, hole = null, card = null;
    let shown = false;                      // did any step reach the screen?

    function config() { return window.__pzTourConfig || { steps: [], cookie: "tour" }; }

    function cookieSet() {
        return doc.cookie.split(";").some(function (part) {
            return part.trim().indexOf(config().cookie + "=") === 0;
        });
    }
    function remember() {
        doc.cookie = config().cookie + "=done; max-age=" + (60 * 60 * 24 * 365) +
                     "; path=/; SameSite=Lax";
    }

    function styles() {
        if (doc.getElementById(STYLE_ID)) return;
        const style = doc.createElement("style");
        style.id = STYLE_ID;
        // the colours and the three fonts are the ones shopfront.css() wrote
        // on :root, so the tour wears whichever style the guest picked; the
        // literals after the comma are only the fallback
        style.textContent = [
"#pz-tour { position: fixed; inset: 0; z-index: 2147483000; }",
"#pz-tour .pz-tour-veil { position: fixed; inset: 0; background: transparent; }",
"#pz-tour .pz-tour-hole { position: fixed; border-radius: 12px; pointer-events: none;",
"    box-shadow: 0 0 0 9999px rgba(30, 20, 14, 0.55);",
"    outline: 3px solid var(--crust, #E8A33D); transition: all 0.25s ease; }",
"#pz-tour .pz-tour-card { position: fixed; width: min(360px, 84vw);",
"    background: var(--dough, #FFF8EC); border: 3px solid var(--char, #2B211A);",
"    border-radius: 12px; padding: 0.9rem 1rem 0.8rem;",
"    font-family: var(--font-body, system-ui, sans-serif); color: var(--char, #2B211A);",
"    box-shadow: 0 10px 24px rgba(30, 20, 14, 0.25); transition: all 0.25s ease; }",
"#pz-tour .pz-tour-count { font-family: var(--font-mono, monospace); font-size: 0.68rem;",
"    letter-spacing: 0.12em; text-transform: uppercase; color: var(--slate, #7A6A58); }",
"#pz-tour h3 { font-family: var(--font-display, cursive); color: var(--tomato, #C8102E);",
"    font-weight: var(--sign-weight, 400); letter-spacing: var(--sign-spacing, 0);",
"    text-transform: var(--sign-transform, none);",
"    font-size: 1.3rem; margin: 0.1rem 0 0.35rem 0; }",
"#pz-tour p { font-size: 0.9rem; line-height: 1.35; margin: 0 0 0.75rem 0; }",
"#pz-tour .pz-tour-buttons { display: flex; gap: 0.4rem; align-items: center; }",
"#pz-tour .pz-tour-buttons .spacer { flex: 1 1 auto; }",
"#pz-tour button { font-family: inherit; font-weight: 600; font-size: 0.82rem;",
"    border: 2px solid var(--char, #2B211A); border-radius: 999px;",
"    background: var(--paper, #FFFFFF);",
"    color: var(--char, #2B211A); padding: 0.25rem 0.8rem; cursor: pointer; }",
"#pz-tour button:hover { background: var(--cheese, #FFE9A8); }",
"#pz-tour button.primary { background: var(--tomato, #C8102E);",
"    border-color: var(--tomato, #C8102E); color: var(--dough, #FFFFFF); }",
"#pz-tour button.primary:hover { background: var(--tomato-l, #E2503F);",
"    border-color: var(--tomato-l, #E2503F); }",
"#pz-tour button:disabled { opacity: 0.4; cursor: default; }",
"#pz-tour button.skip { border-color: var(--slate, #7A6A58); color: var(--slate, #7A6A58); }"
        ].join("\n");
        doc.head.appendChild(style);
    }

    function visible(step) {
        const el = doc.querySelector(step.target);
        if (!el) return null;
        const box = el.getBoundingClientRect();
        return (box.width > 0 && box.height > 0) ? el : null;
    }

    function reposition() {
        if (!root || !steps[index]) return;
        const el = visible(steps[index]);
        if (!el) return;
        const box = el.getBoundingClientRect();
        const pad = 6;
        hole.style.left = (box.left - pad) + "px";
        hole.style.top = (box.top - pad) + "px";
        hole.style.width = (box.width + 2 * pad) + "px";
        hole.style.height = (box.height + 2 * pad) + "px";

        const cardBox = card.getBoundingClientRect();
        const gap = 14;
        let top = box.bottom + gap;
        if (top + cardBox.height > window.innerHeight - 10) {
            top = box.top - cardBox.height - gap;
        }
        if (top < 10) {                     // neither below nor above: beside
            top = Math.min(Math.max(10, box.top),
                           window.innerHeight - cardBox.height - 10);
        }
        let left = box.left + box.width / 2 - cardBox.width / 2;
        left = Math.min(Math.max(10, left), window.innerWidth - cardBox.width - 10);
        card.style.top = Math.round(top) + "px";
        card.style.left = Math.round(left) + "px";
    }

    function render() {
        while (index < steps.length && !visible(steps[index])) index += 1;
        // remember the tour only when the user actually saw it -- a start
        // before the app has painted must be allowed to happen again
        if (index >= steps.length) { stop(shown); return; }
        shown = true;
        const step = steps[index];
        visible(step).scrollIntoView({ block: "center", behavior: "smooth" });
        card.querySelector(".pz-tour-count").textContent =
            "Step " + (index + 1) + " of " + steps.length;
        card.querySelector("h3").textContent = step.title;
        card.querySelector("p").textContent = step.text;
        card.querySelector(".back").disabled = index === 0;
        card.querySelector(".next").textContent =
            index === steps.length - 1 ? "Done" : "Next";
        requestAnimationFrame(reposition);
        setTimeout(reposition, 350);        // after the smooth scroll
        setTimeout(reposition, 700);
    }

    function onKey(event) {
        if (event.key === "Escape") { stop(true); }
        else if (event.key === "ArrowRight") { index += 1; render(); }
        else if (event.key === "ArrowLeft" && index > 0) { index -= 1; render(); }
    }

    function stop(done) {
        const open = doc.getElementById(ROOT_ID);
        if (open) open.remove();
        root = hole = card = null;
        window.removeEventListener("resize", reposition);
        window.removeEventListener("scroll", reposition, true);
        doc.removeEventListener("keydown", onKey, true);
        if (done) remember();
    }

    function start() {
        stop(false);
        styles();
        steps = config().steps || [];
        if (!steps.length) return;
        index = 0;
        shown = false;
        root = doc.createElement("div");
        root.id = ROOT_ID;
        root.innerHTML =
            '<div class="pz-tour-veil"></div>' +
            '<div class="pz-tour-hole"></div>' +
            '<div class="pz-tour-card">' +
            '<div class="pz-tour-count"></div><h3></h3><p></p>' +
            '<div class="pz-tour-buttons">' +
            '<button class="skip" id="pz-tour-skip">Skip</button>' +
            '<span class="spacer"></span>' +
            '<button class="back" id="pz-tour-back">Back</button>' +
            '<button class="next primary" id="pz-tour-next">Next</button>' +
            "</div></div>";
        doc.body.appendChild(root);
        hole = root.querySelector(".pz-tour-hole");
        card = root.querySelector(".pz-tour-card");
        root.querySelector(".skip").addEventListener("click", function () {
            stop(true);
        });
        root.querySelector(".back").addEventListener("click", function () {
            if (index > 0) { index -= 1; render(); }
        });
        root.querySelector(".next").addEventListener("click", function () {
            index += 1;
            if (index >= steps.length) { stop(true); return; }
            render();
        });
        window.addEventListener("resize", reposition);
        window.addEventListener("scroll", reposition, true);
        doc.addEventListener("keydown", onKey, true);
        render();
    }

    // the elements are named by a second script and the app paints in its own
    // time, so wait for the first target instead of guessing a delay
    function waitAndStart(attempt) {
        if ((config().steps || []).some(function (s) { return visible(s); })) {
            start();
            return;
        }
        if (attempt < 30) setTimeout(function () { waitAndStart(attempt + 1); }, 250);
    }

    window.__pzTour = {
        start: start,
        stop: stop,
        waitAndStart: waitAndStart,
        cookieSet: cookieSet,
        open: function () { return !!doc.getElementById(ROOT_ID); },
    };
})();
"""

# What the component iframe does: hand the steps over, make sure the tour code
# lives in the page, and decide whether to open it.
BOOTSTRAP = """
<script>
(function () {
    const win = window.parent;
    const doc = win.document;
    const CONFIG = __CONFIG__;
    win.__pzTourConfig = CONFIG;
    if (!win.__pzTour) {
        const holder = doc.createElement("script");
        holder.id = "pz-tour-code";
        holder.textContent = __CODE__;
        doc.head.appendChild(holder);
    }
    if (!win.__pzTour) return;              // injection blocked -- no tour
    if (CONFIG.force) {
        win.__pzTour.waitAndStart(0);
    } else if (!win.__pzTour.cookieSet() && !win.__pzTourSeen) {
        win.__pzTourSeen = true;            // only once per page session
        win.__pzTour.waitAndStart(0);
    }
})();
</script>
"""


def render(force: bool = False) -> None:
    """Install the tour; `force` starts it even when the cookie is set."""
    payload = json.dumps({"steps": STEPS, "cookie": COOKIE, "force": bool(force)})
    script = (BOOTSTRAP.replace("__CONFIG__", payload)
                       .replace("__CODE__", json.dumps(TOUR_CODE)))
    components.html(script, height=0)


def button() -> bool:
    """The `Tutorial` button, beside `New order`."""
    return st.button(
        "Tutorial", key="pz-widget-tutorial",
        help="Walk through the app step by step: what the picker does, where "
             "the examples come from, and what the kitchen pane shows. Runs "
             "by itself on your first visit; `Skip` or Esc ends it.")
