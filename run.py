"""Launch GovIntel AI on localhost, using a single FastAPI server."""
import os, threading, webbrowser, uvicorn
if __name__=='__main__':
    port=int(os.getenv('API_PORT','8000'))
    if os.getenv('NO_BROWSER')!='1': threading.Timer(2,lambda:webbrowser.open(f'http://localhost:{port}')).start()
    print(f'GovIntel AI: http://localhost:{port} | API docs: http://localhost:{port}/docs')
    uvicorn.run('backend.main:app',host=os.getenv('HOST','127.0.0.1'),port=port)
