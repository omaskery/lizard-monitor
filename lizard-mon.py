from lizard_mon.exceptions import *
import lizard_mon
import argparse
import typing
import lizard
import git
import sys
import os

CAT_CCN = lizard_mon.analysis.Category("cyclomatic complexity violations")
CAT_LINES = lizard_mon.analysis.Category("lines of code violations")
CAT_PARAMS = lizard_mon.analysis.Category("parameter count violations")


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

    analysis_stack = lizard_mon.analysis.Stack(
        CAT_CCN,
        CAT_LINES,
        CAT_PARAMS,
    )
    with analysis_stack.push("all repos"):
        for target in targets:
            print(f"{target.name} ({target.repo_info.url}):")
            root_repo_dir = os.path.join(base_path, "repos")
            repo = get_repo(root_repo_dir, target.name, target.repo_info)

            print(f"  running analysis on {repo.working_tree_dir}")
            with analysis_stack.push(target.name):
                analyse_repo(analysis_stack, repo, target.analysis_settings)


def analyse_repo(analysis_stack: 'lizardmon.analysis.Stack', repo: git.Repo,
                 analysis_settings: 'lizardmon.config.AnalysisSettings'):
    analysis = lizard.analyze(
        [repo.working_tree_dir],
        analysis_settings.exclusions,
        threads=4,
        lans=analysis_settings.languages,
        exts=lizard.get_extensions([])
    )
    analysis = typing.cast(typing.List[lizard.FileInformation], analysis)
    for result in analysis:
        shown_file = False
        for fn in result.function_list:
            ccn = fn.cyclomatic_complexity
            lines = fn.nloc
            parameters = len(fn.parameters)

            violations = []
            if ccn >= analysis_settings.limits.ccn:
                violations.append(f"ccn {ccn} exceeds limit {analysis_settings.limits.ccn}")
            if lines >= analysis_settings.limits.lines:
                violations.append(f"line count {lines} exceeds limit {analysis_settings.limits.lines}")
            if parameters >= analysis_settings.limits.parameters:
                violations.append(
                    f"parameter count {parameters} exceeds limit {analysis_settings.limits.parameters}"
                )

            if len(violations) == 0:
                continue

            if not shown_file:
                shown_file = True
                print(f"  file: {result.filename} (NLOC={result.nloc})")

            print(f"   - {fn.long_name} [{fn.start_line}:{fn.end_line}]")
            print(f"     violations: {', '.join(violations)}")


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


if __name__ == "__main__":
    try:
        main()
    except LizardMonException as lme:
        print(f"error: {lme}")
