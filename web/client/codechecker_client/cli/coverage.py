# -------------------------------------------------------------------------
#
#  Part of the CodeChecker project, under the Apache License v2.0 with
#  LLVM Exceptions. See LICENSE for license information.
#  SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#
# -------------------------------------------------------------------------
"""
'CodeChecker coverage' generates test coverage data by compiling with coverage
flags, running the program, and generating coverage.json file.
"""


import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from codechecker_common import arg, logger
from codechecker_common.cmd_config import add_option

LOG = logger.get_logger('system')


def get_argparser_ctor_args():
    """
    This method returns a dict containing the kwargs for constructing an
    argparse.ArgumentParser (either directly or as a subparser).
    """

    return {
        'prog': 'CodeChecker coverage',
        'formatter_class': arg.RawDescriptionDefaultHelpFormatter,

        # Description is shown when the command's help is queried directly
        'description': """
Generate test coverage data by compiling source files with coverage flags,
running the program, and generating a coverage.json file with covered line
numbers.""",

        # Epilogue is shown after the arguments when the help is queried
        # directly.
        'epilog': """
Examples
------------------------------------------------
  # Compile and run a single source file
  CodeChecker coverage hello.c -o coverage.json

  # Use a build command
  CodeChecker coverage -b "gcc --coverage -o a.out hello.c && ./a.out"

  # Specify output directory
  CodeChecker coverage hello.c -o coverage.json --output-dir ./coverage
""",

        # Help is shown when the "parent" CodeChecker command lists the
        # individual subcommands.
        'help': "Generate test coverage data and create coverage.json file."
    }


def add_arguments_to_parser(parser):
    """
    Add the subcommand's arguments to the given argparse.ArgumentParser.
    """

    parser.add_argument('source_files',
                        type=str,
                        nargs='*',
                        metavar='source_file',
                        help="Source files to analyze for coverage. "
                             "If not provided, use --build-command instead.")

    parser.add_argument('-b', '--build-command',
                        type=str,
                        dest="build_command",
                        required=False,
                        help="Build command to compile and run the program. "
                             "The command should compile with --coverage flag "
                             "and run the program. Example: "
                             "'gcc --coverage -o a.out hello.c && ./a.out'")

    parser.add_argument('-o', '--output',
                        type=str,
                        dest="output",
                        default="coverage.json",
                        required=False,
                        help="Output coverage.json file path. "
                             "(default: coverage.json)")

    parser.add_argument('--output-dir',
                        type=str,
                        dest="output_dir",
                        required=False,
                        help="Output directory for intermediate files "
                             "(gcov files, lcov info). If not specified, "
                             "a temporary directory will be used.")

    parser.add_argument('--keep-temp',
                        dest="keep_temp",
                        action='store_true',
                        required=False,
                        help="Keep temporary files after execution.")

    parser.add_argument('--compiler',
                        type=str,
                        dest="compiler",
                        default="gcc",
                        required=False,
                        help="Compiler to use (default: gcc).")

    add_option(parser)

    parser.set_defaults(func=main)


def parse_lcov_info(lcov_file):
    """
    Parse lcov info file and extract covered lines for each source file.
    Returns a dictionary mapping file paths to lists of covered line numbers.
    """
    coverage_data = {}

    if not os.path.exists(lcov_file):
        LOG.error("lcov info file not found: %s", lcov_file)
        return coverage_data

    with open(lcov_file, 'r', encoding='utf-8', errors='ignore') as f:
        current_file = None
        covered_lines = set()

        for line in f:
            line = line.strip()

            # SF: indicates source file
            if line.startswith('SF:'):
                # Save previous file's coverage if exists
                if current_file and covered_lines:
                    # Convert to absolute path and normalize
                    abs_path = os.path.abspath(current_file)
                    coverage_data[abs_path] = sorted(list(covered_lines))

                current_file = line[3:].strip()
                covered_lines = set()

            # DA: indicates line coverage data (DA:line_number,execution_count)
            elif line.startswith('DA:') and current_file:
                match = re.match(r'DA:(\d+),(\d+)', line)
                if match:
                    line_num = int(match.group(1))
                    exec_count = int(match.group(2))
                    # Only include lines that were executed at least once
                    if exec_count > 0:
                        covered_lines.add(line_num)

        # Save last file's coverage
        if current_file and covered_lines:
            abs_path = os.path.abspath(current_file)
            coverage_data[abs_path] = sorted(list(covered_lines))

    return coverage_data


def compile_with_coverage(source_files, compiler, output_dir):
    """
    Compile source files with coverage flags.
    Returns the path to the compiled executable.
    """
    if not source_files:
        LOG.error("No source files provided")
        return None

    # Determine output executable name
    first_file = source_files[0]
    base_name = os.path.splitext(os.path.basename(first_file))[0]
    executable = os.path.join(output_dir, base_name)

    # Build compile command
    compile_cmd = [
        compiler,
        '--coverage',
        '-o', executable
    ] + source_files

    LOG.info("Compiling with coverage flags...")
    LOG.debug("Command: %s", ' '.join(compile_cmd))

    try:
        result = subprocess.run(
            compile_cmd,
            cwd=output_dir,
            check=True,
            capture_output=True,
            text=True
        )
        LOG.debug("Compilation output: %s", result.stdout)
        return executable
    except subprocess.CalledProcessError as e:
        LOG.error("Compilation failed: %s", e.stderr)
        return None


