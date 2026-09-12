"""The content-hash token is what lets the device skip a download, so its
stability is load-bearing: a token that changed on every render would mean an
e-ink refresh every minute, forever."""
import tempfile
import unittest

from trmnl_server.render import ImageStore


class Store(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.store = ImageStore(self.dir.name, keep=3)

    def test_same_bytes_give_the_same_token(self):
        self.assertEqual(self.store.put(b"same"), self.store.put(b"same"))

    def test_different_bytes_give_different_tokens(self):
        self.assertNotEqual(self.store.put(b"one"), self.store.put(b"two"))

    def test_stored_image_is_retrievable(self):
        token = self.store.put(b"payload")
        self.assertTrue(self.store.has(token))
        with open(self.store.path(token), "rb") as handle:
            self.assertEqual(handle.read(), b"payload")

    def test_pruning_keeps_the_newest(self):
        tokens = [self.store.put(f"image-{i}".encode()) for i in range(6)]
        kept = [t for t in tokens if self.store.has(t)]
        self.assertEqual(len(kept), 3)
        self.assertEqual(kept, tokens[-3:])

    def test_unknown_token_is_absent(self):
        self.assertFalse(self.store.has("deadbeef"))
