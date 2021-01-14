"""
Contains commands for lightweight text editing of an ASDF file.
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import yaml

from .. import constants
from .. import generic_io
from .. import schema
from .. import util

from ..asdf import is_asdf_file, open_asdf, AsdfFile
from ..block import BlockManager
from .main import Command


__all__ = ["edit"]


if sys.platform.startswith("win"):
    DEFAULT_EDITOR = "notepad"
else:
    DEFAULT_EDITOR = "vi"


class Edit(Command):
    @classmethod
    def setup_arguments(cls, subparsers):
        """
        Set up a command line argument parser for the edit subcommand.
        """
        # Set up the parser
        parser = subparsers.add_parser(
            "edit",
            description="Edit the YAML portion of an ASDF file in-place.",
        )

        # Need an input file
        parser.add_argument(
            "filename",
            help="Path to an ASDF file.",
        )

        parser.set_defaults(func=cls.run)

        return parser

    @classmethod
    def run(cls, args):
        """
        Execute the edit subcommand.
        """
        return edit(args.filename)


def read_yaml(fd):
    """
    Read the YAML portion of an open ASDF file's content.

    Parameters
    ----------
    fd : GenericFile

    Returns
    -------
    bytes
        YAML content
    int
        total number of bytes available for YAML area
    bool
        True if the file contains binary blocks
    """
    # All ASDF files produced by this library, even the binary files
    # of an exploded ASDF file, include a YAML header, so we'll just
    # let this raise an error if the end marker can't be found.
    # Revisit this if someone starts producing files without a
    # YAML section, which the standard permits but is not possible
    # with current software.
    reader = fd.reader_until(
        constants.YAML_END_MARKER_REGEX,
        7,
        "End of YAML marker",
        include=True,
    )
    content = reader.read()

    reader = fd.reader_until(
        constants.BLOCK_MAGIC,
        len(constants.BLOCK_MAGIC),
        include=False,
        exception=False,
    )
    buffer = reader.read()

    contains_blocks = fd._peek(len(constants.BLOCK_MAGIC)) == constants.BLOCK_MAGIC

    return content, len(content) + len(buffer), contains_blocks


def write_edited_yaml_larger(path, new_content, version):
    """
    Rewrite an ASDF file, replacing the YAML portion with the
    specified YAML content and updating the block index if present.
    The file is assumed to contain binary blocks.

    Parameters
    ----------
    path : str
        Path to ASDF file
    content : bytes
        Updated YAML content
    """
    prefix = os.path.splitext(os.path.basename(path))[0] + "-"
    # Since the original file may be large, create the temporary
    # file in the same directory to avoid filling up the system
    # temporary area.
    with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), prefix=prefix, suffix=".asdf") as temp_file:
        with generic_io.get_file(temp_file, mode="w") as fd:
            fd.write(new_content)
            # Allocate additional space for future YAML updates:
            pad_length = util.calculate_padding(len(new_content), True, fd.block_size)
            fd.fast_forward(pad_length)

            with generic_io.get_file(path) as original_fd:
                # Consume the file up to the first block, which must exist
                # as a precondition to using this method.
                original_fd.seek_until(
                    constants.BLOCK_MAGIC,
                    len(constants.BLOCK_MAGIC),
                )
                ctx = AsdfFile(version=version)
                blocks = BlockManager(ctx)
                blocks.read_internal_blocks(original_fd, past_magic=True, validate_checksums=False)
                blocks.write_internal_blocks_serial(fd)
                blocks.write_block_index(fd, ctx)

        # Swap in the new version of the file atomically:
        shutil.copy(temp_file.name, path)


def write_edited_yaml(path, new_content, available_bytes):
    """
    Overwrite the YAML portion of an ASDF tree with the specified
    YAML content.  The content must fit in the space available.

    Parameters
    ----------
    path : str
        Path to ASDF file
    yaml_content : bytes
        Updated YAML content
    available_bytes : int
        Number of bytes available for YAML
    """
    # generic_io mode "rw" opens the file as "r+b":
    with generic_io.get_file(path, mode="rw") as fd:
        fd.write(new_content)

        pad_length = available_bytes - len(new_content)
        if pad_length > 0:
            fd.write(b"\0" * pad_length)


def edit(path):
    """
    Copy the YAML portion of an ASDF file to a temporary file, present
    the file to the user for editing, then update the original file
    with the modified YAML.

    Parameters
    ----------
    path : str
        Path to ASDF file
    """
    # Extract the YAML portion of the original file:
    with generic_io.get_file(path, mode="r") as fd:
        if not is_asdf_file(path):
            print(f"Error: '{path}' is not an ASDF file.")
            return 1

        original_content, available_bytes, contains_blocks = read_yaml(fd)

    original_version = parse_version(original_content)

    prefix = os.path.splitext(os.path.basename(path))[0] + "-"
    with tempfile.NamedTemporaryFile(prefix=prefix, suffix=".yaml") as temp_file:
        # Write the YAML to a temporary path:
        temp_file.write(original_content)
        temp_file.flush()

        # Loop so that the user can correct errors in the edited file:
        while True:
            open_editor(temp_file.name)

            temp_file.seek(0)
            new_content = temp_file.read()

            if new_content == original_content:
                print("No changes made to file")
                return 0

            new_version = parse_version(new_content)
            if new_version != original_version:
                print("Error: cannot modify ASDF Standard version using this tool.")
                choice = request_input("(c)ontinue editing or (a)bort? ", ["c", "a"])
                if choice == "a":
                    return 1
                else:
                    continue

            try:
                # Blocks are not read during validation, so this will not raise
                # an error even though we're only opening the YAML portion of
                # the file.
                with open_asdf(io.BytesIO(new_content), _force_raw_types=True):
                    pass
            except yaml.YAMLError as e:
                print("Error: failed to parse updated YAML:")
                print_exception(e)
                choice = request_input("(c)ontinue editing or (a)bort? ", ["c", "a"])
                if choice == "a":
                    return 1
                else:
                    continue
            except schema.ValidationError as e:
                print("Warning: updated ASDF tree failed validation:")
                print_exception(e)
                choice = request_input("(c)ontinue editing, (f)orce update, or (a)bort? ", ["c", "f", "a"])
                if choice == "a":
                    return 1
                elif choice == "c":
                    continue
            except Exception as e:
                print("Error: failed to read updated file as ASDF:")
                print_exception(e)
                choice = request_input("(c)ontinue editing or (a)bort? ", ["c", "a"])
                if choice == "a":
                    return 1
                else:
                    continue

            # We've either opened the file without error, or
            # the user has agreed to ignore validation errors.
            # Break out of the loop so that we can update the
            # original file.
            break

    if len(new_content) <= available_bytes:
        # File has sufficient space allocated in the YAML area.
        write_edited_yaml(path, new_content, available_bytes)
    elif not contains_blocks:
        # File does not have sufficient space, but there are
        # no binary blocks, so we can just expand the file.
        write_edited_yaml(path, new_content, len(new_content))
    else:
        # File does not have sufficient space, and binary blocks
        # are present.
        print("Warning: updated YAML larger than allocated space.  File must be rewritten.")
        choice = request_input("(c)ontinue or (a)bort? ", ["c", "a"])
        if choice == "a":
            return 1
        else:
            write_edited_yaml_larger(path, new_content, new_version)


def parse_version(content):
    """
    Extract the ASDF Standard version from YAML content.

    Parameters
    ----------
    content : bytes

    Returns
    -------
    asdf.versioning.AsdfVersion
        ASDF Standard version
    """
    comments = AsdfFile._read_comment_section(generic_io.get_file(io.BytesIO(content)))
    return AsdfFile._find_asdf_version_in_comments(comments)


def print_exception(e):
    """
    Print an exception, indented 4 spaces and elided if too many lines.
    """
    lines = str(e).split("\n")
    if len(lines) > 20:
        lines = lines[0:20] + ["..."]
    for line in lines:
        print(f"    {line}")


def request_input(message, choices, default=None):
    """
    Request user input.

    Parameters
    ----------
    message : str
        Message to display
    choices : list of str
        List of recognized inputs
    default : str
        Default input
    """
    while True:
        choice = input(message).strip().lower()
        if choice == "" and default is not None:
            choice = default

        if choice in choices:
            return choice
        else:
            print(f"Invalid choice: {choice}")


def open_editor(path):
    """
    Launch an editor process with the file at path opened.
    """
    editor = os.environ.get("EDITOR", DEFAULT_EDITOR)
    subprocess.run(f"{editor} {path}", check=True, shell=True)
