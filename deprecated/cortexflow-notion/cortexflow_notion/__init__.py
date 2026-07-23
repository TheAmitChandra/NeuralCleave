import warnings
warnings.warn(
    "cortexflow-notion has been renamed to neuralcleave-notion. "
    "Please update: pip install neuralcleave-notion",
    DeprecationWarning, stacklevel=2,
)
from neuralcleave_notion import *  # noqa: F401, F403, E402
