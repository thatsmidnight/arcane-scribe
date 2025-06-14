# Third Party
from fastapi import APIRouter

# Local Modules
from api_backend.routers import query, srd

# Create a router instance with a default prefix
router = APIRouter()

# Include other routers
router.include_router(query.router)
router.include_router(srd.router)
