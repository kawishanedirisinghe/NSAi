
import os
import re
import glob
import asyncio
import subprocess
import tempfile
import json
import shutil
import psutil
import requests
import socket
import platform
import time
import threading
from pathlib import Path
from typing import Any, List, Optional, Dict, Union
from app.tool import BaseTool
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Enhanced shell session management
shell_sessions = {}

class MessageNotifyUser(BaseTool):
    name: str = "message_notify_user"
    description: str = "Send a message to user without requiring a response. Use for acknowledging receipt of messages, providing progress updates, reporting task completion, or explaining changes in approach."
    parameters: dict = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Message text to display to user"
            },
            "attachments": {
                "anyOf": [
                    {"type": "string"},
                    {"items": {"type": "string"}, "type": "array"}
                ],
                "description": "(Optional) List of attachments to show to user, can be file paths or URLs"
            },
            "message_type": {
                "type": "string",
                "enum": ["info", "success", "warning", "error"],
                "description": "(Optional) Type of message for styling"
            }
        },
        "required": ["text"]
    }

    async def execute(self, *, text: str, attachments: Optional[List[str]] = None, message_type: str = "info", **kwargs: Any) -> str:
        icons = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌"
        }
        icon = icons.get(message_type, "📢")
        result = f"{icon} **{message_type.title()}**: {text}"
        if attachments:
            result += f"\n\n📎 **Attachments**:\n"
            for attachment in attachments:
                result += f"- {attachment}\n"
        return result

class MessageAskUser(BaseTool):
    name: str = "message_ask_user"
    description: str = "Ask user a question and wait for response. Use for requesting clarification, asking for confirmation, or gathering additional information."
    parameters: dict = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Question text to present to user"
            },
            "attachments": {
                "anyOf": [
                    {"type": "string"},
                    {"items": {"type": "string"}, "type": "array"}
                ],
                "description": "(Optional) List of question-related files or reference materials"
            },
            "suggest_user_takeover": {
                "type": "string",
                "enum": ["none", "browser", "terminal", "file_editor"],
                "description": "(Optional) Suggested operation for user takeover"
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "(Optional) List of suggested options for user to choose from"
            }
        },
        "required": ["text"]
    }

    async def execute(self, *, text: str, attachments: Optional[List[str]] = None, suggest_user_takeover: str = "none", options: Optional[List[str]] = None, **kwargs: Any) -> str:
        result = f"❓ **Question**: {text}"
        if attachments:
            result += f"\n\n📎 **Reference Materials**:\n"
            for attachment in attachments:
                result += f"- {attachment}\n"
        if options:
            result += f"\n\n💡 **Suggested Options**:\n"
            for i, option in enumerate(options, 1):
                result += f"{i}. {option}\n"
        if suggest_user_takeover != "none":
            result += f"\n💡 **Suggestion**: Consider {suggest_user_takeover} takeover for this task."
        return result

class FileRead(BaseTool):
    name: str = "file_read"
    description: str = "Read file content. Use for checking file contents, analyzing logs, or reading configuration files."
    parameters: dict = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Absolute path of the file to read"
            },
            "start_line": {
                "type": "integer",
                "description": "(Optional) Starting line to read from, 0-based"
            },
            "end_line": {
                "type": "integer",
                "description": "(Optional) Ending line number (exclusive)"
            },
            "sudo": {
                "type": "boolean",
                "description": "(Optional) Whether to use sudo privileges"
            },
            "encoding": {
                "type": "string",
                "description": "(Optional) File encoding (default: utf-8)"
            }
        },
        "required": ["file"]
    }

    async def execute(self, *, file: str, start_line: Optional[int] = None, end_line: Optional[int] = None, sudo: bool = False, encoding: str = "utf-8", **kwargs: Any) -> str:
        try:
            if sudo:
                cmd = ["sudo", "cat", file]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    return f"❌ Error reading file '{file}': {result.stderr}"
                content = result.stdout
            else:
                with open(file, 'r', encoding=encoding) as f:
                    content = f.read()
            
            lines = content.split('\n')
            
            if start_line is not None or end_line is not None:
                start = start_line or 0
                end = end_line or len(lines)
                lines = lines[start:end]
                content = '\n'.join(lines)
                result = f"📖 **File Content** (lines {start}-{end}):\n```\n{content}\n```"
            else:
                result = f"📖 **File Content**:\n```\n{content}\n```"
            
            return result
            
        except FileNotFoundError:
            return f"❌ File '{file}' not found"
        except PermissionError:
            return f"❌ Permission denied reading file '{file}'"
        except Exception as e:
            return f"❌ Error reading file '{file}': {str(e)}"

