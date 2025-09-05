from setuptools import setup, find_packages

setup(
    name="kvopt",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.68.0",
        "uvicorn>=0.15.0",
        "pydantic>=1.8.0",
        "pyyaml>=5.4.1",
        "requests>=2.26.0",
    ],
    entry_points={
        "console_scripts": [
            "kvopt-server=kvopt.server.main:main",
        ],
    },
)
