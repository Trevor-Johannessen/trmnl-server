"""A source that goes down must degrade its screen, never stall the render:
the device is waiting on the poll that triggered it."""
import asyncio
import time
import unittest

from trmnl_server.config import Config
from trmnl_server.sources import Source


class Flaky(Source):
    name = "flaky"
    ttl_s = 100.0

    def __init__(self, config):
        super().__init__(config)
        self.calls = 0
        self.fail = False
        self.hang = False

    async def fetch(self):
        self.calls += 1
        if self.hang:
            await asyncio.sleep(10)
        if self.fail:
            raise RuntimeError("upstream is down")
        return {"n": self.calls}


class Degradation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = Config(source_timeout_s=0.05)
        self.source = Flaky(self.config)

    async def test_good_result_is_cached_for_its_ttl(self):
        first = await self.source.get()
        second = await self.source.get()
        self.assertTrue(first.ok and second.ok)
        self.assertEqual(self.source.calls, 1)
        self.assertEqual(second.data, {"n": 1})

    def expire(self):
        """Age the cache past its TTL without aging it past stale_after_s."""
        self.source._at = time.time() - self.source.ttl_s - 1

    async def test_failure_falls_back_to_last_good_marked_stale(self):
        await self.source.get()
        self.expire()
        self.source.fail = True
        reading = await self.source.get()
        self.assertTrue(reading.ok)
        self.assertTrue(reading.stale)
        self.assertEqual(reading.data, {"n": 1})
        self.assertEqual(reading.error, "RuntimeError")

    async def test_failure_with_no_history_is_not_ok(self):
        self.source.fail = True
        reading = await self.source.get()
        self.assertFalse(reading.ok)
        self.assertEqual(reading.data, {})

    async def test_a_hang_is_bounded_by_the_timeout(self):
        self.source.hang = True
        loop = asyncio.get_running_loop()
        started = loop.time()
        reading = await self.source.get()
        self.assertLess(loop.time() - started, 1.0)
        self.assertFalse(reading.ok)
        self.assertEqual(reading.error, "timeout")

    async def test_a_last_good_answer_expires_eventually(self):
        """Past stale_after_s the cached answer is not worth showing at all."""
        await self.source.get()
        self.source._at = time.time() - Flaky.stale_after_s - 1
        self.source.fail = True
        self.assertFalse((await self.source.get()).ok)