class FileWrite(BaseTool):
    name: str = "file_write"
    description: str = "Overwrite or append content to a file. Use for creating new files, appending content, or modifying existing files."
    parameters: dict = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Absolute path of the file to write to"
            },
            "content": {
                "type": "string",
                "description": "Text content to write"
            },
            "append": {
                "type": "boolean",
                "description": "(Optional) Whether to append to existing content"
            },
            "leading_newline": {
                "type": "boolean",
                "description": "(Optional) Whether to add a newline before content"
            },
            "trailing_newline": {
                "type": "boolean",
                "description": "(Optional) Whether to add a newline after content"
            },
            "sudo": {
                "type": "boolean",
                "description": "(Optional) Whether to use sudo privileges"
            },
            "encoding": {
                "type": "string",
                "description": "(Optional) File encoding (default: utf-8)"
            }
        },
        "required": ["file", "content"]
    }

    async def execute(self, *, file: str, content: str, append: bool = False, leading_newline: bool = False, trailing_newline: bool = False, sudo: bool = False, encoding: str = "utf-8", **kwargs: Any) -> str:
        try:
            if leading_newline:
                content = '\n' + content
            if trailing_newline:
                content = content + '\n'
            
            if sudo:
                # Create temporary file
                with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding=encoding) as temp_file:
                    temp_file.write(content)
                    temp_file_path = temp_file.name
                
                # Copy to destination with sudo
                cmd = ["sudo", "cp", temp_file_path, file]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                # Clean up temp file
                os.unlink(temp_file_path)
                
                if result.returncode != 0:
                    return f"❌ Error writing file '{file}': {result.stderr}"
            else:
                mode = 'a' if append else 'w'
                with open(file, mode, encoding=encoding) as f:
                    f.write(content)
            
            action = "appended to" if append else "written to"
            return f"✅ Content {action} file '{file}'"
            
        except Exception as e:
            return f"❌ Error writing file '{file}': {str(e)}"

