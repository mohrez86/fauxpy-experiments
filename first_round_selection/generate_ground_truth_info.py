import ast
import re
from enum import Enum
from pathlib import Path
from typing import Tuple, List, Any, Dict

import common
from ast_manager import ScopeManager

CORRECT = {}
PATCH_INFO_FILE_NAME: str = "ground_truth_info.json"


class ConsumeMode(Enum):
    Normal = 0
    Remove = 1
    Edit = 2
    Add = 3


def get_patch_parts(patch) -> List[List[str]]:
    patch_parts = []
    # patch_lines = patch.split("\n")
    patch_lines = patch.splitlines()
    part_lines = []
    for patch_line in patch_lines:
        meta_line_list = re.findall(r"@@.*@@", patch_line)
        if len(meta_line_list) > 0:
            if len(part_lines) > 0:
                patch_parts.append(part_lines)
            part_lines = []
        part_lines.append(patch_line)
    patch_parts.append(part_lines)

    return patch_parts


def get_patch_part_meta_info(meta_info_line: str):
    meta_info_list_buggy_start = re.findall(r"@@ -(\d+).*@@", meta_info_line)
    meta_info_list_buggy_number_lines = re.findall(r"@@ -\d+,(\d+).*@@", meta_info_line)
    assert len(meta_info_list_buggy_start) == 1
    assert len(meta_info_list_buggy_number_lines) == 1
    starting_buggy_line = meta_info_list_buggy_start[0]
    number_buggy_line = meta_info_list_buggy_number_lines[0]

    meta_info_list_fixed_start = re.findall(r"@@ -\d+,\d+ \+(\d+).*@@", meta_info_line)
    meta_info_list_fixed_number_lines = re.findall(r"@@ -\d+,\d+ \+\d+,(\d+).*@@", meta_info_line)
    assert len(meta_info_list_fixed_start) == 1
    assert len(meta_info_list_fixed_number_lines) == 1
    starting_fixed_line = meta_info_list_fixed_start[0]
    number_fixed_line = meta_info_list_fixed_number_lines[0]

    return int(starting_buggy_line), int(number_buggy_line), int(starting_fixed_line), int(number_fixed_line)


def is_code_line(line: str):
    line_strip = line.strip()
    return (line_strip != "" and
            not line_strip.startswith("#") and
            not line_strip.startswith("'''") and
            not line_strip.startswith('"""'))


def is_decl(line: str):
    """
    FauxPy uses Coverage.py, which does not report
    function and class declarations
    and decorators in its execution trace,
    which is the case for most
    fault localization tools. Thus,
    for the add mode, if we see any of these,
    we skip them and keep the code
    line before (ground truth extension)
    or after them (ground truth).
    """

    line_strip = line.strip()
    return (line_strip.startswith("def") or
            line_strip.startswith("class") and
            line_strip.startswith('@'))


def diff_index_to_buggy_index(lines: List[str],
                              diff_index: int):
    offset = 0
    for index in range(0, diff_index):
        if lines[index].startswith("+"):
            offset += 1

    return diff_index - offset


def diff_index_to_fixed_index(lines: List[str],
                              diff_index: int):
    offset = 0
    for index in range(0, diff_index):
        if lines[index].startswith("-"):
            offset += 1

    return diff_index - offset


def is_docstring(buggy_content: str,
                 file_line_num: int):
    class DocstringVisitor(ast.NodeVisitor):
        def __init__(self, line_num: int):
            self.line_num = line_num
            self.line_num_is_docstring = False

        def visit_Expr(self, node: ast.Expr) -> Any:
            if node.lineno <= self.line_num <= node.end_lineno:
                self.line_num_is_docstring = True
            ast.NodeVisitor.generic_visit(self, node)

        def is_docstring(self):
            return self.line_num_is_docstring

    ast_tree = ast.parse(buggy_content)
    visitor = DocstringVisitor(file_line_num)
    visitor.visit(ast_tree)
    is_that = visitor.is_docstring()
    return is_that


