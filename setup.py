from setuptools import setup, find_packages

setup(
    name="testpilot-ai",
    version="0.1.0",
    description="AI-powered automated testing for Python + Siebel + SOLR + React stacks",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "anthropic>=0.40.0",
        "httpx>=0.27.0",
        "pytest>=8.0.0",
        "respx>=0.21.0",
        "zeep>=4.2.1",
        "pyyaml>=6.0.1",
    ],
    extras_require={
        "dev": ["pytest-cov", "pytest-asyncio", "pytest-json-report"],
    },
    entry_points={
        "console_scripts": [
            "testpilot=testpilot.__main__:main",
        ]
    },
)
