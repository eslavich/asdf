"""
Support for Converter, the new API for serializing custom
types.  Will eventually replace the `asdf.types` module.
"""
import abc
import collections
import warnings
from types import GeneratorType

from .. import tagged
from ..util import get_class_name
from ._tag_definition import TagDefinition


class Converter(abc.ABC):
    """
    Abstract base class for plugins that convert nodes from the
    parsed YAML tree into custom objects, and vice versa.

    Implementing classes must provide the `tags` and `types`
    properties and `to_yaml_tree` and `from_yaml_tree` methods.
    The `select_tag` method is optional.
    """
    @classmethod
    def __subclasshook__(cls, C):
        if cls is Converter:
            return (hasattr(C, "tags") and
                    hasattr(C, "types") and
                    hasattr(C, "to_yaml_tree") and
                    hasattr(C, "from_yaml_tree"))
        return NotImplemented

    @abc.abstractproperty
    def tags(self):
        """
        Get the YAML tags that this converter operates on.

        Returns
        -------
        iterable of str or asdf.extension.AsdfTagDefinition
            If str, the tag URI.
        """
        pass

    @abc.abstractproperty
    def types(self):
        """
        Get the Python types that this converter operates on.

        Returns
        -------
        iterable of str or type, or None
            If str, the fully qualified class name of the type.
            If None, use all types provided by the converters.
        """
        pass

    def select_tag(self, obj, tags, ctx):
        """
        Select the tag to use when converting an object to YAML.
        Typically only one tag will be active in a given context, but
        converters that map one type to many tags should provide logic
        to choose the appropriate tag.

        The default implementation of this method chooses the first
        active tag in the order specified by this converter's
        `tags` property.

        Parameters
        ----------
        obj : object
            Instance of the custom type being converted.  Guaranteed
            to be an instance of one of the types listed in the
            `types` property.
        tags : list of str
            List of active tags to choose from.  Guaranteed to be
            a subset of the tags listed in the `tags` property.
        ctx : asdf.SerializationContext
            Context of the current serialization request.

        Returns
        -------
        str
            The selected tag.  Must be one of the tags passed
            to this method in the `tags` parameter.
        """
        return tags[0]

    @abc.abstractmethod
    def to_yaml_tree(self, obj, tag, ctx):
        """
        Convert an object into a node suitable for YAML serialization.
        This method is not responsible for writing actual YAML; rather, it
        converts an instance of a custom type to a built-in Python object type
        (such as dict, list, str, or number), which can then be automatically
        serialized to YAML as needed.

        For container types returned by this method (dict or list),
        the children of the container should not themselves be converted.
        Any list elements or dict values will be converted by subsequent
        calls to to_yaml_tree implementations.

        The root node of the returned tree must be an instance of `dict`,
        `list`, or `str`.  Descendants of the root node may be any
        type supported by an enabled extension.

        Parameters
        ----------
        obj : object
            Instance of a custom type to be serialized.  Guaranteed to
            be an instance of one of the types listed in the `types`
            property.
        tag : str
            The tag identifying the YAML type that `obj` should be
            converted into.
        ctx : asdf.SerializationContext
            The context of the current serialization request.

        Returns
        -------
        dict or list or str
            The YAML node representation of the object.
        """
        pass

    @abc.abstractmethod
    def from_yaml_tree(self, node, tag, ctx):
        """
        Convert a YAML node into an instance of a custom type.

        For container types received by this method (dict or list),
        the children of the container will have already been converted
        by prior calls to from_yaml_tree implementations.

        Note on circular references: trees that reference themselves
        among their descendants must be handled with care.  Most
        implementations need not concern themselves with this case, but
        if the custom type supports circular references, then the
        implementation of this method will need to return a generator.
        Consult the documentation for more details.

        Parameters
        ----------
        tree : dict or list or str
            The YAML node to convert.
        tag : str
            The YAML tag of the object being converted.
        ctx : asdf.extension.SerializationContext
            The context of the current serialization request.

        Returns
        -------
        object
            An instance of one of the types listed in the `types` property,
            or a generator that yields such an instance.
        """
        pass


class ConverterProxy(AsdfConverter):
    """
    Proxy that wraps an `AsdfConverter` and provides default
    implementations of optional methods.
    """
    def __init__(self, delegate, extension=None):
        if not isinstance(delegate, AsdfConverter):
            raise TypeError("Converter must implement the asdf.extension.AsdfConverter interface")
        self._delegate = delegate
        self._extension = extension
        self._class_name = get_class_name(delegate)

        self._tags = None

    @property
    def tags(self):
        if self._tags is None:
            tags = []
            for tag in self._delegate.tags:
                if isinstance(tag, str):
                    tags.append(AsdfTagDefinition(tag))
                elif isinstance(tag, AsdfTagDefinition):
                    tags.append(tag)
                else:
                    raise TypeError("Converter tags values must be str or asdf.extension.AsdfTagDefinition")
            self._tags = tags
        return self._tags

    @property
    def types(self):
        return list(self._delegate.types)

    def select_tag(self, obj, tags, ctx):
        method = getattr(self._delegate, "select_tag", None)
        if method is None:
            return tags[0]
        else:
            return method(obj, tags, ctx)

    def to_yaml_tree(self, obj, tag, ctx):
        return self._delegate.to_yaml_tree(obj, tag, ctx)

    def from_yaml_tree(self, node, tag, ctx):
        return self._delegate.from_yaml_tree(node, tag, ctx)

    @property
    def delegate(self):
        return self._delegate

    @property
    def extension(self):
        return self._extension

    @property
    def class_name(self):
        return self._class_name

    def __repr__(self):
        return "<ConverterProxy class: {}>".format(
            self.class_name,
        )
