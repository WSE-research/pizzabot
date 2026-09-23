"""Web frontend for a LangGraph bot — and for the *next* one, unchanged.

Two panes: the shop counter on the left, where the order is taken, and the
kitchen view on the right (switch in the header), which shows what the process
did with the last utterance.

Nothing in this file knows a node name, a state key or an endpoint. The
implementation is loaded through `app_loader` (listed in `apps.json`, paths and
credentials in `.env`), the process model is read from the compiled graph, and
the picture of it is generated on startup by `diagram`. Swapping the bot — L1,
L3 static, L3 LLM, whatever comes next — is a line in `apps.json`.

The shop itself belongs to whoever opened it: the name over the door and the
style it is decorated in are asked once and then kept in `shopfront`.

    streamlit run streamlit_chat.py

or, with the endpoint checks and the offline fallback, ./run_local.sh
"""

from __future__ import annotations

import base64
import html
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from langchain_core.messages import AIMessage, HumanMessage

import app_loader
import diagram
import llm_log
import shopfront
import test_runs
import tutorial
from app_loader import KIND_LABEL, LLM, RULE
from settings import HERE, settings

GREETING = ("Hi! I am a pizza bot. I can help you order a pizza. "
            "What would you like to order?")

# =========================================================================
# Look -- a pizzeria: a checked tablecloth band, a hand-written sign for the
# name, and a kitchen pane that stays technical on purpose: monospace, like
# a printed docket. *Which* pizzeria is the guest's decision, though: the
# palette, the three fonts and the icons arrive from `shopfront` as CSS
# variables, so every rule below is written once and holds for all five.
# =========================================================================

