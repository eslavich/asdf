"""
Methods for getting and setting asdf global configuration
options.
"""
import threading
from contextlib import contextmanager
import copy

from . import entry_points
from .resource import ResourceManager
from .extension import ExtensionProxy
from . import versioning
from ._helpers import validate_asdf_standard_version


DEFAULT_VALIDATE_ON_READ = True


class AsdfConfig:
    """
    Container for ASDF configuration options.  Users are not intended to
    construct this object directly; instead, use the `asdf.get_config` and
    `asdf.config_context` module methods.
    """

    def __init__(
        self,
        resource_mappings=None,
        resource_manager=None,
        extensions=None,
        validate_on_read=None,
        default_asdf_standard_version=None,
    ):
        self._resource_mappings = resource_mappings
        self._resource_manager = resource_manager
        self._extensions = extensions

        if validate_on_read is None:
            self._validate_on_read = DEFAULT_VALIDATE_ON_READ
        else:
            self._validate_on_read = validate_on_read

        if default_asdf_standard_version is None:
            self._default_asdf_standard_version = str(versioning.default_version)
        else:
            self._default_asdf_standard_version = default_asdf_standard_version

        self._lock = threading.RLock()

    @property
    def resource_mappings(self):
        """
        Get the list of resource Mapping instances.  Unless
        overridden by user configuration, this includes every Mapping
        registered with an entry point.

        Returns
        -------
        list of collections.abc.Mapping
        """
        if self._resource_mappings is None:
            with self._lock:
                if self._resource_mappings is None:
                    self._resource_mappings = entry_points.get_resource_mappings()
        return self._resource_mappings

    def add_resource_mapping(self, mapping):
        """
        Add a new resource Mapping.

        Parameters
        ----------
        mapping : collections.abc.Mapping
            map of `str` resource URI to `bytes` content
        """
        with self._lock:
            resource_mappings = self.resource_mappings.copy()
            resource_mappings.append(mapping)
            self._resource_mappings = resource_mappings
            self._resource_manager = None

    def remove_resource_mapping(self, mapping):
        """
        Remove a resource mapping.

        Parameters
        ----------
        mapping : collections.abc.Mapping
        """
        with self._lock:
            resource_mappings = [m for m in self.resource_mappings if m is not mapping]
            self._resource_mappings = resource_mappings
            self._resource_manager = None

    def reset_resources(self):
        """
        Reset resource mappings to the default list
        provided as entry points.
        """
        with self._lock:
            self._resource_mappings = None
            self._resource_manager = None

    @property
    def resource_manager(self):
        """
        Get the `ResourceManager` instance.  Includes resources from
        registered resource Mappings and any Mappings added at runtime.

        Returns
        -------
        asdf.resource.ResourceManager
        """
        if self._resource_manager is None:
            with self._lock:
                if self._resource_manager is None:
                    self._resource_manager = ResourceManager(self.resource_mappings)
        return self._resource_manager

    @property
    def extensions(self):
        """
        Get the list of installed `AsdfExtension` instances.

        Returns
        -------
        list of asdf.AsdfExtension
        """
        if self._extensions is None:
            with self._lock:
                if self._extensions is None:
                    self._extensions = entry_points.get_extensions()
        return self._extensions

    def get_extension(self, extension_uri):
        """
        Get the extension with the specified URI.

        Parameters
        ----------
        extension_uri : str

        Returns
        -------
        asdf.AsdfExtension
        """
        for extension in self.extensions:
            if extension.extension_uri == extension_uri:
                return extension

        raise ValueError("URI does not match any installed extension: {}".format(extension_uri))

    def get_default_extensions(self, asdf_standard_version):
        """
        Get the list of `AsdfExtension` instances that are
        enabled by default for new files.

        Parameters
        ----------
        asdf_standard_version : str
            The ASDF Standard version of the new file.

        Returns
        -------
        list of asdf.AsdfExtension
        """
        return [
            e for e in self.extensions
            if (e.default_enabled or e.always_enabled) and asdf_standard_version in e.asdf_standard_requirement
        ]

    def get_always_extensions(self, asdf_standard_version):
        """
        Get the list of `AsdfExtension` instances that are
        always enabled when reading or writing files.

        Parameters
        ----------
        asdf_standard_version : str
            The ASDF Standard version of the file.

        Returns
        -------
        list of asdf.AsdfExtension
        """
        return [
            e for e in self.extensions
            if e.always_enabled and asdf_standard_version in e.asdf_standard_requirement
        ]

    @property
    def validate_on_read(self):
        """
        Get flag that controls schema validation of
        ASDF files on read.

        Returns
        -------
        bool
        """
        return self._validate_on_read

    @validate_on_read.setter
    def validate_on_read(self, value):
        """
        Set the flag that controls schema validation of
        ASDF files on read.  If `True`, newly opened files will
        be validated.

        Parameters
        ----------
        value : bool
        """
        if not isinstance(value, bool):
            raise TypeError("validate_on_read must be bool")
        self._validate_on_read = value

    @property
    def default_asdf_standard_version(self):
        """
        Get the default ASDF Standard version for new files.

        Returns
        -------
        str
        """
        return self._default_asdf_standard_version

    @default_asdf_standard_version.setter
    def default_asdf_standard_version(self, value):
        """
        Set the default ASDF Standard version for new files.

        Parameters
        ----------
        value : str
        """
        self._default_asdf_standard_version = validate_asdf_standard_version(value)

    def __repr__(self):
        return (
            "AsdfConfig(\n"
            "  validate_on_read={!r},\n"
            "  default_asdf_standard_version={!r},\n"
            "  ..."
            ")"
        ).format(
            self.validate_on_read,
            self._default_asdf_standard_version,
        )


class _ConfigLocal(threading.local):
    def __init__(self):
        self.config_stack = []


_global_config = AsdfConfig()
_local = _ConfigLocal()


def get_config():
    """
    Get the current config, which may have been altered by
    one or more surrounding calls to `config_context`.

    Returns
    -------
    AsdfConfig
    """
    if len(_local.config_stack) == 0:
        return _global_config
    else:
        return _local.config_stack[-1]


@contextmanager
def config_context():
    """
    Context manager that temporarily overrides asdf configuration.
    The context yields an `AsdfConfig` instance that can be modified
    without affecting code outside of the context.
    """
    if len(_local.config_stack) == 0:
        base_config = _global_config
    else:
        base_config = _local.config_stack[-1]

    config = copy.copy(base_config)
    _local.config_stack.append(config)

    try:
        yield config
    finally:
        _local.config_stack.pop()
