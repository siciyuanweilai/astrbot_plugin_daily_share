import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "core" / "content" / "evidence.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "daily_share_news_evidence", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class NewsEvidenceTextTests(unittest.TestCase):
    def setUp(self):
        self.strip_links = _load_module().strip_news_reference_links

    def test_removes_numbered_markdown_citation(self):
        text = "气温升至五十度。[[1]](https://example.com/source) 请注意防暑。"

        self.assertEqual(self.strip_links(text), "气温升至五十度。 请注意防暑。")

    def test_keeps_markdown_link_label_without_destination(self):
        text = "可参考[官方通报](https://example.com/notice)。"

        self.assertEqual(self.strip_links(text), "可参考官方通报。")

    def test_removes_plain_url_and_keeps_sentence_punctuation(self):
        text = "详情见 https://example.com/notice，后续等待通报。"

        self.assertEqual(self.strip_links(text), "详情见，后续等待通报。")


if __name__ == "__main__":
    unittest.main()
