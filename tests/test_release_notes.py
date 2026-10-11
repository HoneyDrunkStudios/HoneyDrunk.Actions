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
    def extract(self, files):
        action = ACTION.read_text(encoding="utf-8")
        block = action.split("      id: extract-all\n", 1)[1].split("    - name: Assemble release body", 1)[0]
        script = textwrap.dedent(block.split("      run: |\n", 1)[1])
        values = {"inputs.version": "0.1.0-alpha.4", "inputs.changelog-paths": "", "inputs.search-root": "."}
        script = re.sub(r"\$\{\{\s*(.*?)\s*\}\}", lambda match: values[match[1]], script)
        with tempfile.TemporaryDirectory(prefix="release-discovery-test-") as directory:
            root = Path(directory)
            repo = root / "repository"
            repo.mkdir()
            for name, content in files.items():
                path = repo / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            script_path = root / "extract.sh"
            script_path.write_text(script, encoding="utf-8", newline="\n")
            output = root / "output.txt"
            result = subprocess.run(
                [os.environ.get("BASH_EXE", "bash"), "--noprofile", "--norc", "-e", "-o", "pipefail", script_path.as_posix()],
                cwd=repo, env={**os.environ, "RUNNER_TEMP": root.as_posix(), "GITHUB_OUTPUT": output.as_posix()},
                capture_output=True, text=True, encoding="utf-8",
            )
            return result, output.read_text(encoding="utf-8") if output.exists() else "", (root / "changelog-entries.txt").read_text(encoding="utf-8")

    def test_missing_version_does_not_abort_later_matching_changelog(self):
        result, output, entries = self.extract({
            "a/CHANGELOG.md": "## [0.0.1]\nUnrelated version.\n",
            "z/CHANGELOG.md": "## [0.1.0-alpha.4]\nIdentity release.\n",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("has-changelog=true", output)
        self.assertIn("Identity release.", entries)
        self.assertNotIn("Unrelated version.", entries)

    def test_no_matching_version_allows_generated_notes_fallback(self):
        result, output, entries = self.extract({"CHANGELOG.md": "## [0.0.1]\nOld release.\n"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("has-changelog=false", output)
        self.assertEqual(entries, "")

    def test_actions_checkout_changelogs_and_solutions_are_excluded(self):
        for with_solution in (False, True):
            with self.subTest(with_solution=with_solution):
                files = {
                    "CHANGELOG.md": "## [0.1.0-alpha.4]\nIdentity release.\n",
                    ".github/actions-repo/CHANGELOG.md": "## [0.1.0-alpha.4]\nWrong repository.\n",
                }
                if with_solution:
                    files[".github/actions-repo/Actions.slnx"] = "<Solution />"
                result, output, entries = self.extract(files)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("entry-count=1", output)
                self.assertIn("Identity release.", entries)
                self.assertNotIn("Wrong repository.", entries)

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
