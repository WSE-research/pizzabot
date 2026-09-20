#!/usr/bin/env bash
#
# Start the pizza bot locally -- frontend and LangGraph process together.
#
# The graph is not a separate server: streamlit_chat.py compiles it in-process,
# so "starting both" means one command. What this script adds is everything
# that has to be true before that command can work:
#
#   1. a virtual environment with the pinned requirements
#   2. a .env file
#   3. a reachable Pizza API   (the menu, address validation, orders)
#   4. a reachable LLM endpoint -- and, when there is none, the offline mode
#      that replaces the three LLM steps with the rule implementations
#
#   ./run_local.sh              # checks, then the web UI
#   ./run_local.sh --console    # checks, then the console version
#   ./run_local.sh --check      # only the checks, no app
#   ./run_local.sh --apps       # list the implementations from apps.json
#   ./run_local.sh --app l3-static   # start with that implementation selected
#   ./run_local.sh --offline    # force the rule implementations
#   ./run_local.sh --online     # never fall back, fail if the LLM is down
#   ./run_local.sh --port 8502  # streamlit on another port
#   ./run_local.sh --no-venv    # use the current interpreter as it is
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

VENV="${PIZZABOT_VENV:-$HERE/.venv}"
PORT=8501
MODE="web"          # web | console | check | apps
FORCE=""            # offline | online | ""
USE_VENV=1
INSTALL=1
APP=""                 # empty: whatever PIZZABOT_APP in .env says

while [[ $# -gt 0 ]]; do
    case "$1" in
        --console)   MODE="console" ;;
        --check)     MODE="check" ;;
        --apps)      MODE="apps" ;;
        --app)       APP="${2:?--app needs a key from apps.json}"; shift ;;
        --offline)   FORCE="offline" ;;
        --online)    FORCE="online" ;;
        --port)      PORT="${2:?--port needs a number}"; shift ;;
        --no-venv)   USE_VENV=0 ;;
        --no-install) INSTALL=0 ;;
        -h|--help)   sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1  (try --help)" >&2; exit 2 ;;
    esac
    shift
done

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '   \033[33mwarn\033[0m  %s\n' "$*"; }
bad()  { printf '   \033[31mfail\033[0m  %s\n' "$*"; }

# -------------------------------------------------------------------------
say "1/5  Python environment"

if [[ $USE_VENV -eq 1 ]]; then
    if [[ ! -d "$VENV" ]]; then
        echo "   creating $VENV (this takes a minute the first time)"
        python3 -m venv "$VENV" || {
            bad "python3 -m venv failed -- on Debian/Ubuntu: sudo apt install python3-venv"
            exit 1; }
    fi
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
    ok "venv $VENV"
else
    ok "using $(command -v python3) as it is"
fi

PY="$(command -v python)" || PY="$(command -v python3)"
ok "python $("$PY" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"

if [[ $INSTALL -eq 1 ]]; then
    if ! "$PY" -c 'import streamlit, langgraph, openai, dotenv, fuzzywuzzy' 2>/dev/null; then
        echo "   installing requirements.txt ..."
        "$PY" -m pip install --quiet --upgrade pip
        "$PY" -m pip install --quiet -r requirements.txt
    fi
    ok "requirements installed"
fi

# -------------------------------------------------------------------------
say "2/5  Configuration"

if [[ ! -f .env ]]; then
    cp .env-example .env
    warn ".env was missing -- copied from .env-example, edit it if needed"
fi
set -a; # shellcheck disable=SC1091
source .env; set +a
ok ".env loaded"

if [[ -n "$APP" ]]; then
    export PIZZABOT_APP="$APP"
fi
echo "         PIZZA_API_BASE  = ${PIZZA_API_BASE:-<unset>}"
echo "         OPENAI_API_BASE = ${OPENAI_API_BASE:-<unset>}"
echo "         MODEL_NAME      = ${MODEL_NAME:-<unset>}"
echo "         PIZZABOT_APP    = ${PIZZABOT_APP:-demo}"

# -------------------------------------------------------------------------
say "3/5  Services"