class FileStrReplace(BaseTool):
    name: str = "file_str_replace"
    description: str = "Replace specified string in a file. Use for updating specific content in files or fixing errors in code."
    parameters: dict = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Absolute path of the file to modify"
            },
            "old_str": {
                "type": "string",
                "description": "String to replace"
            },
            "new_str": {
                "type": "string",
                "description": "New string to replace with"
            },
            "sudo": {
                "type": "boolean",
                "description": "(Optional) Whether to use sudo privileges"
            },
            "regex": {
                "type": "boolean",
                "description": "(Optional) Whether to treat old_str as regex pattern"
            }
        },
        "required": ["file", "old_str", "new_str"]
    }

    async def execute(self, *, file: str, old_str: str, new_str: str, sudo: bool = False, regex: bool = False, **kwargs: Any) -> str:
        try:
            if sudo:
                cmd = ["sudo", "cat", file]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    return f"❌ Error reading file '{file}': {result.stderr}"
                content = result.stdout
            else:
                with open(file, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            if regex:
                import re
                new_content = re.sub(old_str, new_str, content)
            else:
                new_content = content.replace(old_str, new_str)
            
            if new_content == content:
                return f"⚠️ No changes made to file '{file}' (string not found)"
            
            if sudo:
                # Create temporary file
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
                    temp_file.write(new_content)
                    temp_file_path = temp_file.name
                
                # Copy to destination with sudo
                cmd = ["sudo", "cp", temp_file_path, file]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                # Clean up temp file
                os.unlink(temp_file_path)
                
                if result.returncode != 0:
                    return f"❌ Error writing file '{file}': {result.stderr}"
            else:
                with open(file, 'w', encoding='utf-8') as f:
                    f.write(new_content)
            
            return f"✅ String replaced in file '{file}'"
            
        except Exception as e:
            return f"❌ Error modifying file '{file}': {str(e)}"

class FileFindInContent(BaseTool):
    name: str = "file_find_in_content"
    description: str = "Search for matching text within file content. Use for finding specific content or patterns in files."
    parameters: dict = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Absolute path of the file to search in"
            },
            "regex": {
                "type": "string",
                "description": "Regex pattern to search for"
            },
            "sudo": {
                "type": "boolean",
                "description": "(Optional) Whether to use sudo privileges"
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "(Optional) Whether search is case sensitive"
            }
        },
        "required": ["file", "regex"]
    }

    async def execute(self, *, file: str, regex: str, sudo: bool = False, case_sensitive: bool = True, **kwargs: Any) -> str:
        try:
            if sudo:
                cmd = ["sudo", "cat", file]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    return f"❌ Error reading file '{file}': {result.stderr}"
                content = result.stdout
            else:
                with open(file, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            import re
            flags = 0 if case_sensitive else re.IGNORECASE
            pattern = re.compile(regex, flags)
            matches = pattern.finditer(content)
            
            lines = content.split('\n')
            results = []
            
            for match in matches:
                start_pos = match.start()
                line_num = content[:start_pos].count('\n') + 1
                line_content = lines[line_num - 1] if line_num <= len(lines) else "Unknown line"
                results.append(f"Line {line_num}: {line_content.strip()}")
            
            if results:
                result_text = "\n".join(results[:10])  # Limit to first 10 matches
                if len(results) > 10:
                    result_text += f"\n... and {len(results) - 10} more matches"
                return f"🔍 **Found {len(results)} matches** in '{file}':\n```\n{result_text}\n```"
            else:
                return f"🔍 No matches found in file '{file}'"
            
        except Exception as e:
            return f"❌ Error searching file '{file}': {str(e)}"

class FileFindByName(BaseTool):
    name: str = "file_find_by_name"
    description: str = "Find files by name pattern in specified directory. Use for locating files with specific naming patterns."
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to search in"
            },
            "glob": {
                "type": "string",
                "description": "Glob pattern to match file names"
            },
            "recursive": {
                "type": "boolean",
                "description": "(Optional) Whether to search recursively"
            },
            "include_hidden": {
                "type": "boolean",
                "description": "(Optional) Whether to include hidden files"
            }
        },
        "required": ["path", "glob"]
    }

    async def execute(self, *, path: str, glob: str, recursive: bool = False, include_hidden: bool = False, **kwargs: Any) -> str:
        try:
            if not os.path.exists(path):
                return f"❌ Directory '{path}' does not exist"
            
            pattern = os.path.join(path, glob)
            if recursive:
                pattern = os.path.join(path, "**", glob)
            
            files = []
            for file_path in Path(path).rglob(glob) if recursive else Path(path).glob(glob):
                if not include_hidden and file_path.name.startswith('.'):
                    continue
                files.append(str(file_path))
            
            if files:
                result_text = "\n".join(files[:20])  # Limit to first 20 files
                if len(files) > 20:
                    result_text += f"\n... and {len(files) - 20} more files"
                return f"📁 **Found {len(files)} files** matching '{glob}' in '{path}':\n```\n{result_text}\n```"
            else:
                return f"📁 No files found matching '{glob}' in '{path}'"
            
        except Exception as e:
            return f"❌ Error searching for files: {str(e)}"

