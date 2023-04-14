from typing import List

import file_manager
from average_fault_localization import AverageFaultLocalization
from combine_fl_manager import CombineFlManager
from csv_score_function_granularity_manager import CsvScoreItemFunctionGranularityManager
from csv_score_item_module_granularity_manager import CsvScoreItemModuleGranularityManager
from csv_score_load_manager import CsvScoreItemLoadManager, FLTechnique
from hierarchical_fault_localization import HierarchicalFaultLocalization
from result_manager import ResultManager
from selected_bugs_types import assign_type_to_selected_bugs


def are_all_different_in_list(item_list) -> bool:
    if len(item_list) == 0:
        return False

    for index_1 in range(0, len(item_list)):
        for index_2 in range(index_1 + 1, len(item_list)):
            if item_list[index_1] == item_list[index_2]:
                return False

    return True


def get_fauxpy_statement_csv_score_items(path_manager: file_manager.PathManager):
    csv_score_item_load_manager = CsvScoreItemLoadManager(path_manager.get_results_path())
    statement_csv_score_items = csv_score_item_load_manager.load_csv_score_items()

    assign_type_to_selected_bugs(statement_csv_score_items, path_manager)

    return statement_csv_score_items


def convert_statement_csv_to_function_csv(path_manager, fauxpy_statement_csv_score_items):
    csv_score_item_function_granularity_manager = CsvScoreItemFunctionGranularityManager(
        fauxpy_statement_csv_score_items,
        path_manager.get_workspace_path())
    fauxpy_function_csv_score_items = csv_score_item_function_granularity_manager.get_function_csv_score_items()

    return fauxpy_function_csv_score_items


def convert_statement_csv_to_module_csv(fauxpy_statement_csv_score_items):
    csv_score_item_module_granularity_manager = CsvScoreItemModuleGranularityManager(fauxpy_statement_csv_score_items)
    module_csv_score_items = csv_score_item_module_granularity_manager.get_module_csv_score_items()

    return module_csv_score_items


def get_mfs_hfl_statement_csv_score_items(fauxpy_statement_csv_score_items,
                                          fauxpy_function_csv_score_items,
                                          fauxpy_module_csv_score_items):
    mfs_hfl_statement_csv_score_items = []
    for index in range(0, len(fauxpy_statement_csv_score_items)):
        print(fauxpy_statement_csv_score_items[index].get_bug_key())
        mfs_hfl = HierarchicalFaultLocalization(
            fauxpy_statement_csv_score_items[index],
            fauxpy_function_csv_score_items[index],
            fauxpy_module_csv_score_items[index])
        current_statement_csv_score_item = mfs_hfl.get_mfs_hfl_statement_csv_score_item()
        mfs_hfl_statement_csv_score_items.append(current_statement_csv_score_item)

    return mfs_hfl_statement_csv_score_items


def get_fs_hfl_statement_csv_score_items(fauxpy_statement_csv_score_items,
                                         fauxpy_function_csv_score_items,
                                         fauxpy_module_csv_score_items):
    fs_hfl_statement_csv_score_items = []
    for index in range(0, len(fauxpy_statement_csv_score_items)):
        print(fauxpy_statement_csv_score_items[index].get_bug_key())
        fs_hfl = HierarchicalFaultLocalization(
            fauxpy_statement_csv_score_items[index],
            fauxpy_function_csv_score_items[index],
            fauxpy_module_csv_score_items[index])
        current_statement_csv_score_item = fs_hfl.get_fs_hfl_statement_csv_score_item()
        fs_hfl_statement_csv_score_items.append(current_statement_csv_score_item)

    return fs_hfl_statement_csv_score_items


def get_average_fl_statement_csv_score_items(fauxpy_statement_csv_score_items):
    def get_csv_technique(technique: FLTechnique, bug_key: str):
        technique_csv = list(filter(lambda x:
                                    (x.get_technique() == technique and
                                     x.get_bug_key() == bug_key),
                                    fauxpy_statement_csv_score_items))[0]
        return technique_csv

    average_fl_statement_csv_score_item_list = []

    all_ochiai_csv_list = list(
        filter(lambda x: x.get_technique() == FLTechnique.Ochiai, fauxpy_statement_csv_score_items))
    for ochiai_csv in all_ochiai_csv_list:
        print(ochiai_csv.get_bug_key())
        dstar_csv = get_csv_technique(FLTechnique.DStar, ochiai_csv.get_bug_key())
        # metallaxis_csv = get_csv_technique(FLTechnique.Metallaxis, ochiai_csv.get_bug_key())
        # muse_csv = get_csv_technique(FLTechnique.Muse, ochiai_csv.get_bug_key())
        # ps_csv = get_csv_technique(FLTechnique.PS, ochiai_csv.get_bug_key())
        st_csv = get_csv_technique(FLTechnique.ST, ochiai_csv.get_bug_key())
        techniques_csv_list = [
            ochiai_csv,
            dstar_csv,
            # metallaxis_csv,
            # muse_csv,
            # ps_csv,
            st_csv
        ]
        average_fl = AverageFaultLocalization(techniques_csv_list, False)
        average_fl_statement_csv_score_item = average_fl.get_average_fl_statement_csv_score_item()
        average_fl_statement_csv_score_item_list.append(average_fl_statement_csv_score_item)

    return average_fl_statement_csv_score_item_list