http_code() { curl -s -o /dev/null -m 6 -w '%{http_code}' "$1" 2>/dev/null || true; }

if [[ -z "${PIZZA_API_BASE:-}" ]]; then
    bad "PIZZA_API_BASE is not set in .env -- the bot cannot read the menu"
fi
PIZZA_CODE="$(http_code "${PIZZA_API_BASE:-}/pizza")"
if [[ "$PIZZA_CODE" == "200" ]] && curl -s -m 6 "$PIZZA_API_BASE/pizza" | grep -q '"name"'; then
    COUNT="$("$PY" - <<'PY'
import json, os, urllib.request
with urllib.request.urlopen(os.environ["PIZZA_API_BASE"] + "/pizza", timeout=6) as r:
    print(len(json.load(r)))
PY
)"
    ok "Pizza API answers ($COUNT pizzas on the menu)"
else
    bad "Pizza API at ${PIZZA_API_BASE:-<unset>} does not answer with a menu (HTTP $PIZZA_CODE)"
    warn "ordering and address validation will fail -- fix PIZZA_API_BASE in .env"
fi

LLM_UP=0
if [[ -n "${OPENAI_API_BASE:-}" ]]; then
    LLM_CODE="$(curl -s -o /dev/null -m 6 -w '%{http_code}' \
        -H "Authorization: Bearer ${OPENAI_API_KEY:-none}" \
        "${OPENAI_API_BASE%/}/models" 2>/dev/null || true)"
    if [[ "$LLM_CODE" =~ ^(200|401|403)$ ]]; then
        LLM_UP=1
        ok "LLM endpoint answers (HTTP $LLM_CODE) -- ${MODEL_NAME:-no model set}"
    else
        warn "LLM endpoint ${OPENAI_API_BASE} unreachable (HTTP $LLM_CODE)"
        warn "the HTWK GPU server is only reachable inside the university network / VPN"
    fi
else
    warn "OPENAI_API_BASE is not set"
fi

# -------------------------------------------------------------------------
say "4/5  Implementations"

"$PY" - <<'PYCODE' || warn "could not read apps.json"
import app_loader
for spec in app_loader.registry():
    ok, why = spec.available
    mark = "   ok   " if ok else "   --   "
    print(f"{mark}{spec.key:<12s} {spec.title}" + ("" if ok else f"   ({why})"))
PYCODE

if [[ "$MODE" == "apps" ]]; then
    echo; echo "pick one with --app KEY, or switch in the header of the web UI."
    exit 0
fi

# -------------------------------------------------------------------------
say "5/5  Mode"

case "$FORCE" in
    offline) export PIZZABOT_OFFLINE=1 ;;
    online)
        export PIZZABOT_OFFLINE=0
        if [[ $LLM_UP -eq 0 ]]; then
            bad "--online was asked for, but the LLM endpoint does not answer"
            exit 1
        fi ;;
    *)  if [[ $LLM_UP -eq 1 ]]; then export PIZZABOT_OFFLINE=0
        else export PIZZABOT_OFFLINE=1; fi ;;
esac

if [[ "${PIZZABOT_OFFLINE}" == "1" ]]; then
    warn "OFFLINE MODE: intent check, address extraction and pizza descriptions"
    warn "run as deterministic rules (the static implementation of iteration 1)."
    warn "Everything else -- graph, slots, Pizza API, order -- is unchanged."
else
    ok "LLM mode: the model answers the three AI-backed steps"
fi

if [[ "$MODE" == "check" ]]; then
    echo; echo "checks done (--check), not starting the app."
    exit 0
fi

# -------------------------------------------------------------------------
if [[ "$MODE" == "console" ]]; then
    say "starting the console bot (pizzabot.py)"
    exec "$PY" pizzabot.py
fi

say "starting the web UI on http://localhost:$PORT"
echo "   the LangGraph process runs inside this app -- no second server needed"
echo "   stop with Ctrl-C"
exec "$PY" -m streamlit run streamlit_chat.py \
    --server.port "$PORT" \
    --server.headless true \
    --browser.gatherUsageStats false