class PythonExec(BaseTool):
    name: str = "python_exec"
    description: str = "Execute Python code in a controlled environment. Use for running Python scripts, data analysis, or testing code."
    parameters: dict = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute"
            },
            "timeout": {
                "type": "integer",
                "description": "(Optional) Execution timeout in seconds (default: 30)"
            },
            "working_dir": {
                "type": "string",
                "description": "(Optional) Working directory for execution"
            },
            "capture_output": {
                "type": "boolean",
                "description": "(Optional) Whether to capture output (default: true)"
            }
        },
        "required": ["code"]
    }

    async def execute(self, *, code: str, timeout: int = 30, working_dir: Optional[str] = None, capture_output: bool = True, **kwargs: Any) -> str:
        try:
            # Create temporary Python file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
                temp_file.write(code)
                temp_file_path = temp_file.name
            
            # Execute Python file
            cmd = ["python3", temp_file_path]
            cwd = working_dir if working_dir else os.getcwd()
            
            result = subprocess.run(
                cmd, 
                capture_output=capture_output, 
                text=True, 
                timeout=timeout,
                cwd=cwd
            )
            
            # Clean up temp file
            os.unlink(temp_file_path)
            
            output = []
            if result.stdout:
                output.append(f"📤 **Output**:\n{result.stdout}")
            if result.stderr:
                output.append(f"⚠️ **Errors**:\n{result.stderr}")
            
            if output:
                return "\n\n".join(output)
            else:
                return "✅ Python code executed successfully (no output)"
            
        except subprocess.TimeoutExpired:
            return f"⏰ Python execution timed out after {timeout} seconds"
        except Exception as e:
            return f"❌ Error executing Python code: {str(e)}"

class ShellExec(BaseTool):
    name: str = "shell_exec"
    description: str = "Execute commands in a specified shell session. Use for running code, installing packages, or managing files."
    parameters: dict = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Shell session ID"
            },
            "exec_dir": {
                "type": "string",
                "description": "Directory to execute command in"
            },
            "command": {
                "type": "string",
                "description": "Command to execute"
            },
            "timeout": {
                "type": "integer",
                "description": "(Optional) Command timeout in seconds (default: 60)"
            },
            "background": {
                "type": "boolean",
                "description": "(Optional) Whether to run command in background"
            }
        },
        "required": ["id", "exec_dir", "command"]
    }

    async def execute(self, *, id: str, exec_dir: str, command: str, timeout: int = 60, background: bool = False, **kwargs: Any) -> str:
        try:
            if id not in shell_sessions:
                shell_sessions[id] = {
                    'process': None,
                    'output': [],
                    'working_dir': exec_dir,
                    'created_at': time.time()
                }
            
            session = shell_sessions[id]
            session['working_dir'] = exec_dir
            
            if background:
                # Run command in background
                process = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=exec_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                session['process'] = process
                return f"🔄 Command started in background (PID: {process.pid})"
            else:
                # Run command and wait for completion
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=exec_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                
                output = []
                if result.stdout:
                    output.append(f"📤 **Output**:\n{result.stdout}")
                if result.stderr:
                    output.append(f"⚠️ **Errors**:\n{result.stderr}")
                
                session['output'].append({
                    'command': command,
                    'returncode': result.returncode,
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'timestamp': time.time()
                })
                
                if output:
                    return "\n\n".join(output)
                else:
                    return f"✅ Command executed successfully (return code: {result.returncode})"
            
        except subprocess.TimeoutExpired:
            return f"⏰ Command timed out after {timeout} seconds"
        except Exception as e:
            return f"❌ Error executing command: {str(e)}"

