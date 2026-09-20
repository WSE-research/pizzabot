"""The shop front: whose pizzeria this is, and what it looks like.

Two things belong to the *guest*, not to the bot and not to the implementation
behind the counter: the **name** over the door and the **style** the shop is
decorated in. Both are asked once, when the app is opened for the first time,
and can be changed at any moment afterwards -- the name by clicking the sign,
the style through the button right of `Tutorial`.

    shopfront.init()            read name and style (cookies -> session)
    shopfront.font_import()     one @import for every style's fonts
    shopfront.css()             the :root block of the *active* style
    shopfront.welcome()         the first-visit screen; True while it is up
    shopfront.headline()        "<name>'s Pizza Bot"

A style is data -- colours, three fonts, a set of icons -- and nothing else in
the frontend knows how many there are. Adding a sixth is a dictionary below.
The colour names stay the ones the CSS of `streamlit_chat.py` already uses
(`--dough` is the page, `--paper` a card, `--char` the ink, `--tomato` the
accent), so a style is a complete repaint without touching a single rule.

Both values survive a reload in a cookie (`pizzabot_shop`, `pizzabot_style`),
which is read back through `st.context.cookies` when the session connects.
"""

from __future__ import annotations

import json
from urllib.parse import quote, unquote

import streamlit as st
import streamlit.components.v1 as components

COOKIE_NAME = "pizzabot_shop"
COOKIE_STYLE = "pizzabot_style"
DEFAULT_STYLE = "trattoria"
DEFAULT_NAME = "Da Mario"
YEAR = 60 * 60 * 24 * 365


# =========================================================================
# The five styles
# -------------------------------------------------------------------------
# `families` are Google-Fonts query fragments (all of them are imported once,
# so every style can be previewed in its own type); `display`, `body` and
# `mono` are the CSS font stacks the rules use through --font-*; `sign`
# adjusts the shop sign, because a script face and a condensed caps face do
# not want the same size. `colors` are the CSS variables, verbatim.
# =========================================================================

