"""Load a LangGraph implementation, and learn everything else from the graph.

This is the seam that keeps the frontend independent of the bot. An
implementation is a Python module that offers

    build_graph()            -> a compiled LangGraph  (required)
    new_state(user_input)    -> the initial state     (optional)
    what_happened(target)    -> the account of one input (optional)

and nothing else. Which modules exist is data, not code: `apps.json` lists
them, `.env` supplies the paths. Everything the UI shows -- the nodes, the
edges, the state keys, the picture, which node ran -- is read from the compiled
graph at runtime, so a new iteration of the bot needs no change here.

Optional prose (what a node is *for*, example sentences) may come from

    frontend_meta/<name>.json    a data file shipped with the frontend, or
    module.FRONTEND              the same dictionary, exported by the module

and when neither exists, the node docstrings are used.
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from settings import HERE, settings

META_DIR = HERE / "frontend_meta"

# What a node does with the outside world, guessed from its own source. A
# sidecar file may override it; nothing here is implementation-specific.
LLM_MARKERS = ("llm_service", "client.chat", "chat.completions", "ChatOpenAI",
               "openai", "invoke_model", "_llm", "llm(")
SERVICE_MARKERS = ("requests.", "httpx.", "pizza_api", "urllib.request",
                   "SPARQLWrapper", "post_order", "get_menu")

RULE, LLM, MIXED = "rule", "llm", "mixed"
KIND_LABEL = {RULE: "static rule", LLM: "LLM-backed", MIXED: "rule + service"}


# =========================================================================
# the registry
# =========================================================================


@dataclass
class AppSpec:
    key: str
    title: str
    module: str
    path: str
    env: dict[str, str] = field(default_factory=dict)
    meta: str = ""
    note: str = ""

    @property
    def root(self) -> Path:
        return Path(settings.expand(self.path or ".")).resolve()

    @property
    def available(self) -> tuple[bool, str]:
        if not self.path:
            return False, "no path configured"
        root = self.root
        if not root.is_dir():
            return False, f"path not found: {root}"
        return True, ""


def registry() -> list[AppSpec]:
    """The implementations offered in the picker, from apps.json."""
    source = settings.app_registry
    if not source.is_file():
        return [AppSpec(key="demo", title="this repository", module="pizzabot", path=".")]
    data = json.loads(source.read_text())
    return [AppSpec(**entry) for entry in data.get("apps", [])]


def spec_for(key: str) -> AppSpec:
    specs = registry()
    for spec in specs:
        if spec.key == key:
            return spec
    return specs[0]


# =========================================================================
# loading
# =========================================================================


def _purge(module_name: str) -> None:
    """Drop a previously loaded implementation from sys.modules.

    Two implementations may use the same top-level package name (`pizzabot`
    is both a file here and a package in the exercises), so switching means
    forgetting the old one first.
    """
    top = module_name.split(".")[0]
    for name in [n for n in sys.modules
                 if n == top or n.startswith(top + ".")]:
        del sys.modules[name]


def _import(spec: AppSpec):
    root = str(spec.root)
    while root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)
    _purge(spec.module)
    for name, value in spec.env.items():
        import os
        os.environ[name] = settings.expand(value)
    return importlib.import_module(spec.module)


def _state_schema(graph):
    """The TypedDict behind the state -- `schema` in LangGraph 0.2, `state_schema` in 1.x."""
    builder = getattr(graph, "builder", None)
    for name in ("state_schema", "schema", "input_schema"):
        schema = getattr(builder, name, None)
        if schema is not None and getattr(schema, "__annotations__", None):
            return schema
    return None


def _callable(module, *names) -> Optional[Callable]:
    for name in names:
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    return None


def _zero(annotation: Any) -> Any:
    """A harmless starting value for a state key, from its type annotation."""
    text = str(annotation)
    if "str" in text and "Optional" not in text:
        return ""
    if "bool" in text:
        return False
    if "list" in text or "List" in text:
        return []
    if "dict" in text or "Dict" in text or "TypedDict" in text or "Slots" in text:
        return {}
    return None


def _node_functions(graph) -> dict[str, Callable]:
    """The callable behind every node, for docstrings and source inspection."""
    functions: dict[str, Callable] = {}
    for name, node in getattr(graph.builder, "nodes", {}).items():
        runnable = getattr(node, "runnable", None)
        function = getattr(runnable, "func", None) or runnable
        functions[name] = function
    return functions


def _source_of(function: Callable) -> str:
    try:
        return inspect.getsource(function)
    except (OSError, TypeError):
        return ""


def _guess_kind(function: Callable) -> str:
    """Rule, LLM call or service call -- read off the node's own code.

    One level deep: a node usually delegates ("check_order_intention(...)"),
    so the helpers it calls are inspected too. A sidecar file may override
    the guess, but nothing here knows a particular implementation.
    """
    haystack = f"{getattr(function, '__module__', '')}\n{_source_of(function)}"
    globals_ = getattr(function, "__globals__", {})
    for name in getattr(getattr(function, "__code__", None), "co_names", ()):
        helper = globals_.get(name)
        if callable(helper) and getattr(helper, "__module__", "").split(".")[0] \
                == getattr(function, "__module__", "").split(".")[0]:
            haystack += "\n" + _source_of(helper)
        elif inspect.ismodule(helper):
            haystack += "\n" + (helper.__name__ or "")
    if any(marker in haystack for marker in LLM_MARKERS):
        return LLM
    if any(marker in haystack for marker in SERVICE_MARKERS):
        return MIXED
    return RULE


def _sentences(value: Any) -> list[str]:
    """Whatever an implementation returns, as a list of sentences.

    A string (one sentence per line), a list of strings, or a list of the
    dictionaries `explain()` produces -- the frontend takes all three.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    lines = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("sentence") or item.get("text") or item
        lines.append(str(item).strip())
    return [line for line in lines if line]