class ShellView(BaseTool):
    name: str = "shell_view"
    description: str = "View the content of a specified shell session. Use for checking command execution results or monitoring output."
    parameters: dict = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Shell session ID"
            },
            "last_n": {
                "type": "integer",
                "description": "(Optional) Number of recent commands to show (default: 5)"
            }
        },
        "required": ["id"]
    }

    async def execute(self, *, id: str, last_n: int = 5, **kwargs: Any) -> str:
        try:
            if id not in shell_sessions:
                return f"❌ Shell session '{id}' not found"
            
            session = shell_sessions[id]
            output = session['output'][-last_n:] if session['output'] else []
            
            if not output:
                return f"📋 No command history for session '{id}'"
            
            result = f"📋 **Shell Session '{id}'** (last {len(output)} commands):\n\n"
            for i, cmd_output in enumerate(output, 1):
                result += f"**Command {i}**: `{cmd_output['command']}`\n"
                result += f"**Return Code**: {cmd_output['returncode']}\n"
                if cmd_output['stdout']:
                    result += f"**Output**:\n```\n{cmd_output['stdout']}\n```\n"
                if cmd_output['stderr']:
                    result += f"**Errors**:\n```\n{cmd_output['stderr']}\n```\n"
                result += "---\n"
            
            return result
            
        except Exception as e:
            return f"❌ Error viewing shell session: {str(e)}"

class ShellWait(BaseTool):
    name: str = "shell_wait"
    description: str = "Wait for the running process in a specified shell session to return. Use after running commands that require longer runtime."
    parameters: dict = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Shell session ID"
            },
            "seconds": {
                "type": "integer",
                "description": "(Optional) Maximum seconds to wait (default: 0 for indefinite)"
            }
        },
        "required": ["id"]
    }

    async def execute(self, *, id: str, seconds: int = 0, **kwargs: Any) -> str:
        try:
            if id not in shell_sessions:
                return f"❌ Shell session '{id}' not found"
            
            session = shell_sessions[id]
            process = session['process']
            
            if not process:
                return f"📋 No running process in session '{id}'"
            
            try:
                stdout, stderr = process.communicate(timeout=seconds if seconds > 0 else None)
                
                session['output'].append({
                    'command': 'Background process completed',
                    'returncode': process.returncode,
                    'stdout': stdout,
                    'stderr': stderr,
                    'timestamp': time.time()
                })
                
                session['process'] = None
                
                output = []
                if stdout:
                    output.append(f"📤 **Output**:\n{stdout}")
                if stderr:
                    output.append(f"⚠️ **Errors**:\n{stderr}")
                
                if output:
                    return "\n\n".join(output)
                else:
                    return f"✅ Background process completed (return code: {process.returncode})"
                
            except subprocess.TimeoutExpired:
                return f"⏰ Process still running after {seconds} seconds"
            
        except Exception as e:
            return f"❌ Error waiting for process: {str(e)}"

class FileCopy(BaseTool):
    name: str = "file_copy"
    description: str = "Copy files or directories from source to destination. Use for backing up files or creating duplicates."
    parameters: dict = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Source file or directory path"
            },
            "destination": {
                "type": "string",
                "description": "Destination path"
            },
            "recursive": {
                "type": "boolean",
                "description": "(Optional) Whether to copy directories recursively"
            },
            "preserve_attributes": {
                "type": "boolean",
                "description": "(Optional) Whether to preserve file attributes"
            }
        },
        "required": ["source", "destination"]
    }

    async def execute(self, *, source: str, destination: str, recursive: bool = False, preserve_attributes: bool = False, **kwargs: Any) -> str:
        try:
            if not os.path.exists(source):
                return f"❌ Source '{source}' does not exist"
            
            if os.path.isdir(source) and recursive:
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination) if preserve_attributes else shutil.copy(source, destination)
            
            return f"✅ Copied '{source}' to '{destination}'"
            
        except Exception as e:
            return f"❌ Error copying '{source}' to '{destination}': {str(e)}"

