"""Exercise both seed entry points with an old catalog; no GitHub writes."""

import contextlib
import io
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
RETIRED = {
    'needs-agent-review', 'agent-review-in-progress', 'agent-reviewed',
    'changes-requested-by-agent', 'skip-grid-review', 'skip-review',
}
AUDIT = {'post-merge-audit-in-progress', 'post-merge-audited', 'post-merge-audit-findings'}


class ReviewRetirement(unittest.TestCase):
    def test_current_catalog_preserves_audit_and_excludes_retired_labels(self):
        labels = json.loads((ROOT / '.github/config/labels.json').read_text(encoding='utf-8'))['labels']
        names = {label['name'] for label in labels}
        self.assertFalse(names & RETIRED)
        self.assertTrue((AUDIT | {'audit-sample', 'large-pr'}) <= names)
        self.assertEqual(len(names), len(labels))

    def test_each_seed_entry_point_filters_old_catalog_without_losing_other_labels(self):
        names = sorted(RETIRED | AUDIT | {'audit-sample', 'large-pr', 'agent-codex', 'custom-label'})
        catalog = json.dumps({'labels': [{'name': n, 'color': '123456', 'description': n} for n in names]})
        for name in ('seed-labels.yml', 'seed-labels-fanout.yml'):
            with self.subTest(workflow=name):
                text = (ROOT / '.github/workflows' / name).read_text(encoding='utf-8')
                match = re.search(r"          python3 - <<'PY' > labels.tsv\n(.*?)          PY", text, re.S)
                self.assertIsNotNone(match)
                source = '\n'.join(line[10:] for line in match.group(1).splitlines())
                output = io.StringIO()
                with patch.object(Path, 'read_text', return_value=catalog), contextlib.redirect_stdout(output):
                    exec(compile(source, name, 'exec'), {})
                emitted = {line.split('\t')[0] for line in output.getvalue().splitlines()}
                self.assertEqual(emitted, set(names) - RETIRED)


if __name__ == '__main__':
    unittest.main()
