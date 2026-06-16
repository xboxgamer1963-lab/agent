import sys
import os

# Make sure the app root is on the path
sys.path.insert(0, os.path.dirname(__file__))

from a2wsgi import ASGIMiddleware
from backend.main import app

application = ASGIMiddleware(app)
