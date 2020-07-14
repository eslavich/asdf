"""
Support for AsdfConverter, the new API for serializing custom
types.  Will eventually replace the `asdf.types` and
`asdf.type_index` modules.
"""
import abc
import collections
import warnings


__all__ = []


class AsdfConverter(abc.ABC):
    """
    Abstract base class for plugins that convert nodes from the
    parsed YAML tree into custom objects, and vice versa.

    Implementing classes must provide the `tag` and `types`
    properties and `to_yaml_tree` and `from_yaml_tree` methods.
    Other properties are optional.
    """
    @classmethod
    def __subclasshook__(cls, C):
        if cls is AsdfConverter:
            return (hasattr(C, "tag") and
                    hasattr(C, "types") and
                    hasattr(C, "to_yaml_tree") and
                    hasattr(C, "from_yaml_tree"))
        return NotImplemented

    @abc.abstractproperty
    def tag(self):
        """
        Get the YAML tag that this converter operates on.

        Returns
        -------
        str
            YAML tag URI.
        """
        pass

    @abc.abstractproperty
    def types(self):
        """
        Get the list of types that this converter supports.

        Returns
        -------
        list of type
        """
        pass

    @abc.abstractmethod
    def to_yaml_tree(self, obj):
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
        ctx : asdf.AsdfFile, optional
            If the implementation of this method accepts a second argument,
            it will receive the `asdf.AsdfFile` associated with obj.

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
    def from_yaml_tree(self, tree):
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

    @property
    def schema_uri(self):
        """
        Get the URI of the schema that validates this converter's
        tagged object.

        Returns
        -------
        str or None
            Schema URI, or `None` if no such schema exists.
        """
        return None

    @property
    def schema(self):
        """
        Get additional schema content that further validates
        this converter's tagged object.

        Returns
        -------
        str or bytes or dict or None
            Schema content as a YAML string or bytes, a dict,
            or `None` to skip additional validation.
        """
        return None

    @property
    def validators(self):
        """
        Get the `dict` of custom jsonschema validators that are to
        be used with this object's schema.  The keys are schema property
        names and the values are methods that accept four arguments:
        the jsonschema validator object, the value of the schema property,
        the object to be validated, and the full schema object.  Validator
        methods are expected to raise `asdf.ValidationError` on validation
        failure.

        Returns
        -------
        dict
        """
        return None


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
    def tag(self):
        return self._delegate.tag

    @property
    def types(self):
        return self._delegate.types

    @property
    def to_yaml_tree(self, obj, ctx):
        if self._delegate.to_yaml_tree.__code__.co_argcount > 1:
            return self._delegate.to_yaml_tree(obj, ctx)
        else:
            return self._delegate.to_yaml_tree(obj)

    @property
    def from_yaml_tree(self, node, ctx):
        if self._delegate.from_yaml_tree.__code__.co_argcount > 1:
            return self._delegate.from_yaml_tree(node, ctx)
        else:
            return self._delegate.to_yaml_tree(node)

    @property
    def schema_uri(self):
        return getattr(self._delegate, "schema_uri", None)

    @property
    def schema(self):
        return getattr(self._delegate, "schema", None)

    @property
    def validators(self):
        result = getattr(self._delegate, "validators", {})
        if result is None:
            return {}
        else:
            return result

    @property
    def delegate(self):
        return self._delegate

    @property
    def extension(self):
        return self._extension

    @property
    def fully_qualified_class_name(self):
        delegate = self._delegate
        return delegate.__class__.__module__ + "." + delegate.__class__.__qualname__

    # TODO: __repr__


class ConverterManager:
    def __init__(self, extensions):
        self._converters_by_tag = collections.defaultdict(list)
        self._converters_by_type = collections.defaultdict(list)
        self._warned_types = set()
        self._warned_tags = set()

        for extension in extensions:
            for converter in extension.converters:
                self._converters_by_tag[converter.tag].append(converter)
                for typ in converter.types:
                    self._converters_by_type[typ].append(converter)

    def tag_supported(self, tag):
        return tag in self._converters_by_tag

    def type_supported(self, typ):
        return typ in self._converters_by_type

    def from_tag(self, tag):
        converters = self._converters_by_tag[tag]
        if len(converters) == 0:
            raise ValueError("No enabled extension supports tag '{}'".format(tag))
        elif len(converters) > 1:
            if tag not in self._warned_tags:
                warnings.warn(
                    "Multiple enabled extensions claim tag '{}': \n\n"
                    "{}\n\n"
                    "Choosing the converter provided by {}.".format(
                        tag.__name__,
                        "\n".join(c.extension.fully_qualified_class_name for c in converters),
                        converters[-1].extension.fully_qualified_class_name
                    )
                )
                self._warned_tags.add(tag)
        else:
            return converters[0]

    def from_type(self, typ):
        converters = self._converters_by_type[typ]
        if len(converters) == 0:
            raise ValueError("No enabled extension supports type {}".format(typ.__name__))
        elif len(converters) > 1:
            if typ not in self._warned_types:
                warnings.warn(
                    "Multiple enabled extensions claim type {}: \n\n"
                    "{}\n\n"
                    "Choosing the converter provided by {}.".format(
                        typ.__name__,
                        "\n".join(c.extension.fully_qualified_class_name for c in converters),
                        converters[-1].extension.fully_qualified_class_name
                    )
                )
                self._warned_types.add(typ)

        return converters[-1]
