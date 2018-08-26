import itertools
import typing


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
            "targets": dict([
                (name, target.to_yaml())
                for name, target in self.targets.items()
            ]),
        }

    def to_shallow_yaml(self):
        return {
            "overall": self.overall.to_yaml(),
            "targets": dict([
                (name, target.to_shallow_yaml())
                for name, target in self.targets.items()
            ])
        }

    @staticmethod
    def from_yaml(data):
        return ResultCache(
            overall=AnalysisResult.from_yaml(data["overall"]),
            targets=dict([
                (name, TargetResultCache.from_yaml(target))
                for name, target in data.get("targets", {}).items()
            ]),
        )

    @staticmethod
    def from_shallow_yaml(data):
        return ResultCache(
            overall=AnalysisResult.from_yaml(data["overall"]),
            targets=dict([
                (name, TargetResultCache.from_shallow_yaml(target))
                for name, target in data.get("targets", {}).items()
            ]),
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

    def to_shallow_yaml(self):
        return self.overall.to_yaml()

    @staticmethod
    def from_yaml(data):
        return TargetResultCache(
            overall=AnalysisResult.from_yaml(data["overall"]),
            files=dict([(name, AnalysisResult.from_yaml(file)) for name, file in data["files"].items()]),
        )

    @staticmethod
    def from_shallow_yaml(data):
        return AnalysisResult.from_yaml(data)
