"""Run a local evaluation checkpoint through the existing pixel-player protocol."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import torch
from app import MAX_PACKET, PolicySession
from export import Actor, NAMES, Policy


class CheckpointActor:
    def __init__(self, snapshot):
        cfg = snapshot['cfg']
        policy = Policy(core=cfg['core'], moods=cfg.get('moods', 0))
        policy.load_state_dict(snapshot['model'])
        self.actor = Actor(policy.eval()).eval()
        self.names = NAMES + (['mood'] if policy.moods else [])

    def run(self, outputs, feed):
        with torch.inference_mode():
            return [value.numpy() for value in self.actor(*(torch.from_numpy(feed[name]) for name in self.names))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--game', required=True)
    args = parser.parse_args()
    torch.set_num_threads(1)
    snapshot = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
    cfg = snapshot['cfg']
    games = cfg['games'].split(',')
    if args.game not in games and not (args.game == 'mario' and 'smb' in games):
        raise ValueError('checkpoint was not trained for this game')
    session = PolicySession(CheckpointActor(snapshot), {'core': cfg['core'], 'moods': cfg.get('moods', 0),
                            'iteration': snapshot.get('it', 0),
                            'checkpoint_sha256': hashlib.sha256(Path(args.checkpoint).read_bytes()).hexdigest()},
                            args.game, 0, 12345, True)
    while raw := sys.stdin.buffer.readline(MAX_PACKET + 1):
        if len(raw) > MAX_PACKET:
            raise ValueError('request exceeds 512 KiB')
        try:
            reply = session.handle(json.loads(raw))
        except (ValueError, UnicodeError):
            reply = {'ok': False, 'error': 'Invalid JSON'}
        print(json.dumps(reply, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
