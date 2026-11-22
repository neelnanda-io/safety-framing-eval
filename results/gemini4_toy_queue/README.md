# The Gemini 4 toy-task queue (21 Nov 2026)

Copies of the script that ran the 144 toy episodes of `runs/w6_hydrogen` and `runs/w6_neon` on the laptop, strictly one at
a time (part A of `docs/GEMINI4_PREREG.md`), its episode order, and its per-episode record (attempts, times, cost, and the
`/tmp` entries each episode created, moved aside or left). The laptop's absolute path to this repository is replaced by
`<repository>/` and the path of the key file by `<home>/Code/.env`; nothing else was changed. `tmp_preexisting_changed`
lists entries that existed before the episode and changed during it; the driver never touched them.

- `driver.py`: the queue, adapted from `results/gpt62_toy_queue/driver.py` (its docstring lists what differs: Hydrogen's 72
  before Neon's 72; a first gate of one pair per model, run with `--gate` and checked by hand before the other 140; the
  job-wide spend and OpenRouter-balance checks). As copied here it is a record, not meant to be run.
- `order.json`: the 144 episodes in the order run (the four gate episodes first).
- `driver_state.json`: one entry per episode.
