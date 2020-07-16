import os
import abc
import warnings
from pkg_resources import iter_entry_points
from collections import defaultdict

import yaml

from . import types
from . import resolver
from .util import get_class_name
from .type_index import AsdfTypeIndex
from .version import version as asdf_version
from .exceptions import AsdfDeprecationWarning, AsdfWarning
from ._converter import ConverterProxy


__all__ = ['AsdfExtension', 'AsdfExtensionList']


ASDF_TEST_BUILD_ENV = 'ASDF_TEST_BUILD'


class AsdfTagDescription:
    def __init__(self, tag_uri, schema_uri=None, title=None, description=None):
        self._tag_uri = tag_uri
        self._schema_uri = schema_uri
        self._title = title
        self._description = description

    @property
    def tag_uri(self):
        return self._tag_uri

    @property
    def schema_uri(self):
        return self._schema_uri

    @property
    def title(self):
        return self._title

    @property
    def description(self):
        return self._description


class AsdfExtension(abc.ABC):
    """
    Abstract base class defining an extension to ASDF.
    """
    @classmethod
    def __subclasshook__(cls, C):
        if cls is AsdfExtension:
            return (
                hasattr(C, 'types') and hasattr(C, 'tag_mapping') or
                hasattr(C, 'extension_uri')
            )
        return NotImplemented

    @property
    def extension_uri(self):
        """
        Get this extension's identifying URI.  New-style `AsdfExtension`
        implementations (those that define the `converters` property)
        must define a URI.

        Returns
        -------
        str
        """
        return None

    @property
    def tags(self):
        """
        Get the tags supported by this extension.

        Returns
        -------
        iterable of str or AsdfTagDescription
            If str, the tag URI value.
        """
        return []

    @property
    def default_enabled(self):
        """
        Return `True` if this extension should be enabled by default.
        Typically extension packages will enable only the latest
        version of the extension.

        Returns
        -------
        bool
        """
        return False

    @property
    def types(self):
        """
        DEPRECATED.  This property will be ignored in asdf 3.0.
        Support for custom types can be provided via the `converters`
        property.

        A list of `asdf.CustomType` subclasses that describe how to store
        custom objects to and from ASDF.
        """
        return []

    @property
    def tag_mapping(self):
        """
        DEPRECATED.  This property will be ignored in asdf 3.0.
        The mapping of tag to schema URI is now defined on each
        individual `AsdfConverter` instance.

        A list of 2-tuples or callables mapping YAML tag prefixes to JSON Schema
        URL prefixes.

        For each entry:

        - If a 2-tuple, the first part of the tuple is a YAML tag
          prefix to match.  The second part is a string, where case
          the following are available as Python formatting tokens:

          - ``{tag}``: the complete YAML tag.
          - ``{tag_suffix}``: the part of the YAML tag after the
            matched prefix.
          - ``{tag_prefix}``: the matched YAML tag prefix.

        - If a callable, it is passed the entire YAML tag must return
          the entire JSON schema URL if it matches, otherwise, return `None`.

        Note that while JSON Schema URLs uniquely define a JSON
        Schema, they do not have to actually exist on an HTTP server
        and be fetchable (much like XML namespaces).

        For example, to match all YAML tags with the
        ``tag:nowhere.org:custom` prefix to the
        ``http://nowhere.org/schemas/custom/`` URL prefix::

           return [('tag:nowhere.org:custom/',
                    'http://nowhere.org/schemas/custom/{tag_suffix}')]
        """
        return []

    @property
    def url_mapping(self):
        """
        DEPRECATED.  This property will be ignored in asdf 3.0.
        Schema content can be provided using the resource Mapping API.

        A list of 2-tuples or callables mapping JSON Schema URLs to
        other URLs.  This is useful if the JSON Schemas are not
        actually fetchable at their corresponding URLs but are on the
        local filesystem, or, to save bandwidth, we have a copy of
        fetchable schemas on the local filesystem.  If neither is
        desirable, it may simply be the empty list.

        For each entry:

        - If a 2-tuple, the first part is a URL prefix to match.  The
          second part is a string, where the following are available
          as Python formatting tokens:

          - ``{url}``: The entire JSON schema URL
          - ``{url_prefix}``: The matched URL prefix
          - ``{url_suffix}``: The part of the URL after the prefix.

        - If a callable, it is passed the entire JSON Schema URL and
          must return a resolvable URL pointing to the schema content.
          If it doesn't match, should return `None`.

        For example, to map a remote HTTP URL prefix to files installed
        alongside as data alongside Python module::

            return [('http://nowhere.org/schemas/custom/1.0.0/',
                    asdf.util.filepath_to_url(
                        os.path.join(SCHEMA_PATH, 'stsci.edu')) +
                    '/{url_suffix}.yaml'
                   )]
        """
        return []

    @property
    def converters(self):
        """
        Iterable of `AsdfConverter` instances that support new tags
        provided by this extension.

        Returns
        -------
        iterable of asdf.AsdfConverter
        """
        return []


