import csv

from helpers import RepoTestCase, make_repo
import sample_claims
import score


class EvaluationTests(RepoTestCase):
    def test_sample_then_score(self):
        repo = make_repo(self.tmp / "repo", {
            "app/x.py": "1\n2\n",
            "docs/p.md": "<!-- agent:begin section=p.a commit=abc1234 -->\n"
                         "Claim one ([app/x.py:1](../app/x.py#L1))\n"
                         "Claim two ([app/x.py:2](../app/x.py#L2))\n"
                         "> **Unknown – needs SME input:** Who?\n"
                         "No citation here\n"
                         "<!-- agent:end -->\n",
        })
        out = repo / "sample.csv"
        sample_claims.main(["--docs", str(repo / "docs"), "--out", str(out)])
        with out.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(sorted(r["type"] for r in rows), ["claim", "claim", "unknown"])

        for r in rows:
            r["verdict"] = "genuine" if r["type"] == "unknown" else "correct"
        result = score.score(rows)
        self.assertEqual(result["claim_accuracy"], 1.0)
        self.assertEqual(result["unknown_genuine_rate"], 1.0)

        rows[0]["verdict"] = "partly" if rows[0]["type"] == "claim" else rows[0]["verdict"]
        rows[1]["verdict"] = "incorrect" if rows[1]["type"] == "claim" else rows[1]["verdict"]
        self.assertLess(score.score(rows)["claim_accuracy"], 0.9)
