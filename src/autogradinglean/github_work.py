import pandas as pd
import subprocess
import json
import re
import os
import toml
from pathlib import Path

# This module performs all the interaction with GitHub, largely via the GitHub API.
# Here is documenation on querying classrooms via the API:
#
#   https://docs.github.com/en/rest/classroom/classroom
#
# The current version of the module takes a simple approach, calling GitHub's `gh` CLI.
# I plan to use the `PyGithub` package in the future. What I still need to understand is how to
# perform authentication as a GitHub App.
# Some useful reading is to be found at
#
#   https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/managing-private-keys-for-github-apps
#
# and at
#
#   https://pygithub.readthedocs.io/en/stable/examples/Authentication.html#app-authentication


class GitHubClassroomBase:
    _ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    @staticmethod
    def run_gh_command(command):
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return None
        return result.stdout

    @staticmethod
    def remove_ansi_codes(text):
        return GitHubClassroomBase._ansi_escape.sub('', text)


class GitHubClassroom(GitHubClassroomBase):
    def __init__(self, marking_root_dir):
        self.marking_root_dir = Path(marking_root_dir).expanduser()
        # Check if marking_root_dir exists
        if not self.marking_root_dir.exists():
            raise FileNotFoundError(f"The specified marking_root_dir '{self.marking_root_dir}' does not exist.")

        # Load configuration from TOML file
        config_file_path = self.marking_root_dir / 'config.toml'
        config = self.load_config_from_toml(config_file_path)
        
        if config is None:
            raise Exception("Failed to load configuration. Initialization aborted.")
        
        self.id = config['classroom_id']
        
        # Make paths in TOML relative to marking_root_dir
        self.classroom_roster_csv = self.marking_root_dir / config['classroom_roster_csv']
        self.sits_candidate_file = self.marking_root_dir / config['sits_candidate_file']

        self.df_classroom_roster = pd.read_csv(self.classroom_roster_csv, dtype=object)
        self.df_sits_candidates = pd.read_csv(self.sits_candidate_file, dtype=object)
        self.df_sits_candidates['Candidate No'] = self.df_sits_candidates['Candidate No'].astype(int).astype(str).apply(lambda x: x.zfill(6))     
        self.df_student_data = pd.DataFrame()
        self.assignments = []  # List to hold GitHubAssignment objects
        self.df_assignments = self.fetch_assignments()  # Fetch assignments on initialization
        self.merge_student_data()
        self.initialize_assignments()  # Initialize GitHubAssignment objects

    @staticmethod
    def load_config_from_toml(config_file_path):
        try:
            config = toml.load(config_file_path)
            return config
        except Exception as e:
            print(f"Failed to load configuration from {config_file_path}: {e}")
            return None

    def fetch_assignments(self):
        command = f'gh api -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" /classrooms/{self.id}/assignments'        
        raw_output = self.run_gh_command(command)
        cleaned_output = self.remove_ansi_codes(raw_output)
        
        try:
            assignments_data = json.loads(cleaned_output)
            df_assignments = pd.DataFrame(assignments_data)
            return df_assignments
        except json.JSONDecodeError as e:
            print(f"Failed to decode JSON: {e}")
            return None

    def merge_student_data(self):
        """Merges candidate data from a GitHub Classroom classroom roster CSV file and a CSV file
        extracted from SITS.
        
        The SITS data should contain the following columns:

            'SPR code', 'Candidate No', 'Forename', 'Surname', 'Email Address'.

        The 'Candidate No' is expected to be a string of 6 digits, padded left with zeros.

        The columns of the classroom roster should be:

            'identifier', 'github_username', 'github_id', 'name'

        The 'identifier' should correspond with the 'Candidate No' from the SITS spreadsheet.
        """
        # The classroom roster and SITS data are already stored in the object
        df_classroom_roster = self.df_classroom_roster
        df_sits_candidates = self.df_sits_candidates

        self.df_student_data = pd.merge(df_classroom_roster, df_sits_candidates, left_on='identifier', right_on='Candidate No', how='outer')
        
    def update_classroom_roster(self, new_classroom_roster_csv):
        self.df_classroom_roster = pd.read_csv(new_classroom_roster_csv, dtype=object)

    def update_sits_candidates(self, new_sits_candidate_file):
        self.df_sits_candidates = pd.read_excel(new_sits_candidate_file, dtype=object)

    def initialize_assignments(self):
        for index, row in self.df_assignments.iterrows():
            assignment_id = row['id']
            new_assignment = GitHubAssignment(assignment_id, self)
            self.assignments.append(new_assignment)

