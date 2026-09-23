"""Run the example dialogue against the loaded implementation, and keep the run.

`test_pizzabot.py` evaluates the demo through LangSmith, with an LLM as judge.
This is the local counterpart the frontend offers: no account, no judge, and
any implementation from `apps.json`.

    run = test_runs.execute(app)      # one run of data/test_dialogue.py
    test_runs.save(run)               # runs/<started>-<key>.json
    test_runs.history()               # every stored run, newest first

The dialogue is the one `test_pizzabot.py` uses (`correct_dialogue`), but it is
played as a *conversation*: the `input` of each turn is sent, one after the
other, into a state that starts from the implementation's own `new_state()`.
The recorded input states of the file carry the demo's state keys, which
another implementation does not have -- the utterances and the expected
answers are what every implementation shares.

A turn passes when the expected answer is contained in what the bot said,
compared case- and whitespace-insensitively, with `<SOME UUID>`-style
placeholders matching anything. That is the judge's question in
`test_pizzabot.py` ("does the actual answer contain all of the information in
the expected answer?") asked without a model. The similarity next to it is
difflib's ratio and says how far off a failed turn is.

Mind the side effect: the last turn of the dialogue places an order with the
Pizza API, exactly as `test_pizzabot.py` does.
"""

from __future__ import annotations

import difflib
import importlib.util
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import llm_log
from settings import HERE, settings

DIALOGUE = HERE / "data" / "test_dialogue.py"
PLACEHOLDER = re.compile(r"<[a-z][a-z _-]*>", re.I)  # <SOME UUID>, <ORDER ID>


# =========================================================================
# the dialogue
# =========================================================================


def dialogue() -> list[dict]:
    """The turns of data/test_dialogue.py: what is said, what should come back.

    Loaded from its file, not imported as `data.test_dialogue`: an
    implementation on sys.path may bring a `data` package of its own.
    """
    loader = importlib.util.spec_from_file_location("pz_test_dialogue", DIALOGUE)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return [{"input": example["inputs"]["input"],
             "expected": example["outputs"]["expected"]}
            for example in module.correct_dialogue]


def _normal(text: str) -> str:
    return " ".join(str(text).split()).lower()


def _pattern(expected: str) -> re.Pattern:
    """The expected answer as a regular expression -- placeholders match anything."""
    pieces = PLACEHOLDER.split(_normal(expected))
    return re.compile(r".+?".join(re.escape(piece) for piece in pieces))


def verdict(expected: str, actual: str) -> tuple[bool, float]:
    """(passed, similarity) of one turn."""
    passed = bool(_pattern(expected).search(_normal(actual)))
    similarity = difflib.SequenceMatcher(None, _normal(expected),
                                         _normal(actual)).ratio()
    return passed, round(similarity, 3)


# =========================================================================
# one run
# =========================================================================


def _revision(root: Path) -> str:
    """The commit the implementation is at, when its folder is a git checkout."""
    try:
        done = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    if done.returncode != 0:
        return ""
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                           capture_output=True, text=True, timeout=5).stdout.strip()
    return done.stdout.strip() + ("+" if dirty else "")


def _said(app, before: int, state: dict) -> str:
    """What the bot said in this turn -- the new AI messages, or the answer key."""
    spoken = [message for message in app.messages(state)[before:]
              if getattr(message, "type", "ai") == "ai"]
    if spoken:
        return "\n".join(str(getattr(message, "content", message))
                         for message in spoken)
    return app.answer_of(state) or ""


def execute(app, on_turn=None) -> dict:
    """Play the dialogue against `app` (an app_loader.LoadedApp) and grade it.

    `on_turn(position, total)` is called before each turn, for a progress bar.
    A turn that raises is recorded as failed, and the run goes on with the
    state as it was -- one bug should not hide the verdict on the rest.
    """
    turns = dialogue()
    started_at = datetime.now().astimezone()
    started = time.perf_counter()
    state = app.new_state("")
    results = []
    for position, turn in enumerate(turns, start=1):
        if on_turn is not None:
            on_turn(position, len(turns))
        state = dict(state)
        state[app.input_key] = turn["input"]
        before = len(app.messages(state))
        recorder = llm_log.Recorder()
        nodes, error, answer = [], "", ""
        turn_started = time.perf_counter()
        try:
            with recorder.recording():
                for chunk in app.graph.stream(state, config={"callbacks": [recorder]},
                                              stream_mode="updates"):
                    for node_name, update in chunk.items():
                        nodes.append(node_name)
                        state.update(update or {})
            answer = _said(app, before, state)
        except Exception as failure:                  # grade it, keep going
            error = f"{type(failure).__name__}: {failure}"
        passed, similarity = verdict(turn["expected"], answer)
        results.append({
            "turn": position, "input": turn["input"],
            "expected": turn["expected"], "actual": answer,
            "passed": passed and not error, "similarity": similarity,
            "ms": int((time.perf_counter() - turn_started) * 1000),
            "nodes": nodes, "error": error,
            "llm_calls": len(recorder.calls),
            "llm_ms": recorder.summary()["ms"],
        })

    passed = sum(1 for result in results if result["passed"])
    return {
        "started": started_at.isoformat(timespec="seconds"),
        "implementation": app.key,
        "title": app.title,
        "module": app.spec.module,
        "revision": _revision(app.spec.root),
        "mode": "offline" if settings.offline else "llm",
        "model": "" if settings.offline else settings.model_name,
        "dialogue": str(DIALOGUE.relative_to(HERE)),
        "passed": passed,
        "total": len(results),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "llm_calls": sum(result["llm_calls"] for result in results),
        "turns": results,
    }


# =========================================================================
# the stored runs
# =========================================================================


def save(run: dict, folder: Optional[Path] = None) -> Path:
    """One JSON file per run -- named so that a listing is already in order."""
    folder = Path(folder or settings.runs_dir)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = run["started"][:19].replace(":", "").replace("-", "")
    path = folder / f"{stamp}-{run['implementation']}.json"
    counter = 1
    while path.exists():                    # two runs within one second
        counter += 1
        path = folder / f"{stamp}-{run['implementation']}-{counter}.json"
    path.write_text(json.dumps(run, indent=2, ensure_ascii=False))
    return path


def history(folder: Optional[Path] = None) -> list[dict]:
    """Every run stored so far, newest first. A broken file is skipped."""
    folder = Path(folder or settings.runs_dir)
    if not folder.is_dir():
        return []
    runs: list[dict[str, Any]] = []
    for path in folder.glob("*.json"):
        try:
            run = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if _well_formed(run):
            run["file"] = path.name
            runs.append(run)
    return sorted(runs, key=lambda run: run.get("started", ""), reverse=True)


def _well_formed(run: Any) -> bool:
    """A run the comparison can show -- a file edited by hand, or written by
    another version of this module, is skipped rather than breaking the tab."""
    return (isinstance(run, dict)
            and isinstance(run.get("started", ""), str)
            and isinstance(run.get("passed"), int)
            and isinstance(run.get("total"), int)
            and all(isinstance(run.get(key, 0), (int, float))
                    for key in ("duration_ms", "llm_calls"))
            and isinstance(run.get("turns"), list)
            and all(isinstance(turn, dict) for turn in run["turns"]))
