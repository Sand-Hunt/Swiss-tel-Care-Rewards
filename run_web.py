import uvicorn
from app.config import get_settings

if __name__ == '__main__':
    settings = get_settings()
    uvicorn.run('app.web.app:app', host=settings.web_host, port=settings.port, reload=False)
