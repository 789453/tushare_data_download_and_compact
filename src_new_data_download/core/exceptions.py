from __future__ import annotations


class DownloadError(RuntimeError):
    pass


class SpecValidationError(ValueError):
    pass


class TaskBuildError(RuntimeError):
    pass


class StateStoreError(RuntimeError):
    pass

