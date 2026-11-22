# The GPT-6.2 toy-task queue (17-18 Nov 2026)

Copies of the script that ran the 144 toy episodes of `runs/w5_astra62` and `runs/w5_sol62` on the laptop, strictly one
at a time, its episode order, and its per-episode record (attempts, times, cost, and the `/tmp` entries each episode
created, moved aside or left). The laptop's absolute path to this repository is replaced by `<repository>/`; nothing
else was changed. `tmp_preexisting_changed` lists entries that existed before the episode and changed during it (for
example the session's own scratch folder); the driver never touched them.

- `driver.py`: the queue (the script reads and writes next to itself; as copied here it is a record, not meant to be run).
- `order.json`: the 144 episodes in the order run.
- `driver_state.json`: one entry per episode.
