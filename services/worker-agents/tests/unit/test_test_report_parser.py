"""Unit tests for test report parsers."""
import pytest
from io import StringIO

from src.utils.test_report_parser import (
    JUnitXMLParser,
    CoberturaXMLParser,
    LCOVParser,
    TestCase,
    TestResults,
    CoverageResults,
    parse_test_report,
    parse_coverage_report,
    detect_report_format,
)


class TestJUnitXMLParser:
    """Tests for JUnitXMLParser."""

    def test_parse_simple_testsuite(self):
        """Test parsing a simple JUnit XML with one testsuite."""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="TestSuite1" tests="3" failures="1" errors="0" skipped="0" time="1.5">
            <testcase name="test_pass1" classname="tests.test_module" time="0.5"/>
            <testcase name="test_pass2" classname="tests.test_module" time="0.3"/>
            <testcase name="test_fail1" classname="tests.test_module" time="0.7">
                <failure message="AssertionError">Expected 1 but got 2</failure>
            </testcase>
        </testsuite>
        '''
        parser = JUnitXMLParser()
        result = parser.parse(xml_content)

        assert isinstance(result, TestResults)
        assert result.total == 3
        assert result.passed == 2
        assert result.failed == 1
        assert result.skipped == 0
        assert result.errors == 0
        assert len(result.test_cases) == 3

    def test_parse_testsuites(self):
        """Test parsing JUnit XML with multiple testsuites."""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <testsuites name="AllTests" tests="5" failures="1" errors="1" skipped="1" time="3.0">
            <testsuite name="Suite1" tests="3" failures="1" errors="0" skipped="0" time="1.5">
                <testcase name="test1" classname="Suite1" time="0.5"/>
                <testcase name="test2" classname="Suite1" time="0.5"/>
                <testcase name="test3" classname="Suite1" time="0.5">
                    <failure>Failed assertion</failure>
                </testcase>
            </testsuite>
            <testsuite name="Suite2" tests="2" failures="0" errors="1" skipped="1" time="1.5">
                <testcase name="test4" classname="Suite2" time="0.5">
                    <error>RuntimeError</error>
                </testcase>
                <testcase name="test5" classname="Suite2" time="0.5">
                    <skipped>Not implemented</skipped>
                </testcase>
            </testsuite>
        </testsuites>
        '''
        parser = JUnitXMLParser()
        result = parser.parse(xml_content)

        assert result.total == 5
        assert result.passed == 2
        assert result.failed == 1
        assert result.errors == 1
        assert result.skipped == 1

    def test_parse_empty_testsuite(self):
        """Test parsing empty testsuite."""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="EmptySuite" tests="0" failures="0" errors="0" skipped="0" time="0.0">
        </testsuite>
        '''
        parser = JUnitXMLParser()
        result = parser.parse(xml_content)

        assert result.total == 0
        assert result.passed == 0
        assert len(result.test_cases) == 0

    def test_parse_with_duration(self):
        """Test that duration is correctly parsed."""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="Suite" tests="1" time="2.5">
            <testcase name="test1" classname="Suite" time="2.5"/>
        </testsuite>
        '''
        parser = JUnitXMLParser()
        result = parser.parse(xml_content)

        assert result.duration == pytest.approx(2.5)
        assert result.test_cases[0].duration == pytest.approx(2.5)

    def test_parse_invalid_xml(self):
        """Test parsing invalid XML."""
        parser = JUnitXMLParser()
        result = parser.parse('not valid xml')

        assert result.total == 0
        assert result.passed == 0

    def test_test_case_status(self):
        """Test individual test case status detection."""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="Suite" tests="4">
            <testcase name="passed" classname="Suite" time="0.1"/>
            <testcase name="failed" classname="Suite" time="0.1">
                <failure>Failed</failure>
            </testcase>
            <testcase name="error" classname="Suite" time="0.1">
                <error>Error</error>
            </testcase>
            <testcase name="skipped" classname="Suite" time="0.1">
                <skipped/>
            </testcase>
        </testsuite>
        '''
        parser = JUnitXMLParser()
        result = parser.parse(xml_content)

        statuses = {tc.name: tc.status for tc in result.test_cases}
        assert statuses['passed'] == 'passed'
        assert statuses['failed'] == 'failed'
        assert statuses['error'] == 'error'
        assert statuses['skipped'] == 'skipped'


class TestCoberturaXMLParser:
    """Tests for CoberturaXMLParser."""

    def test_parse_simple_coverage(self):
        """Test parsing simple Cobertura XML."""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <coverage line-rate="0.85" branch-rate="0.75" lines-covered="85" lines-valid="100" branches-covered="15" branches-valid="20" complexity="10">
            <packages>
                <package name="mypackage" line-rate="0.85" branch-rate="0.75" complexity="10">
                    <classes>
                        <class name="MyClass" filename="myclass.py" line-rate="0.85" branch-rate="0.75">
                            <lines>
                                <line number="1" hits="1"/>
                                <line number="2" hits="1"/>
                                <line number="3" hits="0"/>
                            </lines>
                        </class>
                    </classes>
                </package>
            </packages>
        </coverage>
        '''
        parser = CoberturaXMLParser()
        result = parser.parse(xml_content)

        assert isinstance(result, CoverageResults)
        assert result.line_rate == pytest.approx(0.85)
        assert result.branch_rate == pytest.approx(0.75)
        assert result.lines_covered == 85
        assert result.lines_total == 100

    def test_parse_without_branch_coverage(self):
        """Test parsing Cobertura XML without branch coverage."""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <coverage line-rate="0.90" lines-covered="90" lines-valid="100">
            <packages/>
        </coverage>
        '''
        parser = CoberturaXMLParser()
        result = parser.parse(xml_content)

        assert result.line_rate == pytest.approx(0.90)
        assert result.branch_rate == 0.0

    def test_parse_with_files(self):
        """Test parsing coverage with file details."""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <coverage line-rate="0.80" lines-covered="80" lines-valid="100">
            <packages>
                <package name="pkg">
                    <classes>
                        <class name="Class1" filename="file1.py" line-rate="0.90"/>
                        <class name="Class2" filename="file2.py" line-rate="0.70"/>
                    </classes>
                </package>
            </packages>
        </coverage>
        '''
        parser = CoberturaXMLParser()
        result = parser.parse(xml_content)

        assert len(result.files) == 2
        assert 'file1.py' in result.files
        assert result.files['file1.py'] == pytest.approx(0.90)

    def test_parse_invalid_xml(self):
        """Test parsing invalid XML."""
        parser = CoberturaXMLParser()
        result = parser.parse('invalid xml')

        assert result.line_rate == 0.0
        assert result.lines_covered == 0

    def test_percentage_property(self):
        """Test coverage percentage property."""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <coverage line-rate="0.856" lines-covered="856" lines-valid="1000"/>
        '''
        parser = CoberturaXMLParser()
        result = parser.parse(xml_content)

        assert result.percentage == pytest.approx(85.6)


class TestLCOVParser:
    """Tests for LCOVParser."""

    def test_parse_simple_lcov(self):
        """Test parsing simple LCOV file."""
        lcov_content = '''TN:
SF:/path/to/file1.py
DA:1,1
DA:2,1
DA:3,0
DA:4,1
LF:4
LH:3
end_of_record
'''
        parser = LCOVParser()
        result = parser.parse(lcov_content)

        assert isinstance(result, CoverageResults)
        assert result.lines_total == 4
        assert result.lines_covered == 3
        assert result.line_rate == pytest.approx(0.75)

    def test_parse_multiple_files(self):
        """Test parsing LCOV with multiple files."""
        lcov_content = '''TN:TestName
SF:/path/to/file1.py
DA:1,1
DA:2,1
LF:2
LH:2
end_of_record
SF:/path/to/file2.py
DA:1,1
DA:2,0
DA:3,0
LF:3
LH:1
end_of_record
'''
        parser = LCOVParser()
        result = parser.parse(lcov_content)

        assert result.lines_total == 5
        assert result.lines_covered == 3
        assert len(result.files) == 2
        assert result.files['/path/to/file1.py'] == pytest.approx(1.0)
        assert result.files['/path/to/file2.py'] == pytest.approx(1/3)

    def test_parse_with_branch_coverage(self):
        """Test parsing LCOV with branch coverage."""
        lcov_content = '''SF:/path/to/file.py
DA:1,1
DA:2,1
BRDA:2,0,0,1
BRDA:2,0,1,0
BRF:2
BRH:1
LF:2
LH:2
end_of_record
'''
        parser = LCOVParser()
        result = parser.parse(lcov_content)

        assert result.branches_total == 2
        assert result.branches_covered == 1
        assert result.branch_rate == pytest.approx(0.5)

    def test_parse_empty_content(self):
        """Test parsing empty LCOV content."""
        parser = LCOVParser()
        result = parser.parse('')

        assert result.lines_total == 0
        assert result.lines_covered == 0
        assert result.line_rate == 0.0

    def test_parse_no_coverage_data(self):
        """Test parsing LCOV without DA lines."""
        lcov_content = '''TN:TestName