STYLES: dict[str, dict] = {
    "trattoria": {
        "name": "Trattoria",
        "tagline": "Forno digitale · dine in, deliver out",
        "blurb": "The house look: dough-coloured paper, tomato red, basil "
                 "green and a hand-written sign.",
        "families": ["Pacifico",
                     "Source+Sans+3:wght@300;400;600;700;900",
                     "Source+Code+Pro:wght@400;600"],
        "fonts": {
            "display": "'Pacifico', cursive",
            "body": "'Source Sans 3', system-ui, sans-serif",
            "mono": "'Source Code Pro', ui-monospace, monospace",
        },
        "sign": {"size": "2.9rem", "weight": "400", "spacing": "0",
                 "transform": "none"},
        "icons": {"bot": "🍕", "user": "🧑", "sign": "🍅",
                  "kitchen": "👩‍🍳", "board": "📋", "receipt": "🧾"},
        "colors": {
            "dough": "#FFF8EC", "paper": "#FFFFFF", "char": "#2B211A",
            "line": "#EADFCB", "slate": "#7A6A58",
            "tomato": "#C8102E", "tomato-l": "#E2503F",
            "basil": "#2E7D4F", "crust": "#E8A33D", "crust-d": "#C6791B",
            "cheese": "#FFE9A8",
        },
    },
    "notte": {
        "name": "Notte",
        "tagline": "Il forno di notte · open until the dough runs out",
        "blurb": "The late shift: a dark room, an ember-orange oven and "
                 "condensed capitals over the door.",
        "families": ["Bebas+Neue",
                     "Inter:wght@300;400;600;700;900",
                     "JetBrains+Mono:wght@400;600"],
        "fonts": {
            "display": "'Bebas Neue', Impact, sans-serif",
            "body": "'Inter', system-ui, sans-serif",
            "mono": "'JetBrains Mono', ui-monospace, monospace",
        },
        "sign": {"size": "3.3rem", "weight": "400", "spacing": "0.03em",
                 "transform": "uppercase"},
        "icons": {"bot": "🌜", "user": "🧑‍🍳", "sign": "🔥",
                  "kitchen": "🔥", "board": "🕯", "receipt": "🧾"},
        "colors": {
            "dough": "#16120F", "paper": "#241D18", "char": "#F4E7D5",
            "line": "#3B2E25", "slate": "#A08D77",
            "tomato": "#FF5A36", "tomato-l": "#FF8A5B",
            "basil": "#6FCF97", "crust": "#E8A33D", "crust-d": "#C6791B",
            "cheese": "#3A2C1E",
        },
    },
    "marina": {
        "name": "Marina",
        "tagline": "Pizzeria sul mare · sea breeze and lemon zest",
        "blurb": "The seaside terrace: azure and lemon on white, set in a "
                 "high-contrast serif.",
        "families": ["Playfair+Display:wght@400;600;700",
                     "Karla:wght@300;400;600;700",
                     "IBM+Plex+Mono:wght@400;600"],
        "fonts": {
            "display": "'Playfair Display', Georgia, serif",
            "body": "'Karla', system-ui, sans-serif",
            "mono": "'IBM Plex Mono', ui-monospace, monospace",
        },
        "sign": {"size": "2.6rem", "weight": "700", "spacing": "-0.01em",
                 "transform": "none"},
        "icons": {"bot": "🍋", "user": "⛵", "sign": "🌊",
                  "kitchen": "🐚", "board": "🗒", "receipt": "🧾"},
        "colors": {
            "dough": "#F2F8FB", "paper": "#FFFFFF", "char": "#10323F",
            "line": "#D7E7EE", "slate": "#5C7C8A",
            "tomato": "#0C6E8F", "tomato-l": "#3AA1C0",
            "basil": "#1F8A70", "crust": "#F2B705", "crust-d": "#C99000",
            "cheese": "#FFF3C4",
        },
    },
    "neon": {
        "name": "Neon",
        "tagline": "Slice arcade · open all night, in colour",
        "blurb": "The late-night arcade counter: magenta and cyan on deep "
                 "violet, with a tube-light sign.",
        "families": ["Monoton",
                     "Space+Grotesk:wght@300;400;600;700",
                     "Space+Mono:wght@400;700"],
        "fonts": {
            "display": "'Monoton', 'Space Grotesk', cursive",
            "body": "'Space Grotesk', system-ui, sans-serif",
            "mono": "'Space Mono', ui-monospace, monospace",
        },
        "sign": {"size": "2.1rem", "weight": "400", "spacing": "0.02em",
                 "transform": "none"},
        "icons": {"bot": "🤖", "user": "🕹", "sign": "⚡",
                  "kitchen": "🛠", "board": "💡", "receipt": "🎟"},
        "colors": {
            "dough": "#0D0B1A", "paper": "#171331", "char": "#EFE9FF",
            "line": "#322A5E", "slate": "#9E93C9",
            "tomato": "#FF2E88", "tomato-l": "#FF6EB0",
            "basil": "#21E6C1", "crust": "#FFD53D", "crust-d": "#E0B400",
            "cheese": "#2A2154",
        },
    },
    "bianco": {
        "name": "Bianco",
        "tagline": "Farina, acqua, sale · nothing else on the counter",
        "blurb": "The quiet one: stone, olive and paper white, set in a "
                 "modern serif — for a beamer in a bright room.",
        "families": ["Fraunces:opsz,wght@9..144,400;9..144,600",
                     "IBM+Plex+Sans:wght@300;400;600;700",
                     "IBM+Plex+Mono:wght@400;600"],
        "fonts": {
            "display": "'Fraunces', Georgia, serif",
            "body": "'IBM Plex Sans', system-ui, sans-serif",
            "mono": "'IBM Plex Mono', ui-monospace, monospace",
        },
        "sign": {"size": "2.5rem", "weight": "600", "spacing": "-0.015em",
                 "transform": "none"},
        "icons": {"bot": "🫒", "user": "🧑‍🎨", "sign": "🌾",
                  "kitchen": "🥄", "board": "📄", "receipt": "🧾"},
        "colors": {
            "dough": "#F7F5F1", "paper": "#FFFFFF", "char": "#23211E",
            "line": "#E2DCD1", "slate": "#8B857C",
            "tomato": "#6B7F3E", "tomato-l": "#8FA35C",
            "basil": "#3E7F6B", "crust": "#C9B79C", "crust-d": "#A08E72",
            "cheese": "#EDE7DA",
        },
    },
}

SWATCHES = ("tomato", "basil", "crust", "cheese", "char")


# =========================================================================
# What the session knows
# =========================================================================


def _cookie(name: str) -> str:
    """A cookie the browser sent when this session connected, or ""."""
    try:
        raw = st.context.cookies.get(name)
    except Exception:                                   # no context, no cookie
        return ""
    return unquote(raw) if raw else ""


def init() -> None:
    """Seed name and style from the cookies of a previous visit."""
    if "shop_name" not in st.session_state:
        st.session_state.shop_name = _cookie(COOKIE_NAME).strip()
    if "shop_style" not in st.session_state:
        remembered = _cookie(COOKIE_STYLE)
        st.session_state.shop_style = (remembered if remembered in STYLES
                                       else DEFAULT_STYLE)
    if "shop_setup" not in st.session_state:
        # no name remembered -> this is a first visit and we ask
        st.session_state.shop_setup = not st.session_state.shop_name