class FileDelete(BaseTool):
    name: str = "file_delete"
    description: str = "Delete files or directories. Use for cleaning up temporary files or removing unwanted content."
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to file or directory to delete"
            },
            "recursive": {
                "type": "boolean",
                "description": "(Optional) Whether to delete directories recursively"
            },
            "force": {
                "type": "boolean",
                "description": "(Optional) Whether to force deletion without confirmation"
            }
        },
        "required": ["path"]
    }

    async def execute(self, *, path: str, recursive: bool = False, force: bool = False, **kwargs: Any) -> str:
        try:
            if not os.path.exists(path):
                return f"❌ Path '{path}' does not exist"
            
            if os.path.isdir(path):
                if recursive:
                    shutil.rmtree(path)
                else:
                    os.rmdir(path)
            else:
                os.remove(path)
            
            return f"✅ Deleted '{path}'"
            
        except Exception as e:
            return f"❌ Error deleting '{path}': {str(e)}"

class DirectoryCreate(BaseTool):
    name: str = "directory_create"
    description: str = "Create directories. Use for organizing files or setting up project structure."
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to create"
            },
            "parents": {
                "type": "boolean",
                "description": "(Optional) Whether to create parent directories"
            },
            "mode": {
                "type": "integer",
                "description": "(Optional) Directory permissions (octal)"
            }
        },
        "required": ["path"]
    }

    async def execute(self, *, path: str, parents: bool = True, mode: Optional[int] = None, **kwargs: Any) -> str:
        try:
            os.makedirs(path, mode=mode, exist_ok=True)
            return f"✅ Created directory '{path}'"
            
        except Exception as e:
            return f"❌ Error creating directory '{path}': {str(e)}"

