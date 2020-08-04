import pytest

from packaging.specifiers import SpecifierSet

from asdf.extension import (
    Extension,
    ExtensionProxy,
    TagDefinition,
    Converter,
    ConverterProxy,
    BuiltinExtension,
)
from asdf.types import CustomType

from asdf.tests.helpers import assert_extension_correctness


def test_builtin_extension():
    extension = BuiltinExtension()
    assert_extension_correctness(extension)


class LegacyType(dict, CustomType):
    organization = "somewhere.org"
    name = "test"
    version = "1.0.0"


class LegacyExtension:
    types = [LegacyType]
    tag_mapping = [("tag:somewhere.org/", "http://somewhere.org/{tag_suffix}")]
    url_mapping = [("http://somewhere.org/", "http://somewhere.org/{url_suffix}.yaml")]


class MinimumExtension:
    extension_uri = "asdf://somewhere.org/extensions/minimum-1.0"


class MinimumExtensionSubclassed(Extension):
    extension_uri = "asdf://somewhere.org/extensions/minimum-1.0"


class FullExtension:
    extension_uri = "asdf://somewhere.org/extensions/full-1.0"

    def __init__(
        self,
        converters=None,
        asdf_standard_requirement=None,
        tags=None,
        legacy_class_names=None,
    ):
        self._converters = [] if converters is None else converters
        self._asdf_standard_requirement = asdf_standard_requirement
        self._tags = tags
        self._legacy_class_names = [] if legacy_class_names is None else legacy_class_names

    @property
    def converters(self):
        return self._converters

    @property
    def asdf_standard_requirement(self):
        return self._asdf_standard_requirement

    @property
    def tags(self):
        return self._tags

    @property
    def legacy_class_names(self):
        return self._legacy_class_names


class MinimumConverter:
    def __init__(self, tags=None, types=None):
        if tags is None:
            self._tags = []
        else:
            self._tags = tags

        if types is None:
            self._types = []
        else:
            self._types = types

    @property
    def tags(self):
        return self._tags

    @property
    def types(self):
        return self._types

    def to_yaml_tree(self, obj, tag, ctx):
        return "to_yaml_tree result"

    def from_yaml_tree(self, obj, tag, ctx):
        return "from_yaml_tree result"


class FullConverter(MinimumConverter):
    def select_tag(self, obj, tags, ctx):
        return "select_tag result"


def test_extension_proxy_maybe_wrap():
    extension = MinimumExtension()
    proxy = ExtensionProxy.maybe_wrap(extension)
    assert proxy.delegate is extension
    assert ExtensionProxy.maybe_wrap(proxy) is proxy

    with pytest.raises(TypeError):
        ExtensionProxy.maybe_wrap(object())


