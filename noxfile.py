"""Nox configuration file for running tests, linting, and type checking.

This file is used to define the sessions that Nox will run. Nox is a Python
automation tool that allows you to run tests, linters, and other tasks in
isolated virtual environments.

This configuration is set up to run tests using pytest, check code style with
flake8, and ensure type safety with mypy.
"""

# Third-Party
import nox

# Define the Python versions to use for the sessions
python_versions = ["3.12"]

# Define the Nox sessions to run
nox.options.sessions = ["test_and_lint"]

# Reuse existing virtual environments to speed up the process
nox.options.reuse_existing_virtualenvs = True


@nox.session(python=python_versions, venv_backend="venv")
def test_and_lint(session):
    # Install dependencies
    session.run("python", "-m", "pip", "install", "--upgrade", "pip")
    session.install("poetry")
    session.run("poetry", "lock")
    session.run("poetry", "install")

    # Run tests with coverage
    session.run(
        "poetry",
        "run",
        "pytest",
        "-s",
        "--cov-report",
        "term-missing",
        "--cov=.",
        "tests/unit",
    )

    # Run code linting with flake8
    session.run("flake8", "src")
