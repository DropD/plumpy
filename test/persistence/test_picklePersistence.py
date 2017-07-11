import os.path
from plum.process import ProcessState
from plum.persistence.pickle_persistence import PicklePersistence
from plum.test_utils import ProcessWithCheckpoint, WaitForSignalProcess
from plum.exceptions import LockError
from plum import loop_factory
from plum.wait_ons import run_until
from test.util import TestCase


class TestPicklePersistence(TestCase):
    def setUp(self):
        import tempfile

        super(TestPicklePersistence, self).setUp()

        self.loop = loop_factory()

        self.store_dir = tempfile.mkdtemp()
        self.pickle_persistence = PicklePersistence(running_directory=self.store_dir)
        self.pickle_persistence.start_persisting(self.loop)

    def tearDown(self):
        super(TestPicklePersistence, self).tearDown()
        self.pickle_persistence.clear_all_persisted()
        self._empty_directory()

    def test_store_directory(self):
        self.assertEqual(self.store_dir, self.pickle_persistence.store_directory)

    def test_on_create_process(self):
        proc = self.loop.create_task(ProcessWithCheckpoint)
        self.pickle_persistence.persist_process(proc)
        save_path = self.pickle_persistence.get_running_path(proc.pid)

        self.assertTrue(os.path.isfile(save_path))

    def test_on_waiting_process(self):
        proc = self.loop.create_task(WaitForSignalProcess)
        self.pickle_persistence.persist_process(proc)
        save_path = self.pickle_persistence.get_running_path(proc.pid)

        # Wait - Run the process and wait until it is waiting
        run_until(proc, ProcessState.WAITING, self.loop)

        # Check the file exists
        self.assertTrue(os.path.isfile(save_path))

    def test_on_finishing_process(self):
        proc = self.loop.create_task(ProcessWithCheckpoint)
        pid = proc.pid
        self.pickle_persistence.persist_process(proc)
        running_path = self.pickle_persistence.get_running_path(proc.pid)

        self.assertTrue(os.path.isfile(running_path))
        proc.run()
        self.assertFalse(os.path.isfile(running_path))
        finished_path = \
            os.path.join(self.store_dir,
                         self.pickle_persistence.finished_directory,
                         self.pickle_persistence.pickle_filename(pid))

        self.assertTrue(os.path.isfile(finished_path))

    def test_load_all_checkpoints(self):
        self._empty_directory()
        # Create some processes
        for i in range(0, 3):
            proc = self.loop.create_task(ProcessWithCheckpoint, pid=i)
            self.pickle_persistence.save(proc)

        # Check that the number of checkpoints matches we expected
        num_cps = len(self.pickle_persistence.load_all_checkpoints())
        self.assertEqual(num_cps, 3)

    def test_save(self):
        proc = self.loop.create_task(ProcessWithCheckpoint)
        running_path = self.pickle_persistence.get_running_path(proc.pid)
        self.pickle_persistence.save(proc)
        self.assertTrue(os.path.isfile(running_path))

    def test_persist_twice(self):
        proc = self.loop.create_task(WaitForSignalProcess)
        self.pickle_persistence.persist_process(proc)

        # Try persisting the process again using another persistence manager
        with self.assertRaises(LockError):
            PicklePersistence(running_directory=self.store_dir).persist_process(proc)

    def _empty_directory(self):
        import shutil
        if os.path.isdir(self.store_dir):
            shutil.rmtree(self.store_dir)
