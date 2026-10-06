import os
import json
import tarfile
import shutil

import supervisely as sly
from supervisely.io.fs import silent_remove, remove_dir, get_subdirs
from supervisely.project.pointcloud_project import upload_pointcloud_project
from supervisely.project.pointcloud_episode_project import upload_pointcloud_episode_project
from supervisely.app.v1.app_service import AppService
from supervisely.project.project_settings import LabelingInterface
from src.functions import (
    upload_overlay_project,
    upload_audio_references,
    get_usage_limit_error,
    remove_empty_partial_projects,
    report_usage_limit,
)
from workflow import Workflow


if sly.is_development():
    from dotenv import load_dotenv

    load_dotenv("local.env")
    load_dotenv(os.path.expanduser("~/supervisely.env"))


my_app = AppService()


@my_app.callback("do")
@sly.timeit
def do(**kwargs):
    task_id = sly.env.task_id()
    team_id = sly.env.team_id()
    workspace_id = sly.env.workspace_id()
    project_name = os.environ.get("modal.state.projectName", "")
    project_name = project_name.replace("\\", "").replace("|", "").replace("/", "")

    ecosystem_item_git_url = os.environ["modal.state.slyEcosystemItemGitUrl"]
    ecosystem_item_version = os.environ.get("modal.state.slyEcosystemItemVersion", "master")
    ecosystem_item_id = os.environ["modal.state.slyEcosystemItemId"]

    sly.logger.info(
        "Script arguments",
        extra={
            "teamId: ": team_id,
            "workspaceId: ": workspace_id,
            "projectName: ": project_name,
            "slyEcosystemItemId": ecosystem_item_id,
            "slyEcosystemItemGitUrl: ": ecosystem_item_git_url,
            "slyEcosystemItemVersion: ": ecosystem_item_version,
        },
    )

    api = sly.Api.from_env()
    workflow = Workflow(api)
    # dest_dir = "/sly_task_data/repo"
    dest_dir = my_app.data_dir
    # sly.fs.mkdir(dest_dir)
    sly.fs.clean_dir(dest_dir)

    tar_path = os.path.join(dest_dir, "repo.tar.gz")
    api.app.download_git_archive(
        ecosystem_item_id, None, ecosystem_item_version, tar_path, log_progress=True
    )
    with tarfile.open(tar_path) as archive:
        archive.extractall(dest_dir)

    subdirs = get_subdirs(dest_dir)
    if len(subdirs) != 1:
        raise RuntimeError("Repo is downloaded and extracted, but resulting directory not found")
    extracted_path = os.path.join(dest_dir, subdirs[0])
    clean_repo(extracted_path)

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

    project_meta = sly.ProjectMeta.from_json(meta_json)
    existing_project_ids = {p.id for p in api.project.get_list(workspace_id)}
    try:
        project_id, res_project_name = upload_project(
            api, dest_dir, workspace_id, project_name, project_meta
        )
    except Exception as e:
        usage_limit_error = get_usage_limit_error(e)
        if usage_limit_error is None:
            raise
        # 402 is final: finish normally so the job is not restarted until its backoff limit
        kept = remove_empty_partial_projects(
            api, workspace_id, project_name, existing_project_ids
        )
        report_usage_limit(api, task_id, usage_limit_error, kept)
        my_app.stop()
        return

    sly.logger.info("Project info: id={!r}, name={!r}".format(project_id, res_project_name))

    # to show created project in tasks list (output column)
    sly.logger.info(
        "PROJECT_CREATED",
        extra={"event_type": sly.EventType.PROJECT_CREATED, "project_id": project_id},
    )
    api.task.set_output_project(task_id, project_id, res_project_name)
    # ---------------------------------------- Workflow Output --------------------------------------- #
    workflow.add_output(project_id)
    # ----------------------------------------------- - ---------------------------------------------- #
    my_app.stop()


def upload_project(api, dest_dir, workspace_id, project_name, project_meta):
    project_type = project_meta.project_type
    if project_type == str(sly.ProjectType.IMAGES):
        if project_meta.labeling_interface == LabelingInterface.OVERLAY:
            project_id, res_project_name = upload_overlay_project(
                api, os.path.join(dest_dir, "project"), workspace_id, project_name, project_meta
            )

        else:
            project_id, res_project_name = sly.upload_project(
                dest_dir, api, workspace_id, project_name, log_progress=True
            )
            audio_dir = os.path.join(dest_dir, "audio")
            if sly.fs.dir_exists(audio_dir):
                upload_audio_references(api, project_id, audio_dir)
    elif project_type == str(sly.ProjectType.VIDEOS):
        project_id, res_project_name = sly.upload_video_project(
            dest_dir, api, workspace_id, project_name, log_progress=True
        )
    elif project_type == str(sly.ProjectType.VOLUMES):
        project_id, res_project_name = sly.upload_volume_project(
            dest_dir, api, workspace_id, project_name, log_progress=True
        )
    elif project_type == str(sly.ProjectType.POINT_CLOUDS):
        dest_dir = os.path.join(dest_dir, "project")
        project_id, res_project_name = upload_pointcloud_project(
            dest_dir, api, workspace_id, project_name, log_progress=True
        )
    elif project_type == str(sly.ProjectType.POINT_CLOUD_EPISODES):
        dest_dir = os.path.join(dest_dir, "project")
        project_id, res_project_name = upload_pointcloud_episode_project(
            dest_dir, api, workspace_id, project_name, log_progress=True
        )
    elif project_type == str(sly.ProjectType.AUDIO):
        dest_dir = os.path.join(dest_dir, "project")
        project_id, res_project_name = sly.upload_audio_project(
            dest_dir, api, workspace_id, project_name, log_progress=True
        )
    else:
        raise NotImplementedError("Unknown project type: {}".format(project_type))

    return project_id, res_project_name


def clean_repo(extracted_path: str):
    subdirs = get_subdirs(extracted_path)
    sly.logger.debug(
        f"Extracted path {extracted_path} contains following subdirectories: {subdirs}"
    )

    # audio/ holds the recordings that images with audio references point to
    for subdir in subdirs:
        if subdir not in ("project", "audio"):
            sly.fs.remove_dir(os.path.join(extracted_path, subdir))
    sly.logger.debug(
        f"Deleted all subdirectories except of 'project' and 'audio' from {extracted_path}"
    )


def main():
    initial_events = [
        {
            "state": None,
            "context": None,
            "command": "do",
        }
    ]

    # my_app.run(initial_events=initial_events)
    do(state=None, context=None)


if __name__ == "__main__":
    sly.main_wrapper("main", main, log_for_agent=False)
