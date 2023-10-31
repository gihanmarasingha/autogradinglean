import pandas as pd
import subprocess
import json
import re
import toml
from pathlib import Path
import os
from tqdm import tqdm # for a progress bar

###################################
#
#  TO DO, TO DO, TO DO, TO DO, TO DO, TO DO, 
# 
#  Currently, I'm using the `accepted-assignments` API. This works pretty well
#  but does not return submissions from people who didn't choose a student identifier
#  
#  The `get assignment grades` API gets grades for anyone who submitted (even if) 
#  not associated with a student identifier, but *only if* they submitted before the
#  deadline. Thus, it's no good for working with late submissions
#
#  Plan: primarily use `accepted-assignments` data, but also use
#  `get assignment grades` to identify those people who didn't choose a 
#  student identifier. This may not really be necessary or useful as there's
#  little one can do with just a GitHub username.


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
    def run_command(command):
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return None
        return result.stdout

    @staticmethod
    def run_gh_command(command):
        raw_ouput = GitHubClassroomBase.run_command(command)
        return GitHubClassroomBase._ansi_escape.sub('', raw_ouput)
    

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
        output = self.run_gh_command(command)
        
        try:
            assignments_data = json.loads(output)
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

        file_path = self.marking_root_dir / 'student_data.csv'

        # Save the DataFrame to a CSV file
        self.df_student_data.to_csv(file_path, index=False)        
        
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
        output = self.run_gh_command(command)
        
        try:
            assignment_data = json.loads(output)
            self.slug= assignment_data.get('slug')
            self.accepted = assignment_data.get('accepted') # the number of accepted submissions
            self.title = assignment_data.get('title')
            self.type = assignment_data.get('type')
            self.starter_code_repository = assignment_data.get('starter_code_repository', {}).get('full_name')
            self.deadline = assignment_data.get('deadline')
        except json.JSONDecodeError as e:
            print(f"Failed to decode JSON: {e}")
            return None

    def get_starter_repo(self):
        starter_repo_path = Path(self.assignment_dir) / "starter_repo"
        
        if starter_repo_path.exists():
            # If the starter repo directory exists, pull the latest changes
            command = f"cd {starter_repo_path} && git pull"
        else:
            # Otherwise, clone the starter repo
            command = f"gh repo clone {self.starter_code_repository} {starter_repo_path}"
        
        result = self.run_gh_command(command)
        
        if result is None:
            print("Failed to get starter repository.")
        else:
            print("Successfully cloned or pulled starter repository.")

    def get_starter_repo_mathlib(self):
        starter_repo_path = Path(self.assignment_dir) / "starter_repo"
        
        if starter_repo_path.exists():
            # If the starter repo directory exists, run leanproject get-mathlib-cache
            command = f"cd {starter_repo_path} && leanproject get-mathlib-cache"
            
            result = self.run_command(command)
            
            if result is None:
                print("Failed to get mathlib cache for starter repository.")
            else:
                print("Successfully got mathlib cache for starter repository.")
        else:
            print("Starter repository does not exist. Please clone it first.")


    def get_student_repos(self):
        student_repos_dir = Path(self.assignment_dir) / "student_repos"
        student_repos_dir.mkdir(parents=True, exist_ok=True)  # Create the directory if it doesn't exist

        commit_data_file = Path(self.assignment_dir) / "commit_data.csv"

        # Initialize DataFrame to store commit data
        if commit_data_file.exists():
            commit_data_df = pd.read_csv(commit_data_file)
        else:
            commit_data_df = pd.DataFrame(columns=['repo_full_name', 'login', 'commit_count'])

        page = 1
        per_page = 100  # max allowed value

        pbar = tqdm(total=self.accepted, desc="Getting student repos")
        while True:
            # Fetch accepted assignments from GitHub API
            command = f'gh api -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" /assignments/{self.id}/accepted_assignments?page={page}&per_page={per_page}'
            output = self.run_gh_command(command)
            
            try:
                accepted_assignments = json.loads(output)
                if not accepted_assignments:
                    break  # exit loop if no more assignments

                for assignment in accepted_assignments:
                    repo_info = assignment.get('repository', {})
                    repo_full_name = repo_info.get('full_name', '')
                    login = assignment['students'][0]['login']
                    new_commit_count = assignment.get('commit_count', 0)

                    # Check if this repo is already in the DataFrame
                    existing_row = commit_data_df.loc[commit_data_df['repo_full_name'] == repo_full_name]
                    if existing_row.empty or existing_row.iloc[0]['commit_count'] < new_commit_count:
                        # Logic to clone or pull the repo
                        student_repo_path = student_repos_dir / repo_full_name.split('/')[-1]
                        if student_repo_path.exists():
                            # Pull the repo
                            pull_command = f"cd {student_repo_path} && git pull"
                            self.run_command(pull_command)
                        else:
                            # Clone the repo
                            clone_command = f"git clone {repo_info.get('html_url', '')} {student_repo_path}"
                            self.run_command(clone_command)

                        # Update or add the row in the DataFrame
                        new_row = {'repo_full_name': repo_full_name, 'login': login, 'commit_count': new_commit_count}
                        commit_data_df = pd.concat([commit_data_df, pd.DataFrame([new_row])], ignore_index=True)
                    pbar.update(1)

                page += 1  # increment to fetch the next page

            except json.JSONDecodeError as e:
                print(f"Failed to decode JSON: {e}")
                break

        pbar.close()

        # Save updated commit data
        commit_data_df.to_csv(commit_data_file, index=False)


    def create_symlinks(self):
        student_repos_dir = Path(self.assignment_dir) / "student_repos"
        starter_repo_dir = Path(self.assignment_dir) / "starter_repo"

        for student_dir in student_repos_dir.iterdir():
            if student_dir.is_dir():
                target_link = student_dir / "_target"
                leanpkg_link = student_dir / "leanpkg.path"

                if not target_link.exists():
                    os.symlink(starter_repo_dir / "_target", target_link)
                
                if not leanpkg_link.exists():
                    os.symlink(starter_repo_dir / "leanpkg.path", leanpkg_link)

    def run_autograding(self):
        # Logic to run autograding
        # Step 0: Load the existing grades DataFrame or create a new one
        grades_file = Path(self.assignment_dir) / "grades.csv"
        if grades_file.exists():
            grades_df = pd.read_csv(grades_file)
        else:
            grades_df = pd.DataFrame(columns=['github_username', 'identifier', 'grade', 'manual_grade', 'commit_count', 'last_commit_date', 'last_commit_time', 'comment'])
            grades_df.set_index('student_identifier', inplace=True)

        # Load student repo data and commit counts
        student_data = self.load_student_data()  # Assuming you have a method to load this
        commit_counts = self.load_commit_counts()  # Assuming you have a method to load this

        # Loop through each student repo
        for student, data in student_data.items():
            commit_count = data.get('commit_count', 0)

            # Check if we should grade this repo
            if student not in grades_df.index or commit_count > grades_df.loc[student, 'commit_count']:
                # Step 1: Change directory
                repo_path = Path(self.assignment_dir) / "student_repos" / student

                # Step 2: Run the lean command
                result = subprocess.run(f"cd {repo_path} && lean .evaluate/evaluate.lean", stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

                # Step 3: Check the output
                if "sorry" not in result.stdout and "error" not in result.stdout:
                    grade = 100
                else:
                    grade = 0

                # Update the DataFrame
                grades_df.loc[student] = {
                    'github_username': data['github_username'],
                    'grade': grade,
                    'manual_grade_adjustment': None,  # Default value
                    'commit_count': commit_count,
                    'last_commit_time': data['last_commit_time'],  # Assuming you have this info
                    'comment': ''  # Default value
                }

                # Copy over manual adjustments and comments if they exist
                if student in grades_df.index:
                    grades_df.loc[student, 'manual_grade_adjustment'] = grades_df.loc[student, 'manual_grade_adjustment']
                    grades_df.loc[student, 'comment'] = grades_df.loc[student, 'comment']

        # Save the updated DataFrame
        grades_df.to_csv(grades_file)


    def update_grades(self):
        # Logic to update the df_grades DataFrame
        pass

    def save_grades_to_csv(self):
        # Logic to save grades to a CSV file
        pass

    def autograde(self):
        # High-level method to perform all autograding stepss
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
        output = self.run_gh_command(command)
        try:
            classrooms_data = json.loads(output)
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
