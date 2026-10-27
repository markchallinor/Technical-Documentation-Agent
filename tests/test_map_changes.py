import io
import json
from contextlib import redirect_stdout

from helpers import RepoTestCase, git, make_repo, write_files
import map_changes

MAP = {"version": 1, "mappings": [
    {"globs": ["app/migrations/**", "app/models.py"], "sections": ["data.schema"]},
    {"globs": [".github/workflows/*.yml"], "sections": ["deployment.pipelines"]},
]}


class MapChangesTests(RepoTestCase):
    def test_affected_and_unmapped(self):
        sections, unmapped = map_changes.affected(
            ["app/models.py", "app/migrations/0003.py", "app/views.py", "docs/data.md", ".github/workflows/ci.yml"], MAP, "docs")
        self.assertEqual(sections, {
            "data.schema": ["app/models.py", "app/migrations/0003.py"],
            "deployment.pipelines": [".github/workflows/ci.yml"],
        })
        self.assertEqual(unmapped, ["app/views.py"])

    def test_since_commit(self):
        repo = make_repo(self.tmp / "repo", {"app/models.py": "a\n", "docs/_agent/docs-map.json": json.dumps(MAP)})
        base = git(repo, "rev-parse", "HEAD").strip()
        write_files(repo, {"app/models.py": "b\n", "app/new.py": "c\n"})
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "change")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = map_changes.main(["--since", base, "--repo", str(repo), "--json"])
        result = json.loads(buf.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(result["sections"], {"data.schema": ["app/models.py"]})
        self.assertEqual(result["unmapped_files"], ["app/new.py"])
