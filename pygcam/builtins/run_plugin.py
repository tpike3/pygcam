#!/usr/bin/env python
"""
.. Support for running a sequence of operations for a GCAM project
   that is described in an XML file.

.. codeauthor:: Rich Plevin <rich@plevin.com>

.. Copyright (c) 2015 Richard Plevin
   See the https://opensource.org/licenses/MIT for license details.
"""
from ..log import getLogger
from ..subcommand import SubcommandABC

__version__ = '0.2'

_logger = getLogger(__name__)


class ProjectCommand(SubcommandABC):
    def __init__(self, subparsers, name='run', help='Run the steps for a project defined in a project.xml file'):
        kwargs = {'help' : help}
        super(ProjectCommand, self).__init__(name, subparsers, kwargs)

    def addArgs(self, parser):

        parser.add_argument('-a', '--allGroups', action='store_true',
                            help='''Run all scenarios for all defined groups.''')

        parser.add_argument('-f', '--projectFile',
                            help='''The XML file describing the project. If set, command-line
                            argument takes precedence. Otherwise, value is taken from config file
                            variable GCAM.ProjectXmlFile, if defined, otherwise the default
                            is './project.xml'.''')

        parser.add_argument('-g', '--group',
                            help='''The name of the scenario group to process. If not specified,
                            the group with attribute default="1" is processed.''')

        parser.add_argument('-G', '--listGroups', action='store_true',
                            help='''List the scenario groups defined in the project file and exit.''')

        parser.add_argument('-k', '--skipStep', dest='skipSteps', action='append',
                            help='''Steps to skip. These must be names of steps defined in the
                            project.xml file. Multiple steps can be given in a single (comma-delimited)
                            argument, or the -k flag can be repeated to indicate additional steps.
                            By default, all steps are run.''')

        parser.add_argument('-K', '--skipScenario', dest='skipScenarios', action='append',
                            help='''Scenarios to skip. Multiple scenarios can be given in a single
                            (comma-delimited) argument, or the -K flag can be repeated to indicate
                            additional scenarios. By default, all scenarios are run.''')

        parser.add_argument('-l', '--listSteps', action='store_true',
                            help='''List the steps defined for the given project and exit.
                            Dynamic variables (created at run-time) are not displayed.''')

        parser.add_argument('-L', '--listScenarios', action='store_true',
                            help='''List the scenarios defined for the given project and exit.
                            Dynamic variables (created at run-time) are not displayed.''')

        parser.add_argument('-n', '--noRun', action='store_true',
                            help='''Display the commands that would be run, but don't run them.''')

        parser.add_argument('-p', '--project',
                            help='''The name of the project to run.''')

        parser.add_argument('-q', '--noQuit', action='store_true',
                            help='''Don't quit if an error occurs when processing a scenario, just
                            move on to processing the next scenario, if any.''')

        parser.add_argument('-s', '--step', dest='steps', action='append',
                            help='''The steps to run. These must be names of steps defined in the
                            project.xml file. Multiple steps can be given in a single (comma-delimited)
                            argument, or the -s flag can be repeated to indicate additional steps.
                            By default, all steps are run.''')

        parser.add_argument('-S', '--scenario', dest='scenarios', action='append',
                            help='''Which of the scenarios defined for the given project should
                            be run. Multiple scenarios can be given in a single (comma-delimited)
                            argument, or the -S flag can be repeated to indicate additional scenarios.
                            By default, all active scenarios are run.''')

        parser.add_argument('--version', action='version', version='%(prog)s ' + __version__)

        parser.add_argument('--vars', action='store_true', help='''List variables and their values''')

        parser.add_argument('-x', '--sandboxDir',
                            help='''The directory in which to create the run-time sandbox workspace.
                            Defaults to value of {GCAM.SandboxProjectDir}/{scenarioGroup}.''')

        return parser   # for auto-doc generation


    def run(self, args, tool):
        from ..project import projectMain
        projectMain(args, tool)