# -------------------------------------------------------------------------
#
#  Part of the CodeChecker project, under the Apache License v2.0 with
#  LLVM Exceptions. See LICENSE for license information.
#  SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#
# -------------------------------------------------------------------------

import json
import logging
import os
import subprocess
import tempfile
from typing import Dict, Iterable, List

from codechecker_report_converter.analyzers.analyzer_result import \
    AnalyzerResultBase


LOG = logging.getLogger('report-converter')


class AnalyzerResult(AnalyzerResultBase):
    """GCOV coverage to simple JSON mapping."""

    TOOL_NAME = 'gcov'
    NAME = 'GNU gcov coverage to JSON'
    URL = 'https://gcc.gnu.org/onlinedocs/gcc/Gcov.html'

    def transform(
        self,
        analyzer_result_file_paths: Iterable[str],
        output_dir_path: str,
        export_type: str,
        file_name: str = "{source_file}_{analyzer}_{file_hash}",
        metadata=None
    ) -> bool:
        coverage_map: Dict[str, List[int]] = {}

        for input_path in analyzer_result_file_paths:
            abs_input = os.path.abspath(input_path)
            parsed = self._parse_input(abs_input)
            for src, lines in parsed.items():
                if src not in coverage_map:
                    coverage_map[src] = []
                # Merge while keeping unique lines, maintain increasing order
                merged = set(coverage_map[src]) | set(lines)
                coverage_map[src] = sorted(merged)

        if not os.path.exists(output_dir_path):
            os.makedirs(output_dir_path)

        out_path = os.path.join(output_dir_path, 'gcov_coverage.json')
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(coverage_map, f, indent=2, sort_keys=True)

        LOG.info("Created GCOV coverage JSON: '%s'", out_path)
        return bool(coverage_map)

    def get_reports(self, file_path: str):
        return []

    def _parse_input(self, path: str) -> Dict[str, List[int]]:
        """Accept a .gcov file or run gcov on the given path and parse results."""
        if path.endswith('.gcov') and os.path.isfile(path):
            return self._parse_gcov_file(path)

        # Try invoking gcov to generate coverage for this input.
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = ['gcov', '-b', '-c', '-o', os.path.dirname(path), path]
            try:
                LOG.debug("Running: %s (cwd=%s)", ' '.join(cmd), tmpdir)
                subprocess.run(cmd, cwd=tmpdir, check=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
            except FileNotFoundError:
                LOG.error("'gcov' is not available on PATH. Please install gcov.")
                return {}
            except subprocess.CalledProcessError as err:
                LOG.error("gcov failed for '%s': %s", path, err)
                return {}

            results: Dict[str, List[int]] = {}
            for root, _, files in os.walk(tmpdir):
                for name in files:
                    if not name.endswith('.gcov'):
                        continue
                    fpath = os.path.join(root, name)
                    parsed = self._parse_gcov_file(fpath)
                    for src, lines in parsed.items():
                        results[src] = sorted(set(results.get(src, [])) | set(lines))
            return results

    def _parse_gcov_file(self, gcov_path: str) -> Dict[str, List[int]]:
        """Parse a .gcov file to {source -> sorted covered line numbers}."""
        current_src = None
        covered: Dict[str, List[int]] = {}
        try:
            with open(gcov_path, 'r', encoding='utf-8', errors='replace') as f:
                for raw in f:
                    line = raw.rstrip('\n')
                    stripped = line.lstrip()
                    if stripped.startswith('-:') and 'Source:' in stripped:
                        try:
                            src = stripped.split('Source:', 1)[1].strip()
                        except Exception:  # noqa
                            src = None
                        if src:
                            norm = os.path.normpath(src)
                            current_src = norm
                            if current_src not in covered:
                                covered[current_src] = []
                        continue

                    parts = stripped.split(':', 2)
                    if len(parts) < 2:
                        continue
                    exec_count = parts[0].strip()
                    try:
                        lineno = int(parts[1])
                    except ValueError:
                        continue

                    if current_src is None or lineno <= 0:
                        continue

                    if exec_count == '#####' or exec_count == '-':
                        continue

                    try:
                        count = int(exec_count)
                    except ValueError:
                        continue

                    if count > 0:
                        covered[current_src].append(lineno)

            for k, v in list(covered.items()):
                covered[k] = sorted(set(v))
        except OSError as err:
            LOG.error("Failed to read gcov file '%s': %s", gcov_path, err)
            return {}

        return covered


