"""Validate the complete package set before obtaining a publishing credential."""
import os
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile


def read_identity(path):
    with ZipFile(path) as archive:
        specs = [name for name in archive.namelist() if name.endswith('.nuspec')]
        if len(specs) != 1:
            raise ValueError('Package must contain exactly one nuspec')
        root = ET.fromstring(archive.read(specs[0]))
    metadata = root.find('{*}metadata')
    if metadata is None:
        raise ValueError('Package metadata missing')
    return metadata.findtext('{*}id', '').lower(), metadata.findtext('{*}version')


def validate(directory, version, packages):
    expected = {line.strip().lower() for line in packages.splitlines() if line.strip()}
    if not expected or not version:
        raise ValueError('Expected package IDs and version are required')
    found = set()
    primary_paths = {}
    for path in Path(directory).glob('*.nupkg'):
        package_id, actual_version = read_identity(path)
        if actual_version != version or package_id not in expected:
            raise ValueError('Artifact package ID or version does not match the release')
        if package_id in found:
            raise ValueError('Duplicate package ID in artifact')
        found.add(package_id)
        primary_paths[path.with_suffix('.snupkg').name] = package_id
    if found != expected:
        raise ValueError('Artifact does not contain the complete expected package set')
    for symbols in Path(directory).glob('*.snupkg'):
        package_id, actual_version = read_identity(symbols)
        if actual_version != version or primary_paths.get(symbols.name) != package_id:
            raise ValueError('Symbol package must match its primary package ID, version and filename')


if __name__ == '__main__':
    validate(os.environ['PACKAGE_DIRECTORY'], os.environ['EXPECTED_VERSION'], os.environ['EXPECTED_PACKAGES'])
