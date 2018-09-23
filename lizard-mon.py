#!/usr/bin/env python3

from lizard_mon.exceptions import *
from lizard_mon.results import *
import lizard_mon
import argparse
import datetime
import typing
import lizard
import json
import tqdm
import yaml
import git
import sys
import os


def main():
    parser = argparse.ArgumentParser(
        description="utility for applying the lizard.py analysis tools to git repositories automatically"
    )
    parser.add_argument(
        '--path', default='.', help='directory to pretend lizard-mon.py was invoked from'
    )
    parser.add_argument(
        '-v', action='count', default=0, dest="verbosity", help='level of verbosity'
    )
    parser.add_argument(
        '--at-date',
        help='date to checkout repositories to before running static analysis "<abbrev. month> <day> <year>"'
    )
    args = parser.parse_args()

    os.chdir(args.path)
    base_path = "."

    config_path = os.path.join(base_path, "lizard-mon.yml")
    targets = lizard_mon.config.load_config(config_path)

    cache_path = os.path.join(base_path, "previous-results.yml")
    if os.path.isfile(cache_path):
        with open(cache_path) as cache_file:
            cache = yaml.safe_load(cache_file)
            previous_results = ResultCache.from_yaml(cache)
    else:
        previous_results = ResultCache(AnalysisResult(), {})

    overall_analysis_results = ResultCache(AnalysisResult(), {})
    for target in targets:
        print(f"{target.name} ({target.repo_info.url}):")
        root_repo_dir = os.path.join(base_path, "repos")
        try:
            repo = get_repo(root_repo_dir, target.name, target.repo_info, args.at_date)
        except InvalidRepoDate as ex:
            print(f"  {ex}")
            continue

        print(f"  running analysis on {repo.working_tree_dir}")
        analysis_results = analyse_repo(repo, target.analysis_settings, args.verbosity)
        overall_analysis_results.overall.merge_with(analysis_results.overall)
        overall_analysis_results.targets[target.name] = analysis_results
        print(f"  results for this repo: {analysis_results.overall}")
    print(f"overall results: {overall_analysis_results.overall}")

    with open(cache_path, 'w') as cache_file:
        yaml.safe_dump(overall_analysis_results.to_yaml(), cache_file, default_flow_style=False)

    differences_path = os.path.join(base_path, "differences.yml")
    differences = overall_analysis_results.difference(previous_results)
    with open(differences_path, 'w') as differences_file:
        yaml.safe_dump(differences.to_yaml(), differences_file, default_flow_style=False)

    history_path = os.path.join(base_path, "history.ndjson")
    with open(history_path, 'a') as history_file:
        data = overall_analysis_results.to_shallow_yaml()
        data["timestamp"] = datetime.datetime.utcnow().isoformat()
        history_file.write(f"{json.dumps(data)}\n")


def analyse_repo(repo: git.Repo, analysis_settings: 'lizard_mon.config.AnalysisSettings',
                 verbosity: int) -> 'TargetResultCache':
    result = TargetResultCache(AnalysisResult(), {})

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
    file_analysis = typing.cast(typing.Iterator[lizard.FileInformation], analysis)
    thresholds = analysis_settings.limits
    for analysed_file in file_analysis:
        if verbosity > 0:
            print(f"  - file: {analysed_file.filename} (NLOC={analysed_file.nloc})")

        violations_in_this_file = 0
        for fn in analysed_file.function_list:
            values = lizard_mon.config.AnalysisLimits(
                fn.cyclomatic_complexity,
                fn.nloc,
                len(fn.parameters),
            )

            if not values.exceeds(thresholds):
                continue

            violations = lizard_mon.config.list_limit_violations(values, thresholds)
            violations_in_this_file += 1

            if verbosity > 1:
                print(f"    - {fn.long_name} [{fn.start_line}:{fn.end_line}]")
                print(f"      violations: {', '.join(violations)}")

        file_result = AnalysisResult(
            violation_count=violations_in_this_file,
            lines_of_code=analysed_file.nloc,
            file_count=1,
        )
        if verbosity > 0:
            print(f"    results for this file: {file_result}")
        result.overall.merge_with(file_result)
        result.files[analysed_file.filename] = file_result

    return result


def die(message, exit_code=-1) -> typing.NoReturn:
    print(message, file=sys.stderr)
    sys.exit(exit_code)


def get_repo(repos_dir: str, name: str, repo_info: lizard_mon.config.RepositoryInfo, at_date: str = None) -> git.Repo:
    repo_working_dir = os.path.join(repos_dir, name)
    if not os.path.isdir(repo_working_dir):
        print(f"  cloning '{name}' for first time from: {repo_info.url}")
        with ProgressPrinter() as progress:
            repo = git.Repo.clone_from(repo_info.url, repo_working_dir, branch=repo_info.branch, progress=progress)
    else:
        repo = git.Repo(repo_working_dir)
        if len(repo.remotes) < 1:
            raise LizardMonException(f"target {name} repo has no remotes to pull from")
        else:
            remote = repo.remotes[0]
            print(f"  fetching any changes from remote {remote.name}")
            with ProgressPrinter() as progress:
                remote.fetch(progress=progress)
        if at_date is None:
            if repo.head.is_detached or repo.active_branch.name != repo_info.branch:
                print(f"  checking out branch {repo_info.branch}")
                repo.git.checkout(repo_info.branch)
            else:
                print(f"  ensuring we're up to date on our current branch")
                remote.pull()
        else:
            commit_hash_at_date = repo.git.rev_list("-1", f'--before="{at_date}"', repo_info.branch)
            if not commit_hash_at_date:
                raise InvalidRepoDate(f"unable to checkout {name} at {at_date}")
            print(f"  checkout out at date {at_date} ({commit_hash_at_date})")
            repo.git.checkout(commit_hash_at_date)
    return repo


class InvalidRepoDate(LizardMonException):
    pass


class ProgressPrinter(git.RemoteProgress):

    def __init__(self):
        super().__init__()
        self.bar = typing.cast(tqdm.tqdm, None)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.bar is not None:
            self.bar.close()

    def update(self, op_code, cur_count, max_count=None, message=''):
        if self.bar is None or int(cur_count or 0) < self.bar.n:
            if self.bar is not None:
                self.bar.close()
            self.bar = tqdm.tqdm(
                total=int(max_count or 100),
                initial=int(cur_count or 0),
                leave=False,
            )
        count = int(cur_count or 0)
        delta = count - self.bar.n
        self.bar.set_description(message, False)
        self.bar.update(delta)


if __name__ == "__main__":
    try:
        main()
    except LizardMonException as lme:
        print(f"error: {lme}")
