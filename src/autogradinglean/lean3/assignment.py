"""
Representation of a GitHub Assignment for Lean 3 marking
"""
from __future__ import annotations

# pylint: disable=fixme
import os
import subprocess
from pathlib import Path

import toml

from autogradinglean.base.assignment import GitHubAssignment

# TODO: Document the methods that
# 2) create outputs for mail merge:
# 2.1) Write to candidates with no corresponding github username (classroom level)
# 2.2) Write to all candidates with a github username / classroom roster link to check the link is correct
#       (classroom level)


class GitHubAssignmentLean3(GitHubAssignment):
    """
    Represents a GitHub assignment and provides methods for downloading repositories, autograding, etc.\
    """

    def _get_mathlib(self, starter_repo_path):
        self.logger.debug("Testing if mathlib is a dependency")
        leanpkgtoml_path = starter_repo_path / "leanpkg.toml"
        leanpkgtoml = toml.load(leanpkgtoml_path)
        if "dependencies" in leanpkgtoml:
            if "mathlib" in leanpkgtoml["dependencies"]:
                self.logger.info("Getting mathlib cache for stater repo...")
                command = ["leanproject", "get-mathlib-cache"]
                result = self._run_command(command, cwd=starter_repo_path)

                if result is None:
                    self.logger.error("Failed to get mathlib")
                else:
                    self.logger.info("...successfully retrieved mathlib cache")
            return
        self.logger.debug("Mathlib is not a dependency")

    def configure_starter_repo(self):
        """
        Configure the starter repository. This will download all dependencies.
        """
        starter_repo_path = Path(self.assignment_dir) / "starter_repo"

        self.logger.addHandler(self.console_handler)
        self.logger.info("Configuring the starter repo...")
        try:
            if starter_repo_path.exists():
                # If the starter repo directory exists, run leanpkg configure
                command = ["leanpkg", "configure"]
                result = self._run_command(command, cwd=starter_repo_path)
                if result is None:
                    self.logger.error("Failed to configure the starter repository.")
                else:
                    self.logger.info("...successfully configured the starter repository.")
                self._get_mathlib(starter_repo_path)
            else:
                self.logger.warning("Starter repository does not exist. Please clone it first.")

        finally:
            self.logger.removeHandler(self.console_handler)

    def configure_student_repos(self):
        """Symlink the _target and leanpkg.path from the starter repo to the student repos"""
        student_repos_dir = Path(self.assignment_dir) / "student_repos"
        starter_repo_dir = Path(self.assignment_dir) / "starter_repo"

        self.logger.info("Creating symlinks")
        for student_dir in student_repos_dir.iterdir():
            if student_dir.is_dir():
                target_link = student_dir / "_target"
                leanpkg_link = student_dir / "leanpkg.path"

                if not target_link.exists():
                    os.symlink(starter_repo_dir / "_target", target_link)

                if not leanpkg_link.exists():
                    os.symlink(starter_repo_dir / "leanpkg.path", leanpkg_link)

    @staticmethod
    def _run_grading_command(repo_path):
        result = subprocess.run(
            ["lean", ".evaluate/evaluate.lean"], capture_output=True, text=True, shell=False, check=False, cwd=repo_path
        ).stdout

        if "sorry" not in result and "error" not in result:
            grade = 100
        else:
            grade = 0
        return grade
