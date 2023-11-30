# Local autograding and student record integration via GitHub Classroom and GitHub Codespaces

[![PyPI - Version](https://img.shields.io/pypi/v/autogradinglean.svg)](https://pypi.org/project/autogradinglean)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/autogradinglean.svg)](https://pypi.org/project/autogradinglean)

I will describe a workflow and provide tools by which an instructor can use GitHub Classroom for performing local
autograding and manual grading, integrating the results with your student recrod system.

The tool is extensible: the instructor should write derived classes for each assessment type. I present an example
class for assessing proofs written using the Lean interactive theorem prover.

-----

**Table of Contents**

- [Installation](#installation)
- [Package Overview](#overview)
- [GitHubClassroomManager](#githubclassroommanager)
- [GitHubClassroom](#githubclassroom)
- [GitHubAssignment](#githubassignment)
- [What is GitHub Classroom?](#what-is-github-classroom)
- [Terminology](#terminology)
- [License](#license)

## Installation

```console
pip install autogradinglean
```

You will also need to install the [GitHub CLI app](https://cli.github.com), called `gh``. Authenticate the app by typing

    gh auth login

at the command prompt. Then install the [classroom extension](https://docs.github.com/en/education/manage-coursework-with-github-classroom/teach-with-github-classroom/using-github-classroom-with-github-cli) for `gh` by typing

    gh extension install github/gh-classroom


## Overview

This package consists of several classes that represent aspects of GitHub Classroom, facilitate integration with
your student record system, prepare reports on Classroom-level and assignment-level data, perform local autograding,
and enable annotation with manual marks and comments.

In this document, I use the term 'candidate' or 'candidate number' for the identifier of a student on your institution's
student record system and 'roster identifier' for the corresponding entity in GitHub Classroom. Ideally, there should be
a natural one-to-one mapping from candidates to roster identifiers! This package helps to establish such a mapping.

The classes are:

* GitHubClassroomManger: used primarily to list the classrooms owned by the current user.
* GitHubClassroom: the main class you'll interact with. It represents your (academic) class in two ways: via the
  GitHub Classroom roster and via candidate data imported from your student record system. It can report on
  'unlinked candidates': those candidates for whom there is no link between their roster identifier and their
  GitHub username. It can also find candidates who have enrolled (or unenrolled) since you set up the roster.

  This is also a container class, containing one GitHubAssignment object per assignment.
* GitHubAssignment: an abstract class that represents a GitHub Classroom assignment. Through this module, you can get the starter
  repository and the set of student repositories. You can perform local autograding, adding manual marks and comments.

  This class reports on those candidates who have not made and pushed a commit to their student repository.

  In application, you must use a derived class of GitHubAssignment that specifies the following methods

  * configure_starter_repo
  * configure_student_repos
  * _run_grading_command

  For example, you may have a derived class `GitHubAssignmentPython` suitable for grading Python assignments.

  This package provides a class `GitHubAssignmentLean3` that can be used for grading assignments that involve the Lean 3
  interactive theorem prover.

Currently, the package interacts with GitHub Classroom primarily by creating subprocesses that run the GitHub's `gh`
CLI with the classroom extension. This is why the [installation](#installation) instructions require `gh`.

Primarily, I use `gh` together with the [Classroom REST API](https://docs.github.com/en/rest/classroom/classroom?apiVersion=2022-11-28).


## GitHubClassroomManager

This is a simple wrapper around the `/classrooms` REST API call. It has only one attribute, `classrooms`. This
is a Pandas DataFrame of the GitHub classrooms for the current user.

Example use:
```
from autogradinglean import GitHubClassroomManager

rooms = GitHubClassroomManager()
rooms.classrooms
```

This is especially useful as it returns the list of classroom IDs for each classroom. These are needed for use
with the GitHubClassroom class.

### Limitations

Currently the code is limited to returning at most 30 classrooms.

## GitHubClassroom

This class represents a GitHub Classroom and the sets of candidates from your student record system.

### Configuration file

You must supply a 'classroom directory' as an argument to the constructor. In the root of this directory, there must
be a file `config.toml`. Here is a sample config file:

    [classroom_data]
    classroom_id = "999999"
    classroom_roster_csv = "classroom_roster.csv"

    [candidate_file]
    filename = "STUDENT_DATA.csv"
    candidate_id_col = "Candidate No"
    output_cols = ["Forename", "Surname", "Email Address"]

    [assignment_types]
    default = "autogradinglean.lean3.assignment.GitHubAssignmentLean3"
    assignment123123 = "my_module.PythonGrading"
    assignment536214 = "my_module.MathlabGrading"

#### Classroom data

* `classroom_id` is the identifier of the classroom, as returned by GitHubClassroomManager.
* `classroom_roster_csv` is the name of the csv file containing the GitHub Classroom roster for this classroom. At
  present, GitHub presents no API for downloading this file. You must download it manually from GitHub Classroom.
  The filename can include a path, relative to the classroom directory root.

#### Candidate file

* `filename` is the name of a csv file containing information about your students, extracted from your student record
  system. There is no required format to this file except that it must contain a column that corresponds to the
  student identifiers of the GitHub Classroom roster. As with the `classroom_roster_csv`, the filename can include a
  path relative to the classroom directory root.
* `candidate_id_col` is the name of the column in your student data file that corresponds to the roster identifier in 
  the GitHub Classroom roster.
* `output_cols` are the names of other columes in the student data file that should be included in the reporting
  methods of GitHubClassroom.

#### Assignment types

* `default` the full name of the class that will be used to grade every assignment in this classroom for which there
  is no other specified class.
* `assignmentXXXXXX` the name of the class used to grade the assignment with ID XXXXXX.


### Methods

* list_assignments(): returns a table (a Pandas DataFrame) of assigments for this classroom.
* get_data_from_config_file(): reads the configuration file and imports the referenced data from the GitHub Classroom
  roster and from your student record system. This method is called automatically on initialisation of a
  GitHubClassroom object. You *should* also call the method if your config file or any of the referenced data files
  change.
* get_assignment_by_title(ass_title): returns a GitHubAssignment whose title is ass_title. It is preferable to use
  assignment IDs rather than titles as titles can be changed.
* find_missing_roster_identifiers(): returns a DataFrame of those students who are in the candidate file but not in
  in the classroom roster. This usually indicates students who have enrolled since the roster was last updated.

  **Action**: the instructor must update the classroom roster and (if relevant) ask these candidate to choose their
  roster identifier on GitHub Classroom.
* find_missing_candidates(): returns a DataFrame of those students who are in the classroom roster but not in the
  candidate file. This generally identifies students who have been unenrolled by your institution, but have not been
  removed from the classroom roster. Usually no action is required.
* find_unlinked_candidates(): returns those candidates who have not linked their GitHub account with the roster.

  **Action**: ask these candidates to choose their roster identifier on GitHub.

### Outputs

When you instantiate an object of the `GitHubClassroom` class, the constructor creates one subdirectory of the
'classroom directory' per assignment. Each subdirectory is called assignmentXXXXXX, where XXXXXX is the assignment ID.

Many of the methods create CSV or Excel files that are stored in the `query_output` subdirectory, with a date and
time suffix to the filename. These can be safely edited or deleted as desired.

* assignmentsXXX.csv: a list of all assignments in the classroom. This is the data downloaded from GitHub Classroom and
  shows the assignment IDs, title, invite link, deadline, number of accepted students, number of submissions, number of
  passing students, and other data. This file is created each time the GitHubClassroom object is initialised.
* missing_roster_idsXXX.xlsx: created by find_missing_roster_identifiers(). Shows the candidate number and the values
  from the columns listed in output_cols.
* missing_candidatesXXX.xlsx: created by find_missing_candidates(). Shows the rows from the classroom roster for those
  students who do not appear in the candidate file.
* unlinked_candidatesXXX.xlsx: those candidates who have not yet linked their candidate number with a roster identifier.

### Logging

Actions are logged to `classroom.log`. For additional logging information, initialialse a GitHubClassroom object with
the argument `debug = True`. For example

  myclass = GitHubClassroom('myrootdir', debug=True)

### Example run

Suppose you wish to store your classroom data in a directory called `~/Documents/myclassroom`.

* First create `config.toml` file in the root of this directory, following the example above.
* Also add a classroom roster file and a candidate file in a location specified in the `config.toml`
* Open a Python interpreter and run

      from autogradinglean import GitHubClassroom
      myclass = GitHubClassroom('~/Documents/myclassroom')

  to initialise the classroom.
* Type

      myclass.list_assignments()

  to print and return a Pandas DataFrame showing the assignments for your GitHub Classroom.
* Type

      myclass.find_unlinked_candidates()

  to print and return a Pandas Dataframe showing those candidates whose roster identifier
  has not been linked with a GitHub username.

## GitHubAssignment

Each `GitHubClassroom` object has an attribute `assignments`. This is a dictionary of objects of a (derived class) of
`GitHubAssignment` objects. The objects are keyed by the assignment ID.

It offers two kinds of methods. The first kind of method facilitates autograding:

* get_starter_repo: downloads the 'starter repository' associated with this assignment.
* configure_starter_repo: performs whatever configuration is necessary. This method is abstract and should be defined
  in a derived class.
* get_student_repos: downloads all the student repositories for this assignment.
* configure_student_repos: an abstract method which should be defined in a derived class to perform any necessary
  configuration of the student repositories.
* run_autograding: runs autograding on all the student repositories that have been downloaded. This function does not
  check whether repos have been downloaded and configured.
* autograde: runs all the above methods, in order.

The second kind of method is for reporting:

* find_no_commit_candidates: find the candidates who have not made a submission for this assignment. Though the natural
  thing would be to test if 'commit_count' is zero, this doesn't always work (for reasons unbeknownst to me). That is,
  sometimes a student will commit but the commit count will be zero. Apparently, the issue has been fixed by GitHub
  Classroom.

  In any event, I will look for students where the last_commit_author is `github-classroom[bot]`.

  To ensure you have the latest data, run `get_student_repos()` before running this function.

### Outputs

All outputs are stored in the assignment directory or a subdirectory of it. The assignment directory is a subdirectory
of the classroom directory. It is named assignmentXXXXXX, where XXXXXX is the assignment ID.

* A subdirectory `starter_repo` is created when you call the `get_starter_repo()` method. This contains a
  clone of the starter repository.
* A subdirectory `student_repo` is created with you call `get_student_repos()`. This directory contains
  multiple directories, one for each student repository.

  **Note** at the time of writing, anyone with a link to the Classroom assignment URL can start a
  GitHub Classroom assignment. Thus, these student repositories need not correspond to your students!
* A file `commit_data.csv` is also created in the assignment directory each time you call `get_student_repos()`.
  This contains information about the commit count, commit times, and commit author for each of the student
  repositories. This information is used internally by successive runs of `get_student_repos()` to determine
  whether to pull or clone the student repository.
* A file `grades.csv` is created when you run `run_autograding()`. This gives the github username, auto-generated
  grade, commit count, commit date and time, last commit author and spaces for a **manual grade** and **comment**.
  Successive runs of `run_autograding()` will not change the manual grade or comment.

  The instructor should edit the `grades.csv` file manually to update manual grades and comments.
* Each run of `run_autograding()` also places into the `query_output` subdirectory a file `gradesXXX.xlsx`, where
  XXX is a date and time stamp. This Excel file combines the data from `grades.csv` with the classroom roster
  and candidate file to produce a grade list for all candidates with a linked roster identifier. It provides
  a 'final_grade' which is the maximum of the manual grade and the autograder result.
* A file `no_commitsXXX.xlsx` is placed in the `query_output` subdirectory when you run `find_no_commit_candidates()`.
  This shows those candidates who have accepted the assignment but have not yet made a commit.

### Example run

Let's suppose you have created a `GitHubClassroom` object called `myclass` in the previous example run. You ran
`myclass.list_assignments()` to get a list of the assignments. Suppose you discovered that the assignment you wish to
mark has id `123123`. You can perform all the autograding functions simply as follows:

      ass = myclass.assignments[123123]
      ass.autograde()

If more students submit after you have run the all-one-one autograde command, you can download the new repos and
grade them as follows:

      ass.get_student_repos()
      ass.configure_student_repos()
      ass.run_autograding()

To find the students who have accepted the assignment but not committed, run

      ass.find_no_commit_candidates()



## What is GitHub Classroom?

For each course, an instructor can use GitHub Classroom to create a virtual 'Classroom'.Classrooms
are filled with 'assignments'. Each assignment is a GitHub template repository (the 'starter code')
together with an optional deadline, editor, autograding test, and grade list.

Each Classroom also contains a roster: a (partial) mapping from student identifiers to GitHub usernames.

The autograding test specifies conditions under which a GitHub Actions workflow is triggered. The
workflow is used to create a grade for each student. By default, GitHub Classroom will run the
autograding tests on every push to the assignment repository. This behaviour can be customised in
the `.github/workflows/classroom.yml` of each repository. You may wish to read the read
[documentation on the syntax for this
file](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions).

### Setting up a classroom

The instructor wishing to use GitHub Classroom for autograding student submissions must first create a
[GitHub Classroom](https://classroom.github.com/classrooms) corresponding to their module. It is
recommended to create an additional classroom for testing purposes.

The Classroom roster is the mechanism by which student identifiers are linked with GitHub accounts.

**Important**: each student must have a GitHub account for this to work. Please ask students to
create a GitHub account.

To begin the creation of the roster, you must import a list of roster identifiers into your
classroom. GitHub Classroom should be able to [extract this information automatically from your
Leaning Management
System](https://docs.github.com/en/education/manage-coursework-with-github-classroom/teach-with-github-classroom/connect-a-learning-management-system-course-to-a-classroom#supported-lmses)
(e.g. Canvas, Moodle), though it first needs to be given access be the administrator of your LMS.

If that doesn't work, there is a manual alternative. Begin by getting a list of candidate identifiers,
names, and email addresses from your student record system, ideally as a CSV file.

The list of candidate identifiers can be uploaded to GitHub Classroom and used as student identifiers via the
'Update Students' in the Students tab of each classroom.

The list of students enrolled on a course may change with time as students join and leave the course. Therefore, it is
advisable to periodically reconcile the GitHub roster with your student record system. The tools provided by this
package enable this reconciliation.

### Establishing the roster mapping

Each submission of an assignment and each grade is associated with a GitHub account. For these
submissions and grades to be meaningful in an academic context, there must be a mapping between
GitHub accounts and student identifiers. The roster serves this purpose. Though the instructor can
create this mapping manually, it is simpler to leave the task to each student, as I shall now
describe.

First, create a 'test submission' assignment, as described below. Publish the URL of the assignment
(the 'invitation link') to the students on your module. When a student accepts the assignment, they
will be asked to select their roster identifier from a list of roster identifiers.

**Problem**: a student may easily select the wrong roster identifier. It is therefore incumbent on
the instructor to email each student, asking them to check that the association of roster identifier
to GitHub username is correct. Mail merge can be used for this purpose. This package helps in preparing a mail merge.


### Local versus remote autograding

In an ideal world, in order to find the grades for a particular assignment, it would be sufficient
to choose 'Download grades' from the 'Download' drop-down associated to each assignment in GitHub
Classroom. The result is a CSV file that gives, inter alia, the GitHub username, roster identifier, student repository
name, submission timestamp, and points awarded.

There are a few problems with this system:

* GitHub Classroom does not record marks for late submissions. Though the autograding workflow may
  run if a student commits after the deadline, the work will automatically receive a grade of 0.

* The autograding workflow does not always run when a student performs an action that should cause
  it to trigger.

* The GitHub Classroom autograder sometimes fails and then records a mark of zero even when the student repository
  provides a correct answer.

* You may wish to record manual marks for students and comments.


## Terminology

* **course**: a unit of academic study and assessment.
* **class**: a set of students, together with candidate identifiers provided by the record system of the students'
  educational institution.
* **classroom roster**: a representation of a class in GitHub Classroom. More precisely, a set of student identifiers
  and a partial map from this set to a set of GitHub usernames. The *intention* is that the set of student identifiers
  should corrrespond to the candidate identifiers of the class.
* **classroom**: a representation of a course in GitHub Classroom: this consists of a classroom roster and a list of   
  assignments.
* **assignment**: an assessed component within a classroom: this contains (among other things) a  starter repository, an    
  (optional) deadline, an (optional) autograding scheme to run on GitHub Clasroom, an (optional) editor.

  It also contains a set of student repositories, submission times, and associated grading information, if relevant.
* **starter repository**: a template repository used as the basis of each student repository.


## License

`autogradinglean` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
