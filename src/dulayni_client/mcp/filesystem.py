#!/usr/bin/env python3
"""
MCP Filesystem Server for dulayni-client
A Model Context Protocol server providing secure filesystem operations.
Integrated into the dulayni-client project.
"""

import os
import sys
import json
import asyncio
import shutil
import stat
import tempfile
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime
import fnmatch
import difflib
import base64
import mimetypes
from dataclasses import dataclass

from fastmcp import FastMCP
import aiofiles
import aiofiles.os


@dataclass
class FileInfo:
    """File metadata information."""
    size: int
    created: datetime
    modified: datetime
    accessed: datetime
    is_directory: bool
    is_file: bool
    permissions: str


class PathValidator:
    """Handles path validation and security checks."""
    
    def __init__(self, allowed_directories: List[str]):
        self.allowed_directories = [Path(d).resolve() for d in allowed_directories]
    
    def update_allowed_directories(self, directories: List[str]):
        """Update the list of allowed directories."""
        self.allowed_directories = [Path(d).resolve() for d in directories]
    
    def expand_home(self, filepath: str) -> str:
        """Expand home directory tildes in paths."""
        if filepath.startswith('~/') or filepath == '~':
            return str(Path.home() / filepath[1:])
        return filepath
    
    async def validate_path(self, requested_path: str) -> Path:
        """
        Validate and resolve a path, ensuring it's within allowed directories.
        
        Args:
            requested_path: The path to validate
            
        Returns:
            Resolved Path object
            
        Raises:
            PermissionError: If path is outside allowed directories
            FileNotFoundError: If parent directory doesn't exist (for new files)
        """
        expanded_path = self.expand_home(requested_path)
        absolute_path = Path(expanded_path).resolve()
        
        # Check if path is within allowed directories
        is_allowed = any(
            str(absolute_path).startswith(str(allowed_dir))
            for allowed_dir in self.allowed_directories
        )
        
        if not is_allowed:
            allowed_dirs_str = ', '.join(str(d) for d in self.allowed_directories)
            raise PermissionError(
                f"Access denied - path outside allowed directories: "
                f"{absolute_path} not in {allowed_dirs_str}"
            )
        
        # For new files, verify parent directory exists and is allowed
        if not absolute_path.exists():
            parent_dir = absolute_path.parent.resolve()
            parent_is_allowed = any(
                str(parent_dir).startswith(str(allowed_dir))
                for allowed_dir in self.allowed_directories
            )
            
            if not parent_is_allowed:
                allowed_dirs_str = ', '.join(str(d) for d in self.allowed_directories)
                raise PermissionError(
                    f"Access denied - parent directory outside allowed directories: "
                    f"{parent_dir} not in {allowed_dirs_str}"
                )
            
            if not parent_dir.exists():
                raise FileNotFoundError(f"Parent directory does not exist: {parent_dir}")
        
        return absolute_path


