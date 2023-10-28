# Autograding Lean submissions using GitHub Classroom and GitHub Codespaces

[![PyPI - Version](https://img.shields.io/pypi/v/autogradinglean.svg)](https://pypi.org/project/autogradinglean)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/autogradinglean.svg)](https://pypi.org/project/autogradinglean)

I will describe a workflow and provide tools by which an instructor can use GitHub Classroom for
assessing mathematical proof via the LEAN interactive theorem prover. I use the term 'module' to
refer to a unit of academic study and assessment, this term being common in the UK. In the US, the
word 'course' is typically used to refer to the same concept. For consistency with GitHub, I use the
term 'grade' to refer to the mark a student receives on an assignment, though the term 'mark' is
more common in the UK.

-----

**Table of Contents**

- [Installation](#installation)
- [License](#license)

## Installation

```console
pip install autogradinglean
```


## What is GitHub Classroom?

For each module, an instructor can use GitHub Classroom to create a virtual 'Classroom'. Classrooms
are filled with 'assignments'. Each assignment is a GitHub template repository (the 'starter code')
together with an optional deadline, editor, autograding test, and grade list.

Each Classroom also contains a roster: a (partial) mapping from student identifiers (henceforth
'roster identifiers') to GitHub usernames.

The autograding test specifies conditions under which a GitHub Actions workflow is triggered. The
workflow is used to create a grade for each student. By default, GitHub Classroom will run the
autograding tests on every push to the assignment repository. This behaviour can be customised in
the `.github/workflows/classroom.yml` of each repository. You may wish to read the read
[documentation on the syntax for this
file](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions).

In my practice, I ensure the autograding workflow runs when there is a push involving
`src/assignment.lean`. I also add the `workflow_dispatch` trigger. This enables me to autograde a
student repo on demand.

## Setting up a classroom

The instructor wishing to use GitHub Classroom for autograding LEAN submissions must first create a
[GitHub Classroom](https://classroom.github.com/classrooms) corresponding to their module. It is
recommended to create an additional classroom for testing purposes.

The Classroom roster is the mechanism by which roster identifiers are linked with GitHub accounts.

**Important**: each student must have a GitHub account for this to work. Please ask students to
create a GitHub account.

To begin the creation of the roster, you must import a list of roster identifiers into your
classroom. GitHub Classroom should be able to [extract this information automatically from your
Leaning Management
System](https://docs.github.com/en/education/manage-coursework-with-github-classroom/teach-with-github-classroom/connect-a-learning-management-system-course-to-a-classroom#supported-lmses)
(e.g. Canvas, Moodle), though it first needs to be given access be the administrator of your LMS.

If that doesn't work, there is a manual alternative. Begin by getting a list of student identifiers,
names, email addresses, or candidate numbers from your student record system, ideally as a CSV file.
These can be uploaded to GitHub Classroom and used as roster identifiers via 'Update Students' in
the Students tab of each classroom.

The list of students on a module may change with time. Therefore, it is advisable to periodically
reconcile the GitHub roster with your student record system. To do this, first download the GitHub
Classroom roster as a CSV file using the 'Download' button in the 'Students' tab of your classroom,
then use a tool such as Excel to find differences between the roster and the list of students
provided by your institution's student record system.

**I SHOULD WRITE A SCRIPT TO DO THIS**


## Establishing the roster mapping

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
to GitHub username is correct. Mail merge can be used for this purpose.


## GitHub Classroom autograding in general

The details of autograding LEAN assignments are deferred to a later point in this article. Assuming
that a LEAN autograding mechanism has been devised for use with GitHub Classroom, what remains to be
done for the instructor to make use of the grades thereby produced?

In an ideal world, in order to find the grades for a particular assignment, it would be sufficient
to choose 'Download grades' from the 'Download' drop-down associated to each assignment. The result
is a CSV file that gives, inter alia, the GitHub username, roster identifier, student repository
name, submission timestamp, and points awarded.

There are (at least) two problems with this system:

* GitHub Classroom does not record marks for late submissions. Though the autograding workflow may
  run if a student commits after the deadline, the work will automatically receive a grade of 0.

* The autograding workflow does not always run when a student performs an action that should cause
  it to trigger.


One solution to these problems is to clone all the student repositories associated with an
assignment via the [GitHub CLI app](https://cli.github.com), called gh. First install this, then
install the [classroom
extension](https://docs.github.com/en/education/manage-coursework-with-github-classroom/teach-with-github-classroom/using-github-classroom-with-github-cli)
for gh.

At the time of writing, the first step is to set up authentication with your GitHub account via

    gh auth login

then install the extension by typing

    gh extension install github/gh-classroom

Then, you can download student repositories using

    gh classroom clone student-repos

as described in the link above. In my experience, it takes approximately 2 seconds to download one
student repository

The student repos will contain information of the last commit date (if any), which can be used for
dealing semi-manually with late submissions.

Likewise, the autograding workflow can be triggered manually from each downloaded student
repository.

## Scripts

Local autograding can be accomplished using the scripts in this repository.

### Getdates

[getdates](scripts/getdates) should be run in the directory that contains the student repositories.
It produces a CSV files called `submit_dates.csv` in the current directory. The columns are: GitHub
username, date of last commit, time of last commit, and commit author.

Note that the commit author can be different from the GitHub username. This can occur if:

* The user has specified their name (or some other identifier) as the author or
* the last commit was made by a bot such as `github-classroom[bot]`.

### TOBENAMED

Consider the difference between a downloaded student repository and a working Lean 3 project. The
functioning project will additionally contain a `leanpkg.path` file used to specify the paths of
`.lean` and `.olean` files, including dependencies such as mathlib. The working project will also
contain a `_target` directory containing and dependencies.

## License

`autogradinglean` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
