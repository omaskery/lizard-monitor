from lizard_mon.exceptions import *
import lizard_mon
import argparse
import typing
import lizard
import git
import sys
import os


def main():
    parser = argparse.ArgumentParser(
        description="utility for applying the lizard.py analysis tools to git repositories automatically"
    )
    parser.add_argument(
        '--path', default='.', help='directory to treat as current working directory'
    )
    args = parser.parse_args()
    base_path = args.path

    config_path = os.path.join(base_path, "lizard-mon.yml")
    targets = lizard_mon.config.load_config(config_path)

    overall_analysis_results = AnalysisResult(0, 0)
    for target in targets:
        print(f"{target.name} ({target.repo_info.url}):")
        root_repo_dir = os.path.join(base_path, "repos")
        repo = get_repo(root_repo_dir, target.name, target.repo_info)

        print(f"  running analysis on {repo.working_tree_dir}")
        analysis_results = analyse_repo(repo, target.analysis_settings)
        target_analysis_results = AnalysisResult(0, 0)
        for result in analysis_results.values():
            target_analysis_results.merge_with(result)
        overall_analysis_results.merge_with(target_analysis_results)
        print(f"  results for this repo: {target_analysis_results}")
    print(f"overall results: {overall_analysis_results}")


def analyse_repo(repo: git.Repo, analysis_settings: 'lizard_mon.config.AnalysisSettings'):
    violation_record = {}

    analysis_dir = os.path.relpath(repo.working_tree_dir)

    def patch_relative_exclude_patterns(pattern):
        if pattern.startswith("./") or pattern.startswith(".\\"):
            patched = os.path.join(analysis_dir, pattern[2:])
        else:
            patched = pattern
        patched = patched.replace("\\", "/")
        return patched

    exclusion_patterns = [
        patch_relative_exclude_patterns(pattern)
        for pattern in analysis_settings.exclusion_patterns
    ]
    for pattern in exclusion_patterns:
        print("  excluding:", pattern)
    analysis = lizard.analyze(
        paths=[analysis_dir],
        exclude_pattern=exclusion_patterns,
        threads=os.cpu_count(),
        exts=lizard.get_extensions([]),
        lans=analysis_settings.languages,
    )
    analysis = typing.cast(typing.List[lizard.FileInformation], analysis)
    thresholds = analysis_settings.limits
    for result in analysis:
        print(f"  - file: {result.filename} (NLOC={result.nloc})")
        violations_in_this_file = 0

        for fn in result.function_list:
            values = lizard_mon.config.AnalysisLimits(
                fn.cyclomatic_complexity,
                fn.nloc,
                len(fn.parameters),
            )

            if not values.exceeds(thresholds):
                continue

            violations = lizard_mon.config.list_limit_violations(values, thresholds)
            violations_in_this_file += 1

            print(f"    - {fn.long_name} [{fn.start_line}:{fn.end_line}]")
            print(f"      violations: {', '.join(violations)}")

        file_analysis_result = AnalysisResult(violations_in_this_file, result.nloc)
        print(f"    results for this file: {file_analysis_result}")
        violation_record[result.filename] = file_analysis_result

    return violation_record


def die(message, exit_code=-1) -> typing.NoReturn:
    print(message, file=sys.stderr)
    sys.exit(exit_code)


def get_repo(repos_dir, name, repo_info):
    repo_working_dir = os.path.join(repos_dir, name)
    if not os.path.isdir(repo_working_dir):
        print(f"  cloning '{name}' for first time from: {repo_info.url}")
        repo = git.Repo.clone_from(repo_info.url, repo_working_dir, branch=repo_info.branch)
    else:
        repo = git.Repo(repo_working_dir)
        if len(repo.remotes) < 1:
            print(f"  warning: target {name} repo has no remotes to pull from")
        else:
            remote = repo.remotes[0]
            print(f"  pulling any changes from remote {remote.name}")
            remote.pull()
        if repo.active_branch.name != repo_info.branch:
            if repo_info.branch not in repo.heads:
                raise LizardMonException(f"target {name} repo has no branch '{repo_info.branch}'")
            print(f"changing branch [{repo.active_branch.name} -> {repo_info.branch}]")
            repo.heads[repo_info.branch].checkout()
    return repo


class AnalysisResult:

    def __init__(self, violation_count: int, lines_of_code: int):
        self.violation_count = violation_count
        self.lines_of_code = lines_of_code

    def merge_with(self, other: 'AnalysisResult'):
        self.violation_count += other.violation_count
        self.lines_of_code += other.lines_of_code

    def __str__(self):
        return f"[violations: {self.violation_count}, NLOC={self.lines_of_code}]"


if __name__ == "__main__":
    try:
        main()
    except LizardMonException as lme:
        print(f"error: {lme}")
