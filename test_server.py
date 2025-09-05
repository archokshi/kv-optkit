import sys
import os
import asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kvopt.server.main import app, startup_event

def test_server_startup():
    """Test if the server can start up correctly."""
    # Initialize the app
    asyncio.run(startup_event())
    
    # Create a test client
    client = TestClient(app)
    
    # Test health check endpoint
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    
    print("✅ Server started successfully and health check passed")

if __name__ == "__main__":
    test_server_startup()