def consume(lines: List[str],
            patch_part_starting_buggy_line: int,
            patch_part_starting_fixed_line: int,
            buggy_content: str,
            fixed_content: str,
            fixed_buggy_map: Dict[int, int]) -> Tuple[List[int], List[int]]:
    """
    This function implements a state machine that consumes diffs
    to figure out which lines need to be included in
    the ground truth (i.e., code_lines). It looks for
    three cases:

    1. one or more minus (-) signs, which means remove.
    they should all be included in the ground truth.

    2. One or more plus (+) signs, proceeding one or more minus
    signs which means edit. In this case, only the removed lines
    are included in the ground truth.

    3. One or more plus signs with no minus signs
    before them, which means add.
    In this case, the code line (not empty or comment lines) coming
    right after the plus signs is added to the ground truth.
    We also add the code line before the plus signs to the
    extended version of the ground truth (i.e., code_extended_lines).
    """

    code_lines = []
    code_extended_lines = []
    consume_mode = ConsumeMode.Normal

    start_add_diff_index = None
    end_add_diff_index = None

    buggy_content_lines = buggy_content.splitlines()

    none_code_line_removed_in_edit_counter = 0
    code_line_added_in_edit_counter = 0
    code_line_added_in_add_counter = 0

    for index, line in enumerate(lines):
        if line.startswith("-"):
            assert consume_mode == ConsumeMode.Normal or consume_mode == ConsumeMode.Remove

            consume_mode = ConsumeMode.Remove
            rel_buggy_index = diff_index_to_buggy_index(lines, index)
            abs_buggy_index = rel_buggy_index + patch_part_starting_buggy_line
            if abs_buggy_index not in code_lines:
                code_lines.append(abs_buggy_index)
                if not is_code_line(line[1:]):
                    none_code_line_removed_in_edit_counter += 1
        elif line.startswith("+"):
            if consume_mode == ConsumeMode.Normal:
                consume_mode = ConsumeMode.Add
            elif consume_mode == ConsumeMode.Remove:
                consume_mode = ConsumeMode.Edit

            if consume_mode == ConsumeMode.Add:
                if start_add_diff_index is None:
                    start_add_diff_index = index
                end_add_diff_index = index
                if is_code_line(line[1:]):
                    code_line_added_in_add_counter += 1
            elif consume_mode == ConsumeMode.Edit:
                if is_code_line(line[1:]):
                    code_line_added_in_edit_counter += 1
        else:
            if consume_mode == ConsumeMode.Edit:
                if (none_code_line_removed_in_edit_counter == len(code_lines) and
                        code_line_added_in_edit_counter != 0):
                    print("Manual check! Edit none code!")

            none_code_line_removed_in_edit_counter = 0
            code_line_added_in_edit_counter = 0

            if consume_mode == ConsumeMode.Add and code_line_added_in_add_counter > 0:
                # for ind in range(end_add_diff_index + 1, len(lines)):
                #     if is_code_line(lines[ind]):
                #         rel_buggy_index = diff_index_to_buggy_index(lines, ind)
                #         abs_buggy_index = rel_buggy_index + patch_part_starting_line
                #         if abs_buggy_index not in code_lines:
                #             code_lines.append(abs_buggy_index)
                #         break

                rel_diff_fixed_start_add_index = diff_index_to_fixed_index(lines, start_add_diff_index)
                abs_file_fixed_start_add_index = rel_diff_fixed_start_add_index + patch_part_starting_fixed_line
                rel_diff_fixed_end_add_index = diff_index_to_fixed_index(lines, end_add_diff_index)
                abs_diff_fixed_end_add_index = rel_diff_fixed_end_add_index + patch_part_starting_fixed_line

                print(abs_file_fixed_start_add_index, abs_diff_fixed_end_add_index)

                rel_diff_buggy_start_add_index = diff_index_to_buggy_index(lines, start_add_diff_index)
                # rel_diff_buggy_end_add_index = diff_index_to_buggy_index(lines, end_add_diff_index)
                # abs_file_buggy_start_add_line_num = patch_part_starting_line + rel_diff_buggy_start_add_index
                # abs_file_buggy_end_add_line_num = patch_part_starting_line + rel_diff_buggy_end_add_index
                rel_diff_buggy_before_add_index = rel_diff_buggy_start_add_index - 1
                abs_file_buggy_before_add_line_num = patch_part_starting_buggy_line + rel_diff_buggy_before_add_index
                abs_file_buggy_before_add_index = abs_file_buggy_before_add_line_num - 1

                # assert abs_file_buggy_start_add_line_num == abs_file_buggy_end_add_line_num == abs_file_buggy_before_add_line_num + 1

                scope_range_obj = ScopeManager(buggy_content,
                                               abs_file_buggy_before_add_line_num)
                scope_lines = scope_range_obj.get_sorted_scope_lines()
                if len(scope_lines) == 0:
                    print("Scope empty!")

                # for ind in range(abs_file_buggy_before_add_index + 1, len(buggy_content_lines)):
                for file_line_num in scope_lines:
                    ind = file_line_num - 1
                    if ind <= abs_file_buggy_before_add_index:
                        continue
                    # lxt = buggy_content_lines[ind]
                    # file_line_num = ind + 1
                    if (is_code_line(buggy_content_lines[ind]) and
                            not is_decl(buggy_content_lines[ind]) and
                            not is_docstring(buggy_content, file_line_num)):
                        # rel_buggy_index = diff_index_to_buggy_index(lines, ind)
                        # abs_buggy_index = rel_buggy_index + patch_part_starting_line
                        if file_line_num not in code_lines:
                            code_lines.append(file_line_num)
                        break

                # for ind in range(start_add_diff_index - 1, -1, -1):
                #     if is_code_line(lines[ind]):
                #         rel_buggy_index = diff_index_to_buggy_index(lines, ind)
                #         abs_buggy_index = rel_buggy_index + patch_part_starting_line
                #         if abs_buggy_index not in code_extended_lines and abs_buggy_index not in code_lines:
                #             code_extended_lines.append(abs_buggy_index)
                #         break

                scope_lines.reverse()
                # for ind in range(abs_file_buggy_before_add_index, -1, -1):
                for file_line_num in scope_lines:
                    ind = file_line_num - 1
                    if ind > abs_file_buggy_before_add_index:
                        continue
                    # file_line_num = ind + 1
                    if (is_code_line(buggy_content_lines[ind]) and
                            not is_decl(buggy_content_lines[ind]) and
                            not is_docstring(buggy_content, file_line_num)):
                        # rel_buggy_index = diff_index_to_buggy_index(lines, ind)
                        # abs_buggy_index = rel_buggy_index + patch_part_starting_line
                        if file_line_num not in code_extended_lines and file_line_num not in code_lines:
                            code_extended_lines.append(file_line_num)
                        break

            consume_mode = ConsumeMode.Normal
            start_add_diff_index = None
            end_add_diff_index = None
            code_line_added_in_add_counter = 0

    return code_lines, code_extended_lines


