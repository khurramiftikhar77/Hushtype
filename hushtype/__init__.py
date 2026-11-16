__version__ = "0.5.0"

try:  # written by the installer build (CI): "build 7, 610033e"
    from hushtype._build import BUILD
except ImportError:
    BUILD = "development"
