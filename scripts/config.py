"""Shared configuration for Beacon build scripts."""

import os
from pathlib import Path

# Repository root - resolve relative to this file's location
REPO_ROOT = Path(__file__).parent.parent

# Source data
SOURCE_DIR = REPO_ROOT / "source" / "raw"
SOURCE_CSV = SOURCE_DIR / "kentucky.csv"

# Generated data output
DATA_DIR = REPO_ROOT / "data"
RESOURCES_JSON = DATA_DIR / "resources.json"
RESOURCES_CSV = DATA_DIR / "resources.csv"
INDEX_JSON = DATA_DIR / "index.json"

# Schema files
SCHEMA_DIR = REPO_ROOT / "schema"
RESOURCE_SCHEMA = SCHEMA_DIR / "resource.schema.json"
CATEGORIES_SCHEMA = SCHEMA_DIR / "categories.json"
COUNTIES_SCHEMA = SCHEMA_DIR / "counties.json"

# Tests
TESTS_DIR = REPO_ROOT / "tests"

# Scripts
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Build date
BUILD_DATE = "2026-09-20"

# Version
VERSION = "2.0.0"

# Base path for GitHub Pages (all internal links must use this)
BASE_PATH = "/beacon"