class DulayniFileSystemMCP:
    """MCP server for filesystem operations integrated with dulayni-client."""
    
    def __init__(self, allowed_directories: List[str]):
        self.path_validator = PathValidator(allowed_directories)
        self.mcp = FastMCP("dulayni-filesystem")
        self._setup_tools()
    
    def _setup_tools(self):
        """Register all MCP tools."""
        
        @self.mcp.tool()
        async def read_text_file(
            path: str,
            head: Optional[int] = None,
            tail: Optional[int] = None
        ) -> str:
            """
            Read the complete contents of a file from the file system as text.
            Handles various text encodings and provides detailed error messages
            if the file cannot be read. Use this tool when you need to examine
            the contents of a single file. Use the 'head' parameter to read only
            the first N lines of a file, or the 'tail' parameter to read only
            the last N lines of a file. Operates on the file as text regardless of extension.
            Only works within allowed directories.
            
            Args:
                path: File path to read
                head: If provided, returns only the first N lines of the file
                tail: If provided, returns only the last N lines of the file
            
            Returns:
                File contents as string
            """
            if head is not None and tail is not None:
                raise ValueError("Cannot specify both head and tail parameters simultaneously")
            
            validated_path = await self.path_validator.validate_path(path)
            
            if tail is not None:
                return await self._tail_file(validated_path, tail)
            elif head is not None:
                return await self._head_file(validated_path, head)
            else:
                async with aiofiles.open(validated_path, 'r', encoding='utf-8') as f:
                    return await f.read()
        
        @self.mcp.tool()
        async def read_media_file(path: str) -> Dict[str, Any]:
            """
            Read an image or audio file. Returns the base64 encoded data and MIME type.
            Only works within allowed directories.
            
            Args:
                path: Path to the media file
                
            Returns:
                Dictionary with 'data', 'mimeType', and 'type' keys
            """
            validated_path = await self.path_validator.validate_path(path)
            
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(str(validated_path))
            if not mime_type:
                mime_type = "application/octet-stream"
            
            # Read file as binary and encode to base64
            async with aiofiles.open(validated_path, 'rb') as f:
                content = await f.read()
            
            data = base64.b64encode(content).decode('utf-8')
            
            # Determine content type for MCP
            if mime_type.startswith("image/"):
                content_type = "image"
            elif mime_type.startswith("audio/"):
                content_type = "audio"
            else:
                content_type = "blob"
            
            return {
                "type": content_type,
                "data": data,
                "mimeType": mime_type
            }
        
        @self.mcp.tool()
        async def read_multiple_files(paths: List[str]) -> str:
            """
            Read the contents of multiple files simultaneously. This is more
            efficient than reading files one by one when you need to analyze
            or compare multiple files. Each file's content is returned with its
            path as a reference. Failed reads for individual files won't stop
            the entire operation. Only works within allowed directories.
            
            Args:
                paths: List of file paths to read
                
            Returns:
                Combined file contents with path headers
            """
            results = []
            
            for file_path in paths:
                try:
                    validated_path = await self.path_validator.validate_path(file_path)
                    async with aiofiles.open(validated_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                    results.append(f"{file_path}:\n{content}\n")
                except Exception as e:
                    results.append(f"{file_path}: Error - {str(e)}")
            
            return "\n---\n".join(results)
        
        @self.mcp.tool()
        async def write_file(path: str, content: str) -> str:
            """
            Create a new file or completely overwrite an existing file with new content.
            Use with caution as it will overwrite existing files without warning.
            Handles text content with proper encoding. Only works within allowed directories.
            
            Args:
                path: File path to write to
                content: Content to write to the file
                
            Returns:
                Success message
            """
            validated_path = await self.path_validator.validate_path(path)
            
            # Use atomic write via temporary file for safety
            temp_path = validated_path.with_suffix(validated_path.suffix + '.tmp')
            
            try:
                async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
                    await f.write(content)
                
                # Atomic rename
                await aiofiles.os.rename(temp_path, validated_path)
                
                return f"Successfully wrote to {path}"
            except Exception as e:
                # Cleanup temp file on error
                if temp_path.exists():
                    await aiofiles.os.remove(temp_path)
                raise e
        
        @self.mcp.tool()
        async def edit_file(
            path: str,
            edits: List[Dict[str, str]],
            dry_run: bool = False
        ) -> str:
            """
            Make line-based edits to a text file. Each edit replaces exact line sequences
            with new content. Returns a git-style diff showing the changes made.
            Only works within allowed directories.
            
            Args:
                path: File path to edit
                edits: List of edit operations with 'oldText' and 'newText' keys
                dry_run: Preview changes using git-style diff format
                
            Returns:
                Git-style diff showing the changes
            """
            validated_path = await self.path_validator.validate_path(path)
            
            # Read current content
            async with aiofiles.open(validated_path, 'r', encoding='utf-8') as f:
                original_content = await f.read()
            
            modified_content = original_content
            
            # Apply edits sequentially
            for edit in edits:
                old_text = edit.get('oldText', '')
                new_text = edit.get('newText', '')
                
                if old_text in modified_content:
                    modified_content = modified_content.replace(old_text, new_text, 1)
                else:
                    # Try line-by-line matching with whitespace flexibility
                    result = self._apply_flexible_edit(modified_content, old_text, new_text, apply=True)
                    if result == modified_content:  # No change means no match found
                        raise ValueError(f"Could not find exact match for edit:\n{old_text}")
                    modified_content = result
            
            # Create unified diff
            diff = self._create_unified_diff(original_content, modified_content, str(validated_path))
            
            # Write changes if not dry run
            if not dry_run:
                await self.write_file(path, modified_content)
            
            return diff
        
        @self.mcp.tool()
        async def create_directory(path: str) -> str:
            """
            Create a new directory or ensure a directory exists. Can create multiple
            nested directories in one operation. If the directory already exists,
            this operation will succeed silently. Perfect for setting up directory
            structures for projects or ensuring required paths exist. Only works within allowed directories.
            
            Args:
                path: Directory path to create
                
            Returns:
                Success message
            """
            validated_path = await self.path_validator.validate_path(path)
            validated_path.mkdir(parents=True, exist_ok=True)
            return f"Successfully created directory {path}"
        
        @self.mcp.tool()
        async def list_directory(path: str) -> str:
            """
            Get a detailed listing of all files and directories in a specified path.
            Results clearly distinguish between files and directories with [FILE] and [DIR]
            prefixes. This tool is essential for understanding directory structure and
            finding specific files within a directory. Only works within allowed directories.
            
            Args:
                path: Directory path to list
                
            Returns:
                Formatted directory listing
            """
            validated_path = await self.path_validator.validate_path(path)
            
            if not validated_path.is_dir():
                raise NotADirectoryError(f"{path} is not a directory")
            
            entries = []
            for entry in validated_path.iterdir():
                prefix = "[DIR]" if entry.is_dir() else "[FILE]"
                entries.append(f"{prefix} {entry.name}")
            
            return "\n".join(sorted(entries))
        
        @self.mcp.tool()
        async def list_directory_with_sizes(
            path: str,
            sort_by: str = "name"
        ) -> str:
            """
            Get a detailed listing of all files and directories in a specified path, including sizes.
            Results clearly distinguish between files and directories with [FILE] and [DIR]
            prefixes. This tool is useful for understanding directory structure and
            finding specific files within a directory. Only works within allowed directories.
            
            Args:
                path: Directory path to list
                sort_by: Sort entries by name or size
                
            Returns:
                Formatted directory listing with sizes
            """
            validated_path = await self.path_validator.validate_path(path)
            
            if not validated_path.is_dir():
                raise NotADirectoryError(f"{path} is not a directory")
            
            entries = []
            total_size = 0
            file_count = 0
            dir_count = 0
            
            for entry in validated_path.iterdir():
                try:
                    stat_result = entry.stat()
                    size = stat_result.st_size if entry.is_file() else 0
                    
                    if entry.is_file():
                        file_count += 1
                        total_size += size
                    else:
                        dir_count += 1
                    
                    entries.append({
                        'name': entry.name,
                        'is_dir': entry.is_dir(),
                        'size': size,
                        'mtime': stat_result.st_mtime
                    })
                except OSError:
                    # Skip entries we can't stat
                    continue
            
            # Sort entries
            if sort_by == "size":
                entries.sort(key=lambda x: x['size'], reverse=True)
            else:
                entries.sort(key=lambda x: x['name'])
            
            # Format output
            lines = []
            for entry in entries:
                prefix = "[DIR]" if entry['is_dir'] else "[FILE]"
                name = entry['name'].ljust(30)
                size_str = self._format_size(entry['size']) if not entry['is_dir'] else ""
                lines.append(f"{prefix} {name} {size_str.rjust(10)}")
            
            # Add summary
            lines.extend([
                "",
                f"Total: {file_count} files, {dir_count} directories",
                f"Combined size: {self._format_size(total_size)}"
            ])
            
            return "\n".join(lines)
        
        @self.mcp.tool()
        async def directory_tree(path: str) -> str:
            """
            Get a recursive tree view of files and directories as a JSON structure.
            Each entry includes 'name', 'type' (file/directory), and 'children' for directories.
            Files have no children array, while directories always have a children array (which may be empty).
            The output is formatted with 2-space indentation for readability. Only works within allowed directories.
            
            Args:
                path: Directory path to get tree for
                
            Returns:
                JSON string representing the directory tree
            """
            validated_path = await self.path_validator.validate_path(path)
            tree = await self._build_directory_tree(validated_path)
            return json.dumps(tree, indent=2)
        
        @self.mcp.tool()
        async def move_file(source: str, destination: str) -> str:
            """
            Move or rename files and directories. Can move files between directories
            and rename them in a single operation. If the destination exists, the
            operation will fail. Works across different directories and can be used
            for simple renaming within the same directory. Both source and destination must be within allowed directories.
            
            Args:
                source: Source path
                destination: Destination path
                
            Returns:
                Success message
            """
            validated_source = await self.path_validator.validate_path(source)
            validated_dest = await self.path_validator.validate_path(destination)
            
            if validated_dest.exists():
                raise FileExistsError(f"Destination already exists: {destination}")
            
            await aiofiles.os.rename(validated_source, validated_dest)
            return f"Successfully moved {source} to {destination}"
        
        @self.mcp.tool()
        async def search_files(
            path: str,
            pattern: str,
            exclude_patterns: List[str] = None
        ) -> str:
            """
            Recursively search for files and directories matching a pattern.
            Searches through all subdirectories from the starting path. The search
            is case-insensitive and matches partial names. Returns full paths to all
            matching items. Great for finding files when you don't know their exact location.
            Only searches within allowed directories.
            
            Args:
                path: Starting directory path
                pattern: Search pattern (case-insensitive)
                exclude_patterns: Patterns to exclude from search
                
            Returns:
                Newline-separated list of matching file paths
            """
            if exclude_patterns is None:
                exclude_patterns = []
            
            validated_path = await self.path_validator.validate_path(path)
            results = await self._search_files_recursive(
                validated_path, pattern, exclude_patterns
            )
            
            return "\n".join(results) if results else "No matches found"
        
        @self.mcp.tool()
        async def get_file_info(path: str) -> str:
            """
            Retrieve detailed metadata about a file or directory. Returns comprehensive
            information including size, creation time, last modified time, permissions,
            and type. This tool is perfect for understanding file characteristics
            without reading the actual content. Only works within allowed directories.
            
            Args:
                path: File or directory path
                
            Returns:
                Formatted file information
            """
            validated_path = await self.path_validator.validate_path(path)
            info = await self._get_file_stats(validated_path)
            
            return "\n".join(f"{key}: {value}" for key, value in info.items())
        
        @self.mcp.tool()
        async def list_allowed_directories() -> str:
            """
            Returns the list of directories that this server is allowed to access.
            Use this to understand which directories are available before trying to access files.
            
            Returns:
                List of allowed directories
            """
            directories = [str(d) for d in self.path_validator.allowed_directories]
            return f"Allowed directories:\n" + "\n".join(directories)
    
    async def _tail_file(self, file_path: Path, num_lines: int) -> str:
        """Get the last N lines of a file efficiently."""
        chunk_size = 1024
        lines = []
        
        async with aiofiles.open(file_path, 'rb') as f:
            # Get file size
            await f.seek(0, 2)  # Seek to end
            file_size = await f.tell()
            
            if file_size == 0:
                return ""
            
            position = file_size
            remaining_text = b""
            
            while position > 0 and len(lines) < num_lines:
                # Read chunk from current position backwards
                read_size = min(chunk_size, position)
                position -= read_size
                
                await f.seek(position)
                chunk = await f.read(read_size)
                
                # Combine with remaining text from previous iteration
                chunk_text = chunk + remaining_text
                text = chunk_text.decode('utf-8', errors='replace')
                
                # Split by newlines
                chunk_lines = text.split('\n')
                
                # If not at start of file, first line might be incomplete
                if position > 0:
                    remaining_text = chunk_lines[0].encode('utf-8')
                    chunk_lines = chunk_lines[1:]
                
                # Add lines to result (up to the number we need)
                for i in range(len(chunk_lines) - 1, -1, -1):
                    if len(lines) >= num_lines:
                        break
                    lines.insert(0, chunk_lines[i])
        
        return '\n'.join(lines)
    
    async def _head_file(self, file_path: Path, num_lines: int) -> str:
        """Get the first N lines of a file efficiently."""
        lines = []
        
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            async for line in f:
                lines.append(line.rstrip('\n\r'))
                if len(lines) >= num_lines:
                    break
        
        return '\n'.join(lines)
    
    def _apply_flexible_edit(self, content: str, old_text: str, new_text: str, apply: bool = False) -> Union[bool, str]:
        """Apply edit with flexible whitespace matching."""
        old_lines = old_text.split('\n')
        content_lines = content.split('\n')
        
        for i in range(len(content_lines) - len(old_lines) + 1):
            potential_match = content_lines[i:i + len(old_lines)]
            
            # Compare with normalized whitespace
            is_match = all(
                old_line.strip() == content_line.strip()
                for old_line, content_line in zip(old_lines, potential_match)
            )
            
            if is_match:
                if not apply:
                    return True
                
                # Apply the edit preserving indentation
                new_lines = new_text.split('\n')
                if new_lines and content_lines[i]:
                    # Preserve original indentation
                    original_indent = len(content_lines[i]) - len(content_lines[i].lstrip())
                    indent = ' ' * original_indent
                    new_lines = [indent + line.lstrip() if j == 0 else line 
                               for j, line in enumerate(new_lines)]
                
                content_lines[i:i + len(old_lines)] = new_lines
                return '\n'.join(content_lines)
        
        return False if not apply else content
    
    def _create_unified_diff(self, original: str, modified: str, filename: str) -> str:
        """Create a unified diff between two text strings."""
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=filename,
            tofile=filename,
            lineterm=''
        )
        
        diff_text = ''.join(diff)
        
        # Format with appropriate number of backticks
        num_backticks = 3
        while '`' * num_backticks in diff_text:
            num_backticks += 1
        
        return f"{'`' * num_backticks}diff\n{diff_text}{'`' * num_backticks}\n\n"
    
    async def _build_directory_tree(self, directory: Path) -> List[Dict[str, Any]]:
        """Build a recursive directory tree structure."""
        tree = []
        
        try:
            for entry in directory.iterdir():
                try:
                    # Validate each path before processing
                    await self.path_validator.validate_path(str(entry))
                    
                    entry_data = {
                        'name': entry.name,
                        'type': 'directory' if entry.is_dir() else 'file'
                    }
                    
                    if entry.is_dir():
                        entry_data['children'] = await self._build_directory_tree(entry)
                    
                    tree.append(entry_data)
                    
                except (PermissionError, OSError):
                    # Skip entries we can't access
                    continue
                    
        except (PermissionError, OSError):
            # Skip directories we can't read
            pass
        
        return tree
    
    async def _search_files_recursive(
        self, directory: Path, pattern: str, exclude_patterns: List[str]
    ) -> List[str]:
        """Recursively search for files matching a pattern."""
        results = []
        
        try:
            for entry in directory.iterdir():
                try:
                    # Validate path
                    await self.path_validator.validate_path(str(entry))
                    
                    # Check exclusion patterns
                    relative_path = entry.relative_to(directory)
                    if any(fnmatch.fnmatch(str(relative_path), pattern) 
                           for pattern in exclude_patterns):
                        continue
                    
                    # Check if name matches search pattern
                    if pattern.lower() in entry.name.lower():
                        results.append(str(entry))
                    
                    # Recurse into directories
                    if entry.is_dir():
                        sub_results = await self._search_files_recursive(
                            entry, pattern, exclude_patterns
                        )
                        results.extend(sub_results)
                        
                except (PermissionError, OSError):
                    # Skip entries we can't access
                    continue
                    
        except (PermissionError, OSError):
            # Skip directories we can't read
            pass
        
        return results
    
    async def _get_file_stats(self, file_path: Path) -> Dict[str, Any]:
        """Get detailed file statistics."""
        stat_result = file_path.stat()
        
        return {
            'size': stat_result.st_size,
            'created': datetime.fromtimestamp(stat_result.st_ctime).isoformat(),
            'modified': datetime.fromtimestamp(stat_result.st_mtime).isoformat(),
            'accessed': datetime.fromtimestamp(stat_result.st_atime).isoformat(),
            'is_directory': file_path.is_dir(),
            'is_file': file_path.is_file(),
            'permissions': oct(stat_result.st_mode)[-3:]
        }
    
    def _format_size(self, bytes_size: int) -> str:
        """Format file size in human-readable format."""
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        if bytes_size == 0:
            return '0 B'
        
        i = 0
        while bytes_size >= 1024 and i < len(units) - 1:
            bytes_size /= 1024
            i += 1
        
        if i == 0:
            return f"{int(bytes_size)} {units[i]}"
        else:
            return f"{bytes_size:.2f} {units[i]}"
    
    def start_server(self, host: str = "0.0.0.0", port: int = 8003):
        """Start the MCP server."""
        self.mcp.run(transport="streamable-http", stateless_http=True, host=host, port=port)


