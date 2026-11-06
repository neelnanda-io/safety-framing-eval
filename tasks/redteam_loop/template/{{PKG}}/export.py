"""Export episode transcripts as JSONL (one episode per line) or as a Markdown page for reading."""
from __future__ import annotations

import json

from {{PKG}}.episode import EpisodeResult, Turn


def turn_to_dict(turn: Turn) -> dict:
    return {"role": turn.role, "content": turn.content, "score": turn.score}


def result_to_dict(result: EpisodeResult) -> dict:
    """Plain-dict form of an episode; `transcript` holds every turn of the episode, in order."""
    return {
        "episode_id": result.episode_id,
        "strategy": result.strategy,
        "{{OUTCOME}}": result.{{OUTCOME}},
        "turns_used": result.turns_used,
        "error": result.error,
        "system_prompt": result.system_prompt,
        # the first entry is the system prompt, which is exported separately above
        "transcript": [turn_to_dict(t) for t in result.transcript[1:]],
    }


def to_jsonl(results: list[EpisodeResult], path: str) -> None:
    """Write one JSON object per episode to `path`. Every line, including the last, ends with a newline,
    so files from several runs can be concatenated with `cat`."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(result_to_dict(r)) for r in results))


def load_jsonl(path: str) -> list[EpisodeResult]:
    """Read episodes written by to_jsonl back into EpisodeResult objects, in file order."""
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f.read().split("\n")]
    return [EpisodeResult(**row) for row in rows]


def to_markdown(result: EpisodeResult) -> str:
    """Render one episode for human review. Lines, in this order:

        # Episode <episode_id>: <strategy>
        {{OUTCOME}}: yes | no, turns used: <turns_used>
        error: <error>                    (only when the episode errored)
        > system: <system_prompt>
        **<role>**: <content>             (one line per turn, in order; a scored turn ends with
                                           " (score 0.90)", the score to two decimals)
    """
    raise NotImplementedError
