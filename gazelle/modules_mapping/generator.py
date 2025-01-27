import argparse
import json
import pathlib
import re
import sys
import zipfile


# Generator is the modules_mapping.json file generator.
class Generator:
    stderr = None
    output_file = None
    excluded_patterns = None
    mapping = {}

    def __init__(self, stderr, output_file, excluded_patterns):
        self.stderr = stderr
        self.output_file = output_file
        self.excluded_patterns = [re.compile(pattern) for pattern in excluded_patterns]

    # dig_wheel analyses the wheel .whl file determining the modules it provides
    # by looking at the directory structure.
    def dig_wheel(self, whl):
        with zipfile.ZipFile(whl, "r") as zip_file:
            for path in zip_file.namelist():
                if is_metadata(path):
                    if data_has_purelib_or_platlib(path):
                        self.module_for_path(path, whl)
                    else:
                        continue
                else:
                    self.module_for_path(path, whl)

    def module_for_path(self, path, whl):
        ext = pathlib.Path(path).suffix
        if ext == ".py" or ext == ".so":
            if "purelib" in path or "platlib" in path:
                root = "/".join(path.split("/")[2:])
            else:
                root = path

            wheel_name = get_wheel_name(whl)

            if root.endswith("/__init__.py"):
                # Note the '/' here means that the __init__.py is not in the
                # root of the wheel, therefore we can index the directory
                # where this file is as an importable package.
                module = root[: -len("/__init__.py")].replace("/", ".")
                if not self.is_excluded(module):
                    self.mapping[module] = wheel_name

            # Always index the module file.
            if ext == ".so":
                # Also remove extra metadata that is embeded as part of
                # the file name as an extra extension.
                ext = "".join(pathlib.Path(root).suffixes)
            module = root[: -len(ext)].replace("/", ".")
            if not self.is_excluded(module):
                self.mapping[module] = wheel_name

    def is_excluded(self, module):
        for pattern in self.excluded_patterns:
            if pattern.search(module):
                return True
        return False

    # run is the entrypoint for the generator.
    def run(self, wheels):
        for whl in wheels:
            try:
                self.dig_wheel(whl)
            except AssertionError as error:
                print(error, file=self.stderr)
                return 1
        mapping_json = json.dumps(self.mapping)
        with open(self.output_file, "w") as f:
            f.write(mapping_json)
        return 0


def get_wheel_name(path):
    pp = pathlib.PurePath(path)
    if pp.suffix != ".whl":
        raise RuntimeError(
            "{} is not a valid wheel file name: the wheel doesn't follow ".format(
                pp.name
            )
            + "https://www.python.org/dev/peps/pep-0427/#file-name-convention"
        )
    return pp.name[: pp.name.find("-")]


# is_metadata checks if the path is in a metadata directory.
# Ref: https://www.python.org/dev/peps/pep-0427/#file-contents.
def is_metadata(path):
    top_level = path.split("/")[0].lower()
    return top_level.endswith(".dist-info") or top_level.endswith(".data")


# The .data is allowed to contain a full purelib or platlib directory
# These get unpacked into site-packages, so require indexing too.
# This is the same if "Root-Is-Purelib: true" is set and the files are at the root.
# Ref: https://peps.python.org/pep-0427/#what-s-the-deal-with-purelib-vs-platlib
def data_has_purelib_or_platlib(path):
    maybe_lib = path.split("/")[1].lower()
    return is_metadata(path) and (maybe_lib == "purelib" or maybe_lib == "platlib")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="generator",
        description="Generates the modules mapping used by the Gazelle manifest.",
    )
    parser.add_argument("--output_file", type=str)
    parser.add_argument("--exclude_patterns", nargs="+", default=[])
    parser.add_argument("--wheels", nargs="+", default=[])
    args = parser.parse_args()
    generator = Generator(sys.stderr, args.output_file, args.exclude_patterns)
    exit(generator.run(args.wheels))
