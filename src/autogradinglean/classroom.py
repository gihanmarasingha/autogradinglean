"""
Representation of a GitHub Classroom
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import toml

from autogradinglean.base import GitHubClassroomQueryBase

# pylint: disable=fixme

# TODO: Document the methods that
# 2) create outputs for mail merge:
# 2.1) Write to candidates with no corresponding github username (classroom level)
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
        candidate_id_col = "Candidate No"
        output_cols = ["Forename", "Surname", "Email Address"]

    Above,
    * classroom_id is the GitHub classroom id (which can be found via a GitHutClassrooms object),
    * classrooom_roster_csv is the name of the file downloaded from GitHub Classroom,
    * filename is the name of a CSV file containing student data from your institution's record system,
    * candidate_id_col is the name of the column in 'filename' that gives the GitHub student identifiers,
    * output_cols is a list of 'filename' columns that should be output by certain queries.
    """
    def __init__(self, marking_root_dir, *, debug = False):
        self.assignments = {} # Dictionary to hold GitHubAssignment objects
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
        
        self.id = self.df_classroom_roster = self.df_candidates = self.candidate_id_col = self.output_cols = None
        self.df_student_data = pd.DataFrame()

        self._queries_dir = self.marking_root_dir / "query_output"
        self.get_data_from_config_file()
        self._df_assignments = self._fetch_assignments()  # Fetch assignments on initialization

        self._initialize_assignments()  # Initialize GitHubAssignment objects

    def get_data_from_config_file(self):
        """Read config file and associated data"""

        self.logger.info("Reading config.toml file")
        config_file_path = self.marking_root_dir / "config.toml"
        config = self._load_config_from_toml(config_file_path)

        if config is None:
            msg = "Failed to load configuration. Initialization aborted."
            self.logger.error(msg)
            raise RuntimeError(msg)
        self.id = config["classroom_id"]

        classroom_roster_csv = self.marking_root_dir / config["classroom_roster_csv"]
        candidate_file = self.marking_root_dir / config["candidate_file"]["filename"]

        self.df_classroom_roster = pd.read_csv(classroom_roster_csv, dtype=object)
        self.df_candidates = pd.read_csv(candidate_file, dtype=object)

        self.candidate_id_col = config["candidate_file"]["candidate_id_col"]
        self.output_cols = config["candidate_file"]["output_cols"]
        self._merge_student_data()

    def list_assignments(self):
        """Returns the Pandas DataFrame of assignment data"""
        return self._df_assignments

    def _run_command(self, command, cwd=None):
        """Runs the specified command as a subprocess. Returns None on error or the stdout"""
        self.logger.debug("Running command %s", command)
        return GitHubClassroomQueryBase._run_command_base(command, cwd)

    def _run_gh_api_command(self, command):
        """Runs a command through the GitHub api via the `gh` CLI. This command pretty prints its ouput. Thus,
        we postprocess by removing ANSI escape codes."""
        self.logger.debug("Running command %s", command)
        return GitHubClassroomQueryBase._run_gh_api_command_base(command)

    def get_assignment_by_title(self, title):
        """Returns the first assignment with the given title (if it exists)"""
        ids =self._df_assignments[self._df_assignments['title']==title]['id']
        self.logger.debug("Trying to get assignment titled %s", title)
        return self.assignments[ids.iloc[0]]

    @property
    def queries_dir(self):
        return self._queries_dir

    def _load_config_from_toml(self,config_file_path):
        """Loads data from a toml file"""
        try:
            config = toml.load(config_file_path)
            return config
        except toml.TomlDecodeError as e:
            self.logger.addHandler(self.console_handler)
            self.logger.error("Failed to load configuration from %s: %s:", config_file_path, e)
            self.logger.removeHandler(self.console_handler)
            return None

    def _fetch_assignments(self):
        """Gets a dataframe of assignments for this classroom"""
        self.logger.info("Fetching assignments from GitHub")
        command = f"/classrooms/{self.id}/assignments"
        output = self._run_gh_api_command(command)

        try:
            assignments_data = json.loads(output)
            df_assignments = pd.DataFrame(assignments_data)
            self.save_query_output(df_assignments, "assignments")
            return df_assignments
        except json.JSONDecodeError as e:
            self.logger.addHandler(self.console_handler)
            self.logger.error("Failed to decode JSON: %s", e)
            self.logger.removeHandler(self.console_handler)
            return None

    def _merge_student_data(self):
        """Merges candidate data from a GitHub Classroom classroom roster CSV file and a CSV file
        extracted from the student record system.
        """
        # The classroom roster and student record system data are already stored in the object
        df_classroom_roster = self.df_classroom_roster
        df_candidates = self.df_candidates

        self.df_student_data = pd.merge(
            df_classroom_roster, df_candidates, left_on="identifier", right_on=self.candidate_id_col, how="outer"
        )

    def _initialize_assignments(self):
        """Create a list of assignments"""
        from autogradinglean.assignment import GitHubAssignment  # pylint: disable=import-outside-toplevel
        for _, row in self._df_assignments.iterrows():
            assignment_id = row["id"]
            new_assignment = GitHubAssignment(assignment_id, self)
            self.assignments[assignment_id] = new_assignment

    def find_missing_roster_identifiers(self):
        """
        Returns those students who appear in the student record system data but not in the classroom roster. This
        typically indicates students who enrolled since the last update of the roster.
        
        The instructor should manually adjust the classroom roster on GitHub and then update the local classroom roster.
        """
        # Rows where 'identifier' is NaN will be the ones that are in df_candidates but not in df_classroom_roster
        self.logger.info("Finding missing roster identifiers")
        mask = self.df_student_data["identifier"].isna()
        missing_roster_ids = self.df_student_data.loc[mask, [self.candidate_id_col, *self.output_cols]]
        self.save_query_output(missing_roster_ids, "missing_roster_ids", excel=True)
        return missing_roster_ids

    def find_missing_candidates(self):
        """
        Returns those students on the classroom roster who are not in the student record system data. This typically
        indicates students who have unenrolled from the course.
        
        The instructor can either:
        (1) manually update the GitHub classroom roster to remove those identifers and then update the local classroom
            roster or
        (2) just ignore the issue
        """
        # Rows where 'identifier' is NaN will be the ones that are in df_candidates but not in df_classroom_roster
        merged_df = pd.merge(self.df_classroom_roster,self.df_candidates, left_on="identifier", right_on=self.candidate_id_col, how='left', indicator=True)
        no_match_df = merged_df[merged_df['_merge'] == 'left_only']
        missing_candidates = no_match_df.drop(columns=self.df_candidates.columns.to_list() + ['_merge'])
        self.save_query_output(missing_candidates, "missing_candidates", excel=True)
        return missing_candidates

    def find_unlinked_candidates(self):
        """Returns those candidates who have not linked their GitHub account with the roster"""
        mask = self.df_student_data["github_username"].isna() & self.df_student_data[self.candidate_id_col].notna()
        unlinked_candidates = self.df_student_data.loc[mask, [self.candidate_id_col, *self.output_cols]]
        self.logger.info("Finding unlinked candidates")
        self.save_query_output(unlinked_candidates, "unlinked_candidates", excel=True)
        return unlinked_candidates
