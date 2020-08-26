import os
import json
import supervisely_lib as sly

team_id = os.environ['modal.state.teamId']
workspace_id = os.environ['modal.state.workspaceId']
project_name = os.environ['modal.state.projectName']
ecosystem_item_git_url = os.environ['modal.state.ecosystem_item_git_url']
ecosystem_item_version = os.environ.get('modal.state.ecosystem_item_version', "master")
github_token = os.environ.get('modal.context.github_token', None)

sly.logger.info("Script arguments", extra={"team_id: ": team_id,
                                           "workspace_id: ": workspace_id,
                                           "project_name: ": project_name,
                                           "ecosystem_item_git_url: ": ecosystem_item_git_url,
                                           "ecosystem_item_version: ": ecosystem_item_version,
                                           "github_token: ": github_token})

dest_dir = "/sly_task_data/repo"
sly.fs.mkdir(dest_dir)
sly.fs.clean_dir(dest_dir)
sly.git.download(ecosystem_item_git_url, dest_dir, github_token, ecosystem_item_version, log_progress=True)

api = sly.Api.from_env()
#project_name = sly.fs.get_file_name(ecosystem_item_git_url)

with open(os.path.join(dest_dir, "project", "meta.json")) as json_file:
    meta_json = json.load(json_file)

project_type = sly.ProjectMeta.from_json(meta_json).project_type
if project_type == str(sly.ProjectType.IMAGES):
    project_id, res_project_name = sly.upload_project(dest_dir, api, workspace_id, project_name, log_progress=True)
elif project_type == str(sly.ProjectType.VIDEOS):
    raise NotImplementedError("Video project")
elif project_type == str(sly.ProjectType.VOLUMES):
    raise NotImplementedError("DICOM project")
else:
    raise NotImplementedError("Unknown type: {}".format(project_type))

sly.logger.info("Project info: id={!r}, name={!r}".format(project_id, res_project_name))

# to show created project in tasks list (output column)
sly.logger.info('PROJECT_CREATED', extra={'event_type': sly.EventType.PROJECT_CREATED, 'project_id': project_id})