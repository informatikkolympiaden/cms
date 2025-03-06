#!/usr/bin/env python3

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
import os.path
from pathlib import Path

import yaml

from cms import TOKEN_MODE_DISABLED, FEEDBACK_LEVEL_RESTRICTED
from cmscommon.constants import SCORE_MODE_MAX_SUBTASK
from cms.db import Task, Statement, Dataset, Attachment, Team, Manager, Testcase
from .base_loader import TaskLoader

logger = logging.getLogger(__name__)

def load_yaml_from_path(path):
    with open(path, "rt", encoding="utf-8") as f:
        return yaml.safe_load(f)

class SubtaskNode:
    def __init__(self, path):
        name = path.name
        self.path = path
        testdata = {}
        if path.joinpath("testdata.yaml").is_file():
            testdata = load_yaml_from_path(path.joinpath("testdata.yaml"))
        testdata.setdefault("grading", {})

        if name == "data" or name == "secret":
            testdata["grading"].setdefault("score", 1)
            testdata["grading"].setdefault("aggregation", "sum")
        elif name == "sample":
            testdata["grading"].setdefault("score", 0)
            testdata["grading"].setdefault("aggregation", "sum")
        else:
            testdata["grading"].setdefault("score", 1)
            testdata["grading"].setdefault("aggregation", "min")

        self.conf = testdata
        self.testcases = {}
        self.subgroups = {}

        for p in sorted(path.iterdir()):
            if p.name == "testdata.yaml":
                continue
            elif p.is_dir():
                self.subgroups[p.name] = SubtaskNode(p)
            elif p.suffix == ".in":
                self.testcases.setdefault(p.stem, {})
                self.testcases[p.stem]["in_file"] = p
            elif p.suffix == ".ans":
                self.testcases.setdefault(p.stem, {})
                self.testcases[p.stem]["out_file"] = p

    def list_testcases(self):
        testcases = []
        testcases += self.testcases.values()
        for subgroup in self.subgroups.values():
            testcases += subgroup.list_testcases()
        return testcases

    def to_testcase_group(self):
        if len(self.subgroups) > 0:
            raise Exception("Testcase group can't have any subgroups")

        score = self.conf["grading"]["score"]

        if self.conf["grading"]["aggregation"] == "sum":
            score = score / len(self.testcases)

        return [
            score,
            len(self.testcases)
        ]

    def to_groups(self):
        if self.conf["grading"]["aggregation"] != "sum":
            raise Exception("Root testcase group aggregation must be sum")

        if len(self.testcases) > 0:
            raise Exception("Root testcase group can't have any direct testcases")

        groups = []

        for subgroup in self.subgroups.values():
            if len(subgroup.subgroups) > 0:
                groups += subgroup.to_groups()
            else:
                groups += [subgroup.to_testcase_group()]
        return groups

    def score_type(self):
        score_type = None
        if self.conf["grading"]["aggregation"] != "sum":
            raise Exception("Root testcase group aggregation must be sum")

        for subgroup in self.subgroups.values():
            if len(subgroup.subgroups) > 0:
                group_type = subgroup.score_type()
                if score_type is not None and group_type is not None and score_type != group_type:
                    raise Exception("Different score types")
                score_type = score_type or group_type
            else:
                group_type = subgroup.conf["grading"]["aggregation"]
                if subgroup.conf["grading"]["score"] == 0:
                    group_type = None
                if score_type is not None and group_type is not None and score_type != group_type:
                    raise Exception("Different score types")
                score_type = score_type or group_type

        return score_type

class KattisLoader(TaskLoader):

    short_name = "kattis"
    description = "Kattis Problem Package Format"

    @staticmethod
    def detect(path):
        """See docstring in class Loader."""
        # TODO - Not really refined...
        return os.path.exists(os.path.join(path, "problem.yaml")) and \
            os.path.exists(os.path.join(path, "data"))

    def task_has_changed(self):
        """See docstring in class Loader.

        """
        return True

    def get_task(self, get_statement=True):
        """See docstring in class TaskLoader."""
        name = os.path.split(self.path)[1]

        if not os.path.exists(os.path.join(self.path, "problem.yaml")):
            logger.critical("File missing: \"problem.yaml\"")
            return None

        # We first look for the yaml file inside the task folder,
        # and eventually fallback to a yaml file in its parent folder.
        try:
            conf = load_yaml_from_path(os.path.join(self.path, "problem.yaml"))
        except OSError:
            raise err


        args = {}

        args["name"] = name
        args["title"] = conf["name"]

        if args["name"] == args["title"]:
            logger.warning("Short name equals long name (title). "
                           "Please check.")

        name = args["name"]

        logger.info("Loading parameters for task %s.", name)

        # Get statements


        if get_statement:
            args["statements"] = {}
            for statement_path in Path(self.path).glob("problem_statement/problem.*.pdf"):
                lang = statement_path.suffixes[0][1:]
                digest = self.file_cacher.put_file_from_path(
                    statement_path,
                    "Statement for task %s (lang: %s)" %
                    (name, lang))
                args["statements"][lang] = Statement(lang, digest)

        args["submission_format"] = ["%s.%%l" % name]

        args["feedback_level"] = FEEDBACK_LEVEL_RESTRICTED

        args["score_mode"] = SCORE_MODE_MAX_SUBTASK

        args["token_mode"] = TOKEN_MODE_DISABLED

        # Attachments
        args["attachments"] = dict()
        if os.path.exists(os.path.join(self.path, "attachments")):
            for filename in os.listdir(os.path.join(self.path, "attachments")):
                digest = self.file_cacher.put_file_from_path(
                    os.path.join(self.path, "att", filename),
                    "Attachment %s for task %s" % (filename, name))
                args["attachments"][filename] = Attachment(filename, digest)

        task = Task(**args)

        args = {}
        args["task"] = task
        args["description"] = "Default"
        args["autojudge"] = False

        args["time_limit"] = 1.0
        args["memory_limit"] = 2048 * 1024 * 1024
        if conf.get("limits") is not None:
            if "time_limit" in conf["limits"]:
                args["time_limit"] = float(conf["limits"]["time_limit"])
            if "time" in conf["limits"]:
                args["time_limit"] = float(conf["limits"]["time"])
            if "memory" in conf["limits"]:
                args["memory_limit"] = conf["limits"]["memory"] * 1024 * 1024

        # Builds the parameters that depend on the task type
        args["managers"] = []

        compilation_param = "alone"
        evaluation_param = "diff"

        subtasks = SubtaskNode(Path(self.path).joinpath("data"))

        if subtasks.score_type() == "min":
            args["score_type"] = "GroupMin"
        else:
            args["score_type"] = "GroupSum"
        args["score_type_parameters"] = subtasks.to_groups()

        args["task_type"] = "Batch"
        args["task_type_parameters"] = \
            [compilation_param, ["", ""], evaluation_param]

        args["testcases"] = []

        for i, testcase in enumerate(subtasks.list_testcases()):
            input_digest = self.file_cacher.put_file_from_path(
                testcase["in_file"],
                "Input %d for task %s" % (i, task.name))
            output_digest = self.file_cacher.put_file_from_path(
                testcase["out_file"],
                "Output %d for task %s" % (i, task.name))
            args["testcases"] += [
                Testcase("%03d" % i, True, input_digest, output_digest)]

        args["testcases"] = dict((tc.codename, tc) for tc in args["testcases"])
        args["managers"] = dict((mg.filename, mg) for mg in args["managers"])

        dataset = Dataset(**args)

        task.active_dataset = dataset

        logger.info("Task parameters loaded.")

        return task