STYLE = """
<style>
/* The colours, the three fonts and the sign metrics are *not* here: they are
   the `:root` block `shopfront.css()` writes for the style the guest picked.
   Every rule below reads them, so a style change is a repaint and never an
   edit of this file.
     --dough page · --paper card · --char ink · --line hairline · --slate quiet
     --tomato accent · --tomato-l accent hover · --basil second accent
     --crust/--crust-d warm line · --cheese highlight
     --font-display sign · --font-body text · --font-mono technical        */

html, body, [class*="css"], .stApp {
    font-family: var(--font-body);
    line-height: 1.3;
    color: var(--char);
}
.stApp { background: var(--dough); }
/* Streamlit's own toolbar is a fixed bar over the page -- leave room for it,
   otherwise the first element (the tablecloth band) hides underneath. */
[data-testid="stHeader"] { background: transparent; height: 2.6rem; }
.block-container { padding-top: 3.1rem; max-width: 1500px; }

/* --- the tablecloth band --------------------------------------------- */
.pz-cloth {
    height: 22px; overflow: hidden; margin: 0 0 0.9rem 0;
    background: repeating-conic-gradient(
        var(--tomato) 0% 25%, var(--paper) 0% 50%) 0 0 / 22px 22px;
    border-bottom: 3px solid var(--char);
}

/* --- shop sign -------------------------------------------------------- */
.pz-sign { font-family: var(--font-display); font-size: var(--sign-size);
           font-weight: var(--sign-weight); letter-spacing: var(--sign-spacing);
           text-transform: var(--sign-transform);
           color: var(--tomato); line-height: 1.05; margin: 0.1rem 0; }
.pz-sub  { font-size: 1rem; color: var(--char); font-weight: 600; letter-spacing: 0.02em; }
.pz-kicker {
    font-family: var(--font-mono); font-size: 0.68rem;
    letter-spacing: 0.16em; text-transform: uppercase; color: var(--slate);
}
.pz-rule { border-top: 3px dashed var(--crust); margin: 0.7rem 0 1rem 0;
           height: 0; overflow: hidden; }

/* the sign is a button, so that clicking it can rename the shop; the
   !important is the answer to the one further down that repaints every
   other button from the style */
#pz-button-rename button, #pz-button-rename button:hover,
#pz-button-rename button:focus, #pz-button-rename button:active {
    font-family: var(--font-display); font-size: var(--sign-size);
    font-weight: var(--sign-weight); letter-spacing: var(--sign-spacing);
    text-transform: var(--sign-transform); line-height: 1.05;
    color: var(--tomato) !important; background: none !important;
    border: none !important; box-shadow: none;
    padding: 0; width: auto; text-align: left;
}
/* the label sits two divs deep and Streamlit sets both size and family
   there, so the sign is written onto the text itself, not only the button */
#pz-button-rename button p, #pz-button-rename button div {
    font-family: var(--font-display) !important;
    font-size: var(--sign-size) !important; font-weight: inherit;
    line-height: inherit; letter-spacing: inherit; text-transform: inherit;
}
#pz-button-rename button::after {
    content: "✎"; font-size: 0.34em; vertical-align: super;
    margin-left: 0.25em; opacity: 0; transition: opacity 0.15s;
}
#pz-button-rename button:hover { color: var(--tomato-l); }
#pz-button-rename button:hover::after { opacity: 0.65; }

/* --- chips ------------------------------------------------------------ */
.pz-chip {
    display: inline-block; font-family: var(--font-mono);
    font-size: 0.68rem; font-weight: 600; padding: 3px 9px; margin-right: 7px;
    border-radius: 999px; border: 2px solid var(--char); background: var(--paper);
    color: var(--char);
}
.pz-chip.open   { background: var(--basil); color: var(--dough); border-color: var(--basil); }
.pz-chip.oven   { background: var(--cheese); color: var(--char); border-color: var(--crust-d); }
.pz-chip.llm    { background: var(--tomato); color: var(--dough); border-color: var(--tomato); }
.pz-chip.rule   { background: var(--paper); color: var(--char); }
.pz-chip.mixed  { background: var(--crust); color: var(--char); border-color: var(--crust-d); }
.pz-chip.problem{ background: var(--tomato-l); color: var(--dough); border-color: var(--tomato); }
.pz-note {
    font-family: var(--font-mono); font-size: 0.7rem;
    color: var(--slate); margin: 0.15rem 0 0.5rem 0;
}
.pz-note.inline { display: inline; }

/* --- chat: order slips ------------------------------------------------ */
[data-testid="stChatMessage"] {
    background: var(--paper); border: 1px solid var(--line);
    border-left: 7px solid var(--crust); border-radius: 10px;
    padding: 0.6rem 0.9rem; margin-bottom: 0.5rem;
    box-shadow: 0 1px 0 rgba(0,0,0,0.06);
}
/* who spoke is in the label of the content, not in a testid of the avatar */
[data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) {
    border-left-color: var(--basil);
}
[data-testid="stChatMessage"] > div:first-child {      /* the avatar disc */
    background: var(--cheese) !important; color: var(--char) !important;
}

/* --- the menu board (a bordered Streamlit container) ------------------- */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--paper); border: 2px solid var(--char) !important;
    border-radius: 12px; padding: 0.15rem 0.5rem 0 0.5rem; margin-top: 0.5rem;
}
.pz-board-title {
    font-family: var(--font-display); color: var(--tomato);
    font-size: 1.35rem; margin: 0.2rem 0 0.1rem 0; font-weight: var(--sign-weight);
    letter-spacing: var(--sign-spacing); text-transform: var(--sign-transform);
}
/* Streamlit paints buttons from its own config theme, which is one palette
   and there are five -- so the surface colours are forced from :root. */
[data-testid^="stBaseButton-secondary"], [data-testid^="stBaseButton-primary"] {
    border: 2px solid var(--char) !important;
    background: var(--paper) !important; border-radius: 999px !important;
    color: var(--char) !important; font-weight: 600; font-size: 0.82rem;
    padding: 0.3rem 0.85rem; width: 100%; text-align: left;
}
[data-testid^="stBaseButton-secondary"]:hover,
[data-testid^="stBaseButton-primary"]:hover {
    background: var(--cheese) !important; border-color: var(--crust-d) !important;
    color: var(--char) !important;
}
[data-testid^="stBaseButton-secondary"]:disabled,
[data-testid^="stBaseButton-secondary"]:disabled:hover {
    background: var(--cheese) !important; color: var(--slate) !important;
    border-color: var(--line) !important;
}
[data-testid^="stBaseButton-primary"] {
    background: var(--tomato) !important; border-color: var(--tomato) !important;
    color: var(--dough) !important;
}
[data-testid^="stBaseButton-primary"]:hover {
    background: var(--tomato-l) !important;
    border-color: var(--tomato-l) !important; color: var(--dough) !important;
}
.pz-item-note {
    font-family: var(--font-mono); font-size: 0.65rem;
    color: var(--slate); margin: -0.35rem 0 0.55rem 0.9rem;
}

/* --- receipt ---------------------------------------------------------- */
.pz-receipt {
    background: var(--paper); border: 2px dashed var(--char); border-radius: 8px;
    padding: 0.6rem 0.9rem; font-family: var(--font-mono);
    font-size: 0.78rem; margin: 0.4rem 0 0.6rem 0;
}
.pz-receipt .quiet { color: var(--slate); }

/* --- kitchen pane ----------------------------------------------------- */
.pz-kitchen {
    font-family: var(--font-display); color: var(--char);
    font-size: 1.5rem; margin: 0 0 0.1rem 0; font-weight: var(--sign-weight);
    letter-spacing: var(--sign-spacing); text-transform: var(--sign-transform);
}
.pz-station {
    background: var(--paper); border: 1px solid var(--line);
    border-left: 7px solid var(--line); border-radius: 8px;
    padding: 0.5rem 0.75rem; margin-bottom: 0.5rem;
}
.pz-station.ran  { border-left-color: var(--basil); }
.pz-station.last { border-left-color: var(--tomato); }
.pz-station h4 {
    font-family: var(--font-mono); font-size: 0.9rem;
    font-weight: 600; margin: 0 0 0.25rem 0; color: var(--char);
}
.pz-station .role { font-family: var(--font-body); font-size: 0.72rem; color: var(--slate); }
.pz-station p { font-size: 0.8rem; margin: 0.18rem 0; }
.pz-station .keys {
    font-family: var(--font-mono); font-size: 0.69rem; color: var(--slate);
}
.pz-station .fail { font-size: 0.73rem; color: var(--slate); font-style: italic; }

.pz-ticket {
    font-family: var(--font-mono); font-size: 0.78rem;
    background: var(--paper); border: 2px dashed var(--char); border-radius: 8px;
    padding: 0.6rem 0.8rem;
}
.pz-ticket .step { padding: 0.18rem 0; border-bottom: 1px dotted var(--line); }
.pz-ticket .step:last-child { border-bottom: none; }
.pz-ticket .ms { color: var(--slate); }
.pz-ticket .keys { color: var(--crust-d); }
.pz-ticket .none { color: var(--slate); font-style: italic; }
.pz-ticket .no { color: var(--slate); }

.pz-state { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
.pz-state td { border-bottom: 1px dotted var(--line); padding: 4px 6px; vertical-align: top; }
.pz-state td.k { font-family: var(--font-mono); font-weight: 600; width: 44%; }
.pz-state td.v { font-family: var(--font-mono); }
.pz-state td.v.empty { color: var(--slate); }
.pz-state tr.set td.v { background: var(--cheese); }

/* --- widgets ---------------------------------------------------------- */
.pz-description {
    background: var(--paper); border: 1px dashed var(--char); border-radius: 8px;
    padding: 0.7rem 0.9rem; font-size: 0.86rem; color: var(--char);
}
.pz-account {
    background: var(--paper); border: 1px dashed var(--char); border-radius: 8px;
    padding: 0.7rem 0.9rem; font-size: 0.83rem; color: var(--char);
}
.pz-account p { margin: 0 0 0.45rem 0; line-height: 1.45; }
.pz-account p:last-child { margin-bottom: 0; }
.pz-account code { font-family: var(--font-mono); font-size: 0.76rem; color: var(--crust-d); }
/* the LLM calls tab: a prompt is a stack of messages, the answer the last */
.pz-llm { font-size: 0.76rem; }
.pz-llm .msg { border-left: 4px solid var(--line); padding: 0.1rem 0 0.1rem 0.55rem;
               margin-bottom: 0.45rem; }
.pz-llm .msg.answer { border-left-color: var(--basil); }
.pz-llm .role { font-family: var(--font-mono); font-size: 0.64rem;
                letter-spacing: 0.12em; text-transform: uppercase; color: var(--slate); }
.pz-llm pre { font-family: var(--font-mono); font-size: 0.72rem; white-space: pre-wrap;
              word-break: break-word; margin: 0.1rem 0 0 0; padding: 0.35rem 0.5rem;
              border-radius: 6px; color: var(--char); }
/* the test runs: a comparison table that scrolls sideways in a narrow pane */
.pz-runs-frame { overflow-x: auto; margin-bottom: 0.6rem; }
.pz-runs { width: 100%; border-collapse: collapse; font-family: var(--font-mono);
           font-size: 0.7rem; white-space: nowrap; }
.pz-runs th { text-align: left; color: var(--slate); font-weight: 600;
              border-bottom: 2px solid var(--char); padding: 3px 6px; }
.pz-runs td { border-bottom: 1px dotted var(--line); padding: 3px 6px; }
.pz-runs tr.set td { background: var(--cheese); }
.pz-runs td.all { color: var(--basil); font-weight: 600; }
.pz-runs td.none { color: var(--tomato); font-weight: 600; }
.pz-figure { background: var(--paper); border: 1px solid var(--line); border-radius: 8px;
             padding: 0.4rem; margin-bottom: 0.4rem; }
.pz-figure svg, .pz-figure img { display: block; width: 100%; height: auto; }
/* the floor plan at any size: the canvas is a share of the frame's width,
   and whatever does not fit scrolls inside the frame, never the page */
.pz-figure-scroll { overflow: auto; }
.pz-figure-scroll.zoomed { max-height: 72vh; }
.pz-figure-canvas { margin: 0 auto; }
/* the width control sits between the heading and the tabs: one quiet line */
#pz-kitchen-width [data-testid="stWidgetLabel"] p,
#pz-floor-plan-size [data-testid="stWidgetLabel"] p {
    font-family: var(--font-mono); font-size: 0.68rem; color: var(--slate);
}
#pz-kitchen-width [data-testid="stSlider"],
#pz-floor-plan-size [data-testid="stSlider"] { padding: 0 0.5rem; }
[data-baseweb="tab-highlight"] { background: var(--tomato) !important; }
/* five tabs have to fit the narrow pane: let the row wrap instead of
   scrolling behind a chevron */
[data-testid="stTabs"] > div > div {
    overflow-x: visible !important; flex-wrap: wrap !important;
}
[data-testid="stTab"] { padding: 0 0.42rem !important; }
[data-testid="stTab"] p { font-size: 0.8rem !important; color: var(--char); }

/* Streamlit's own theme is one palette and there are five, so the widgets
   are repainted from the same variables -- otherwise a dark style keeps a
   white select, a white code block and an invisible label. */
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label,
.stMarkdown, .stMarkdown p, [data-testid="stExpander"] summary,
[data-testid="stElementToolbarButton"] { color: var(--char); }
[data-testid="stSelectbox"] > div > div, [data-baseweb="select"] > div,
[data-baseweb="input"], [data-testid="stTextInputRootElement"] {
    background: var(--paper) !important; border-color: var(--char) !important;
    color: var(--char) !important;
}
/* the text itself carries Streamlit's own theme colour, which is one
   palette and not five -- it has to be overridden on the element */
input, textarea, [data-baseweb="select"] div, [data-baseweb="select"] svg {
    color: var(--char) !important;
}
input::placeholder, textarea::placeholder { color: var(--slate) !important; }
[data-baseweb="popover"] ul, [data-baseweb="menu"] {
    background: var(--paper) !important; color: var(--char) !important;
}
[data-baseweb="popover"] li { color: var(--char) !important; }
[data-baseweb="popover"] li:hover { background: var(--cheese) !important; }
[data-testid="stDialog"] { background: rgba(30, 20, 14, 0.5) !important; }
[data-testid="stDialog"] > div, [data-testid="stDialog"] section[role="dialog"] {
    background: var(--dough) !important; border-radius: 14px;
}
[data-testid="stDialog"] > div { border: 3px solid var(--char); }
[data-testid="stDialog"] h2, [data-testid="stDialog"] h3 {
    font-family: var(--font-display); color: var(--tomato);
    font-weight: var(--sign-weight); letter-spacing: var(--sign-spacing);
}
[data-testid="stExpander"] details {
    background: var(--paper); border-color: var(--line);
}
.stCode, .stCode pre, pre, code { background: var(--cheese) !important; }
.stCode code, pre code { color: var(--char) !important; }
[data-testid="stTooltipContent"] {
    background: var(--paper) !important; color: var(--char) !important;
    border: 1px solid var(--line);
}

/* --- the style cards -------------------------------------------------- */
/* a card is painted in the colours and the type of the style it offers, so
   the pick needs no preview button: the card *is* the preview. */
.pz-style-card {
    display: flex; flex-direction: column;
    border: 2px solid; border-radius: 12px; padding: 0.6rem 0.7rem 0.5rem;
    margin-bottom: 0.4rem; height: 210px;
}
.pz-style-card.chosen { box-shadow: 0 0 0 3px var(--crust); }
.pz-style-sign { line-height: 1.05; margin-bottom: 0.25rem; }
.pz-style-body { font-size: 0.74rem; line-height: 1.3; flex: 1 1 auto; }
.pz-style-icons { font-size: 1.05rem; letter-spacing: 0.1em; margin: 0.3rem 0 0.35rem; }
.pz-style-swatches { display: flex; gap: 4px; margin-bottom: 0.35rem; }
.pz-swatch { width: 100%; height: 12px; border-radius: 3px;
             border: 1px solid rgba(0,0,0,0.25); }
.pz-style-mono { font-size: 0.62rem; letter-spacing: 0.04em; }

/* --- the first visit --------------------------------------------------- */
#pz-welcome { max-width: 1150px; margin: 0 auto; }
#pz-welcome .stButton > button { text-align: center; }
#pz-welcome .pz-board-title { margin-top: 0.9rem; }

/* --- the footer: who built this, and where the source is -------------- */
/* It belongs below the input, on the bottom edge of the screen, so it is
   lifted out of the page flow and fixed there. Streamlit's own bottom bar
   (stBottom) is fixed at bottom: 0 as well, so the room for this strip is
   made by padding the bar's inner block -- see the block below. The element
   still renders inside the page, which is what gives it the id and lets the
   guided tour point at it. */
/* The bar is fixed, not the Streamlit container around it: that container is
   a vertical block whose height collapses to a few pixels, and a fixed box
   shorter than its content spills off the bottom of the screen. */
.st-key-pz-footer { height: 0; }
.pz-footer {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 999990;
    background: var(--dough);
}
.pz-footer-row {
    display: flex; flex-wrap: wrap; gap: 0.1rem 1.4rem;
    align-items: center; justify-content: space-between;
    max-width: 1500px; margin: 0 auto; padding: 0.24rem 1rem 0.46rem 1rem;
    font-family: var(--font-body); font-size: 0.8rem; color: var(--slate);
}
.pz-footer-row a { color: var(--tomato); text-decoration: none;
               border-bottom: 1px solid transparent; }
.pz-footer-row a:hover, .pz-footer-row a:focus { border-bottom-color: var(--tomato); }
.pz-footer-row .pz-source { font-family: var(--font-mono); font-size: 0.76rem; }
/* the cube rides on the text baseline and scales with it */
.pz-footer-row .pz-cube { height: 1.25em; width: auto; vertical-align: -0.3em;
                      margin-right: 0.32em; }
/* the welcome screen has no bottom bar, so it makes its own room */
#pz-welcome { padding-bottom: 2.6rem; }

/* --- the counter edge: Streamlit's bottom strip ----------------------- */
/* stBottom is transparent and hands the colour to an inner div, so both
   need the dough; the strip also gets the same dashed crust line as the
   header, and the pill has to reach *through* to the inner container --
   otherwise its square corners stick out of the rounded border. */
[data-testid="stBottom"] { background: var(--dough); }
[data-testid="stBottom"] > div {
    background: var(--dough);
    border-top: 3px dashed var(--crust);
}
[data-testid="stBottomBlockContainer"] {
    /* the bottom padding is the strip the footer sits in */
    max-width: 1500px; padding: 0.75rem 1rem 2.5rem 1rem;
}
[data-testid="stChatInput"] {
    border: 2px solid var(--char); border-radius: 999px;
    background: var(--paper); overflow: hidden;
}
[data-testid="stChatInput"] > div {
    background: var(--paper) !important; border: none !important;
    border-radius: 999px !important;
}
[data-testid="stChatInput"]:focus-within { box-shadow: 0 0 0 3px var(--cheese); }
[data-testid="stChatInput"] textarea {
    font-size: 0.95rem; color: var(--char); padding-left: 0.4rem;
    background: var(--paper);
}
[data-testid="stChatInput"] textarea::placeholder { color: var(--slate); }
[data-testid="stChatInput"] button { color: var(--tomato); }
[data-testid="stChatInput"] button:hover { background: var(--cheese); }

/* --- serving: one message at a time ----------------------------------- */
@keyframes pz-serve {
    from { opacity: 0; transform: translateY(10px) scale(0.99); }
    to   { opacity: 1; transform: none; }
}

/* --- clearing the counter for a new order ----------------------------- */
@keyframes pz-clear {
    from { opacity: 1; transform: none; }
    to   { opacity: 0; transform: translateY(-12px) scale(0.98); }
}
</style>
"""


