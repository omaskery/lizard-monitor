from lizard_mon.exceptions import *
import lizard_mon
import itertools
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
        '--path', default='.', help='directory to treat as current working directory'
    )
    args = parser.parse_args()
    base_path = args.path

    config_path = os.path.join(base_path, "lizard-mon.yml")
    targets = lizard_mon.config.load_config(config_path)

    cache_path = os.path.join(base_path, "previous-results.yml")
    if os.path.isfile(cache_path):
        with open(cache_path) as cache_file:
            cache = yaml.safe_load(cache_file)
            previous_results = ResultCache.from_yaml(cache)
    else:
        previous_results = ResultCache(AnalysisResult(0, 0), {})

    overall_analysis_results = ResultCache(AnalysisResult(0, 0), {})
    for target in targets:
        print(f"{target.name} ({target.repo_info.url}):")
        root_repo_dir = os.path.join(base_path, "repos")
        repo = get_repo(root_repo_dir, target.name, target.repo_info)

        print(f"  running analysis on {repo.working_tree_dir}")
        analysis_results = analyse_repo(repo, target.analysis_settings)
        overall_analysis_results.overall.merge_with(analysis_results.overall)
        overall_analysis_results.targets[target.name] = analysis_results
        print(f"  results for this repo: {overall_analysis_results.overall}")
    print(f"overall results: {overall_analysis_results.overall}")

    with open(cache_path, 'w') as cache_file:
        yaml.safe_dump(overall_analysis_results.to_yaml(), cache_file, default_flow_style=False)

    differences_path = os.path.join(base_path, "differences.yml")
    differences = overall_analysis_results.difference(previous_results)
    with open(differences_path, 'w') as differences_file:
        yaml.safe_dump(differences.to_yaml(), differences_file, default_flow_style=False)

    history_path = os.path.join(base_path, "history.json")
    with open(history_path, 'a') as history_file:
        data = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "overall": overall_analysis_results.overall.to_yaml(),
            "targets": dict([
                (name, target.overall.to_yaml())
                for name, target in overall_analysis_results.targets.items()
            ]),
        }
        history_file.write(f"{json.dumps(data)}\n")


def analyse_repo(repo: git.Repo, analysis_settings: 'lizard_mon.config.AnalysisSettings') -> 'TargetResultCache':
    result = TargetResultCache(AnalysisResult(0, 0), {})

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

            print(f"    - {fn.long_name} [{fn.start_line}:{fn.end_line}]")
            print(f"      violations: {', '.join(violations)}")

        file_result = AnalysisResult(violations_in_this_file, analysed_file.nloc)
        print(f"    results for this file: {file_result}")
        result.overall.merge_with(file_result)
        result.files[analysed_file.filename] = file_result

    return result


def die(message, exit_code=-1) -> typing.NoReturn:
    print(message, file=sys.stderr)
    sys.exit(exit_code)


def get_repo(repos_dir, name, repo_info):
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
            print(f"  pulling any changes from remote {remote.name}")
            with ProgressPrinter() as progress:
                remote.pull(progress=progress)
        if repo.active_branch.name != repo_info.branch:
            print(f"  checking out branch {repo_info.branch}")
            repo.git.checkout(repo_info.branch)
    return repo


class AnalysisResult:

    def __init__(self, violation_count: int, lines_of_code: int):
        self.violation_count = violation_count
        self.lines_of_code = lines_of_code

    def merge_with(self, other: 'AnalysisResult'):
        self.violation_count += other.violation_count
        self.lines_of_code += other.lines_of_code

    def difference(self, other: 'AnalysisResult') -> 'AnalysisResult':
        return AnalysisResult(
            violation_count=self.violation_count-other.violation_count,
            lines_of_code=self.lines_of_code-other.lines_of_code,
        )

    def __str__(self):
        return f"[violations: {self.violation_count}, NLOC={self.lines_of_code}]"

    def to_yaml(self):
        return {
            "violation_count": self.violation_count,
            "lines_of_code": self.lines_of_code,
        }

    @staticmethod
    def from_yaml(data) -> 'AnalysisResult':
        return AnalysisResult(
            data["violation_count"],
            data["lines_of_code"],
        )


class ResultCache:

    def __init__(self, overall: AnalysisResult, targets: typing.Dict[str, 'TargetResultCache']):
        self.overall = overall
        self.targets = targets

    def difference(self, other: 'ResultCache') -> 'ResultCache':
        targets = {}
        for key in set(itertools.chain(self.targets.keys(), other.targets.keys())):
            target_a = self.targets.get(key, TargetResultCache(AnalysisResult(0, 0), {}))
            target_b = other.targets.get(key, TargetResultCache(AnalysisResult(0, 0), {}))
            targets[key] = target_a.difference(target_b)
        return ResultCache(
            overall=self.overall.difference(other.overall),
            targets=targets,
        )

    def to_yaml(self):
        return {
            "overall": self.overall.to_yaml(),
            "targets": dict([(name, target.to_yaml()) for name, target in self.targets.items()]),
        }

    @staticmethod
    def from_yaml(data):
        return ResultCache(
            overall=AnalysisResult.from_yaml(data["overall"]),
            targets=dict([(name, TargetResultCache.from_yaml(target)) for name, target in data["targets"].items()]),
        )


class TargetResultCache:

    def __init__(self, overall: AnalysisResult, files: typing.Dict[str, 'AnalysisResult']):
        self.overall = overall
        self.files = files

    def difference(self, other: 'TargetResultCache') -> 'TargetResultCache':
        files = {}
        for key in set(itertools.chain(self.files.keys(), other.files.keys())):
            file_a = self.files.get(key, AnalysisResult(0, 0))
            file_b = other.files.get(key, AnalysisResult(0, 0))
            files[key] = file_a.difference(file_b)
        return TargetResultCache(
            overall=self.overall.difference(other.overall),
            files=files,
        )

    def to_yaml(self):
        return {
            "overall": self.overall.to_yaml(),
            "files": dict([(name, file.to_yaml()) for name, file in self.files.items()]),
        }

    @staticmethod
    def from_yaml(data):
        return TargetResultCache(
            overall=AnalysisResult.from_yaml(data["overall"]),
            files=dict([(name, AnalysisResult.from_yaml(file)) for name, file in data["files"].items()]),
        )


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

    def line_dropped(self, line):
        # print("dropped:", line)
        pass


if __name__ == "__main__":
    try:
        main()
    except LizardMonException as lme:
        print(f"error: {lme}")
