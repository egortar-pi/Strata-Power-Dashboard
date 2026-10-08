import tempfile
import threading
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
import app

class StabilityTests(unittest.TestCase):
    def test_collector_recovers_after_db_error(self):
        stop = threading.Event()
        calls = []
        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise sqlite3.OperationalError('unable to open database file')
            stop.set()
        with patch.object(app, 'collector_once', side_effect=flaky), patch.object(app,'con',side_effect=sqlite3.OperationalError('db unavailable')):
            app.collector_loop(stop)
        self.assertEqual(len(calls), 2)

    def test_old_null_history(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / 'history.sqlite3'
            with patch.object(app,'ROOT',Path(d)), patch.object(app,'DB',db):
                app.init()
                with app.con() as con:
                    con.execute('INSERT INTO samples(ts,gpu_w,system_w,input_delta,output_delta,system_kwh_delta) VALUES(?,?,?,?,?,?)', (1,None,None,None,None,None))
                chart=app.snapshot('all')['chart']
                self.assertIsNone(chart[0]['gpu_w'])
                self.assertIsNone(chart[0]['system_w'])
                self.assertEqual(chart[0]['input'],0)

    def test_db_path_can_be_separate_from_root(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'program-dir'
            db=Path(d)/'data-dir'/'history.sqlite3'
            with patch.object(app,'ROOT',root), patch.object(app,'DB',db):
                app.init()
                self.assertTrue(db.exists())
                self.assertFalse((root/'history.sqlite3').exists())

if __name__ == '__main__':
    unittest.main()
