import os
import supervisely_lib as sly

print("hello")

github_token = os.environ.get('GITHUB_TOKEN', None)
github_token = os.environ.get('GITHUB_URL', None)
github_url = "https://github.com/supervisely-ecosystem/lemons_annotated"
workspace_id = 47 # os.environ.get('WORKSPACE_ID', None)

dest_dir = "/sly_task_data/repo"
sly.fs.clean_dir(dest_dir)
sly.git.download(github_url, dest_dir, github_token)

api = sly.Api.from_env()
project_name = sly.fs.get_file_name(github_url)
project_id, res_project_name = sly.upload_project(dest_dir, api, workspace_id, project_name, log_progress=True)
sly.logger.info("Project info: id={!r}, name={!r}".format(project_id, res_project_name))

# to show created project in tasks list (output column)
sly.logger.info('PROJECT_CREATED', extra={'event_type': sly.EventType.PROJECT_CREATED, 'project_id': project_id})