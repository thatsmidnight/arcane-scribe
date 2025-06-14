# Third Party
from fastapi import APIRouter, Depends

# Local Modules
from api_backend.routers import query, srd
from api_backend.dependencies import verify_source_ip

# Create a router instance with a default prefix
router = APIRouter(dependencies=[Depends(verify_source_ip)])

# Include other routers
router.include_router(query.router)
router.include_router(srd.router)
