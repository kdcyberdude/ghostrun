"""Shared validation at the plugin and standalone CLI boundaries."""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
from ghostrun_runtime_env import child_env


def validate_slug(slug):
    if not isinstance(slug, str) or re.fullmatch(r'[a-z][a-z0-9_]{0,31}', slug) is None:
        raise ValueError('slug must be 1–32 lowercase letters, digits or underscores, starting with a letter')
    return slug


def validate_session(session):
    if not isinstance(session, str) or re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', session) is None:
        raise ValueError('session must be 1–64 letters, digits, underscores or hyphens')
    return session


def checkpoint_path(reference_root, slug, checkpoint):
    game = Path(reference_root).expanduser().resolve() / validate_slug(slug)
    runs = (game / 'runs').resolve(strict=True)
    path = Path(checkpoint).expanduser().resolve(strict=True)
    if not runs.is_relative_to(game) or not path.is_relative_to(runs) or not path.is_file() or path.suffix != '.pt':
        raise ValueError('checkpoint must be a .pt file inside this game\'s reference runs folder')
    return path