def save_detailed(detailed_table: List, tool_name: str, granularity: str, dir_name: str):
    technique_detailed_file_name = f"{tool_name}_{granularity}_detailed.csv"
    file_manager.save_csv_to_output_dir(detailed_table,
                                        dir_name,
                                        technique_detailed_file_name)


def save_overall(overall_table: List, tool_name: str, granularity: str, dir_name: str):
    technique_overall_file_name = f"{tool_name}_{granularity}_overall.csv"
    file_manager.save_csv_to_output_dir(overall_table,
                                        dir_name,
                                        technique_overall_file_name)


def save_quantile(overall_table: List, tool_name: str, granularity: str, dir_name: str):
    quantile_file_name = f"{tool_name}_{granularity}_quantile.csv"
    file_manager.save_csv_to_output_dir(overall_table,
                                        dir_name,
                                        quantile_file_name)


def calc_fauxpy_statement_and_save(fauxpy_statement_csv_score_items, ground_truth_info, size_counts_info):
    fauxpy_statement_result_manager = ResultManager(fauxpy_statement_csv_score_items,
                                                    ground_truth_info,
                                                    size_counts_info,
                                                    True)
    all_detailed_tables, all_overall_table = fauxpy_statement_result_manager.get_metric_results()

    all_quantiles = fauxpy_statement_result_manager.get_score_based_quantile_function()

    dir_name = "output_fauxpy_statement"
    file_manager.clean_make_output_dir(dir_name)
    save_detailed(all_detailed_tables, "fauxpy", "statement", dir_name)
    save_overall(all_overall_table, "fauxpy", "statement", dir_name)
    save_quantile(all_quantiles, "fauxpy", "statement", dir_name)


def calc_fauxpy_function_and_save(fauxpy_function_csv_score_items, ground_truth_info, size_counts_info):
    fauxpy_result_manager = ResultManager(fauxpy_function_csv_score_items,
                                          ground_truth_info,
                                          size_counts_info)
    literature_detailed_tables, literature_overall_table = fauxpy_result_manager.get_metric_results()
    dir_name = "output_fauxpy_function"
    file_manager.clean_make_output_dir(dir_name)
    save_detailed(literature_detailed_tables, "fauxpy", "function", dir_name)
    save_overall(literature_overall_table, "fauxpy", "function", dir_name)


def calc_fauxpy_module_and_save(fauxpy_module_csv_score_items, ground_truth_info, size_counts_info):
    fauxpy_result_manager = ResultManager(fauxpy_module_csv_score_items,
                                          ground_truth_info,
                                          size_counts_info)
    literature_detailed_tables, literature_overall_table = fauxpy_result_manager.get_metric_results()
    dir_name = "output_fauxpy_module"
    file_manager.clean_make_output_dir(dir_name)
    save_detailed(literature_detailed_tables, "fauxpy", "module", dir_name)
    save_overall(literature_overall_table, "fauxpy", "module", dir_name)


def calc_mfs_hfl_statement_and_save(mfs_hfl_statement_csv_score_items, ground_truth_info, size_counts_info):
    mfs_hfl_statement_result_manager = ResultManager(mfs_hfl_statement_csv_score_items,
                                                     ground_truth_info,
                                                     size_counts_info,
                                                     True)
    literature_detailed_tables, literature_overall_table = mfs_hfl_statement_result_manager.get_metric_results()
    dir_name = "output_mfs_hfl_statement"
    file_manager.clean_make_output_dir(dir_name)
    save_detailed(literature_detailed_tables, "mfs_hfl", "statement", dir_name)
    save_overall(literature_overall_table, "mfs_hfl", "statement", dir_name)


def calc_fs_hfl_statement_and_save(fs_hfl_statement_csv_score_items, ground_truth_info, size_counts_info):
    fs_hfl_statement_result_manager = ResultManager(fs_hfl_statement_csv_score_items,
                                                    ground_truth_info,
                                                    size_counts_info,
                                                    True)
    literature_detailed_tables, literature_overall_table = fs_hfl_statement_result_manager.get_metric_results()
    dir_name = "output_fs_hfl_statement"
    file_manager.clean_make_output_dir(dir_name)
    save_detailed(literature_detailed_tables, "fs_hfl", "statement", dir_name)
    save_overall(literature_overall_table, "fs_hfl", "statement", dir_name)


