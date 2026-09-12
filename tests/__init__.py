"""Several tests deliberately drive failure paths (a source that times out, a
screen that raises). Their log output is expected, not a signal."""
import logging

logging.disable(logging.CRITICAL)