class ManifestExtension(AsdfExtension):
    def __init__(self, extension_uri, converters=None, default_enabled=False):
        self._extension_uri = extension_uri
        self._default_enabled = default_enabled
        self._converters = converters

        from ._config import get_config
        self._manifest = yaml.safe_load(get_config().resouce_manager[extension_uri])

    @property
    def extension_uri(self):
        return self._extension_uri

    @property
    def default_enabled(self):
        return self._default_enabled

    @property
    def converters(self):
        return self._converters

    @property
    def tags(self):
        result = []
        for tag in self._manifest.get("tags", []):
            result.append(AsdfTagDescription(
                tag["tag_uri"],
                schema_uri=tag.get("schema_uri"),
                title=tag.get("title"),
                description=tag.get("description"),
            ))
        return result


class ExtensionProxy(AsdfExtension):
    """
    Proxy that wraps an `AsdfExtension` and provides default
    implementations of optional methods.
    """
    def __init__(self, delegate, legacy=False):
        self._delegate = delegate
        self._legacy = legacy

    @property
    def extension_uri(self):
        return getattr(self._delegate, "extension_uri", None)

    @property
    def converters(self):
        converters = getattr(self._delegate, "converters", [])
        return [ConverterProxy(c, self) for c in converters]

    @property
    def types(self):
        return getattr(self._delegate, "types", [])

    @property
    def tag_mapping(self):
        return getattr(self._delegate, "tag_mapping", [])

    @property
    def url_mapping(self):
        return getattr(self._delegate, "url_mapping", [])

    @property
    def tag_descriptions(self):
        result = []
        for tag in getattr(self._delegate, "tags", []):
            if isinstance(tag, str):
                result.append(AsdfTagDescription(tag))
            elif isinstance(tag, AsdfTagDescription):
                result.append(tag)
            else:
                # TODO: Error should mention the extension's package name
                raise TypeError("Extension tags value must be str or AsdfTagDescription")
        return result

    @property
    def default_enabled(self):
        return getattr(self._delegate, "default_enabled", False)

    @property
    def delegate(self):
        return self._delegate

    @property
    def legacy(self):
        return self._legacy

    # TODO: __repr__

    # TODO: Need to know the package name

    @property
    def fully_qualified_class_name(self):
        delegate = self._delegate
        return delegate.__class__.__module__ + "." + delegate.__class__.__qualname__


class ExtensionManager:
    def __init__(self, extensions):
        extensions = [ExtensionProxy(e) for e in extensions]

        converters_by_type = defaultdict(list)
        converters_by_tag = defaultdict(list)
        extensions_by_tag = defaultdict(list)

        for extension in extensions:
            for converter in extension.converters:
                for typ in converter.types:
                     converters_by_type[typ].append(converter)
                for tag in converter.tags:
                    converters_by_tag[tag].append(converter)
            for tag_desc in extension.tag_descriptions:
                extensions_by_tag[tag_desc.tag_uri].append(extension)

        disable_extensions = set()

        for typ, converters in converters_by_type.items():
            if len(converters) > 1:
                for c in converters:
                    disable_extensions.add(c.extension)

        for tag, converters in converters_by_tag.items():
            if len(converters) > 1:
                for c in converters:
                    disable_extensions.add(c.extension)

        for tag, tag_extensions in extensions_by_tag.items():
            if len(tag_extensions) > 1:
                disable_extensions.add(tag_extensions)

        if len(disable_extensions) > 0:
            warnings.warn(
                "The following extensions conflict in their support for "
                "Python types, YAML tags, or both: \n\n{}\n\n"
                "They will all be ignored.  Disable the unneeded extensions "
                "with asdf.get_config().disable_extension(...) to allow the "
                "others to be used.".format("\n".join(repr(e) for e in disable_extensions)),
                AsdfWarning

            )

        self._extensions = [e for e in extensions if e not in disable_extensions]
        self._converters_by_type = {}
        self._converters_by_tag = {}
        self._tag_descriptions_by_tag = {}

        for extension in self._extensions:
            for converter in extension.converters:
                for typ in converter.types:
                     self._converters_by_type[typ] = converter
                for tag in converter.tags:
                    self._converters_by_tag[tag] = converter
            for tag_desc in extension.tag_descriptions:
                self._tag_descriptions_by_tag[tag_desc.tag_uri] = tag_desc

    def get_tag_schema_uri(self, tag):
        tag_description = self._tag_descriptions_by_tag.get(tag)
        if tag_description is None:
            # TODO: warn missing tag?
            return None
        else:
            return tag_description.schema_uri

    def get_converter_for_tag(self, tag):
        return self._converters_by_tag.get(tag)

    def get_converter_for_type(self, type):
        return self._converters_by_type.get(type)


