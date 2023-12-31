# pip install PyGithub
import datetime
import os
import pickle
from pathlib import Path
from typing import List, Dict

import common
from call_graph import is_affecting_test_module, affected_test_modules

INFO = {}
TIME_SELECTED = {}
SUBJECT_INFO_CSV_FILE_NAME = "subject_info.csv"
CACHE_DIR_NAME = "cache_subject_info"


def load_info():
    global TIME_SELECTED
    global INFO

    TIME_SELECTED = common.load_json_to_dictionary(common.TIME_SELECTED_BUGS_FILE_NAME)
    del TIME_SELECTED["NUM_BUGS"]
    # del TIME_SELECTED["TIME_ESTIMATION_HOURS"]
    # del TIME_SELECTED["TIME_ESTIMATION_DAYS"]
    # del TIME_SELECTED["TIME_ESTIMATION_WEEKS"]

    json_files = list(Path(common.SUBJECT_INFO_DIRECTORY_NAME).rglob("*.json"))
    json_files_2 = list(Path(common.SUBJECT_INFO_DIRECTORY_NAME_2).rglob("*.json"))
    json_files_1_and_2 = json_files + json_files_2
    json_files_1_and_2.sort()
    for item in json_files_1_and_2:
        benchmark_info = common.load_json_to_dictionary(str(item.absolute().resolve()))
        INFO[benchmark_info["BENCHMARK_NAME"]] = benchmark_info


def unittest_to_pytest(item):
    elements = item.split(".")
    if len(elements) == 4:
        return f"{elements[0]}/{elements[1]}.py::{elements[2]}::{elements[3]}"
    elif len(elements) == 5:
        return f"{elements[0]}/{elements[1]}/{elements[2]}.py::{elements[3]}::{elements[4]}"
    elif len(elements) == 3:
        print("3 element test..")
        return f"{elements[0]}/{elements[1]}.py::{elements[2]}"
    else:
        raise Exception("Problem!")


def get_generalized_test(item):
    return item.split("[")[0]


def get_reformatted_target_failing_tests(original_target_tests: List[str]) -> List[str]:
    reformatted_target_tests = []

    for item in original_target_tests:
        generalized_original = get_generalized_test(item)
        if "/" in generalized_original.lower() and ".py" in generalized_original.lower():
            reformatted_target_tests.append(generalized_original)
        else:
            assert "/" not in generalized_original.lower()
            assert ".py" not in generalized_original.lower()

            generalized_original = unittest_to_pytest(generalized_original)
            reformatted_target_tests.append(generalized_original)

        # if item != generalized_original:
        #     print("Reformat test")
        #     print(item)
        #     print(generalized_original)
        #     print("------------")

    return reformatted_target_tests


def get_target_failing_tests(benchmark_name: str,
                             bug_num: int) -> List[str]:
    buggy_path = common.get_buggy_project_path(benchmark_name, bug_num)
    run_test_file_path = buggy_path / common.RUN_TEST_FILE_NAME

    content = common.read_file_content(run_test_file_path)

    target_tests_in_content = list(filter(
        lambda x: x.lower().startswith("test") or
                  x.lower().startswith("tests") or
                  x.lower().startswith("pandas/tests") or
                  x.lower().startswith("pandas/test") or
                  x.lower().startswith("spacy/tests") or
                  x.lower().startswith("spacy/test") or
                  x.lower().startswith("tornado.test") or
                  x.lower().startswith("tornado.tests") or
                  x.lower().startswith("tqdm/tests") or
                  x.lower().startswith("tqdm/test"), content.split()))

    target_failing_tests = get_reformatted_target_failing_tests(target_tests_in_content)

    return target_failing_tests


# Only used for analysis. Not in the pipeline.
def get_target_dir(benchmark_name: str,
                   bug_num: int):
    default_target_dir = INFO[benchmark_name]["TARGET_DIR"]

    if default_target_dir == ".":
        return "."

    changed_modules = common.get_changed_modules(benchmark_name, bug_num)

    target_dir = INFO[benchmark_name]["TARGET_DIR"]
    for item in changed_modules:
        if not item.startswith(target_dir):
            print(benchmark_name, bug_num)
            print(item)


