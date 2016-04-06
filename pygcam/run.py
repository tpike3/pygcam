'''
.. Created on: 2/26/15

.. codeauthor:: Rich Plevin <rich@plevin.com>

.. Copyright (c) 2016 Richard Plevin
   See the https://opensource.org/licenses/MIT for license details.
'''
import os
import subprocess
import platform
import shutil
from lxml import etree as ET
from .error import ConfigFileError, ProgramExecutionError
from .utils import mkdirs
from .config import getConfig, getParam, getParamAsBoolean
from .log import getLogger
from .windows import setJavaPath, removeSymlink
from .subcommand import SubcommandABC

_logger = getLogger(__name__)

PROGRAM = os.path.basename(__file__)
__version__ = "0.2"

PlatformName = platform.system()

def readScenarioName(configFile):
    """
    Read the file `configFile` and extract the scenario name.

    :param configFile: (str) the path to a GCAM configuration file
    :return: (str) the name of the scenario defined in `configFile`
    """
    parser = ET.XMLParser(remove_blank_text=True)
    tree   = ET.parse(configFile, parser)
    scenarioName = tree.find('//Strings/Value[@name="scenarioName"]')
    return scenarioName.text

def setupWorkspace(runWorkspace):
    refWorkspace = getParam('GCAM.RefWorkspace')

    if os.path.lexists(runWorkspace) and os.path.samefile(runWorkspace, refWorkspace):
        _logger.info("setupWorkspace: run workspace is reference workspace; no setup performed")
        return

    copyAllFiles = getParamAsBoolean('GCAM.CopyAllFiles')

    def tryLink(src, dst):
        try:
            os.symlink(src, dst)
        except Exception as e:
            pass

    def workspaceSymlink(src, isDir=False):
        '''
        Create a link (or copy) in the new workspace to the
        equivalent file in the main GCAM workspace.
        '''
        dstPath = os.path.join(runWorkspace, src)
        dirName = dstPath if isDir else os.path.dirname(dstPath)
        mkdirs(dirName)

        if not os.path.lexists(dstPath):
            srcPath = os.path.join(refWorkspace, src)

            if copyAllFiles:
                # for Windows users without symlink permission
                _logger.warn('Copying %s to %s' % (srcPath, dstPath))
                if os.path.isdir(srcPath):
                    shutil.copytree(srcPath, dstPath)
                else:
                    shutil.copy2(srcPath, dstPath)
            else:
                os.symlink(srcPath, dstPath)

    # Create the workspace if needed
    if not os.path.isdir(runWorkspace):
        _logger.info("Creating GCAM workspace '%s'", runWorkspace)

    # Create a local output dir
    outDir = os.path.join(runWorkspace, 'output')
    mkdirs(outDir)

    logPath = os.path.join(runWorkspace, 'exe', 'logs')
    mkdirs(logPath)

    # Create link in the new workspace "exe" dir to the executable program and other required files/dirs
    exeName = getParam('GCAM.Executable')
    exeName = exeName[2:] if exeName[:2] == './' else exeName   # trim leading './' if present
    exePath = os.path.join('exe', exeName)                      # expressed as relative to the exe dir
    workspaceSymlink(exePath)

    workspaceSymlink(os.path.join('exe', 'configuration.xml'))  # link to default configuration file
    workspaceSymlink(os.path.join('exe', 'log_conf.xml'))       # and log configuration file
    workspaceSymlink('input')
    workspaceSymlink('libs')

    # Add links to libs for basex and xerces-c_3_1.dll (Windows)
    for filename in ['WriteLocalBaseXDB.class', 'xerces-c_3_1.dll']:
        if os.path.lexists(os.path.join(refWorkspace, 'exe', filename)):
            workspaceSymlink(os.path.join('exe', filename))

    # Add symlinks to dirs holding files generated by "setup" scripts
    def linkXmlDir(varName, xmlDir):
        src = getParam(varName)
        dst = os.path.abspath(os.path.join(runWorkspace, xmlDir))

        if os.path.lexists(dst) and os.path.islink(dst):
            removeSymlink(dst)

        if copyAllFiles:
            # for Windows users without symlink permission
            _logger.warn('Copying %s to %s' % (src, dst))
            shutil.copytree(src, dst)
        else:
            os.symlink(src, dst)

    linkXmlDir('GCAM.LocalXml', 'local-xml')
    linkXmlDir('GCAM.DynXml',   'dyn-xml')


