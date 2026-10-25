import unittest
from PIL import Image
from gradient_theme import number_color
from render import checked_layout, RenderError


class GradientTests(unittest.TestCase):
    def test_layout_preserves_theme_and_individual_position(self):
        data = dict(position="top", title_size=72, body_size=34, text_color="#24384A", panel=.82,
                    theme="ivory-gradient", image_offset_y=105)
        self.assertEqual(checked_layout(data), data)
        for invalid in ("105", True, 301, -201):
            with self.assertRaises(RenderError):
                checked_layout(dict(data, image_offset_y=invalid))

    def test_number_inverts_only_when_background_needs_it(self):
        box = (0, 0, 60, 60)
        dark = number_color(Image.new("RGB", (60, 60), "#142334"), box)
        light = number_color(Image.new("RGB", (60, 60), "#f7f3e8"), box)
        self.assertEqual(dark[0], (255, 255, 255))
        self.assertEqual(light[0], (36, 56, 74))
        self.assertFalse(dark[1]["outline"])
        self.assertFalse(light[1]["outline"])
