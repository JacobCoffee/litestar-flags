:layout: landing
:description: Production-ready feature flags for Litestar applications with percentage rollouts, A/B testing, and time-based rules.

litestar-flags
==============

.. rst-class:: lead

   Ship features with confidence. Production-ready feature flags
   for `Litestar <https://litestar.dev>`_ with percentage rollouts,
   A/B testing, user targeting, and time-based scheduling.

.. container:: buttons

   `Get Started </getting-started/index.html>`_
   `GitHub <https://github.com/JacobCoffee/litestar-flags>`_
   `PyPI <https://pypi.org/project/litestar-flags/>`_


.. grid:: 1 1 2 3
   :gutter: 2
   :padding: 0
   :class-row: surface

   .. grid-item-card:: :octicon:`database` Multiple Backends

      Memory, Redis, and SQLAlchemy storage backends.
      Choose what fits your infrastructure.

   .. grid-item-card:: :octicon:`graph` Percentage Rollouts

      Gradually release features to a subset of users.
      Roll back instantly if issues arise.

   .. grid-item-card:: :octicon:`beaker` A/B Testing

      Built-in variant support for experimentation.
      Measure impact with confidence.

   .. grid-item-card:: :octicon:`people` User Targeting

      Target specific users, groups, or segments.
      Personalize experiences at scale.

   .. grid-item-card:: :octicon:`clock` Time-based Rules

      Schedule launches, maintenance windows,
      and recurring availability patterns.

   .. grid-item-card:: :octicon:`plug` OpenFeature

      Vendor-agnostic feature flagging via
      the OpenFeature standard.

-----

Quick Start
-----------

.. code-block:: python
   :caption: app.py

   from litestar import Litestar, get
   from litestar_flags import FeatureFlagsPlugin, FeatureFlagsConfig, FeatureFlagsClient

   config = FeatureFlagsConfig()
   plugin = FeatureFlagsPlugin(config=config)

   @get("/")
   async def index(feature_flags: FeatureFlagsClient) -> dict:
       if await feature_flags.is_enabled("dark_mode"):
           return {"theme": "dark"}
       return {"theme": "light"}

   app = Litestar(plugins=[plugin])


.. grid:: 1 2 2 2
   :gutter: 2
   :padding: 0
   :class-row: surface

   .. grid-item-card:: :octicon:`shield-check` Type-Safe
      :class-card: sd-border-0

      Full type hints with msgspec validation.
      Catch errors before they reach production.

   .. grid-item-card:: :octicon:`rocket` Zero Config
      :class-card: sd-border-0

      Works out of the box with sensible defaults.
      Customize when you need to.

   .. grid-item-card:: :octicon:`sync` Async Native
      :class-card: sd-border-0

      Built for async from the ground up.
      No blocking operations.

   .. grid-item-card:: :octicon:`package` Lightweight
      :class-card: sd-border-0

      Minimal dependencies. Install only
      the backends you need.

-----

.. grid:: 1 1 3 3
   :gutter: 2
   :padding: 0

   .. grid-item-card:: Getting Started
      :link: getting-started/index
      :link-type: doc
      :class-card: sd-rounded-3

      Installation, configuration, and your first feature flag in minutes.

   .. grid-item-card:: How-To Guides
      :link: guides/index
      :link-type: doc
      :class-card: sd-rounded-3

      Step-by-step guides for rollouts, testing, targeting, and more.

   .. grid-item-card:: API Reference
      :link: api/index
      :link-type: doc
      :class-card: sd-rounded-3

      Complete documentation for all modules, classes, and functions.


.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Documentation

   getting-started/index
   guides/index
   api/index


.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Integrations

   user-guide/openfeature
   user-guide/time-based-rules
   user-guide/multi-environment
   user-guide/analytics
   usage/admin-api
   guides/workflows


.. toctree::
   :maxdepth: 1
   :hidden:
   :caption: Project

   changelog
   GitHub <https://github.com/JacobCoffee/litestar-flags>
