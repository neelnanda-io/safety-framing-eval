"""{{PROJECT_TITLE}}.

Stages (see docs/DESIGN.md): ingest -> normalize -> dedupe -> judge -> parse -> split -> stats -> export.
"""

__version__ = "0.4.1"

POSITIVE = "{{POS}}"
NEGATIVE = "{{NEG}}"
LABELS = (POSITIVE, NEGATIVE)

# Name of the grouping field in source files and in the exported corpus.
GROUP_KEY = "{{GROUP}}"
