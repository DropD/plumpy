
from unittest import TestCase
from plum.persistence.pickle_persistence import PicklePersistence
from plum.process_monitor import MONITOR
from plum.test_utils import ProcessWithCheckpoint, WaitForSignalProcess
import os.path
import threading


class TestPicklePersistence(TestCase):
    def setUp(self):
        import tempfile

        self.assertEqual(len(MONITOR.get_pids()), 0)

        self.store_dir = tempfile.mkdtemp()
        self.pickle_persistence = PicklePersistence(running_directory=self.store_dir)

    def tearDown(self):
        self.assertEqual(len(MONITOR.get_pids()), 0)
        self._empty_directory()

    def test_store_directory(self):
        self.assertEqual(self.store_dir,
                         self.pickle_persistence.store_directory)

    def test_on_create_process(self):
        proc = ProcessWithCheckpoint.new_instance()
        self.pickle_persistence.persist_process(proc)
        save_path = self.pickle_persistence.get_running_path(proc.pid)

        self.assertTrue(os.path.isfile(save_path))

    def test_on_waiting_process(self):
        proc = WaitForSignalProcess.new_instance()
        self.pickle_persistence.persist_process(proc)
        save_path = self.pickle_persistence.get_running_path(proc.pid)

        t = threading.Thread(target=proc.start)
        t.start()

        # Check the file exists
        self.assertTrue(os.path.isfile(save_path))

        proc.abort()
        t.join()

    def test_on_finishing_process(self):
        proc = ProcessWithCheckpoint.new_instance()
        pid = proc.pid
        self.pickle_persistence.persist_process(proc)
        running_path = self.pickle_persistence.get_running_path(proc.pid)

        self.assertTrue(os.path.isfile(running_path))
        proc.start()
        self.assertFalse(os.path.isfile(running_path))
        finished_path =\
            os.path.join(self.store_dir,
                         self.pickle_persistence.finished_directory,
                         self.pickle_persistence.pickle_filename(pid))

        self.assertTrue(os.path.isfile(finished_path))

    def test_load_all_checkpoints(self):
        self._empty_directory()
        # Create some processes
        for i in range(0, 3):
            proc = ProcessWithCheckpoint.new_instance(pid=i)
            self.pickle_persistence.persist_process(proc)

        # Check that the number of checkpoints matches we we expected
        num_cps = len(self.pickle_persistence.load_all_checkpoints())
        self.assertEqual(num_cps, 3)

    def test_save(self):
        proc = ProcessWithCheckpoint.new_instance()
        running_path = self.pickle_persistence.get_running_path(proc.pid)
        self.pickle_persistence.save(proc)
        self.assertTrue(os.path.isfile(running_path))

    def _empty_directory(self):
        import shutil
        if os.path.isdir(self.store_dir):
            shutil.rmtree(self.store_dir)

