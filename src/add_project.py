import os
import json
import time
import tarfile
import shutil

import supervisely_lib as sly
from supervisely_lib.io.fs import ensure_base_path, silent_remove, get_file_name, remove_dir, get_subdirs

def main():
    team_id = os.environ['modal.state.teamId']
    workspace_id = os.environ['modal.state.workspaceId']
    project_name = os.environ['modal.state.projectName']
    ecosystem_item_git_url = os.environ['modal.state.slyEcosystemItemGitUrl']
    ecosystem_item_version = os.environ.get('modal.state.slyEcosystemItemVersion', "master")
    ecosystem_item_id = os.environ['modal.state.slyEcosystemItemId']

    sly.logger.info("Script arguments", extra={"teamId: ": team_id,
                                               "workspaceId: ": workspace_id,
                                               "projectName: ": project_name,
                                               "slyEcosystemItemId": ecosystem_item_id,
                                               "slyEcosystemItemGitUrl: ": ecosystem_item_git_url,
                                               "slyEcosystemItemVersion: ": ecosystem_item_version})

    api = sly.Api.from_env()

    dest_dir = "/sly_task_data/repo"
    sly.fs.mkdir(dest_dir)
    sly.fs.clean_dir(dest_dir)

    tar_path = os.path.join(dest_dir, 'repo.tar.gz')
    api.app.download_git_archive(ecosystem_item_id, ecosystem_item_version, tar_path, log_progress=True)
    with tarfile.open(tar_path) as archive:
        archive.extractall(dest_dir)
    subdirs = get_subdirs(dest_dir)
    if len(subdirs) != 1:
        raise RuntimeError("Repo is downloaded and extracted, but resulting directory not found")
    extracted_path = os.path.join(dest_dir, subdirs[0])

    for filename in os.listdir(extracted_path):
        shutil.move(os.path.join(extracted_path, filename), os.path.join(dest_dir, filename))
    remove_dir(extracted_path)
    silent_remove(tar_path)

    #sly.git.download(ecosystem_item_git_url, dest_dir, github_token, ecosystem_item_version, log_progress=True)

    project_name = sly.fs.get_file_name(ecosystem_item_git_url)

    with open(os.path.join(dest_dir, "project", "meta.json")) as json_file:
        meta_json = json.load(json_file)

    project_type = sly.ProjectMeta.from_json(meta_json).project_type
    if project_type == str(sly.ProjectType.IMAGES):
        project_id, res_project_name = sly.upload_project(dest_dir, api, workspace_id, project_name, log_progress=True)
    elif project_type == str(sly.ProjectType.VIDEOS):
        project_id, res_project_name = sly.upload_video_project(dest_dir, api, workspace_id, project_name, log_progress=True)
    elif project_type == str(sly.ProjectType.VOLUMES):
        raise NotImplementedError("DICOM project")
    else:
        raise NotImplementedError("Unknown type: {}".format(project_type))

    sly.logger.info("Project info: id={!r}, name={!r}".format(project_id, res_project_name))

    # to show created project in tasks list (output column)
    sly.logger.info('PROJECT_CREATED', extra={'event_type': sly.EventType.PROJECT_CREATED, 'project_id': project_id})

    #@TODO: set task output

if __name__ == "__main__":
    sly.main_wrapper("main", main)