import os
from typing import Optional
from fastapi import Request, HTTPException
from agenta_backend.utils.common import APIRouter
import logging

from agenta_backend.models.api.api_models import (
    SaveConfigPayload,
    GetConfigResponse,
)
from agenta_backend.services import (
    db_manager,
    app_manager,
)

if os.environ["FEATURE_FLAG"] in ["cloud", "ee"]:
    from agenta_backend.commons.services.selectors import (
        get_user_and_org_id,
    )  # noqa pylint: disable-all
else:
    from agenta_backend.services.selectors import get_user_and_org_id


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

router = APIRouter()


@router.post("/", operation_id="save_config")
async def save_config(
    payload: SaveConfigPayload,
    request: Request,
):
    try:
        user_org_data: dict = await get_user_and_org_id(request.state.user_id)
        base_db = await db_manager.fetch_base_and_check_access(
            payload.base_id, user_org_data
        )
        variants_db = await db_manager.list_variants_for_base(base_db, **user_org_data)
        variant_to_overwrite = None
        for variant_db in variants_db:
            if variant_db.config_name == payload.config_name:
                variant_to_overwrite = variant_db
                break
        if variant_to_overwrite is not None:
            if payload.overwrite or variant_to_overwrite.config.parameters == {}:
                print(f"update_variant_parameters  ===> {payload.overwrite}")
                await app_manager.update_variant_parameters(
                    app_variant_id=str(variant_to_overwrite.id),
                    parameters=payload.parameters,
                    **user_org_data,
                )
            else:
                raise HTTPException(
                    status_code=200,
                    detail="Config name already exists. Please use a different name or set overwrite to True.",
                )
        else:
            print(
                f"add_variant_from_base_and_config overwrite ===> {payload.overwrite}"
            )
            await db_manager.add_variant_from_base_and_config(
                base_db=base_db,
                new_config_name=payload.config_name,
                parameters=payload.parameters,
                **user_org_data,
            )
    except HTTPException as e:
        logger.error(f"save_config http exception ===> {e.detail}")
        raise
    except Exception as e:
        logger.error(f"save_config exception ===> {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/", response_model=GetConfigResponse, operation_id="get_config")
async def get_config(
    request: Request,
    base_id: str,
    config_name: Optional[str] = None,
    environment_name: Optional[str] = None,
):
    try:
        # detemine whether the user has access to the base
        user_org_data: dict = await get_user_and_org_id(request.state.user_id)
        base_db = await db_manager.fetch_base_and_check_access(base_id, user_org_data)
        # in case environment_name is provided, find the variant deployed
        if environment_name:
            app_environments = await db_manager.list_environments(
                app_id=str(base_db.app.id)
            )
            found_variant = None
            for app_environment in app_environments:
                if app_environment.name == environment_name:
                    found_variant_revision = (
                        app_environment.deployed_app_variant_revision
                    )
                    break
            if not found_variant_revision:
                raise HTTPException(
                    status_code=400,
                    detail=f"Environment name {environment_name} not found for base {base_id}",
                )
            if str(found_variant_revision.base.id) != base_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Environment {environment_name} does not deploy base {base_id}",
                )
            config = found_variant_revision.config
        elif config_name:
            variants_db = await db_manager.list_variants_for_base(
                base_db, **user_org_data
            )
            found_variant = None
            for variant_db in variants_db:
                if variant_db.config_name == config_name:
                    found_variant = variant_db
                    break
            if not found_variant:
                raise HTTPException(
                    status_code=400,
                    detail=f"Config name {config_name} not found for base {base_id}",
                )
            config = found_variant.config
        logger.debug(config.parameters)
        return GetConfigResponse(
            config_id=str(
                0
            ),  # TODO: Remove from the model and regenerate the SDK client
            config_name=config.config_name,
            current_version=str(
                0
            ),  # TODO: remove from teh model and regenerate the SDK client
            parameters=config.parameters,
        )
    except HTTPException as e:
        logger.error(f"get_config http exception: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"get_config exception: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get(
    "/deployment/{deployment_revision_id}/",
    operation_id="get_config_deployment_revision",
)
async def get_config_deployment_revision(request: Request, deployment_revision_id: str):
    environment_revision = await db_manager.fetch_app_environment_revision(
        deployment_revision_id
    )
    if environment_revision is None:
        raise HTTPException(
            404, f"No environment revision found for {deployment_revision_id}"
        )

    variant_revision = await db_manager.fetch_app_variant_revision_by_id(
        str(environment_revision.deployed_app_variant_revision)
    )
    if not variant_revision:
        raise HTTPException(
            404,
            f"No configuration found for deployment revision {deployment_revision_id}",
        )
    return GetConfigResponse(
        **variant_revision.config.dict(),
        current_version=environment_revision.revision,
    )


@router.post(
    "/deployment/{deployment_revision_id}/revert/",
    operation_id="revert_deployment_revision",
)
async def revert_deployment_revision(request: Request, deployment_revision_id: str):
    environment_revision = await db_manager.fetch_app_environment_revision(
        deployment_revision_id
    )
    if environment_revision is None:
        raise HTTPException(
            404,
            f"No environment revision found for deployment revision {deployment_revision_id}",
        )

    if environment_revision.deployed_app_variant_revision is None:
        raise HTTPException(
            404,
            f"No deployed app variant found for deployment revision: {deployment_revision_id}",
        )

    await db_manager.update_app_environment_deployed_variant_revision(
        environment_revision.environment,
        environment_revision.deployed_app_variant_revision,
    )
    return "Environment was reverted to deployment revision successful"