# =========================================================================
# Element identity
# -------------------------------------------------------------------------
# Every element of this app sits in a container with a `key`, which Streamlit
# renders as the class `st-key-<key>`. The snippet below runs in the page and
#   * copies that key into the element's `id`, so each element is addressable
#     directly (`#pz-button-new-order`),
#   * adds a class per element *type* derived from its `data-testid`
#     (`pz-el-button`, `pz-el-chat-message`, `pz-el-tabs`, ...), so all
#     elements of one kind can be addressed together.
# A MutationObserver re-applies both after every Streamlit rerender.
# =========================================================================

IDENTITY_SCRIPT = """
<script>
(function () {
    const doc = window.parent.document;
    const KEY = "st-key-";
    function typeClass(testid) {
        return "pz-el-" + testid.replace(/^st/, "")
            .replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
    }
    // regions Streamlit renders itself, named so they can be addressed too
    const ALIASES = {
        '[data-testid="stBottom"]': "pz-input",
        '[data-testid="stMain"]': "pz-main",
        '[data-testid="stBottomBlockContainer"]': "pz-input-block",
    };
    function decorate() {
        Object.keys(ALIASES).forEach(function (selector) {
            const el = doc.querySelector(selector);
            if (el && !el.id) el.id = ALIASES[selector];
        });
        doc.querySelectorAll('[class*="' + KEY + '"]').forEach(function (el) {
            const marker = Array.from(el.classList)
                .find(function (c) { return c.indexOf(KEY) === 0; });
            if (!marker) return;
            const id = marker.slice(KEY.length);
            if (id && el.id !== id) el.id = id;
        });
        doc.querySelectorAll("[data-testid]").forEach(function (el) {
            const name = typeClass(el.getAttribute("data-testid"));
            if (!el.classList.contains(name)) el.classList.add(name);
        });
    }
    decorate();
    // childList only: our own id/class writes are attribute changes and
    // therefore cannot trigger this observer again.
    new MutationObserver(decorate)
        .observe(doc.body, { childList: true, subtree: true });
})();
</script>
"""


def install_identity():
    """Give every element a unique id and a class for its type."""
    components.html(IDENTITY_SCRIPT, height=0)


