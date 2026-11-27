from observateur_actif.research import ResearchError, parse_feed, load_feed_config, save_leads


RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><item>
<title>Mystery discovered</title><link>https://example.org/story</link>
<description>A report &amp; details</description><pubDate>Thu, 27 Nov 2026 01:00:00 GMT</pubDate>
</item></channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<title>Ancient site report</title><link href="https://example.org/atom" rel="alternate"/>
<summary>New research</summary><updated>2026-11-27T01:00:00Z</updated>
</entry></feed>"""


def test_parse_rss_marks_items_unverified():
    items = parse_feed(RSS, feed_url="https://example.org/rss", publisher="Example")
    assert len(items) == 1
    assert items[0]["title"] == "Mystery discovered"
    assert items[0]["editorial_status"] == "lead_unverified"
    assert items[0]["published_at"].startswith("2026-11-27")


def test_parse_atom_feed():
    items = parse_feed(ATOM, feed_url="https://example.org/atom.xml", publisher="Example")
    assert items[0]["url"] == "https://example.org/atom"
    assert items[0]["summary"] == "New research"


def test_invalid_xml_raises():
    import pytest
    with pytest.raises(ResearchError, match="XML invalide"):
        parse_feed(b"<not-closed>", feed_url="https://example.org/rss", publisher="Example")


def test_feed_config_and_save(tmp_path):
    import json
    config = tmp_path / "feeds.json"
    config.write_text(json.dumps([{"publisher": "Example", "url": "https://example.org/rss"}]))
    assert load_feed_config(config)[0]["publisher"] == "Example"
    output = save_leads([{"title": "A lead"}], tmp_path / "out" / "leads.json")
    assert json.loads(output.read_text())[0]["title"] == "A lead"


def test_feed_config_must_be_a_list(tmp_path):
    import pytest
    config = tmp_path / "feeds.json"
    config.write_text('{"publisher":"Example"}')
    with pytest.raises(ResearchError, match="liste JSON"):
        load_feed_config(config)


def test_collect_feeds_skips_one_unavailable_publisher():
    from unittest.mock import Mock, patch
    import urllib.error
    import pytest
    from observateur_actif.research import collect_feeds

    response = Mock()
    response.status = 200
    response.read.return_value = RSS
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    feeds = [
        {"publisher": "Broken", "url": "https://broken.example/rss"},
        {"publisher": "Working", "url": "https://working.example/rss"},
    ]
    with patch("observateur_actif.research.urllib.request.urlopen",
               side_effect=[urllib.error.URLError("404"), response]):
        with pytest.warns(RuntimeWarning, match="Flux ignoré"):
            items = collect_feeds(feeds)
    assert len(items) == 1
    assert items[0]["publisher"] == "Working"


def test_collect_feeds_fails_if_every_publisher_is_unavailable():
    from unittest.mock import patch
    import urllib.error
    import pytest
    from observateur_actif.research import collect_feeds

    with patch("observateur_actif.research.urllib.request.urlopen",
               side_effect=urllib.error.URLError("offline")):
        with pytest.warns(RuntimeWarning):
            with pytest.raises(ResearchError, match="Aucun flux RSS exploitable"):
                collect_feeds([{"publisher": "Offline", "url": "https://offline.example/rss"}])
