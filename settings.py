"""The one place that reads the environment.

Endpoints, credentials and the choice of implementation all come from `.env`
(see `.env-example`); nothing in the frontend hard-codes a URL, a key or a
model name. The implementations keep their own configuration modules -- they
read the same variables out of the same file, so one `.env` serves all of them.

    from settings import settings
    settings.pizza_api_base      # https://wse-research.org/pizza-api
    settings.model_name          # whatever .env says
    settings.offline             # rule implementations instead of LLM calls

The values are read on every access, because switching the implementation in
the UI may change a variable (`BOT_CONFIG`, for instance) while the app runs.
"""

from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent

# What the shell set before any .env file was read. Deployment environments
# must win over the local file, especially for the shared-mode safety gates.
_SHELL = dict(os.environ)

try:
    from dotenv import load_dotenv
except ImportError:                                   # pragma: no cover
    def load_dotenv(*_args, **_kwargs):               # type: ignore
        return False


def load(path: Path | str | None = None, override: bool = False) -> bool:
    """Read a .env file into the environment. Missing file -> nothing happens."""
    target = Path(path) if path else HERE / ".env"
    if not target.is_file():
        return False
    return bool(load_dotenv(target, override=override))


load()                                                # the frontend's own .env


# The Pizza API is public and the whole course points at this one instance, so
# a checkout with no .env still answers "what pizzas do you have?". Credentials
# have no such default: a missing key has to be a missing key.
PIZZA_API_DEFAULT = "https://wse-research.org/pizza-api"


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def _integer(value: str, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


class Settings:
    """Read-through accessors -- never a snapshot."""

    @staticmethod
    def get(name: str, default: str = "") -> str:
        return os.environ.get(name, default)

    # --- services ---------------------------------------------------------
    @property
    def pizza_api_base(self) -> str:
        return (self.get("PIZZA_API_BASE") or PIZZA_API_DEFAULT).rstrip("/")

    @property
    def openai_api_base(self) -> str:
        return self.get("OPENAI_API_BASE").rstrip("/")

    @property
    def openai_api_key(self) -> str:
        return self.get("OPENAI_API_KEY") or self.get("ILAAS_API_KEY")

    @property
    def model_name(self) -> str:
        return self.get("MODEL_NAME") or self.get("ILAAS_CHAT_MODEL")

    @property
    def qanary_api_base(self) -> str:
        return self.get("QANARY_API_BASE").rstrip("/")

    @property
    def qanary_sparql_hosts(self) -> tuple[str, ...]:
        """Extra hosts a Qanary response may name as its SPARQL endpoint."""
        return tuple(
            host.strip().lower()
            for host in self.get("QANARY_SPARQL_HOSTS").split(",")
            if host.strip()
        )

    @property
    def allow_insecure_http(self) -> bool:
        """Allow plain HTTP for non-loopback services (unsafe, opt-in only)."""
        return _truthy(self.get("PIZZABOT_ALLOW_INSECURE_HTTP", "0"))

    # --- modes ------------------------------------------------------------
    @property
    def offline(self) -> bool:
        """Shell wins over .env here -- run_local.sh decides it from a probe."""
        value = _SHELL.get("PIZZABOT_OFFLINE")
        if value is None:
            value = self.get("PIZZABOT_OFFLINE", "")
        return _truthy(value)

    @property
    def llm_configured(self) -> bool:
        key = self.openai_api_key.strip()
        return bool(key) and not key.startswith("<") and bool(self.openai_api_base)

    @property
    def deployment(self) -> str:
        value = self.get("PIZZABOT_DEPLOYMENT", "local").strip().lower()
        return value if value in ("local", "shared") else "local"

    @property
    def shared_deployment(self) -> bool:
        return self.deployment == "shared"

    @property
    def access_token(self) -> str:
        return self.get("PIZZABOT_ACCESS_TOKEN")

    def _feature(self, name: str) -> bool:
        default = "0" if self.shared_deployment else "1"
        value = self.get(name).strip()
        return _truthy(value or default)

    @property
    def orders_enabled(self) -> bool:
        return self._feature("PIZZABOT_ENABLE_ORDERS")

    @property
    def test_runs_enabled(self) -> bool:
        return self._feature("PIZZABOT_ENABLE_TEST_RUNS")

    @property
    def llm_logging_enabled(self) -> bool:
        return self._feature("PIZZABOT_ENABLE_LLM_LOG")

    @property
    def app_switching_enabled(self) -> bool:
        return self._feature("PIZZABOT_ENABLE_APP_SWITCHING")

    @property
    def external_apps_enabled(self) -> bool:
        return self._feature("PIZZABOT_ENABLE_EXTERNAL_APPS")

    @property
    def max_input_chars(self) -> int:
        default = 2_000 if self.shared_deployment else 20_000
        return _integer(self.get("PIZZABOT_MAX_INPUT_CHARS"), default, 100, 100_000)

    @property
    def max_turns(self) -> int:
        default = 100 if self.shared_deployment else 1_000
        return _integer(self.get("PIZZABOT_MAX_TURNS"), default, 1, 10_000)

    @property
    def max_llm_calls(self) -> int:
        default = 100 if self.shared_deployment else 10_000
        return _integer(self.get("PIZZABOT_MAX_LLM_CALLS"), default, 1, 100_000)

    @property
    def min_turn_interval_ms(self) -> int:
        default = 500 if self.shared_deployment else 0
        return _integer(
            self.get("PIZZABOT_MIN_TURN_INTERVAL_MS"),
            default,
            0,
            60_000,
        )

    # --- which implementation --------------------------------------------
    @property
    def app_key(self) -> str:
        """The implementation the UI starts with; the picker can change it."""
        return self.get("PIZZABOT_APP", "demo")

    @property
    def app_registry(self) -> Path:
        return Path(self.get("PIZZABOT_APPS", str(HERE / "apps.json")))

    # --- where the test runs are kept -------------------------------------
    @property
    def runs_dir(self) -> Path:
        """One JSON file per run of the example dialogue -- see test_runs.py."""
        folder = Path(self.expand(self.get("PIZZABOT_RUNS", "runs")))
        return folder if folder.is_absolute() else HERE / folder

    def expand(self, value: str) -> str:
        """Resolve ${VAR} and ~ in a registry entry."""
        return os.path.expanduser(os.path.expandvars(value))


settings = Settings()
