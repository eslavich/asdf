import os
import abc
import warnings
from pkg_resources import iter_entry_points
from collections import defaultdict
from types import GeneratorType
from setuptools.extern.packaging.specifiers import SpecifierSet

import yaml

from . import tagged
from . import types
from . import resolver
from .tags.core import ExtensionMetadata, Software
from .util import get_class_name
from .type_index import AsdfTypeIndex
from .version import version as asdf_version
from .exceptions import AsdfDeprecationWarning, AsdfWarning
from ._converter import ConverterProxy
from ._helpers import validate_asdf_standard_version


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
    def asdf_standard_requirement(self):
        """
        Get the ASDF Standard version requirement for this extension.

        Returns
        -------
        str or None
            If str, PEP 440 version specifier.
            If None, support all versions.
        """
        return None

    @property
    def default_enabled(self):
        """
        Return `True` if this extension should be enabled by default
        for new files (that meet the ASDF Standard requirement).
        Typically extension packages will enable only the latest version
        of an extension as default.  Users can reconfigure default
        extensions globally or on an individual file basis.

        This flag does not automatically enable the extension when
        reading existing files.  Instead, enabled extensions will
        be selected based on file metadata.

        Returns
        -------
        bool
        """
        return False

    @property
    def always_enabled(self):
        """
        Return `True` if this extension should always be enabled
        when reading and writing files (that meet the ASDF Standard
        requirement).  Use judiciously, as users will only be able
        to disable the extension by uninstalling its associated package.

        This feature is intended to allow convenient reading of
        older files that did not list extension URIs in their metadata.

        Returns
        -------
        bool
        """
        return False

    @property
    def tags(self):
        """
        Get the tags supported by this extension.

        Returns
        -------
        iterable of str or AsdfTagDescription, or None
            If str, the tag URI value.
            If None, use all tags provided by the converters.
        """
        return None

    @property
    def converters(self):
        """
        Iterable of `AsdfConverter` instances that support tags
        provided by this extension.

        Returns
        -------
        iterable of asdf.AsdfConverter
        """
        return []

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


class ManifestExtension(AsdfExtension):
    def __init__(self, manifest, default_enabled=False, always_enabled=False, converters=None):
        self._manifest = manifest
        self._default_enabled = default_enabled
        self._always_enabled = always_enabled

        if converters is None:
            self._converters = []

    @property
    def extension_uri(self):
        return self._manifest["extension_uri"]

    @property
    def asdf_standard_requirement(self):
        version = self._manifest.get("asdf_standard_requirement", None)
        if version is None:
            return None
        elif isinstance(version, str):
            return "=={}".format(version)
        else:
            specifiers = []
            for prop, operator in [("gt", ">"), ("gte", ">="), ("lt", "<"), ("lte", "<=")]:
                value = version.get(prop)
                if value:
                    specifiers.append("{}{}".format(operator, value))
            return ",".join(specifiers)

    @property
    def default_enabled(self):
        return self._default_enabled

    @property
    def always_enabled(self):
        return self._always_enabled

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

    def __repr__(self):
        return "ManifestExtension(<{}>, default_enabled={!r}, always_enabled={!r}, converters=[...])".format(
            self.extension_uri,
            self.default_enabled,
            self.always_enabled,
        )


# TODO: add heavy-duty validation here
class ExtensionProxy(AsdfExtension):
    """
    Proxy that wraps an `AsdfExtension` and provides default
    implementations of optional methods.
    """
    @classmethod
    def maybe_wrap(self, delegate):
        if isinstance(delegate, ExtensionProxy):
            return delegate
        else:
            return ExtensionProxy(delegate)

    def __init__(self, delegate, package_name=None, package_version=None, legacy=False):
        if not isinstance(delegate, AsdfExtension):
            raise TypeError("Extension must implement the AsdfExtension interface")

        self._delegate = delegate
        self._package_name = package_name
        self._package_version = package_version
        self._legacy = legacy

    @property
    def extension_uri(self):
        return getattr(self._delegate, "extension_uri", None)

    @property
    def asdf_standard_requirement(self):
        version = getattr(self._delegate, "asdf_standard_requirement", None)
        if isinstance(version, str):
            return SpecifierSet(version)
        elif version is None:
            return SpecifierSet()
        else:
            raise TypeError("asdf_standard_requirement must be str or None")

    @property
    def default_enabled(self):
        return getattr(self._delegate, "default_enabled", False)

    @property
    def always_enabled(self):
        value = getattr(self._delegate, "always_enabled", None)
        if value is None:
            return self._legacy
        else:
            return value

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

        tags = getattr(self._delegate, "tags", None)
        if tags is None:
            for converter in self.converters:
                for tag in converter.tags:
                    result.append(AsdfTagDescription(tag))
        else:
            for tag in tags:
                if isinstance(tag, str):
                    result.append(AsdfTagDescription(tag))
                elif isinstance(tag, AsdfTagDescription):
                    result.append(tag)
                else:
                    raise TypeError("Extension tags values must be str or AsdfTagDescription")

        return result

    @property
    def delegate(self):
        return self._delegate

    @property
    def package_name(self):
        return self._package_name

    @property
    def package_version(self):
        return self._package_version

    @property
    def legacy(self):
        return self._legacy

    def get_metadata(self):
        return ExtensionMetadata(
            extension_class=get_class_name(self._delegate),
            software=Software(name=self.package_name, version=self.package_version),
            extension_uri=self.extension_uri
        )

    def __repr__(self):
        return "ExtensionProxy({!r}, package_name={!r}, package_version={!r}, legacy={!r})".format(
            self.delegate,
            self.package_name,
            self.package_version,
            self.legacy,
        )