CONFIG_FILE_DELIM = ':'

def runGCAM(args):
    getConfig(args.configSection)
    from .config import CONFIG_VAR_NAME, WORKSPACE_VAR_NAME, NO_RUN_GCAM_VAR_NAME

    isQueued = (CONFIG_VAR_NAME in os.environ)     # see if this is a batch run on cluster

    if isQueued:
        configFiles = os.environ[CONFIG_VAR_NAME].split(CONFIG_FILE_DELIM)
        workspace   = os.environ[WORKSPACE_VAR_NAME]
        args.noRunGCAM = int(os.environ[NO_RUN_GCAM_VAR_NAME])
        runQsub = False
    else:
        scenarios  = args.scenario.split(',') if args.scenario else None
        runLocal   = args.runLocal
        runQsub    = not runLocal
        jobName    = args.jobName    # args default is "queueGCAM"
        queueName  = args.queueName  or getParam('GCAM.DefaultQueue')
        workspace  = args.workspace  or getParam('GCAM.SandboxRoot')
        workspace  = os.path.abspath(os.path.expanduser(workspace))     # handle ~ in pathname
        setupWorkspace(workspace)

    # less confusing names
    showCommandsOnly = args.noRun
    postProcessOnly  = args.noRunGCAM

    # Optional script to run after successful GCAM runs
    postProcessor = not args.noPostProcessor and (args.postProcessor or getParam('GCAM.PostProcessor'))

    exeDir = os.path.join(workspace, 'exe')

    setJavaPath(exeDir)     # required for Windows; a no-op otherwise

    def runCommand(command, args=None, shell=False):
        '''
        Run the command given by the args list (if given) or the command
        string and raise the ProgramExecutionError exception if it fails.
        '''
        _logger.info('Running: %s', command)
        exitCode = subprocess.call(args or command, shell=shell)
        if exitCode != 0:
            raise ProgramExecutionError(command, exitCode)

    if not isQueued:
        if scenarios:
            # Translate scenario names into config file paths, assuming scenario FOO lives in
            # {scenariosDir}/FOO/config.xml
            scenariosDir = os.path.abspath(args.scenariosDir or getParam('GCAM.ScenariosDir') or '.')
            configFiles  = map(lambda name: os.path.join(scenariosDir, name, "config.xml"), scenarios)
        else:
            configFiles = map(os.path.abspath, args.configFile.split(',')) \
                            if args.configFile else [os.path.join(exeDir, 'configuration.xml')]

    if runQsub:
        logFile  = os.path.join(exeDir, 'queueGCAM.log')
        minutes  = (args.minutes or float(getParam('GCAM.Minutes'))) * len(configFiles)
        walltime = "%02d:%02d:00" % (minutes / 60, minutes % 60)
        configs  = CONFIG_FILE_DELIM.join(configFiles)

        # This dictionary is applied to the string value of GCAM.BatchCommand, via
        # the str.format method, which must specify options using any of the keys.
        batchArgs = {'logFile'   : logFile,
                     'minutes'   : minutes,
                     'walltime'  : walltime,
                     'queueName' : queueName,
                     'jobName'   : jobName,
                     'configs'   : configs,
                     'exeDir'    : exeDir,
                     'workspace' : workspace,
                     'noRunGCAM' : int(args.noRunGCAM)}

        batchCmd = getParam('GCAM.BatchCommand')
        scriptPath = os.path.abspath(__file__)
        batchCmd += ' ' + scriptPath

        try:
            command = batchCmd.format(**batchArgs)
        except KeyError as e:
            raise ConfigFileError('Badly formatted batch command (%s) in config file: %s', batchCmd, e)

        if not showCommandsOnly:
            runCommand(command, shell=True)
    else:
        # Run locally, which might mean on a desktop machine, interactively on a
        # compute node (via "qsub -I", or in batch mode on a compute node.
        gcamPath = getParam('GCAM.Executable')
        _logger.info("cd %s", exeDir)
        os.chdir(exeDir)        # if isQsubbed, this is redundant but harmless

        for configFile in configFiles:
            gcamArgs = [gcamPath, '-C%s' % configFile]  # N.B. GCAM doesn't allow space between -C and filename
            gcamCmd   = ' '.join(gcamArgs)

            if postProcessor:
                scenarioName = readScenarioName(configFile)
                postProcArgs = [postProcessor, workspace, configFile, scenarioName]
                postProcCmd = ' '.join(postProcArgs)

            if showCommandsOnly:
                print gcamCmd
                print postProcCmd if postProcessor else "No post-processor defined"
                continue

            if not postProcessOnly:
                runCommand(gcamCmd, args=gcamArgs)

            if postProcessor:
                runCommand(postProcCmd, args=postProcArgs)

