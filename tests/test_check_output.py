import io
from contextlib import redirect_stdout

from helpers import RepoTestCase, make_repo, write_files
import check_output

STAMPED = "<!-- agent:begin section=page.a commit=abc1234 agent=0.1.0 -->\n{body}\n<!-- agent:end -->\n"


def run(repo):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = check_output.main(["--repo", str(repo)])
    return rc, buf.getvalue()


class CheckOutputTests(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.repo = make_repo(self.tmp / "repo", {"app.py": "x = 1\n", "docs/page.md": STAMPED.format(body="ok")})
        (self.repo / ".docs-agent").mkdir()
        (self.repo / ".docs-agent" / "facts.json").write_text("{}")

    def write_doc(self, body):
        write_files(self.repo, {"docs/page.md": STAMPED.format(body=body)})

    def test_clean_docs_pass(self):
        self.write_doc("Uses `DATABASE_URL`. Contact user@example.com. Port 8000.")
        rc, out = run(self.repo)
        self.assertEqual(rc, 0, out)
        self.assertIn("PASSED", out)

    def test_change_outside_docs_fails(self):
        write_files(self.repo, {"app.py": "x = 2\n"})
        rc, out = run(self.repo)
        self.assertEqual(rc, 1)
        self.assertIn("app.py: changed outside docs/", out)

    def test_secrets_detected_without_printing_them(self):
        key = "AKIA" + "ABCDEFGHIJKLMNOP"
        self.write_doc(f'aws {key}\npassword = "hunter2hunter2"\npostgres://admin:pa55word@db/x')
        rc, out = run(self.repo)
        self.assertEqual(rc, 1)
        self.assertIn("aws-access-key-id", out)
        self.assertIn("assigned-secret", out)
        self.assertIn("url-with-credentials", out)
        self.assertNotIn(key, out)
        self.assertNotIn("hunter2", out)

    def test_placeholders_are_not_secrets(self):
        self.write_doc('password = "<your-password-here>"\npostgres://user:<password>@host/db')
        rc, out = run(self.repo)
        self.assertEqual(rc, 0, out)

    def test_personal_data_detected(self):
        self.write_doc("jane.doe@company.co.uk\nAB 12 34 56 C\n07700 900123\n4111 1111 1111 1111")
        rc, out = run(self.repo)
        self.assertEqual(rc, 1)
        for text in ("email address", "National Insurance", "UK phone", "payment card"):
            self.assertIn(text, out)

    def test_unstamped_marker_fails_and_guidance_warns(self):
        write_files(self.repo, {"docs/new.md": "<!-- agent:begin section=new.a commit=PENDING -->\n"
                                               "<!-- guide: fill me -->\n<!-- agent:end -->\n"})
        rc, out = run(self.repo)
        self.assertEqual(rc, 1)
        self.assertIn("not stamped", out)
        self.assertIn("guidance comment", out)

    def test_ip_and_internal_host_warn_only(self):
        self.write_doc("Talks to 10.0.0.12 and db.svc.cluster.local")
        rc, out = run(self.repo)
        self.assertEqual(rc, 0, out)
        self.assertIn("IP address", out)
        self.assertIn("internal-looking hostname", out)
