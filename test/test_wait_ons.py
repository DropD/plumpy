from plum.loop.event_loop import BaseEventLoop
from plum.process import ProcessState
from plum.test_utils import WaitForSignalProcess, DummyProcess
from plum.wait_ons import WaitOnProcessState, run_until
from util import TestCase


class TestWaitOnProcessStateEvent(TestCase):
    def setUp(self):
        super(TestWaitOnProcessStateEvent, self).setUp()
        self.loop = BaseEventLoop()

    def test_already_in_state(self):
        p = self.loop.create_task(DummyProcess)
        wait_for = WaitOnProcessState(p, ProcessState.CREATED, self.loop)
        result = self.loop.run_until_complete(wait_for.future())
        self.assertEqual(result, WaitOnProcessState.STATE_REACHED)

    def test_state_messages(self):
        for state in (ProcessState.RUNNING, ProcessState.STOPPED):
            p = self.loop.create_task(DummyProcess)

            wait_for = WaitOnProcessState(p, state, self.loop)
            result = self.loop.run_until_complete(wait_for.future())
            self.assertEqual(result, WaitOnProcessState.STATE_REACHED)
            self.assertTrue(p.state, state)

    def test_waiting_state(self):
        p = self.loop.create_task(WaitForSignalProcess)

        wait_for = WaitOnProcessState(p, ProcessState.WAITING, self.loop)
        result = self.loop.run_until_complete(wait_for.future())

        self.assertEqual(result, WaitOnProcessState.STATE_REACHED)

    def test_wait_until(self):
        p = self.loop.create_task(WaitForSignalProcess)
        run_until(p, ProcessState.WAITING, self.loop)
