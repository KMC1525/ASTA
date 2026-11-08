"""v0.14 — Studio: ordem das camadas na exportação (V2 sobre V1), igual à prévia da timeline."""
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asta.canvas.render import render_timeline  # noqa: E402
from asta.studio import schema as S  # noqa: E402
from tests.test_core import TmpCase  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def pixel(video: Path, x: int, y: int, at: float = 1.0):
    out = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(at), "-i", str(video), "-vf", f"crop=4:4:{x}:{y},format=rgb24,scale=1:1", "-frames:v", "1", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    return tuple(out[:3])


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg não instalado")
class LayerOrderTests(TmpCase):
    def setUp(self):
        super().setUp()
        for name, color in (("red", "red"), ("blue", "blue")):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s=320x180:d=3:r=24", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(self.tmp / f"{name}.mp4")], check=True)
        self.files = {k: {"path": self.tmp / f"{k}.mp4", "kind": "video", "duration": 3} for k in ("red", "blue")}

    def timeline(self):
        return S.normalize_timeline({"tracks": S.default_tracks(), "clips": [
            {"id": "a", "track": "t_v1", "asset": "red", "start": 0, "dur": 3, "scale": 1},    # V1: vídeo principal em tela cheia
            {"id": "b", "track": "t_v2", "asset": "blue", "start": 0, "dur": 3, "scale": 0.4},  # V2: janelinha no centro, por cima
        ]})

    def test_the_studio_export_stacks_V2_over_V1_like_the_preview(self):
        out = self.tmp / "studio.mp4"
        render_timeline(self.timeline(), 320, 180, 24, "#000000", lambda c: self.files[c["asset"]], out, top_first=True)
        r, g, b = pixel(out, 158, 88)   # centro: a janelinha azul da V2
        self.assertGreater(b, 200)
        self.assertLess(r, 60)
        r, g, b = pixel(out, 8, 8)      # canto: só a V1 vermelha
        self.assertGreater(r, 200)
        self.assertLess(b, 60)

    def test_the_canvas_editor_keeps_its_own_order_last_track_on_top(self):
        out = self.tmp / "canvas.mp4"
        tl = S.normalize_timeline({"tracks": [{"id": "v1", "kind": "video"}, {"id": "v2", "kind": "video"}], "clips": [
            {"id": "a", "track": "v1", "asset": "red", "start": 0, "dur": 3}, {"id": "b", "track": "v2", "asset": "blue", "start": 0, "dur": 3, "scale": 0.4}]})
        render_timeline(tl, 320, 180, 24, "#000000", lambda c: self.files[c["asset"]], out)
        self.assertGreater(pixel(out, 158, 88)[2], 200)   # v2 (última da lista) por cima, como sempre foi no Canvas


if __name__ == "__main__":
    unittest.main()
