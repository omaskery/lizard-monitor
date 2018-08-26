from lizard_mon import results
import dateutil.parser
import datetime
import argparse
import typing
import json
import csv


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
        fieldnames = ["timestamp"]
        for target in target_list:
            fieldnames.append(target + "-nloc")
            fieldnames.append(target + "-violations")
        writer = csv.DictWriter(output_file, fieldnames)
        writer.writeheader()
        for timestamp, result in iterate_history_file(args.history_path):
            new_row = dict([
                (key, "") for key in fieldnames
            ])
            new_row["timestamp"] = timestamp
            for name, target in result.targets.items():
                new_row[name + "-nloc"] = target.lines_of_code
                new_row[name + "-violations"] = target.violation_count
            writer.writerow(new_row)


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
