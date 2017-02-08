from abc import ABCMeta, abstractmethod
import re
import threading
from plum.process_monitor import ProcessMonitorListener, MONITOR
from plum.util import override, protected, ListenContext
from plum.wait import WaitOn, Unsavable


class EventEmitter(object):
    """
    A class to send general events to listeners
    """
    __metaclass__ = ABCMeta

    @staticmethod
    def contains_wildcard(eventstring):
        """
        Does the event string contain a wildcard.

        :param eventstring: The event string
        :type eventstring: str or unicode
        :return: True if it does, False otherwise
        """
        return eventstring.find('*') != -1 or eventstring.find('#') != -1

    def __init__(self):
        self._specific_listeners = {}
        self._wildcard_listeners = {}
        self._wildcard_regexs = {}

    def start_listening(self, listener, event='*'):
        """
        Start listening to a particular event or a group of events.

        :param listener: The listener callback function to call when the
            event happens
        :param event: An event string
        :type event: str or unicode
        """
        self._check_listener(listener)
        if self.contains_wildcard(event):
            self._add_wildcard_listener(listener, event)
        else:
            self._add_specific_listener(listener, event)

    def stop_listening(self, listener, event=None):
        """
        Stop listening for events.  If event is not specified it is assumed
        that the listener wants to stop listening to all events.

        :param listener: The listener that is currently listening
        :param event: (optional) event to stop listening for
        :type event: str or unicode
        """
        if event is None:
            # This means remove ALL messages for this listener
            for e, ls, in self._specific_listeners.items():
                self._remove_specific_listener(listener, e)
            for e, ls in self._wildcard_listeners.items():
                self._remove_wildcard_listener(listener, e)
        else:
            if self.contains_wildcard(event):
                try:
                    self._remove_wildcard_listener(listener, event)
                except KeyError:
                    pass
            else:
                try:
                    self._remove_specific_listener(listener, event)
                except KeyError:
                    pass

    def listen_scope(self, listener, event=None):
        return ListenContext(self, listener, event)

    def clear_all_listeners(self):
        self._specific_listeners = {}
        self._wildcard_listeners = {}

    def num_listening(self):
        """
        Get the number of events that are being listening for.  This
        corresponds exactly to the number of .start_listening() calls made
        this this emitter.

        :return: The number of events listened for
        :rtype: int
        """
        total = 0
        for e, ls in self._specific_listeners.iteritems():
            total += len(ls)
        for e, ls in self._wildcard_listeners.iteritems():
            total += len(ls)
        return total

    def event_occurred(self, event, body=None):
        # These loops need to use copies because, e.g., the recipient may
        # add or remove listeners during the delivery

        # Deal with the wildcard listeners
        for e, ls in self._wildcard_listeners.items():
            if self._wildcard_match(e, event):
                for l in ls.copy():
                    self.deliver_msg(l, event, body)

        # And now with the specific listeners
        try:
            ls = self._specific_listeners[event].copy()
        except KeyError:
            pass
        else:
            for l in ls:
                try:
                    self.deliver_msg(l, event, body)
                except TypeError:
                    raise RuntimeError(
                        "Failed to deliver message to '{}', check the it"
                        " takes three arguments".format(l))

    @protected
    def deliver_msg(self, listener, event, body):
        listener(self, event, body)

    @protected
    def get_specific_listeners(self):
        return self._specific_listeners

    @protected
    def get_wildcard_listeners(self):
        return self._wildcard_listeners

    @staticmethod
    def _check_listener(listener):
        if not callable(listener):
            raise ValueError("Listener must be callable")
        # Can do more sophisticated checks here, but it's a pain (to check both
        # classes that are callable having the right signature and plain functions)

    def _add_wildcard_listener(self, listener, event):
        if event in self._wildcard_listeners:
            self._wildcard_listeners[event].add(listener)
        else:
            self._wildcard_listeners[event] = {listener}
            # Build the regular expression
            regex = event.replace('.', '\.').replace('*', '.*').replace('#', '.+')
            self._wildcard_regexs[event] = re.compile(regex)

    def _remove_wildcard_listener(self, listener, event):
        """
        Remove a wildcard listener.
        Precondition: listener in self._wildcard_listeners[event]

        :param listener: The listener to remove
        :param event: The event to stop listening for
        """
        self._wildcard_listeners[event].discard(listener)
        if len(self._wildcard_listeners[event]) == 0:
            del self._wildcard_listeners[event]
            del self._wildcard_regexs[event]

    def _add_specific_listener(self, listener, event):
        self._specific_listeners.setdefault(event, set()).add(listener)

    def _remove_specific_listener(self, listener, event):
        """
        Remove a specific listener.
        Precondition: listener in self._specific_listeners[event]

        :param listener: The listener to remove
        :param event: The event to stop listening for
        """
        self._specific_listeners[event].discard(listener)
        if len(self._specific_listeners[event]) == 0:
            del self._specific_listeners[event]

    def _wildcard_match(self, wildcard_string, to_match):
        return self._wildcard_regexs[wildcard_string].match(to_match) is not None