class AsdfExtensionList:
    """
    Manage a set of extensions that are in effect.
    """
    def __init__(self, extensions):
        tag_mapping = []
        url_mapping = []
        validators = {}
        self._type_index = AsdfTypeIndex()
        for extension in extensions:
            if not isinstance(extension, AsdfExtension):
                raise TypeError(
                    "Extension must implement asdf.types.AsdfExtension "
                    "interface")
            tag_mapping.extend(extension.tag_mapping)
            # New-style extensions will not include a url_mapping attribute.
            if hasattr(extension, "url_mapping"):
                url_mapping.extend(extension.url_mapping)
            for typ in extension.types:
                self._type_index.add_type(typ, extension)
                validators.update(typ.validators)
                for sibling in typ.versioned_siblings:
                    self._type_index.add_type(sibling, extension)
                    validators.update(sibling.validators)
        self._tag_mapping = resolver.Resolver(tag_mapping, 'tag')
        self._url_mapping = resolver.Resolver(url_mapping, 'url')
        self._resolver = resolver.ResolverChain(self._tag_mapping, self._url_mapping)
        self._validators = validators

    @property
    def tag_to_schema_resolver(self):
        """Deprecated. Use `tag_mapping` instead"""
        warnings.warn(
            "The 'tag_to_schema_resolver' property is deprecated. Use "
            "'tag_mapping' instead.",
            AsdfDeprecationWarning)
        return self._tag_mapping

    @property
    def tag_mapping(self):
        return self._tag_mapping

    @property
    def url_mapping(self):
        return self._url_mapping

    @property
    def resolver(self):
        return self._resolver

    @property
    def type_index(self):
        return self._type_index

    @property
    def validators(self):
        return self._validators


class BuiltinExtension:
    """
    This is the "extension" to ASDF that includes all the built-in
    tags.  Even though it's not really an extension and it's always
    available, it's built in the same way as an extension.
    """
    @property
    def types(self):
        return types._all_asdftypes

    @property
    def tag_mapping(self):
        return resolver.DEFAULT_TAG_TO_URL_MAPPING

    @property
    def url_mapping(self):
        return resolver.DEFAULT_URL_MAPPING


class _DefaultExtensions:
    def __init__(self):
        self._extensions = []
        self._extension_list = None
        self._package_metadata = {}

    def _load_installed_extensions(self, group='asdf_extensions'):
        for entry_point in iter_entry_points(group=group):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter('always', category=AsdfDeprecationWarning)
                ext = entry_point.load()
            if not issubclass(ext, AsdfExtension):
                warnings.warn("Found entry point {}, from {} but it is not a "
                              "subclass of AsdfExtension, as expected. It is "
                              "being ignored.".format(ext, entry_point.dist),
                              AsdfWarning)
                continue

            dist = entry_point.dist
            name = get_class_name(ext, instance=False)
            self._package_metadata[name] = (dist.project_name, dist.version)
            self._extensions.append(ext())

            for warning in w:
                warnings.warn('{} (from {})'.format(warning.message, name),
                              AsdfDeprecationWarning)

    @property
    def extensions(self):
        # This helps avoid a circular dependency with external packages
        if not self._extensions:
            # If this environment variable is defined, load the default
            # extension. This allows the package to be tested without being
            # installed (e.g. for builds on Debian).
            if os.environ.get(ASDF_TEST_BUILD_ENV):
                # Fake the extension metadata
                name = get_class_name(BuiltinExtension, instance=False)
                self._package_metadata[name] = ('asdf', asdf_version)
                self._extensions.append(BuiltinExtension())

            self._load_installed_extensions()

        return self._extensions

    @property
    def extension_list(self):
        if self._extension_list is None:
            self._extension_list = AsdfExtensionList(self.extensions)

        return self._extension_list

    @property
    def package_metadata(self):
        return self._package_metadata

    def reset(self):
        """This will be used primarily for testing purposes."""
        self._extensions = []
        self._extension_list = None
        self._package_metadata = {}

    @property
    def resolver(self):
        return self.extension_list.resolver


default_extensions = _DefaultExtensions()


def get_default_resolver():
    """
    Get the resolver that includes mappings from all installed extensions.
    """
    return default_extensions.resolver
