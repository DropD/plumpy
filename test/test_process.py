from unittest import TestCase

import threading
from plum.persistence.bundle import Bundle
from plum.process import Process, ProcessState
from plum.process_monitor import MONITOR
from plum.test_utils import DummyProcess, ExceptionProcess, TwoCheckpointProcess, \
    DummyProcessWithOutput, TEST_PROCESSES, ProcessSaver
from plum.test_utils import ProcessListenerTester
from plum.util import override


class ForgetToCallParent(Process):
    @override
    def _run(self):
        pass

    @override
    def on_create(self, pid, inputs, saved_instance_state):
        pass

    @override
    def on_start(self):
        pass

    @override
    def on_run(self):
        pass

    @override
    def on_fail(self, exception):
        pass

    @override
    def on_finish(self):
        pass

    @override
    def on_stop(self):
        pass

    @override
    def on_destroy(self):
        pass


class TestProcess(TestCase):
    def setUp(self):
        self.events_tester = ProcessListenerTester()
        self.proc = DummyProcessWithOutput()
        self.proc.add_process_listener(self.events_tester)

    def tearDown(self):
        self.proc.remove_process_listener(self.events_tester)

    def test_spec(self):
        """
        Check that the references to specs are doing the right thing...
        """
        dp = DummyProcess.new_instance()
        self.assertIsNot(DummyProcess.spec(), Process.spec())
        self.assertIs(dp.spec(), DummyProcess.spec())

        class Proc(DummyProcess):
            pass

        self.assertIsNot(Proc.spec(), Process.spec())
        self.assertIsNot(Proc.spec(), DummyProcess.spec())
        p = Proc.new_instance()
        self.assertIs(p.spec(), Proc.spec())

    def test_on_run(self):
        self.proc.on_run()
        self.assertTrue(self.events_tester.run)

    def test_on_output_emitted(self):
        self.proc._run()
        self.assertTrue(self.events_tester.emitted)

    def test_on_finished(self):
        self.proc.on_finish()
        self.assertTrue(self.events_tester.finish)

    def test_dynamic_inputs(self):
        class NoDynamic(Process):
            def _run(self, **kwargs):
                pass

        class WithDynamic(Process):
            @classmethod
            def _define(cls, spec):
                super(WithDynamic, cls)._define(spec)

                spec.dynamic_input()

            def _run(self, **kwargs):
                pass

        with self.assertRaises(ValueError):
            NoDynamic.run(inputs={'a': 5})
        WithDynamic.run(inputs={'a': 5})

    def test_inputs(self):
        class Proc(Process):
            @classmethod
            def _define(cls, spec):
                super(Proc, cls)._define(spec)
                spec.input('a')

            def _run(self, a):
                pass

        p = Proc()

        # Check that we can't access inputs before creating
        with self.assertRaises(AttributeError):
            p.raw_inputs.a

        # Check that we can access the inputs after creating
        p._perform_create(0, {'a': 5})
        self.assertEqual(p.raw_inputs.a, 5)
        with self.assertRaises(AttributeError):
            p.raw_inputs.b

    def test_inputs_default(self):
        class Proc(DummyProcess):
            @classmethod
            def _define(cls, spec):
                super(Proc, cls)._define(spec)
                spec.input("input", default=5, required=False)

        # Supply a value
        p = Proc.new_instance(inputs={'input': 2})
        self.assertEqual(p.inputs['input'], 2)

        # Don't supply, use default
        p = Proc.new_instance()
        self.assertEqual(p.inputs['input'], 5)

    def test_run(self):
        p = DummyProcessWithOutput.new_instance()
        p.start()

        self.assertTrue(p.has_finished())
        self.assertEqual(p.state, ProcessState.DESTROYED)
        self.assertEqual(p.outputs, {'default': 5})

    def test_run_from_class(self):
        # Test running through class method
        results = DummyProcessWithOutput.run()
        self.assertEqual(results['default'], 5)

    def test_forget_to_call_parent(self):
        p = ForgetToCallParent()

        with self.assertRaises(AssertionError):
            p._perform_create(None, None, None)

        with self.assertRaises(AssertionError):
            p._perform_start()

        with self.assertRaises(AssertionError):
            p._perform_run()

        with self.assertRaises(AssertionError):
            p._perform_finish()

        with self.assertRaises(AssertionError):
            p._perform_stop()

        with self.assertRaises(AssertionError):
            p._perform_destroy()

    def test_pid(self):
        # Test auto generation of pid
        p = DummyProcessWithOutput.new_instance()
        self.assertIsNotNone(p.pid)

        # Test using integer as pid
        p = DummyProcessWithOutput.new_instance(pid=5)
        self.assertEquals(p.pid, 5)

        # Test using string as pid
        p = DummyProcessWithOutput.new_instance(pid='a')
        self.assertEquals(p.pid, 'a')

    def test_exception(self):
        proc = ExceptionProcess.new_instance()
        with self.assertRaises(BaseException):
            proc.start()
        self.assertEqual(proc.state, ProcessState.RUNNING)
        del proc

    def test_get_description(self):
        # Not all that much we can test for, but check if it's a string at
        # least
        for ProcClass in TEST_PROCESSES:
            desc = ProcClass.get_description()
            self.assertIsInstance(desc, str)

        # Dummy process should at least use the docstring as part of the
        # description and so it shouldn't be empty
        desc = DummyProcess.get_description()
        self.assertNotEqual(desc, "")

    def test_created_bundle(self):
        """
        Check that the bundle after just creating a process is as we expect
        :return:
        """
        proc = DummyProcessWithOutput.new_instance()
        b = Bundle()
        proc.save_instance_state(b)
        self.assertIsNone(b.get('inputs', None))
        self.assertEqual(len(b['outputs']), 0)

    def test_instance_state(self):
        proc = DummyProcessWithOutput.new_instance()

        saver = ProcessSaver(proc)
        proc.start()

        for info, outputs in zip(saver.snapshots, saver.outputs):
            state, bundle = info
            # Check that it is a copy
            self.assertIsNot(
                outputs, bundle[Process.BundleKeys.OUTPUTS.value].get_dict())
            # Check the contents are the same
            self.assertEqual(
                outputs, bundle[Process.BundleKeys.OUTPUTS.value].get_dict())

        self.assertIsNot(
            proc.outputs, saver.snapshots[-1][1][Process.BundleKeys.OUTPUTS.value])

    def test_saving_each_step(self):
        for ProcClass in TEST_PROCESSES:
            proc = ProcClass.new_instance()

            saver = ProcessSaver(proc)
            proc.start()

            self.assertEqual(proc.state, ProcessState.DESTROYED)
            self._check_process_against_snapshots(ProcClass, saver.snapshots)

    def test_fast_forward(self):
        import plum.knowledge_provider as knowledge_provider
        from plum.in_memory_database import InMemoryDatabase

        class FastForwarding(Process):
            @classmethod
            def _define(cls, spec):
                super(FastForwarding, cls)._define(spec)

                spec.input("a", required=True)
                spec.output("out")
                spec.deterministic()

            def __init__(self):
                super(FastForwarding, self).__init__()
                self.did_ff = False

            @override
            def fast_forward(self):
                super(FastForwarding, self).fast_forward()
                self.did_ff = True

            @override
            def _run(self, **kwargs):
                self.out("out", self.inputs.a)

        old_kp = knowledge_provider.get_global_provider()
        imdb = InMemoryDatabase(retain_inputs=True, retain_outputs=True)
        knowledge_provider.set_global_provider(imdb)

        for ProcClass in TEST_PROCESSES:
            # Try running first time
            try:
                outputs = ProcClass.run()
            except BaseException:
                pass
            else:
                # Check that calling again doesn't mess with the process
                outputs2 = ProcClass.run()
                self.assertEqual(outputs, outputs2)

        ff_proc = FastForwarding.new_instance(inputs={'a': 5})
        ff_proc.start()
        outs1 = ff_proc.outputs
        self.assertFalse(ff_proc.did_ff)

        # Check the same inputs again
        ff_proc = FastForwarding.new_instance(inputs={'a': 5})
        ff_proc.start()
        outs2 = ff_proc.outputs
        self.assertTrue(ff_proc.did_ff)
        self.assertEqual(outs1, outs2)

        # Now check different inputs
        ff_proc = FastForwarding.new_instance(inputs={'a': 6})
        ff_proc.start()
        outs3 = ff_proc.outputs
        self.assertFalse(ff_proc.did_ff)
        self.assertNotEqual(outs1, outs3)

        knowledge_provider.set_global_provider(old_kp)

    def test_saving_each_step_interleaved(self):
        for ProcClass in TEST_PROCESSES:
            proc = ProcClass.new_instance()
            ps = ProcessSaver(proc)
            try:
                proc.start()
            except BaseException:
                pass

            self._check_process_against_snapshots(ProcClass, ps.snapshots)

    def test_logging(self):
        class LoggerTester(Process):
            def _run(self, **kwargs):
                self.logger.info("Test")

        # TODO: Test giving a custom logger to see if it gets used
        p = LoggerTester.new_instance()
        p.run()

    def test_abort(self):
        # Can't abort a process that hasn't been started
        proc = DummyProcess.new_instance()
        self.assertTrue(proc.abort())
        proc.start()

        self.assertTrue(proc.aborted)
        self.assertEqual(proc.state, ProcessState.DESTROYED)

    def _check_process_against_snapshots(self, proc_class, snapshots):
        for i, info in zip(range(0, len(snapshots)), snapshots):
            loaded = proc_class.create_from(info[1])

            ps = ProcessSaver(loaded)
            # Run the process
            loaded.start()

            # Now check going backwards until running that the saved states match
            j = 1
            while True:
                if j >= min(len(snapshots), len(ps.snapshots)) or \
                                snapshots[-j][0] is ProcessState.STARTED:
                    break

                self.assertEqual(snapshots[-j], ps.snapshots[-j])
                j += 1

    def _check_process_against_snapshot(self, snapshot, proc):
        self.assertEqual(snapshot.state, proc.state)

        new_bundle = Bundle()
        proc.save_instance_state(new_bundle)
        self.assertEqual(snapshot.bundle, new_bundle,
                         "Bundle mismatch with process class {}\n"
                         "Snapshot:\n{}\n"
                         "Loaded:\n{}".format(
                             proc.__class__, snapshot.bundle, new_bundle))

        self.assertEqual(snapshot.outputs, proc.outputs,
                         "Outputs mismatch with process class {}\n"
                         "Snapshot:\n{}\n"
                         "Loaded:\n{}".format(
                             proc.__class__, snapshot.outputs, proc.outputs))
