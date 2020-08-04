import abc
from collections import defaultdict

from packaging.specifiers import SpecifierSet

from ..util import get_class_name
from ._tag import TagDefinition
from ._legacy import AsdfExtension
from ._converter import ConverterProxy


class Extension(abc.ABC):
    """
    Abstract base class defining an extension to ASDF.

    Implementing classes must provide the `extension_uri`.
    Other properties are optional.
    """
    @classmethod
    def __subclasshook__(cls, C):
        if cls is Extension:
            return hasattr(C, "extension_uri")
        return NotImplemented # pragma: no cover

    @abc.abstractproperty
    def extension_uri(self):
        """
        Get this extension's identifying URI.

        Returns
        -------
        str
        """
        pass # pragma: no cover

    @property
    def converters(self):
        """
        Get the `asdf.extension.Converter` instances for tags
        and Python types supported by this extension.

        Returns
        -------
        iterable of asdf.extension.Converter
        """
        return []

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
    def tags(self):
        """
        Get the YAML tags supported by this extension.

        Returns
        -------
        iterable of str or asdf.extension.TagDefinition, or None
            If str, the tag URI.
            If None, use all tags supported by the converters.
        """
        return None

    @property
    def legacy_class_names(self):
        """
        Get the set of fully-qualified class names used by older
        versions of this extension.  This allows a new-style
        implementation of an extension to prevent warnings when a
        legacy extension is missing.

        Returns
        -------
        iterable of str
        """
        return set()


class ExtensionProxy(Extension, AsdfExtension):
    """
    Proxy that wraps an extension, provides default implementations
    of optional methods, and carries additional information on the
    package that provided the extension.
    """
    @classmethod
    def maybe_wrap(self, delegate):
        if isinstance(delegate, ExtensionProxy):
            return delegate
        else:
            return ExtensionProxy(delegate)

    def __init__(self, delegate, package_name=None, package_version=None):
        if not isinstance(delegate, (Extension, AsdfExtension)):
            raise TypeError(
                "Extension must implement the Extension or AsdfExtension interface"
            )

        self._delegate = delegate
        self._package_name = package_name
        self._package_version = package_version

        self._class_name = get_class_name(delegate)

        self._legacy = isinstance(delegate, AsdfExtension)

        # Sort these out up-front so that errors are raised when the extension is loaded
        # and not in the middle of the user's session.  The extension will fail to load
        # and a warning will be emitted, but it won't crash the program.
        self._converters = [ConverterProxy(c, self) for c in getattr(self._delegate, "converters", [])]

        value = getattr(self._delegate, "asdf_standard_requirement", None)
        if isinstance(value, str):
            self._asdf_standard_requirement = SpecifierSet(value)
        elif value is None:
            self._asdf_standard_requirement = SpecifierSet()
        else:
            raise TypeError("Extension property 'asdf_standard_requirement' must be str or None")

        self._tags = []
        extension_tags = getattr(self._delegate, "tags", None)
        if extension_tags is None:
            for converter in self._converters:
                self._tags.extend(converter.tags)
        else:
            converter_tags_by_uri = {t.tag_uri: t for c in self._converters for t in c.tags}
            for tag in extension_tags:
                if isinstance(tag, str):
                    converter_tag = converter_tags_by_uri.get(tag)
                    if converter_tag is not None:
                        self._tags.append(converter_tag)
                elif isinstance(tag, TagDefinition):
                    if tag.tag_uri in converter_tags_by_uri:
                        self._tags.append(tag)
                else:
                    raise TypeError("Extension property 'tags' must contain str or asdf.extension.TagDefinition values")

        self._legacy_class_names = set()
        for class_name in getattr(self._delegate, "legacy_class_names", []):
            if isinstance(class_name, str):
                self._legacy_class_names.add(class_name)
            else:
                raise TypeError("Extension property 'legacy_class_names' must contain str values")

    @property
    def extension_uri(self):
        """
        Get the extension's identifying URI.

        Returns
        -------
        str or None
        """
        return getattr(self._delegate, "extension_uri", None)

    @property
    def converters(self):
        """
        Get the extension's converters.

        Returns
        -------
        list of asdf.extension.Converter
        """
        return self._converters

    @property
    def asdf_standard_requirement(self):
        """
        Get the extension's ASDF Standard requirement.

        Returns
        -------
        packaging.specifiers.SpecifierSet
        """
        return self._asdf_standard_requirement

    @property
    def tags(self):
        """
        Get the YAML tags supported by this extension.

        Returns
        -------
        list of asdf.extension.TagDefinition
        """
        return self._tags

    @property
    def legacy_class_names(self):
        """
        Get this extension's legacy class names.

        Returns
        -------
        set of str
        """
        return self._legacy_class_names

    @property
    def types(self):
        """
        Get the legacy extension's ExtensionType subclasses.

        Returns
        -------
        iterable of asdf.type.ExtensionType
        """
        return getattr(self._delegate, "types", [])

    @property
    def tag_mapping(self):
        """
        Get the legacy extension's tag-to-schema-URI mapping.

        Returns
        -------
        iterable of tuple or callable
        """
        return getattr(self._delegate, "tag_mapping", [])

    @property
    def url_mapping(self):
        """
        Get the legacy extension's schema-URI-to-URL mapping.

        Returns
        -------
        iterable of tuple or callable
        """
        return getattr(self._delegate, "url_mapping", [])

    @property
    def delegate(self):
        """
        Get the wrapped extension instance.

        Returns
        -------
        asdf.extension.Extension or asdf.extension.AsdfExtension
        """
        return self._delegate

    @property
    def package_name(self):
        """
        Get the name of the Python package that provided this extension.

        Returns
        -------
        str or None
            `None` if the extension was added at runtime.
        """
        return self._package_name

    @property
    def package_version(self):
        """
        Get the version of the Python package that provided the extension

        Returns
        -------
        str or None
            `None` if the extension was added at runtime.
        """
        return self._package_version

    @property
    def class_name(self):
        """
        Get the fully qualified class name of the extension.

        Returns
        -------
        str
        """
        return self._class_name

    @property
    def legacy(self):
        """
        Get the extension's legacy flag.  Subclasses of `asdf.extension.AsdfExtension`
        are marked `True`.

        Returns
        -------
        bool
        """
        return self._legacy

    def __eq__(self, other):
        if isinstance(other, ExtensionProxy):
            return other.delegate is self.delegate
        else:
            return False

    def __hash__(self):
        return hash(id(self.delegate))

    def __repr__(self):
        if self.package_name is None:
            package_description = "(none)"
        else:
            package_description = "{}=={}".format(self.package_name, self.package_version)

        return "<ExtensionProxy class: {} package: {} legacy: {}>".format(
            self.class_name,
            package_description,
            self.legacy,
        )