def test_extension_proxy():
    # Test with minimum properties:
    extension = MinimumExtension()
    proxy = ExtensionProxy(extension)

    assert proxy.extension_uri == "asdf://somewhere.org/extensions/minimum-1.0"
    assert proxy.converters == []
    assert proxy.asdf_standard_requirement == SpecifierSet()
    assert proxy.tags == []
    assert proxy.legacy_class_names == set()
    assert proxy.types == []
    assert proxy.tag_mapping == []
    assert proxy.url_mapping == []
    assert proxy.delegate is extension
    assert proxy.legacy is False
    assert proxy.package_name is None
    assert proxy.package_version is None
    assert proxy.class_name == "asdf.tests.test_extension.MinimumExtension"

    # The subclassed version should have the same defaults:
    extension = MinimumExtensionSubclassed()
    subclassed_proxy = ExtensionProxy(extension)
    assert subclassed_proxy.extension_uri == proxy.extension_uri
    assert subclassed_proxy.converters == proxy.converters
    assert subclassed_proxy.asdf_standard_requirement == proxy.asdf_standard_requirement
    assert subclassed_proxy.tags == proxy.tags
    assert subclassed_proxy.legacy_class_names == proxy.legacy_class_names
    assert subclassed_proxy.types == proxy.types
    assert subclassed_proxy.tag_mapping == proxy.tag_mapping
    assert subclassed_proxy.url_mapping == proxy.url_mapping
    assert subclassed_proxy.delegate is extension
    assert subclassed_proxy.legacy == proxy.legacy
    assert subclassed_proxy.package_name == proxy.package_name
    assert subclassed_proxy.package_version == proxy.package_name
    assert subclassed_proxy.class_name == "asdf.tests.test_extension.MinimumExtensionSubclassed"

    # Test with all properties present:
    converters = [
        MinimumConverter(
            tags=["asdf://somewhere.org/extensions/full/tags/foo-1.0"],
            types=[]
        )
    ]
    extension = FullExtension(
        converters=converters,
        asdf_standard_requirement=">=1.4.0",
        tags=["asdf://somewhere.org/extensions/full/tags/foo-1.0"],
        legacy_class_names=["foo.extensions.SomeOldExtensionClass"]
    )
    proxy = ExtensionProxy(extension, package_name="foo", package_version="1.2.3")

    assert proxy.extension_uri == "asdf://somewhere.org/extensions/full-1.0"
    assert proxy.converters == [ConverterProxy(c, proxy) for c in converters]
    assert proxy.asdf_standard_requirement == SpecifierSet(">=1.4.0")
    assert len(proxy.tags) == 1
    assert proxy.tags[0].tag_uri == "asdf://somewhere.org/extensions/full/tags/foo-1.0"
    assert proxy.legacy_class_names == {"foo.extensions.SomeOldExtensionClass"}
    assert proxy.types == []
    assert proxy.tag_mapping == []
    assert proxy.url_mapping == []
    assert proxy.delegate is extension
    assert proxy.legacy is False
    assert proxy.package_name == "foo"
    assert proxy.package_version == "1.2.3"
    assert proxy.class_name == "asdf.tests.test_extension.FullExtension"

    # Should fail when the input is not one of the two extension interfaces:
    with pytest.raises(TypeError):
        ExtensionProxy(object)

    # Should fail with a bad converter:
    with pytest.raises(TypeError):
        ExtensionProxy(FullExtension(converters=[object()]))

    # Unparseable ASDF Standard requirement:
    with pytest.raises(ValueError):
        ExtensionProxy(FullExtension(asdf_standard_requirement="asdf-standard >= 1.4.0"))

    # Unrecognized ASDF Standard requirement type:
    with pytest.raises(TypeError):
        ExtensionProxy(FullExtension(asdf_standard_requirement=object()))

    # Bad tag:
    with pytest.raises(TypeError):
        ExtensionProxy(FullExtension(tags=[object()]))

    # Bad legacy class names:
    with pytest.raises(TypeError):
        ExtensionProxy(FullExtension(legacy_class_names=[object]))


def test_extension_proxy_tags():
    """
    The tags behavior is a tad complex, so they get their own test.
    """
    tag_uri = "asdf://somewhere.org/extensions/full/tags/foo-1.0"
    tag_def = TagDefinition(
        tag_uri,
        schema_uri="asdf://somewhere.org/extensions/full/schemas/foo-1.0",
        title="Some tag title",
        description="Some tag description"
    )

    # Converter has tag but extension has none.
    # Should return the tag from the converter.
    converter = FullConverter(tags=[tag_def])
    extension = FullExtension(tags=None, converters=[converter])
    proxy = ExtensionProxy(extension)
    assert proxy.tags == [tag_def]

    # Both extension and converter have tags.
    # Should return a single tag.
    converter = FullConverter(tags=[tag_def])
    extension = FullExtension(tags=[tag_def], converters=[converter])
    proxy = ExtensionProxy(extension)
    assert proxy.tags == [tag_def]

    # Extension lists tag that converter is missing.
    # Should not return the tag, since it isn't supported.
    converter = FullConverter(tags=[])
    extension = FullExtension(tags=[tag_def], converters=[converter])
    proxy = ExtensionProxy(extension)
    assert proxy.tags == []

    # Extension tag is only a string.  Should return the
    # converter's more comprehensive tag definition.
    converter = FullConverter(tags=[tag_def])
    extension = FullExtension(tags=[tag_uri], converters=[converter])
    proxy = ExtensionProxy(extension)
    assert proxy.tags == [tag_def]

    # Converter tag is only a string.  Should return the
    # extension's more comprehensive tag definition.
    converter = FullConverter(tags=[tag_uri])
    extension = FullExtension(tags=[tag_def], converters=[converter])
    proxy = ExtensionProxy(extension)
    assert proxy.tags == [tag_def]

    # Both converter and extension tags are strings.  Should
    # create a TagDefinition.
    converter = FullConverter(tags=[tag_uri])
    extension = FullExtension(tags=[tag_uri], converters=[converter])
    proxy = ExtensionProxy(extension)
    assert len(proxy.tags) == 1
    assert proxy.tags[0].tag_uri == tag_uri


