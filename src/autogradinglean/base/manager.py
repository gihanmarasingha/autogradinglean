"""Autograding with GitHub Classroom and Lean 3"""
import json
import logging

import pandas as pd

from autogradinglean.base.base import GitHubClassroomBase


class GitHubClassroomManager(GitHubClassroomBase):
    """A class for representing all classrooms for the current user"""

    def __init__(self):
        self.classrooms = pd.DataFrame()
        self.fetch_classrooms()

    # TODO modify the code below so it can deal with more than one page of classrooms.
    # See the functions _get_page and _get_accepted_assignments in the assignments module.
    def fetch_classrooms(self):
        """Get all classroom data"""
        command = "/classrooms"
        output = self._run_gh_api_command_base(command)
        try:
            classrooms_data = json.loads(output)
            self.classrooms = pd.DataFrame(classrooms_data)
        except json.JSONDecodeError as e:
            logging.error("Failed to decode JSON: %s", e)
            raise
