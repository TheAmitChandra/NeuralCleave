import warnings
warnings.warn(
    "cortexflow-google-calendar has been renamed to neuralcleave-google-calendar. "
    "Please update: pip install neuralcleave-google-calendar",
    DeprecationWarning, stacklevel=2,
)
from neuralcleave_google_calendar import *  # noqa: F401, F403, E402