def style_key() -> str:
    return st.session_state.get("shop_style", DEFAULT_STYLE)


def current() -> dict:
    return STYLES.get(style_key(), STYLES[DEFAULT_STYLE])


def icon(name: str) -> str:
    return current()["icons"].get(name, "")


def name() -> str:
    return st.session_state.get("shop_name") or DEFAULT_NAME


def headline() -> str:
    """The sign over the door -- and it does not say "pizza" twice.

    A shop called "Da Mario" gets "Da Mario’s Pizza Bot"; a shop whose name
    already carries the word ("Saint Etiennes’ Best Pizza") is shown as it is.
    """
    shop = name()
    return shop if "pizza" in shop.lower() else f"{shop}’s Pizza Bot"


def needs_setup() -> bool:
    return bool(st.session_state.get("shop_setup"))


def remember() -> None:
    """Write name and style into cookies, so the next visit starts dressed.

    Called once per script run, from `create_chat_app`, and never before an
    `st.rerun()` -- the rerun ends the run before a component that was only
    just queued can reach the browser.
    """
    script = f"""
<script>
(function () {{
    const doc = window.parent.document;
    const tail = ";max-age={YEAR};path=/;SameSite=Lax";
    doc.cookie = "{COOKIE_NAME}=" + {json.dumps(quote(name()))} + tail;
    doc.cookie = "{COOKIE_STYLE}=" + {json.dumps(style_key())} + tail;
}})();
</script>"""
    components.html(script, height=0)


# =========================================================================
# The style, as CSS
# =========================================================================


def font_import() -> str:
    """One request for every family of every style -- previews need them all.

    The browser downloads a face only when a rule actually uses it, so the
    four styles that are not active cost a line of CSS and no font file.
    """
    families = []
    for style in STYLES.values():
        for family in style["families"]:
            if family not in families:
                families.append(family)
    query = "&".join(f"family={family}" for family in families)
    return (f"<style>@import url('https://fonts.googleapis.com/css2?{query}"
            "&display=swap');</style>")


def css() -> str:
    """The `:root` block of the active style -- every rule reads from here."""
    style = current()
    lines = [f"    --{key}: {value};"
             for key, value in style["colors"].items()]
    lines += [
        f"    --font-display: {style['fonts']['display']};",
        f"    --font-body: {style['fonts']['body']};",
        f"    --font-mono: {style['fonts']['mono']};",
        f"    --sign-size: {style['sign']['size']};",
        f"    --sign-weight: {style['sign']['weight']};",
        f"    --sign-spacing: {style['sign']['spacing']};",
        f"    --sign-transform: {style['sign']['transform']};",
    ]
    return "<style>:root {\n" + "\n".join(lines) + "\n}</style>"


def _swatch_row(style: dict) -> str:
    return "".join(
        f'<span class="pz-swatch" style="background:{style["colors"][key]}">'
        "</span>" for key in SWATCHES)


def _preview(key: str, style: dict, chosen: bool) -> str:
    """A card that shows a style *in that style* -- colours, type and icons."""
    colors = style["colors"]
    return (
        f'<div class="pz-style-card{" chosen" if chosen else ""}" '
        f'style="background:{colors["dough"]};border-color:{colors["char"]}">'
        f'<div class="pz-style-sign" style="font-family:{style["fonts"]["display"]};'
        f'color:{colors["tomato"]};font-size:{style["sign"]["size"]};'
        f'font-weight:{style["sign"]["weight"]};'
        f'letter-spacing:{style["sign"]["spacing"]};'
        f'text-transform:{style["sign"]["transform"]}">{style["name"]}</div>'
        f'<div class="pz-style-body" style="font-family:{style["fonts"]["body"]};'
        f'color:{colors["char"]}">{style["blurb"]}</div>'
        f'<div class="pz-style-icons">'
        + " ".join(style["icons"][slot] for slot in
                   ("bot", "user", "sign", "kitchen", "board"))
        + "</div>"
        f'<div class="pz-style-swatches">{_swatch_row(style)}</div>'
        f'<div class="pz-style-mono" style="font-family:{style["fonts"]["mono"]};'
        f'color:{colors["slate"]}">{key} · '
        f'{style["fonts"]["mono"].split(",")[0].strip(chr(39))}</div>'
        "</div>")


def _choose(key: str) -> None:
    st.session_state.shop_style = key


