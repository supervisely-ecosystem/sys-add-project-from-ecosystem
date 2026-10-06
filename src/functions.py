from typing import Callable, Optional, Set
import supervisely as sly
import os
import re
from supervisely._utils import batched
from supervisely.io.fs import get_file_ext


def upload_overlay_project(
    api: sly.Api,
    project_dir: str,
    workspace_id: int,
    project_name: str,
    meta: sly.ProjectMeta,
    progress_cb: Optional[Callable] = None,
    batch_size: int = 50,
) -> int:
    project = api.project.create(workspace_id, project_name, change_name_if_conflict=True)
    api.project.update_meta(project.id, meta)
    try:
        api.project.set_overlay_settings(project.id)
    except Exception as e:
        try:
            api.app.set_output_text(
                sly.env.task_id(),
                "Failed to import project",
                description=(
                    "This project uses Overlay mode, which is available only in the "
                    "Images MAX package. Please choose another project from Ecosystem "
                    "or use a workspace with Images MAX support."
                ),
                zmdi_icon="zmdi-alert-triangle",
                icon_color="#FFA500",
                background_color="#FFE8BE",
            )
        except Exception:
            sly.logger.warning("Failed to set warning output text.", exc_info=True)
            raise e

    uploaded_items_cnt = 0

    for dataset_name in sorted(os.listdir(project_dir)):
        dataset_path = os.path.join(project_dir, dataset_name)
        if not sly.fs.dir_exists(dataset_path):
            continue

        imgs_dir = os.path.join(dataset_path, "img")
        ann_dir = os.path.join(dataset_path, "ann")
        overlay_dir = os.path.join(dataset_path, "overlay")
        if not sly.fs.dir_exists(imgs_dir):
            continue
        if not sly.fs.dir_exists(overlay_dir):
            sly.logger.warning(
                f"Skipping dataset '{dataset_name}' because directory '{overlay_dir}' was not found."
            )
            continue

        image_paths = sly.fs.list_files(
            imgs_dir,
            valid_extensions=sly.image.SUPPORTED_IMG_EXTS,
            ignore_valid_extensions_case=True,
        )
        if len(image_paths) == 0:
            continue

        dataset = api.dataset.create(project.id, dataset_name, change_name_if_conflict=True)
        meta_dir = os.path.join(dataset_path, "meta")

        items = []
        for image_path in image_paths:
            image_name = os.path.basename(image_path)
            image_stem = os.path.splitext(image_name)[0]
            image_overlay_dir = os.path.join(overlay_dir, image_stem)

            overlay_paths = []
            if sly.fs.dir_exists(image_overlay_dir):
                overlay_paths = sly.fs.list_files(
                    image_overlay_dir,
                    valid_extensions=sly.image.SUPPORTED_IMG_EXTS,
                    ignore_valid_extensions_case=True,
                )

            if len(overlay_paths) == 0:
                sly.logger.warning(
                    f"Skipping image '{image_name}' in dataset '{dataset_name}' because no overlay files were found."
                )
                continue

            ann_name = image_name + ".json"
            ann_path = os.path.join(ann_dir, ann_name)
            if not os.path.exists(ann_path):
                ann_path = None

            image_meta = {}
            image_meta_path = os.path.join(meta_dir, image_name + ".json")
            if os.path.isfile(image_meta_path):
                image_meta = sly.json.load_json_file(image_meta_path)

            items.append(
                {
                    "image_name": image_name,
                    "image_path": image_path,
                    "overlay_paths": overlay_paths,
                    "overlay_names": [os.path.basename(path) for path in overlay_paths],
                    "ann_path": ann_path,
                    "meta": image_meta,
                }
            )

        if len(items) == 0:
            sly.logger.warning(
                f"Skipping dataset '{dataset_name}' because no valid overlay items were found."
            )
            api.dataset.remove(dataset.id)
            continue

        for items_batch in batched(items, batch_size):
            parent_names = [item["image_name"] for item in items_batch]
            parent_paths = [item["image_path"] for item in items_batch]
            overlay_names = [item["overlay_names"] for item in items_batch]
            overlay_paths = [item["overlay_paths"] for item in items_batch]

            upload_result = api.image.upload_overlay_images(
                dataset.id,
                names=parent_names,
                paths=parent_paths,
                overlay_names=overlay_names,
                overlay_paths=overlay_paths,
            )
            image_infos = upload_result[0] if isinstance(upload_result, tuple) else upload_result
            uploaded_items_cnt += len(image_infos)

            if progress_cb is not None:
                progress_cb(len(items_batch))

            for image_info, item in zip(image_infos, items_batch):
                if len(item["meta"]) > 0:
                    api.image.update_meta(image_info.id, item["meta"])

            image_ids = []
            annotations = []
            for image_info, item in zip(image_infos, items_batch):
                ann_path = item["ann_path"]
                if ann_path is None:
                    continue
                try:
                    ann = sly.Annotation.load_json_file(ann_path, meta)
                except Exception:
                    sly.logger.warning(
                        f"Failed to load annotation for image '{item['image_name']}'. Skipping annotation upload.",
                        exc_info=True,
                    )
                    continue
                image_ids.append(image_info.id)
                annotations.append(ann)

            if len(image_ids) > 0:
                api.annotation.upload_anns(image_ids, annotations)
            if progress_cb is not None:
                progress_cb(len(items_batch))

    if uploaded_items_cnt == 0:
        api.project.remove(project.id)
        raise RuntimeError("Failed to import overlay project. No valid overlay items were found.")

    return project.id, project.name


USAGE_LIMIT_STATUS_CODE = 402


def get_usage_limit_error(exc: BaseException) -> Optional[str]:
    """Returns the server message if the exception (or its cause) is HTTP 402 Usage limits reached."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        response = getattr(exc, "response", None)
        if getattr(response, "status_code", None) == USAGE_LIMIT_STATUS_CODE:
            try:
                body = response.json()
                message = body.get("error") or body.get("message") or body.get("details")
            except Exception:
                message = None
            return str(message or response.text or "Usage limits reached")
        if "Usage limits reached" in str(exc):
            return str(exc)
        exc = exc.__cause__ or exc.__context__
    return None


def remove_partial_projects(
    api: sly.Api, workspace_id: int, project_name: str, existing_ids: Set[int]
) -> None:
    """Removes projects this task created in the workspace before the upload failed."""
    try:
        my_id = api.user.get_my_info().id
        name_pattern = re.compile(re.escape(project_name) + r"(_\d+)?")
        for project in api.project.get_list(workspace_id):
            if (
                project.id not in existing_ids
                and project.created_by_id == my_id
                and name_pattern.fullmatch(project.name)
            ):
                sly.logger.info(f"Removing partially uploaded project id={project.id}")
                api.project.remove(project.id)
    except Exception:
        sly.logger.warning("Failed to remove partially uploaded project.", exc_info=True)


def report_usage_limit(api: sly.Api, task_id: int, message: str) -> None:
    message = message.strip().rstrip(".")
    sly.logger.warning(f"Project was not added: {message}")
    try:
        api.app.set_output_text(
            task_id,
            "Plan limit reached",
            description=(
                f"{message}. The project was not added. "
                "Delete projects you no longer need or upgrade your plan, then try again."
            ),
            zmdi_icon="zmdi-alert-triangle",
            icon_color="#FFA500",
            background_color="#FFE8BE",
        )
    except Exception:
        sly.logger.warning("Failed to set warning output text.", exc_info=True)
