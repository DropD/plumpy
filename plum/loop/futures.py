import plum.util


class Future(plum.util.Future):
    def __init__(self, loop):
        super(Future, self).__init__()
        self._loop = loop
        self._callbacks = []

    def cancel(self):
        if super(Future, self).cancel():
            self._schedule_callbacks()
            return True
        else:
            return False

    def set_result(self, result):
        super(Future, self).set_result(result)
        self._schedule_callbacks()

    def set_exception(self, exception):
        super(Future, self).set_exception(exception)
        self._schedule_callbacks()

    def add_done_callback(self, fn):
        """
        Add a callback to be run when the future becomes done.
        
        :param fn: The callback function.
        """
        if self.done():
            self._loop.call_soon(fn, self)
        else:
            self._callbacks.append(fn)

    def remove_done_callback(self, fn):
        self._callbacks.remove(fn)

    def _schedule_callbacks(self):
        """
        Ask the event loop to call all callbacks.
        
        The callbacks are scheduled to be called as soon as possible.
        """
        callbacks = self._callbacks[:]
        if not callbacks:
            return

        self._callbacks[:] = []
        for callback in callbacks:
            self._loop.call_soon(callback, self)