class GcamCommand(SubcommandABC):
    def __init__(self, subparsers):
        kwargs = {'help' : '''Run the GCAM executable''',
                  'description' : '''Queue a GCAM job on a Linux cluster or run the job
                  locally (via "-l" flag). (On OS X, the "-l" flag is not needed; only
                  local running is supported.)'''}

        super(GcamCommand, self).__init__('gcam', subparsers, kwargs)

    def addArgs(self, parser):
        parser.add_argument('-C', '--configFile',
                            help='''Specify the one or more GCAM configuration filenames, separated commas.
                                    If multiple configuration files are given, the are run in succession in
                                    the same "job" on the cluster.
                                    N.B. This argument is ignored if scenarios are named via the -s flag.''')

        parser.add_argument('-E', '--enviroVars',
                            help='''Comma-delimited list of environment variable assignments to pass
                                    to qsub, e.g., -E "FOO=1,BAR=2".''')

        parser.add_argument('-j', '--jobName', default='queueGCAM',
                            help='''Specify a name for the queued job. Default is "queueGCAM".''')

        parser.add_argument('-l', '--runLocal', action='store_true', default=(PlatformName in ['Darwin', 'Windows']),
                            help='''Run GCAM locally on current host, not via qsub. (It's not necessary
                                    to specify this flag on OS X and Windows since only local execution
                                    is supported.)''')

        parser.add_argument('-m', '--minutes', type=float,
                            help='''Set the number of minutes to allocate for each job submitted.
                                    Overrides config parameter GCAM.Minutes.''')

        parser.add_argument('-n', '--noRun', action="store_true",
                            help="Show the 'qsub' command to be run, but don't run it")

        parser.add_argument('-N', '--noRunGCAM', action="store_true",
                            help="Don't run GCAM, just run the post-processing script on existing results.")

        parser.add_argument('-r', '--resources', default='',
                            help='''Specify resources for the qsub command. Can be a comma-delimited list of
                                    assignments NAME=value, e.g., -r pvmem=6GB.''')

        parser.add_argument('-p', '--postProcessor', default='',
                            help='''Specify the path to a script to run after GCAM completes. It should accept three
                                    command-line arguments, the first being the path to the workspace in which GCAM
                                    was executed, the second being the name of the configuration file used, and the
                                    third being the scenario name of interest. Defaults to value of configuration
                                    parameter GCAM.PostProcessor.''')

        parser.add_argument('-P', '--noPostProcessor', action='store_true', default=False,
                            help='''Don't run the post-processor script. (Use this to skip post-processing when a script
                                    is named in the ~/.gcam.cfg configuration file.)''')

        parser.add_argument('-Q', '--queueName',
                            help='''Specify a queue name for qsub. Default is given by config file
                                    param GCAM.DefaultQueue.''')

        parser.add_argument('-s', '--scenario', default='',
                            help='''Specify the scenario(s) to run. Can be a comma-delimited list of scenario names.
                                    The scenarios will be run serially in a single batch job, with an allocated
                                    time = GCAM.Minutes * {the number of scenarios}.''')

        parser.add_argument('-S', '--scenariosDir', default='',
                            help='''Specify the directory holding scenarios. Default is the value of config file param
                            GCAM.ScenariosDir, if set, otherwise ".".''')

        parser.add_argument('--version', action='version', version='%(prog)s ' + __version__)

        parser.add_argument('-w', '--workspace',
                            help='''Specify the path to the GCAM workspace to use. If it doesn't exist, the named workspace
                                    will be created. If not specified on the command-line, the value of config file parameter
                                    GCAM.Workspace is used, i.e., the "standard" workspace.''')

        return parser

    def run(self, args, tool):
        runGCAM(args)
