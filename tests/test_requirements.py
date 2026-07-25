import unittest
from pathlib import Path


class RequirementsTests(unittest.TestCase):
    def test_offline_wordcloud_dependency_is_pinned(self):
        requirements = Path("requirements.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("pyecharts==2.0.6", requirements)


if __name__ == "__main__":
    unittest.main()