# Backward compatibility with the original simple function
def ls(path: str) -> list:
    """Use this tool to physically list all files in given `path`"""
    return os.listdir(path)


def start_server(host: str = "0.0.0.0", port: int = 8003):
    """Start the dulayni filesystem MCP server with default allowed directories."""
    # Default to current working directory if no specific directories are provided
    allowed_directories = [os.getcwd()]
    
    server = DulayniFileSystemMCP(allowed_directories)
    print(f"Starting Dulayni MCP Filesystem Server on {host}:{port}")
    print(f"Allowed directories: {', '.join(allowed_directories)}")
    
    try:
        server.start_server(host, port)
    except KeyboardInterrupt:
        print("\nShutting down server...")
    except Exception as e:
        print(f"Server error: {e}")
        sys.exit(1)


def main():
    """Main entry point for the MCP filesystem server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Dulayni MCP Filesystem Server")
    parser.add_argument(
        "directories",
        nargs='*',  # Allow 0 or more directories
        default=[os.getcwd()],  # Default to current directory
        help="Allowed directories for filesystem operations (default: current directory)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8003,
        help="Port to bind to (default: 8003)"
    )
    
    args = parser.parse_args()
    
    # If no directories specified, use current directory
    directories = args.directories if args.directories else [os.getcwd()]
    
    # Validate that all directories exist and are accessible
    for directory in directories:
        dir_path = Path(directory).expanduser().resolve()
        if not dir_path.exists():
            print(f"Error: Directory does not exist: {directory}")
            sys.exit(1)
        if not dir_path.is_dir():
            print(f"Error: Path is not a directory: {directory}")
            sys.exit(1)
    
    # Create and start the server
    server = DulayniFileSystemMCP(directories)
    print(f"Starting Dulayni MCP Filesystem Server on {args.host}:{args.port}")
    print(f"Allowed directories: {', '.join(directories)}")
    
    try:
        server.start_server(args.host, args.port)
    except KeyboardInterrupt:
        print("\nShutting down server...")
    except Exception as e:
        print(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
