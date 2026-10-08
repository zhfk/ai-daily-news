import importlib.util
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo
from pathlib import Path
spec = importlib.util.spec_from_file_location('generate', Path(__file__).parents[1] / 'scripts/generate.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

class CollectionTests(unittest.TestCase):
    def test_publication_window_and_page_confirmation(self):
        now = datetime(2026, 10, 8, 7, tzinfo=ZoneInfo('Asia/Shanghai'))
        recent = (now - timedelta(hours=1)).isoformat()
        old = (now - timedelta(days=2)).isoformat()
        feed = f'''<rss version="2.0"><channel><title>Test</title>
        <item><title>AI model release</title><link>https://example.com/new</link><pubDate>{recent}</pubDate></item>
        <item><title>AI old model</title><link>https://example.com/old</link><pubDate>{old}</pubDate></item>
        <item><title>AI updated only</title><link>https://example.com/updated</link></item>
        <item><title>AI recycled</title><link>https://example.com/recycled</link><pubDate>{recent}</pubDate></item>
        </channel></rss>'''.encode()
        def fetch(url):
            if url.endswith('/feed'): return feed, url
            published = old if url.endswith('/recycled') else recent
            return f'<meta property="article:published_time" content="{published}"><meta name="description" content="Original model summary">'.encode(), url
        with patch.object(g, 'fetch', fetch):
            items, status = g.collect(('Test', 'https://example.com/feed', True), now)
        self.assertEqual(status['status'], 'ok')
        self.assertEqual([x['title'] for x in items], ['AI model release'])
    def test_network_failure_is_reported(self):
        with patch.object(g, 'fetch', side_effect=OSError('blocked')):
            items, status = g.collect(g.FEEDS[0], datetime.now(ZoneInfo('Asia/Shanghai')))
        self.assertEqual(items, [])
        self.assertEqual(status['status'], 'failed')
    def test_unsafe_html_is_removed_and_images_remain(self):
        output = g.render('<div class="image-group"><figure><img src="https://example.com/a.png" onerror="alert(1)"></figure></div>')
        self.assertIn('display:flex', output)
        self.assertIn('<figure>', output)
        self.assertNotIn('onerror', output)
    def test_unknown_timezone_is_not_assumed(self):
        self.assertIsNone(g.date_value('2026-10-08T07:00:00'))
        self.assertIsNone(g.date_value('not a date'))

if __name__ == '__main__': unittest.main()
