import unittest
from app import normalize_url, selector

class InputTests(unittest.TestCase):
    def test_link_variants(self):
        expected = 'https://www.youtube.com/watch?v=dMFNkCkOOrU'
        for url in ('https://youtu.be/dMFNkCkOOrU?t=10', expected + '&list=example',
                    'https://www.youtube.com/shorts/dMFNkCkOOrU',
                    'https://www.youtube.com/live/dMFNkCkOOrU'):
            self.assertEqual(normalize_url(url), expected)

    def test_invalid_links(self):
        for url in ('file:///test', 'https://youtube.com.evil.test/watch?v=dMFNkCkOOrU',
                    'https://youtube.com/playlist?list=x', 'https://youtu.be/short'):
            with self.assertRaises(ValueError):
                normalize_url(url)

    def test_selection_keeps_audio_and_caps_video(self):
        self.assertEqual(selector(), 'bv+ba/b')
        self.assertEqual(selector(1080), 'bv[height<=1080]+ba/b[height<=1080]')

if __name__ == '__main__':
    unittest.main()
