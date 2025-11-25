"""Web routes for admin dashboard - Main router configuration."""
from fastapi import APIRouter
from app.web.routes import auth, dashboard, clients, api_keys

# Create main router
router = APIRouter()

# Include authentication routes (no prefix, under /admin/)
router.include_router(auth.router, prefix="/admin", tags=["auth"])

# Include dashboard routes (under /admin/)
router.include_router(dashboard.router, prefix="/admin", tags=["dashboard"])

# Include client management routes (under /admin/clients)
router.include_router(clients.router, prefix="/admin/clients", tags=["clients"])

# Include API key management routes (under /admin/clients)
router.include_router(api_keys.router, prefix="/admin/clients", tags=["api-keys"])
