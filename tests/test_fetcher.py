"""Fetching a content pack without freezing the window.

A texture pack is 450 MB. Fetching it on the frame loop's thread stops the
window dead for minutes — no redraw, no cancel, and on most desktops an
eventual "this application is not responding".

So the work happens on a worker and the frame loop *polls*: `poll()` is called
once a frame, returns what has changed, and is the only place anything from the
worker is read. That is the whole of the thread safety, and it is why none of
this needs a lock in the caller.
"""

from __future__ import annotations

import threading
import time

import pytest

from twig_bb import fetcher
from twig_bb.assetpack import AssetPack


def pack(**named):
    values = dict(key='sample', title='A sample pack',
                  url='https://example.com/sample.zip', directory='sample',
                  archive='zip', approximate_bytes=1000,
                  copyright='Nobody, public domain', marker='')
    values.update(named)
    return AssetPack(**values)


def settle(job, timeout=5.0):
    """Poll until the job finishes, as a frame loop would, and return it."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job.poll()
        if job.finished:
            return job
        time.sleep(0.005)
    raise AssertionError('the job never finished: %r' % (job.state,))


class TestAJobThatSucceeds:

    def fetch(self, **named):
        seen = []

        def work(pack, progress, cancel):
            for done in (250, 500, 1000):
                progress(done, 1000)
                seen.append(done)
            return '/content/sample'

        job = fetcher.FetchJob([pack()], fetch=work, **named)
        job.start()
        return settle(job), seen

    def test_it_finishes(self):
        job, _ = self.fetch()
        assert job.finished
        assert job.failed is None

    def test_the_roots_it_unpacked_come_back(self):
        job, _ = self.fetch()
        assert job.roots == ['/content/sample']

    def test_progress_reaches_the_frame_loop(self):
        job, _ = self.fetch()
        assert job.fraction == pytest.approx(1.0)

    def test_it_says_what_it_is_doing(self):
        job, _ = self.fetch()
        assert 'sample' in job.state.lower() or job.state

    def test_nothing_is_read_from_the_worker_except_in_poll(self):
        """The rule that makes the caller lock-free.

        A job that has run to completion but has not been polled still reports
        itself unfinished, because `finished` is what the last poll saw.
        """
        job = fetcher.FetchJob([pack()], fetch=lambda p, prog, can: '/content')
        job.start()
        job._thread.join(5.0)
        assert not job.finished
        job.poll()
        assert job.finished


class TestSeveralPacks:

    def test_every_pack_is_fetched(self):
        done = []
        job = fetcher.FetchJob(
            [pack(key='a', directory='a'), pack(key='b', directory='b')],
            fetch=lambda p, prog, can: done.append(p.key) or ('/content/' + p.key))
        job.start()
        settle(job)
        assert done == ['a', 'b']
        assert job.roots == ['/content/a', '/content/b']

    def test_progress_spans_the_whole_set_rather_than_each_pack(self):
        """One bar for the job, not a bar that restarts per pack.

        A user consenting to three packs agreed to one download of their total
        size; a bar that fills and resets three times reads as three failures.
        So the small pack finishing has to read as a quarter done, not as
        finished — and the second pack is held until that has been observed,
        because a race would let the whole job complete before the first poll.
        """
        first_done = threading.Event()
        release = threading.Event()

        def work(pack, progress, cancel):
            # The second pack waits *before* reporting anything, so the first
            # pack's quarter is still what the job shows when it is polled.
            if pack.key == 'b':
                assert release.wait(5.0)
            progress(pack.approximate_bytes, pack.approximate_bytes)
            if pack.key == 'a':
                first_done.set()
            return '/content/' + pack.key

        job = fetcher.FetchJob(
            [pack(key='a', directory='a', approximate_bytes=1000),
             pack(key='b', directory='b', approximate_bytes=3000)],
            fetch=work)
        job.start()
        assert first_done.wait(5.0)
        job.poll()
        assert job.fraction == pytest.approx(0.25, abs=0.01)
        release.set()
        settle(job)
        assert job.fraction == pytest.approx(1.0)


class TestAJobThatFails:

    def test_a_failure_is_reported_rather_than_raised(self):
        """A frame loop cannot catch an exception raised on another thread."""
        def broken(pack, progress, cancel):
            raise IOError('the network went away')

        job = fetcher.FetchJob([pack()], fetch=broken)
        job.start()
        settle(job)
        assert job.failed is not None
        assert 'network' in str(job.failed)

    def test_a_failure_partway_keeps_what_did_arrive(self):
        """Two of three packs is better than nothing, and is usable."""
        def half(pack, progress, cancel):
            if pack.key == 'b':
                raise IOError('gone')
            return '/content/' + pack.key

        job = fetcher.FetchJob([pack(key='a', directory='a'),
                                pack(key='b', directory='b')], fetch=half)
        job.start()
        settle(job)
        assert job.roots == ['/content/a']
        assert job.failed is not None


class TestCancelling:

    def test_a_cancelled_job_stops(self):
        started = threading.Event()

        def slow(pack, progress, cancel):
            started.set()
            while not cancel():
                time.sleep(0.005)
            raise fetcher.Cancelled()

        job = fetcher.FetchJob([pack()], fetch=slow)
        job.start()
        assert started.wait(5.0)
        job.cancel()
        settle(job)
        assert job.cancelled

    def test_a_cancelled_job_is_not_a_failure(self):
        """Nothing went wrong; the user changed their mind."""
        def slow(pack, progress, cancel):
            while not cancel():
                time.sleep(0.005)
            raise fetcher.Cancelled()

        job = fetcher.FetchJob([pack()], fetch=slow)
        job.start()
        job.cancel()
        settle(job)
        assert job.failed is None

    def test_cancelling_stops_the_packs_that_have_not_started(self):
        touched = []

        def work(pack, progress, cancel):
            touched.append(pack.key)
            job.cancel()
            raise fetcher.Cancelled()

        job = fetcher.FetchJob([pack(key='a', directory='a'),
                                pack(key='b', directory='b')], fetch=work)
        job.start()
        settle(job)
        assert touched == ['a']

    def test_cancelling_a_job_that_never_started_is_harmless(self):
        job = fetcher.FetchJob([pack()], fetch=lambda p, prog, can: '/c')
        job.cancel()
        assert job.cancelled


class TestReportingItToAUser:

    def test_a_fraction_with_no_work_is_complete_rather_than_undefined(self):
        job = fetcher.FetchJob([], fetch=lambda p, prog, can: '/c')
        job.start()
        settle(job)
        assert job.fraction == 1.0

    def test_the_total_size_is_what_the_user_consented_to(self):
        job = fetcher.FetchJob([pack(approximate_bytes=1_000_000),
                                pack(key='b', directory='b',
                                     approximate_bytes=3_000_000)],
                               fetch=lambda p, prog, can: '/c')
        assert job.total_bytes == 4_000_000

    def test_the_size_reads_in_megabytes(self):
        job = fetcher.FetchJob([pack(approximate_bytes=41_711_739)],
                               fetch=lambda p, prog, can: '/c')
        assert job.human_total() == '42 MB'
