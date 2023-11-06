"""
Representation of a GitHub Assignment
"""
from __future__ import annotations
# pylint: disable=fixme

import json
import os
import subprocess
from pathlib import Path


import pandas as pd
from tqdm import tqdm  # for a progress bar

from autogradinglean.base import GitHubClassroomQueryBase
from autogradinglean.classroom import GitHubClassroom

# TODO: Document the methods that
# 2) create outputs for mail merge:
# 2.1) Write to sits candidates with no corresponding github username (classroom level)
# 2.2) Write to all candidates with a github username / classroom roster link to check the link is correct
#       (classroom level)

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
        self.logger, self.file_handler, self.console_handler = \
            self._initialise_logger(logger_name, log_file, debug = parent_classroom.debug)
        # self.df_grades = pd.DataFrame()  # DataFrame to hold grades
        self.fetch_assignment_info()  # Fetch assignment info during initialization

    def run_command(self, command, cwd=None):
        """Runs the specified command as a subprocess. Returns None on error or the stdout"""
        self.logger.debug("Running command %s", command)
        return GitHubClassroomQueryBase._run_command(command, cwd)

    def run_gh_api_command(self, command):
        """Runs a command through the GitHub api via the `gh` CLI. This command pretty prints its ouput. Thus,
        we postprocess by removing ANSI escape codes."""
        self.logger.debug("Running command %s", command)
        return GitHubClassroomQueryBase._run_gh_api_command(command)

    @property
    def queries_dir(self):
        return self._queries_dir

    def fetch_assignment_info(self):
        """Gets information about this assignment."""
        command = f"/assignments/{self.id}"
        output = self.run_gh_api_command(command)

        try:
            assignment_data = json.loads(output)
            #self.slug = assignment_data.get("slug")
            self.accepted = assignment_data.get("accepted")  # the number of accepted submissions
            #self.title = assignment_data.get("title")
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

        result = self.run_command(command, cwd)

        if result is None:
            self.logger.addHandler(self.console_handler)
            self.logger.error("Failed to get starter repository.")
            self.logger.removeHandler(self.console_handler)
        else:
            self.logger.info("Retrieved starter repository.")

    def get_starter_repo_mathlib(self):
        """Get the mathlib cache for the starter repository"""
        starter_repo_path = Path(self.assignment_dir) / "starter_repo"

        self.logger.addHandler(self.console_handler)
        self.logger.info("Getting mathlib for starter repo...")
        try:
            if starter_repo_path.exists():
                # If the starter repo directory exists, run leanproject get-mathlib-cache
                command = ["leanproject", "get-mathlib-cache"]
                result = self.run_command(command, cwd=starter_repo_path)

                if result is None:
                    self.logger.error("Failed to get mathlib cache for starter repository.")
                else:
                    self.logger.info("...successfully retrieved mathlib cache for starter repository.")
            else:

                self.logger.warning("Starter repository does not exist. Please clone it first.")

        finally:
            self.logger.removeHandler(self.console_handler)

    def get_student_repos(self):
        """Download the student repos for this assignment"""
        
        self.logger.info("Starting 'get_student_repos' function")
        student_repos_dir = Path(self.assignment_dir) / "student_repos"
        student_repos_dir.mkdir(parents=True, exist_ok=True)  # Create the directory if it doesn't exist
        self.logger.debug("Trying to load commit data")
        commit_data_file = Path(self.assignment_dir) / "commit_data.csv"

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

        page = 1
        per_page = 100  # max allowed value

        self.logger.info("Getting %s student repos", self.accepted)
        pbar = tqdm(total=self.accepted, desc="Getting student repos")
        while True:
            # Fetch accepted assignments from GitHub API
            command = f"/assignments/{self.id}/accepted_assignments?page={page}per_page={per_page}"
            output = self.run_gh_api_command(command)

            try:
                accepted_assignments = json.loads(output)
                if not accepted_assignments:
                    break  # exit loop if no more assignments

                for submission in accepted_assignments:
                    repo_info = submission.get("repository", {})
                    repo_full_name = repo_info.get("full_name", "")
                    student_repo_name = repo_full_name.split("/")[-1]
                    student_repo_path = student_repos_dir / student_repo_name
                    login = submission["students"][0]["login"]
                    new_commit_count = submission.get("commit_count", 0)

                    # Check if this repo is already in the DataFrame
                    existing_row = commit_data_df.loc[commit_data_df["student_repo_name"] == student_repo_name]
                    if existing_row.empty or existing_row.iloc[0]["commit_count"] < new_commit_count:
                        # Logic to clone or pull the repo
                        if student_repo_path.exists():
                            # Pull the repo
                            pull_command = ["git", "pull"]
                            self.run_command(pull_command, cwd=student_repo_path)
                        else:
                            # Clone the repo
                            clone_command = ["git", "clone", f"{repo_info.get('html_url', '')}", f"{student_repo_path}"]
                            self.run_command(clone_command)

                        # TODO: think about how the following is affected by different time zones and locales.
                        git_log_command = [
                            "git", "log",  "-1",  r"--format=%cd,%an",
                            r"--date=format-local:%d/%m/%y,%H:%M:%S", r"src/assignment.lean"
                        ]
                        git_log_result = self.run_command(git_log_command, cwd=student_repo_path)

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

                        commit_data_df = pd.concat([commit_data_df, pd.DataFrame([new_row])], ignore_index=True)
                    pbar.update(1)

                page += 1  # increment to fetch the next page

            except json.JSONDecodeError as e:
                self.logger.addHandler(self.console_handler)
                self.logger.error("Failed to decode JSON: %s", e)
                self.logger.removeHandler(self.console_handler)
                break

        pbar.close()
        self.logger.info("Received student repos")

        # Save updated commit data
        commit_data_df.to_csv(commit_data_file, index=False)

    def create_symlinks(self):
        """Symlink the mathlib and leanpkg.path from the starter repo to the student repos"""
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

    def run_autograding(self):
        """Runs autograding on all student repositories. Assumes that we have retrieved the starter repo,
        the starter repo mathlib, downloaded the student repos and created the symlinks"""
        # Logic to run autograding
        # Step 0: Load the existing grades DataFrame or create a new one
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
            # df_grades.set_index('student_identifier', inplace=True)

        # Load student repo data and commit counts
        commit_data_file = Path(self.assignment_dir) / "commit_data.csv"
        commit_data_df = pd.read_csv(commit_data_file)

        self.logger.info("Autograding student repos...")
        pbar = tqdm(total=self.accepted, desc="Autograding student repos")
        # Loop through each student repo
        for _, row in commit_data_df.iterrows():
            commit_count = row.get("commit_count", 0)
            login = row["login"]
            student_repo_name = row["student_repo_name"]
            self.logger.debug("Examining student repo %s", student_repo_name)
            # Check if this login exists in df_grades
            existing_row = df_grades.loc[df_grades["github_username"] == login]

            # Check if we should proceed with grading
            if existing_row.empty or existing_row.iloc[0]["commit_count"] < commit_count:
                # Do some grading!
                #print(f"Grading for {login} with commit_count {commit_count}")
                repo_path = Path(self.assignment_dir) / "student_repos" / student_repo_name
                # Step 2: Run the lean command
                result = subprocess.run(
                    ["lean", ".evaluate/evaluate.lean"],
                    capture_output=True, text=True, shell=False, check=False, cwd=repo_path
                ).stdout

                # Step 3: Check the output
                if "sorry" not in result and "error" not in result:
                    grade = 100
                else:
                    grade = 0

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
                last_commit_date = row.get("last_commit_date")
                last_commit_time = row.get("last_commit_time")
                last_commit_author = row.get("last_commit_author")

                new_row = {
                    "github_username": login,
                    "grade": grade,
                    "commit_count": commit_count,
                    "last_commit_date": last_commit_date,
                    "last_commit_time": last_commit_time,
                    "last_commit_author": last_commit_author,
                }

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
            else:
                self.logger.debug("Repo %s not updated since last run. Not grading.", student_repo_name)
            pbar.update(1)

        pbar.close()
        self.logger.info("...autograding complete")
        # Save the updated DataFrame
        df_grades.to_csv(grades_file, index=False)

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
            ~self.parent_classroom.df_student_data[self.parent_classroom.student_id_col].isna()
        ]

        # Merge the dataframes
        df_grades_out = pd.merge(df_student_data_filtered, df_grades[condition], on="github_username", how="inner")
        df_grades_out.drop(["github_id", "name"], axis=1, inplace=True)

        self.save_query_output(df_grades_out, "grades", excel=True)

    # def update_grades(self):
    # Logic to update the df_grades DataFrame
    #    pass

    # def save_grades_to_csv(self):
    # Logic to save grades to a CSV file
    #    pass

    def autograde(self):
        """High-level method to perform all autograding steps"""
        self.logger.addHandler(self.console_handler)
        try:
            self.get_starter_repo()
            self.get_starter_repo_mathlib()
            self.get_student_repos()
            self.create_symlinks()
            self.run_autograding()
            # self.update_grades()
            # self.save_grades_to_csv()
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
            ["identifier", "github_username", *self.parent_classroom.output_cols, "student_repo_name"]
        ]
        self.save_query_output(df_no_commits, "no_commits", excel=True)
