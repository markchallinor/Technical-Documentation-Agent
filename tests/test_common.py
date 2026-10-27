import unittest

from helpers import ROOT  # noqa: F401  (sets sys.path)
from docs_agent_common import path_matches


class GlobTests(unittest.TestCase):
    def test_double_star_matches_any_depth(self):
        self.assertTrue(path_matches("app/migrations/0001.py", ["app/migrations/**"]))
        self.assertTrue(path_matches("a/b/c/README.md", ["**/README*"]))
        self.assertTrue(path_matches("README.md", ["**/README*"]))

    def test_single_star_stays_in_one_directory(self):
        self.assertTrue(path_matches("src/app.py", ["src/*.py"]))
        self.assertFalse(path_matches("src/sub/app.py", ["src/*.py"]))

    def test_pattern_without_slash_matches_basename(self):
        self.assertTrue(path_matches("deep/dir/Dockerfile", ["Dockerfile"]))

    def test_requirements_is_not_excluded_as_documentation(self):
        from docs_agent_common import DEFAULT_CONFIG
        self.assertFalse(path_matches("requirements.txt", DEFAULT_CONFIG["evidence_exclude"]))
        self.assertTrue(path_matches("docs/old.md", DEFAULT_CONFIG["evidence_exclude"]))


if __name__ == "__main__":
    unittest.main()