class SerializationContext:
    def __init__(self):
        self._extensions_used = set()

    def mark_extension_used(self, extension):
        self._extensions_used.add(extension)

    @property
    def extensions_used(self):
        return self._extensions_used


class ExtensionManager:
    def __init__(self, extensions=None):
        self._reset()

        if extensions is not None:
            for extension in extensions:
                self.add_extension(extension)

    def _reset(self):
        self._extensions = []
        self._tag_descriptions_by_tag = defaultdict(list)
        self._converters_by_tag = defaultdict(list)
        self._converters_by_type = defaultdict(list)
        self._tags = set()
        self._types = set()
        self._extension_list = None

    def add_extension(self, extension):
        extension = ExtensionProxy.maybe_wrap(extension)

        if any(e for e in self._extensions if e.delegate is extension.delegate):
            # It's useful for this method to be idempotent.
            return

        self._extensions.append(extension)

        extension_tags = set()
        for tag_desc in extension.tag_descriptions:
            self._tag_descriptions_by_tag[tag_desc.tag_uri].append(tag_desc)
            extension_tags.add(tag_desc.tag_uri)

        extension_types = set()
        for converter in extension.converters:
            for tag in converter.tags:
                # The converters may support multiple extension versions, so
                # only map tags that are included in the extension's tag list.
                if tag in extension_tags:
                    self._converters_by_tag[tag].append(converter)
            for typ in converter.types:
                extension_types.add(typ)
                self._converters_by_type[typ].append(converter)

        self._tags.update(extension_tags)
        self._types.update(extension_types)
        self._extension_list = None

    def remove_extension(self, extension):
        extension = ExtensionProxy.maybe_wrap(extension)

        remaining_extensions = [e for e in self.extensions if e.delegate is not extension.delegate]
        self._reset()
        for ext in remaining_extensions:
            self.add_extension(ext)

    @property
    def extensions(self):
        return self._extensions

    @property
    def tags(self):
        return self._tags

    @property
    def types(self):
        return self._types

    @property
    def _extension_list(self):
        if self._extension_list is None:
            self._extension_list = AsdfExtensionList(self.extensions)
        return self._extension_list

    def get_tag_schema_uri(self, tag):
        tag_descriptions = self._tag_descriptions_by_tag.get(tag, [])
        if len(tag_descriptions) == 0:
            return None
        elif len(tag_descriptions) == 1:
            return tag_descriptions[0].schema_uri
        else:
            # TODO: warning
            return tag_descriptions[0].schema_uri

    def to_yaml_tree(self, obj, ctx):
        if type(obj) not in self._types:
            raise TypeError("Unhandled object type: {!r}".format(type(obj)))

        converter = self.get_converter_for_type(type(obj))

        tags = self.tags.intersection(converter.tags)
        if len(tags) == 1:
            tag_or_tags = iter(tags).next()
        else:
            tag_or_tags = tags

        node = converter.to_yaml_tree(obj, tag_or_tags, ctx)
        if isinstance(node, GeneratorType):
            generator = node
            node = next(generator)
        else:
            generator = None

        if not isinstance(node, tagged.Tagged):
            if len(tags) > 1:
                raise RuntimeError("Ambiguous tag for type {}".format(type(obj)))
            node = tagged.tag_object(tag_or_tags, node, ctx=ctx)

        ctx.mark_extension_used(converter.extension)

        yield node
        if generator is not None:
            yield from generator

    def from_yaml_tree(self, node, ctx):
        if node._tag not in self.tags:
            raise TypeError("Unhandled tag: {}".format(node._tag))

        converter = self.get_converter_for_tag(node._tag)
        result = converter.from_yaml_tree(node, node._tag, ctx)
        ctx.mark_extension_used(converter.extension)
        return result

    def get_converter_for_tag(self, tag):
        converters = self._converters_by_tag.get(tag, [])
        if len(converters) == 0:
            return None
        elif len(converters) == 1:
            return converters[0]
        else:
            # TODO: warning
            return converters[0]

    def get_converter_for_type(self, typ):
        converters = self._converters_by_type.get(typ, [])
        if len(converters) == 0:
            return None
        elif len(converters) == 1:
            return converters[0]
        else:
            # TODO: warning
            return converters[0]


class AsdfExtensionList:
    """
    Manage a set of extensions that are in effect.
    """
    def __init__(self, extensions):
        extensions = [ExtensionProxy.maybe_wrap(e) for e in extensions]

        tag_mapping = []
        url_mapping = []
        validators = {}
        self._type_index = AsdfTypeIndex()
        for extension in extensions:
            tag_mapping.extend(extension.tag_mapping)
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
    @property
    def extensions(self):
        from ._config import get_config
        return [e for e in get_config().extensions if e.legacy]

    @property
    def extension_list(self):
        return AsdfExtensionList(self.extensions)

    @property
    def resolver(self):
        return self.extension_list.resolver


# This is no longer used by AsdfFile, but it remains in case
# external users need it.
default_extensions = _DefaultExtensions()


def get_default_resolver():
    """
    Get the resolver that includes mappings from all installed extensions.
    """
    return default_extensions.resolver
