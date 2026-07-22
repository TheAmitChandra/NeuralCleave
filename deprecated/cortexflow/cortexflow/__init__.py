import warnings

warnings.warn(
    "The 'cortexflow' package has been renamed to 'neuralcleave'. "
    "Please update your dependency: pip install neuralcleave. "
    "This stub will be removed in a future release.",
    DeprecationWarning,
    stacklevel=2,
)

from neuralcleave import *  # noqa: F401, F403, E402
from neuralcleave import __version__  # noqa: E402
