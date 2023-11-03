"""Autograding with GitHub Classroom and Lean 3"""
import json
import logging

import pandas as pd

from .base import GitHubClassroomBase


class GitHubClassroomManager(GitHubClassroomBase):
    """A class for representing all classrooms for the current user"""
    def __init__(self):
        self.df_classrooms = pd.DataFrame()
        self.fetch_classrooms()

    def fetch_classrooms(self):
        """Get all classroom data"""
        command = "/classrooms"
        output = self.run_gh_api_command(command)
        try:
            classrooms_data = json.loads(output)
            self.df_classrooms = pd.DataFrame(classrooms_data)
        except json.JSONDecodeError as e:
            logging.error("Failed to decode JSON: %s", e)
