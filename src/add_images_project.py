import os
import json
import supervisely_lib as sly


context = json.loads(os.environ.get('CONTEXT', None))
state = json.loads(os.environ.get('STATE', None))

team_id = state["destination"]["teamId"]
workspace_id = state["destination"]["workspaceId"]
name = state["name"]

github_token = context.get("githubToken", None)
github_url = context["githubUrl"]

dest_dir = "/sly_task_data/repo"
sly.fs.clean_dir(dest_dir)
sly.git.download(github_url, dest_dir, github_token)

api = sly.Api.from_env()
project_name = sly.fs.get_file_name(github_url)
project_id, res_project_name = sly.upload_project(dest_dir, api, workspace_id, project_name, log_progress=True)
sly.logger.info("Project info: id={!r}, name={!r}".format(project_id, res_project_name))

# to show created project in tasks list (output column)
sly.logger.info('PROJECT_CREATED', extra={'event_type': sly.EventType.PROJECT_CREATED, 'project_id': project_id})