def test_extension_proxy_legacy():
    extension = LegacyExtension()
    proxy = ExtensionProxy(extension, package_name="foo", package_version="1.2.3")

    assert proxy.extension_uri is None
    assert proxy.converters == []
    assert proxy.asdf_standard_requirement == SpecifierSet()
    assert proxy.tags == []
    assert proxy.legacy_class_names == set()
    assert proxy.types == [LegacyType]
    assert proxy.tag_mapping == LegacyExtension.tag_mapping
    assert proxy.url_mapping == LegacyExtension.url_mapping
    assert proxy.delegate is extension
    assert proxy.legacy is True
    assert proxy.package_name == "foo"
    assert proxy.package_version == "1.2.3"
    assert proxy.class_name == "asdf.tests.test_extension.LegacyExtension"


def test_extension_proxy_hash_and_eq():
    extension = MinimumExtension()
    proxy1 = ExtensionProxy(extension)
    proxy2 = ExtensionProxy(extension, package_name="foo", package_version="1.2.3")

    assert proxy1 == proxy2
    assert hash(proxy1) == hash(proxy2)
    assert proxy1 != extension
    assert proxy2 != extension


def test_extension_proxy_repr():
    proxy = ExtensionProxy(MinimumExtension(), package_name="foo", package_version="1.2.3")
    assert "class: asdf.tests.test_extension.MinimumExtension" in repr(proxy)
    assert "package: foo==1.2.3" in repr(proxy)
    assert "legacy: False" in repr(proxy)

    proxy = ExtensionProxy(MinimumExtension())
    assert "class: asdf.tests.test_extension.MinimumExtension" in repr(proxy)
    assert "package: (none)" in repr(proxy)
    assert "legacy: False" in repr(proxy)

    proxy = ExtensionProxy(LegacyExtension(), package_name="foo", package_version="1.2.3")
    assert "class: asdf.tests.test_extension.LegacyExtension" in repr(proxy)
    assert "package: foo==1.2.3" in repr(proxy)
    assert "legacy: True" in repr(proxy)


def test_tag_definition():
    tag_def = TagDefinition(
        "asdf://somewhere.org/extensions/foo/tags/foo-1.0",
        schema_uri="asdf://somewhere.org/extensions/foo/schemas/foo-1.0",
        title="Some title",
        description="Some description",
    )

    assert tag_def.tag_uri == "asdf://somewhere.org/extensions/foo/tags/foo-1.0"
    assert tag_def.schema_uri == "asdf://somewhere.org/extensions/foo/schemas/foo-1.0"
    assert tag_def.title == "Some title"
    assert tag_def.description == "Some description"


def test_converter():
    class ConverterNoSubclass:
        tags = []
        types = []

        def to_yaml_tree(self, *args):
            pass

        def from_yaml_tree(self, *args):
            pass

    assert issubclass(ConverterNoSubclass, Converter)

    class ConverterWithSubclass(Converter):
        tags = []
        types = []

        def to_yaml_tree(self, *args):
            pass

        def from_yaml_tree(self, *args):
            pass

    # Confirm the behavior of the default select_tag implementation
    assert ConverterWithSubclass().select_tag(object(), ["tag1", "tag2"], object()) == "tag1"