def fixed_to_buggy_map(patch_parts, fixed_content_line_numbers):
    f_to_b_map = {}
    last_seen_fixed_line = 0

    delta = 0
    for patch_part in patch_parts:
        meta_info_line = patch_part[0]

        (starting_buggy_line,
         number_buggy_line,
         starting_fixed_line,
         number_fixed_line) = get_patch_part_meta_info(meta_info_line)

        delta = starting_fixed_line - starting_buggy_line

        for fixed_line in range(last_seen_fixed_line + 1, starting_fixed_line):
            f_to_b_map[fixed_line] = fixed_line - delta
            last_seen_fixed_line = fixed_line

        # c_1_m = list(f_to_b_map.items())[-1]
        # print(c_1_m)

        lines = patch_part[1:]
        rem_line_num = 0
        for patch_index, patch_line in enumerate(lines):
            fixed_line = patch_index - rem_line_num + starting_fixed_line
            if patch_line.startswith("+"):
                delta += 1
                last_seen_fixed_line = fixed_line
            elif patch_line.startswith("-"):
                delta -= 1
                rem_line_num += 1
            else:
                # fixed_line = patch_index - rem_line_num + starting_fixed_line
                f_to_b_map[fixed_line] = fixed_line - delta
                last_seen_fixed_line = fixed_line

        # c_1_m = list(f_to_b_map.items())[-1]
        # print(c_1_m)

    for fixed_line in range(last_seen_fixed_line + 1, fixed_content_line_numbers + 1):
        f_to_b_map[fixed_line] = fixed_line - delta

    # c_1_m = list(f_to_b_map.items())[-1]
    # print(c_1_m)

    return f_to_b_map


