import json
from fastapi.openapi.utils import get_openapi
import sys
import os

# Add services/api-gateway to path so we can import main
sys.path.append(os.path.join(os.path.dirname(__file__), "services", "api-gateway"))

from main import app

def export_openapi():
    with open("openapi.json", "w", encoding="utf-8") as f:
        json.dump(
            get_openapi(
                title=app.title,
                version=app.version,
                openapi_version=app.openapi_version,
                description=app.description,
                routes=app.routes,
            ),
            f,
            indent=2
        )
    print("Exported OpenAPI schema to openapi.json")

if __name__ == "__main__":
    export_openapi()
