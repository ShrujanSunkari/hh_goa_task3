"""
pytest configuration for hh_goa_task3.

TensorFlow 2.15 emits C-level output to stderr during import which can
conflict with pytest's default file-based capture.  Switching to sys-level
capture (addopts below) prevents the 'I/O operation on closed file' crash
that otherwise occurs when pytest tears down its capture machinery while TF
is still flushing its startup logs.
"""

collect_ignore_glob = []


def pytest_configure(config):
    """Force sys-level capture so TF stderr doesn't crash pytest teardown."""
    # Only override if the user hasn't explicitly set a capture mode
    if not config.option.__dict__.get("capture"):
        config.option.capture = "sys"