class ProcessList(BaseTool):
    name: str = "process_list"
    description: str = "List running processes. Use for monitoring system activity or finding specific processes."
    parameters: dict = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Optional pattern to filter processes"
            },
            "user": {
                "type": "string",
                "description": "Optional user to filter processes by"
            },
            "limit": {
                "type": "integer",
                "description": "Optional limit on number of processes to show"
            }
        },
        "required": []
    }

    async def execute(self, *, pattern: str = "", user: str = "", limit: int = 20, **kwargs: Any) -> str:
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent']):
                try:
                    proc_info = proc.info
                    if pattern and pattern.lower() not in proc_info['name'].lower():
                        continue
                    if user and proc_info['username'] != user:
                        continue
                    processes.append(proc_info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Sort by CPU usage
            processes.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
            processes = processes[:limit]
            
            if processes:
                result = "🖥️ **Running Processes**:\n"
                result += "PID\tName\t\tUser\t\tCPU%\tMemory%\n"
                result += "-" * 60 + "\n"
                for proc in processes:
                    result += f"{proc['pid']}\t{proc['name'][:15]:<15}\t{proc['username']:<10}\t{proc['cpu_percent']:.1f}\t{proc['memory_percent']:.1f}\n"
                return result
            else:
                return "🖥️ No processes found matching criteria"
            
        except Exception as e:
            return f"❌ Error listing processes: {str(e)}"

class SystemInfo(BaseTool):
    name: str = "system_info"
    description: str = "Get system information. Use for monitoring system resources or debugging."
    parameters: dict = {
        "type": "object",
        "properties": {
            "detailed": {
                "type": "boolean",
                "description": "(Optional) Whether to include detailed information"
            }
        },
        "required": []
    }

    async def execute(self, *, detailed: bool = False, **kwargs: Any) -> str:
        try:
            info = {}
            
            # Basic system info
            info['platform'] = platform.platform()
            info['python_version'] = platform.python_version()
            info['architecture'] = platform.architecture()[0]
            
            # CPU info
            info['cpu_count'] = psutil.cpu_count()
            info['cpu_percent'] = psutil.cpu_percent(interval=1)
            
            # Memory info
            memory = psutil.virtual_memory()
            info['memory_total'] = f"{memory.total // (1024**3):.1f} GB"
            info['memory_available'] = f"{memory.available // (1024**3):.1f} GB"
            info['memory_percent'] = f"{memory.percent:.1f}%"
            
            # Disk info
            disk = psutil.disk_usage('/')
            info['disk_total'] = f"{disk.total // (1024**3):.1f} GB"
            info['disk_free'] = f"{disk.free // (1024**3):.1f} GB"
            info['disk_percent'] = f"{disk.percent:.1f}%"
            
            # Network info
            network = psutil.net_io_counters()
            info['network_bytes_sent'] = f"{network.bytes_sent // (1024**2):.1f} MB"
            info['network_bytes_recv'] = f"{network.bytes_recv // (1024**2):.1f} MB"
            
            if detailed:
                # Additional detailed info
                info['boot_time'] = datetime.fromtimestamp(psutil.boot_time()).strftime('%Y-%m-%d %H:%M:%S')
                info['hostname'] = socket.gethostname()
                info['ip_address'] = socket.gethostbyname(socket.gethostname())
                
                # Load average (Linux only)
                try:
                    load_avg = os.getloadavg()
                    info['load_average'] = f"{load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}"
                except:
                    info['load_average'] = "N/A"
            
            result = "🖥️ **System Information**:\n"
            for key, value in info.items():
                result += f"**{key.replace('_', ' ').title()}**: {value}\n"
            
            return result
            
        except Exception as e:
            return f"❌ Error getting system information: {str(e)}"

class NetworkTest(BaseTool):
    name: str = "network_test"
    description: str = "Test network connectivity and performance. Use for diagnosing network issues or checking connectivity."
    parameters: dict = {
        "type": "object",
        "properties": {
            "host": {
                "type": "string",
                "description": "Host to test connectivity to"
            },
            "port": {
                "type": "integer",
                "description": "(Optional) Port to test (default: 80)"
            },
            "timeout": {
                "type": "integer",
                "description": "(Optional) Timeout in seconds (default: 5)"
            }
        },
        "required": ["host"]
    }

    async def execute(self, *, host: str, port: int = 80, timeout: int = 5, **kwargs: Any) -> str:
        try:
            # Test basic connectivity
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            start_time = time.time()
            result = sock.connect_ex((host, port))
            end_time = time.time()
            
            sock.close()
            
            if result == 0:
                response_time = (end_time - start_time) * 1000
                return f"✅ **Network Test**: {host}:{port} is reachable (Response time: {response_time:.2f}ms)"
            else:
                return f"❌ **Network Test**: {host}:{port} is not reachable"
            
        except Exception as e:
            return f"❌ Error testing network connectivity: {str(e)}"

class WebRequest(BaseTool):
    name: str = "web_request"
    description: str = "Make HTTP requests to web services. Use for API calls, web scraping, or checking web services."
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to make request to"
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE", "HEAD"],
                "description": "(Optional) HTTP method (default: GET)"
            },
            "headers": {
                "type": "object",
                "description": "(Optional) HTTP headers to include"
            },
            "data": {
                "type": "string",
                "description": "(Optional) Data to send with request"
            },
            "timeout": {
                "type": "integer",
                "description": "(Optional) Request timeout in seconds (default: 30)"
            }
        },
        "required": ["url"]
    }

    async def execute(self, *, url: str, method: str = "GET", headers: Optional[Dict] = None, data: Optional[str] = None, timeout: int = 30, **kwargs: Any) -> str:
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers or {},
                data=data,
                timeout=timeout
            )
            
            result = f"🌐 **HTTP {method} Request**: {url}\n"
            result += f"**Status Code**: {response.status_code}\n"
            result += f"**Response Time**: {response.elapsed.total_seconds():.2f}s\n"
            
            if response.headers:
                result += f"**Response Headers**:\n"
                for key, value in list(response.headers.items())[:5]:  # Show first 5 headers
                    result += f"  {key}: {value}\n"
            
            if response.text:
                # Truncate response if too long
                text = response.text[:1000] + "..." if len(response.text) > 1000 else response.text
                result += f"**Response Body**:\n```\n{text}\n```"
            
            return result
            
        except requests.exceptions.Timeout:
            return f"⏰ Request to {url} timed out after {timeout} seconds"
        except requests.exceptions.ConnectionError:
            return f"❌ Connection error to {url}"
        except Exception as e:
            return f"❌ Error making request to {url}: {str(e)}"

