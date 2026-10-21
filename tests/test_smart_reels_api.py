"""API integration: Smart Reels accepts one long clip plus optional music.

Gemini is mocked: this tests the complete HTTP/render queue/FFmpeg plumbing
without spending model credits or uploading user footage.
"""
import json
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from refeditor.web import create_app


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class SmartReelsAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = tempfile.TemporaryDirectory()
        folder = Path(cls.data.name)
        cls.video = folder / "source.mp4"
        cls.music = folder / "music.mp3"
        subprocess.run([
            "ffmpeg","-y","-v","error","-f","lavfi","-i",
            "color=c=blue:s=120x90:r=12:d=16","-f","lavfi","-i",
            "sine=frequency=440:duration=16", "-c:v","libx264",
            "-c:a","aac", "-shortest",str(cls.video)
        ],capture_output=True,check=True,timeout=40)
        subprocess.run([
            "ffmpeg","-y","-v","error","-f","lavfi","-i",
            "sine=frequency=200:duration=20",
            "-c:a","libmp3lame",str(cls.music)
        ],capture_output=True,check=True,timeout=40)

    @classmethod
    def tearDownClass(cls):
        cls.data.cleanup()

    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(self.data_dir.name),
                                 headers={"X-Refeditor-Client":"web"})
        self.client.__enter__()
        self.pid = self.client.post("/api/projects").json()["id"]

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.data_dir.cleanup()

    def upload(self, role, path):
        response = self.client.post(f"/api/projects/{self.pid}/media",
                                    params={"role":role,"name":path.name},
                                    content=path.read_bytes())
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def test_music_upload_and_explicit_ai_consent(self):
        self.assertEqual(self.client.post(f"/api/projects/{self.pid}/renders",
            json={"editor_mode":"smart_reels","ai_semantic":True}).status_code,400)
        video = self.upload("source",self.video)
        music = self.upload("music",self.music)
        self.assertAlmostEqual(music["metadata"]["duration"],20,delta=1)
        self.assertEqual(self.client.get(f"/api/projects/{self.pid}").json()["music"]["id"], music["id"])
        response = self.client.post(f"/api/projects/{self.pid}/renders",
            json={"editor_mode":"smart_reels","ai_semantic":False,
                  "source_ids":[video["id"]]})
        self.assertEqual(response.status_code,400,response.text)
        response = self.client.post(f"/api/projects/{self.pid}/renders",
            json={"editor_mode":"reference","ai_semantic":False})
        self.assertEqual(response.status_code,400,response.text)

    def test_ai_reels_pipeline_without_reference_video(self):
        asset = self.upload("source",self.video)
        music = self.upload("music",self.music)
        def fake_proposal(source,target_seconds=60,brief="",model=None):
            return {"source":str(source),"clips":[{"start_s":.25,"end_s":2.25,
                    "duration_s":2.0,"reason":"test hook"}],
                    "model":"mock-gemini","story":"test",
                    "warnings":[]}
        def fake_renderer(plan,output,music=None,*,progress=None,resolution=(720,1280)):
            args=["ffmpeg","-y","-v","error","-f","lavfi","-i",
                  "color=c=red:s=120x216:r=12:d=2",
                  "-f","lavfi","-i","sine=frequency=440:duration=2",
                  "-c:v","libx264","-c:a","aac","-shortest",str(output)]
            subprocess.run(args,check=True,capture_output=True,timeout=40)
            return str(output)
        with patch("refeditor.smart_reels.propose_highlights",side_effect=fake_proposal), \
             patch("refeditor.smart_reels.render_reels",side_effect=fake_renderer):
            response = self.client.post(f"/api/projects/{self.pid}/renders",
                json={"editor_mode":"smart_reels","ai_semantic":True,
                      "reel_seconds":30,"brief":"choose fun",
                      "source_ids":[asset["id"]]})
            self.assertEqual(response.status_code,202,response.text)
            self.assertEqual(response.json()["settings"]["editor_mode"],"smart_reels")
            deadline=time.monotonic()+25
            while time.monotonic()<deadline:
                run=self.client.get(f"/api/projects/{self.pid}").json()["renders"][-1]
                if run["status"] not in ("queued","running"):
                    break
                time.sleep(.15)
            self.assertEqual(run["status"],"completed",run)
            self.assertEqual(self.client.get(run["video_url"]).status_code,200)
            project=self.client.get(run["project_url"]).json()
            self.assertEqual(project["story"],"test")
            self.assertEqual(project["music"],self.music.name)
            qa=self.client.get(run["qa_url"]).json()
            self.assertTrue(qa["audio_present"])
            self.assertEqual(qa["highlights"],1)


if __name__=="__main__":
    unittest.main()