def _first_line(text: Optional[str]) -> str:
    if not text:
        return ""
    for line in text.strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def _meta_for(spec: AppSpec, module) -> dict:
    """Prose about nodes and examples: sidecar file, module, or nothing."""
    name = spec.meta or spec.key
    path = META_DIR / f"{name}.json"
    if path.is_file():
        return json.loads(path.read_text())
    exported = getattr(module, "FRONTEND", None)
    return dict(exported) if isinstance(exported, dict) else {}


@dataclass
class LoadedApp:
    spec: AppSpec
    graph: Any
    module: Any
    meta: dict
    nodes: dict[str, dict]
    edges: list[tuple[str, str, bool]]
    state_keys: dict[str, str]
    entry: str
    _new_state: Optional[Callable] = None
    _explain: Optional[Callable] = None
    explain_name: str = ""

    # --- the contract the UI needs ---------------------------------------
    @property
    def key(self) -> str:
        return self.spec.key

    @property
    def title(self) -> str:
        return self.meta.get("title") or self.spec.title

    def new_state(self, user_input: str = "") -> dict:
        if self._new_state is not None:
            try:
                return self._new_state(user_input)
            except TypeError:
                state = self._new_state()
                state[self.input_key] = user_input
                return state
        annotations = getattr(_state_schema(self.graph), "__annotations__", {})
        state = {key: _zero(kind) for key, kind in annotations.items()}
        defaults = self.meta.get("initial_state", {})
        state.update(defaults)
        state[self.input_key] = user_input
        return state

    @property
    def input_key(self) -> str:
        return self.meta.get("input_key", "input")

    @property
    def message_key(self) -> str:
        return self.meta.get("message_key", "messages")

    def messages(self, state: dict) -> list:
        value = state.get(self.message_key) or []
        return value if isinstance(value, list) else []

    def is_ended(self, state: dict) -> bool:
        return bool(state.get("ended"))

    def answer_of(self, state: dict) -> Optional[str]:
        """Used when a graph has no message list."""
        for key in ("answer", "response", "output"):
            if state.get(key):
                return str(state[key])
        return None

    @property
    def examples(self) -> list[dict]:
        return list(self.meta.get("examples", []))

    # --- the optional explanation contract --------------------------------
    @property
    def target_key(self) -> str:
        """The state key holding the IRI of the current user input."""
        return self.meta.get("target_key", "input_iri")

    @property
    def explains(self) -> bool:
        """Does this implementation offer an account of its own runs?"""
        return self._explain is not None

    def explanation(self, state: dict) -> list[str]:
        """What the implementation says happened to the last input.

        Optional, like `new_state()`. A module may offer

            what_happened(target) -> str | list[str]
            explain(target)       -> str | list[str] | list[dict]

        where `target` is the IRI of the user's input -- the state key named
        by `target_key` (`input_iri` unless the sidecar file says otherwise).
        A bot that has no such key is handed the state instead, so keeping the
        annotations in the state works too. Nothing here knows a node name: an
        implementation explains itself, or the frontend reads the run.
        """
        if self._explain is None:
            return []
        target = state.get(self.target_key)
        return _sentences(self._explain(target if target else state))


