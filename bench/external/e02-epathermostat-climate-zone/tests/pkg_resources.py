"""Stand-in for setuptools' pkg_resources.resource_stream, which newer Pythons no longer ship by default."""
from importlib.resources import files


def resource_stream(package, name):
    return files(package).joinpath(name).open("rb")
