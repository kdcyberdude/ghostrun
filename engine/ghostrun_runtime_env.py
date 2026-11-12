"""Environment passed to game runtimes; provider credentials never belong here."""
import os

_NAMES = {'PATH', 'HOME', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TMPDIR', 'TMP', 'TEMP',
          'LD_LIBRARY_PATH', 'LIBRARY_PATH', 'CUDA_HOME', 'CUDA_PATH', 'CUDA_VISIBLE_DEVICES',
          'CUDA_DEVICE_ORDER', 'NVIDIA_VISIBLE_DEVICES', 'NVIDIA_DRIVER_CAPABILITIES',
          'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'WORLD_SIZE', 'LOCAL_RANK', 'RANK',
          'MASTER_ADDR', 'MASTER_PORT', 'NES_ROM_DIR'}
_PREFIXES = ('NESLE_', 'RL_', 'REWARD10_', 'PYTORCH_')


def child_env():
    return {k: v for k, v in os.environ.items() if k in _NAMES or k.startswith(_PREFIXES)}
