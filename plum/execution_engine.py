
from collections import namedtuple
from abc import ABCMeta, abstractmethod

ProcessEntry = namedtuple('ProcessEntry', ['process', 'record'])


class Future(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def cancel(self):
        """
        Attempt to cancel the Process. If the call is currently being executed
        and cannot be cancelled then the method will return False, otherwise the
        Process will be cancelled and the method will return True.
        """
        pass

    @abstractmethod
    def cancelled(self):
        """
        Return True if the Process was successfully cancelled.
        """
        pass

    @abstractmethod
    def running(self):
        """
        Return True if the Process is currently being executed and cannot be
        cancelled.
        :return:
        """
        pass

    @abstractmethod
    def done(self):
        """
        Return True if the Process was successfully cancelled or finished
        running.
        """
        pass

    @abstractmethod
    def result(self, timeout=None):
        """
        Return the outputs from the Process. If the Process hasn't yet
        completed then this method will wait up to timeout seconds. If the call
        hasn't completed in timeout seconds, then a
        concurrent.futures.TimeoutError will be raised. timeout can be an int
        or float. If timeout is not specified or None, there is no limit to the
        wait time.

        If the future is cancelled before completing then CancelledError will be
        raised.

        If the Process raised, this method will raise the same exception.

        :param timeout: The timeout to wait for.  If None then waits until
        completion.
        """
        pass

    @abstractmethod
    def exception(self, timeout=None):
        """
        Return the exception raised by the Process. If the call hasn't yet
        completed then this method will wait up to timeout seconds. If the
        Process hasn't completed in timeout seconds, then a
        concurrent.futures.TimeoutError will be raised. timeout can be an int
        or float. If timeout is not specified or None, there is no limit to
        the wait time.

        If the future is cancelled before completing then CancelledError will be
        raised.

        If the call completed without raising, None is returned.

        :param timeout: The timeout to wait for.  If None then waits until
        completion.
        """
        pass

    @abstractmethod
    def add_done_callback(self, fn):
        """
        Attaches the callable fn to the future. fn will be called, with the
        future as its only argument, when the future is cancelled or finishes
        running.

        Added callables are called in the order that they were added and are
        always called in a thread belonging to the process that added them. If
        the callable raises an Exception subclass, it will be logged and
        ignored. If the callable raises a BaseException subclass, the behavior
        is undefined.

        If the future has already completed or been cancelled, fn will be
        called immediately.

        :param func: The function to call back.
        """
        pass


class EngineListener(object):
    __metaclass__ = ABCMeta

    def on_submitted_process(self, engine, process_class, inputs, checkpoint):
        pass

    def on_starting_process(self, engine, process, inputs):
        pass

    def on_waiting_process(self, engine, process, wait_on):
        pass

    def on_continuing_process(self, engine, process, callback_name):
        pass

    def on_finishing_process(self, engine, process):
        pass


class ExecutionEngine(object):
    """
    An execution engine is used to launch Processes.  This interface defines
    the things that the engine must be able to do.
    There are many imaginable types of engine e.g. multithreaded, celery based
    distributed across multiple machines, etc.
    """
    __metaclass__ = ABCMeta

    @abstractmethod
    def submit(self, process_class, inputs, checkpoint=None):
        """
        Submit a process to be executed with some inputs at some point.

        :param process_class: The process class to execute
        :param inputs: The inputs to execute the process with
        :param checkpoint: The checkpoint to continue from (or None)
        :return: A Future object that represents the execution of the Process.
        """
        pass

    @abstractmethod
    def get_process(self, pid):
        """
        Get a running process from its pid.

        :param pid: The pid of the process to get.
        :return: A running Process instance correponding to the pid.
        """
        pass
