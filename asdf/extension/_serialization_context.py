class SerializationContext:
    """
    Container for the current (de)serialization context.
    """
    def __init__(self, version, extension_manager):
        self._version = version
        self._extension_manager = extension_manager

        self._extensions_used = set()

    @property
    def version(self):
        """
        Get the ASDF Standard version.

        Returns
        -------
        str
        """
        return self._version

    @property
    def extension_manager(self):
        """
        Get the ExtensionManager instance.

        Returns
        -------
        asdf.extension.ExtensionManager
        """
        return self._extension_manager

    def mark_extension_used(self, extension):
        """
        Note that an extension was used when reading or writing the file.

        Parameters
        ----------
        extension : asdf.extension.Extension or asdf.extension.AsdfExtension
        """
        self._extensions_used.add(extension)

    @property
    def extensions_used(self):
        """
        Get the set of extensions that were used when reading or writing the file.

        Returns
        -------
        set of asdf.extension.Extension or asdf.extension.AsdfExtension
        """
        return self._extensions_used
