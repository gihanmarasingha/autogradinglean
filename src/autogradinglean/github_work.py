import pandas as pd
import subprocess
import json
import re
import toml
from pathlib import Path
import os
from tqdm import tqdm # for a progress bar
from datetime import datetime

###################################
#
#  TODO, TODO, TODO, TODO, TODO, TODO, 
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


# TODO: Add methods to
# 1) create grade sheets that merge the output of the autograder with the SITS data
# 2) create outputs for mail merge:
# 2.1) Write to sits candidates with no corresponding github username (classroom level)
# 2.2) Write to all candidates with a github username / classroom roster link to check the link is correct (classroom level)
# 2.3) Write to all candidates (with a linked roster) with their grades and comments (assignment level)
# 2.4) Output all accepted users who have not selected a student ID (assignment level)


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
        
    def save_query_output(self, df_query_output, base_name, excel=False):
        # Generate the current date and time in the format YYMMDDHHMMSS
        current_time = datetime.now().strftime(r'%y%m%d%H%M%S')
        
        # Create the filename
        if excel:
            filename = f"{base_name}{current_time}.xlsx"
        else:
            filename = f"{base_name}{current_time}.csv"
        
        # Create the 'queries' subdirectory if it doesn't exist
        queries_dir = self.marking_root_dir / "query_output"
        queries_dir.mkdir(parents=True, exist_ok=True)
        
        # Full path to the output file
        file_path = queries_dir / filename
        
        # Save the DataFrame to Excel
        if excel:
            df_query_output.to_excel(file_path, index=False)
        else:
            df_query_output.to_csv(file_path, index=False)

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

        #file_path = self.marking_root_dir / 'student_data.csv'

        # Save the DataFrame to a CSV file
        #self.df_student_data.to_csv(file_path, index=False)        
        
    def update_classroom_roster(self, new_classroom_roster_csv):
        self.df_classroom_roster = pd.read_csv(new_classroom_roster_csv, dtype=object)

    def update_sits_candidates(self, new_sits_candidate_file):
        self.df_sits_candidates = pd.read_excel(new_sits_candidate_file, dtype=object)

    def initialize_assignments(self):
        for index, row in self.df_assignments.iterrows():
            assignment_id = row['id']
            new_assignment = GitHubAssignment(assignment_id, self)
            self.assignments.append(new_assignment)

    def find_missing_roster_identifiers(self):
        """Returns those students who appear in the SITS data but not in the classroom roster. This typically
        indicates students who enrolled since the last update of the roster. The instructor should manually
        adjust the classroom roster on GitHub and then update the local classroom roster."""
        # Rows where 'identifier' is NaN will be the ones that are in df_sits_candidates but not in df_classroom_roster
        unmatched_candidates = self.df_student_data[self.df_student_data['identifier'].isna()]
        return unmatched_candidates
    
    def find_missing_candidates(self):
        """Returns those students on the classroom roster who are not in the SITS data. This typically
        indicates students who have unenrolled from the course. The instructor can either (1) manually update
        the GitHub classroom roster to remove those identifers and then update the local classroom roster or
        (2) just ignore the issue"""
        # Rows where 'identifier' is NaN will be the ones that are in df_sits_candidates but not in df_classroom_roster
        unmatched_candidates = self.df_student_data[self.df_student_data['Candidate No'].isna()]
        return unmatched_candidates
    
    def find_unlinked_candidates(self):
        """Returns those candidates who have not linked their GitHub account with the roster"""
        unlinked_candidates = self.df_student_data.loc[pd.isna(self.df_student_data['github_username']) & ~pd.isna(self.df_student_data['Candidate No']), 
                     ['Candidate No', 'Forename', 'Surname', 'Email Address']]
        self.save_query_output(unlinked_candidates, 'unlinked_candidates', excel=True)


