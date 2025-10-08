lazyk8s
=======

The lazier way to manage Kubernetes - Python edition

A terminal UI for managing Kubernetes clusters with ease.

.. image:: screenshot.png
   :alt: lazyk8s screenshot

Features
--------

- Browse pods across namespaces
- View pod information and logs
- Execute shells in containers
- Colorized log output
- Keyboard-driven interface

Installation
------------

.. code-block:: bash

   pip install lazyk8s

Usage
-----

.. code-block:: bash

   lazyk8s <namespace> 

Requirements
------------

- Python 3.8+
- kubectl configured with access to your cluster
- KUBECONFIG environment variable set (or default ~/.kube/config)

Development
-----------

.. code-block:: bash

   pip install -e . 

Acknowledgements
----------------

- Inspired by `lazydocker <https://github.com/jesseduffield/lazydocker>`_ by Jesse Duffield
- Built with `Textual <https://github.com/Textualize/textual>`_ TUI framework
