
#!/usr/bin/env python3

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2018 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2014 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2016 Masaki Hara <ackie.h.gmai@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os
import tempfile
from functools import reduce

from cms import config, rmtree
from cms.db import Executable
from cms.grading.ParameterTypes import ParameterTypeChoice, ParameterTypeInt
from cms.grading.Sandbox import wait_without_std, Sandbox
from cms.grading.languagemanager import LANGUAGES, get_language
from cms.grading.steps import compilation_step, evaluation_step_before_run, \
    evaluation_step_after_run, extract_outcome_and_text, \
    human_evaluation_message, merge_execution_stats, trusted_step
from cms.grading.steps.evaluation import EVALUATION_MESSAGES
from cms.grading.tasktypes import check_files_number
from . import TaskType, check_executables_number, check_manager_present, \
    create_sandbox, delete_sandbox, is_manager_for_compilation


logger = logging.getLogger(__name__)


# Dummy function to mark translatable string.
def N_(message):
    return message


class Kattis(TaskType):
    """Task type class for tasks with a fully admin-controlled process.

    The task type will run *manager*, an admin-provided executable, and one or
    more instances of the user solution, optionally compiled together with a
    language-specific stub.

    During the evaluation, the manager and each of the user processes
    communicate via FIFOs. The manager will read the input, send it (possibly
    with some modifications) to the user process(es). The user processes, either
    via functions provided by the stub or by themselves, will communicate with
    the manager. Finally, the manager will decide outcome and text, and print
    them on stdout and stderr.

    The manager reads the input from stdin and writes to stdout and stderr the
    standard manager output (that is, the outcome on stdout and the text on
    stderr, see trusted.py for more information). It receives as argument the
    names of the fifos: first from and to the first user process, then from and
    to the second user process, and so on. It can also print some information
    to a file named "output.txt"; the content of this file will be shown to
    users submitting a user test.

    The user process receives as argument the fifos (from and to the manager)
    and, if there are more than one user processes, the 0-based index of the
    process. The pipes can also be set up to be redirected to stdin/stdout: in
    that case the names of the pipes are not passed as arguments.

    """
    # Filename of the manager (the stand-alone, admin-provided program).
    MANAGER_FILENAME = "manager"
    # Filename of the input in the manager sandbox. The content will be
    # redirected to stdin, and managers should read from there.
    INPUT_FILENAME = "input.txt"
    # Filename where the manager can write additional output to show to users
    # in case of a user test.
    ANSWER_FILENAME = "answer.txt"

    # Constants used in the parameter definition.
    COMPILATION_ALONE = "alone"
    USER_IO_FIFOS = "fifo_io"

    IS_INTERACTIVE = "interactive"
    IS_NONINTERACTIVE = "non-interactive"

    ALLOW_PARTIAL_SUBMISSION = False

    _INTERACTIVE= ParameterTypeChoice(
        "Interactive",
        "interactive",
        "",
        {IS_INTERACTIVE: "The program is run with an interactive validator",
         IS_NONINTERACTIVE: "The program is run without an interactive validator"})


    ACCEPTED_PARAMETERS = [_INTERACTIVE]

    @property
    def name(self):
        """See TaskType.name."""
        return "Kattis"

    def __init__(self, parameters):
        super().__init__(parameters)

        if self.parameters[0] == "interactive":
            self.interactive = True
        else:
            self.interactive = False

    def get_compilation_commands(self, submission_format):
        """See TaskType.get_compilation_commands."""
        codenames_to_compile = []
        if self._uses_stub():
            codenames_to_compile.append(self.STUB_BASENAME + ".%l")
        codenames_to_compile.extend(submission_format)
        res = dict()
        for language in LANGUAGES:
            source_ext = language.source_extension
            executable_filename = self._executable_filename(submission_format,
                                                            language)
            res[language.name] = language.get_compilation_commands(
                [codename.replace(".%l", source_ext)
                 for codename in codenames_to_compile],
                executable_filename)
        return res

    def get_user_managers(self):
        return []

    def get_auto_managers(self):
        """See TaskType.get_auto_managers."""
        return [self.MANAGER_FILENAME]

    def _uses_stub(self):
        return False

    def _uses_fifos(self):
        return True

    @staticmethod
    def _executable_filename(codenames, language):
        """Return the chosen executable name computed from the codenames.

        codenames ([str]): submission format or codename of submitted files,
            may contain %l.
        language (Language): the programming language of the submission.

        return (str): a deterministic executable name.

        """
        name = "_".join(sorted(codename.replace(".%l", "")
                               for codename in codenames))
        return name + language.executable_extension

    def compile(self, job, file_cacher):
        """See TaskType.compile."""
        language = get_language(job.language)
        source_ext = language.source_extension

        if not check_files_number(job, 1, or_more=True):
            return

        # Prepare the files to copy in the sandbox and to add to the
        # compilation command.
        filenames_to_compile = []
        filenames_and_digests_to_get = {}
        # User's submitted file(s) (copy and add to compilation).
        for codename, file_ in job.files.items():
            filename = codename.replace(".%l", source_ext)
            filenames_to_compile.append(filename)
            filenames_and_digests_to_get[filename] = file_.digest

        # Prepare the compilation command
        executable_filename = self._executable_filename(job.files.keys(),
                                                        language)
        commands = language.get_compilation_commands(
            filenames_to_compile, executable_filename)

        # Create the sandbox.
        sandbox = create_sandbox(file_cacher, name="compile")
        job.sandboxes.append(sandbox.get_root_path())

        # Copy all required files in the sandbox.
        for filename, digest in filenames_and_digests_to_get.items():
            sandbox.create_file_from_storage(filename, digest)

        # Run the compilation.
        box_success, compilation_success, text, stats = \
            compilation_step(sandbox, commands)

        # Retrieve the compiled executables.
        job.success = box_success
        job.compilation_success = compilation_success
        job.text = text
        job.plus = stats
        if box_success and compilation_success:
            digest = sandbox.get_file_to_storage(

                                executable_filename,
                "Executable %s for %s" % (executable_filename, job.info))
            job.executables[executable_filename] = \
                Executable(executable_filename, digest)

        # Cleanup.
        delete_sandbox(sandbox, job.success, job.keep_sandbox)

    def _extract_outcome(self, stats, feedbackdir):
        exit_code = stats["exit_code"]

        score_multiplier_file = os.path.join(feedbackdir, 'score_multiplier.txt')

        outcome = None
        text = None

        if exit_code not in [42, 43]:
            return None, None

        text = EVALUATION_MESSAGES.get("wrong").message

        if exit_code == 43:
            outcome = 0.0
        elif os.path.isfile(score_multiplier_file):
            outcome = float(open(score_multiplier_file).read())
            if outcome > 0.0 and outcome < 1.0:
                text = EVALUATION_MESSAGES.get("partial").message
            else:
                text = EVALUATION_MESSAGES.get("success").message
        else:
            text = EVALUATION_MESSAGES.get("success").message
            outcome = 1.0

        return outcome, [text]

    def _get_results(self, feedback_dir, sandbox_user, sandbox_mgr, job):
        # Get the results of the manager sandbox.
        box_success_mgr, evaluation_success_mgr, stats_mgr = \
            evaluation_step_after_run(sandbox_mgr)

        if box_success_mgr and stats_mgr["exit_code"] in [42, 43]:
            evaluation_success_mgr = True

        # Coalesce the results of the user sandboxes.
        user_result = evaluation_step_after_run(sandbox_user)
        box_success_user = user_result[0]
        evaluation_success_user = user_result[1]
        stats_user = user_result[2]

        success = box_success_user \
            and box_success_mgr and evaluation_success_mgr
        outcome = None
        text = None

        # If at least one sandbox had problems, or the manager did not
        # terminate correctly, we report an error (and no need for user stats).
        if not success:
            stats_user = None

        # If just asked to execute, fill text and set dummy outcome.
        elif job.only_execution:
            outcome = 0.0
            text = [N_("Execution completed successfully")]

        # If the user sandbox detected some problem (timeout, ...),
        # the outcome is 0.0 and the text describes that problem.
        elif not evaluation_success_user:
            outcome = 0.0
            text = human_evaluation_message(stats_user)

        # Otherwise, we use the manager to obtain the outcome.
        else:
            outcome, text = self._extract_outcome(stats_mgr, feedback_dir)

        # If asked so, save the output file with additional information,
        # provided that it exists.
        # if job.get_output:
        #     if sandbox_mgr.file_exists(self.OUTPUT_FILENAME):
        #         job.user_output = sandbox_mgr.get_file_to_storage(
        #             self.OUTPUT_FILENAME,
        #             "Output file in job %s" % job.info,
        #             trunc_len=100 * 1024)
        #     else:
        #         job.user_output = None

        # Fill in the job with the results.
        job.success = success
        job.outcome = "%s" % outcome if outcome is not None else None
        job.text = text
        job.plus = stats_user
        
    def _evaluate_interactive(self, job, file_cacher):
        """See TaskType.evaluate."""
        if not check_executables_number(job, 1):
            return
        executable_filename = next(iter(job.executables.keys()))
        executable_digest = job.executables[executable_filename].digest

        # Make sure the required manager is among the job managers.
        if not check_manager_present(job, self.MANAGER_FILENAME):
            return
        manager_digest = job.managers[self.MANAGER_FILENAME].digest

        # Create FIFOs.
        fifo_dir = tempfile.mkdtemp(dir=config.temp_dir)
        fifo_user_to_manager = os.path.join(fifo_dir, "u_to_m")
        fifo_manager_to_user = os.path.join(fifo_dir, "m_to_u")

        os.mkfifo(fifo_user_to_manager)
        os.mkfifo(fifo_manager_to_user)
        os.chmod(fifo_dir, 0o755)
        os.chmod(fifo_user_to_manager, 0o666)
        os.chmod(fifo_manager_to_user, 0o666)

        # Names of the fifos after being mapped inside the sandboxes.
        sandbox_fifo_dir = "/fifo"
        sandbox_fifo_user_to_manager = os.path.join(sandbox_fifo_dir, "u_to_m")
        sandbox_fifo_manager_to_user = os.path.join(sandbox_fifo_dir, "m_to_u")

        # Create feedback dir
        feedback_dir = tempfile.mkdtemp(dir=config.temp_dir)
        os.chmod(feedback_dir, 0o777)
        sandbox_feedback_dir = "/feedback"

        # Create the manager sandbox and copy manager and input.
        sandbox_mgr = create_sandbox(file_cacher, name="manager_evaluate")
        job.sandboxes.append(sandbox_mgr.get_root_path())
        sandbox_mgr.create_file_from_storage(
            self.MANAGER_FILENAME, manager_digest, executable=True)
        sandbox_mgr.create_file_from_storage(
            self.INPUT_FILENAME, job.input)
        sandbox_mgr.create_file_from_storage(
            self.ANSWER_FILENAME, job.output)

        # Create the user sandbox(es) and copy the executable.
        sandbox_user = create_sandbox(file_cacher, name="user_evaluate")
        job.sandboxes.extend(sandbox_user.get_root_path())

        sandbox_user.create_file_from_storage(
            executable_filename, executable_digest, executable=True)

        # Start the manager. Redirecting to stdin is unnecessary, but for
        # historical reasons the manager can choose to read from there
        # instead than from INPUT_FILENAME.
        manager_command = [
            "./%s" % self.MANAGER_FILENAME, 
            self.INPUT_FILENAME,
            self.ANSWER_FILENAME,
            sandbox_feedback_dir
        ]

        # We could use trusted_step for the manager, since it's fully
        # admin-controlled. But trusted_step is only synchronous at the moment.
        # Thus we use evaluation_step, and we set a time limit generous enough
        # to prevent user programs from sending the manager in timeout.
        # This means that:
        # - the manager wall clock timeout must be greater than the sum of all
        #     wall clock timeouts of the user programs;
        # - with the assumption that the work the manager performs is not
        #     greater than the work performed by the user programs, the manager
        #     user timeout must be greater than the maximum allowed total time
        #     of the user programs; in theory, this is the task's time limit,
        #     but in practice is num_processes times that because the
        #     constraint on the total time can only be enforced after all user
        #     programs terminated.
        manager_time_limit = max(job.time_limit + 1.0,
                                 config.trusted_sandbox_max_time_s)
        manager = evaluation_step_before_run(
            sandbox_mgr,
            manager_command,
            manager_time_limit,
            config.trusted_sandbox_max_memory_kib * 1024,
            dirs_map = {
                fifo_dir: (sandbox_fifo_dir, "rw"),
                feedback_dir: (sandbox_feedback_dir, "rw")
            },
            stdin_redirect=sandbox_fifo_user_to_manager,
            stdout_redirect=sandbox_fifo_manager_to_user,
            multiprocess=job.multithreaded_sandbox)

        # Start the user submission compiled with the stub.
        language = get_language(job.language)
        main = os.path.splitext(executable_filename)[0]
        process = None

        args = []
        stdin_redirect = None
        stdout_redirect = None

        commands = language.get_evaluation_commands(
            executable_filename,
            main=main,
            args=args)
        # Assumes that the actual execution of the user solution is the
        # last command in commands, and that the previous are "setup"
        # that don't need tight control.
        if len(commands) > 1:
            trusted_step(sandbox_user[i], commands[:-1])
        process = evaluation_step_before_run(
            sandbox_user,
            commands[-1],
            job.time_limit,
            job.memory_limit,
            dirs_map={fifo_dir: (sandbox_fifo_dir, "rw")},
            stdin_redirect=sandbox_fifo_manager_to_user,
            stdout_redirect=sandbox_fifo_user_to_manager,
            multiprocess=job.multithreaded_sandbox)

        # Wait for the processes to conclude, without blocking them on I/O.
        wait_without_std([process, manager])

        self._get_results(feedback_dir, sandbox_user, sandbox_mgr, job)

        delete_sandbox(sandbox_mgr, job.success, job.keep_sandbox)
        delete_sandbox(sandbox_user, job.success, job.keep_sandbox)
        if job.success and not config.keep_sandbox and not job.keep_sandbox:
            rmtree(fifo_dir)
            rmtree(feedback_dir)


    def _evaluate_noninteractive(self, job, file_cacher):
        """See TaskType.evaluate."""
        if not check_executables_number(job, 1):
            return
        executable_filename = next(iter(job.executables.keys()))
        executable_digest = job.executables[executable_filename].digest

        # Make sure the required manager is among the job managers.
        if not check_manager_present(job, self.MANAGER_FILENAME):
            return
        manager_digest = job.managers[self.MANAGER_FILENAME].digest

        output_dir = tempfile.mkdtemp(dir=config.temp_dir)
        os.chmod(output_dir, 0o777)
        sandbox_output_dir = "/output"
        sandbox_output_filename = os.path.join(sandbox_output_dir, "output.txt")

        # Create the user sandbox(es) and copy the executable.
        sandbox_user = create_sandbox(file_cacher, name="user_evaluate")
        job.sandboxes.extend(sandbox_user.get_root_path())

        sandbox_user.create_file_from_storage(
            executable_filename, executable_digest, executable=True)

        sandbox_user.create_file_from_storage(
            self.INPUT_FILENAME, job.input)

        # Start the user submission compiled with the stub.
        language = get_language(job.language)
        main = os.path.splitext(executable_filename)[0]
        process = None

        args = []
        stdin_redirect = None
        stdout_redirect = None

        commands = language.get_evaluation_commands(
            executable_filename,
            main=main,
            args=args)
        # Assumes that the actual execution of the user solution is the
        # last command in commands, and that the previous are "setup"
        # that don't need tight control.
        if len(commands) > 1:
            trusted_step(sandbox_user[i], commands[:-1])
        process = evaluation_step_before_run(
            sandbox_user,
            commands[-1],
            job.time_limit,
            job.memory_limit,
            dirs_map={output_dir: (sandbox_output_dir, "rw")},
            stdin_redirect=self.INPUT_FILENAME,
            stdout_redirect=sandbox_output_filename,
            multiprocess=job.multithreaded_sandbox)

        # Wait for the processes to conclude, without blocking them on I/O.
        wait_without_std([process])

        feedback_dir = tempfile.mkdtemp(dir=config.temp_dir)
        sandbox_feedback_dir = "/feedback"
        os.chmod(feedback_dir, 0o777)

        # Create the manager sandbox and copy manager and input.
        sandbox_mgr = create_sandbox(file_cacher, name="manager_evaluate")
        job.sandboxes.append(sandbox_mgr.get_root_path())
        sandbox_mgr.create_file_from_storage(
            self.MANAGER_FILENAME, manager_digest, executable=True)
        sandbox_mgr.create_file_from_storage(
            self.INPUT_FILENAME, job.input)
        sandbox_mgr.create_file_from_storage(
            self.ANSWER_FILENAME, job.output)

        # Start the manager. Redirecting to stdin is unnecessary, but for
        # historical reasons the manager can choose to read from there
        # instead than from INPUT_FILENAME.
        manager_command = [
            "./%s" % self.MANAGER_FILENAME, 
            self.INPUT_FILENAME,
            self.ANSWER_FILENAME,
            sandbox_feedback_dir
        ]

        manager_time_limit = max(job.time_limit + 1.0,
                                 config.trusted_sandbox_max_time_s)
        manager = evaluation_step_before_run(
            sandbox_mgr,
            manager_command,
            manager_time_limit,
            config.trusted_sandbox_max_memory_kib * 1024,
            dirs_map = {
                output_dir: (sandbox_output_dir, "rw"),
                feedback_dir: (sandbox_feedback_dir, "rw")
            },
            stdin_redirect=sandbox_output_filename,
            multiprocess=job.multithreaded_sandbox)

        wait_without_std([manager])

        self._get_results(feedback_dir, sandbox_user, sandbox_mgr, job)

        delete_sandbox(sandbox_mgr, job.success, job.keep_sandbox)
        delete_sandbox(sandbox_user, job.success, job.keep_sandbox)
        if job.success and not config.keep_sandbox and not job.keep_sandbox:
            rmtree(feedback_dir)

    def evaluate(self, job, file_cacher):
        """See TaskType.evaluate."""

        if self.interactive:
            self._evaluate_interactive(job, file_cacher)
        else:
            self._evaluate_noninteractive(job, file_cacher)
