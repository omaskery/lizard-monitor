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
            data["branch"],
        )


class AnalysisSettings:

    def __init__(self, exclusions, languages, limits):
        self.exclusions = exclusions
        self.languages = languages
        self.limits = limits

    @staticmethod
    def from_yaml(data):
        return AnalysisSettings(
            data["exclusions"],
            data["languages"],
            AnalysisLimits.from_yaml(data["limits"])
        )


class AnalysisLimits:

    def __init__(self, ccn, lines, parameters):
        self.ccn = ccn
        self.lines = lines
        self.parameters = parameters

    @staticmethod
    def from_yaml(data):
        return AnalysisLimits(
            int(data["ccn"]),
            int(data["lines"]),
            int(data["parameters"]),
        )