def test_converter_proxy():
    # Test the minimum set of converter methods:
    extension = ExtensionProxy(MinimumExtension())
    converter = MinimumConverter()
    proxy = ConverterProxy(converter, extension)
    assert proxy.tags == []
    assert proxy.types == []
    assert proxy.to_yaml_tree(None, None, None) == "to_yaml_tree result"
    assert proxy.from_yaml_tree(None, None, None) == "from_yaml_tree result"
    assert proxy.select_tag(None, ["tag1", "tag2"], None) == "tag1"
    assert proxy.delegate is converter
    assert proxy.extension == extension
    assert proxy.package_name is None
    assert proxy.package_version is None
    assert proxy.class_name == "asdf.tests.test_extension.MinimumConverter"

    # Check the __eq__ and __hash__ behavior:
    assert proxy == ConverterProxy(converter, extension)
    assert proxy != ConverterProxy(MinimumConverter(), extension)
    assert proxy != ConverterProxy(converter, MinimumExtension())
    assert proxy in {ConverterProxy(converter, extension)}
    assert proxy not in {
        ConverterProxy(MinimumConverter(), extension),
        ConverterProxy(converter, MinimumExtension())
    }

    # Check the __repr__:
    assert "class: asdf.tests.test_extension.MinimumConverter" in repr(proxy)
    assert "package: (none)" in repr(proxy)

    # Test the full set of converter methods:
    class Foo:
        pass

    class Bar:
        pass

    converter = FullConverter(
        tags=[
            "asdf://somewhere.org/extensions/test/tags/foo-1.0",
            TagDefinition(
                "asdf://somewhere.org/extensions/test/tags/bar-1.0",
                schema_uri="asdf://somewhere.org/extensions/test/schemas/bar-1.0",
                title="Some tag title",
                description="Some tag description"
            ),
        ],
        types=[Foo, Bar]
    )

    extension = ExtensionProxy(MinimumExtension(), package_name="foo", package_version="1.2.3")
    proxy = ConverterProxy(converter, extension)
    assert proxy.tags[0].tag_uri == "asdf://somewhere.org/extensions/test/tags/foo-1.0"
    assert proxy.tags[0].schema_uri is None
    assert proxy.tags[0].title is None
    assert proxy.tags[0].description is None
    assert proxy.tags[1].tag_uri == "asdf://somewhere.org/extensions/test/tags/bar-1.0"
    assert proxy.tags[1].schema_uri == "asdf://somewhere.org/extensions/test/schemas/bar-1.0"
    assert proxy.tags[1].title == "Some tag title"
    assert proxy.tags[1].description == "Some tag description"
    assert proxy.types == [Foo, Bar]
    assert proxy.to_yaml_tree(None, None, None) == "to_yaml_tree result"
    assert proxy.from_yaml_tree(None, None, None) == "from_yaml_tree result"
    assert proxy.select_tag(None, ["tag1", "tag2"], None) == "select_tag result"
    assert proxy.delegate is converter
    assert proxy.extension == extension
    assert proxy.package_name == "foo"
    assert proxy.package_version == "1.2.3"
    assert proxy.class_name == "asdf.tests.test_extension.FullConverter"

    # Check the __repr__ since it will contain package info now:
    assert "class: asdf.tests.test_extension.FullConverter" in repr(proxy)
    assert "package: foo==1.2.3" in repr(proxy)

    # Should error because object() does fulfill the Converter interface:
    with pytest.raises(TypeError):
        ConverterProxy(object(), extension)

    # Should fail because tags must be str or TagDescription:
    with pytest.raises(TypeError):
        ConverterProxy(MinimumConverter(tags=[object()]), extension)

    # Should fail because types must instances of type:
    with pytest.raises(TypeError):
        ConverterProxy(MinimumConverter(types=[object()]), extension)