class GitHubAssignment(GitHubClassroomBase):
    def __init__(self, assignment_id, parent_classroom):
        self.id = assignment_id
        self.parent_classroom = parent_classroom  # Reference to the parent GitHubClassroom object
        self.assignment_dir = self.parent_classroom.marking_root_dir / f"assignment{self.id}"
        if not self.assignment_dir.exists():
            self.assignment_dir.mkdir(parents=True)  # Create the directory if it doesn't exist
        #self.df_grades = pd.DataFrame()  # DataFrame to hold grades
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
            commit_data_df = pd.DataFrame(columns=['student_repo_name', 'login', 'commit_count', 'last_commit_date', 'last_commit_time', 'last_commit_author'])

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

                for submission in accepted_assignments:
                    repo_info = submission.get('repository', {})
                    repo_full_name = repo_info.get('full_name', '')
                    student_repo_name = repo_full_name.split('/')[-1]
                    student_repo_path = student_repos_dir / student_repo_name
                    login = submission['students'][0]['login']
                    new_commit_count = submission.get('commit_count', 0)

                    # Check if this repo is already in the DataFrame
                    existing_row = commit_data_df.loc[commit_data_df['student_repo_name'] == student_repo_name]
                    if existing_row.empty or existing_row.iloc[0]['commit_count'] < new_commit_count:
                        # Logic to clone or pull the repo
                        if student_repo_path.exists():
                            # Pull the repo
                            pull_command = f"cd {student_repo_path} && git pull"
                            self.run_command(pull_command)
                        else:
                            # Clone the repo
                            clone_command = f"git clone {repo_info.get('html_url', '')} {student_repo_path}"
                            self.run_command(clone_command)

                        # TODO: think about how the following is affected by different time zones and locales.
                        git_log_command = f"cd {student_repo_path} && git log -1 --format='%cd,%an' --date=format-local:'%d/%m/%y,%H:%M:%S' src/assignment.lean"
                        git_log_result = self.run_command(git_log_command)

                         # Update or add the row in the DataFrame
                        new_row = {'student_repo_name': student_repo_name, 'login': login, 'commit_count': new_commit_count}

                        if git_log_result:
                            last_commit_date, last_commit_time, last_commit_author = git_log_result.strip().split(',')
                            new_row['last_commit_date'] = last_commit_date
                            new_row['last_commit_time'] = last_commit_time
                            new_row['last_commit_author'] = last_commit_author

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
            df_grades = pd.read_csv(grades_file)
        else:
            df_grades = pd.DataFrame(columns=['github_username', 'grade', 'commit_count', 'last_commit_date', 'last_commit_time', 'last_commit_author', 'manual_grade', 'comment'])
            #df_grades.set_index('student_identifier', inplace=True)

        # Load student repo data and commit counts
        # ASSUMES WE HAVE RECENTLY RUN `get_student_repos`
        commit_data_file = Path(self.assignment_dir) / "commit_data.csv"
        commit_data_df = pd.read_csv(commit_data_file)

        pbar = tqdm(total=self.accepted, desc="Autograding student repos")
        # Loop through each student repo
        for index, row in commit_data_df.iterrows():
            commit_count = row.get('commit_count', 0)
            login = row['login']
            student_repo_name = row['student_repo_name']
            # Check if this login exists in df_grades
            existing_row = df_grades.loc[df_grades['github_username'] == login]

            # Check if we should proceed with grading
            if existing_row.empty or existing_row.iloc[0]['commit_count'] < commit_count:
                # Do some grading!
                #print(f"Grading for {login} with commit_count {commit_count}")
                repo_path = Path(self.assignment_dir) / "student_repos" / student_repo_name

                # Step 2: Run the lean command
                result = subprocess.run(f"cd {repo_path} && lean .evaluate/evaluate.lean", stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

                # Step 3: Check the output
                if "sorry" not in result.stdout and "error" not in result.stdout:
                    grade = 100
                else:
                    grade = 0

                # Update the DataFrame
                # TODO: think carefully about what happens if a student makes a commit after the deadline. There are several possibilities:
                # 1) The student made no commit before the deadline. Then this counts as their only commit. The Hub can determine what mark should be awarded.
                # 2) The student made a commit before the deadline *and* after the deadline.
                #   The fairest resolution might be to start by grading the last submission before the deadline. If (on the advice of the Hub),
                #   mitigation is given, then a chosen submission after the deadline should be marked.
                #   If we go down this route, I'll have to think about how to represent the grades in the DataFrame.
                last_commit_date = row.get('last_commit_date')
                last_commit_time = row.get('last_commit_time')
                last_commit_author = row.get('last_commit_author')

                new_row = {'github_username': login, 'grade': grade, 'commit_count': commit_count, 'last_commit_date': last_commit_date, 'last_commit_time': last_commit_time, 'last_commit_author': last_commit_author}

                if existing_row.empty:
                    # Append new row with default values for manual_grade and comment
                    new_row['manual_grade'] = None
                    new_row['comment'] = None
                    df_grades = pd.concat([df_grades, pd.DataFrame([new_row])], ignore_index=True)
                else:
                    # Update existing row without modifying manual_grade and comment
                    existing_index = existing_row.index[0]
                    for key, value in new_row.items():
                        df_grades.at[existing_index, key] = value
            pbar.update(1)

        pbar.close()
        # Save the updated DataFrame
        df_grades.to_csv(grades_file, index=False)


    #def update_grades(self):
        # Logic to update the df_grades DataFrame
    #    pass

    #def save_grades_to_csv(self):
        # Logic to save grades to a CSV file
    #    pass

    def autograde(self):
        # High-level method to perform all autograding stepss
        self.get_starter_repo()
        self.get_starter_repo_mathlib()
        self.get_student_repos()
        self.create_symlinks()
        self.run_autograding()
        #self.update_grades()
        #self.save_grades_to_csv()


    def find_no_commit_candidates(self):
        """Find the candidates who have not made a submission for this assignment"""


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
