"""Sphinx configuration for litestar-flags documentation."""

from __future__ import annotations

import logging
import os
import sys
import warnings
from datetime import datetime

# Add the source directory to the path for autodoc
sys.path.insert(0, os.path.abspath("../src"))

# -- Project information -----------------------------------------------------

project = "litestar-flags"
copyright = f"{datetime.now().year}, Jacob Coffee"  # noqa: A001
author = "Jacob Coffee"
release = "0.1.0"
version = "0.1.0"

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx_autodoc_typehints",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
master_doc = "index"
language = "en"

# -- Napoleon settings -------------------------------------------------------

napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True

# -- Autodoc settings --------------------------------------------------------

autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
    "show-inheritance": True,
    "no-value": True,  # Don't show default values in signature
}
autodoc_class_signature = "separated"
autodoc_typehints = "description"
autodoc_inherit_docstrings = True
autosummary_generate = False  # Disabled - using manual module pages instead

# Mock optional dependencies that may not be installed
autodoc_mock_imports = [
    "litestar_workflows",
    "openfeature",
]

# Filter out duplicate object warnings from pydantic/dataclass fields


class DuplicateObjectFilter(logging.Filter):
    """Filter out duplicate object description warnings."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter duplicate object warnings from dataclasses."""
        msg = record.getMessage()
        if "duplicate object description" in msg:
            return False
        return True


# Apply filters to all relevant loggers
for logger_name in [
    "sphinx.domains.python",
    "sphinx.domains",
    "sphinx",
    "docutils",
]:
    logging.getLogger(logger_name).addFilter(DuplicateObjectFilter())

# Also filter warnings module
warnings.filterwarnings("ignore", message=".*duplicate object description.*")

# -- Type hints settings -----------------------------------------------------

typehints_fully_qualified = False
always_document_param_types = True
typehints_document_rtype = True

# -- Intersphinx settings ----------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "litestar": ("https://docs.litestar.dev/latest/", None),
    "sqlalchemy": ("https://docs.sqlalchemy.org/en/20/", None),
    "redis": ("https://redis-py.readthedocs.io/en/stable/", None),
}

# -- Todo settings -----------------------------------------------------------

todo_include_todos = True

# -- MyST Parser settings ----------------------------------------------------

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "html_admonition",
    "html_image",
    "linkify",
    "replacements",
    "smartquotes",
    "strikethrough",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3

# -- Copy button settings ----------------------------------------------------

copybutton_prompt_text = r">>> |\.\.\. |\$ |In \[\d*\]: | {2,5}\.\.\.: | {5,8}: "
copybutton_prompt_is_regexp = True
copybutton_remove_prompts = True

# -- Suppress warnings -------------------------------------------------------

# Suppress warnings:
# - myst.header: MyST parser header warnings
# - ref.python: Python cross-reference warnings (optional deps not installed)
# - autodoc: Suppress autodoc duplicate warnings from pydantic/dataclass fields
suppress_warnings = ["myst.header", "ref.python", "autodoc"]

# Disable nitpicky mode to avoid false positives on missing references
nitpicky = False

# -- HTML output -------------------------------------------------------------

html_theme = "shibuya"
html_title = "litestar-flags"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

html_theme_options = {
    "accent_color": "bronze",
    "github_url": "https://github.com/JacobCoffee/litestar-flags",
    "nav_links": [
        {"title": "Litestar", "url": "https://litestar.dev/"},
        {"title": "PyPI", "url": "https://pypi.org/project/litestar-flags/"},
    ],
}