def load(key: str) -> LoadedApp:
    """Import the implementation and read its process model."""
    spec = spec_for(key)
    ok, reason = spec.available
    if not ok:
        raise FileNotFoundError(f"{spec.key}: {reason}")

    module = _import(spec)
    build = _callable(module, "build_graph", "make_graph", "create_graph")
    graph = build() if build is not None else None
    if graph is None:
        graph = getattr(module, "graph", None) or getattr(module, "app", None)
    if graph is None:
        raise AttributeError(
            f"{spec.module} offers neither build_graph() nor a compiled `graph`")

    meta = _meta_for(spec, module)
    drawn = graph.get_graph()
    functions = _node_functions(graph)
    node_meta = meta.get("nodes", {})

    nodes: dict[str, dict] = {}
    for order, name in enumerate(drawn.nodes):
        if name in ("__start__", "__end__"):
            continue
        function = functions.get(name)
        extra = node_meta.get(name, {})
        nodes[name] = {
            "name": name,
            "order": extra.get("order", order),
            "kind": extra.get("kind") or (_guess_kind(function) if function else RULE),
            "purpose": extra.get("purpose") or _first_line(getattr(function, "__doc__", "")),
            "station": extra.get("station", ""),
            "code": extra.get("code") or _code_location(function),
            "services": extra.get("services", []),
            "failure": extra.get("failure", ""),
            "routes_to": sorted({target for source, target, _ in _edges(drawn)
                                 if source == name}),
        }

    annotations = getattr(_state_schema(graph), "__annotations__", {})
    described = meta.get("state_keys", {})
    state_keys = {key: described.get(key, _type_name(value))
                  for key, value in annotations.items()}

    entry = next((target for source, target, _ in _edges(drawn)
                  if source == "__start__"), "")

    explain = _callable(module, "what_happened", "explain", "explanation")

    return LoadedApp(
        spec=spec, graph=graph, module=module, meta=meta, nodes=nodes,
        edges=_edges(drawn), state_keys=state_keys, entry=entry,
        _new_state=_find_state_factory(module, spec),
        _explain=explain, explain_name=getattr(explain, "__name__", ""),
    )


def _find_state_factory(module, spec: AppSpec) -> Optional[Callable]:
    """`new_state` in the module, in its package, or in a `state` module beside it."""
    found = _callable(module, "new_state", "initial_state")
    if found is not None:
        return found
    package = spec.module.split(".")[0]
    for name in (package, f"{package}.state", f"{spec.module}_state"):
        try:
            neighbour = importlib.import_module(name)
        except ImportError:
            continue
        found = _callable(neighbour, "new_state", "initial_state")
        if found is not None:
            return found
    return None


def _edges(drawn) -> list[tuple[str, str, bool]]:
    return [(edge.source, edge.target, bool(getattr(edge, "conditional", False)))
            for edge in drawn.edges]


def _type_name(annotation: Any) -> str:
    name = getattr(annotation, "__name__", None)
    return name or str(annotation).replace("typing.", "")


def _code_location(function: Optional[Callable]) -> str:
    if function is None:
        return ""
    module = getattr(function, "__module__", "")
    name = getattr(function, "__qualname__", getattr(function, "__name__", ""))
    return f"{module}.{name}" if module else name


# =========================================================================
# examples: data, evaluated against the live state
# =========================================================================


def _resolve(state: dict, path: str) -> Any:
    value: Any = state
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = getattr(value, part, None)
        if value is None:
            return None
    return value


def _matches(state: dict, condition: dict) -> bool:
    for path, expected in condition.items():
        value = _resolve(state, path)
        if expected == "set":
            if not value:
                return False
        elif expected == "unset":
            if value:
                return False
        elif isinstance(expected, bool):
            if bool(value) != expected:
                return False
        elif value != expected:
            return False
    return True


def examples_for(app: LoadedApp, state: dict) -> list[dict]:
    """The examples whose conditions hold now and whose nodes exist here."""
    available = set(app.nodes)
    chosen = []
    for example in app.examples:
        required = set(example.get("requires", []))
        if required and not required <= available:
            continue
        if not _matches(state, example.get("when", {})):
            continue
        chosen.append(example)
    return chosen
