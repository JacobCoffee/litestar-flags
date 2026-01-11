Installation
============

This page covers detailed installation instructions for litestar-flags.


Requirements
------------

- Python 3.11 or higher
- Litestar 2.0.0 or higher


Installing from PyPI
--------------------

The simplest way to install litestar-flags is via your preferred package manager:

.. tab-set::
   :sync-group: package-manager

   .. tab-item:: uv (Recommended)
      :sync: uv

      .. code-block:: bash

         uv add litestar-flags

   .. tab-item:: pip
      :sync: pip

      .. code-block:: bash

         pip install litestar-flags


Optional Dependencies
---------------------

litestar-flags supports multiple storage backends through optional dependencies:

Redis Support
~~~~~~~~~~~~~

For distributed feature flag storage using Redis:

.. tab-set::
   :sync-group: package-manager

   .. tab-item:: uv (Recommended)
      :sync: uv

      .. code-block:: bash

         uv add litestar-flags[redis]

   .. tab-item:: pip
      :sync: pip

      .. code-block:: bash

         pip install litestar-flags[redis]

This installs ``redis>=5.0.0`` as a dependency.

Database Support
~~~~~~~~~~~~~~~~

For persistent storage using SQLAlchemy (supports PostgreSQL, MySQL, SQLite, etc.):

.. tab-set::
   :sync-group: package-manager

   .. tab-item:: uv (Recommended)
      :sync: uv

      .. code-block:: bash

         uv add litestar-flags[database]

   .. tab-item:: pip
      :sync: pip

      .. code-block:: bash

         pip install litestar-flags[database]

This installs ``advanced-alchemy>=0.10.0`` and ``sqlalchemy[asyncio]>=2.0.0``.

Workflow Support
~~~~~~~~~~~~~~~~

For approval workflows and governance features using litestar-workflows:

.. tab-set::
   :sync-group: package-manager

   .. tab-item:: uv (Recommended)
      :sync: uv

      .. code-block:: bash

         uv add litestar-flags[workflows]

   .. tab-item:: pip
      :sync: pip

      .. code-block:: bash

         pip install litestar-flags[workflows]

This installs ``litestar-workflows>=0.1.0`` for human-in-the-loop approval
workflows, scheduled rollouts, and auditable flag changes.

All Dependencies
~~~~~~~~~~~~~~~~

To install all optional dependencies:

.. tab-set::
   :sync-group: package-manager

   .. tab-item:: uv (Recommended)
      :sync: uv

      .. code-block:: bash

         uv add litestar-flags[all]

   .. tab-item:: pip
      :sync: pip

      .. code-block:: bash

         pip install litestar-flags[all]


Development Installation
------------------------

For contributing to litestar-flags:

.. code-block:: bash

   git clone https://github.com/JacobCoffee/litestar-flags.git
   cd litestar-flags

.. tab-set::
   :sync-group: package-manager

   .. tab-item:: uv (Recommended)
      :sync: uv

      .. code-block:: bash

         uv sync

   .. tab-item:: pip
      :sync: pip

      .. code-block:: bash

         pip install -e ".[dev]"


Verifying Installation
----------------------

You can verify the installation by importing the package:

.. code-block:: python

   >>> import litestar_flags
   >>> print(litestar_flags.__version__)
   0.1.0
