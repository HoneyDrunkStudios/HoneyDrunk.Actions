"""Validate the complete package set before obtaining a publishing credential."""
import os
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile


def validate(directory, version, packages):
    expected = {line.strip().lower() for line in packages.splitlines() if line.strip()}
    if not expected or not version:
        raise ValueError('Expected package IDs and version are required')
    found = set()
    for path in Path(directory).glob('*.nupkg'):
        with ZipFile(path) as archive:
            specs = [name for name in archive.namelist() if name.endswith('.nuspec')]
            if len(specs) != 1:
                raise ValueError('Package must contain exactly one nuspec')
            root = ET.fromstring(archive.read(specs[0]))
        metadata = root.find('{*}metadata')
        if metadata is None:
            raise ValueError('Package metadata missing')
        package_id = metadata.findtext('{*}id', '').lower()
        if metadata.findtext('{*}version') != version or package_id not in expected:
            raise ValueError('Artifact package ID or version does not match the release')
        if package_id in found:
            raise ValueError('Duplicate package ID in artifact')
        found.add(package_id)
    if found != expected:
        raise ValueError('Artifact does not contain the complete expected package set')


if __name__ == '__main__':
    validate(os.environ['PACKAGE_DIRECTORY'], os.environ['EXPECTED_VERSION'], os.environ['EXPECTED_PACKAGES'])
