# Autograding Lean submissions using GitHub Classroom and GitHub Codespaces

[![PyPI - Version](https://img.shields.io/pypi/v/autogradinglean.svg)](https://pypi.org/project/autogradinglean)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/autogradinglean.svg)](https://pypi.org/project/autogradinglean)

I will describe a workflow and provide tools by which an instructor can use GitHub Classroom for assessing mathematical
proof via the LEAN interactive theorem prover. Currently, this repository is designed for use with Lean 3.



-----

**Table of Contents**

- [Installation](#installation)
- [Package Overview](#overview)
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
* GitHubAssignment: an abstraction of a GitHub Classroom assignment. Through this module, you can get the starter
  repository and the set of student repositories. You can perform local autograding, adding manual marks and comments.

  This class reports on those candidates who have not made and pushed a commit to their student repository.

Currently, the package interacts with GitHub Classroom primarily by creating subprocesses that run the GitHub's `gh`
CLI with the classroom extension. This is why the [installation](#installation) instructions require `gh`.

Primarily, I use `gh` together with the [Classroom REST API](https://docs.github.com/en/rest/classroom/classroom?apiVersion=2022-11-28).


## GitHubClassroomManager

This is a simple wrapper around the `/classrooms` REST API call. It has only one property, `df_classrooms`. This
is a Pandas DataFrame of the GitHub classrooms for the current user.

Example use:
```
from autogradinglean import GitHubClassroomManager

rooms = GitHubClassroomManager()
rooms.df_classrooms
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

    classroom_id = "999999"
    classroom_roster_csv = "classroom_roster.csv"

    [candidate_file]
    filename = "STUDENT_DATA.csv"
    candidate_id_col = "Candidate No"
    output_cols = ["Forename", "Surname", "Email Address"]

* `classroom_id` is the identifier of the classroom, as returned by GitHubClassroomManager.
* `classroom_roster_csv` is the name of the csv file containing the GitHub Classroom roster for this classroom. At
  present, there is no API for downloading this file. You must download it manually from GitHub Classroom.
  The filename can include a path, relative to the classroom directory root.
* `filename` is the name of a csv file containing information about your students, extracted from your student record
  system. There is no required format to this file except that it must contain a column that corresponds to the
  student identifiers of the GitHub Classroom roster. As with the `classroom_roster_csv`, the filename can include a
  path relative to the classroom directory root.
* `candidate_id_col` is the name of the column in your student data file that corresponds to the roster identifier in 
  the GitHub Classroom roster.
* `output_cols` are the names of other columes in the student data file that should be included in the reporting
  methods of GitHubClassroom.

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

### Query output

Many of the methods create CSV or Excel files that are stored in the `query_output` subdirectory, with a date and
time suffix to the filename. These can be safely edited or deleted as desired.

* assignmentsXXX.csv: a list of all assignments in the classroom. This is the data downloaded from GitHub Classroom and
  shows the assignment IDs, title, invite link, deadline, number of accepted students, number of submissions, number of
  passing students, and other data. This file is created each time the GitHubClassroom object is initialised.
* missing_roster_idsXXX.xlsx: created by find_missing_roster_identifiers(). Shows the candidate number and the values
  from the columns listed in output_cols.
* **COMPLETE THIS**.

## GitHubAssignment


Note that the commit author can be different from the GitHub username. This can occur if:

* The user has specified their name (or some other identifier) as the author or
* the last commit was made by a bot such as `github-classroom[bot]`.

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

The instructor wishing to use GitHub Classroom for autograding LEAN submissions must first create a
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


### GitHub Classroom autograding in general

The details of autograding LEAN assignments are deferred to a later point in this article. Assuming
that a LEAN autograding mechanism has been devised for use with GitHub Classroom, what remains to be
done for the instructor to make use of the grades thereby produced?

In an ideal world, in order to find the grades for a particular assignment, it would be sufficient
to choose 'Download grades' from the 'Download' drop-down associated to each assignment. The result
is a CSV file that gives, inter alia, the GitHub username, roster identifier, student repository
name, submission timestamp, and points awarded.

There are a few problems with this system:

* GitHub Classroom does not record marks for late submissions. Though the autograding workflow may
  run if a student commits after the deadline, the work will automatically receive a grade of 0.

* The autograding workflow does not always run when a student performs an action that should cause
  it to trigger.

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
