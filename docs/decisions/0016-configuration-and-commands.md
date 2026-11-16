# 0016: Configuration and commands

Date: 2026-11-16. Status: accepted.

## Context

The programs read two kinds of configuration. Setups and index specs are TOML files in the
repository, and `setups check` checks them (architecture, section 4.1). The deployment
configuration names what a deployment serves, and the programs read it when they start
(architecture, section 6.2). When a program skips a key with a typo, the deployment runs
differently than its configuration says, and nobody notices.

The batch tools run from cron on the serving node and as jobs on the cluster, which can
preempt a job or end it at its time limit (decision 0005). Whoever starts them needs to
know whether a run failed for good or can simply run again.

## Decision

Configuration:

- Every configuration file is TOML. Its content is checked by pydantic models that all
  inherit one base class with `extra="forbid"` and `frozen=True`, nested models included.
  Lists and tables in them are tuples and read-only mappings. An unknown key is an error,
  and the loaded configuration cannot change while the program runs.
- Every step type and every index builder in the registry has its own model of
  parameters. The setup loader takes `type`, `input` and `inputs` out of each table
  `[steps.*]` and checks the rest against the model of the type. `setups check` therefore
  needs no list of keys of its own.
- The loader collects the errors of the whole content and reports them together. A syntax
  error stops the reading at the first one.
- A program finds its deployment configuration through the option `--config` of its main
  command, or else through the environment variable `EXPLORER_CONFIG`. Without either, it
  stops with a configuration error.
- Secrets, such as the key of e-INFRA or the password of the database, come only from
  environment variables with the prefix `EXPLORER_`, never from a file in the repository.
  In the code they have the type `SecretStr`, which prints as stars. A variable with the
  prefix that the program does not know is an error, so a typo in the name of a secret
  does not pass.
- Our settings come from no other environment variable. The boundary modules (decision
  0015) pass every setting the configuration names, such as the full address of the
  database, so `PGHOST` or a similar variable of a library cannot redirect them. Variables
  of libraries apply only where the configuration says nothing: a proxy, the cache folder
  of models, the GPUs that SLURM assigns.
- A configuration with errors raises `ConfigurationError` and the program stops when it
  starts (decision 0014). The API checks at start the setups its deployment configuration
  names, the default and the fallback. Other setups are checked when they are first used.

Commands:

- Each program is one console command with subcommands, written with typer:
  `explorer-api`, `explorer-batch` and `explorer-eval`. The commands `eval run` and
  `setups check` of the architecture are `explorer-eval run` and
  `explorer-eval setups check`. Every program has a main callback, so that typer keeps the
  subcommands even when a program has only one.
- Exit codes: 0 when done, 1 after a programming error, and 2 after a wrong call of the
  command, as Python and typer set them. From the convention `sysexits`, 75 means
  a passing failure, so a later run can succeed (`Unavailable` of decision 0014, or a run
  stopped by a signal), and 78 means a configuration error, so another run does not help.
  A process killed by a signal ends with 128 plus the number of the signal, such as 137
  after SIGKILL or 143 after SIGTERM. Scripts run a command again after 75 or a code
  above 128, and leave it to a person after 1, 2 or 78.
- A batch command works in small units and records each unit when it is saved. The next
  run skips the saved units and does the rest. A unit is saved whole or not at all:
  - In the database it is one transaction.
  - A file is written to a temporary file in the same folder, flushed to disk and renamed.
    The next run deletes temporary files that a killed run left behind.
  - When a unit writes a file and a row that refers to it, the file comes first. A file
    without its row is harmless and the next run writes it again.
- SIGTERM and SIGINT (Ctrl+C) do the same: the command drops the units that have not
  started, finishes the units in progress and exits with 75. A unit has to be short enough
  to finish within the time before the kill: the stop grace period of Docker, 10 s by
  default, or the time that `sbatch --signal` gives before the time limit of a job.
- Each run of a batch command is recorded in the catalog with its outcome (architecture,
  section 4.2). The next run of the same command closes a run that has a start and no end
  as interrupted. Two runs of the same command never overlap: a run that finds another
  one active exits with 75.

## Consequences

- An operator finds every setting of a deployment in one file, and a typo stops the
  program with the place of the error.
- cron and the job scripts on the cluster decide from the exit code whether to run
  a command again.
- A preempted job may be killed right after SIGTERM, because the grace time of SLURM is
  zero by default. Then at most the units in progress are lost.
- Windows does not deliver SIGTERM to a Python program as a signal it can catch, so tests
  of stopping run in a Linux container or skip on Windows.
- Jobs on the cluster that need a secret get it in a file readable only by their user,
  because other users or the job listing of PBS can see environment variables.
- typer is still a beta (version 0.29) and carries its own copy of the code of click, on
  which it used to depend. Moving to click would mean rewriting the definitions of the
  commands, which are small.
- pydantic and typer come into the packages with their first code.

## Alternatives considered

- **pydantic-settings.** It reads settings from environment variables by itself, but
  according to its documentation it skips an environment variable whose name does not
  match any setting. Rejecting unknown `EXPLORER_*` variables would need our own check
  anyway, and a few secrets do not need the library.
- **Environment variables for every setting.** The settings of a deployment would be
  spread over the environment of each container instead of one file.
- **argparse.** It is in the standard library, but it returns values without types, which
  strict type checking cannot follow.
- **click.** It is stable, but each option is written twice: in a decorator with its type,
  and in the signature of the function.