class EmitterAggregator(EventEmitter):
    def __init__(self):
        super(EmitterAggregator, self).__init__()
        self._children = []

    @override
    def start_listening(self, listener, event='*'):
        super(EmitterAggregator, self).start_listening(listener, event)
        for t in self._children:
            try:
                t.start_listening(self._event_passthrough, event)
            except ValueError:
                pass

    @override
    def stop_listening(self, listener, event=None):
        specific = set(self.get_specific_listeners().viewkeys())
        wildcard = set(self.get_wildcard_listeners().viewkeys())
        # Now stop firing myself
        super(EmitterAggregator, self).stop_listening(listener, event)

        # Check the different in events being listen to to see if we now are no
        # longer listening to some events
        specific -= set(self.get_specific_listeners().viewkeys())
        wildcard -= set(self.get_wildcard_listeners().viewkeys())
        for event in specific | wildcard:
            for child in self._children:
                child.stop_listening(self._event_passthrough, event)

    @override
    def clear_all_listeners(self):
        for t in self._children:
            t.clear_all_listeners()
        super(EmitterAggregator, self).clear_all_listeners()

    def add_child(self, child):
        """
        Add a child to this aggregator

        :param child: The child to add
        :type child: :class:`EventEmitter`
        """
        assert isinstance(child, EventEmitter)

        self._children.append(child)
        for e in self._specific_listeners.iterkeys():
            try:
                child.start_listening(self.event_occurred, e)
            except ValueError:
                pass
        for e in self._wildcard_listeners.iterkeys():
            try:
                child.start_listening(self.event_occurred, e)
            except ValueError:
                pass

    def remove_child(self, child):
        """
        Remove a tracker from this aggregator

        :param child: The tracker to remove
        :type child: :class:`EventEmitter`
        """
        assert child in self._children
        child.stop_listening(self.event_occurred)
        self._children.remove(child)

    def _event_passthrough(self, emitter, event, body):
        self.event_occurred(event, body)


class WithProcessEvents(object):
    """
    A mixin to add a commonly used proxy function that removes the need for
    boilerplate event message code for processes.
    """
    @protected
    def process_event_occurred(self, pid, event, body=None):
        self.event_occurred("process.{}.{}".format(pid, event), body)


