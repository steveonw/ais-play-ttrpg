#!/usr/bin/env python3
"""Synthetic routing/packet benchmark; never contacts a model or writes the source."""
import argparse
import copy
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from rounds import RoundSession, compact
from test_rounds import CONFIG, FixtureProvider
from ttrpg import Campaign


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, help='Optional completed campaign for a disposable packet-size probe')
    args = parser.parse_args()
    report = {'kind': 'synthetic_preplay_benchmark', 'model_calls': 0, 'campaign_advanced': False}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / 'fixture'
        Campaign.create(root, copy.deepcopy(CONFIG))
        session = RoundSession.attach(root)
        start = time.perf_counter()
        while session.run_batch(FixtureProvider()): pass
        report.update(rounds=session.e['round'], character_turns=session.s['turn'],
                      fixture_role_replies=session.e['calls'], local_fixture_seconds=round(time.perf_counter() - start, 3))
        report['fixture_request_characters_by_role'] = {
            role: {'min': min(values), 'median': statistics.median(values), 'max': max(values)}
            for role in ['player', 'gm', 'chronicler']
            if (values := [a['input_characters'] for a in session.e['audit']
                           if ('player' if a['agent_id'].startswith('player-') else a['agent_id']) == role])}
        if args.checkpoint:
            before = args.checkpoint.read_bytes(); source = json.loads(before)
            session = RoundSession.continue_from(args.checkpoint, Path(tmp) / 'probe', 'packet-probe')
            provider = FixtureProvider(); packets = []
            # One disposable synthetic round measures all roles with the real inherited memory.
            session.e['max_rounds'] = 1; session.save()
            while current := session.requests():
                for packet in current:
                    packets.append({'role': packet['agent_id'], 'operation': packet['operation'], 'characters': len(compact(packet))})
                    response, _ = provider.complete(packet)
                    if packet['operation'] in ['opening', 'adjudicate']:
                        response['payload']['location'] = source['location']
                        response['payload']['narration'] = source['scene'][:1400]
                    session.submit(response)
            assert args.checkpoint.read_bytes() == before, 'Source checkpoint changed'
            report['saved_campaign_packet_probe'] = {'source_session': source['config']['session_id'], 'source_unchanged': True, 'packets': packets}
    report['limitations'] = 'Local timings measure fixtures and disk work, not model latency, live story quality or API compatibility.'
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
