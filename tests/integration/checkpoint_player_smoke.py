"""CPU-only smoke: real checkpoint protocol and rejection of executable pickle data."""
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'engine/rl'))
from model import Policy

torch.set_num_threads(1)
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    checkpoint = path/'model.pt'
    torch.save({'model': Policy(core=32, moods=0).state_dict(), 'cfg': {'core':32, 'moods':0, 'games':'g'}}, checkpoint)
    image = io.BytesIO(); Image.new('RGB', (256,240)).save(image,format='PNG')
    requests = [{'op':'hello'}, {'op':'reset','image_png_base64':base64.b64encode(image.getvalue()).decode()}]
    argv = [sys.executable,str(ROOT/'engine/rl/player/checkpoint.py'),'--checkpoint',str(checkpoint),'--game','g']
    result = subprocess.run(argv,input=''.join(json.dumps(r)+'\n' for r in requests),text=True,capture_output=True,timeout=60)
    assert result.returncode==0,result.stderr
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(replies)==2 and all(r['ok'] for r in replies),replies
    assert replies[1]['frames']==1 and isinstance(replies[1]['mask'],int)
    marker = path/'executed'
    class Payload:
        def __reduce__(self):
            return os.system, (f'touch {marker}',)
    torch.save(Payload(), checkpoint)
    result = subprocess.run(argv,input='',text=True,capture_output=True,timeout=60)
    assert result.returncode != 0 and not marker.exists()
print('Checkpoint protocol, one CPU inference, and unsafe-pickle rejection passed.')
