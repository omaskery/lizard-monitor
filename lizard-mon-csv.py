#!/usr/bin/env python3

from lizard_mon import results
import dateutil.parser
import datetime
import argparse
import typing
import json
import csv


CSV_HEADER_SEPARATOR = ":"
OVERALL_HEADER_PREFIX = "overall"
TARGET_HEADER_PREFIX = "tgt"
HEADER_TIMESTAMP = "timestamp"
HEADER_NLOC = "nloc"
HEADER_VIOLATIONS = "violations"
HEADER_VIOLATIONS_NORMALISED = "violations-normalised"
HEADER_FILES = "files"


def main():
    parser = argparse.ArgumentParser(
        description='utility for converting history.ndjson files from lizard-monitor to csv'
    )
    parser.add_argument(
        'history_path', help='path to the history.ndjson file to convert'
    )
    parser.add_argument(
        'output', help='path to write output csv to'
    )
    args = parser.parse_args()
    target_list = scan_for_targets(args.history_path)

    with open(args.output, 'w', newline='') as output_file:
        def header(*parts):
            return CSV_HEADER_SEPARATOR.join(parts)

        fieldnames = [header(HEADER_TIMESTAMP)]

        def add_columns_for(root):
            fieldnames.append(header(root, HEADER_NLOC))
            fieldnames.append(header(root, HEADER_VIOLATIONS))
            fieldnames.append(header(root, HEADER_VIOLATIONS_NORMALISED))
            fieldnames.append(header(root, HEADER_FILES))

        add_columns_for(OVERALL_HEADER_PREFIX)
        for target in target_list:
            add_columns_for(header(TARGET_HEADER_PREFIX, target))

        writer = csv.DictWriter(output_file, fieldnames)
        writer.writeheader()
        for timestamp, result_cache in iterate_history_file(args.history_path):
            new_row = typing.cast(typing.Dict[str, str], dict([
                (key, "") for key in fieldnames
            ]))

            def set_columns_for(root, result: results.AnalysisResult):
                new_row[header(root, HEADER_NLOC)] = str(result.lines_of_code)
                new_row[header(root, HEADER_VIOLATIONS)] = str(result.violation_count)
                new_row[header(root, HEADER_VIOLATIONS_NORMALISED)] = str(normalise_violations(result))
                new_row[header(root, HEADER_FILES)] = str(result.file_count)

            new_row[header(HEADER_TIMESTAMP)] = str(timestamp)
            set_columns_for(OVERALL_HEADER_PREFIX, result_cache.overall)
            for name, target in result_cache.targets.items():
                set_columns_for(header(TARGET_HEADER_PREFIX, name), target.overall)
            writer.writerow(new_row)


def normalise_violations(result: results.AnalysisResult):
    if result.violation_count <= 0 or result.lines_of_code <= 0:
        return 0.0
    return float(result.violation_count) / float(result.lines_of_code)


def scan_for_targets(history_path: str) -> typing.List[str]:
    targets = set()
    for _, result in iterate_history_file(history_path):
        for target in result.targets.keys():
            targets.add(target)
    return list(targets)


def iterate_history_file(history_path: str) -> typing.Iterable[typing.Tuple[datetime.datetime, results.ResultCache]]:
    def to_result(d: typing.Any):
        return d, results.ResultCache.from_shallow_yaml(d)

    for data, result in map(to_result, iterate_ndjson(history_path)):
        timestamp = dateutil.parser.parse(data["timestamp"])
        yield (timestamp, result)


def iterate_ndjson(path: str) -> typing.Iterable[typing.Any]:
    with open(path) as file:
        for line in file.readlines():
            yield json.loads(line)


if __name__ == "__main__":
    main()