class ExtensionManager:
    """
    Wraps a list of extensions and indexes their converters
    by tag and by Python type.

    Parameters
    ----------
    extensions : iterable of asdf.extension.Extension
        List of enabled extensions to manage.  Extensions placed earlier
        in the list take precedence.
    """
    def __init__(self, extensions):
        self._extensions = [ExtensionProxy.maybe_wrap(e) for e in extensions]

        self._tag_defs_by_tag = {}
        self._converters_by_tag = {}
        # This dict has both str and type keys:
        self._converters_by_type = {}

        for extension in self._extensions:
            extension_tags = set()
            for tag_def in extension.tags:
                if tag_def.tag_uri not in self._tag_defs_by_tag:
                    self._tag_defs_by_tag[tag_def.tag_uri] = tag_def
                    extension_tags.add(tag_def.tag_uri)
            for converter in extension.converters:
                for tag_def in converter.tags:
                    # The converters may support multiple extension versions, so
                    # only map tags that are included in the extension's tag list.
                    if tag_def.tag_uri in extension_tags and tag_def.tag_uri not in self._converters_by_tag:
                        self._converters_by_tag[tag_def.tag_uri] = converter
                for typ in converter.types:
                    if isinstance(typ, str):
                        if typ not in self._converters_by_type:
                            self._converters_by_type[typ] = converter
                    else:
                        type_class_name = get_class_name(typ, instance=False)
                        if typ not in self._converters_by_type and type_class_name not in self._converters_by_type:
                            self._converters_by_type[typ] = converter
                            self._converters_by_type[type_class_name] = converter

    @property
    def extensions(self):
        """
        Get the list of extensions.

        Returns
        -------
        list of asdf.extension.Extension
        """
        return self._extensions

    def handles_tag(self, tag):
        """
        Return `True` if the specified tag is handled by a
        converter.

        Parameters
        ----------
        tag : str
            Tag URI.

        Returns
        -------
        bool
        """
        return tag in self._converters_by_tag

    def handles_type(self, typ):
        """
        Returns `True` if the specified Python type is handled
        by a converter.

        Parameters
        ----------
        typ : type

        Returns
        -------
        bool
        """
        return (
            typ in self._converters_by_type
            or get_class_name(typ, instance=False) in self._converters_by_type
        )

    def get_tag_definition(self, tag):
        """
        Get the tag definition for the specified tag.

        Parameters
        ----------
        tag : str
            Tag URI.

        Returns
        -------
        asdf.extension.TagDefinition

        Raises
        ------
        KeyError
            Unrecognized tag URI.
        """
        try:
            return self._tag_defs_by_tag[tag]
        except KeyError:
            raise KeyError(
                "No support available for YAML tag '{}'.  "
                "You may need to install a missing extension.".format(
                    tag
                )
            ) from None

    def get_converter_for_tag(self, tag):
        """
        Get the converter for the specified tag.

        Parameters
        ----------
        tag : str
            Tag URI.

        Returns
        -------
        asdf.extension.Converter

        Raises
        ------
        KeyError
            Unrecognized tag URI.
        """
        try:
            return self._converters_by_tag[tag]
        except KeyError:
            raise KeyError(
                "No support available for YAML tag '{}'.  "
                "You may need to install a missing extension.".format(
                    tag
                )
            ) from None

    def get_converter_for_type(self, typ):
        """
        Get the converter for the specified Python type.

        Parameters
        ----------
        typ : type

        Returns
        -------
        asdf.extension.AsdfConverter

        Raises
        ------
        KeyError
            Unrecognized type.
        """
        try:
            return self._converters_by_type[typ]
        except KeyError:
            class_name = get_class_name(typ, instance=False)
            try:
                return self._converters_by_type[class_name]
            except KeyError:
                raise KeyError(
                    "No support available for Python type '{}'.  "
                    "You may need to install or enable an extension.".format(
                        get_class_name(typ, instance=False)
                    )
                ) from None