def get_test_suite(benchmark_name: str,
                   bug_num: int,
                   target_failing_tests: List[str]) -> List[str]:
    # if benchmark_name != "fastapi":
    #     return []

    buggy_proj_path = common.get_buggy_project_path(benchmark_name, bug_num)
    changed_modules = common.get_changed_modules(benchmark_name, bug_num)
    test_suite_path = buggy_proj_path / INFO[benchmark_name]["TEST_SUITE"][0]
    # test_module_paths = list(test_suite_path.rglob("test_*.py")) + list(test_suite_path.rglob("*_test.py"))
    test_module_paths = list(test_suite_path.rglob("test_*.py")) + list(test_suite_path.rglob("*_test.py")) + list(
        test_suite_path.rglob("*tests*.py"))

    if benchmark_name == "pandas":
        source_code_packages = [str((buggy_proj_path / "pandas").absolute().resolve())]
    else:
        source_code_packages = [str(buggy_proj_path.absolute().resolve())]

    print(benchmark_name, bug_num)
    print(changed_modules)

    selected_test_modules = []
    for item in test_module_paths:
        print("Analyze test module: ", item)
        # if "test/test_update.py" in str(item):
        #     continue

        if "tests/keras/layers/merge_test.py" in str(item) and benchmark_name == "keras":
            # Let's just select "merge_test.py" module.
            # It has around 10 tests which are very fast to run.
            # The call graph generation takes forever.
            keep_it = True
        elif "test/test_download.py" in str(item) and benchmark_name == "youtube-dl":
            # Remove test/test_download.py because it is too slow.
            # It is not necessary thought.
            keep_it = False
        elif ("tests/rules/test_git_checkout.py" in str(item) or
              "tests/rules/test_git_two_dashes.py" in str(item) or
              "tests/rules/test_touch.py" in str(item)) and benchmark_name == "thefuck":
            # Remove three test files that have errors.
            # "tests/rules/test_git_checkout.py"
            # "tests/rules/test_git_two_dashes.py"
            # "tests/rules/test_touch.py"
            keep_it = False
        elif "tests/test_tutorial/" in str(item) and benchmark_name == "fastapi":
            # Remove the test package tests/test_tutorial.
            # These tests have bugs and stops Pytest.
            keep_it = False
        elif "spacy/tests/test_gold.py" in str(item) and benchmark_name == "spacy":
            # Let's just select "spacy/tests/test_gold.py" module.
            # The tests in it run quickly.
            # The call graph generation requires more than
            # my physical and virtual memory. So it stops.
            keep_it = True
        # elif any(map(lambda x: x in str(item), [
        #     "pandas/tests/test_downstream.py",
        #     # "pandas/tests/test_strings.py"
        # ])) and benchmark_name == "pandas":
        #     # Let's just select it.
        #     # It has around 10 tests which are very fast to run.
        #     # The call graph generation takes forever.
        #     keep_it = True
        else:
            keep_it = is_affecting_test_module(str(item.absolute().resolve()),
                                               source_code_packages,
                                               changed_modules,
                                               10)
        print(keep_it)
        if keep_it:
            selected_test_modules.append(str(item.relative_to(buggy_proj_path)))

    selected_test_modules.sort()

    print(len(selected_test_modules), len(test_module_paths))
    print(changed_modules)
    print(selected_test_modules)

    for item in target_failing_tests:
        elems = item.split("::")
        if elems[0] not in selected_test_modules:
            # print(selected_test_modules)
            print("Adding the modules of the target failing tests")
            selected_test_modules = [elems[0]] + selected_test_modules
            print(selected_test_modules)

    return selected_test_modules


