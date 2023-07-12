import os
import json
import tarfile
import shutil

import supervisely as sly
from supervisely.io.fs import silent_remove, remove_dir, get_subdirs
from supervisely.project.pointcloud_project import upload_pointcloud_project
from supervisely.project.pointcloud_episode_project import upload_pointcloud_episode_project
from supervisely.app.v1.app_service import AppService

my_app = AppService()


@my_app.callback("do")
@sly.timeit
def do(**kwargs):
    task_id = os.environ["TASK_ID"]
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
    api.app.download_git_archive(ecosystem_item_id, None, ecosystem_item_version, tar_path, log_progress=True)
    with tarfile.open(tar_path) as archive:
        archive.extractall(dest_dir)

    subdirs = get_subdirs(dest_dir)
    if len(subdirs) != 1:
        raise RuntimeError("Repo is downloaded and extracted, but resulting directory not found")
    extracted_path = os.path.join(dest_dir, subdirs[0])

    github_dir = os.path.join(extracted_path, ".github")
    sly.logger.debug(f"Trying to remove {github_dir}...")
    list_dir = os.listdir(extracted_path)
    sly.logger.debug(f"list_dir in extracted_path: {list_dir}")

    for filename in os.listdir(extracted_path):
        shutil.move(os.path.join(extracted_path, filename), os.path.join(dest_dir, filename))
    remove_dir(extracted_path)
    silent_remove(tar_path)

    if project_name == "":
        project_name = None
        with open(os.path.join(dest_dir, "config.json")) as json_file:
            config_json = json.load(json_file)
            project_name = config_json["name"]

        if project_name is None:
            raise KeyError("Can not read name from {!r}".format("config.json"))
            # sly.logger.warn("Can not read name from {!r}".format("config.json"))
            # project_name = sly.fs.get_file_name(ecosystem_item_git_url)

    sly.logger.info("Result project name = {!r}".format(project_name))
    with open(os.path.join(dest_dir, "project", "meta.json")) as json_file:
        meta_json = json.load(json_file)

    project_type = sly.ProjectMeta.from_json(meta_json).project_type
    if project_type == str(sly.ProjectType.IMAGES):
        project_id, res_project_name = sly.upload_project(dest_dir, api, workspace_id, project_name, log_progress=True)
    elif project_type == str(sly.ProjectType.VIDEOS):
        project_id, res_project_name = sly.upload_video_project(dest_dir, api, workspace_id, project_name,
                                                                log_progress=True)
    elif project_type == str(sly.ProjectType.VOLUMES):
        project_id, res_project_name = sly.upload_volume_project(dest_dir, api, workspace_id, project_name,
                                                                log_progress=True)
    elif project_type == str(sly.ProjectType.POINT_CLOUDS):
        dest_dir = os.path.join(dest_dir, "project")
        project_id, res_project_name = upload_pointcloud_project(dest_dir, api, workspace_id, project_name, 
                                                                         log_progress=True)
    elif project_type == str(sly.ProjectType.POINT_CLOUD_EPISODES):
        dest_dir = os.path.join(dest_dir, "project")
        project_id, res_project_name = upload_pointcloud_episode_project(dest_dir, api, workspace_id, project_name, 
                                                                         log_progress=True)
    else:
        raise NotImplementedError("Unknown project type: {}".format(project_type))

    sly.logger.info("Project info: id={!r}, name={!r}".format(project_id, res_project_name))

    # to show created project in tasks list (output column)
    sly.logger.info('PROJECT_CREATED', extra={'event_type': sly.EventType.PROJECT_CREATED, 'project_id': project_id})
    api.task.set_output_project(task_id, project_id, res_project_name)
    my_app.stop()
    

def main():
    initial_events = [
        {
            "state": None,
            "context": None,
            "command": "do",
        }
    ]

    my_app.run(initial_events=initial_events)


if __name__ == "__main__":
    sly.main_wrapper("main", main)
