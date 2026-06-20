#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from main import app
import uvicorn

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=8000)