def get_test_suite2(benchmark_name: str,
                    bug_num: int,
                    target_failing_tests: List[str]) -> List[str]:
    buggy_proj_path = common.get_buggy_project_path(benchmark_name, bug_num)
    changed_modules = common.get_changed_modules(benchmark_name, bug_num)
    test_suite_path = buggy_proj_path / INFO[benchmark_name]["TEST_SUITE"][0]
    # test_module_paths = list(test_suite_path.rglob("test_*.py")) + list(test_suite_path.rglob("*_test.py"))
    test_module_paths = list(test_suite_path.rglob("test_*.py")) + list(test_suite_path.rglob("*_test.py")) + list(
        test_suite_path.rglob("*tests*.py"))

    if benchmark_name == "pandas":
        source_code_packages = [str((buggy_proj_path / "pandas").absolute().resolve())]
    else:
        source_code_packages = [str(buggy_proj_path.absolute().resolve())]

    print(benchmark_name, bug_num)
    print(changed_modules)

    test_modules_analyzing = []
    test_modules_not_analyzing = []
    for item in test_module_paths:
        # print("Analyze test module: ", item)
        # if "tests/test_tutorial/" not in str(item):
        #     continue

        if "tests/keras/layers/merge_test.py" in str(item) and benchmark_name == "keras":
            # Let's just select "merge_test.py" module.
            # It has around 10 tests which are very fast to run.
            # The call graph generation takes forever.
            test_modules_not_analyzing.append(item)
        elif "test/test_download.py" in str(item) and benchmark_name == "youtube-dl":
            # Remove test/test_download.py because it is too slow.
            # It is not necessary thought.
            pass
        elif ("tests/rules/test_git_checkout.py" in str(item) or
              "tests/rules/test_git_two_dashes.py" in str(item) or
              "tests/rules/test_touch.py" in str(item)) and benchmark_name == "thefuck":
            # Remove three test files that have errors.
            # "tests/rules/test_git_checkout.py"
            # "tests/rules/test_git_two_dashes.py"
            # "tests/rules/test_touch.py"
            pass
        elif "tests/test_tutorial/" in str(item) and benchmark_name == "fastapi":
            # Remove the test package tests/test_tutorial.
            # These tests have bugs and stops Pytest.
            pass
        # elif ("spacy/tests/test_gold.py" in str(item) or
        #       "spacy/tests/test_displacy.py" in str(item)) and benchmark_name == "spacy":
        #     # Let's just select "spacy/tests/test_gold.py" module.
        #     # The call graph generation requires more than
        #     # my physical and virtual memory. So it stops.
        #     # For "spacy/tests/test_displacy.py", it cannot generate call graph.
        #     test_modules_not_analyzing.append(item)
        # elif "pandas/tests/test_downstream.py" in str(item) and benchmark_name == "pandas":
        #     # Let's just select it.
        #     # It has around 10 tests which are very fast to run.
        #     # The call graph generation takes forever.
        #     test_modules_not_analyzing.append(item)
        elif "tornado/test/asyncio_test.py" in str(item) and bug_num in [8, 10, 11, 12] and benchmark_name == "tornado":
            # This test has a syntactical error.
            pass
        else:
            test_modules_analyzing.append(item)

    test_modules_analyzing_absolute = list(map(lambda x: str(x.absolute().resolve()),
                                               test_modules_analyzing))
    affected_tests = affected_test_modules(test_modules_analyzing_absolute,
                                           source_code_packages[0],
                                           changed_modules)
    affected_tests_relative = list(map(lambda x: str(Path(x).relative_to(buggy_proj_path)),
                                       affected_tests))

    not_analyzed_tests_relative = list(map(lambda x: str(x.relative_to(buggy_proj_path)),
                                           test_modules_not_analyzing))

    affected_tests_relative = affected_tests_relative + not_analyzed_tests_relative

    affected_tests_relative.sort()

    print(len(affected_tests_relative), len(test_module_paths))
    print(changed_modules)
    print(affected_tests_relative)

    for item in target_failing_tests:
        elems = item.split("::")
        if elems[0] not in affected_tests_relative:
            # print(selected_test_modules)
            print("Adding the modules of the target failing tests")
            affected_tests_relative = [elems[0]] + affected_tests_relative
            print(affected_tests_relative)

    return affected_tests_relative


# These three (among the 320) had target directories other
# than the default ones. So, we changed their json
# information files.
# keras 9
# docs/autogen.py
# sanic 1
# examples/blueprint_middlware_execution_order.py
# sanic/app.py
# spacy 3
# bin/wiki_entity_linking/wikipedia_processor.py
def get_subject_info_for_bug(benchmark_name: str,
                             bug_num: int):
    cache_file_path = CACHE_DIR_NAME / Path(f"{benchmark_name}_{bug_num}")
    if cache_file_path.exists():
        with cache_file_path.open("rb") as file:
            record = pickle.load(file)
        return record

    target_failing_tests = get_target_failing_tests(benchmark_name, bug_num)
    # get_target_dir(benchmark_name, bug_num)

    if benchmark_name in ["spacy", "pandas", "ansible"]:
        tm1 = datetime.datetime.now()
        test_suite = get_test_suite(benchmark_name, bug_num, target_failing_tests)
        tm2 = datetime.datetime.now()
        print("Testsuite 1 time:", tm2 - tm1)
    else:
        tm1 = datetime.datetime.now()
        test_suite = get_test_suite2(benchmark_name, bug_num, target_failing_tests)
        tm2 = datetime.datetime.now()
        print("Testsuite 2 time:", tm2 - tm1)

    record = {
        "PYTHON_V": INFO[benchmark_name]["PYTHON_V"],
        "BENCHMARK_NAME": benchmark_name,
        "BUG_NUMBER": bug_num,
        "TARGET_DIR": INFO[benchmark_name]["TARGET_DIR"],
        # "TEST_SUITE": INFO[benchmark_name]["TEST_SUITE"],
        "TEST_SUITE": test_suite,
        "EXCLUDE": INFO[benchmark_name]["EXCLUDE"],
        "TARGET_FAILING_TESTS": target_failing_tests
    }

    if not os.path.exists(Path(CACHE_DIR_NAME)):
        os.mkdir(CACHE_DIR_NAME)

    with cache_file_path.open("wb") as file:
        pickle.dump(record, file)

    return record