def serving_styles(keys: list[str], gap: float = 0.5) -> str:
    """One CSS rule per freshly served message: appear, then wait `gap`."""
    rules = []
    for position, key in enumerate(keys):
        rules.append(f".{key} {{ animation: pz-serve 0.45s ease-out both;"
                     f" animation-delay: {position * gap:.2f}s; }}")
    return "<style>" + "".join(rules) + "</style>"


# clearing the counter: the old conversation fades out, then the page stays
# empty for half a second before the bot says hello again
CLEAR_SECONDS = 0.4
CLEAR_PAUSE = 0.5


def clearing_styles() -> str:
    """Fade out everything the finished conversation put on the counter."""
    targets = ", ".join((".st-key-pz-transcript", ".st-key-pz-receipt",
                         ".st-key-pz-examples"))
    return (f"<style>{targets} {{ animation: pz-clear {CLEAR_SECONDS}s "
            "ease-in both; }</style>")


# =========================================================================
# The implementation behind the counter
# =========================================================================


@st.cache_resource(show_spinner="loading the process…")
def load_app(key: str):
    """Import the implementation once per session and read its process model."""
    return app_loader.load(key)


@st.cache_resource(show_spinner="drawing the process model…")
def draw(key: str, structure: str, _graph, title: str):
    """Generate the picture on startup -- `structure` keys the cache."""
    return diagram.render(_graph, key, title)


def current_app():
    return load_app(st.session_state.app_key)


# =========================================================================
# Session state
# =========================================================================

# How much of the page the kitchen view takes, in percent. 40 is the old
# fixed 3 : 2 split; the pane gets narrower for an audience and wider for
# reading a long prompt.
KITCHEN_WIDTHS = [25, 30, 35, 40, 45, 50, 55, 60, 65, 70]
KITCHEN_WIDTH = 40

# How large the floor plan is drawn, in percent of the pane's width. Above
# 100 the picture scrolls inside its frame instead of widening the page.
PLAN_SIZES = [50, 75, 100, 125, 150, 200, 250, 300]
PLAN_SIZE = 100


def init_session():
    if "app_key" not in st.session_state:
        st.session_state.app_key = settings.app_key
    if "bot_state" not in st.session_state:
        reset_dialog()
    if "show_pane" not in st.session_state:
        st.session_state.show_pane = True
    if "pending" not in st.session_state:
        st.session_state.pending = None
    if "serve_from" not in st.session_state:
        st.session_state.serve_from = 0
    if "clearing" not in st.session_state:
        st.session_state.clearing = False
    if "kitchen_width" not in st.session_state:
        st.session_state.kitchen_width = from_query("kitchen", KITCHEN_WIDTHS,
                                                    KITCHEN_WIDTH)
    if "llm_log" not in st.session_state:
        # one entry per turn, across orders: the LLM calls tab reads it
        st.session_state.llm_log = []
    if "plan_size" not in st.session_state:
        st.session_state.plan_size = from_query("plan", PLAN_SIZES, PLAN_SIZE)


