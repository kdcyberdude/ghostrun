"""Read reward metadata in the configured game runtime."""
import importlib
import sys
from ghostrun_security import validate_slug

if __name__ == '__main__':
    print(importlib.import_module('games.' + validate_slug(sys.argv[1])).PROGRESS_UNIT)
