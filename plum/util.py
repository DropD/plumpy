# -*- coding: utf-8 -*-

import threading
import inspect
import importlib
import frozendict
from plum.settings import check_protected, check_override
from plum.exceptions import ClassNotFoundException
import plum.lang

protected = plum.lang.protected(check=check_protected)
override = plum.lang.override(check=check_override)


class EventHelper(object):
    def __init__(self, listener_type):
        assert(listener_type is not None)
        self._listener_type = listener_type
        self._listeners = set()

    def add_listener(self, listener):
        assert isinstance(listener, self._listener_type)
        self._listeners.add(listener)

    def remove_listener(self, listener):
        self._listeners.discard(listener)

    def remove_all_listeners(self):
        self._listeners.clear()

    @property
    def listeners(self):
        return self._listeners

    def fire_event(self, event_function, *args, **kwargs):
        # TODO: Check if the function is in the listener type
        # We have to use a copy here because the listener may
        # remove themselves during the message
        for l in list(self.listeners):
            getattr(l, event_function.__name__)(*args, **kwargs)


class ListenContext(object):
    """
    A context manager for listening to producer that can generate messages.
    The requirements for the producer are that it has methods:
    * start_listening(..), and,
    * stop_listening(..)
    and that these methods take zero or more arguments that identify the
    listener and perhaps what it wants to listen to if this make sense for
    the producer/listener combination.

    A typical usage would be:
    with ListenContext(producer, listener):
        # Producer generates messages that the listener gets
        pass
    """
    def __init__(self, producer, *args, **kwargs):
        self._producer = producer
        self._args = args
        self._kwargs = kwargs

    def __enter__(self):
        self._producer.start_listening(*self._args, **self._kwargs)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self._producer.stop_listening(*self._args, **self._kwargs)


class ThreadSafeCounter(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.counter = 0

    def increment(self):
        with self.lock:
            self.counter += 1

    def decrement(self):
        with self.lock:
            self.counter -= 1

    @property
    def value(self):
        with self.lock:
            return self.counter


def fullname(object):
    """
    Get the fully qualified name of an object.

    :param object: The object to get the name from.
    :return: The fully qualified name.
    """
    if inspect.isclass(object):
        return object.__module__ + "." + object.__name__
    else:
        return object.__module__ + "." + object.__class__.__name__


def load_class(classstring):
    """
    Load a class from a string
    """
    class_data = classstring.split(".")
    module_path = ".".join(class_data[:-1])
    class_name = class_data[-1]

    module = importlib.import_module(module_path)

    # Finally, retrieve the class
    try:
        return getattr(module, class_name)
    except AttributeError:
        raise ClassNotFoundException("Class {} not found".format(classstring))


class AttributesFrozendict(frozendict.frozendict):
    def __init__(self, *args, **kwargs):
        super(AttributesFrozendict, self).__init__(*args, **kwargs)
        self._initialised = True

    def __getattr__(self, attr):
        """
        Read a key as an attribute. Raise AttributeError on missing key.
        Called only for attributes that do not exist.
        """
        # This attribute is looked for by pickle when deserialising.  At this point
        # the object is not yet constructed and so accessing any members is
        # dangerous and often causes infinite recursion so I have to guard like this.
        if attr == "__setstate__":
            raise AttributeError()
        try:
            return self[attr]
        except KeyError:
            errmsg = "'{}' object has no attribute '{}'".format(
                self.__class__.__name__, attr)
            raise AttributeError(errmsg)

    def __dir__(self):
        """
        So we get tab completion.
        :return: The keys of the dict
        """
        return self.keys()