class FileCompress(BaseTool):
    name: str = "file_compress"
    description: str = "Compress files or directories into archive formats. Use for creating backups or reducing file sizes."
    parameters: dict = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Source file or directory to compress"
            },
            "destination": {
                "type": "string",
                "description": "Destination archive file path"
            },
            "format": {
                "type": "string",
                "enum": ["zip", "tar", "tar.gz"],
                "description": "(Optional) Archive format (default: zip)"
            }
        },
        "required": ["source", "destination"]
    }

    async def execute(self, *, source: str, destination: str, format: str = "zip", **kwargs: Any) -> str:
        try:
            if not os.path.exists(source):
                return f"❌ Source '{source}' does not exist"
            
            if format == "zip":
                if os.path.isdir(source):
                    shutil.make_archive(destination.replace('.zip', ''), 'zip', source)
                else:
                    shutil.make_archive(destination.replace('.zip', ''), 'zip', os.path.dirname(source), os.path.basename(source))
            elif format == "tar":
                shutil.make_archive(destination.replace('.tar', ''), 'tar', source)
            elif format == "tar.gz":
                shutil.make_archive(destination.replace('.tar.gz', ''), 'gztar', source)
            
            return f"✅ Compressed '{source}' to '{destination}'"
            
        except Exception as e:
            return f"❌ Error compressing '{source}': {str(e)}"

class FileExtract(BaseTool):
    name: str = "file_extract"
    description: str = "Extract files from archive formats. Use for unpacking compressed files or restoring backups."
    parameters: dict = {
        "type": "object",
        "properties": {
            "archive": {
                "type": "string",
                "description": "Archive file to extract"
            },
            "destination": {
                "type": "string",
                "description": "Destination directory for extracted files"
            },
            "format": {
                "type": "string",
                "enum": ["auto", "zip", "tar", "tar.gz"],
                "description": "(Optional) Archive format (default: auto)"
            }
        },
        "required": ["archive", "destination"]
    }

    async def execute(self, *, archive: str, destination: str, format: str = "auto", **kwargs: Any) -> str:
        try:
            if not os.path.exists(archive):
                return f"❌ Archive '{archive}' does not exist"
            
            os.makedirs(destination, exist_ok=True)
            
            if format == "auto":
                if archive.endswith('.zip'):
                    format = "zip"
                elif archive.endswith('.tar.gz'):
                    format = "tar.gz"
                elif archive.endswith('.tar'):
                    format = "tar"
            
            if format == "zip":
                import zipfile
                with zipfile.ZipFile(archive, 'r') as zip_ref:
                    zip_ref.extractall(destination)
            elif format in ["tar", "tar.gz"]:
                import tarfile
                mode = 'r:gz' if format == "tar.gz" else 'r'
                with tarfile.open(archive, mode) as tar_ref:
                    tar_ref.extractall(destination)
            
            return f"✅ Extracted '{archive}' to '{destination}'"
            
        except Exception as e:
            return f"❌ Error extracting '{archive}': {str(e)}"

# Export all tools
__all__ = [
    'MessageNotifyUser',
    'MessageAskUser', 
    'FileRead',
    'FileWrite',
    'FileStrReplace',
    'FileFindInContent',
    'FileFindByName',
    'PythonExec',
    'ShellExec',
    'ShellView',
    'ShellWait',
    'FileCopy',
    'FileDelete',
    'DirectoryCreate',
    'ProcessList',
    'SystemInfo',
    'NetworkTest',
    'WebRequest',
    'FileCompress',
    'FileExtract'
]
