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

# What the shell set before any .env file was read. `load_dotenv(override=True)`
# lets the file win over the shell -- except for the offline switch, which
# run_local.sh decides from the endpoint check and must therefore stay on top.
_SHELL = dict(os.environ)

try:
    from dotenv import load_dotenv
except ImportError:                                   # pragma: no cover
    def load_dotenv(*_args, **_kwargs):               # type: ignore
        return False


def load(path: Path | str | None = None, override: bool = True) -> bool:
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

    # --- which implementation --------------------------------------------
    @property
    def app_key(self) -> str:
        """The implementation the UI starts with; the picker can change it."""
        return self.get("PIZZABOT_APP", "demo")

    @property
    def app_registry(self) -> Path:
        return Path(self.get("PIZZABOT_APPS", str(HERE / "apps.json")))

    def expand(self, value: str) -> str:
        """Resolve ${VAR} and ~ in a registry entry."""
        return os.path.expanduser(os.path.expandvars(value))


settings = Settings()
