# -*- coding: utf-8 -*-

import threading
from abc import ABCMeta

from plum.persistence.bundle import Bundle
from plum.util import fullname, protected, override
from plum.exceptions import Unsupported


class Interrupted(Exception):
    pass


class WaitOn(object):
    """
    An object that represents something that is being waited on.

    .. warning:: Only a single thread can `wait` on this wait on.  If it is
        necessary to have another thread wait on the same thing then a copy
        should be made.
    """
    __metaclass__ = ABCMeta

    CLASS_NAME = "class_name"
    OUTCOME = "outcome"
    RECREATE_FROM_KEY = 'recreate_from'

    @staticmethod
    def _is_saved_state(args):
        return len(args) == 1 and isinstance(args[0], Bundle)

    @staticmethod
    def create_from(bundle):
        """
        Create the wait on from a save instance state.

        :param bundle: The saved instance state
        :return: The wait on with its state as it was when it was saved
        :rtype: :class:`WaitOn`
        """
        class_name = bundle[WaitOn.CLASS_NAME]
        wait_on_class = bundle.get_class_loader().load_class(class_name)
        return wait_on_class(recreate_from=bundle)

    def __init__(self, *args, **kwargs):
        self._outcome = None

        # Variables below this don't need to be saved in the instance state
        self._waiting = threading.Event()
        self._interrupt_lock = threading.Lock()
        self.__super_called = False

        if kwargs and kwargs.get(self.RECREATE_FROM_KEY, False):
            bundle = kwargs.pop(self.RECREATE_FROM_KEY)
            assert isinstance(bundle, Bundle), \
                "'{}' must be of type {}".format(self.RECREATE_FROM_KEY, Bundle.__class__)
            assert not args and not kwargs, \
                "If '{}' is supplied cannot have another parameters".format(self.RECREATE_FROM_KEY)
            self.load_instance_state(bundle, *args, **kwargs)
        else:
            self.init(*args, **kwargs)

        assert self.__super_called, \
            "Base method was not called\n" \
            "Hint: Try adding super({}, self).[method_name](bundle) " \
            "as the first line of your method".format(self.__class__.__name__)

    def is_done(self):
        """
        Indicate if finished waiting or not.
        To find out if what the outcome is call `get_outcome`

        :return: True if finished, False otherwise.
        """
        return self._outcome is not None

    def get_outcome(self):
        """
        Get the outcome of waiting.  Returns a tuple consisting of (bool, str)
        where the first value indicates success or failure, while the second
        gives an optional message.

        :return: A tuple indicating the outcome of waiting.
        :rtype: tuple
        """
        return self._outcome

    def save_instance_state(self, out_state):
        """
        Save the current state of this wait on.  Subclassing methods should
        call the superclass method.

        If a subclassing wait on is unable to save state because, for example,
        it depends on something that is only available at runtime then it
        should raise a :class:`Unsupported` error

        :param out_state: The bundle to save the state into
        """
        out_state[self.CLASS_NAME] = fullname(self)
        out_state[self.OUTCOME] = self._outcome

    def wait(self, timeout=None):
        """
        Block until this wait on to completes.  If a timeout is supplied it is
        interpreted to be a float in second (or fractions thereof).  If the
        timeout is reached without the wait on being done this method will
        return False.

        :param timeout: An optional timeout after which this method will
            return with the value False.
        :type timeout: float
        :raise: :class:`Interrupted` if :func:`interrupt` is called before the
            wait on is done
        :return: True if the wait on has completed, False otherwise.
        """
        # TODO: Add check that this is not called from multiple threads simultaneously
        with self._interrupt_lock:
            if self.is_done():
                return True
            # Going to have to wait
            self._waiting.clear()

        if not self._waiting.wait(timeout):
            # The threading Event returns False if it timed out
            return False
        elif self.is_done():
            return True
        else:
            # Must have been interrupted
            raise Interrupted()

    def interrupt(self):
        with self._interrupt_lock:
            self._waiting.set()

    @protected
    def init(self, *args, **kwargs):
        """
        This should be used as the constructor rather than __init__ so that
        wait ons can be created either by passing a saved instance state
        or the expected construction parameters.

        :param args: Any positional arguments
        :param kwargs: Any keyword arguments
        """
        self.__super_called = True

    @protected
    def load_instance_state(self, bundle):
        """
        Load the state of a wait on from a saved instance state.  All
        subclasses implementing this should call the superclass method.

        :param bundle: :class:`Bundle` The save instance state
        """
        outcome = bundle[self.OUTCOME]
        if outcome is not None:
            self.done(outcome[0], outcome[1])
        self.__super_called = True

    @protected
    def done(self, success=True, msg=None):
        """
        Implementing classes should call this when they are done waiting.  As
        well as indicating success or failure they can provide an optional
        outcome message.

        :param success: True if finished waiting successfully, False otherwise.
        :type success: bool
        :param msg: An (optional) message
        :type msg: str
        """
        assert self._outcome is None, "Cannot call done more than once"

        with self._interrupt_lock:
            self._outcome = success, msg
            self._waiting.set()


class Unsavable(object):
    """
    A mixin used to make a wait on unable to be saved or loaded
    """
    @override
    def save_instance_state(self, out_state):
        raise Unsupported("This WaitOn cannot be saved")

    @override
    def load_instance_state(self, bundle):
        raise Unsupported("This WaitOn cannot be loaded")