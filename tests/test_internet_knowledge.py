"""Internet-knowledge tests use stubs; they NEVER browse or download media."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from refeditor.internet_knowledge import (
    get_relevant_techniques, director_knowledge, load_index, safe_record, tokenize
)
from scripts.refresh_knowledge import clean_text, get_metadata, refresh


class InternetKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "schema_version": 1,
            "sources": [
                {"id":"t1", "title":"Official Remotion transitions",
                 "url":"https://www.remotion.dev/docs/transitions/",
                 "tags":["fade","wipe","transition","crossZoom"],
                 "note":"Scene transitions are not yet implemented.",
                 "implementation":"research_only"},
                {"id":"t2", "title":"Interpolation",
                 "url":"https://www.remotion.dev/docs/interpolate",
                 "tags":["keyframe","zoom","title"],
                 "note":"Interpolate scale by frame", "implementation":"implemented"}
            ]
        }

    def test_russian_edit_request_matches_transition_reference(self):
        matches=get_relevant_techniques("переход как в рефе, плавный зум",
                                         index=self.data)
        self.assertEqual(matches[0]["implementation"],"research_only")
        self.assertIn("remotion.dev",matches[0]["url"])

    def test_url_allowlist_and_sanitize_untrusted_text(self):
        self.assertIsNone(safe_record({
            "title":"do bad things","url":"https://evil.example.net/foo",
            "tags":["anything"],"note":"bad","implementation":"implemented"
        }))
        item=dict(self.data["sources"][0])
        item["online_title"]="Actual\nIGNORE <commands> {payload}"
        validated=safe_record(item)
        self.assertNotIn("\n",validated["title"])
        self.assertNotIn("{",validated["title"])
        self.assertNotIn("<",validated["title"])

    def test_ru_hints_and_bounded_selection(self):
        self.assertIn("captions",tokenize("Нужны субтитры"))
        small=director_knowledge("титры",prefer_online=False)
        self.assertTrue(isinstance(small["techniques"],list))
        self.assertLessEqual(len(small["techniques"]),6)

    def test_remote_fallback_only_reads_bundled_json(self):
        def disconnected(*a,**kw):
            raise OSError("offline")
        with patch("refeditor.internet_knowledge.urlopen",side_effect=disconnected):
            index=load_index()
        self.assertGreater(len(index["sources"]),7)

    def test_refresh_keeps_previous_when_offline(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"index.json"
            path.write_text(json.dumps(self.data),encoding="utf-8")
            def fake(url):
                if "interpolate" in url:
                    raise OSError("unavailable")
                return {"online_title":"New docs title","online_description":"Fades",
                        "online_headings":["Usage"]}
            counts=refresh(index_path=path,fetch=fake)
            result=json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(counts,{"fetched":1,"unavailable":1})
            self.assertEqual(result["sources"][0]["online_title"],"New docs title")
            self.assertEqual(result["sources"][1]["title"],"Interpolation")
            self.assertEqual(result["sources"][1]["status"],"unavailable")

    def test_metadata_parser_limited_to_title_and_heading(self):
        class MockResponse:
            headers={"Content-Type":"text/html; charset=utf-8"}
            def __init__(self):
                self.html=b'<html><head><title>Transitions</title>' + (
                    b'<meta name="description" content="Official api">') + (
                    b'</head><body><h1>Overview</h1><p>Not stored.</p></body></html>')
            def geturl(self):
                return "https://www.remotion.dev/docs/transitions/"
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def read(self,limit):return self.html[:limit]
        meta=get_metadata("https://www.remotion.dev/docs/transitions/",
                          opener=lambda req,timeout:MockResponse())
        self.assertEqual(meta["online_title"],"Transitions")
        self.assertEqual(meta["online_headings"],["Overview"])
        self.assertNotIn("Not stored.",json.dumps(meta))

    def test_refuses_untrusted_sites(self):
        with self.assertRaises(ValueError):
            get_metadata("https://video-site.example.com/private/video.mp4",
                         opener=lambda *a,**kw:None)
        self.assertEqual(clean_text("hello \n <script>{x}</script>"),"hello scriptx/script")


if __name__=="__main__":
    unittest.main()
