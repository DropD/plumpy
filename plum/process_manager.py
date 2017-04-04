import threading
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from plum.process import Process, ProcessListener
from plum.util import override, protected
from plum.exceptions import TimeoutError


class _ProcInfo(object):
    def __init__(self, proc, thread):
        self.proc = proc
        self.executor_future = None


class Future(ProcessListener):
    def __init__(self, process):
        """
        The process manager creates instances of futures that can be used by the
        user.

        :param process: The process this is a future for
        :type process: :class:`plum.process.Process`
        """
        self._process = process
        self._terminated = threading.Event()
        self._process.add_process_listener(self)
        self._callbacks = []
        if self._process.has_terminated():
            self._terminated.set()

    @property
    def pid(self):
        """
        Contains the pid of the process

        :return: The pid
        """
        return self._process.pid

    @property
    def outputs(self):
        """
        Contains the current outputs of the process.  If it is still running
        these may grow (but not change) over time.

        :return: A mapping of {output_port: value} outputs
        :rtype: dict
        """
        return self._process.outputs

    def get_process(self):
        return self._process

    def result(self, timeout=None):
        """
        This method will block until the process has finished producing outputs
        and then return the final dictionary of outputs.

        If a timeout is given and the process has not finished in that time
        a :class:`TimeoutError` will be raised.

        :param timeout: (optional) maximum time to wait for process to finish
        :return: The final outputs
        """
        if self._terminated.wait(timeout):
            if self._process.has_failed():
                exc_info = self._process.get_exc_info()
                raise exc_info[0], exc_info[1], exc_info[2]
            else:
                return self.outputs
        else:
            raise TimeoutError()

    def exception(self, timeout=None):
        try:
            self.result(timeout)
        except TimeoutError:
            raise
        except BaseException as e:
            return e

        return None

    def abort(self, msg=None, timeout=None):
        """
        Abort the process

        :param msg: The abort message
        :type msg: str
        :param timeout: How long to wait for the process to abort itself
        :type timeout: float
        """
        return self._process.abort(msg, timeout)

    def play(self):
        return self._process.play()

    def pause(self, timeout):
        return self._process.pause(timeout)

    def wait(self, timeout=None):
        return self._terminated.wait(timeout)

    def add_done_callback(self, fn):
        if self._terminated.is_set():
            fn(self)
        else:
            self._callbacks.append(fn)

    @protected
    def on_process_done_playing(self, process):
        if process.has_terminated():
            self._terminate()

    def _terminate(self):
        self._terminated.set()
        for fn in self._callbacks:
            fn(self)


def wait_for_all(futures):
    for future in futures:
        future.wait()


class ProcessManager(ProcessListener):
    """
    Used to launch processes on separate threads and monitor their progress
    """

    def __init__(self, max_threads=1024):
        self._max_threads = max_threads
        self._processes = {}
        self._executor = ThreadPoolExecutor(max_workers=self._max_threads)

    def launch(self, proc_class, inputs=None, pid=None, logger=None):
        """
        Create a process and start it.

        :param proc_class: The process class
        :param inputs: The inputs to the process
        :param pid: The (optional) pid for the process
        :param logger: The (optional) logger for the process to use
        :return: A :class:`Future` representing the execution of the process
        :rtype: :class:`Future`
        """
        return self.start(proc_class.new(inputs, pid, logger))

    def start(self, proc):
        """
        Start an existing process.

        :param proc: The process to start
        :type proc: :class:`plum.process.Process`
        :return: A :class:`Future` representing the execution of the process
        :rtype: :class:`Future`
        """
        self._processes[proc.pid] = _ProcInfo(proc, None)
        proc.add_process_listener(self)
        self._play(proc)
        return Future(proc)

    def get_processes(self):
        return [info.proc for info in self._processes.values()]

    def has_process(self, pid):
        return pid in self._processes

    def play(self, pid):
        try:
            self._play(self._processes[pid].proc)
        except KeyError:
            raise ValueError("Unknown pid")

    def play_all(self):
        for info in self._processes.itervalues():
            self._play(info.proc)

    def pause(self, pid, timeout=None):
        try:
            return self._pause(self._processes[pid].proc, timeout)
        except KeyError:
            raise ValueError("Unknown pid")

    def pause_all(self, timeout=None):
        """
        Pause all processes.  This is a blocking call and will wait until they
        are all paused before returning.
        """
        result = True
        for info in self._processes.values():
            result &= self._pause(info.proc, timeout=timeout)
        return result

    def abort(self, pid, msg=None, timeout=None):
        try:
            return self._abort(self._processes[pid].proc, msg, timeout)
        except KeyError:
            raise ValueError("Unknown pid")

    def abort_all(self, msg=None, timeout=None):
        result = True
        for info in self._processes.values():
            try:
                result &= self._abort(info.proc, msg, timeout)
            except AssertionError:
                # This happens if the process is not playing
                pass
        return result

    def wait_for(self, pid, timeout=None):
        try:
            self._processes[pid].executor_future.result(timeout)
        except KeyError:
            raise ValueError("Unknown pid")
        except concurrent.futures.TimeoutError:
            return False

        return True

    def get_num_processes(self):
        return len(self._processes)

    def reset(self):
        self.shutdown()
        self._executor = ThreadPoolExecutor(max_workers=self._max_threads)

    def shutdown(self):
        self.pause_all()
        for p in self._processes.values():
            self._delete_process(p.proc)
        assert not self._processes
        self._executor.shutdown(True)

    # region From ProcessListener
    @override
    def on_process_stop(self, process):
        super(ProcessManager, self).on_process_stop(process)
        self._delete_process(process)

    @override
    def on_process_fail(self, process):
        super(ProcessManager, self).on_process_fail(process)
        self._delete_process(process)

    # endregion

    def _play(self, proc):
        if not proc.is_playing():
            info = self._processes[proc.pid]
            info.executor_future = self._executor.submit(proc.play)

    def _pause(self, proc, timeout=None):
        if proc.is_playing():
            info = self._processes[proc.pid]
            proc.pause()
            try:
                info.executor_future.result(timeout)
            except concurrent.futures.TimeoutError:
                return False

        return True

    def _abort(self, proc, msg=None, timeout=None):
        info = self._processes[proc.pid]
        info.proc.abort(msg)

        try:
            info.executor_future.result(timeout)
        except concurrent.futures.TimeoutError:
            return False

        return True

    def _delete_process(self, proc):
        """
        :param proc: :class:`plum.process.Process`
        """
        proc.remove_process_listener(self)
        info = self._processes.pop(proc.pid)
        assert info.executor_future is None or not info.executor_future.running()


_DEFAULT_PROCMAN = None


def get_default_procman():
    """
    :return: The default process manager
    :rtype: :class:`ProcessManager`
    """
    global _DEFAULT_PROCMAN
    if _DEFAULT_PROCMAN is None:
        _DEFAULT_PROCMAN = ProcessManager()
    return _DEFAULT_PROCMAN


def async(process, **inputs):
    if isinstance(process, Process):
        assert not inputs, "Cannot pass inputs to an already instantiated process"
        to_play = process
    elif isinstance(process, Process.__class__):
        to_play = process.new(inputs=inputs)
    else:
        raise ValueError("Process must be a process instance or class")

    get_default_procman().start(to_play)
