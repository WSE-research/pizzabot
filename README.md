# Pizza Bot — a LangGraph dialog process with a shop front

A task-oriented dialog process (order a pizza, slot by slot) built with LangGraph, plus two frontends: a console script and a Streamlit web app.

The web app is **not tied to this bot**. It loads whichever LangGraph implementation `apps.json` lists — the demo here, Exercise 3 in its static configuration, Exercise 3 LLM-backed, whatever comes next — reads the process model out of the compiled graph, and draws it. Changing the bot never means changing the frontend. If you have written your own graph and want it behind this counter, go to [*Plugging your own LangGraph implementation into this frontend*](#plugging-your-own-langgraph-implementation-into-this-frontend).

The shop itself is the guest's: the name over the door and the style it is decorated in are asked once, when the app is opened, and can be changed at any time.

## Quick start (instructor)

```sh
./run_local.sh
```

One command starts everything. The graph is **not** a separate server — the Streamlit app compiles it in-process — so the script's job is everything that must be true before that works:

1. a virtual environment (`.venv`) with the pinned requirements,
2. a `.env` file (copied from `.env-example` when missing),
3. a reachable **Pizza API** (menu, address validation, orders),
4. a reachable **LLM endpoint** — and, when there is none, the offline mode described below,
5. the implementations from `apps.json`, with the reason when one is not loadable.

| call | what it does |
|---|---|
| `./run_local.sh` | checks, then the web UI on http://localhost:8501 |
| `./run_local.sh --app l3-static` | start with that implementation selected |
| `./run_local.sh --apps` | list the implementations and stop |
| `./run_local.sh --console` | checks, then the console bot (`pizzabot.py`) |
| `./run_local.sh --check` | only the checks, starts nothing — the pre-lecture smoke test |
| `./run_local.sh --offline` / `--online` | force the rule implementations / insist on the LLM |
| `./run_local.sh --port 8502` | another port |
| `./run_local.sh --no-venv` | use the interpreter that is already active |

## What the web UI shows

**Left — the counter.** The conversation, and under it a board of **example inputs that are known to work** *with the loaded implementation*, filtered by the step the dialog is in. One click sends them; the tooltip says what each demonstrates.

**Right — the kitchen view** (switch in the header). Five tabs, all filled from the compiled graph:

* **Ticket** — the nodes that ran for the last sentence, in order, with the time they took and the state keys each one wrote. Read from `graph.stream(..., stream_mode="updates")`, so it is what actually happened.
* **Stations** — one card per node: what it does, where it routes, which external service it calls, how it fails, and where its code lives. Green = ran in the last turn, red = ran last.
* **Order pad** — the state after the last turn, with the filled values highlighted.
* **Floor plan** — the process model, **generated when the implementation is loaded** (see below).
* **Description** — the last process told as a sentence; not written yet, so the tab says so.

**The header** carries the shop sign on the left — click it to rename the pizzeria — and the implementation picker on the right: switch between the registered bots live, in the lecture, without restarting. Below the picker, in one row, sit the four controls: the **Kitchen view** switch, **New order**, **Tutorial** and **Style**.

## Your pizzeria: the name and the five styles

The bot belongs to the course; the shop belongs to whoever opens it. On the first visit the app does not go to the counter at all — it asks two questions:

1. **What is your pizzeria called?** The answer goes over the door as *“&lt;name&gt;’s Pizza Bot”*, into the browser tab and onto the receipt. The line under the input shows the sign while you type.
2. **Pick a style.** Five cards, each painted in the style it offers — its own palette, its own three fonts, its own icons. One click repaints the whole page, so what you see on the welcome screen is what you get at the counter.

Both are remembered in cookies (`pizzabot_shop`, `pizzabot_style`), read back through `st.context.cookies` when the session connects, so the question is asked once per browser and not once per reload.

Afterwards:

* **click the sign** — the overlay *The name over the door* changes the name,
* **click the Style button**, right of *Tutorial* — the overlay *How the shop looks* changes the style. The button carries the current style's icon, so the header says which one is on.

| key | style | palette | display · body · mono | icons |
|---|---|---|---|---|
| `trattoria` | the house look | dough, tomato, basil | Pacifico · Source Sans 3 · Source Code Pro | 🍕 🧑 🍅 |
| `notte` | the late shift, dark | charcoal, ember orange | Bebas Neue · Inter · JetBrains Mono | 🌜 🧑‍🍳 🔥 |
| `marina` | the seaside terrace | white, azure, lemon | Playfair Display · Karla · IBM Plex Mono | 🍋 ⛵ 🌊 |
| `neon` | the late-night arcade, dark | violet, magenta, cyan | Monoton · Space Grotesk · Space Mono | 🤖 🕹 ⚡ |
| `bianco` | the quiet one, for a bright room | stone, olive, paper | Fraunces · IBM Plex Sans · IBM Plex Mono | 🫒 🧑‍🎨 🌾 |

A style is **data**: a dictionary in `shopfront.py` with a palette, three font stacks, the sign's metrics and a set of icons. `shopfront.css()` writes it as the `:root` block of the page and every rule in `streamlit_chat.py` reads it from there (`--dough` the page, `--paper` a card, `--char` the ink, `--tomato` the accent, `--font-display/-body/-mono`). Adding a sixth style is one dictionary and no CSS. Streamlit paints its own widgets from `.streamlit/config.toml`, which is one palette and not five, so the inputs, buttons, selects and dialogs are repainted from the same variables — that is what the `!important` block in `STYLE` is for, and it is the only reason the dark styles are readable.

The guided tour reads the same variables, so it is dressed in the style that is on.

## The contract between frontend and implementation

An implementation is a Python module that offers

```python
def build_graph():      # required -- returns a compiled LangGraph
    ...

def new_state(user_input=""):   # optional -- the initial state
    ...
```

Everything else is discovered:

| the UI shows | where it comes from |
|---|---|
| nodes, edges, entry point | `compiled.get_graph()` |
| what ran this turn | `compiled.stream(..., stream_mode="updates")` |
| state keys | the graph's state schema (`state_schema` / `schema`) |
| what a node is *for* | the node function's docstring |
| rule / LLM / service | the node's own source, one level deep into the helpers it calls |
| the answer | the new messages in the state, else `answer` / `response` / `output` |
| the picture | generated from the graph (below) |

`new_state` may also live in the package or in a `state` module beside it, as in the exercises. When the implementation has none, the frontend builds the initial state from the schema.

Prose that cannot be derived — a sentence per node, the example inputs — is **data**, in `frontend_meta/<name>.json` (shipped with the frontend) or in a `FRONTEND` dict exported by the implementation. Adding an iteration is therefore a line in `apps.json` plus, optionally, one JSON file. No Python changes.

### Registering an implementation

`apps.json`:

```json
{"key": "l4", "title": "L4 — KGQA", "module": "pizzabot.graph",
 "path": "${L4_PATH}", "env": {"BOT_CONFIG": "static"}, "meta": "l4"}
```

`path` may use `${VAR}` from `.env`; `env` sets variables before the module is imported (this is how the two L3 configurations are one entry each). Implementations that share a top-level package name are unloaded before the next one is imported, so `pizzabot` here and `pizzabot` in the exercises can live in one process.

### The example inputs

Each entry in `frontend_meta/*.json` may declare when it applies:

```json
{"label": "Give the address", "text": "deliver it to 5 Rue Michelet, Saint-Étienne",
 "shows": "address_recognition + validation by the Pizza API",
 "when": {"expected": "address", "ended": false}, "requires": ["address_recognition"]}
```

`when` is evaluated against the live state (dotted paths, `set` / `unset` / a literal), `requires` against the node names of the loaded graph.

## Plugging your own LangGraph implementation into this frontend

The frontend is not a wrapper you copy and change; it is a **host**. Your implementation stays where it is, in your own repository, and the frontend loads it. Six steps, in order.

### Step 1 — make your module satisfy the contract

Somewhere in your package there has to be one importable module that offers `build_graph()` and returns a **compiled** LangGraph:

```python
# yourbot/graph.py
def build_graph():
    workflow = StateGraph(YourState)
    ...
    return workflow.compile()          # compiled, not the builder
```

That is the whole obligation. `new_state(user_input="")` is optional (the frontend builds an initial state from the state schema when you have none), and it may live in the module, in its package, or in a `state` module beside it. Nothing in your code imports anything from the frontend — if it does, the seam is in the wrong place.

### Step 2 — tell `.env` where your repository is

```.env
MYBOT_PATH=/home/me/git/my-pizzabot
```

The path is the directory that `import yourbot.graph` works from — the one you would put on `PYTHONPATH`, not the package folder itself.

### Step 3 — add one line to `apps.json`

```json
{"key": "mine", "title": "My bot — iteration 4", "module": "yourbot.graph",
 "path": "${MYBOT_PATH}", "env": {"BOT_CONFIG": "static"}, "meta": "mine",
 "note": "router / kgqa / order_form"}
```

`key` is what `PIZZABOT_APP` and `run_local.sh --app` take, `title` is what the picker shows, `env` is set **before** your module is imported (that is how one implementation with two configurations becomes two entries). Nothing else in the frontend changes — no Python, no CSS.

### Step 4 — start it and pick it

```sh
./run_local.sh --app mine
```

The script checks the environment, the Pizza API and the LLM endpoint first and then serves the UI on <http://localhost:8501>. In the lecture, the picker in the header switches between the registered implementations live.

### Step 5 — read what the UI now says about your graph

Everything in the kitchen pane is read from *your* compiled graph, so it is a free review of what you built: **Stations** lists your nodes with their docstrings, **Floor plan** is your process model drawn from `get_graph()`, **Ticket** is `stream(..., stream_mode="updates")` — the nodes that really ran, in order, with what each one wrote. If a node shows the wrong chip (`static rule` where you call a model), the guess came from your node's own source; override it in the sidecar of the next step.

### Step 6 — optional: the prose and the example inputs

What cannot be derived is data, in `frontend_meta/mine.json` (the name comes from `meta` in `apps.json`) or in a `FRONTEND` dict exported by your module: a sentence per node, the station name, the services it calls, how it fails — and the example sentences the board offers, each with the state condition under which it applies. Still no Python.

### What happens when you change your implementation

**Nothing, until you say so** — and this is the one thing worth knowing before the practical session. The frontend keeps the compiled graph in `@st.cache_resource`, which lives as long as the **server process**, and Streamlit's file watcher only watches files under the frontend's own folder. Your repository is outside it. So, measured (Streamlit 1.64):

| you do this | your change is picked up |
|---|---|
| save your file, send another sentence | **no** — same compiled graph |
| save your file, reload the browser (F5) | **no** — a reload starts a new *session*, not a new *process*; the cache is process-wide |
| **⋮ → Clear cache** in Streamlit's menu (shortcut `C`) | **yes** — the cached graph is dropped and the next run re-imports your module from disk |
| stop and restart `./run_local.sh` | **yes** |

So: **no restart is needed, but a reload is not enough.** The one-key loop while you work on your bot is *save → press `C` → confirm → send your sentence again*. Clearing the cache also clears the session, so the conversation starts over and the implementation picker returns to the default — the pizzeria name and the style survive, because those are in cookies and not in the session.

Editing the **frontend's** own files is the ordinary Streamlit loop: the watcher notices, the page offers *Rerun* / *Auto rerun*, and the main script is re-read on every run. One caveat that costs minutes if you do not know it: an edited *imported* module (`shopfront.py`, `tutorial.py`, `app_loader.py`) is only re-imported by the session that saw the change, so a browser reload can keep the old one. When a frontend module edit does not seem to arrive, restart the server.

### What happens when your implementation has a bug

The frontend is written so that your bug is **your** bug, shown where you can read it, and never a blank page. Three cases, all observed:

**A node raises during a turn.** `run_turn` catches it. The bot answers *“The process raised an error: …”* in the conversation, and the **Ticket** shows the nodes that ran before the failure with their timings, followed by a red `ERROR` row carrying the message. The app stays alive, the state is not advanced, and you can keep typing. This is deliberate: a demo in front of a room must not die because a node raised.

**Your module cannot be imported, or `build_graph()` itself raises** (a syntax error, a missing import, a `KeyError` while wiring). The load happens before anything can be rendered, so Streamlit shows the exception instead of the page: the type and message first, **with the file and the line in your repository**, then the traceback — the last frames are yours, the first are the frontend's `load_app → app_loader.load → importlib`. The shop sign still renders above it. Fix the file, then `C` to clear the cache: no restart.

**The path in `apps.json` is wrong, or the entry is not loadable.** Then your implementation is not offered at all: the picker lists only what is available, and a grey line under it names the key and the reason (`mine (path not found: /home/me/…)`). `./run_local.sh --apps` prints the same list without starting anything, which is the faster way to find a typo in `.env`.

Two more failure shapes worth naming, because they are contract violations rather than crashes: if `build_graph()` returns the *builder* instead of a compiled graph, `app_loader` raises while reading the process model; and if your graph produces no message and no `answer` / `response` / `output` key, the bot says *“(nothing to say — see the ticket)”* — which is the frontend telling you that your turn wrote state but never spoke.

## The guided tour

Once the shop front has been set up — and on every later visit without a `pizzabot_tutorial` cookie — a tour starts by itself: the page dims, the element a step talks about is cut out of the veil and outlined, and a card explains it. **Skip** (or Esc) ends it and remembers that; **Next / Back** (or the arrow keys) walk through the eleven steps, which begin at the sign (click it to rename) and end at the Style button. The **Tutorial** button, right of *New order*, brings it back at any time, cookie or not.

The steps live in `tutorial.py` as data — a selector, a title, a sentence — and address the elements by the ids described below, so adding a step is one dictionary and no other change. Two details that took a moment to get right, and that anyone extending this should know:

* the tour's code is injected into the **page**, not into the component's iframe. Streamlit re-mounts component iframes on every rerun, and a tour whose buttons live in a destroyed iframe stops responding.
* it waits for its first target to exist instead of guessing a delay (the ids are assigned by a second script, and the app paints in its own time), and it only sets the cookie once a step has really been on screen.

## Addressing elements from CSS or JavaScript

Every element of the app sits in a container with a `key`, which Streamlit renders as the class `st-key-<key>`. A small script (`IDENTITY_SCRIPT` in `streamlit_chat.py`) copies that key into the element's `id` and adds a class per element *type*, derived from its `data-testid`. Both are re-applied after every rerender, so:

* **one element** — `#pz-button-new-order`, `#pz-tab-description`, `#pz-message-3`, `#pz-widget-implementation`
* **all elements of one kind** — `.pz-el-button`, `.pz-el-chat-message`, `.pz-el-tab`, `.pz-el-chat-input`, `.pz-el-vertical-block`

The ids in use:

| id | what it is |
|---|---|
| `pz-header`, `pz-brand`, `pz-controls`, `pz-status` | the shop sign, the controls beside it, the status chips |
| `pz-button-rename`, `pz-widget-rename` | the sign itself — a button, so that a click on it can open the rename overlay |
| `pz-widget-implementation`, `pz-toggle-kitchen-view`, `pz-widget-kitchen-view`, `pz-button-new-order`, `pz-widget-new-order`, `pz-button-tutorial`, `pz-widget-tutorial`, `pz-button-style`, `pz-widget-style` | the picker and the four controls of the header row (`pz-widget-*` is the widget itself, the other is its container) |
| `pz-welcome`, `pz-welcome-name`, `pz-widget-welcome-name`, `pz-welcome-open`, `pz-widget-welcome-open` | the first-visit screen: the name input and the button that opens the shop |
| `pz-style-<where>-<key>`, `pz-widget-<where>-<key>` | one style card and its button, `<where>` being `welcome` or `dialog` |
| `pz-output` | everything the process shows: chat column plus kitchen pane |
| `pz-chat`, `pz-transcript`, `pz-message-<n>`, `pz-receipt` | the conversation column, the message list, one message, the receipt |
| `pz-examples`, `pz-example-<n>`, `pz-widget-example-<app>-<turn>-<n>` | the menu board, one entry, its button |
| `pz-kitchen`, `pz-kitchen-tabs`, `pz-tab-ticket`, `pz-tab-stations`, `pz-tab-order-pad`, `pz-tab-floor-plan`, `pz-tab-description` | the kitchen pane and its tabs |
| `pz-input`, `pz-input-block`, `pz-widget-chat-input` | Streamlit's fixed bottom bar, its inner block, the chat input |
| `pz-main` | the scrolling page area |

`pz-input`, `pz-input-block` and `pz-main` are aliases the script puts on elements Streamlit renders itself — the chat input has to stay a direct child of the page, otherwise it leaves the fixed bottom bar and scrolls away.

Messages are served one at a time: each message that arrives in a turn fades in, the next one **500 ms** later (`serving_styles()` writes one CSS rule per new message; the keyframes are `pz-serve`).

**New order** clears the counter in three steps rather than blanking it: the conversation, the receipt and the menu board fade out (`pz-clear`, 0.4 s), the counter stays empty for **500 ms**, and only then does the bot greet again — with the same serving animation. The click only sets `clearing`; the state is reset at the end of that script run, after the fade has been sent to the browser (`CLEAR_SECONDS`, `CLEAR_PAUSE` in `streamlit_chat.py`).

## The process picture

`diagram.py` generates it on load, from the graph, and caches it under `assets/generated/` keyed by a hash of the structure — change the graph, get a new picture; change nothing, pay nothing. Four ways out, in order:

1. `dot` (graphviz), if the installation can actually write SVG or PNG,
2. the built-in layered SVG renderer — no dependency, works offline, always available,
3. LangGraph's `draw_mermaid_png()` (needs mermaid.ink, i.e. the network),
4. a text diagram.

The mermaid source of the loaded graph sits under the picture, ready to paste into the slides.

## Offline mode (no VPN, no GPU server)

The AI-backed steps — intent check, address extraction, pizza description — need an OpenAI-compatible endpoint, by default the HTWK GPU server, which answers only inside the university network. With

```sh
PIZZABOT_OFFLINE=1
```

they run as deterministic rules instead (`rule_check_order_intention`, `rule_extract_address`, `rule_generate_pizza_description` in `utils.py`). `run_local.sh` sets it automatically when the endpoint does not answer, and the header says **HOUSE RECIPE** while it is on. Nothing else changes: same graph, same slots, same contracts, same Pizza API, same defined failures — the rule version *is* the static implementation of iteration 1. (The Exercise 3 implementation brings its own fallback; there the LLM configuration degrades to its rules by itself.)

## Configuration

Everything comes from `.env` (see `.env-example`) — endpoints, credentials, the default implementation, the paths in `apps.json`. `settings.py` is the only module that reads the environment; the bots read the same variables out of the same file.

```.env
OPENAI_API_KEY=SECRET
MODEL_NAME=CHECK THE AVAILABLE AT http://gpu01.imn.htwk-leipzig.de:8081/v1/models
OPENAI_API_BASE=http://gpu01.imn.htwk-leipzig.de:8081/v1
PIZZA_API_BASE=https://wse-research.org/pizza-api
QANARY_API_BASE=http://demos.swe.htwk-leipzig.de:40111
PIZZABOT_OFFLINE=0
PIZZABOT_APP=demo
L3_PATH=/path/to/saint-etienne-exercise-03/student
```

A shell `PIZZABOT_OFFLINE` wins over the file (that is how `run_local.sh` reports its probe); for everything else the file wins, as before.

The Pizza API is live at <https://wse-research.org/pizza-api> (Swagger UI at `/docs`): 20 pizzas, delivering to Leipzig, Halle, Dresden and every commune of France. Menu and delivery area are read from it, never hard-coded.

## Manual start

```sh
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python pizzabot.py                   # console
streamlit run streamlit_chat.py      # web UI
```

Requires Python 3.9 or higher. The pinned stack follows the current course exercises (LangGraph 1.2.11, langchain-core 1.6.2), so one environment runs every implementation the frontend can load.

## Files

| file | role |
|---|---|
| `pizzabot.py` | the demo process: state, the four nodes, `build_graph()`, `new_state()`, the console loop |
| `utils.py` | the outside world: Pizza API, LLM calls, Qanary/Wikidata — plus the rule implementations of the LLM steps |
| `settings.py` | the only reader of `.env`: endpoints, credentials, modes |
| `app_loader.py` | loads an implementation and reads its process model |
| `diagram.py` | generates the process picture from a compiled graph |
| `streamlit_chat.py` | the web frontend: counter, kitchen view, example board, picker |
| `shopfront.py` | whose pizzeria this is: the name over the door, the five styles, the welcome screen and the two overlays |
| `tutorial.py` | the guided tour: the steps as data, and the code that runs it in the page |
| `apps.json` | which implementations are offered |
| `frontend_meta/*.json` | per-implementation prose and example inputs (data, not code) |
| `run_local.sh` | the start script described above |
| `.streamlit/config.toml` | theme (dough, tomato, charcoal) |
| `test_pizzabot.py`, `data/test_dialogue.py` | LangSmith evaluation over a recorded dialog |

## Example run (console)

```
-- Chatbot:  Hi! I am a pizza bot. I can help you order a pizza. What would you like to order?
-> Your response: I want a pizza
-- Chatbot:  What pizza would you like to order?
Or should I describe the pizza for you? Here are the options: Margherita, Pepperoni, Hawaiian, Quattro Formaggi, ...
-> Your response: Hawaiian
-- Chatbot:  What is your delivery address?
-> Your response: Maksim Gorki Str 58, Leipzig
-- Chatbot:  Thank you for providing all the details. Your order is being processed! Keep your order id ready incase you have further inquiries: 72ee0f12-ce97-4c2d-9386-e6b40bbb55ff .
```

## External tools

* Pizza API: <https://wse-research.org/pizza-api/docs>
* Qanary pipeline (pizza descriptions from Wikidata): `QANARY_API_BASE`
