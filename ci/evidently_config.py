"""Report proxy changes for human investigation, without a quality verdict."""
from evidently.cli.report import ReportConfig
from evidently.presets import DataDriftPreset

conf = ReportConfig(metrics=[DataDriftPreset()], include_tests=False)
