import io
import json
from contextlib import redirect_stdout

from helpers import RepoTestCase, make_repo
import check_citations


def run(*args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = check_citations.main(list(args))
    return rc, buf.getvalue()


class CitationTests(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.ws = self.tmp / "ws"
        make_repo(self.ws / "other", {"svc/api.py": "a\nb\nc\n"})
        self.repo = make_repo(self.ws / "repo", {
            "app/x.py": "1\n2\n3\n4\n",
            "docs/page.md": "<!-- agent:begin section=page.a commit=PENDING -->\n"
                            "Good ([app/x.py:2](../app/x.py#L2)) and range ([app/x.py:2-4](../app/x.py#L2-L4)).\n"
                            "> **Unknown – needs SME input:** Who owns it?\n"
                            "<!-- agent:end -->\n"
                            "<!-- agent:begin section=page.b commit=PENDING -->\nNo evidence here.\n<!-- agent:end -->\n"
                            "See [other page](other.md) and [site](https://www.gov.uk).\n",
            "docs/sub/deep.md": "Cross `other:svc/api.py:3` and nested ([x](../../app/x.py#L1)).\n",
        })
        self.docs = str(self.repo / "docs")

    def test_valid_citations_pass_and_counts(self):
        rc, out = run("--docs", self.docs, "--workspace", str(self.ws), "--json")
        result = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(result["broken_citations"], [])
        self.assertEqual(result["totals"]["citations"], 4)
        self.assertEqual(result["totals"]["unknown"], 1)
        self.assertEqual(result["sections_without_citations"], ["page.b"])

    def test_broken_line_missing_file_and_escape(self):
        (self.repo / "docs" / "bad.md").write_text(
            "[a](../app/x.py#L99) [b](../app/missing.py#L1) [c](../../other/svc/api.py#L1) `other:svc/api.py:9`\n")
        rc, out = run("--docs", self.docs, "--workspace", str(self.ws), "--json")
        problems = [b["problem"] for b in json.loads(out)["broken_citations"]]
        self.assertEqual(rc, 1)
        self.assertEqual(len(problems), 4)
        self.assertIn("file does not exist", problems)
        self.assertIn("points outside the repository", problems)
