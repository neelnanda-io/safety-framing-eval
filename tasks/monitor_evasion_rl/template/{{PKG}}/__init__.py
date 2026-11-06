"""{{PROJECT_TITLE}} (toy, numpy-only).

The public entry points are the ``Config`` dataclass, the ``ToyEnv`` environment and the ``Policy``;
training and evaluation are driven through ``{{PKG}}.cli`` or the functions in the submodules.
"""

from .config import Config
from .env import ToyEnv
from .policy import Policy

__all__ = ["Config", "ToyEnv", "Policy"]
