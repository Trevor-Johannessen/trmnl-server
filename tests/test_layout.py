import unittest

from trmnl_server.config import HEIGHT, WIDTH
from trmnl_server.layout import Window, Zone, document, esc


class Leaf(Window):
    def __init__(self, text):
        self.text = text

    def render(self):
        return f"<p>{esc(self.text)}</p>"


class Zones(unittest.TestCase):
    def test_leaf_renders_its_window(self):
        self.assertIn("<p>hello</p>", Zone(window=Leaf("hello")).render())

    def test_split_renders_both_children(self):
        html = Zone(direction="row", percentage=40,
                    zone_one=Zone(window=Leaf("L")),
                    zone_two=Zone(window=Leaf("R"))).render()
        self.assertIn("<p>L</p>", html)
        self.assertIn("<p>R</p>", html)
        self.assertIn("flex-direction:row", html)

    def test_window_and_subzones_are_mutually_exclusive(self):
        with self.assertRaises(ValueError):
            Zone(window=Leaf("x"), direction="row", percentage=50)

    def test_direction_and_percentage_come_as_a_pair(self):
        with self.assertRaises(ValueError):
            Zone(direction="row")
        with self.assertRaises(ValueError):
            Zone(percentage=50)

    def test_bad_direction_and_percentage_are_rejected(self):
        with self.assertRaises(ValueError):
            Zone(direction="diagonal", percentage=50)
        for bad in (0, 100, -10, 150):
            with self.assertRaises(ValueError):
                Zone(direction="row", percentage=bad)

    def test_base_window_refuses_to_render(self):
        with self.assertRaises(NotImplementedError):
            Window().render()


class Document(unittest.TestCase):
    def test_canvas_is_pinned_to_the_panel(self):
        html = document("<p>x</p>", "body{}")
        self.assertIn(f"width:{WIDTH}px", html)
        self.assertIn(f"height:{HEIGHT}px", html)

    def test_escaping(self):
        self.assertEqual(esc('<a href="x">'), "&lt;a href=&quot;x&quot;&gt;")
        self.assertEqual(esc(None), "")
