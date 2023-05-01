from fastapi import APIRouter, Depends

from papermerge.core.models import User

from papermerge.core.schemas.folders import Folder as PyFolder
from papermerge.core.models import Folder

from .auth import oauth2_scheme
from .auth import get_current_user as current_user

router = APIRouter(
    prefix="/folders",
    tags=["folders"],
    dependencies=[Depends(oauth2_scheme)]
)


@router.get("/{folder_id}")
def get_node(
    folder_id,
    user: User = Depends(current_user)
) -> PyFolder:

    folder = Folder.objects.get(id=folder_id, user_id=user.id)
    return PyFolder.from_orm(folder)