def from_query(name: str, allowed: list[int], default: int) -> int:
    """A view setting out of the address bar -- so a link keeps the layout."""
    try:
        value = int(st.query_params.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value in allowed else default


def remember_in_query(name: str, value: int, default: int):
    """Write a view setting into the address bar; the default is left out."""
    if st.query_params.get(name) == (None if value == default else str(value)):
        return                                  # already there: no message
    if value == default:
        st.query_params.pop(name, None)
    else:
        st.query_params[name] = str(value)


def reset_dialog():
    app = current_app()
    st.session_state.bot_state = app.new_state("")
    st.session_state.transcript = [AIMessage(content=greeting(app))]
    st.session_state.trace = []
    st.session_state.turns = 0
    st.session_state.pending = None
    st.session_state.serve_from = 0
    st.session_state.order_no = st.session_state.get("order_no", 0) + 1


def greeting(app) -> str:
    return app.meta.get("greeting", GREETING)


def switch_app(key: str):
    st.session_state.app_key = key
    reset_dialog()


# =========================================================================
# One turn through the graph, with the node trace
# =========================================================================


def run_turn(user_input: str):
    """Send one utterance through whatever graph is loaded."""
    app = current_app()
    state = dict(st.session_state.bot_state)
    state[app.input_key] = user_input
    seen = len(app.messages(state))

    final_state = dict(state)
    trace = []
    # every LLM call of this turn -- through LangChain or the openai client
    recorder = llm_log.Recorder()
    log_llm_calls(user_input, recorder)
    started = time.perf_counter()
    try:
        # stream_mode="updates" yields {node_name: state_update} per node,
        # which is exactly what the kitchen pane shows -- for any graph.
        with recorder.recording():
            for chunk in app.graph.stream(state, config={"callbacks": [recorder]},
                                          stream_mode="updates"):
                now = time.perf_counter()
                for node_name, update in chunk.items():
                    update = update or {}
                    trace.append({
                        "node": node_name,
                        "ms": int((now - started) * 1000),
                        "writes": [key for key in update if key != app.message_key],
                    })
                    final_state.update(update)
                started = now
    except Exception as error:                      # keep the UI alive
        trace.append({"node": "error", "ms": 0, "writes": [], "error": str(error)})
        st.session_state.trace = trace
        st.session_state.transcript.append(
            AIMessage(content=f"The process raised an error: {error}"))
        return

    st.session_state.bot_state = final_state
    spoken = app.messages(final_state)[seen:]
    if spoken:
        st.session_state.transcript.extend(spoken)
    else:
        answer = app.answer_of(final_state)
        st.session_state.transcript.append(
            AIMessage(content=answer or "(nothing to say — see the ticket)"))
    st.session_state.trace = trace
    st.session_state.turns += 1


# the LLM calls tab keeps this many turns; older ones are dropped
LLM_LOG_TURNS = 60


def log_llm_calls(user_input: str, recorder: llm_log.Recorder):
    """Open the log entry of this turn -- the recorder fills it while it runs."""
    log = st.session_state.llm_log
    log.append({"no": log[-1]["no"] + 1 if log else 1,
                "order": st.session_state.order_no,
                "turn": st.session_state.turns + 1, "input": user_input,
                "at": time.strftime("%H:%M:%S"), "offline": settings.offline,
                "calls": recorder.calls})
    del log[:-LLM_LOG_TURNS]


# =========================================================================
# Shop front
# =========================================================================


def header():
    app = current_app()
    with st.container(key="pz-header"):
        st.markdown('<div class="pz-cloth">&nbsp;</div>', unsafe_allow_html=True)
        left, right = st.columns([3, 2])
        with left:
            with st.container(key="pz-brand"):
                st.markdown(f'<div class="pz-kicker">'
                            f'{shopfront.current()["tagline"]}</div>',
                            unsafe_allow_html=True)
                # the sign is a button: clicking it renames the pizzeria
                with st.container(key="pz-button-rename"):
                    if shopfront.sign_button():
                        shopfront.rename_dialog()
                st.markdown(f'<div class="pz-sub">{app.title} '
                            f'{shopfront.icon("sign")}</div>',
                            unsafe_allow_html=True)
        with right:
            with st.container(key="pz-controls"):
                implementation_picker()
                # one row: the kitchen-view switch and the three buttons
                controls = st.columns([1.25, 1, 1, 0.95], gap="small",
                                      vertical_alignment="center")
                with controls[0]:
                    with st.container(key="pz-toggle-kitchen-view"):
                        st.session_state.show_pane = st.toggle(
                            "Kitchen view", value=st.session_state.show_pane,
                            key="pz-widget-kitchen-view",
                            help="Show or hide the pane on the right: which "
                                 "nodes ran, what they wrote, the state and the "
                                 "process model of the loaded implementation.")
                with controls[1]:
                    with st.container(key="pz-button-new-order"):
                        if st.button(
                                "New order", key="pz-widget-new-order",
                                help="Start over: the conversation, the state of "
                                     "the graph and the last ticket are cleared, "
                                     "and the bot greets you again. The selected "
                                     "implementation stays as it is — use this "
                                     "before a new example, or after an order was "
                                     "placed."):
                            # the reset happens after the counter was cleared
                            # on screen -- see the end of create_chat_app()
                            st.session_state.clearing = True
                            st.rerun()
                with controls[2]:
                    with st.container(key="pz-button-tutorial"):
                        if tutorial.button():
                            st.session_state.tour = True
                            st.rerun()
                with controls[3]:
                    with st.container(key="pz-button-style"):
                        if shopfront.style_button():
                            shopfront.style_dialog()
        with st.container(key="pz-status"):
            st.markdown(status_line(), unsafe_allow_html=True)
        st.markdown('<div class="pz-rule">&nbsp;</div>', unsafe_allow_html=True)


# Where the group and the source live. The utm parameters follow the ones the
# other WSE web tools use, so a visit from this app is recognisable.
WSE_RESEARCH = ("https://wse-research.org/?utm_source=pizzabot&utm_medium=app"
                "&utm_campaign=pizzabot&utm_content=footer")
HTWK_LEIPZIG = "https://www.htwk-leipzig.de/"
REPOSITORY = "https://github.com/WSE-research/pizzabot"


@st.cache_data(show_spinner=False)
def wse_mark() -> str:
    """The WSE cube as a data URI.

    Streamlit serves nothing out of `assets/` unless static serving is turned
    on, and turning it on would publish the whole folder -- for one 128px mark
    that is the wrong trade. Read once, kept by the cache for the process.
    """
    path = HERE / "assets" / "wse-logo.png"
    if not path.is_file():                      # the mark is decoration
        return ""
    return "data:image/png;base64," + base64.b64encode(
        path.read_bytes()).decode("ascii")


def footer():
    """Who built this, on the left; where the source is, on the right.

    Fixed to the bottom edge of the screen, under the input -- see the
    `.st-key-pz-footer` rule.
    """
    mark = wse_mark()
    cube = f'<img class="pz-cube" src="{mark}" alt="">' if mark else ""
    with st.container(key="pz-footer"):
        st.markdown(
            f'<div class="pz-footer"><div class="pz-footer-row">'
            f'<span>Built by '
            f'<a href="{WSE_RESEARCH}" target="_blank" rel="noopener">'
            f'{cube}WSE Research</a> at '
            f'<a href="{HTWK_LEIPZIG}" target="_blank" rel="noopener">'
            f'Leipzig University of Applied Sciences</a></span>'
            f'<a class="pz-source" href="{REPOSITORY}" target="_blank" '
            f'rel="noopener" title="Source code on GitHub">'
            f'{REPOSITORY.split("//", 1)[1]}</a>'
            f'</div></div>', unsafe_allow_html=True)


def implementation_picker():
    """Which LangGraph implementation is behind the counter."""
    specs = app_loader.registry()  # noqa: E501
    usable = [spec for spec in specs if spec.available[0]]
    labels = {spec.key: spec.title for spec in usable}
    if not usable:
        st.error("no implementation available — check apps.json and .env")
        return
    keys = list(labels)
    if st.session_state.app_key not in keys:
        st.session_state.app_key = keys[0]
    chosen = st.selectbox(
        "Implementation", keys, index=keys.index(st.session_state.app_key),
        format_func=lambda key: labels[key], key="pz-widget-implementation",
        help="Which LangGraph implementation is behind the counter. Switching "
             "reloads the graph and starts a new conversation; the frontend "
             "itself does not change.")
    if chosen != st.session_state.app_key:
        switch_app(chosen)
        st.rerun()
    missing = [spec for spec in specs if not spec.available[0]]
    if missing:
        st.markdown('<div class="pz-note">not available: '
                    + " · ".join(f"{spec.key} ({spec.available[1]})"
                                 for spec in missing) + "</div>",
                    unsafe_allow_html=True)


def status_line() -> str:
    app = current_app()
    state = st.session_state.bot_state
    if app.is_ended(state):
        stage = "order is in the oven"
    elif st.session_state.turns == 0:
        stage = "waiting for your order"
    else:
        stage = f"turn {st.session_state.turns}"
    chips = [f'<span class="pz-chip open">OPEN · {stage}</span>']
    if settings.offline:
        chips.append('<span class="pz-chip oven">HOUSE RECIPE</span>'
                     '<span class="pz-note inline">no LLM endpoint: the AI-backed '
                     'steps run as rules</span>')
    else:
        chips.append(f'<span class="pz-chip llm">LLM · {settings.model_name or "unset"}</span>'
                     '<span class="pz-note inline">'
                     f'{settings.openai_api_base or "no endpoint configured"}</span>')
    return "".join(chips)


def chat_pane():
    app = current_app()
    fresh = []                       # messages served in this run, in order
    with st.container(key="pz-transcript"):
        for index, message in enumerate(st.session_state.transcript):
            # FunctionMessages (and tool messages) are protocol between the
            # nodes, not something the guest at the counter should read.
            kind = getattr(message, "type", "ai")
            if kind not in ("ai", "human"):
                continue
            key = f"pz-message-{index}"
            if index >= st.session_state.serve_from and kind == "ai":
                fresh.append(f"st-key-{key}")
            with st.container(key=key):
                if kind == "human":
                    with st.chat_message("user", avatar=shopfront.icon("user")):
                        st.write(message.content)
                else:
                    with st.chat_message("assistant",
                                         avatar=shopfront.icon("bot")):
                        st.write(getattr(message, "content", str(message)))
    if st.session_state.clearing:
        st.markdown(clearing_styles(), unsafe_allow_html=True)
    elif fresh:
        # every new message fades in, half a second after the one before it
        st.markdown(serving_styles(fresh), unsafe_allow_html=True)
    st.session_state.serve_from = len(st.session_state.transcript)

    if app.is_ended(st.session_state.bot_state):
        with st.container(key="pz-receipt"):
            receipt()
    example_buttons()


def receipt():
    state = st.session_state.bot_state
    rows = [f'<b>— {shopfront.name().upper()} · ORDER RECEIPT '
            f'{shopfront.icon("receipt")} —</b>']
    for key in ("slots", "order_id", "customer_address", "pizza_id"):
        value = state.get(key)
        if value:
            rows.append(f"{key:<10}{value}")
    rows.append('<span class="quiet">grazie! press “New order” to start again</span>')
    st.markdown('<div class="pz-receipt">' + "<br>".join(str(row) for row in rows)
                + "</div>", unsafe_allow_html=True)


def example_buttons():
    """Inputs that are known to work with *this* implementation, right now."""
    app = current_app()
    examples = app_loader.examples_for(app, st.session_state.bot_state)
    if not examples:
        return
    with st.container(border=True, key="pz-examples"):
        st.markdown(f'<h3 class="pz-board-title">{shopfront.icon("board")} '
                    'Things you can say</h3>', unsafe_allow_html=True)
        st.markdown('<div class="pz-note">tested examples for this step — '
                    'one click sends it</div>', unsafe_allow_html=True)
        columns = st.columns(2)
        for index, example in enumerate(examples):
            with columns[index % 2]:
                with st.container(key=f"pz-example-{index}"):
                    if st.button(
                            f'„{example["text"]}"',
                            key=f'pz-widget-example-{app.key}-'
                                f'{st.session_state.turns}-{index}',
                            help=f'{example.get("label", "")} — '
                                 f'{example.get("shows", "")}'):
                        st.session_state.pending = example["text"]
                        st.rerun()
                    st.markdown('<div class="pz-item-note">'
                                f'{example.get("label", "")}</div>',
                                unsafe_allow_html=True)


# =========================================================================
# Kitchen pane
# =========================================================================


def system_pane():
    with st.container(key="pz-kitchen"):
        st.markdown(f'<div class="pz-kitchen">{shopfront.icon("kitchen")} '
                    'In the kitchen</div>', unsafe_allow_html=True)
        st.markdown('<div class="pz-note">what the LangGraph process did with '
                    'your last sentence</div>', unsafe_allow_html=True)
        with st.container(key="pz-kitchen-width"):
            kitchen_width_control()
        with st.container(key="pz-kitchen-tabs"):
            (ticket_tab, nodes_tab, state_tab, graph_tab, account_tab,
             llm_tab, runs_tab) = st.tabs(["Ticket", "Stations", "Order pad",
                                           "Floor plan", "What happened",
                                           "LLM calls", "Test runs"])

            with ticket_tab:
                with st.container(key="pz-tab-ticket"):
                    render_trace()
            with nodes_tab:
                with st.container(key="pz-tab-stations"):
                    render_nodes()
            with state_tab:
                with st.container(key="pz-tab-order-pad"):
                    render_state()
            with graph_tab:
                with st.container(key="pz-tab-floor-plan"):
                    render_graph()
            with account_tab:
                with st.container(key="pz-tab-what-happened"):
                    render_what_happened()
            with llm_tab:
                with st.container(key="pz-tab-llm-calls"):
                    render_llm_calls()
            with runs_tab:
                with st.container(key="pz-tab-test-runs"):
                    render_test_runs()


def kitchen_width_control():
    """How wide the kitchen view is -- the chat column takes the rest."""
    def changed():
        st.session_state.kitchen_width = st.session_state["pz-widget-kitchen-width"]

    st.select_slider(
        "Width of the kitchen view", options=KITCHEN_WIDTHS,
        value=st.session_state.kitchen_width, key="pz-widget-kitchen-width",
        format_func=lambda share: f"{share} %", on_change=changed,
        help="How much of the page this pane takes; the conversation gets the "
             "rest. Kept for the session and in the address bar (`?kitchen=`), "
             "so a bookmark opens with the same layout.")


def plan_size_control():
    """How large the floor plan is drawn -- relative to the pane's width."""
    def changed():
        st.session_state.plan_size = st.session_state["pz-widget-floor-plan-size"]

    st.select_slider(
        "Size of the floor plan", options=PLAN_SIZES,
        value=st.session_state.plan_size, key="pz-widget-floor-plan-size",
        format_func=lambda size: f"{size} %", on_change=changed,
        help="100 % fits the picture to the pane. Larger sizes scroll inside "
             "the frame (drag the scrollbars, or shift + wheel sideways). "
             "Kept for the session and in the address bar (`?plan=`).")


def render_llm_calls():
    """The prompts of a turn, as they went to the endpoint, and the answers.

    Recorded by `llm_log` for whatever implementation is loaded -- from the
    LangChain callbacks the graph is run with, and from the openai client --
    so nothing here knows which node asks a model or how.
    """
    log = st.session_state.llm_log
    recorded = [entry for entry in log if entry["calls"]]
    if settings.offline and not recorded:
        st.markdown('<div class="pz-account"><p><b>Offline mode — no LLM '
                    'endpoint.</b> With <code>PIZZABOT_OFFLINE=1</code> the '
                    'AI-backed steps run as rules, so no prompt leaves this '
                    'process and there is nothing to show here.</p><p>Start '
                    'with an endpoint in <code>.env</code> (or '
                    '<code>./run_local.sh --online</code>) to see every prompt, '
                    'the answer and how long the endpoint took.</p></div>',
                    unsafe_allow_html=True)
        return
    if not log:
        st.markdown('<div class="pz-note">No turn yet — say something and every '
                    'prompt the process sends to an LLM will be listed here, with '
                    'the answer and the response time.</div>',
                    unsafe_allow_html=True)
        return

    total = sum(len(entry["calls"]) for entry in log)
    seconds = sum(call.get("ms", 0) for entry in log for call in entry["calls"]) / 1000
    st.markdown(f'<div class="pz-note">{total} LLM call(s) in {len(log)} turn(s) '
                f'of this session, {seconds:.1f}&nbsp;s waiting for the '
                'endpoint</div>', unsafe_allow_html=True)

    newest_first = list(reversed(log))

    def label(index: int) -> str:
        entry = newest_first[index]
        said = entry["input"] if len(entry["input"]) <= 40 else entry["input"][:39] + "…"
        return (f'order {entry["order"]} · turn {entry["turn"]} · „{said}“ · '
                f'{len(entry["calls"])} call(s)')

    # the key changes with every new turn, so the newest one is selected --
    # the running number, not the length, which stops growing at the cap
    index = st.selectbox("Turn", range(len(newest_first)), format_func=label,
                         key=f"pz-widget-llm-turn-{log[-1]['no']}")
    entry = newest_first[index]
    if not entry["calls"]:
        reason = ("offline mode: the AI-backed steps ran as rules"
                  if entry["offline"] else
                  "every station that ran in this turn was answered without a model")
        st.markdown(f'<div class="pz-note">No LLM call in this turn — {reason}.'
                    '</div>', unsafe_allow_html=True)
        return
    for position, call in enumerate(entry["calls"], start=1):
        with st.expander(llm_call_title(position, call), expanded=position == 1):
            st.markdown(llm_call_body(call), unsafe_allow_html=True)


def llm_call_title(position: int, call: dict) -> str:
    """One line per call: which model, which node, how long, what went wrong."""
    parts = [f'{position}. {call.get("model") or "unknown model"}']
    if call.get("node"):
        parts.append(f'node {call["node"]}')
    parts.append(f'{call.get("ms", 0)} ms')
    if call.get("error"):
        parts.append("ERROR")
    return " · ".join(parts)


def llm_call_body(call: dict) -> str:
    """The prompt as a list of messages, then the answer -- all escaped."""
    tokens = call.get("tokens") or {}
    facts = [f'via {call.get("source", "?")}']
    if tokens:
        facts.append(f'{tokens.get("prompt", "?")} prompt + '
                     f'{tokens.get("answer", "?")} answer tokens')
    rows = [f'<div class="pz-note">{" · ".join(facts)}</div>',
            '<div class="pz-llm">']
    for message in call.get("messages", []):
        rows.append(f'<div class="msg"><span class="role">'
                    f'{html.escape(message.get("role", "?"))}</span>'
                    f'<pre>{html.escape(message.get("content", ""))}</pre></div>')
    if call.get("error"):
        rows.append('<div class="msg answer"><span class="role">error</span>'
                    f'<pre>{html.escape(call["error"])}</pre></div>')
    else:
        rows.append('<div class="msg answer"><span class="role">answer</span>'
                    f'<pre>{html.escape(call.get("answer") or "(empty)")}</pre></div>')
    rows.append("</div>")
    return "".join(rows)


def render_test_runs():
    """Play the example dialogue against this implementation, and compare runs.

    The run happens beside the conversation, not in it: it starts from a
    fresh state of its own, so the order at the counter stays where it is.
    Every run is a JSON file in `runs/`, and the table compares all of them --
    across implementations, models and offline mode.
    """
    app = current_app()
    turns = test_runs.dialogue()
    st.markdown(f'<div class="pz-note">plays <code>{test_runs.DIALOGUE.name}'
                f'</code> ({len(turns)} turns, the dialogue of '
                '<code>test_pizzabot.py</code>) against the implementation behind '
                'the counter — your conversation stays as it is. A turn passes '
                'when the expected answer is contained in what the bot said.'
                '</div>', unsafe_allow_html=True)
    with st.container(key="pz-button-run-tests"):
        # off by default: the last turn completes the order, and a working
        # implementation then places a real one with the Pizza API
        place_order = st.checkbox(
            "Place the real order", value=False, key="pz-widget-place-order",
            help="Also sends the last utterance of the dialogue, which "
                 "completes the order — a working implementation then places "
                 "a real order with the Pizza API, as test_pizzabot.py does. "
                 "Off, that turn is skipped and left out of the verdict.")
        run_now = st.button(
            f"Run the test dialogue on {app.key}", key="pz-widget-run-tests",
            help="Sends the utterances of the example dialogue one after the "
                 "other into a fresh state, grades every answer against the "
                 "expected one and stores the run in runs/.")
    if run_now:
        progress = st.progress(0.0, text="starting…")

        def on_turn(position: int, total: int):
            progress.progress((position - 1) / total,
                              text=f"turn {position} of {total}")

        try:                                    # keep the UI alive
            run = test_runs.execute(app, on_turn=on_turn, place_order=place_order)
            st.session_state.last_run = test_runs.save(run).name
        except Exception as error:
            st.error(f"The test run did not complete: {type(error).__name__}: "
                     f"{error}")
        progress.empty()

    runs = test_runs.history()
    if not runs:
        st.markdown('<div class="pz-note">No run stored yet — the button above '
                    'makes the first one.</div>', unsafe_allow_html=True)
        return

    st.markdown(f'<div class="pz-note">{len(runs)} run(s) in '
                f'<code>{html.escape(settings.runs_dir.name)}/</code>, newest first — '
                'highlighted: the one just made</div>', unsafe_allow_html=True)
    rows = ['<div class="pz-runs-frame"><table class="pz-runs"><tr>'
            '<th>when</th><th>implementation</th><th>mode</th><th>passed</th>'
            '<th>time</th><th>LLM</th><th>rev</th></tr>']
    for run in runs:
        fresh = run.get("file") == st.session_state.get("last_run")
        verdict = "all" if run["passed"] == run["total"] else (
            "none" if run["passed"] == 0 else "some")
        rows.append(
            f'<tr class="{"set" if fresh else ""}">'
            f'<td>{html.escape(run.get("started", "")[:16].replace("T", " "))}</td>'
            f'<td title="{html.escape(str(run.get("title", "")))}">'
            f'{html.escape(str(run.get("implementation", "")))}</td>'
            f'<td>{html.escape(run_mode(run))}</td>'
            f'<td class="{verdict}">{html.escape(run_passed(run))}</td>'
            f'<td>{run.get("duration_ms", 0) / 1000:.1f}&nbsp;s</td>'
            f'<td>{run.get("llm_calls", 0)}</td>'
            f'<td>{html.escape(str(run.get("revision", "") or "—"))}</td></tr>')
    rows.append("</table></div>")
    st.markdown("".join(rows), unsafe_allow_html=True)

    def label(index: int) -> str:
        run = runs[index]
        return (f'{run.get("started", "")[:16].replace("T", " ")} · '
                f'{run.get("implementation", "")} · {run_mode(run)} · '
                f'{run_passed(run)}')

    chosen = st.selectbox("Turns of the run", range(len(runs)), format_func=label,
                          key=f"pz-widget-test-run-{runs[0].get('file', '')}")
    render_run_turns(runs[chosen])


def run_mode(run: dict) -> str:
    """Offline, or the model that answered -- the column that makes runs comparable."""
    if run.get("mode") == "offline":
        return "offline · rules"
    return str(run.get("model") or "LLM")


def run_passed(run: dict) -> str:
    """Passed of graded turns -- and how many were not sent (the real order)."""
    skipped = run.get("skipped", 0)
    return f'{run["passed"]}/{run["total"]}' + (f" · {skipped} skipped"
                                                if skipped else "")


def render_run_turns(run: dict):
    """One card per turn: said, expected, answered, and how long it took."""
    for turn in run.get("turns", []):
        if turn.get("skipped"):
            css, mark, chip = "pz-station", "SKIPPED", "rule"
        elif turn.get("passed"):
            css, mark, chip = "pz-station ran", "PASS", "open"
        else:
            css, mark, chip = "pz-station last", "FAIL", "problem"
        facts = html.escape(f'{turn.get("ms", 0)} ms · similarity '
                            f'{turn.get("similarity", 0)} · '
                            f'{turn.get("llm_calls", 0)} LLM call(s)')
        lines = [f'<div class="{css}">',
                 f'<h4>{html.escape(str(turn.get("turn", "?")))}. '
                 f'<span class="pz-chip {chip}">{mark}</span>'
                 f'<span class="role">{"" if turn.get("skipped") else facts}'
                 '</span></h4>',
                 f'<p><b>said</b> {html.escape(str(turn.get("input", "")))}</p>',
                 f'<p class="keys">expected: '
                 f'{html.escape(str(turn.get("expected", "")))}</p>']
        if turn.get("skipped"):
            lines.append('<p class="fail">not sent — this turn completes the '
                         'order, and a working implementation would place a '
                         'real one with the Pizza API. Tick <b>Place the real '
                         'order</b> to send it.</p>')
        else:
            lines.append(f'<p class="keys">answered: '
                         f'{html.escape(str(turn.get("actual") or "(nothing)"))}</p>')
        if turn.get("nodes"):
            path = " → ".join(str(node) for node in turn["nodes"])
            lines.append(f'<p class="keys">→ {html.escape(path)}</p>')
        if turn.get("error"):
            lines.append(f'<p class="fail">{html.escape(str(turn["error"]))}</p>')
        lines.append("</div>")
        st.markdown("".join(lines), unsafe_allow_html=True)


def render_what_happened():
    """The last turn in words -- from the bot if it can say, else from the run.

    A bot that keeps a process knowledge graph (one annotation per request to
    a component: who was asked, what it was given, what it returned, how sure)
    can verbalize it and offers `what_happened(target)`. One that does not
    still gets an account here, assembled from the trace this pane already
    has -- honestly labelled as such, because it is the frontend talking, not
    the process.
    """
    app = current_app()
    if not st.session_state.trace:
        st.markdown('<div class="pz-note">No turn yet — say something and this '
                    'tab will tell you what the process did with it.</div>',
                    unsafe_allow_html=True)
        return

    sentences, note = [], ""
    if app.explains:
        try:
            sentences = app.explanation(st.session_state.bot_state)
            note = (f'explained by the implementation itself — '
                    f'<code>{app.explain_name}()</code> over its process graph')
        except Exception as failure:                  # keep the UI alive
            note = (f'<b>{app.explain_name}()</b> raised '
                    f'<code>{type(failure).__name__}: {failure}</code>')
    if not sentences:
        sentences = account_from_trace(app)
        note = (note + " — " if note else "") + (
            'this implementation has no explanation of its own, so the account '
            'below is read from the run: the stations that ran, in order')

    st.markdown(f'<div class="pz-note">{note}</div>', unsafe_allow_html=True)
    rows = ['<div class="pz-account">']
    rows += [f'<p>{sentence}</p>' for sentence in sentences]
    rows.append("</div>")
    st.markdown("".join(rows), unsafe_allow_html=True)


def account_from_trace(app) -> list[str]:
    """The fallback account: what the frontend itself watched happen."""
    said = st.session_state.bot_state.get(app.input_key) or ""
    lines = [f'You said <i>&ldquo;{said}&rdquo;</i>. '
             f'{len(st.session_state.trace)} station(s) ran:'] if said else []
    for position, step in enumerate(st.session_state.trace, start=1):
        if "error" in step:
            lines.append(f'<b>{position}.</b> the process stopped with an error: '
                         f'<code>{step["error"]}</code>')
            continue
        info = app.nodes.get(step["node"], {})
        purpose = (info.get("purpose") or "").rstrip(".")
        written = (", ".join(f"<code>{key}</code>" for key in step["writes"])
                   if step["writes"] else "nothing new")
        lines.append(
            f'<b>{position}. {step["node"]}</b> '
            f'({kind_chip(info.get("kind", RULE))}, {step["ms"]}&nbsp;ms)'
            + (f' — {purpose}' if purpose else "")
            + f'. It wrote {written} into the order pad.')
    return lines


def kind_chip(kind: str) -> str:
    """The chip label -- offline, an LLM step is answered by its rule twin."""
    if kind == LLM and settings.offline:
        return "LLM step · rules today"
    return KIND_LABEL.get(kind, kind)


def render_trace():
    app = current_app()
    if not st.session_state.trace:
        st.markdown('<div class="pz-note">No turn yet — say something and the '
                    'nodes that ran will be printed here, in order.</div>',
                    unsafe_allow_html=True)
        return
    rows = ['<div class="pz-ticket">',
            f'<div class="step"><b>TICKET #{st.session_state.turns}</b> '
            f'<span class="ms">· {len(st.session_state.trace)} node(s) '
            f'· entry {app.entry}</span></div>']
    for position, step in enumerate(st.session_state.trace, start=1):
        if "error" in step:
            rows.append('<div class="step"><span class="pz-chip problem">ERROR</span>'
                        f'{step["error"]}</div>')
            continue
        info = app.nodes.get(step["node"], {})
        kind = info.get("kind", RULE)
        writes = ", ".join(step["writes"]) if step["writes"] else None
        written = (f'<span class="keys">writes {writes}</span>' if writes
                   else '<span class="none">no state change</span>')
        rows.append(
            f'<div class="step"><span class="no">{position}.</span> '
            f'<b>{step["node"]}</b> '
            f'<span class="pz-chip {kind}">{kind_chip(kind)}</span>'
            f'<span class="ms">{step["ms"]} ms</span><br>'
            f'&nbsp;&nbsp;&nbsp;{written}</div>')
    rows.append('</div>')
    st.markdown("".join(rows), unsafe_allow_html=True)


def render_nodes():
    app = current_app()
    ran = [step["node"] for step in st.session_state.trace]
    last = ran[-1] if ran else None
    st.markdown(f'<div class="pz-note">the {len(app.nodes)} nodes of the compiled '
                'graph — green: ran in the last turn, red: ran last</div>',
                unsafe_allow_html=True)
    for name, info in sorted(app.nodes.items(), key=lambda item: item[1]["order"]):
        css = "pz-station"
        if name in ran:
            css += " last" if name == last else " ran"
        kind = info["kind"]
        lines = [f'<div class="{css}">',
                 f'<h4>{name} <span class="pz-chip {kind}">{kind_chip(kind)}</span>'
                 f'<span class="role">{info.get("station", "")}</span></h4>']
        if info.get("purpose"):
            lines.append(f'<p>{info["purpose"]}</p>')
        if info.get("routes_to"):
            lines.append(f'<p class="keys">→ {", ".join(info["routes_to"])}</p>')
        if info.get("services"):
            lines.append('<p class="keys">' + "<br>".join(info["services"]) + "</p>")
        if info.get("failure"):
            lines.append(f'<p class="fail">{info["failure"]}</p>')
        if info.get("code"):
            lines.append(f'<p class="keys">{info["code"]}</p>')
        lines.append("</div>")
        st.markdown("".join(lines), unsafe_allow_html=True)
    if settings.offline:
        st.markdown('<div class="pz-note">house recipe: the '
                    f'<b>{KIND_LABEL[LLM]}</b> steps run as rules — same '
                    'contract, other implementation</div>', unsafe_allow_html=True)


def render_state():
    app = current_app()
    state = st.session_state.bot_state
    st.markdown('<div class="pz-note">the state after the last turn — '
                'highlighted: what is already written down</div>',
                unsafe_allow_html=True)
    rows = ['<table class="pz-state">']
    for key, description in app.state_keys.items():
        if key == app.input_key:
            continue
        raw = state.get(key)
        if key == app.message_key:
            value, filled = f"{len(app.messages(state))} message(s)", bool(raw)
        else:
            filled = raw not in (None, False, "", [], {})
            value = "—" if not filled else str(raw)
            if len(value) > 90:
                value = value[:87] + "…"
        rows.append(f'<tr class="{"set" if filled else ""}">'
                    f'<td class="k" title="{description}">{key}</td>'
                    f'<td class="v {"" if filled else "empty"}">{value}</td></tr>')
    rows.append("</table>")
    st.markdown("".join(rows), unsafe_allow_html=True)


def render_graph():
    app = current_app()
    nodes, edges = diagram.structure(app.graph)
    fingerprint = diagram.fingerprint(nodes, edges)
    kind, payload = draw(app.key, fingerprint, app.graph, app.title)
    if kind == "png" and not Path(payload).is_file():   # generated file went away
        draw.clear()
        kind, payload = draw(app.key, fingerprint, app.graph, app.title)
    st.markdown('<div class="pz-note">generated from the compiled graph when the '
                'implementation was loaded</div>', unsafe_allow_html=True)
    if kind in ("png", "svg"):
        with st.container(key="pz-floor-plan-size"):
            plan_size_control()
        size = st.session_state.plan_size
        if kind == "png":
            # an <img> rather than st.image, so it scales like the SVG does
            data = base64.b64encode(Path(payload).read_bytes()).decode("ascii")
            picture = (f'<img src="data:image/png;base64,{data}" '
                       f'alt="process model of {html.escape(app.title)}">')
        else:
            picture = payload
        # up to 100 % the picture is shown whole; beyond, the frame keeps a
        # fixed height and scrolls both ways
        frame = "pz-figure pz-figure-scroll" + (" zoomed" if size > 100 else "")
        st.markdown(f'<div class="{frame}">'
                    f'<div class="pz-figure-canvas" style="width:{size}%">'
                    f'{picture}</div></div>', unsafe_allow_html=True)
    else:
        st.code(payload, language="text")
    with st.expander("mermaid source"):
        st.code(diagram.mermaid(app.graph), language="text")


# =========================================================================
# App
# =========================================================================


def create_chat_app():
    # the style decides the page icon, so it has to be known before the page
    # is configured -- reading cookies and session state is not an element
    shopfront.init()
    st.set_page_config(page_title=f"{shopfront.name()} · Pizza Bot",
                       page_icon=shopfront.icon("sign"), layout="wide")
    st.markdown(shopfront.font_import(), unsafe_allow_html=True)
    st.markdown(shopfront.css(), unsafe_allow_html=True)   # the picked style
    st.markdown(STYLE, unsafe_allow_html=True)             # the rules over it
    install_identity()

    # first visit: ask for the name and the style before anything is loaded
    if shopfront.welcome():
        footer()          # the welcome screen is the first page anybody sees
        return
    shopfront.remember()

    init_session()
    # the view settings go into the address bar on every run -- written from
    # a widget callback, Streamlit does not pass them on to the browser
    remember_in_query("kitchen", st.session_state.kitchen_width, KITCHEN_WIDTH)
    remember_in_query("plan", st.session_state.plan_size, PLAN_SIZE)
    # the tour runs itself on the first visit (no cookie) and whenever the
    # Tutorial button was pressed
    tutorial.render(force=st.session_state.pop("tour", False))

    # a click on an example, or the chat input of the previous run -- run it
    # before the header, so the header shows the step we are in *now*
    if st.session_state.pending and not st.session_state.clearing:
        pending, st.session_state.pending = st.session_state.pending, None
        st.session_state.transcript.append(HumanMessage(content=pending))
        with st.spinner("the process is running…"):
            run_turn(pending)

    header()

    # pz-output holds everything the process says, pz-input what is sent to it
    with st.container(key="pz-output"):
        if st.session_state.show_pane:
            share = st.session_state.kitchen_width
            chat_column, system_column = st.columns([100 - share, share],
                                                    gap="large")
        else:
            chat_column, system_column = st.container(key="pz-chat-only"), None

        with chat_column:
            with st.container(key="pz-chat"):
                chat_pane()
        if system_column is not None:
            with system_column:
                system_pane()

    if not current_app().is_ended(st.session_state.bot_state):
        # no container around this one: it would leave Streamlit's fixed
        # bottom bar (stBottom) and scroll away with the page. The bar itself
        # is given the id `pz-input` by the identity script.
        user_input = st.chat_input("Type your order…", key="pz-widget-chat-input")
        if user_input:
            st.session_state.pending = user_input
            st.rerun()

    footer()          # last in the page, and fixed to the bottom of the screen

    if st.session_state.clearing:
        # the page above has been sent to the browser and is fading out; wait
        # for the animation, keep the counter empty for half a second, and
        # only then greet again -- the greeting arrives with its own animation
        time.sleep(CLEAR_SECONDS + CLEAR_PAUSE)
        reset_dialog()
        st.session_state.clearing = False
        st.rerun()


if __name__ == "__main__":
    create_chat_app()
