"""
Representation of a GitHub Classroom
"""
import json
import os
import subprocess
from pathlib import Path
from typing import List, TYPE_CHECKING

import pandas as pd
import toml
from tqdm import tqdm  # for a progress bar

from autogradinglean.base import GitHubClassroomQueryBase

if TYPE_CHECKING:
    from autograding.assignment import GitHubAssignment

# TODO: Document the methods that
# 2) create outputs for mail merge:
# 2.1) Write to sits candidates with no corresponding github username (classroom level)
# 2.2) Write to all candidates with a github username / classroom roster link to check the link is correct
#       (classroom level)


class GitHubClassroom(GitHubClassroomQueryBase):
    """Class that encapsulates a GitHub Classroom. Contains GitHubAssignment objects
    exposes functions for reporting on unlinked candidates and other useful information.

    Configured by a toml file `config.toml` in the specified directory. The file should take the following form:

        classroom_id = "666666"
        classroom_roster_csv = "classroom_roster.csv"

        [candidate_file]
        filename = "mth9999.csv"
        student_id_col = "Candidate No"
        output_cols = ["Forename", "Surname", "Email Address"]

    Above,
    * classroom_id is the GitHub classroom id (which can be found via a GitHutClassrooms object),
    * classrooom_roster_csv is the name of the file downloaded from GitHub Classroom,
    * filename is the name of a CSV file containing student data from your institution's record system,
    * student_id_col is the name of the column in 'filename' that gives the GitHub student identifiers,
    * output_cols is a list of 'filename' columns that should be output by certain queries.
    """
    def __init__(self, marking_root_dir, *, debug = False):
        self.assignments: "List[GitHubAssignment]" = [] # List to hold GitHubAssignment objects
        self.marking_root_dir = Path(marking_root_dir).expanduser()
        # Check if marking_root_dir exists
        if not self.marking_root_dir.exists():
            msg = f"The specified marking_root_dir '{self.marking_root_dir}' does not exist."
            raise FileNotFoundError(msg)

        logger_name = "GitHubClassroom"
        log_file = self.marking_root_dir / "classroom.log"
        self.debug = debug
        self.logger, self.file_handler, self.console_handler = \
            self._initialise_logger(logger_name, log_file, debug = self.debug)

        self.logger.info("Initializing classroom object")
        self._queries_dir = self.marking_root_dir / "query_output"

        # Load configuration from TOML file

        self.logger.info("Reading config.toml file")
        config_file_path = self.marking_root_dir / "config.toml"
        config = self.load_config_from_toml(config_file_path)

        if config is None:
            msg = "Failed to load configuration. Initialization aborted."
            self.logger.error(msg)
            raise RuntimeError(msg)
        self.id = config["classroom_id"]

        # Make paths in TOML relative to marking_root_dir
        self.classroom_roster_csv = self.marking_root_dir / config["classroom_roster_csv"]
        self.sits_candidate_file = self.marking_root_dir / config["candidate_file"]["filename"]

        self.df_classroom_roster = pd.read_csv(self.classroom_roster_csv, dtype=object)
        self.df_sits_candidates = pd.read_csv(self.sits_candidate_file, dtype=object)

        self.student_id_col = config["candidate_file"]["student_id_col"]
        self.output_cols = config["candidate_file"]["output_cols"]
        # self.df_sits_candidates[self.student_id_col] = (
        #     self.df_sits_candidates[self.student_id_col].astype(int).astype(str).apply(lambda x: x.zfill(6))
        # )
        self.df_student_data = pd.DataFrame()
        self.df_assignments = self.fetch_assignments()  # Fetch assignments on initialization
        self.merge_student_data()
        self.initialize_assignments()  # Initialize GitHubAssignment objects

    @property
    def queries_dir(self):
        return self._queries_dir

    def load_config_from_toml(self,config_file_path):
        """Loads data from a toml file"""
        try:
            config = toml.load(config_file_path)
            return config
        except toml.TomlDecodeError as e:
            self.logger.addHandler(self.console_handler)
            self.logger.error("Failed to load configuration from %s: %s:", config_file_path, e)
            self.logger.removeHandler(self.console_handler)
            return None

    def fetch_assignments(self):
        """Gets a table of dataframe of assignments for this classroom"""
        self.logger.info("Fetching assignments from GitHub")
        command = f"/classrooms/{self.id}/assignments"
        output = self.run_gh_api_command(command)

        try:
            assignments_data = json.loads(output)
            df_assignments = pd.DataFrame(assignments_data)
            return df_assignments
        except json.JSONDecodeError as e:
            self.logger.addHandler(self.console_handler)
            self.logger.error("Failed to decode JSON: %s", e)
            self.logger.removeHandler(self.console_handler)
            return None

    def merge_student_data(self):
        """Merges candidate data from a GitHub Classroom classroom roster CSV file and a CSV file
        extracted from SITS.

        The columns of the classroom roster should be:

            'identifier', 'github_username', 'github_id', 'name'

        The 'identifier' should correspond with the student_id_col from the SITS spreadsheet.
        """
        # The classroom roster and SITS data are already stored in the object
        df_classroom_roster = self.df_classroom_roster
        df_sits_candidates = self.df_sits_candidates

        self.df_student_data = pd.merge(
            df_classroom_roster, df_sits_candidates, left_on="identifier", right_on=self.student_id_col, how="outer"
        )

        # file_path = self.marking_root_dir / 'student_data.csv'

        # Save the DataFrame to a CSV file
        # self.df_student_data.to_csv(file_path, index=False)

    # def update_classroom_roster(self, new_classroom_roster_csv):
    #     self.df_classroom_roster = pd.read_csv(new_classroom_roster_csv, dtype=object)

    # def update_sits_candidates(self, new_sits_candidate_file):
    #     self.df_sits_candidates = pd.read_excel(new_sits_candidate_file, dtype=object)

    def initialize_assignments(self):
        """Create a list of assignments"""
        from .assignment import GitHubAssignment
        for _, row in self.df_assignments.iterrows():
            assignment_id = row["id"]
            new_assignment = GitHubAssignment(assignment_id, self)
            self.assignments.append(new_assignment)

    def find_missing_roster_identifiers(self):
        """Returns those students who appear in the SITS data but not in the classroom roster. This typically
        indicates students who enrolled since the last update of the roster. The instructor should manually
        adjust the classroom roster on GitHub and then update the local classroom roster."""
        # Rows where 'identifier' is NaN will be the ones that are in df_sits_candidates but not in df_classroom_roster
        unmatched_candidates = self.df_student_data[self.df_student_data["identifier"].isna()]
        self.logger.info("Finding missing roster identifiers")
        return unmatched_candidates

    def find_missing_candidates(self):
        """Returns those students on the classroom roster who are not in the SITS data. This typically
        indicates students who have unenrolled from the course. The instructor can either (1) manually update
        the GitHub classroom roster to remove those identifers and then update the local classroom roster or
        (2) just ignore the issue"""
        # Rows where 'identifier' is NaN will be the ones that are in df_sits_candidates but not in df_classroom_roster
        unmatched_candidates = self.df_student_data[self.df_student_data[self.student_id_col].isna()]
        return unmatched_candidates

    def find_unlinked_candidates(self):
        """Returns those candidates who have not linked their GitHub account with the roster"""
        mask = self.df_student_data["github_username"].isna() & self.df_student_data[self.student_id_col].notna()
        unlinked_candidates = self.df_student_data.loc[mask, [self.student_id_col, *self.output_cols]]
        self.logger.info("Finding unlinked candidates")
        self.save_query_output(unlinked_candidates, "unlinked_candidates", excel=True)
