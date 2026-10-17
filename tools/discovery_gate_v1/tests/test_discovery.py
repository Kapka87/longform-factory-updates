import json
import tempfile
import unittest
from pathlib import Path
from discovery_gate import FixtureAPI, parse_time, verified_collect, write_outputs, dur_seconds, safe_csv, title_review_flags

FIXTURE=Path(__file__).with_name('sample_fixture.json')

class DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=json.loads(FIXTURE.read_text())
        cls.result=verified_collect(FixtureAPI(cls.fixture),parse_time('2026-10-17T00:00:00Z'),search_budget=3)
    def test_title_review_flags_are_not_factual_verdicts(self):
        self.assertIn('TITLE_SCRIPT_REVIEW_ONLY',title_review_flags('History — मेसोपोटामिया'))
        self.assertIn('THIRD_PARTY_MEDIA_RIGHTS_REVIEW_ONLY',title_review_flags('Jumanji FULL MOVIE'))
        self.assertIn('THIRD_PARTY_MEDIA_RIGHTS_REVIEW_ONLY',title_review_flags('Wizard of Oz Lost Scene'))
        self.assertEqual(title_review_flags('Why Are Wolves So Strange?'),[])

    def test_iso_duration(self):
        self.assertEqual(dur_seconds('PT8M'),480)
        self.assertEqual(dur_seconds('PT1H2M3S'),3723)
    def test_dedup_and_filter(self):
        r=self.result
        self.assertEqual(r['small_channel_candidates'],2)
        self.assertEqual(set(x['video_id'] for x in r['candidates']),{'a0000000001','e0000000005'})
        self.assertEqual(r['rejects']['TOO_SHORT'],1)
        self.assertEqual(r['rejects']['EXPLICITLY_NON_ENGLISH'],1)
        self.assertEqual(r['rejects']['OUTSIDE_SMALL_CHANNEL_SCOPE'],1)
        self.assertEqual(r['rejects']['SUBSCRIBERS_UNVERIFIED'],1)
    def test_raw_comparison_no_derived_score(self):
        a=next(x for x in self.result['candidates'] if x['video_id']=='a0000000001')
        self.assertEqual(a['baseline_video_views'],'2000;2400;2700')
        self.assertTrue(self.result['no_custom_scores'])
        self.assertNotIn('outlier_score',a)
        self.assertEqual(a['source_status'],'YOUTUBE_API_METADATA')
    def test_unknown_language_is_not_passed(self):
        e=next(x for x in self.result['candidates'] if x['video_id']=='e0000000005')
        self.assertEqual(e['language_status'],'UNVERIFIED')
        self.assertIn('LANGUAGE_NEEDS_MANUAL_REVIEW',e['flags'])
    def test_output_and_csv_formula_safety(self):
        self.assertEqual(safe_csv('=1+2'),"'=1+2")
        with tempfile.TemporaryDirectory() as d:
            write_outputs(self.result,Path(d))
            self.assertTrue((Path(d)/'report.md').is_file())
            self.assertEqual(len(json.loads((Path(d)/'candidates.json').read_text())['candidates']),2)

if __name__=='__main__':unittest.main()