def map_check(fixed_buggy_map: Dict[int, int],
              buggy_content: str,
              fixed_content: str):
    buggy_content_lines = buggy_content.splitlines()
    fixed_content_lines = fixed_content.splitlines()

    for key, value in fixed_buggy_map.items():
        buggy_line = buggy_content_lines[value - 1]
        fixed_line = fixed_content_lines[key - 1]
        if fixed_line != buggy_line:
            print(key, fixed_line)
            print(value, buggy_line)
        assert fixed_line == buggy_line


def get_file_ground_truth(patch: str,
                          buggy_content: str,
                          fixed_content: str) -> Tuple[List[int], List[int]]:
    code_lines = []
    code_extended_lines = []

    # buggy_content_lines = buggy_content.splitlines()
    patch_parts = get_patch_parts(patch)
    fixed_buggy_map = fixed_to_buggy_map(patch_parts, len(fixed_content.splitlines()))

    map_check(fixed_buggy_map, buggy_content, fixed_content)

    for patch_part in patch_parts:
        meta_info_line = patch_part[0]
        (starting_buggy_line,
         number_buggy_line,
         starting_fixed_line,
         number_fixed_line) = get_patch_part_meta_info(meta_info_line)
        lines = patch_part[1:]
        current_code_lines, current_code_extended_lines = consume(lines, starting_buggy_line, starting_fixed_line,
                                                                  buggy_content, fixed_content, fixed_buggy_map)
        # code_lines += [x + starting_buggy_line for x in relative_code_lines]
        # code_extended_lines += [x + starting_buggy_line for x in relative_code_extended_lines]
        code_lines += current_code_lines
        code_extended_lines += current_code_extended_lines
    return code_lines, code_extended_lines


def get_bug_ground_truth(benchmark_name: str,
                         bug_number: int):
    python_none_test_files = common.get_diff_commit(benchmark_name, bug_number)

    but_ground_truth = []

    # python_none_test_files = list(filter(lambda x:
    #                                      x.filename.endswith(".py") and
    #                                      "test/" not in x.filename and
    #                                      "tests/" not in x.filename,
    #                                      diff_commit.files))

    for file in python_none_test_files:
        filename = file.filename
        patch = file.patch
        buggy_content = file.buggy_content
        fixed_content = file.fixed_content
        lines, extended_lines = get_file_ground_truth(patch, buggy_content, fixed_content)
        but_ground_truth.append(
            {
                "FILE_NAME": filename,
                "LINES": lines,
                "EXTENDED_LINES": extended_lines
            }
        )
    return but_ground_truth


def calculate_all_line_nums(bug_patch_info):
    lines_num = 0
    for item in bug_patch_info:
        lines_num += len(item["LINES"])

    return lines_num


def main():
    global CORRECT

    CORRECT = common.load_correct_test_bugs()

    patch_info_dict = {}

    for benchmark_name, benchmark_items in CORRECT.items():
        for bug_number in benchmark_items["ACCEPTED"]:

            # if benchmark_name != "cookiecutter" or bug_number != 2:
            #     continue

            print(benchmark_name, bug_number)
            bug_patch_info = get_bug_ground_truth(benchmark_name, bug_number)
            all_line_nums = calculate_all_line_nums(bug_patch_info)
            if all_line_nums <= 0:
                print("Manual check! Empty lines in: ", benchmark_name, bug_number)
            patch_info_dict[f"{benchmark_name}:{bug_number}"] = bug_patch_info

    common.save_object_to_json(patch_info_dict, Path(PATCH_INFO_FILE_NAME))


if __name__ == '__main__':
    main()
