import copy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from agent_provider import ResponsesProvider, ProviderError
from round_memory import context, recall
from rounds import RoundSession, compact
from ttrpg import Campaign, ProtocolError

ROOT = Path(__file__).parents[1]
CONFIG = json.loads((ROOT / 'config/tavern-zero.json').read_text())
JOURNAL = {'goal': 'Explore', 'notes': [], 'questions': []}


def answer(packet, payload):
    return {k: packet[k] for k in ['request_id', 'agent_id', 'state_version']} | {'payload': payload}


class FixtureProvider:
    """Synthetic protocol responses, never a model or campaign play."""
    def complete(self, packet):
        ctx, op = packet['context'], packet['operation']
        records = {'entities': [], 'facts': [], 'grants': [], 'public_fact_ids': []}
        if op == 'opening':
            payload = dict(kind='scene', narration='A road leads outside.', location='crooked-lantern',
                           notebook=copy.deepcopy(JOURNAL), **records)
        elif op == 'declare':
            cid = ctx['character']['id']
            payload = dict(kind='action', character_id=cid, speech='Let us explore.', action='Walk outside with the party.',
                           intent='PRIVATE_' + cid, target=None,
                           journal=dict(goal='Explore', notes=['NOTE_' + cid], questions=[]))
        elif op in ['adjudicate', 'resolve']:
            checks = ctx['saved_checks']
            payload = dict(kind='resolved', narration='The party looks down the lane.', location='crooked-lantern',
                           results=[{'character_id': a['character_id'], 'outcome': checks.get(a['character_id'], {}).get('outcome', 'NO_ROLL')}
                                    for a in ctx['declarations']], notebook=copy.deepcopy(JOURNAL), **records)
        else:
            payload = dict(kind='review', approved=True, conflicts=[], summary='The party explored together.',
                           source_fact_ids=['fact-seed-tavern'], next_hook='Continue exploring.')
        return answer(packet, payload), {'input_tokens': 5, 'output_tokens': 3, 'total_tokens': 8}


class RoundTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'campaign'
        Campaign.create(self.root, copy.deepcopy(CONFIG))
        self.live = RoundSession.attach(self.root)
        self.provider = FixtureProvider()

    def accept(self, packet=None, change=None):
        packet = packet or self.live.requests()[0]
        response, usage = self.provider.complete(packet)
        if change: change(response['payload'])
        self.live.submit(response, usage=usage)
        return response

    def opening(self): self.accept()

    def declarations(self):
        for packet in self.live.requests(): self.accept(packet)

    def adjudicate(self):
        self.opening(); self.declarations()
        return self.live.requests()[0]

    def check(self, packet, difficulty=13):
        actor = self.live.e['actors'][0]
        return answer(packet, dict(kind='checks', checks=[dict(character_id=actor, skill='INSIGHT', difficulty=difficulty,
                                  advantage=False, disadvantage=False, reason='Inspect')]))

    def test_five_rounds_are_15_turns_and_22_calls(self):
        while self.live.run_batch(self.provider): pass
        self.assertEqual(('ENDED', 15, 5, 22), (self.live.s['phase'], self.live.s['turn'], self.live.e['round'], self.live.e['calls']))
        self.assertEqual(1, len(self.live.e['reviews']))
        self.assertEqual(5, sum(a.get('operation') == 'adjudicate' for a in self.live.e['audit']))
        self.assertTrue(all(a['dispatch_to_reply_ms'] is not None for a in self.live.e['audit']))
        transcript = (self.root / 'sessions/session-0001/transcript.md').read_text()
        self.assertNotIn('PRIVATE_', transcript)
        self.assertEqual(5, transcript.count('The party looks down the lane.'))

    def test_same_scene_independent_packets_and_out_of_order_replies(self):
        self.opening(); packets = self.live.requests()
        self.assertEqual(1, len({p['state_version'] for p in packets}))
        self.assertEqual(1, len({p['context']['scene'] for p in packets}))
        self.accept(packets[2]); self.accept(packets[0])
        self.assertEqual(0, self.live.s['turn'])
        restarted = RoundSession(self.root)
        self.assertEqual([packets[1]], restarted.requests())
        self.live = restarted; self.accept(packets[1])
        gm = self.live.requests()[0]
        self.assertEqual(list(self.live.s['characters']), [a['character_id'] for a in gm['context']['declarations']])
        self.accept(gm)
        for packet in self.live.requests():
            cid = packet['context']['character']['id']
            self.assertIn('NOTE_' + cid, compact(packet))
            for other in self.live.s['characters']:
                if other != cid:
                    self.assertNotIn('NOTE_' + other, compact(packet))
                    self.assertNotIn('PRIVATE_' + other, compact(packet))
        self.assertNotIn('NOTE_', compact(context(self.live.s, 'gm')))

    def test_dice_survive_export_crash_and_duplicate(self):
        packet = self.adjudicate(); response = self.check(packet)
        with patch.object(self.live, 'export', side_effect=OSError('Crash after commit')):
            with self.assertRaises(OSError): self.live.submit(response)
        self.live = RoundSession(self.root)
        checks = copy.deepcopy(self.live.e['checks']); rng = compact(self.live.s['rng_state'])
        self.assertTrue(self.live.submit(response)['duplicate'])
        self.assertEqual(checks, self.live.e['checks'])
        self.assertEqual(rng, compact(self.live.s['rng_state']))
        self.assertEqual(1, sum(e['message_type'] == 'DICE_RESULT' for e in self.live.s['events']))
        packet = self.live.requests()[0]
        self.assertEqual(checks, packet['context']['saved_checks'])
        self.accept(packet)
        self.assertEqual(3, self.live.s['turn'])

    def test_invalid_roll_and_result_cannot_change_world(self):
        packet = self.adjudicate(); rng = compact(self.live.s['rng_state'])
        with self.assertRaises(ProtocolError): self.live.submit(self.check(packet, 31))
        self.assertEqual(rng, compact(self.live.s['rng_state']))
        self.live.submit(self.check(packet, 1))
        packet = self.live.requests()[0]
        with self.assertRaises(ProtocolError): self.accept(packet, lambda p: p['results'][0].update(outcome='FAILURE'))
        self.assertEqual(0, self.live.s['turn'])
        self.accept(packet)

    def test_prefix_defers_choices_and_rotates_actor(self):
        packet = self.adjudicate()
        self.accept(packet, lambda p: p.update(results=p['results'][:1]))
        self.assertEqual((1, 1), (self.live.s['turn'], self.live.s['next_actor']))
        packets = self.live.requests()
        self.assertEqual('player-02', packets[0]['agent_id'])
        self.assertEqual(3, len(packets))
        self.assertEqual(2, len(self.live.e['round_metrics'][0]['deferred_characters']))

    def test_rolled_actor_cannot_be_deferred(self):
        packet = self.adjudicate(); response = self.check(packet)
        response['payload']['checks'][0].update(character_id='torren-bright', skill='ARCANA')
        self.live.submit(response)
        with self.assertRaises(ProtocolError): self.accept(change=lambda p: p.update(results=p['results'][:1]))
        self.assertEqual(0, self.live.s['turn'])

    def add_secret(self, payload):
        payload['facts'] = [dict(id='hidden-test', entity_id='crooked-lantern', source='gm', classification='SECRET_CANON', statement='HIDDEN_ZEBRA_739')]
        payload['grants'] = [dict(character_id='arlen-vale', fact_id='hidden-test')]

    def test_selective_knowledge_gate_recall_and_journal_privacy(self):
        self.accept(change=self.add_secret)
        self.assertEqual('GATE', self.live.e['phase'])
        self.assertNotIn('hidden-test', self.live.s['facts'])
        self.accept()
        self.assertEqual(1, len(recall(self.live.s, 'player-01', 'hidden-test')['facts']))
        self.assertEqual([], recall(self.live.s, 'player-02', 'hidden-test')['facts'])
        for packet in self.live.requests():
            if packet['agent_id'] != 'player-01': self.assertNotIn('HIDDEN_ZEBRA', compact(packet))
        self.assertEqual('SECRET_CANON', self.live.s['facts']['hidden-test']['classification'])

    def test_verbatim_secret_in_public_narration_rejected(self):
        def leak(payload): self.add_secret(payload); payload['narration'] = 'HIDDEN_ZEBRA_739'
        with self.assertRaises(ProtocolError): self.accept(change=leak)
        self.assertEqual([], self.live.s['public_log'])
        self.assertNotIn('hidden-test', self.live.s['facts'])

    def test_review_conflict_pauses_without_publication(self):
        self.accept(change=self.add_secret)
        self.accept(change=lambda p: p.update(approved=False, conflicts=[dict(fact_id='hidden-test', reason='Needs investigation')]))
        self.assertEqual('not_committed', self.live.e['paused']['publication'])
        with self.assertRaises(ProtocolError): self.live.retry('Ignore this')
        self.assertNotIn('hidden-test', self.live.s['facts'])

    def test_recall_is_scoped_bounded_and_durable(self):
        self.opening(); packet = self.live.requests()[0]
        for _ in range(2):
            self.live.submit(answer(packet, {'kind': 'recall', 'query': 'tavern'}))
            self.live = RoundSession(self.root)
            packet = next(p for p in self.live.requests() if p['agent_id'] == 'player-01')
        self.assertTrue(packet['context']['recalled'])
        with self.assertRaises(ProtocolError): self.live.submit(answer(packet, {'kind': 'recall', 'query': 'tavern'}))

    def test_call_budget_reserves_entire_batch_before_provider(self):
        self.opening(); self.live.e['maximum_calls'] = 3; self.live.save()
        with patch.object(self.provider, 'complete') as complete:
            with self.assertRaises(ProtocolError): self.live.run_batch(self.provider)
        complete.assert_not_called()
        self.assertEqual(1, self.live.e['calls'])

    def test_player_calls_are_parallel_with_reserved_inboxes(self):
        self.opening(); barrier = threading.Barrier(3, timeout=5)
        base = self.provider.complete
        def complete(packet):
            state = json.loads(self.live.campaign.path.read_text())
            self.assertTrue(all(r['in_flight'] for r in state['round_runtime']['requests'].values()))
            barrier.wait()
            return base(packet)
        with patch.object(self.provider, 'complete', side_effect=complete): self.live.run_batch(self.provider)
        self.assertEqual('ADJUDICATE', self.live.e['phase'])

    def test_interruption_and_bad_replies_have_bounded_attempts(self):
        packet = self.live.requests()[0]; rid = packet['request_id']
        self.live.reserve(rid); self.live = RoundSession(self.root)
        with self.assertRaises(ProtocolError): self.live.reserve(rid)
        self.live.interrupt(rid)
        for _ in range(2):
            bad, _ = self.provider.complete(packet); bad['agent_id'] = 'player-01'
            with self.assertRaises(ProtocolError): self.live.submit(bad)
        self.assertEqual(3, self.live.e['calls'])
        self.assertEqual('attempt_limit', self.live.e['paused']['kind'])

    def test_end_cap_resolves_only_remaining_character(self):
        self.opening(); self.live.s['turn'] = 99; self.live.save()
        packets = self.live.requests(); self.assertEqual(1, len(packets))
        self.accept(packets[0]); self.accept(); self.accept()
        self.assertEqual(('ENDED', 100), (self.live.s['phase'], self.live.s['turn']))

    def test_finish_after_declaration_completes_round_and_review(self):
        self.opening(); self.accept(self.live.requests()[0]); self.live.finish()
        while self.live.run_batch(self.provider): pass
        self.assertEqual((1, 3), (self.live.e['round'], self.live.s['turn']))

    def test_periodic_review_and_final_review_not_duplicated(self):
        self.live.e['max_rounds'] = 6; self.live.save()
        while self.live.run_batch(self.provider): pass
        self.assertEqual((18, 27, 2), (self.live.s['turn'], self.live.e['calls'], len(self.live.e['reviews'])))

    def test_continuation_preserves_source_knowledge_journals_and_rng(self):
        self.live.e['max_rounds'] = 1; self.live.save()
        while self.live.run_batch(self.provider): pass
        source = self.live.campaign.path; before = source.read_bytes()
        nxt = RoundSession.continue_from(source, Path(self.temp.name) / 'next')
        self.assertEqual(before, source.read_bytes())
        for key in ['characters', 'role_journals', 'facts']:
            self.assertEqual(self.live.s[key], nxt.s[key])
        self.assertEqual(compact(self.live.s['rng_state']), compact(nxt.s['rng_state']))
        self.assertEqual((0, 0, 0), (nxt.s['turn'], nxt.e['calls'], nxt.e['round']))

    def test_stale_writer_and_legacy_writes_rejected(self):
        stale = RoundSession(self.root); self.opening()
        with self.assertRaises(ProtocolError): stale.requests()
        with self.assertRaises(ProtocolError): self.live.campaign.submit('scene', {'message_id': 'legacy', 'payload': {}})

    def test_profiles_and_unmeasured_relay_time(self):
        packet = self.live.requests()[0]
        self.assertEqual('gpt-6-astra', packet['profile']['native_model'])
        self.accept(packet)
        self.assertIsNone(self.live.e['audit'][-1]['dispatch_to_reply_ms'])
        packet = self.live.requests()[0]
        self.assertEqual('gpt-5.6-luna', packet['profile']['native_model'])
        self.assertEqual('low', packet['profile']['reasoning_effort'])
        self.assertLess(len(compact(packet)), 8000)

    def test_gate_can_cite_new_public_fact_but_not_new_secret(self):
        def create(payload):
            self.add_secret(payload)
            payload['facts'].append(dict(id='public-test', entity_id='crooked-lantern', source='gm', classification='RUMOR', statement='A traveler claims a storm approaches.'))
            payload['grants'] += [dict(character_id=cid, fact_id='public-test') for cid in self.live.s['characters']]
            payload['public_fact_ids'] = ['public-test']
        self.accept(change=create)
        self.accept(change=lambda p: p.update(source_fact_ids=['public-test']))
        self.assertEqual('RUMOR', self.live.s['facts']['public-test']['classification'])
        fact = next(f for f in context(self.live.s, 'gm')['facts'] if f['id'] == 'hidden-test')
        self.assertEqual(['arlen-vale'], fact['known_by'])

    def test_group_travel_creates_location_in_one_result(self):
        packet = self.adjudicate()
        def move(payload):
            payload['entities'] = [dict(id='test-lane', name='Test Lane', type='LOCATION', undefined_fields=[])]
            payload['location'] = 'test-lane'
            payload['narration'] = 'Together, the party walks onto the lane.'
        self.accept(packet, move)
        self.assertEqual(('test-lane', 3, 5), (self.live.s['location'], self.live.s['turn'], self.live.e['calls']))
        self.assertEqual('test-lane', self.live.requests()[0]['context']['location'])

    def test_compaction_keeps_current_action_and_review_evidence(self):
        self.opening()
        self.live.s['public_log'] += [dict(kind='scene', scene_id='fixture-scene', turn=0, text='x' * 20000) for _ in range(3)]
        self.live.s['scene'] = 's' * 1400
        self.live.save()
        for packet in self.live.requests(): self.assertLessEqual(len(compact(packet)), 8000)
        self.declarations(); self.accept()
        self.live.finish(); review = self.live.requests()[0]
        self.assertTrue(review['context']['record_changes'])
        self.assertEqual(self.live.s['public_log'], review['context']['review_window'])

    def test_packet_build_failure_does_not_leave_half_built_inboxes(self):
        before = copy.deepcopy(self.live.s)
        with patch('rounds.response_schema', side_effect=ProtocolError('Packet failure')):
            with self.assertRaises(ProtocolError): self.live.requests()
        self.assertEqual(before, self.live.s)
        self.assertEqual(before, RoundSession(self.root).s)

    def test_api_profile_controls_effort_and_output_limit(self):
        seen = []
        def opener(request, timeout):
            seen.append(json.loads(request.data))
            return io.BytesIO(b'{"status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":"{}"}]}]}')
        p = self.live.requests()[0]
        provider = ResponsesProvider({'gm': 'fixture-model'}, api_key='TEST_ONLY', opener=opener,
                                     role_settings={'gm': {'reasoning_effort': 'medium', 'max_output_tokens': 4500}})
        provider.complete(p)
        self.assertEqual({'effort': 'medium'}, seen[0]['reasoning'])
        self.assertEqual(4500, seen[0]['max_output_tokens'])
        self.assertNotIn('tools', seen[0])


if __name__ == '__main__': unittest.main()