def calc_average_fl_statement_and_save(average_fl_statement_csv_score_items, ground_truth_info, size_counts_info):
    average_fl_statement_result_manager = ResultManager(average_fl_statement_csv_score_items,
                                                        ground_truth_info,
                                                        size_counts_info,
                                                        True)
    literature_detailed_tables, literature_overall_table = average_fl_statement_result_manager.get_metric_results()
    dir_name = "output_average_fl_statement"
    file_manager.clean_make_output_dir(dir_name)
    save_detailed(literature_detailed_tables, "average_fl", "statement", dir_name)
    save_overall(literature_overall_table, "average_fl", "statement", dir_name)


def main():
    path_manager = file_manager.PathManager()
    ground_truth_info = file_manager.load_json_to_dictionary(path_manager.get_ground_truth_file_name())
    size_counts_info = file_manager.load_json_to_dictionary(path_manager.get_size_counts_file_name())

    fauxpy_statement_csv_score_items = file_manager.Cache.load("fauxpy_statement_csv_score_items")
    if fauxpy_statement_csv_score_items is None:
        fauxpy_statement_csv_score_items = get_fauxpy_statement_csv_score_items(path_manager)
        file_manager.Cache.save(fauxpy_statement_csv_score_items, "fauxpy_statement_csv_score_items")

    # file_manager.save_score_items_to_given_directory_path(path_manager.get_statement_csv_score_directory_path(),
    #                                                       fauxpy_statement_csv_score_items)
    # calc_fauxpy_statement_and_save(fauxpy_statement_csv_score_items, ground_truth_info, size_counts_info)

    # fauxpy_function_csv_score_items = file_manager.Cache.load("fauxpy_function_csv_score_items")
    # if fauxpy_function_csv_score_items is None:
    #     fauxpy_function_csv_score_items = convert_statement_csv_to_function_csv(path_manager,
    #                                                                             fauxpy_statement_csv_score_items)
    #     file_manager.Cache.save(fauxpy_function_csv_score_items, "fauxpy_function_csv_score_items")
    #
    # file_manager.save_score_items_to_given_directory_path(path_manager.get_function_csv_score_directory_path(),
    #                                                       fauxpy_function_csv_score_items)
    # calc_fauxpy_function_and_save(fauxpy_function_csv_score_items, ground_truth_info, size_counts_info)
    #
    # fauxpy_module_csv_score_items = convert_statement_csv_to_module_csv(fauxpy_statement_csv_score_items)
    # file_manager.save_score_items_to_given_directory_path(path_manager.get_module_csv_score_directory_path(),
    #                                                       fauxpy_module_csv_score_items)
    # calc_fauxpy_module_and_save(fauxpy_module_csv_score_items, ground_truth_info, size_counts_info)
    #
    # mfs_hfl_statement_csv_score_items = get_mfs_hfl_statement_csv_score_items(fauxpy_statement_csv_score_items,
    #                                                                           fauxpy_function_csv_score_items,
    #                                                                           fauxpy_module_csv_score_items)
    # calc_mfs_hfl_statement_and_save(mfs_hfl_statement_csv_score_items, ground_truth_info, size_counts_info)
    #
    # fs_hfl_statement_csv_score_items = get_fs_hfl_statement_csv_score_items(fauxpy_statement_csv_score_items,
    #                                                                         fauxpy_function_csv_score_items,
    #                                                                         fauxpy_module_csv_score_items)
    # calc_fs_hfl_statement_and_save(fs_hfl_statement_csv_score_items, ground_truth_info, size_counts_info)
    #
    average_fl_statement_csv_score_items = get_average_fl_statement_csv_score_items(fauxpy_statement_csv_score_items)
    calc_average_fl_statement_and_save(average_fl_statement_csv_score_items, ground_truth_info, size_counts_info)


def generate_combine_fl_data_input():
    path_manager = file_manager.PathManager()
    ground_truth_info = file_manager.load_json_to_dictionary(path_manager.get_ground_truth_file_name())
    size_counts_info = file_manager.load_json_to_dictionary(path_manager.get_size_counts_file_name())
    fauxpy_statement_csv_score_items = get_fauxpy_statement_csv_score_items(path_manager)

    combine_fl_manager = CombineFlManager(fauxpy_statement_csv_score_items, ground_truth_info, size_counts_info)
    release_json_dict_list = combine_fl_manager.get_release_json_dict_list()
    qid_lines_csv_table = combine_fl_manager.get_qid_lines_csv_table()
    techniques_str = combine_fl_manager.get_techniques_sorted_as_string()
    projects_str = combine_fl_manager.get_projects_sorted_as_string()

    directory_name = "inputs_to_combine_fl"
    output_dir_path = file_manager.clean_make_output_dir(directory_name)

    for index, release_json_dict_item in enumerate(release_json_dict_list):
        file_manager.save_dictionary_to_json(release_json_dict_item, output_dir_path / f"python_release_{index}.json")
    file_manager.save_csv_to_output_dir(qid_lines_csv_table, directory_name, "python_qid-lines.csv")
    file_manager.save_string_to_file(techniques_str, output_dir_path / "techniques.txt")
    file_manager.save_string_to_file(projects_str, output_dir_path / "projects.txt")


if __name__ == '__main__':
    # generate_combine_fl_data_input()
    main()
