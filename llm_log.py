"""Record what the loaded implementation asked an LLM -- whatever it is.

The kitchen view shows the prompts of a turn, the answers and how long the
endpoint took. Nothing here knows an implementation: a `Recorder` is handed to
the graph as a LangChain callback,

    recorder = llm_log.Recorder()
    with recorder.recording():
        graph.stream(state, config={"callbacks": [recorder]}, ...)
    recorder.calls        # one dictionary per LLM call, in order

and so sees every chat model or LLM a LangChain-based node invokes. Most
course implementations -- the demo in this repository among them -- talk to
the endpoint through the `openai` client directly, which no LangChain callback
ever hears of. For those, the client's `create()` is wrapped once, process
wide; the wrapper records into the recorder of the *current context* and is a
plain pass-through everywhere else. A LangChain model that uses the `openai`
client underneath is recorded once, by its callback, not twice.
"""

from __future__ import annotations

import functools
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

# the recorder of the turn that is running in this context -- LangGraph copies
# the context into the threads that run its nodes, so a node sees it too
_ACTIVE: ContextVar[Optional["Recorder"]] = ContextVar("pz_llm_recorder",
                                                       default=None)

LANGCHAIN, OPENAI_SDK = "langchain", "openai client"


def _node() -> str:
    """The graph node that is running now, from LangGraph's own run config."""
    try:
        from langchain_core.runnables.config import var_child_runnable_config
        config = var_child_runnable_config.get() or {}
    except Exception:                                   # pragma: no cover
        return ""
    return str((config.get("metadata") or {}).get("langgraph_node", ""))


