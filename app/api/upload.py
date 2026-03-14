
from fastapi import APIRouter, UploadFile, File

from app.services.upload_service import upload_dataset_service

router = APIRouter()


@router.post("/")
async def upload_dataset(file: UploadFile = File(...)):

    result = await upload_dataset_service(file)

    return result