def get_subject_infos_for_benchmark(benchmark_name: str,
                                    bugs: List[int]):
    subject_infos_for_benchmark = []

    for bug_num in bugs:
        subject_info_for_bug = get_subject_info_for_bug(benchmark_name, bug_num)
        subject_infos_for_benchmark.append(subject_info_for_bug)

    return subject_infos_for_benchmark


def python_list_to_info_list(python_list):
    if len(python_list) == 0:
        return "-"

    info_list = f"{python_list[0]}"
    for item in python_list[1:]:
        info_list += f";\n{item}"

    return info_list


def wrap_in_double_quotes(item: str):
    return f'"{item}"'


def get_csv_row(row_num, row_info):
    record_csv_format = f'{row_num},' \
                        f'{row_info["PYTHON_V"]},' \
                        f'{row_info["BENCHMARK_NAME"]},' \
                        f'{row_info["BUG_NUMBER"]},' \
                        f'{row_info["TARGET_DIR"]},' \
                        f'{wrap_in_double_quotes(python_list_to_info_list(row_info["TEST_SUITE"]))},' \
                        f'{wrap_in_double_quotes(python_list_to_info_list(row_info["EXCLUDE"]))},' \
                        f'{wrap_in_double_quotes(python_list_to_info_list(row_info["TARGET_FAILING_TESTS"]))}'

    return record_csv_format


def produce_row_number(row_info):
    benchmark_names = list(INFO.keys())
    ind = benchmark_names.index(row_info["BENCHMARK_NAME"])
    row_number = (ind + 1) * 1000 + row_info["BUG_NUMBER"]

    return row_number


def save_subject_info_list_as_csv(row_infos: List[Dict]):
    csv_rows: List[str] = []
    for index, row_info in enumerate(row_infos):
        row_number = produce_row_number(row_info)
        csv_row = get_csv_row(row_number, row_info)
        csv_rows.append(csv_row)

    with open(SUBJECT_INFO_CSV_FILE_NAME, "w") as file:
        file.write("#,PYTHON_V,BENCHMARK_NAME,BUG_NUMBER,TARGET_DIR,TEST_SUITE,EXCLUDE,TARGET_FAILING_TESTS\n")
        for csv_r in csv_rows:
            file.write(csv_r + "\n")


def main():
    load_info()

    all_subject_infos = []

    for benchmark_name, bugs in TIME_SELECTED.items():
        subject_infos_for_benchmark = get_subject_infos_for_benchmark(benchmark_name, bugs)
        all_subject_infos += subject_infos_for_benchmark

    common.save_object_to_json(all_subject_infos, Path("subject_info.json"))
    save_subject_info_list_as_csv(all_subject_infos)


# Only used for analysis. Not in the pipeline.
def checking():
    load_info()

    for benchmark_name, bugs in TIME_SELECTED.items():
        if benchmark_name == "spacy":
            # subject_infos_for_benchmark = get_subject_infos_for_benchmark(benchmark_name, bugs)
            for bug_num in bugs:
                buggy_path = common.get_buggy_project_path(benchmark_name, bug_num)
                if (buggy_path / "spacy/tests").exists():
                    print("tests")
                if (buggy_path / "spacy/test").exists():
                    print("!!!!!!!!!!!")
                if (buggy_path / "tests").exists():
                    print("!!!!!!!!!!!")
                if (buggy_path / "test").exists():
                    print("!!!!!!!!!!!")


if __name__ == '__main__':
    main()
    # checking()
