"""Lists the license of every installed Python package and fails on GPL or AGPL.

LGPL is allowed (see THIRD_PARTY.md). Run with: make license-check
"""
import importlib.metadata as metadata
import re
import sys

LESSER = re.compile(r"LGPL|(Library or )?Lesser General Public License|Library General Public License")
STRONG = re.compile(r"GPL|General Public License")


def license_of(dist) -> str:
    meta = dist.metadata
    if meta.get("License-Expression"):
        return meta["License-Expression"]
    classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License")]
    return "; ".join(classifiers) or (meta.get("License") or "unknown").strip().splitlines()[0][:80]


def main():
    bad = []
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name, license = dist.metadata["Name"], license_of(dist)
        print(f"{name:32} {license}")
        if STRONG.search(LESSER.sub("", license)):
            bad.append(name)
    if bad:
        sys.exit(f"\nNot allowed (GPL/AGPL): {', '.join(bad)}")
    print("\nNo GPL or AGPL packages.")


main()
