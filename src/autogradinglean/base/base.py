"""
Base classes for autograding with GitHub Classroom and Lean 3
"""
import logging  # for logging!
import re  # needed for a hack that strips `gh` output of ansi codes.
import subprocess  # runs `gh` and other commands as subprocesses
import uuid  # ensure each logger is uniquely identified
from abc import ABC, abstractmethod  # for abstract base classes
from datetime import datetime, timezone  # for attaching date and time to filenames

# pylint: disable=fixme

###################################
#
# This module performs all the interaction with GitHub, largely via the GitHub API.
# Here is documenation on querying classrooms via the API:
#
#   https://docs.github.com/en/rest/classroom/classroom
#
# The current version of the module takes a simple approach, calling GitHub's `gh` CLI.
# TODO: I plan to use the `PyGithub` package in the future. What I still need to understand is how to
# perform authentication as a GitHub App.
# Some useful reading is to be found at
#
#   https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/
#       managing-private-keys-for-github-apps
#
# and at
#
#   https://pygithub.readthedocs.io/en/stable/examples/Authentication.html#app-authentication


class GitHubClassroomBase:
    """Provides methods to be used in derived classes for running subprocess and outputing query results"""

    _ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    @staticmethod
    def _run_command_base(command, cwd=None, logger=None):
        """Runs the specified command as a subprocess. Returns the stdout of the command if it was successful, otherwise
        raises a CalledProcessError. If a logger is provided, the command is logged."""
        if logger is not None:
            logger.debug("Running command %s", command)
        result = subprocess.run(command, capture_output=True, text=True, shell=False, check=False, cwd=cwd)
        if result.returncode != 0:
            if logger is not None:
                logger.error(f"Command {command} failed with return code {result.returncode}")
            msg = f"Command {command} failed with return code {result.returncode}"
            raise RuntimeError(msg) from subprocess.CalledProcessError(
                result.returncode, command, output=result.stdout, stderr=result.stderr)
        return result.stdout

    @staticmethod
    def _run_gh_api_command_base(command, logger=None):
        """Runs a command through the GitHub api via the `gh` CLI. This command pretty prints its ouput. Thus,
        we postprocess by removing ANSI escape codes."""
        gh_api = ["gh", "api", "-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2022-11-28"]
        try:
            raw_ouput = GitHubClassroomBase._run_command_base([*gh_api, command], logger=logger)
            return GitHubClassroomBase._ansi_escape.sub("", raw_ouput)
        except RuntimeError as e:
            if logger is not None:
                logger.error(f"Failed to run GitHub API command: {e}")
            msg = "Failed to run GitHub API command."
            raise RuntimeError(msg) from e
        except TypeError as e:
            logger.debug("Encountered TypeError %s", e)
            raise


class GitHubClassroomQueryBase(ABC, GitHubClassroomBase):
    """Abstract base class for classes that output query results and performs logging"""

    @property
    @abstractmethod
    def queries_dir(self):
        """Wrapper for a property that specifies the directory for query output"""

    def save_query_output(self, df_query_output, base_name, *, excel=False):
        """Writes a dataframe as a CSV (default) or excel. The filename is formed from the basename and
        the current date and time"""
        # Generate the current date and time in the format YYMMDDHHMMSS
        current_time = datetime.now(tz=timezone.utc).strftime(r"%Y%m%d_%H%M_%S")

        # Create the filename
        if excel:
            filename = f"{base_name}{current_time}.xlsx"
        else:
            filename = f"{base_name}{current_time}.csv"

        # Create the 'queries' subdirectory if it doesn't exist
        self.queries_dir.mkdir(parents=True, exist_ok=True)

        # Full path to the output file
        file_path = self.queries_dir / filename

        # Save the DataFrame to Excel
        if excel:
            df_query_output.to_excel(file_path, index=False)
        else:
            df_query_output.to_csv(file_path, index=False, encoding = "utf-8")

    def _initialise_logger(self, logger_name, log_file, *, debug=False):
        logger = logging.getLogger(logger_name + uuid.uuid4().hex)
        if debug is True:
            logging_level = logging.DEBUG
        else:
            logging_level = logging.INFO
        logger.setLevel(logging_level)

        # Define a format for the log messages
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

        # Create a file handler for writing to log file
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Create a console handler for output to stdout
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging_level)
        console_handler.setFormatter(formatter)

        return logger, file_handler, console_handler
