import supervisely as sly
import os


def check_compatibility(func):
    def wrapper(self, *args, **kwargs):
        if self.is_compatible is None:
            self.is_compatible = self.check_instance_ver_compatibility()
        if not self.is_compatible:
            return
        return func(self, *args, **kwargs)

    return wrapper


class Workflow:
    def __init__(self, api: sly.Api, min_instance_version: str = None):
        self.is_compatible = None
        self.api = api
        self._min_instance_version = (
            "6.9.31" if min_instance_version is None else min_instance_version
        )
    
    def check_instance_ver_compatibility(self):
        if self.api.instance_version < self._min_instance_version:
            sly.logger.info(
                f"Supervisely instance version does not support workflow and versioning features. To use them, please update your instance minimum to version {self._min_instance_version}."
            )
            return False
        return True
    
    @check_compatibility
    def add_input(self):
        raise NotImplementedError("Method is not implemented yet.")

    @check_compatibility
    def add_output(self, project_id: int):
        self.api.app.workflow.add_output_project(project_id)

