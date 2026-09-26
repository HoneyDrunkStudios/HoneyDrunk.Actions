"""Exercise the real composite-action assembly script with local Git histories."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest


ACTION = Path(__file__).resolve().parents[1] / ".github/actions/release/generate-notes/action.yml"


class ReleaseNotesTests(unittest.TestCase):
    def assemble(self, tags=(), *, previous_implementation=False, initialize_git=True):
        action = ACTION.read_text(encoding="utf-8")
        script = textwrap.dedent(action.split("      id: assemble\n", 1)[1].split("      run: |\n", 1)[1])
        values = {
            "inputs.version": "0.3.0",
            "inputs.product-name": "Example",
            "inputs.product-description": "Release fixture",
            "inputs.nuget-packages": "Example.Abstractions",
            "inputs.docs-url": "https://example.invalid/docs",
            "inputs.include-compare-link": "true",
            "steps.extract-all.outputs.has-changelog": "false",
            "steps.extract-all.outputs.entry-count": "0",
            "github.repository": "example/project",
        }
        script = re.sub(r"\$\{\{\s*(.*?)\s*\}\}", lambda match: values[match[1]], script)
        if previous_implementation:
            self.assertIn("sed -n '/^v[0-9]/p'", script)
            script = script.replace("sed -n '/^v[0-9]/p'", "grep -E '^v[0-9]'", 1)

        with tempfile.TemporaryDirectory(prefix="release-notes-test-") as directory:
            root = Path(directory)
            repo = root / "repository"
            repo.mkdir()
            if initialize_git:
                def git(*args):
                    subprocess.run(
                        ["git", "-c", "user.name=Release Test", "-c", "user.email=release@example.invalid",
                         "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
                        cwd=repo, check=True, capture_output=True,
                    )
                git("init", "--quiet")
                git("commit", "--allow-empty", "--quiet", "-m", "test: seed release fixture")
                for tag in tags:
                    git("tag", tag)

            script_path = root / "assemble.sh"
            script_path.write_text(script, encoding="utf-8", newline="\n")
            output = root / "output.txt"
            env = {**os.environ, "RUNNER_TEMP": root.as_posix(), "GITHUB_OUTPUT": output.as_posix(),
                   "GITHUB_REPOSITORY": "example/project"}
            result = subprocess.run(
                [os.environ.get("BASH_EXE", "bash"), "--noprofile", "--norc", "-e", "-o", "pipefail", script_path.as_posix()],
                cwd=repo, env=env, capture_output=True, text=True, encoding="utf-8",
            )
            return result, output.read_text(encoding="utf-8") if output.exists() else ""

    def test_no_tags_produces_release_body_without_compare_link(self):
        result, output = self.assemble()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Example v0.3.0", output)
        self.assertNotIn("/compare/", output)

    def test_only_nonmatching_tags_produces_release_body_without_compare_link(self):
        result, output = self.assemble(("runtime-v0.2.0", "abstractions-v0.2.0"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Example v0.3.0", output)
        self.assertNotIn("/compare/", output)

    def test_matching_tags_preserve_second_tag_selection(self):
        result, output = self.assemble(("v0.1.0", "v0.2.0", "v0.3.0", "runtime-v9.0.0"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/compare/v0.2.0...v0.3.0", output)

    def test_previous_implementation_reproduces_empty_history_failure(self):
        result, output = self.assemble(previous_implementation=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, "")

    def test_real_git_failure_remains_fatal(self):
        result, output = self.assemble(initialize_git=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
