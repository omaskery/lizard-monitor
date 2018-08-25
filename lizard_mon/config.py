from .exceptions import LizardMonException
import yaml
import os


def load_config(path):
    if not os.path.isfile(path):
        raise LizardMonException(f"no config file present at '{config_path}'")

    with open(path) as cfg_file:
        cfg = yaml.safe_load(cfg_file)

    if not isinstance(cfg, dict):
        raise LizardMonException("config file is not a block mapping at root level")

    try:
        targets = [
            TargetInfo.from_yaml(name, data)
            for name, data in cfg.items()
        ]
    except KeyError as ke:
        raise LizardMonException(f"target missing key '{ke.args}'")

    return targets


class TargetInfo:

    def __init__(self, name, repo_info, analysis_settings):
        self.name = name
        self.repo_info = repo_info
        self.analysis_settings = analysis_settings

    @staticmethod
    def from_yaml(target_name, data):
        return TargetInfo(
            target_name,
            RepositoryInfo.from_yaml(data["repo"]),
            AnalysisSettings.from_yaml(data["analysis"]),
        )


class RepositoryInfo:

    def __init__(self, url, branch):
        self.url = url
        self.branch = branch

    @staticmethod
    def from_yaml(data):
        return RepositoryInfo(
            data["url"],
            data.get("branch", "master"),
        )


class AnalysisSettings:

    def __init__(self, exclusions, languages, limits):
        self.exclusion_patterns = exclusions
        self.languages = languages
        self.limits = limits

    @staticmethod
    def from_yaml(data):
        return AnalysisSettings(
            data.get("exclusion_patterns", []),
            data["languages"],
            AnalysisLimits.from_yaml(data["limits"])
        )


class AnalysisLimits:

    def __init__(self, ccn, lines, parameters):
        self.ccn = ccn
        self.lines = lines
        self.parameters = parameters

    def exceeds(self, thresholds: 'AnalysisLimits'):
        return (
            self.ccn > thresholds.ccn or
            self.lines > thresholds.lines or
            self.parameters > thresholds.parameters
        )

    def merge_with(self, other: 'AnalysisLimits'):
        return AnalysisLimits(
            max(self.ccn, other.ccn),
            max(self.lines, other.lines),
            max(self.parameters, other.parameters),
        )

    @staticmethod
    def from_yaml(data):
        return AnalysisLimits(
            int(data["ccn"]),
            int(data["lines"]),
            int(data["parameters"]),
        )


def list_limit_violations(values, thresholds):
    violations = []
    if values.ccn >= thresholds.ccn:
        violations.append(f"ccn {values.ccn} exceeds limit {thresholds.ccn}")
    if values.lines >= thresholds.lines:
        violations.append(f"line count {values.lines} exceeds limit {thresholds.lines}")
    if values.parameters >= thresholds.parameters:
        violations.append(
            f"parameter count {values.parameters} exceeds limit {thresholds.parameters}"
        )
    return violations

