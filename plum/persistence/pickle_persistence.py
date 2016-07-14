
import glob
import os
import os.path as path
import tempfile
import pickle
from plum.process_listener import ProcessListener
from plum.process_monitor import monitor, ProcessMonitorListener
from plum.util import override
from plum.persistence._base import LOGGER


_STORE_DIRECTORY = path.join(tempfile.gettempdir(), "process_records")
_FINISHED_DIRECTORY = path.join(_STORE_DIRECTORY, "finished")
_FAILED_DIRECTORY = path.join(_STORE_DIRECTORY, "failed")


class PicklePersistence(ProcessListener, ProcessMonitorListener):
    def __init__(self, process_factory, auto_persist=False,
                 directory=_STORE_DIRECTORY,
                 finished_directory=_FINISHED_DIRECTORY,
                 failed_directory=_FAILED_DIRECTORY):
        self._process_factory = process_factory
        self._running_directory = directory
        self._finished_directory = finished_directory
        self._failed_directory = failed_directory
        self._auto_persist = auto_persist

        monitor.add_monitor_listener(self)

    def load_checkpoint(self, pid):
        for check_dir in [self._running_directory, self._failed_directory,
                          self._finished_directory]:
            p = path.join(check_dir, str(pid) + ".pickle")
            if path.isfile(p):
                return self.load_checkpoint_from_file(p)

        raise ValueError(
            "Not checkpoint with pid '{}' could be found".format(pid))

    def load_all_checkpoints(self):
        checkpoints = []
        for f in glob.glob(path.join(self._running_directory, "*.pickle")):
            try:
                checkpoints.append(self.load_checkpoint_from_file(f))
            except EOFError:
                pass
        return checkpoints

    def load_checkpoint_from_file(self, filepath):
        with open(filepath, 'rb') as file:
            return pickle.load(file)

    @property
    def store_directory(self):
        return self._running_directory

    @property
    def failed_directory(self):
        return self._failed_directory

    @property
    def finished_directory(self):
        return self._finished_directory

    def persist_process(self, process):
        # If the process doesn't have a persisted state then persist it now
        if not path.isfile(self.get_running_path(process.pid)):
            try:
                self.save(process)
            except pickle.PicklingError as e:
                LOGGER.error(
                    "exception raised trying to pickle process (pid={}).\n"
                    "{}".format(process.pid, e.message))

        process.add_process_listener(self)

    def get_running_path(self, pid):
        """
        Get the path where the pickle for a process with pid will be stored
        while it's running.
        :param pid: The process pid
        :return: A string to the absolute path of where the pickle is stored.
        """
        return path.join(self._running_directory, self._pickle_filename(pid))

    def save(self, process, wait_on=None):
        checkpoint = self._process_factory.create_checkpoint(process, wait_on)
        self._ensure_directory(self._running_directory)
        filename = self.get_running_path(process.pid)
        try:
            with open(filename, 'wb') as f:
                pickle.dump(checkpoint, f)
        except pickle.PickleError:
            # Don't leave a half-baked pickle around
            if path.isfile(filename):
                os.remove(filename)
            raise

    # ProcessListener messages #################################################
    @override
    def on_process_run(self, process):
        try:
            self.save(process)
        except pickle.PicklingError:
            LOGGER.error("exception raised trying to pickle process (pid={}) "
                         "during on_run message.".format(process.pid))

    @override
    def on_process_wait(self, process, wait_on):
        try:
            self.save(process, wait_on)
        except pickle.PicklingError:
            LOGGER.error("exception raised trying to pickle process (pid={}) "
                         "during on_wait message.".format(process.pid))

    @override
    def on_process_finish(self, process, retval):
        try:
            self.save(process)
        except pickle.PicklingError:
            LOGGER.error("exception raised trying to pickle process (pid={}) "
                         "during on_finish message.".format(process.pid))

    @override
    def on_process_destroy(self, process):
        try:
            self._release_process(process.pid, self.finished_directory)
        except ValueError:
            pass
    ############################################################################

    # ProcessMonitorListener messages ##########################################
    @override
    def on_monitored_process_failed(self, pid):
        try:
            self._release_process(pid, self.failed_directory)
        except ValueError:
            pass
    ############################################################################

    @override
    def on_monitored_process_created(self, process):
        if self._auto_persist:
            self.persist_process(process)


    def _release_process(self, pid, save_path):
        pickle_path = self.get_running_path(pid)
        if not path.isfile(pickle_path):
            raise ValueError(
                "Cannot find pickle for process with pid '{}'".format(pid))

        if path.isfile(pickle_path):
            if save_path is not None:
                self._ensure_directory(save_path)
                to = path.join(
                    save_path, self._pickle_filename(pid))
                os.rename(pickle_path, to)
            else:
                os.remove(pickle_path)

    @staticmethod
    def _pickle_filename(pid):
        return "{}.pickle".format(pid)

    @staticmethod
    def _ensure_directory(dir_path):
        if not path.isdir(dir_path):
            os.makedirs(dir_path)