def style_chooser(columns: int = 5, prefix: str = "pick") -> bool:
    """The five cards side by side; True when one was clicked."""
    picked = False
    active = style_key()
    grid = st.columns(columns, gap="small")
    for position, (key, style) in enumerate(STYLES.items()):
        with grid[position % columns]:
            with st.container(key=f"pz-style-{prefix}-{key}"):
                st.markdown(_preview(key, style, key == active),
                            unsafe_allow_html=True)
                label = "✓ in use" if key == active else f"Use {style['name']}"
                if st.button(label, key=f"pz-widget-{prefix}-{key}",
                             disabled=key == active,
                             help=style["tagline"]):
                    _choose(key)
                    picked = True
    return picked


# =========================================================================
# Asking: once at the door, and whenever the guest wants
# =========================================================================


def welcome() -> bool:
    """The first-visit screen. Returns True while the shop is not open yet."""
    if not needs_setup():
        return False
    with st.container(key="pz-welcome"):
        st.markdown('<div class="pz-cloth">&nbsp;</div>', unsafe_allow_html=True)
        st.markdown('<div class="pz-kicker">Benvenuto · let us open your '
                    'pizzeria</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="pz-sign">{icon("sign")} Your Pizza Bot</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="pz-sub">Two questions, and the shop is '
                    'yours.</div>', unsafe_allow_html=True)
        st.markdown('<div class="pz-rule">&nbsp;</div>', unsafe_allow_html=True)

        st.markdown('<div class="pz-board-title">1 · What is your pizzeria '
                    'called?</div>', unsafe_allow_html=True)
        with st.container(key="pz-welcome-name"):
            entered = st.text_input(
                "Name of the pizzeria", value=st.session_state.shop_name,
                placeholder=DEFAULT_NAME, key="pz-widget-welcome-name",
                label_visibility="collapsed",
                help="It goes over the door: “<name>’s Pizza Bot”. You can "
                     "change it later by clicking the sign.")
        chosen_name = (entered or "").strip() or DEFAULT_NAME
        st.markdown('<div class="pz-note">over the door: '
                    f'<b>{chosen_name}’s Pizza Bot</b></div>',
                    unsafe_allow_html=True)

        st.markdown('<div class="pz-board-title">2 · Pick a style</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="pz-note">colours, type and icons — one click '
                    'repaints this page, so what you see is what you get; '
                    'changeable later through the style button</div>',
                    unsafe_allow_html=True)
        if style_chooser(prefix="welcome"):
            st.rerun()

        st.markdown('<div class="pz-rule">&nbsp;</div>', unsafe_allow_html=True)
        with st.container(key="pz-welcome-open"):
            if st.button("Open the shop ▸", key="pz-widget-welcome-open",
                         type="primary",
                         help="Keeps the name and the style in this browser "
                              "and takes you to the counter."):
                st.session_state.shop_name = chosen_name
                st.session_state.shop_setup = False
                st.rerun()            # the next run writes the cookies
    return True


@st.dialog("The name over the door")
def rename_dialog() -> None:
    st.markdown('<div class="pz-note">the sign reads “<i>&lt;name&gt;</i>’s '
                'Pizza Bot” — or just the name, when it already says pizza.'
                '</div>', unsafe_allow_html=True)
    with st.form("pz-form-rename", border=False):
        entered = st.text_input(
            "Name of the pizzeria", value=name(),
            key="pz-widget-rename-name", label_visibility="collapsed")
        if st.form_submit_button("Change the sign", type="primary"):
            st.session_state.shop_name = (entered or "").strip() or DEFAULT_NAME
            st.rerun()


@st.dialog("How the shop looks", width="large")
def style_dialog() -> None:
    st.markdown('<div class="pz-note">five styles, each with its own colours, '
                'type and icons. The pick is remembered in this browser.</div>',
                unsafe_allow_html=True)
    if style_chooser(prefix="dialog"):
        st.rerun()
    st.markdown(f'<div class="pz-note">in use: <b>{current()["name"]}</b> — '
                f'{current()["tagline"]}</div>', unsafe_allow_html=True)


def sign_button() -> bool:
    """The shop sign itself -- a button, so that clicking it can rename it."""
    return st.button(
        headline(), key="pz-widget-rename",
        help="Click the sign to change the name of your pizzeria.")


def style_button() -> bool:
    """The style button, right of `Tutorial`."""
    return st.button(
        f"{icon('sign')} Style", key="pz-widget-style",
        help=f"Change how the shop looks — colours, type and icons. "
             f"Currently: {current()['name']}.")
