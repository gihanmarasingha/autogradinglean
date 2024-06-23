# Package design

TODO: finish this document!

## Base module

The module `base` defines all the main base classes.

### GitHubClassroomBase

The root class is `GitHubClassroomBase`. It defines two protected 
static methods[^1].

* `_run_command_base(command, cwd=None, logger=None)`: used to run a `command` as a subprocess with `cwd` as the
  working directory. On an error, messages are logged to `logger` and a `RuntimeError` exception is raised.
* `_run_gh_api_command_base(command, logger=None)`. A wrapper around `_run_command_base` that uses `gh` (the GitHub
  CLI app) to make a GitHub API call `command`. Error handling as in `_run_command_base`.


### GitHubClassroomQueryBase

Most classes in this package output pandas query results and perform more advanced logging.
The abstract base class `GitHubClassroomQueryBase` that derives from `GitHubClassroomBase` provides these facilities.

The class defines:

* `queries_dir`: this method is marked with the `@abstract_method`[^2] and `@property`[^3] decorators and denotes the
  directory in which query results are stored.
* `save_query_output(self, df_query_output, base_name, *, excel=False)`: this saves a pandas DataFrame `df_query_output`
    to a file whose name is of the form `{base_name}{current_time}.csv` (or `{base_name}{current_time}.xlsx` if
    `excel==True`) in the `queries_dir` directory. The current time (and date) is in UTC and is of the form
    "%Y%m%d_%H%M_%S" (yyyymmdd_hhmm_ss).
* `_initialise_logger(self, logger_name, log_file, *, debug=False)`: this method should be called from the constructor
  of a derived class. It returns an object `logger`, a `file_handler` for writing to a log file and a `console_handler`
  for writing to stdout.

## Manager module

This simple module defines only the class `GitHubClassroomManager`, which derives from `GitHubClassroomBase`. Its
constructor calls a method `fetch_classrooms` that updates the attribute `classroom` with all the classrooms associated
with the user.

## Classroom module

This is a Python representation of a GitHub classroom. 

[^1]: A static method is one that is bound to the class, not to any instance of the class.
[^2]: An abstract method of an abstract base class is one that *must* be defined in any derived class.
[^3]: Using the property decorator allows the method to be accessed as an attribute, obviating the need for explicit 'getter' and 'setter' functions.
