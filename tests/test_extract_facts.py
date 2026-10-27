import json

from helpers import RepoTestCase, make_repo
from docs_agent_common import load_config
import extract_facts

SECRET = "s3cr3t-value-that-must-never-appear"

FILES = {
    "app/settings.py": 'import os\nSECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")\nDEBUG = os.getenv("DEBUG", "false")\n'
                       'NOTIFY = "https://api.notifications.service.gov.uk"\n# TODO: tidy up\n',
    "app/urls.py": 'from django.urls import path\nurlpatterns = [\n    path("contact/", views.contact),\n]\n',
    "app/models.py": "from django.db import models\nclass Enquiry(models.Model):\n    pass\n",
    "app/migrations/0001_initial.py": "",
    "app/migrations/0002_add_field.py": "",
    "web/server.js": "const app = express();\napp.get('/health', h);\nconst k = process.env.API_KEY;\n",
    "api/main.py": "@app.route('/items', methods=['GET', 'POST'])\ndef items(): pass\n",
    "requirements.txt": "Django==4.2.1\nredis>=4  # cache\n",
    "package.json": json.dumps({"name": "web", "dependencies": {"express": "^4.18.0"}, "scripts": {"test": "jest"}}),
    "Dockerfile": "FROM python:3.11-slim\nENV PORT=8000\nEXPOSE 8000\nCMD [\"gunicorn\"]\n",
    ".github/workflows/ci.yml": "name: CI\non:\n  push:\n  pull_request:\njobs:\n  test:\n    runs-on: ubuntu-latest\n",
    "main.tf": 'resource "aws_s3_bucket" "uploads" {\n}\n',
    ".env.example": "DJANGO_SECRET_KEY=\nDEBUG=true\n",
    ".env": f"DJANGO_SECRET_KEY={SECRET}\n",
    "docs/old-guide.md": "# Out of date\nSet REDIS_URL via os.environ.get(\"OLD_ONLY_IN_DOCS\")\n",
    "docs/openapi.yaml": "openapi: 3.0.0\ninfo:\n  title: Enquiries API\n",
    "README.md": "# Old readme\n",
    "tests/test_views.py": "app.get('/only-in-tests')\nos.environ.get(\"ONLY_IN_TESTS\")\n",
    "deploy.sh": "TARGET=prod\nfor ITEM in a b; do echo $ITEM; done\necho \"$TARGET $DEPLOY_TOKEN ${BASH_SOURCE[0]}\"\n",
}


class ExtractFactsTests(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.repo = make_repo(self.tmp / "repo", FILES)
        self.facts = extract_facts.extract(self.repo, load_config(self.repo))
        self.raw = json.dumps(self.facts, default=sorted)

    def test_secret_values_never_extracted(self):
        self.assertNotIn(SECRET, self.raw)
        self.assertIn(".env", self.facts["sensitive_files"]["paths"])
        self.assertNotIn(".env.example", self.facts["sensitive_files"]["paths"])

    def test_no_email_addresses_in_facts(self):
        self.assertNotIn("tester@example.com", self.raw)

    def test_environment_variable_names_and_locations(self):
        env = {e["name"]: e for e in self.facts["environment_variables"]["items"]}
        self.assertIn("DJANGO_SECRET_KEY", env)
        self.assertIn("app/settings.py:2", env["DJANGO_SECRET_KEY"]["locations"])
        self.assertTrue(env["DJANGO_SECRET_KEY"]["in_example_file"])
        self.assertIn("API_KEY", env)
        self.assertIn("PORT", env)
        self.assertEqual(env["DEBUG"]["sources"], ["example-env-file", "python"])
        self.assertIn("DEPLOY_TOKEN", env)
        for local in ("TARGET", "ITEM", "BASH_SOURCE", "ONLY_IN_TESTS"):
            self.assertNotIn(local, env)

    def test_existing_docs_are_not_evidence(self):
        names = {e["name"] for e in self.facts["environment_variables"]["items"]}
        self.assertNotIn("OLD_ONLY_IN_DOCS", names)
        existing = self.facts["existing_documentation"]
        self.assertTrue(existing["docs_dir_exists"])
        self.assertIn("docs/openapi.yaml", existing["non_documentation_files_in_docs_dir"])
        self.assertIn("README.md", existing["other_documentation_files"])

    def test_routes_across_frameworks(self):
        routes = {(r["framework"], r["path"]) for r in self.facts["routes"]["items"]}
        self.assertIn(("django", "contact/"), routes)
        self.assertIn(("express-style", "/health"), routes)
        self.assertIn(("flask", "/items"), routes)
        flask = next(r for r in self.facts["routes"]["items"] if r["framework"] == "flask")
        self.assertEqual(flask["method"], "GET,POST")
        self.assertFalse(any(r["location"].startswith("tests/") for r in self.facts["routes"]["items"]))

    def test_data_models_and_migrations(self):
        self.assertEqual(self.facts["data"]["migrations"][0]["count"], 2)
        self.assertEqual(self.facts["data"]["models"]["items"][0]["model"], "Enquiry")

    def test_manifests_ci_infra_and_specs(self):
        ecosystems = {m["ecosystem"] for m in self.facts["dependencies"]["manifests"]}
        self.assertEqual(ecosystems, {"pip", "npm"})
        ci = self.facts["ci"][0]
        self.assertEqual(ci["triggers"], ["push", "pull_request"])
        self.assertEqual([j["job"] for j in ci["jobs"]], ["test"])
        self.assertEqual(self.facts["infrastructure"]["terraform"]["items"][0]["type"], "aws_s3_bucket")
        self.assertEqual(self.facts["api_specs"][0]["title"], "Enquiries API")
        self.assertIn("api.notifications.service.gov.uk", self.facts["integrations"]["url_domains_in_code"])
        self.assertEqual(self.facts["todo_markers"]["total"], 1)

    def test_git_history_and_docs_map(self):
        self.assertEqual(self.facts["git"]["commit_count"], 1)
        sections = {s for m in self.facts["suggested_docs_map"]["mappings"] for s in m["sections"]}
        self.assertIn("data.schema", sections)
        self.assertIn("deployment.pipelines", sections)

    def test_cli_writes_facts_file(self):
        rc = extract_facts.main(["--repo", str(self.repo)])
        self.assertEqual(rc, 0)
        self.assertTrue((self.repo / ".docs-agent" / "facts.json").is_file())