def run_program(executable):
    """
    Run the compiled program to generate coverage data.
    """
    if not executable or not os.path.exists(executable):
        LOG.error("Executable not found: %s", executable)
        return False

    LOG.info("Running program to generate coverage data...")
    LOG.debug("Executable: %s", executable)

    try:
        result = subprocess.run(
            [executable],
            cwd=os.path.dirname(executable) or '.',
            check=True,
            capture_output=True,
            text=True
        )
        LOG.debug("Program output: %s", result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        LOG.warning("Program execution failed (this may be expected): %s",
                    e.stderr)
        # Still return True as coverage data might be generated
        return True


def generate_gcov_files(source_files, output_dir):
    """
    Generate gcov files for source files.
    """
    LOG.info("Generating gcov files...")

    for source_file in source_files:
        if not os.path.exists(source_file):
            LOG.warning("Source file not found: %s", source_file)
            continue

        # Run gcov on the source file
        gcov_cmd = ['gcov', source_file]

        try:
            result = subprocess.run(
                gcov_cmd,
                cwd=output_dir,
                check=True,
                capture_output=True,
                text=True
            )
            LOG.debug("gcov output for %s: %s", source_file, result.stdout)
        except subprocess.CalledProcessError as e:
            LOG.warning("gcov failed for %s: %s", source_file, e.stderr)


def capture_lcov_data(output_dir, lcov_file):
    """
    Capture coverage data using lcov.
    """
    LOG.info("Capturing coverage data with lcov...")

    lcov_cmd = [
        'lcov',
        '--capture',
        '--directory', output_dir,
        '--output-file', lcov_file
    ]

    try:
        result = subprocess.run(
            lcov_cmd,
            check=True,
            capture_output=True,
            text=True
        )
        LOG.debug("lcov output: %s", result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        LOG.error("lcov failed: %s", e.stderr)
        return False
    except FileNotFoundError:
        LOG.error("lcov not found. Please install lcov: "
                  "sudo apt-get install lcov (Ubuntu/Debian) or "
                  "brew install lcov (macOS)")
        return False


def process_build_command(build_command, output_dir):
    """
    Process a build command that compiles and runs the program.
    """
    LOG.info("Executing build command...")
    LOG.debug("Build command: %s", build_command)

    try:
        # Split the command by && to handle multiple commands
        commands = [cmd.strip() for cmd in build_command.split('&&')]

        for cmd in commands:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=output_dir,
                check=True,
                capture_output=True,
                text=True
            )
            LOG.debug("Command output: %s", result.stdout)

        return True
    except subprocess.CalledProcessError as e:
        LOG.error("Build command failed: %s", e.stderr)
        return False


def main(args):
    """
    Main function for the coverage command.
    """
    logger.setup_logger(args.verbose if 'verbose' in args else None)

    # Determine output directory
    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
        os.makedirs(output_dir, exist_ok=True)
        temp_dir = None
    else:
        temp_dir = tempfile.mkdtemp(prefix='codechecker_coverage_')
        output_dir = temp_dir
        LOG.debug("Using temporary directory: %s", output_dir)

    try:
        lcov_file = os.path.join(output_dir, 'coverage.info')

        # Process build command or source files
        if args.build_command:
            # Use build command
            if not process_build_command(args.build_command, output_dir):
                LOG.error("Build command execution failed")
                sys.exit(1)

            # Generate gcov files
            # Find .gcda files to determine which source files were covered
            gcov_files = []
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    if file.endswith('.gcda'):
                        # Get corresponding source file name
                        base = file.replace('.gcda', '')
                        # Look for source files in the directory
                        for ext in ['.c', '.cpp', '.cc', '.cxx']:
                            source_file = os.path.join(root, base + ext)
                            if os.path.exists(source_file):
                                gcov_files.append(source_file)
                                break

            if not gcov_files:
                LOG.warning("No source files found for gcov generation")
                # Try to generate gcov for all .gcda files found
                for root, dirs, files in os.walk(output_dir):
                    for file in files:
                        if file.endswith('.gcda'):
                            base = file.replace('.gcda', '')
                            generate_gcov_files([base], output_dir)

        elif args.source_files:
            # Compile source files with coverage
            source_files = [os.path.abspath(f) for f in args.source_files]
            executable = compile_with_coverage(source_files, args.compiler,
                                                output_dir)

            if not executable:
                LOG.error("Compilation failed")
                sys.exit(1)

            # Run the program
            if not run_program(executable):
                LOG.warning("Program execution had issues, but continuing...")

            # Generate gcov files
            generate_gcov_files(source_files, output_dir)
        else:
            LOG.error("Either source files or --build-command must be provided")
            sys.exit(1)

        # Capture coverage data with lcov
        if not capture_lcov_data(output_dir, lcov_file):
            LOG.error("Failed to capture coverage data with lcov")
            sys.exit(1)

        # Parse lcov info file
        coverage_data = parse_lcov_info(lcov_file)

        if not coverage_data:
            LOG.warning("No coverage data found in lcov file")
            sys.exit(1)

        # Write coverage.json
        output_file = os.path.abspath(args.output)
        output_dir_path = os.path.dirname(output_file)
        if output_dir_path:
            os.makedirs(output_dir_path, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(coverage_data, f, indent=2, sort_keys=True)

        LOG.info("Coverage data written to: %s", output_file)
        LOG.info("Covered %d file(s)", len(coverage_data))

        # Print summary
        total_lines = sum(len(lines) for lines in coverage_data.values())
        LOG.info("Total covered lines: %d", total_lines)

    finally:
        # Clean up temporary directory if not keeping temp files
        if temp_dir and not args.keep_temp:
            LOG.debug("Cleaning up temporary directory: %s", temp_dir)
            shutil.rmtree(temp_dir, ignore_errors=True)

    return 0