def _content(value: Any) -> str:
    """A message's content as text -- strings, content blocks, or anything."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for block in value:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or block))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(value)


def _message(role: Any, content: Any) -> dict:
    return {"role": str(role or "?"), "content": _content(content)}


class Recorder(BaseCallbackHandler):
    """Collects the LLM calls of one turn (or one test run)."""

    # a recorder that fails must never take the turn down with it
    raise_error = False

    def __init__(self):
        super().__init__()
        self.calls: list[dict] = []
        self._open: dict[UUID, dict] = {}

    # --- the context the openai wrapper records into ----------------------
    @contextmanager
    def recording(self):
        install()
        token = _ACTIVE.set(self)
        try:
            yield self
        finally:
            _ACTIVE.reset(token)

    # --- LangChain callbacks ------------------------------------------------
    def _start(self, run_id: UUID, serialized: dict, messages: list[dict],
               metadata: Optional[dict], kwargs: dict) -> None:
        params = kwargs.get("invocation_params") or {}
        model = (params.get("model") or params.get("model_name")
                 or (metadata or {}).get("ls_model_name")
                 or ((serialized or {}).get("kwargs") or {}).get("model")
                 or ((serialized or {}).get("kwargs") or {}).get("model_name")
                 or (serialized or {}).get("name") or "")
        call = {"source": LANGCHAIN, "model": str(model),
                "node": str((metadata or {}).get("langgraph_node") or _node()),
                "messages": messages, "answer": "", "ms": 0,
                "tokens": {}, "error": "", "_started": time.perf_counter()}
        self._open[run_id] = call
        self.calls.append(call)

    def on_chat_model_start(self, serialized, messages, *, run_id,
                            parent_run_id=None, tags=None, metadata=None,
                            **kwargs):
        flat = [_message(getattr(message, "type", "?"),
                         getattr(message, "content", message))
                for batch in messages for message in batch]
        self._start(run_id, serialized, flat, metadata, kwargs)

    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None,
                     tags=None, metadata=None, **kwargs):
        self._start(run_id, serialized,
                    [_message("prompt", prompt) for prompt in prompts],
                    metadata, kwargs)

    def on_llm_end(self, response, *, run_id, parent_run_id=None, **kwargs):
        call = self._open.pop(run_id, None)
        if call is None:
            return
        call["ms"] = int((time.perf_counter() - call.pop("_started")) * 1000)
        texts, tokens = [], {}
        for generations in getattr(response, "generations", None) or []:
            for generation in generations:
                message = getattr(generation, "message", None)
                texts.append(_content(getattr(message, "content", None))
                             or getattr(generation, "text", ""))
                usage = getattr(message, "usage_metadata", None) or {}
                if usage:
                    tokens = {"prompt": usage.get("input_tokens"),
                              "answer": usage.get("output_tokens")}
        usage = ((getattr(response, "llm_output", None) or {})
                 .get("token_usage") or {})
        if usage and not tokens:
            tokens = {"prompt": usage.get("prompt_tokens"),
                      "answer": usage.get("completion_tokens")}
        call["answer"] = "\n".join(text for text in texts if text)
        call["tokens"] = {k: v for k, v in tokens.items() if v is not None}

    def on_llm_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        call = self._open.pop(run_id, None)
        if call is None:
            return
        call["ms"] = int((time.perf_counter() - call.pop("_started")) * 1000)
        call["error"] = f"{type(error).__name__}: {error}"

    # --- the openai wrapper's side ------------------------------------------
    @property
    def inside_langchain(self) -> bool:
        """A LangChain model is running -- its callback records this call."""
        return bool(self._open)

    def summary(self) -> dict:
        return {"calls": len(self.calls),
                "ms": sum(call.get("ms", 0) for call in self.calls)}


# =========================================================================
# the openai client, wrapped once
# =========================================================================

_INSTALLED = False


def _answer_of(response: Any, streamed: bool) -> tuple[str, str, dict]:
    """Model, answer text and token counts out of an openai response."""
    if streamed:
        return "", "(streamed — not read by the recorder)", {}
    model = str(getattr(response, "model", "") or "")
    texts = []
    for choice in getattr(response, "choices", None) or []:
        message = getattr(choice, "message", None)
        text = getattr(message, "content", None) if message is not None \
            else getattr(choice, "text", None)
        calls = getattr(message, "tool_calls", None) if message is not None else None
        if calls:
            text = (text or "") + "\n" + "\n".join(
                f"→ tool {getattr(c.function, 'name', '?')}"
                f"({getattr(c.function, 'arguments', '')})" for c in calls)
        texts.append(_content(text))
    usage = getattr(response, "usage", None)
    tokens = {}
    if usage is not None:
        tokens = {"prompt": getattr(usage, "prompt_tokens", None),
                  "answer": getattr(usage, "completion_tokens", None)}
    return model, "\n".join(texts), {k: v for k, v in tokens.items() if v is not None}


def _begin(kwargs: dict) -> Optional[dict]:
    recorder = _ACTIVE.get()
    if recorder is None or recorder.inside_langchain:
        return None
    if "messages" in kwargs:
        messages = [_message(m.get("role"), m.get("content")) if isinstance(m, dict)
                    else _message(getattr(m, "role", "?"), getattr(m, "content", m))
                    for m in kwargs.get("messages") or []]
    else:
        prompt = kwargs.get("prompt")
        messages = [_message("prompt", p) for p in
                    (prompt if isinstance(prompt, list) else [prompt])]
    call = {"source": OPENAI_SDK, "model": str(kwargs.get("model") or ""),
            "node": _node(), "messages": messages, "answer": "", "ms": 0,
            "tokens": {}, "error": ""}
    recorder.calls.append(call)
    return call


def _finish(call: dict, started: float, response: Any = None,
            error: Optional[BaseException] = None, streamed: bool = False):
    call["ms"] = int((time.perf_counter() - started) * 1000)
    if error is not None:
        call["error"] = f"{type(error).__name__}: {error}"
        return
    model, answer, tokens = _answer_of(response, streamed)
    call["model"] = model or call["model"]
    call["answer"], call["tokens"] = answer, tokens


def _wrap(original):
    @functools.wraps(original)
    def create(self, *args, **kwargs):
        call = _begin(kwargs)
        if call is None:
            return original(self, *args, **kwargs)
        started = time.perf_counter()
        try:
            response = original(self, *args, **kwargs)
        except BaseException as error:
            _finish(call, started, error=error)
            raise
        _finish(call, started, response, streamed=bool(kwargs.get("stream")))
        return response
    create.__pz_recorded__ = True
    return create


def _wrap_async(original):
    @functools.wraps(original)
    async def create(self, *args, **kwargs):
        call = _begin(kwargs)
        if call is None:
            return await original(self, *args, **kwargs)
        started = time.perf_counter()
        try:
            response = await original(self, *args, **kwargs)
        except BaseException as error:
            _finish(call, started, error=error)
            raise
        _finish(call, started, response, streamed=bool(kwargs.get("stream")))
        return response
    create.__pz_recorded__ = True
    return create


def install() -> bool:
    """Wrap `create()` of the openai client's (chat) completions, once.

    Returns False when the `openai` package is not installed -- then only the
    LangChain callbacks record, which is all such an implementation can use.
    """
    global _INSTALLED
    if _INSTALLED:
        return True
    try:
        from openai.resources import completions
        from openai.resources.chat import completions as chat
    except ImportError:                                 # pragma: no cover
        return False
    for owner, wrap in ((chat.Completions, _wrap), (chat.AsyncCompletions, _wrap_async),
                        (completions.Completions, _wrap),
                        (completions.AsyncCompletions, _wrap_async)):
        if not getattr(owner.create, "__pz_recorded__", False):
            owner.create = wrap(owner.create)
    _INSTALLED = True
    return True