SF:/path/to/file.py
end_of_record
'''
        parser = LCOVParser()
        result = parser.parse(lcov_content)

        assert result.lines_total == 0


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_detect_report_format_junit(self):
        """Test detecting JUnit XML format."""
        junit_xml = '<testsuite name="Test"><testcase name="test1"/></testsuite>'
        assert detect_report_format(junit_xml) == 'junit'

    def test_detect_report_format_testsuites(self):
        """Test detecting JUnit XML with testsuites."""
        junit_xml = '<testsuites><testsuite name="Test"/></testsuites>'
        assert detect_report_format(junit_xml) == 'junit'

    def test_detect_report_format_cobertura(self):
        """Test detecting Cobertura XML format."""
        cobertura_xml = '<coverage line-rate="0.5"><packages/></coverage>'
        assert detect_report_format(cobertura_xml) == 'cobertura'

    def test_detect_report_format_lcov(self):
        """Test detecting LCOV format."""
        lcov_content = 'SF:/path/to/file.py\nDA:1,1\nend_of_record'
        assert detect_report_format(lcov_content) == 'lcov'

    def test_detect_report_format_unknown(self):
        """Test unknown format detection."""
        assert detect_report_format('random content') == 'unknown'

    def test_parse_test_report(self):
        """Test parse_test_report helper function."""
        junit_xml = '''<?xml version="1.0"?>
        <testsuite tests="2" failures="0">
            <testcase name="test1" classname="Suite"/>
            <testcase name="test2" classname="Suite"/>
        </testsuite>
        '''
        result = parse_test_report(junit_xml, 'junit')

        assert isinstance(result, TestResults)
        assert result.total == 2
        assert result.passed == 2

    def test_parse_coverage_report_cobertura(self):
        """Test parse_coverage_report with Cobertura format."""
        cobertura_xml = '''<?xml version="1.0"?>
        <coverage line-rate="0.80" lines-covered="80" lines-valid="100"/>
        '''
        result = parse_coverage_report(cobertura_xml, 'cobertura')

        assert isinstance(result, CoverageResults)
        assert result.line_rate == pytest.approx(0.80)

    def test_parse_coverage_report_lcov(self):
        """Test parse_coverage_report with LCOV format."""
        lcov_content = 'SF:file.py\nDA:1,1\nDA:2,0\nLF:2\nLH:1\nend_of_record'
        result = parse_coverage_report(lcov_content, 'lcov')

        assert isinstance(result, CoverageResults)
        assert result.line_rate == pytest.approx(0.5)


class TestDataclasses:
    """Tests for dataclasses."""

    def test_test_case_creation(self):
        """Test TestCase dataclass creation."""
        tc = TestCase(
            name='test_example',
            classname='tests.test_module',
            status='passed',
            duration=1.5,
            message=None,
            stdout=None,
            stderr=None
        )

        assert tc.name == 'test_example'
        assert tc.status == 'passed'
        assert tc.duration == 1.5

    def test_test_results_creation(self):
        """Test TestResults dataclass creation."""
        results = TestResults(
            total=10,
            passed=8,
            failed=1,
            skipped=1,
            errors=0,
            duration=5.0,
            test_cases=[]
        )

        assert results.total == 10
        assert results.passed == 8

    def test_coverage_results_creation(self):
        """Test CoverageResults dataclass creation."""
        coverage = CoverageResults(
            line_rate=0.85,
            branch_rate=0.75,
            lines_covered=850,
            lines_total=1000,
            branches_covered=75,
            branches_total=100,
            files={'file.py': 0.90}
        )

        assert coverage.line_rate == 0.85
        assert coverage.percentage == 85.0
        assert coverage.files['file.py'] == 0.90
