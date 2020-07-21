"""
Support for AsdfConverter, the new API for serializing custom
types.  Will eventually replace the `asdf.types` and
`asdf.type_index` modules.
"""
import abc
import collections
import warnings
from types import GeneratorType

from . import tagged


__all__ = []


class AsdfConverter(abc.ABC):
    """
    Abstract base class for plugins that convert nodes from the
    parsed YAML tree into custom objects, and vice versa.

    Implementing classes must provide the `tags` and `types`
    properties and `to_yaml_tree` and `from_yaml_tree` methods.
    """
    @classmethod
    def __subclasshook__(cls, C):
        if cls is AsdfConverter:
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
        iterable of str
        """
        pass

    @abc.abstractproperty
    def types(self):
        """
        Get the Python types that this converter operates on.

        Returns
        -------
        iterable of type
        """
        pass

    @abc.abstractmethod
    def to_yaml_tree(self, obj, tag_or_tags, ctx):
        """
        Convert an object into an object tree suitable for YAML serialization.
        This method is not responsible for writing actual YAML; rather, it
        converts an instance of a custom type to a tree of built-in Python types
        (such as dict, list, str, or number), which can then be automatically
        serialized to YAML as needed.

        For container types returned by this method (dict or list),
        the children of the container should not themselves be converted.
        Any list elements or dict values will be converted by subsequent
        calls to to_yaml_tree implementations.

        The root node of the returned tree must be an instance of `dict`,
        `list`, or `str`.  Descendants of the root node may be any
        type supported by YAML serialization.

        Parameters
        ----------
        obj : object
            Instance of a custom type to be serialized.  Guaranteed to
            be an instance of one of the types listed in the `types`
            property.
        tag_or_tags : str or set of str
            The tag identifying the YAML type that `obj` should be converted
            into.  If multiple tags listed in this converter's `tags` property
            are enabled, this value will be a set.
        ctx : asdf.AsdfFile
            The `asdf.AsdfFile` for which this object is being serialized.

        Returns
        -------
        dict or list or str
            The tree representation of the object. Implementations that
            wish to override the tag used to identify the object in YAML
            are free to instead return an instance of `asdf.tagged.TaggedDict`,
            `asdf.tagged.TaggedList`, or `asdf.tagged.TaggedString`.
        """
        pass

    @abc.abstractmethod
    def from_yaml_tree(self, tree, tag, ctx):
        """
        Convert a YAML subtree into an instance of a custom type.

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
            The YAML subtree to convert.  For the sake of performance, this
            object will actually be an instance of `asdf.tagged.TaggedDict`,
            `asdf.tagged.TaggedList`, or `asdf.tagged.TaggedString`.  These
            objects should behave identically to their built-in counterparts.
        tag : str
            The YAML type of the object being deserialized.
        ctx : asdf.AsdfFile, optional
            If the implementation of this method accepts a second argument,
            it will receive the `asdf.AsdfFile` associated with the tree.

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
    def __init__(self, delegate, extension):
        if not isinstance(delegate, AsdfConverter):
            raise TypeError("Expected AsdfConverter")
        self._delegate = delegate
        self._extension = extension

    @property
    def tags(self):
        return set(self._delegate.tags)

    @property
    def types(self):
        return set(self._delegate.types)

    def to_yaml_tree(self, obj, tag_or_tags, ctx):
        return self._delegate.to_yaml_tree(obj, tag_or_tags, ctx)

    def from_yaml_tree(self, node, tag, ctx):
        return self._delegate.from_yaml_tree(node, tag, ctx)

    @property
    def delegate(self):
        return self._delegate

    @property
    def extension(self):
        return self._extension

    def __repr__(self):
        return "ConverterProxy({!r}, {!r})".format(
            self.delegate,
            self.extension,
        )
