"""
Abstract representation of a GitHub Assignment

Any derived class must implement the methods

* configure_starter_repo()
* configure_student_repos()
* _run_grading_command()

"""
from __future__ import annotations

import json
import time
from abc import abstractmethod
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from math import ceil
from pathlib import Path

import pandas as pd
from tqdm import tqdm  # for a progress bar

from autogradinglean.base.base import GitHubClassroomQueryBase
from autogradinglean.base.classroom import GitHubClassroom


class GitHubAssignment(GitHubClassroomQueryBase):
    """Represents a GitHub assignment and provides methods for downloading repositories, autograding, etc."""

    def __init__(self, assignment_id, parent_classroom: GitHubClassroom):
        self.id = assignment_id
        self.parent_classroom = parent_classroom  # Reference to the parent GitHubClassroom object
        self.assignment_dir = self.parent_classroom.marking_root_dir / f"assignment{self.id}"
        if not self.assignment_dir.exists():
            self.assignment_dir.mkdir(parents=True)  # Create the directory if it doesn't exist
        self._queries_dir = self.assignment_dir / "query_output"
        logger_name = f"GitHubAssignment{self.id}"
        log_file = self.assignment_dir / f"assignment{self.id}.log"
        self.logger, self.file_handler, self.console_handler = self._initialise_logger(
            logger_name, log_file, debug=parent_classroom.debug
        )
        # self.df_grades = pd.DataFrame()  # DataFrame to hold grades
        self.fetch_assignment_info()  # Fetch assignment info during initialization

    def _run_command(self, command, cwd=None):
        """Runs the specified command as a subprocess. Returns None on error or the stdout"""
        return GitHubClassroomQueryBase._run_command_base(command, cwd=cwd, logger=self.logger)

    def _run_gh_api_command(self, command):
        """Runs a command through the GitHub api via the `gh` CLI. This command pretty prints its ouput. Thus,
        we postprocess by removing ANSI escape codes."""
        return GitHubClassroomQueryBase._run_gh_api_command_base(command, logger=self.logger)

    @property
    def queries_dir(self):
        return self._queries_dir

    def fetch_assignment_info(self):
        """Gets information about this assignment."""
        command = f"/assignments/{self.id}"
        output = self._run_gh_api_command(command)

        try:
            assignment_data = json.loads(output)
            # self.slug = assignment_data.get("slug")
            self.accepted = assignment_data.get("accepted")  # the number of accepted submissions
            # self.title = assignment_data.get("title")
            self.type = assignment_data.get("type")
            self.starter_code_repository = assignment_data.get("starter_code_repository", {}).get("full_name")
            self.deadline = assignment_data.get("deadline")
        except json.JSONDecodeError as e:
            self.logger.addHandler(self.console_handler)
            self.logger.error("Failed to decode JSON: %s", e)
            self.logger.removeHandler(self.console_handler)
        self.logger.info("Received assignment information")

    def get_starter_repo(self):
        """Download the starter repository for this assignment"""
        starter_repo_path = Path(self.assignment_dir) / "starter_repo"

        if starter_repo_path.exists():
            # If the starter repo directory exists, pull the latest changes
            command, cwd = (["git", "pull"]), starter_repo_path
        else:
            # Otherwise, clone the starter repo
            command, cwd = (["gh", "repo", "clone", f"{self.starter_code_repository}", f"{starter_repo_path}"]), None

        result = self._run_command(command, cwd)

        if result is None:
            self.logger.addHandler(self.console_handler)
            self.logger.error("Failed to get starter repository.")
            self.logger.removeHandler(self.console_handler)
        else:
            self.logger.info("Retrieved starter repository.")

    @abstractmethod
    def configure_starter_repo(self):
        """
        Configure the starter repository. This will download all dependencies.
        """

    def _read_commit_data(self, commit_data_file):
        """
        Read (or create if it doesn't exist) the commit_data.csv file
        """
        # Initialize DataFrame to store commit data
        if commit_data_file.exists():
            commit_data_df = pd.read_csv(commit_data_file)
            self.logger.debug("Loaded commit data")
        else:
            commit_data_df = pd.DataFrame(
                columns=[
                    "student_repo_name",
                    "login",
                    "commit_count",
                    "last_commit_date",
                    "last_commit_time",
                    "last_commit_author",
                ]
            )
            self.logger.debug("No commit data. Creating empty dataframe.")
        return commit_data_df

    def _get_student_repo(self, submission, student_repos_dir, pbar):
        """
        Get a single student repository
        """
        repo_info = submission.get("repository", {})
        student_repo_name = repo_info.get("full_name", "").split("/")[-1]
        student_repo_path = student_repos_dir / student_repo_name
        login = submission["students"][0]["login"]
        new_commit_count = submission.get("commit_count", 0)

        self.logger.debug("Repo %s not already in commit data file", student_repo_name)
        # Logic to clone or pull the repo
        if student_repo_path.exists():
            # Pull the repo
            pull_command = ["git", "pull"]
            self._run_command(pull_command, cwd=student_repo_path)
        else:
            # Clone the repo
            clone_command = ["git", "clone", f"{repo_info.get('html_url', '')}", f"{student_repo_path}"]
            self._run_command(clone_command)

        # TODO: think about how the following is affected by different time zones and locales.
        git_log_command = [
            "git",
            "log",
            "-1",
            r"--format=%cd,%an",
            r"--date=format-local:%d/%m/%y,%H:%M:%S",
            r"src/assignment.lean",
        ]
        git_log_result = self._run_command(git_log_command, cwd=student_repo_path)

        # Update or add the row in the DataFrame
        new_row = {
            "student_repo_name": student_repo_name,
            "login": login,
            "commit_count": new_commit_count,
        }

        if git_log_result:
            last_commit_date, last_commit_time, last_commit_author = git_log_result.strip().split(",")
            new_row["last_commit_date"] = last_commit_date
            new_row["last_commit_time"] = last_commit_time
            new_row["last_commit_author"] = last_commit_author

        pbar.update(1)
        return new_row

    def _get_page(self, page, per_page):
        """
        Get a page of submissions.

        Due to GitHub API rate limiting, if the call to `_run_gh_api_command` fails, we should wait and try again

        TODO:
        * incorporate this into the `_run_gh_api_command` function (and get rid of this function).
        * deal with rate limiting more intelligently.
        """
        self.logger.debug("Getting submissions page %s, with %s items per page", page, per_page)
        command = f"/assignments/{self.id}/accepted_assignments?page={page}&per_page={per_page}"

        for _ in range(3):  # Retry up to 3 times
            output = self._run_gh_api_command(command)
            if output is not None:
                return output
            time.sleep(4)  # Wait for 4 seconds before retrying
        return None  # Could not get the page after 3 attempts

    def _get_accepted_assignments(self):
        """
        Return a list of all accepted assignments
        """
        per_page = 30  # start at page 1, do 30 'items' per page
        pages = ceil(self.accepted / 30.0)
        self.logger.debug("Getting pages of student repo data")
        accepted_assignments = []  # a list to hold all accepted assignments

        pbar = tqdm(total=pages, desc="Getting pages of student repo data")
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(self._get_page, page, per_page) for page in range(1, pages + 1)]

            for future in as_completed(futures):
                output = future.result()
                next_page = json.loads(output)
                if next_page:
                    accepted_assignments += next_page  # add the next page of assignments to the list
                    pbar.update(1)
        assert len(accepted_assignments) == self.accepted
        pbar.close()
        return accepted_assignments

    def _get_changed_repos(self, accepted_assignments, commit_data_df):
        """
        Determine which student repos are new or have been changed since the last run
        """
        changed_repos = []  # a list of repos which are new or have been changed
        for submission in accepted_assignments:
            repo_info = submission.get("repository", {})
            student_repo_name = repo_info.get("full_name", "").split("/")[-1]
            new_commit_count = submission.get("commit_count", 0)

            self.logger.debug("Considering student repository: %s", student_repo_name)

            # Check if this repo is already in the DataFrame
            existing_row = commit_data_df.loc[commit_data_df["student_repo_name"] == student_repo_name]
            if existing_row.empty or existing_row.iloc[0]["commit_count"] < new_commit_count:
                self.logger.debug("The repo %s is new or has changed", student_repo_name)
                changed_repos.append(submission)
        return changed_repos

    def get_student_repos(self):
        """Download the student repos for this assignment"""

        self.logger.info("Starting 'get_student_repos' function")
        student_repos_dir = Path(self.assignment_dir) / "student_repos"
        student_repos_dir.mkdir(parents=True, exist_ok=True)  # Create the directory if it doesn't exist
        self.logger.debug("Trying to load commit data")
        commit_data_file = Path(self.assignment_dir) / "commit_data.csv"
        commit_data_df = self._read_commit_data(commit_data_file)
        self.logger.info("Getting %s student repos", self.accepted)

        accepted_assignments = self._get_accepted_assignments()
        changed_repos = self._get_changed_repos(accepted_assignments, commit_data_df)

        pbar = tqdm(total=len(changed_repos), desc="Getting student repos")

        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(self._get_student_repo, submission, student_repos_dir, pbar)
                for submission in changed_repos
            ]

            for future in as_completed(futures):
                new_row = future.result()
                if new_row is not None:
                    commit_data_df = pd.concat([commit_data_df, pd.DataFrame([new_row])], ignore_index=True)

        commit_data_df.to_csv(commit_data_file, index=False)

        pbar.close()
        self.logger.info("Received student repos")

    @abstractmethod
    def configure_student_repos(self):
        """
        Perform any configuration of the student repos required before moving on to grading
        """

    def _get_grades(self):
        grades_file = Path(self.assignment_dir) / "grades.csv"
        if grades_file.exists():
            df_grades = pd.read_csv(grades_file)
        else:
            df_grades = pd.DataFrame(
                columns=[
                    "github_username",
                    "grade",
                    "commit_count",
                    "last_commit_date",
                    "last_commit_time",
                    "last_commit_author",
                    "manual_grade",
                    "comment",
                ]
            )
        return grades_file, df_grades

    @staticmethod
    @abstractmethod
    def _run_grading_command(repo_path):
        """
        Grades the given repo and returns a integer variable grade
        """

    def _save_grades(self, df_grades, grades_file):
        """Saves the df_grades DataFrame to a CSV file then merges with the student data and saves to an Excel file."""

        # TODO: ensure that the grade output excel file contains no duplicates
        # Question: what happens if several different marks are given for the same student and the same assignment?

        # Save the updated DataFrame to a CSV file
        df_grades.to_csv(grades_file, index=False, encoding = 'utf-8')

        # Filter rows where 'last_commit_author' is not 'github-classroom[bot]'
        condition = df_grades["last_commit_author"] != "github-classroom[bot]"

        # Update 'final_grade' based on the condition
        df_grades.loc[condition, "final_grade"] = df_grades.loc[condition].apply(
            lambda row: row["manual_grade"] if pd.notna(row["manual_grade"]) else row["grade"], axis=1
        )

        # Drop the original 'grade' and 'manual_grade' columns
        df_grades.drop(["grade", "manual_grade"], axis=1, inplace=True)

        # Filter student data
        df_student_data_filtered = self.parent_classroom.df_student_data[
            ~self.parent_classroom.df_student_data[
                self.parent_classroom.config["candidate_file"]["candidate_id_col"]
            ].isna()
        ]

        # Merge the dataframes
        df_grades_out = pd.merge(df_student_data_filtered, df_grades[condition], on="github_username", how="inner")
        df_grades_out.drop(["github_id", "name"], axis=1, inplace=True)

        self.save_query_output(df_grades_out, "grades", excel=True)

    @staticmethod
    def _update_student_grade(grade, row, existing_row):
        """
        Update the dataframe with the new student grade
        """
        # Update the DataFrame
        # TODO: think carefully about what happens if a student makes a commit after the deadline.
        #   There are several possibilities:
        # 1) The student made no commit before the deadline. Then this counts as their only commit. The Hub can
        #       determine what mark should be awarded.
        # 2) The student made a commit before the deadline *and* after the deadline.
        #   The fairest resolution might be to start by grading the last submission before the deadline. If
        #   (on the advice of the Hub), mitigation is given, then a chosen submission after the deadline should
        #   be marked.
        #   If we go down this route, I'll have to think about how to represent the grades in the DataFrame.
        new_row = {
            "github_username": row["login"],
            "grade": grade,
            "commit_count": row.get("commit_count", 0),
            "last_commit_date": row.get("last_commit_date"),
            "last_commit_time": row.get("last_commit_time"),
            "last_commit_author": row.get("last_commit_author"),
        }

        return existing_row, new_row

    @classmethod
    def _grade_repo(cls, row, assignment_dir, df_grades):
        commit_count = row.get("commit_count", 0)
        login = row["login"]
        student_repo_name = row["student_repo_name"]
        # Check if this login exists in df_grades
        existing_row = df_grades.loc[df_grades["github_username"] == login]

        # Check if we should proceed with grading
        if existing_row.empty or existing_row.iloc[0]["commit_count"] < commit_count:
            # Do some grading!
            repo_path = Path(assignment_dir) / "student_repos" / student_repo_name
            # Run the lean command
            grade = cls._run_grading_command(repo_path)

            return cls._update_student_grade(grade, row, existing_row)
        return None

    def run_autograding(self):
        """Runs autograding on all student repositories. Assumes that we have retrieved the starter repo,
        the starter repo mathlib, downloaded the student repos and created the symlinks"""
        # Load the existing grades DataFrame or create a new one
        grades_file, df_grades = self._get_grades()
        # Load student repo data and commit counts
        commit_data_file = Path(self.assignment_dir) / "commit_data.csv"
        commit_data_df = pd.read_csv(commit_data_file)

        self.logger.info("Autograding student repos...")
        pbar = tqdm(total=self.accepted, desc="Autograding student repos")
        # Loop through each student repo

        with ProcessPoolExecutor() as executor:
            futures = [
                executor.submit(type(self)._grade_repo, row, self.assignment_dir, df_grades)
                for _, row in commit_data_df.iterrows()
            ]

            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    existing_row, new_row = result
                    self.logger.debug("Graded repo for student with github username %s", new_row["github_username"])
                    if existing_row.empty:
                        # Append new row with default values for manual_grade and comment
                        new_row["manual_grade"] = None
                        new_row["comment"] = None
                        df_grades = pd.concat([df_grades, pd.DataFrame([new_row])], ignore_index=True)
                    else:
                        # Update existing row without modifying manual_grade and comment
                        existing_index = existing_row.index[0]
                        for key, value in new_row.items():
                            df_grades.at[existing_index, key] = value
                pbar.update(1)

        pbar.close()
        self.logger.info("...autograding complete")
        self._save_grades(df_grades, grades_file)

    def autograde(self):
        """High-level method to perform all autograding steps"""
        self.logger.addHandler(self.console_handler)
        try:
            self.get_starter_repo()
            self.configure_starter_repo()
            self.get_student_repos()
            self.configure_student_repos()
            self.run_autograding()
        finally:
            self.logger.removeHandler(self.console_handler)

    def find_no_commit_candidates(self):
        """Find the candidates who have not made a submission for this assignment. Though the natural
        thing would be to test if 'commit_count' is zero, this doesn't always work (for reasons unbeknownst
        to me). That is, sometimes a student will commit but the commit count will be zero. Perhaps this happens
        if they push after the deadline.

        In any event, I will look for students where the last_commit_author is `github-classroom[bot]`.

        To ensure you have the latest data, run `get_student_repos()` before running this function.
        """

        commit_data_file = Path(self.assignment_dir) / "commit_data.csv"
        # TODO: error handing if the commit_data_file doesn't exist
        commit_data_df = pd.read_csv(commit_data_file)
        filtered_commit_data_df = commit_data_df[commit_data_df["last_commit_author"] == "github-classroom[bot]"]
        df_no_commits = pd.merge(
            self.parent_classroom.df_student_data,
            filtered_commit_data_df,
            left_on="github_username",
            right_on="login",
            how="inner",
        )
        df_no_commits = df_no_commits[
            [
                "identifier",
                "github_username",
                *self.parent_classroom.config["candidate_file"]["output_cols"],
                "student_repo_name",
            ]
        ]
        self.save_query_output(df_no_commits, "no_commits", excel=True)