class ProcessMonitorEmitter(EventEmitter, WithProcessEvents, ProcessMonitorListener):
    """
    Emit events as gathered from the process monitor
    """

    def __init__(self):
        super(ProcessMonitorEmitter, self).__init__()

    @override
    def start_listening(self, listener, event='*'):
        if not event.startswith("process."):
            raise ValueError("This emitter only knows about process.[pid[.event]] events")
        super(ProcessMonitorEmitter, self).start_listening(listener, event)
        if self.num_listening() > 0:
            MONITOR.start_listening(self)

    @override
    def stop_listening(self, listener, event=None):
        super(ProcessMonitorEmitter, self).stop_listening(listener, event)
        if self.num_listening() == 0:
            MONITOR.stop_listening(self)

    @override
    def on_monitored_process_finish(self, process):
        self.process_event_occurred(process.pid, "finished")

    @override
    def on_monitored_process_stopped(self, process):
        self.process_event_occurred(process.pid, "stopped")

    @override
    def on_monitored_process_failed(self, process):
        self.process_event_occurred(process.pid, "failed")


class PollingEmitter(EventEmitter):
    __metaclass__ = ABCMeta

    def __init__(self, poll_interval):
        """
        :param poll_interval: A poll interval specified as a float representing
            the number of seconds between polls
        """
        super(PollingEmitter, self).__init__()
        self._poll_interval = poll_interval
        self._stop = False
        self._polling = False
        self._timer = None
        # Any internal reads/writes of state should use this lock
        # need to use an rlock 'cause poll may call, e.g., stop_listening()
        # which will reacquire the lock
        self._state_lock = threading.RLock()

    def is_polling(self):
        return self._polling

    @override
    def start_listening(self, listener, event='*'):
        with self._state_lock:
            super(PollingEmitter, self).start_listening(listener, event)
            if not self._polling:
                self._start_polling()

    @override
    def stop_listening(self, listener, event=None):
        with self._state_lock:
            super(PollingEmitter, self).stop_listening(listener, event)
            if self.num_listening() == 0:
                self._stop_polling()

    @override
    def clear_all_listeners(self):
        with self._state_lock:
            super(PollingEmitter, self).clear_all_listeners()
            if self.num_listening() == 0:
                self._stop_polling()

    @abstractmethod
    def poll(self):
        """
        The subclass should implement this to perform the actions it wants
        to do every time it is polled.
        """
        pass

    def _start_polling(self):
        self._stop = False
        self._polling = True
        self._timer = threading.Timer(0, self._poll)
        self._timer.start()

    def _stop_polling(self):
        if self._polling:
            self._stop = True
            self._polling = False
            self._timer.cancel()
            self._timer = None

    def _poll(self):
        with self._state_lock:
            if not self._stop:
                # The reason it's done this way is that the poll() call may take some
                # time during which a user may have called stop() so we check again
                self.poll()
                if not self._stop:
                    self._timer = threading.Timer(self._poll_interval, self._poll)
                    self._timer.start()


class WaitOnEvent(WaitOn, Unsavable):
    def __init__(self, emitter, event):
        """
        :param emitter: The emitter to listen to
        :type emitter: :class:`EventEmitter`
        :param event: The event to listen for
        :type event: str or unicode
        """
        super(WaitOnEvent, self).__init__()
        self._event = event
        self._received_event = None
        emitter.start_listening(self.event_occurred, event)

    def event_occurred(self, emitter, event, body):
        self._received_event = event, body
        emitter.stop_listening(self._event)
        self.done()

    def get_received_event(self):
        """
        Returns a tuple containing the event string itself and the body
        (if any) of the event that was received.
        :return:
        """
        return self._received_event


class WaitOnProcessEvent(WaitOnEvent):
    """
    Wait for an event(s) from a process(es).  You can wait for a specific or
    wildcard event from a specific or wildcard process id.
    """

    def __init__(self, emitter, pid='*', event='*'):
        """
        :param emitter: The event emitter to listen to
        :type emitter: :class:`EventEmitter`
        :param pid: The process id, can also contain a wilcard string.  By
            default listens for all processes
        :param event: The process event to listen for e.g. finished, can be
            wildcard on which case all events are listened for
        """
        super(WaitOnProcessEvent, self).__init__(
            emitter, "process.{}.{}".format(pid, event))
