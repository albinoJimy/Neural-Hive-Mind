#!/usr/bin/env python3
"""Extract coverage percentage from coverage.xml."""

import sys
import xml.etree.ElementTree as ET


def main():
    try:
        tree = ET.parse("tests/results/coverage/coverage.xml")
        root = tree.getroot()
        line_rate = float(root.attrib.get("line-rate", 0))
        coverage = line_rate * 100
        print(f"{coverage:.2f}")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        print("0.00", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
