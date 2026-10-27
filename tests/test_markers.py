from helpers import RepoTestCase, make_repo, write_files
import markers

GOOD = """# Data
<!-- agent:begin section=data.schema commit=PENDING -->
Text
<!-- agent:end -->

Human notes.

<!-- agent:begin section=data.migrations commit=abc1234 agent=0.0.9 -->
More
<!-- agent:end -->

```markdown
<!-- agent:begin section=data.example commit=PENDING -->
<!-- agent:end -->
```
"""


class MarkerTests(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.repo = make_repo(self.tmp / "repo", {"app.py": "x = 1\n", "docs/data.md": GOOD})
        self.docs = self.repo / "docs"

    def test_scan_ignores_code_fences(self):
        sections, errors = markers.scan(self.docs)
        self.assertEqual(errors, [])
        self.assertEqual([s.section for s in sections], ["data.schema", "data.migrations"])

    def test_stamp_only_pending_by_default(self):
        self.assertEqual(markers.stamp(self.docs, "f" * 40, "0.1.0"), 1)
        sections, _ = markers.scan(self.docs)
        self.assertEqual(sections[0].commit, "f" * 40)
        self.assertEqual(sections[1].commit, "abc1234")
        text = (self.docs / "data.md").read_text()
        self.assertIn("Human notes.", text)
        self.assertIn("section=data.example commit=PENDING", text)  # fenced example untouched

    def test_stamp_all(self):
        self.assertEqual(markers.stamp(self.docs, "e" * 40, "0.1.0", restamp_all=True), 2)

    def test_errors(self):
        write_files(self.docs, {"bad.md": "<!-- agent:begin section=Bad commit=PENDING -->\n"
                                          "<!-- agent:begin section=data.schema commit=PENDING -->\n"
                                          "<!-- agent:end -->\n<!-- agent:end -->\n"})
        _, errors = markers.scan(self.docs)
        joined = "\n".join(errors)
        self.assertIn("should look like file.section", joined)
        self.assertIn("inside the section opened", joined)
        self.assertIn("without a matching agent:begin", joined)
        self.assertIn("duplicate section id 'data.schema'", joined)

    def test_cli_stamp_uses_head(self):
        rc = markers.main(["stamp", "--docs", str(self.docs), "--repo", str(self.repo)])
        self.assertEqual(rc, 0)
        sections, _ = markers.scan(self.docs)
        self.assertRegex(sections[0].commit, r"^[0-9a-f]{40}$")