class GitHubAssignment(GitHubClassroomBase):
    def __init__(self, assignment_id, parent_classroom):
        self.id = assignment_id
        self.parent_classroom = parent_classroom  # Reference to the parent GitHubClassroom object
        self.assignment_dir = self.parent_classroom.marking_root_dir / f"assignment{self.id}"
        if not self.assignment_dir.exists():
            self.assignment_dir.mkdir(parents=True)  # Create the directory if it doesn't exist
        self.df_grades = pd.DataFrame()  # DataFrame to hold grades
        self.fetch_assignment_info()  # Fetch assignment info during initialization

        # Initialize other attributes related to the assignment

    def fetch_assignment_info(self):
        command = f'gh api -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" /assignments/{self.id}'
        raw_output = self.run_gh_command(command)
        cleaned_output = self.remove_ansi_codes(raw_output)
        
        try:
            assignment_data = json.loads(cleaned_output)
            self.title = assignment_data.get('title')
            self.type = assignment_data.get('type')
            self.starter_code_repository = assignment_data.get('stater_code_repository', {}).get('full_name')
            self.deadline = assignment_data.get('deadline')
        except json.JSONDecodeError as e:
            print(f"Failed to decode JSON: {e}")
            return None

    def clone_or_pull_starter_repo(self):
        # Logic to clone or pull the starter repo
        pass

    def clone_or_pull_student_repos(self):
        # Logic to clone or pull student repos
        pass

    def create_symlinks(self):
        # Logic to create symlinks from starter repo to student repos
        pass

    def run_autograding(self):
        # Logic to run autograding
        pass

    def update_grades(self):
        # Logic to update the df_grades DataFrame
        pass

    def save_grades_to_csv(self):
        # Logic to save grades to a CSV file
        pass

    def autograde(self):
        # High-level method to perform all autograding steps
        self.clone_or_pull_starter_repo()
        self.clone_or_pull_student_repos()
        self.create_symlinks()
        self.run_autograding()
        self.update_grades()
        self.save_grades_to_csv()


class GitHubClassroomManager(GitHubClassroomBase):
    def __init__(self):
        self.df_classrooms = pd.DataFrame()
        self.fetch_classrooms()

    def fetch_classrooms(self):
        command = 'gh api -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" /classrooms'
        raw_output = self.run_gh_command(command)
        cleaned_output = self.remove_ansi_codes(raw_output)
        try:
            classrooms_data = json.loads(cleaned_output)
            self.df_classrooms = pd.DataFrame(classrooms_data)
        except json.JSONDecodeError as e:
            print(f"Failed to decode JSON: {e}")
    
    # def fetch_assignments(self, classroom_id=None, classroom_name=None):
    #     if classroom_id:
    #         command = f'gh api -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" /classrooms/{classroom_id}/assignments'
    #     elif classroom_name:
    #         classroom_row = self.df_classrooms[self.df_classrooms['name'] == classroom_name]
    #         if not classroom_row.empty:
    #             classroom_id = classroom_row.iloc[0]['id']
    #             command = f'gh api -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" /classrooms/{classroom_id}/assignments'
    #         else:
    #             print(f"No classroom found with the name {classroom_name}")
    #             return None
    #     else:
    #         print("Either classroom_id or classroom_name must be provided.")
    #         return None
        
    #     raw_output = self.run_gh_command(command)
    #     cleaned_output = self.remove_ansi_codes(raw_output)
        
    #     try:
    #         assignments_data = json.loads(cleaned_output)
    #         df_assignments = pd.DataFrame(assignments_data)
            
    #         # Create a GitHubClassroom object and populate it
    #         classroom = GitHubClassroom(classroom_id, classroom_name)
    #         classroom.df_assignments = df_assignments
            
    #         return classroom
    #     except json.JSONDecodeError as e:
    #         print(f"Failed to decode JSON: {e}")
    #         return None
